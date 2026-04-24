"""Strategic recommendations service (US-7.5).

Generates AI-backed recommendations across four categories (pricing, advertising,
inventory, content) using an organization-wide snapshot of recent performance.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.advertising import AdvertisingCampaign, AdvertisingMetrics
from app.models.amazon_account import AmazonAccount
from app.models.inventory import InventoryData
from app.models.product import Product
from app.models.sales_data import SalesData
from app.models.strategic_recommendation import StrategicRecommendation
from app.services.data_extraction import DAILY_TOTAL_ASIN

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"pricing", "advertising", "inventory", "content"}
VALID_STATUSES = {"pending", "implemented", "dismissed"}
VALID_PRIORITIES = {"high", "medium", "low"}


def _priority_to_score(priority: Optional[str]) -> int:
    return {"high": 100, "medium": 50, "low": 10}.get((priority or "medium").lower(), 50)


def _sanitize_category(value: Optional[str]) -> str:
    val = (value or "").strip().lower()
    return val if val in VALID_CATEGORIES else "pricing"


def _sanitize_priority(value: Optional[str]) -> str:
    val = (value or "").strip().lower()
    return val if val in VALID_PRIORITIES else "medium"


def _normalize_asin(value: Optional[str]) -> Optional[str]:
    val = (value or "").strip().upper()
    return val or None


class _StrategicRecAnalysisService:
    """Claude wrapper that turns an org snapshot into 3-6 recommendations."""

    def __init__(self, api_key: str):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)

    def analyze(self, *, snapshot: Dict[str, Any], language: str = "en") -> Dict[str, Any]:
        lang_instruction = (
            "Respond entirely in Italian." if language == "it" else "Respond entirely in English."
        )
        prompt = f"""You are an Amazon marketplace strategist advising a seller on weekly priorities.

{lang_instruction}

Organization snapshot (last {snapshot.get('lookback_days')} days):
{json.dumps(snapshot, ensure_ascii=False, indent=2, default=str)}

Return a JSON object with exactly this structure:
{{
  "summary": "2-4 sentence executive summary",
  "recommendations": [
    {{
      "category": "pricing|advertising|inventory|content",
      "priority": "high|medium|low",
      "title": "short imperative title (< 90 chars)",
      "rationale": "why this action follows from the snapshot, quoting concrete numbers",
      "expected_impact": "expected business impact with a directional estimate",
      "context": {{"account_id": "<uuid if account-specific, else omit>", "asins": ["B000..."]}}
    }}
  ]
}}

Rules:
- Produce 3-6 recommendations ordered by priority.
- Use exactly one of the four categories above per recommendation.
- Ground every recommendation in the numbers from the snapshot; do not invent data.
- If `snapshot.filters.selected_asin` is present, sales and inventory are scoped to that ASIN.
- If `snapshot.filters.selected_asin` is present, ads metrics remain account-level unless a field explicitly says they are ASIN-level.
- If a recommendation targets a single account or ASIN, include those identifiers in `context`.
- Return ONLY the JSON object, no markdown or commentary."""

        message = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2200,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text.strip()
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            response_text = "\n".join(lines)

        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error("Strategic rec AI returned invalid JSON: %s", e)
            raise ValueError(f"AI returned invalid JSON: {e}")

        recs = []
        for rec in payload.get("recommendations", []) or []:
            recs.append(
                {
                    "category": _sanitize_category(rec.get("category")),
                    "priority": _sanitize_priority(rec.get("priority")),
                    "title": (rec.get("title") or "").strip()[:500],
                    "rationale": (rec.get("rationale") or "").strip(),
                    "expected_impact": (rec.get("expected_impact") or "").strip() or None,
                    "context": rec.get("context") if isinstance(rec.get("context"), dict) else None,
                }
            )
        payload["recommendations"] = recs
        return payload


class StrategicRecommendationsService:
    """CRUD + generation of strategic recommendations for an organization."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------------------------------------------------------- queries
    async def list_recommendations(
        self,
        org_id: UUID,
        *,
        status: Optional[str] = None,
        category: Optional[str] = None,
        account_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[StrategicRecommendation]:
        stmt = select(StrategicRecommendation).where(
            StrategicRecommendation.organization_id == org_id
        )
        if status:
            if status not in VALID_STATUSES:
                raise ValueError(f"Invalid status: {status}")
            stmt = stmt.where(StrategicRecommendation.status == status)
        if category:
            if category not in VALID_CATEGORIES:
                raise ValueError(f"Invalid category: {category}")
            stmt = stmt.where(StrategicRecommendation.category == category)
        if account_id is not None:
            stmt = stmt.where(StrategicRecommendation.account_id == account_id)
        stmt = stmt.order_by(
            StrategicRecommendation.generated_at.desc(),
            StrategicRecommendation.priority_score.desc(),
        ).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get(self, rec_id: UUID, org_id: UUID) -> Optional[StrategicRecommendation]:
        result = await self.db.execute(
            select(StrategicRecommendation).where(
                StrategicRecommendation.id == rec_id,
                StrategicRecommendation.organization_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    async def mark_status(
        self,
        rec_id: UUID,
        org_id: UUID,
        status: str,
        *,
        outcome_notes: Optional[str] = None,
    ) -> StrategicRecommendation:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        rec = await self.get(rec_id, org_id)
        if rec is None:
            raise ValueError("Recommendation not found")
        rec.status = status
        now = datetime.utcnow()
        if status == "implemented":
            rec.implemented_at = now
        elif status == "dismissed":
            rec.dismissed_at = now
        if outcome_notes is not None:
            rec.outcome_notes = outcome_notes
        await self.db.flush()
        await self.db.refresh(rec)
        return rec

    # --------------------------------------------------------------- generate
    async def generate_for_organization(
        self,
        org_id: UUID,
        *,
        user_id: Optional[UUID] = None,
        lookback_days: int = 28,
        language: str = "en",
        account_id: Optional[UUID] = None,
        asin: Optional[str] = None,
    ) -> List[StrategicRecommendation]:
        """Build snapshot, call Claude, persist recommendation rows."""
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")

        normalized_asin = _normalize_asin(asin)
        snapshot = await self._build_org_snapshot(
            org_id,
            lookback_days,
            account_id=account_id,
            asin=normalized_asin,
        )
        if not snapshot["accounts"]:
            logger.info("No accounts found for org %s; skipping generation", org_id)
            return []

        ai = _StrategicRecAnalysisService(settings.ANTHROPIC_API_KEY)
        payload = ai.analyze(snapshot=snapshot, language=language)

        account_id_set = {str(a["account_id"]) for a in snapshot["accounts"]}
        created: List[StrategicRecommendation] = []
        for rec in payload.get("recommendations", []):
            if not rec["title"] or not rec["rationale"]:
                continue

            context = dict(rec.get("context") or {})
            raw_account_id = context.get("account_id") if isinstance(context, dict) else None
            account_uuid: Optional[UUID] = None
            if account_id is not None:
                account_uuid = account_id
                context["account_id"] = str(account_id)
            elif raw_account_id and str(raw_account_id) in account_id_set:
                try:
                    account_uuid = UUID(str(raw_account_id))
                except (TypeError, ValueError):
                    account_uuid = None

            if normalized_asin:
                context["asins"] = [normalized_asin]

            if account_id is not None or normalized_asin:
                context["generation_filters"] = {
                    key: value
                    for key, value in {
                        "account_id": str(account_id) if account_id is not None else None,
                        "asin": normalized_asin,
                    }.items()
                    if value is not None
                }

            model = StrategicRecommendation(
                organization_id=org_id,
                account_id=account_uuid,
                created_by_id=user_id,
                category=rec["category"],
                priority=rec["priority"],
                priority_score=_priority_to_score(rec["priority"]),
                title=rec["title"],
                rationale=rec["rationale"],
                expected_impact=rec["expected_impact"],
                context=context or None,
                generated_by="ai_analysis",
            )
            self.db.add(model)
            created.append(model)

        await self.db.flush()
        for model in created:
            await self.db.refresh(model)
        return created

    # ---------------------------------------------------------------- helpers
    async def _build_org_snapshot(
        self,
        org_id: UUID,
        lookback_days: int,
        *,
        account_id: Optional[UUID] = None,
        asin: Optional[str] = None,
    ) -> Dict[str, Any]:
        today = date.today()
        start_date = today - timedelta(days=lookback_days)

        normalized_asin = _normalize_asin(asin)
        accounts_stmt = select(AmazonAccount).where(AmazonAccount.organization_id == org_id)
        if account_id is not None:
            accounts_stmt = accounts_stmt.where(AmazonAccount.id == account_id)
        accounts_result = await self.db.execute(accounts_stmt)
        accounts = list(accounts_result.scalars().all())
        if account_id is not None and not accounts:
            raise LookupError("Account not found")
        account_ids = [a.id for a in accounts]

        snapshot: Dict[str, Any] = {
            "lookback_days": lookback_days,
            "date_from": start_date.isoformat(),
            "date_to": today.isoformat(),
            "filters": {
                "account_id": str(account_id) if account_id is not None else None,
                "selected_asin": normalized_asin,
                "ads_scope": "account_level" if normalized_asin else "scope_level",
            },
            "accounts": [],
        }

        if not account_ids:
            return snapshot

        if normalized_asin:
            selected_product_result = await self.db.execute(
                select(Product)
                .where(
                    Product.account_id.in_(account_ids),
                    Product.asin == normalized_asin,
                )
                .order_by(Product.updated_at.desc())
            )
            selected_products = list(selected_product_result.scalars().all())
            if selected_products:
                product = selected_products[0]
                snapshot["selected_product"] = {
                    "asin": normalized_asin,
                    "title": product.title,
                    "brand": product.brand,
                    "category": product.category,
                    "accounts_present": len({str(p.account_id) for p in selected_products}),
                }
            else:
                snapshot["selected_product"] = {"asin": normalized_asin}

        # --- sales per account
        sales_stmt = (
            select(
                SalesData.account_id,
                func.sum(SalesData.ordered_product_sales).label("revenue"),
                func.sum(SalesData.units_ordered).label("units"),
                func.sum(SalesData.total_order_items).label("orders"),
            )
            .where(
                SalesData.account_id.in_(account_ids),
                SalesData.date >= start_date,
                SalesData.date <= today,
                SalesData.asin != DAILY_TOTAL_ASIN,
            )
            .group_by(SalesData.account_id)
        )
        if normalized_asin:
            sales_stmt = sales_stmt.where(SalesData.asin == normalized_asin)
        sales_rows = await self.db.execute(sales_stmt)
        sales_by_account = {
            row.account_id: {
                "revenue": float(row.revenue or 0),
                "units": int(row.units or 0),
                "orders": int(row.orders or 0),
            }
            for row in sales_rows
        }

        # --- ads per account (via campaigns)
        ads_rows = await self.db.execute(
            select(
                AdvertisingCampaign.account_id,
                func.sum(AdvertisingMetrics.cost).label("spend"),
                func.sum(AdvertisingMetrics.attributed_sales_7d).label("ad_sales"),
                func.sum(AdvertisingMetrics.clicks).label("clicks"),
                func.sum(AdvertisingMetrics.impressions).label("impressions"),
            )
            .join(
                AdvertisingCampaign,
                AdvertisingMetrics.campaign_id == AdvertisingCampaign.id,
            )
            .where(
                AdvertisingCampaign.account_id.in_(account_ids),
                AdvertisingMetrics.date >= start_date,
                AdvertisingMetrics.date <= today,
            )
            .group_by(AdvertisingCampaign.account_id)
        )
        ads_by_account: Dict[Any, Dict[str, float]] = {}
        for row in ads_rows:
            spend = float(row.spend or 0)
            ad_sales = float(row.ad_sales or 0)
            ads_by_account[row.account_id] = {
                "spend": spend,
                "ad_sales": ad_sales,
                "clicks": int(row.clicks or 0),
                "impressions": int(row.impressions or 0),
                "acos": round((spend / ad_sales * 100), 2) if ad_sales > 0 else None,
                "roas": round((ad_sales / spend), 2) if spend > 0 else None,
            }

        # --- inventory low-stock signal (latest snapshot per account)
        latest_dates = await self.db.execute(
            select(
                InventoryData.account_id,
                func.max(InventoryData.snapshot_date).label("latest"),
            )
            .where(InventoryData.account_id.in_(account_ids))
            .group_by(InventoryData.account_id)
        )
        latest_by_account = {row.account_id: row.latest for row in latest_dates}

        low_stock_by_account: Dict[Any, int] = {}
        selected_inventory_by_account: Dict[Any, Dict[str, int]] = {}
        for acc_id, latest in latest_by_account.items():
            if latest is None:
                continue
            if normalized_asin:
                inventory_result = await self.db.execute(
                    select(
                        InventoryData.afn_fulfillable_quantity,
                        InventoryData.afn_total_quantity,
                        InventoryData.mfn_fulfillable_quantity,
                    )
                    .where(
                        InventoryData.account_id == acc_id,
                        InventoryData.snapshot_date == latest,
                        InventoryData.asin == normalized_asin,
                    )
                )
                inventory_row = inventory_result.first()
                if inventory_row is not None:
                    selected_inventory_by_account[acc_id] = {
                        "afn_fulfillable_quantity": int(
                            inventory_row.afn_fulfillable_quantity or 0
                        ),
                        "afn_total_quantity": int(inventory_row.afn_total_quantity or 0),
                        "mfn_fulfillable_quantity": int(
                            inventory_row.mfn_fulfillable_quantity or 0
                        ),
                    }
                continue
            low_stock_result = await self.db.execute(
                select(func.count())
                .select_from(InventoryData)
                .where(
                    InventoryData.account_id == acc_id,
                    InventoryData.snapshot_date == latest,
                    InventoryData.afn_fulfillable_quantity <= 10,
                )
            )
            low_stock_by_account[acc_id] = int(low_stock_result.scalar() or 0)

        # --- top and bottom ASINs by revenue (org-level)
        top_asins_stmt = (
            select(
                SalesData.asin,
                func.sum(SalesData.ordered_product_sales).label("revenue"),
                func.sum(SalesData.units_ordered).label("units"),
            )
            .where(
                SalesData.account_id.in_(account_ids),
                SalesData.date >= start_date,
                SalesData.date <= today,
                SalesData.asin != DAILY_TOTAL_ASIN,
            )
            .group_by(SalesData.asin)
            .order_by(func.sum(SalesData.ordered_product_sales).desc())
            .limit(5)
        )
        if normalized_asin:
            top_asins_stmt = top_asins_stmt.where(SalesData.asin == normalized_asin)
        top_asins_result = await self.db.execute(top_asins_stmt)
        top_asins = [
            {"asin": row.asin, "revenue": float(row.revenue or 0), "units": int(row.units or 0)}
            for row in top_asins_result
        ]

        # Assemble per-account entries
        for account in accounts:
            sales = sales_by_account.get(account.id, {"revenue": 0.0, "units": 0, "orders": 0})
            ads = ads_by_account.get(account.id, {})
            snapshot["accounts"].append(
                {
                    "account_id": str(account.id),
                    "name": account.account_name,
                    "marketplace": account.marketplace_country,
                    "sales": sales,
                    "ads": ads,
                    "low_stock_skus": (
                        None if normalized_asin else low_stock_by_account.get(account.id, 0)
                    ),
                    "selected_asin_inventory": selected_inventory_by_account.get(account.id),
                }
            )

        snapshot["top_asins_by_revenue"] = top_asins
        return snapshot
