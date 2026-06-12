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
from app.models.amazon_account import AccountType, AmazonAccount
from app.models.brand_search_term import BrandSearchTerm
from app.models.economics import AsinEconomics
from app.models.inventory import InventoryData
from app.models.listing_quality import ListingQualitySnapshot
from app.models.market_snapshot import FeeEstimate, PriceSnapshot
from app.models.product import Product
from app.models.sales_data import SalesData
from app.models.strategic_recommendation import StrategicRecommendation
from app.services.data_extraction import DAILY_TOTAL_ASIN
from app.services.sales_metrics import display_revenue_expr, display_units_expr
from app.services.granularity import Granularity, resolve_granularity

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"pricing", "advertising", "inventory", "content"}
VALID_STATUSES = {"pending", "implemented", "dismissed"}
VALID_PRIORITIES = {"high", "medium", "low"}
VALID_CONFIDENCE = {"high", "medium", "low"}


class AIProviderUnavailableError(RuntimeError):
    """The Anthropic provider rejected the request (auth, quota, rate limit, outage).

    Distinct from a missing API key so the API layer can surface a 502 instead of
    a 503 and never leak the raw provider message to the end user.
    """


def _is_anthropic_provider_error(exc: BaseException) -> bool:
    """Duck-typed check so we don't import anthropic where it may be absent."""
    for klass in type(exc).__mro__:
        if klass.__module__.split(".", 1)[0] == "anthropic" and klass.__name__ in {
            "APIStatusError",
            "APIConnectionError",
            "APITimeoutError",
            "RateLimitError",
            "AuthenticationError",
            "PermissionDeniedError",
            "AnthropicError",
        }:
            return True
    return False

# Seller (daily) data is dense, so a 4-week window is enough. Vendor (monthly)
# data lands one settled row per month and routinely trails several weeks, so a
# 28-day window can be entirely empty for a perfectly healthy account. Default
# to a quarter for monthly cadence to avoid false "0 sales / stock-out" alarms.
DEFAULT_LOOKBACK_DAILY = 28
DEFAULT_LOOKBACK_MONTHLY = 90
# When the requested window is empty but the account has data further back, fall
# back through these widths before concluding there is genuinely nothing to say.
FALLBACK_LOOKBACK_LADDER = [90, 180, 365]


def _priority_to_score(priority: Optional[str]) -> int:
    return {"high": 100, "medium": 50, "low": 10}.get((priority or "medium").lower(), 50)


def _sanitize_category(value: Optional[str]) -> str:
    val = (value or "").strip().lower()
    return val if val in VALID_CATEGORIES else "pricing"


def _sanitize_priority(value: Optional[str]) -> str:
    val = (value or "").strip().lower()
    return val if val in VALID_PRIORITIES else "medium"


def _sanitize_confidence(value: Optional[str]) -> str:
    val = (value or "").strip().lower()
    return val if val in VALID_CONFIDENCE else "medium"


def _normalize_asin(value: Optional[str]) -> Optional[str]:
    val = (value or "").strip().upper()
    return val or None


# ── Brand Pulse deterministic recommendations ────────────────────────────────
# Rule-based, evidence-backed recommendations derived from an already-computed
# Brand Pulse snapshot. No AI call, so they never depend on an API key and can
# never fabricate a number — every figure is read from the snapshot. Each rec
# carries Source, Confidence and Evidence so the UI can show why it fired.
PULSE_MIN_BASELINE_REVENUE = 50.0  # ignore swings off a near-zero prior period
PULSE_REVENUE_DECLINE_PCT = -10.0
PULSE_REVENUE_DECLINE_CRITICAL_PCT = -25.0
PULSE_REVENUE_GROWTH_PCT = 15.0
PULSE_ACOS_HIGH_PCT = 30.0
PULSE_ACOS_CRITICAL_PCT = 45.0
PULSE_TACOS_HIGH_PCT = 25.0


def _pulse_money(value: Optional[float]) -> str:
    return f"€{float(value or 0):,.0f}"


def _pulse_signed(value: Optional[float]) -> str:
    return f"{float(value or 0):+.0f}"


def _pulse_text(language: str, en: str, it: str) -> str:
    return it if language == "it" else en


def _pulse_rec(*, title: str, priority: str, confidence: str, source: str, evidence: str, rationale: str) -> Dict[str, Any]:
    return {
        "title": title,
        "priority": _sanitize_priority(priority),
        "confidence": _sanitize_confidence(confidence),
        "source": source,
        "evidence": evidence,
        "rationale": rationale,
    }


def build_pulse_recommendations(pulse: Dict[str, Any], *, language: str = "en") -> List[Dict[str, Any]]:
    """Deterministic, evidence-backed recommendations from a Brand Pulse snapshot.

    Mirrors the AI engine's anti-hallucination discipline: every number is read
    from the snapshot, swings off a near-zero baseline are suppressed, and
    per-ASIN signals (a seller snapshot, not a 30-day sum) are flagged at medium
    confidence with honest evidence. Returns at most five, highest priority first.
    """
    overview = pulse.get("overview") or {}
    current = overview.get("current") or {}
    previous = overview.get("previous") or {}
    changes = overview.get("changes") or {}
    ads = pulse.get("ads") or {}
    declining = pulse.get("declining_asins") or []
    period = pulse.get("period") or {}

    cur_rev = float(current.get("revenue") or 0.0)
    prev_rev = float(previous.get("revenue") or 0.0)
    rev_change = (changes.get("revenue") or {}).get("percent")
    window = period.get("window_days", 30)
    # Monthly-cadence accounts with no posted data this period: the "-100%" is a
    # reporting-lag artifact, so suppress the sales/decline alarms entirely.
    awaiting_data = bool(period.get("awaiting_data"))

    recs: List[Dict[str, Any]] = []

    # Revenue trend — only off a meaningful baseline, so a near-zero prior period
    # cannot produce a misleading "down 100%" alarm.
    if not awaiting_data and rev_change is not None and prev_rev >= PULSE_MIN_BASELINE_REVENUE:
        if rev_change <= PULSE_REVENUE_DECLINE_PCT:
            critical = rev_change <= PULSE_REVENUE_DECLINE_CRITICAL_PCT
            recs.append(_pulse_rec(
                title=_pulse_text(language,
                    f"Brand revenue down {abs(round(rev_change))}% vs prior {window} days",
                    f"Fatturato in calo del {abs(round(rev_change))}% rispetto ai {window} giorni precedenti"),
                priority="high" if critical else "medium",
                confidence="high",
                source="Sales (SP-API)",
                evidence=_pulse_text(language,
                    f"Revenue {_pulse_money(cur_rev)} vs {_pulse_money(prev_rev)} ({_pulse_signed(rev_change)}%); "
                    f"units {current.get('units', 0)} vs {previous.get('units', 0)}.",
                    f"Fatturato {_pulse_money(cur_rev)} vs {_pulse_money(prev_rev)} ({_pulse_signed(rev_change)}%); "
                    f"unità {current.get('units', 0)} vs {previous.get('units', 0)}."),
                rationale=_pulse_text(language,
                    "Investigate the largest declining ASINs and any buy-box or pricing changes in the period.",
                    "Analizza gli ASIN in maggior calo e le variazioni di buy-box o prezzo nel periodo."),
            ))
        elif rev_change >= PULSE_REVENUE_GROWTH_PCT:
            recs.append(_pulse_rec(
                title=_pulse_text(language,
                    f"Brand revenue up {round(rev_change)}% vs prior {window} days",
                    f"Fatturato in crescita del {round(rev_change)}% rispetto ai {window} giorni precedenti"),
                priority="low",
                confidence="high",
                source="Sales (SP-API)",
                evidence=f"{_pulse_money(cur_rev)} vs {_pulse_money(prev_rev)} ({_pulse_signed(rev_change)}%).",
                rationale=_pulse_text(language,
                    "Protect stock and ad coverage on the rising ASINs to sustain the momentum.",
                    "Proteggi stock e copertura ADV sugli ASIN in crescita per sostenere lo slancio."),
            ))

    # Declining ASIN cluster — seller per-ASIN is a snapshot, so medium confidence.
    if declining and not awaiting_data:
        fast = [d for d in declining if d.get("trend_class") == "declining_fast"]
        worst = declining[0]
        worst_label = worst.get("title") or worst.get("asin")
        recs.append(_pulse_rec(
            title=_pulse_text(language,
                f"{len(declining)} ASINs declining" + (f", {len(fast)} sharply" if fast else ""),
                f"{len(declining)} ASIN in calo" + (f", {len(fast)} in forte calo" if fast else "")),
            priority="high" if fast else "medium",
            confidence="medium",
            source="Sales by ASIN (latest snapshot)",
            evidence=_pulse_text(language,
                f"Worst: {worst_label} {_pulse_money(worst.get('previous_revenue'))} → "
                f"{_pulse_money(worst.get('revenue'))} ({_pulse_signed(worst.get('change_percent'))}%).",
                f"Peggiore: {worst_label} {_pulse_money(worst.get('previous_revenue'))} → "
                f"{_pulse_money(worst.get('revenue'))} ({_pulse_signed(worst.get('change_percent'))}%)."),
            rationale=_pulse_text(language,
                "Review listing quality, price and ad support for the declining ASINs.",
                "Rivedi qualità della scheda, prezzo e supporto ADV per gli ASIN in calo."),
        ))

    # Advertising efficiency — only when ad data actually covers the window.
    if ads.get("is_available"):
        acos = ads.get("acos")
        tacos = ads.get("tacos")
        if acos is not None and acos >= PULSE_ACOS_HIGH_PCT:
            recs.append(_pulse_rec(
                title=_pulse_text(language, f"Advertising ACOS high at {acos}%", f"ACOS pubblicitario alto al {acos}%"),
                priority="high" if acos >= PULSE_ACOS_CRITICAL_PCT else "medium",
                confidence="high",
                source="Amazon Ads",
                evidence=_pulse_text(language,
                    f"Spend {_pulse_money(ads.get('spend'))}, ad sales {_pulse_money(ads.get('ad_sales'))}, "
                    f"ACOS {acos}% (7-day attribution).",
                    f"Spesa {_pulse_money(ads.get('spend'))}, vendite ADV {_pulse_money(ads.get('ad_sales'))}, "
                    f"ACOS {acos}% (attribuzione 7 giorni)."),
                rationale=_pulse_text(language,
                    "Trim spend on targets above the brand-average ACOS and shift budget to efficient terms.",
                    "Riduci la spesa sui target sopra l'ACOS medio e sposta budget sui termini efficienti."),
            ))
        if tacos is not None and tacos >= PULSE_TACOS_HIGH_PCT:
            recs.append(_pulse_rec(
                title=_pulse_text(language,
                    f"Sales rely heavily on ads (TACOS {tacos}%)",
                    f"Le vendite dipendono molto dall'ADV (TACOS {tacos}%)"),
                priority="medium",
                confidence="high",
                source="Amazon Ads + Sales",
                evidence=_pulse_text(language,
                    f"Ad spend is {tacos}% of total revenue ({_pulse_money(ads.get('spend'))} of {_pulse_money(cur_rev)}).",
                    f"La spesa ADV è il {tacos}% del fatturato totale ({_pulse_money(ads.get('spend'))} su {_pulse_money(cur_rev)})."),
                rationale=_pulse_text(language,
                    "Build organic rank on the top ASINs to reduce ad dependence over time.",
                    "Costruisci posizionamento organico sui top ASIN per ridurre la dipendenza dall'ADV."),
            ))

    recs.sort(key=lambda r: _priority_to_score(r["priority"]), reverse=True)
    return recs[:5]


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

Organization snapshot (analysis window: {snapshot.get('date_from')} to {snapshot.get('date_to')}, {snapshot.get('lookback_days')} days):
{json.dumps(snapshot, ensure_ascii=False, indent=2, default=str)}

Return a JSON object with exactly this structure:
{{
  "summary": "2-4 sentence executive summary",
  "recommendations": [
    {{
      "category": "pricing|advertising|inventory|content",
      "priority": "high|medium|low",
      "confidence": "high|medium|low",
      "title": "short imperative title (< 90 chars)",
      "rationale": "why this action follows from the snapshot, naming the period/account/metric and quoting concrete numbers",
      "expected_impact": "expected business impact with a directional estimate",
      "context": {{"account_id": "<uuid if account-specific, else omit>", "asins": ["B000..."]}}
    }}
  ]
}}

Rules:
- Produce 3-6 recommendations ordered by priority.
- Use exactly one of the four categories above per recommendation.
- Ground every recommendation in the numbers from the snapshot; do not invent data.
- The snapshot already covers a window appropriate to each account's reporting cadence (`accounts[].cadence`: vendor accounts report monthly, so their data trails by weeks). NEVER infer a stock-out, dead listing, or "0 units sold" problem from an empty or low window: the snapshot's sales totals are the authoritative figures for the window shown. If `data_sufficiency.status` is "insufficient" for an account, do NOT emit any negative/alarm recommendation for it — at most note that more data is needed (confidence "low").
- Set `confidence` to "low" when the supporting numbers are thin or trailing, "high" only when the window has solid, recent data directly backing the action.
- If `product_signals` is present, cross-reference it: lost Buy Box entries (`buy_box.lost_detail`) and thin/negative margins (`fees_margins`) are prime pricing candidates; low `listing_quality` scores and `catalog_weak_social_proof` are prime content candidates; `search_terms` shows where the brand already ranks organically. Quote the specific ASIN and numbers. Distinguish Amazon-computed actuals (`source: amazon_economics_actuals`) from estimates.
- In every `rationale`, state the period analysed and the account/metric it is based on.
- If `snapshot.filters.selected_asin` is present, sales and inventory are scoped to that ASIN.
- If `snapshot.filters.selected_asin` is present, ads metrics remain account-level unless a field explicitly says they are ASIN-level.
- If a recommendation targets a single account or ASIN, include those identifiers in `context`.
- Return ONLY the JSON object, no markdown or commentary."""

        message = self.client.messages.create(
            model="claude-sonnet-4-6",
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
                    "confidence": _sanitize_confidence(rec.get("confidence")),
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

    async def delete(self, rec_id: UUID, org_id: UUID) -> None:
        rec = await self.get(rec_id, org_id)
        if rec is None:
            raise ValueError("Recommendation not found")
        await self.db.delete(rec)
        await self.db.flush()

    # -------------------------------------------------------------- cadence
    async def _resolve_granularity(
        self, org_id: UUID, account_id: Optional[UUID]
    ) -> Granularity:
        account_ids = [account_id] if account_id is not None else None
        return await resolve_granularity(self.db, org_id, account_ids)

    @staticmethod
    def _effective_lookback(
        requested: Optional[int], granularity: Granularity
    ) -> int:
        if requested is not None:
            return requested
        # `auto`: pick a window that matches the slowest cadence in scope so a
        # monthly vendor account is never judged on an empty 4-week window.
        if granularity in (Granularity.MONTHLY, Granularity.MIXED, Granularity.UNKNOWN):
            return DEFAULT_LOOKBACK_MONTHLY
        return DEFAULT_LOOKBACK_DAILY

    # --------------------------------------------------------------- generate
    async def generate_for_organization(
        self,
        org_id: UUID,
        *,
        user_id: Optional[UUID] = None,
        lookback_days: Optional[int] = None,
        language: str = "en",
        account_id: Optional[UUID] = None,
        asin: Optional[str] = None,
    ) -> List[StrategicRecommendation]:
        """Build snapshot, call Claude, persist recommendation rows."""
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")

        normalized_asin = _normalize_asin(asin)

        granularity = await self._resolve_granularity(org_id, account_id)
        effective_lookback = self._effective_lookback(lookback_days, granularity)

        snapshot = await self._build_org_snapshot(
            org_id,
            effective_lookback,
            account_id=account_id,
            asin=normalized_asin,
            granularity=granularity,
            lookback_requested=lookback_days,
        )
        if not snapshot["accounts"]:
            logger.info("No accounts found for org %s; skipping generation", org_id)
            return []

        ai = _StrategicRecAnalysisService(settings.ANTHROPIC_API_KEY)
        try:
            payload = ai.analyze(snapshot=snapshot, language=language)
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider SDK raises many error types
            if _is_anthropic_provider_error(exc):
                logger.warning("Anthropic provider unavailable for org %s: %s", org_id, exc)
                raise AIProviderUnavailableError(str(exc)) from exc
            raise

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
                confidence=rec.get("confidence", "medium"),
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
        granularity: Optional[Granularity] = None,
        lookback_requested: Optional[int] = None,
    ) -> Dict[str, Any]:
        today = date.today()

        normalized_asin = _normalize_asin(asin)
        accounts_stmt = select(AmazonAccount).where(AmazonAccount.organization_id == org_id)
        if account_id is not None:
            accounts_stmt = accounts_stmt.where(AmazonAccount.id == account_id)
        accounts_result = await self.db.execute(accounts_stmt)
        accounts = list(accounts_result.scalars().all())
        if account_id is not None and not accounts:
            raise LookupError("Account not found")
        account_ids = [a.id for a in accounts]

        # If the requested window is empty but the account has data further back,
        # widen it instead of feeding the AI an all-zero snapshot (which is what
        # produced false "0 sales / stock-out" alarms for monthly vendor data).
        lookback_days, data_sufficiency = await self._resolve_window(
            account_ids, lookback_days, today
        )
        start_date = today - timedelta(days=lookback_days)

        snapshot: Dict[str, Any] = {
            "lookback_days": lookback_days,
            "lookback_requested": lookback_requested,
            "granularity": (granularity or Granularity.UNKNOWN).value,
            "date_from": start_date.isoformat(),
            "date_to": today.isoformat(),
            "data_sufficiency": data_sufficiency,
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
                func.sum(display_revenue_expr()).label("revenue"),
                func.sum(display_units_expr()).label("units"),
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
                func.sum(display_revenue_expr()).label("revenue"),
                func.sum(display_units_expr()).label("units"),
            )
            .where(
                SalesData.account_id.in_(account_ids),
                SalesData.date >= start_date,
                SalesData.date <= today,
                SalesData.asin != DAILY_TOTAL_ASIN,
            )
            .group_by(SalesData.asin)
            .order_by(func.sum(display_revenue_expr()).desc())
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
                    "cadence": (
                        "monthly"
                        if account.account_type == AccountType.VENDOR
                        else "daily"
                    ),
                    "sales": sales,
                    "ads": ads,
                    "low_stock_skus": (
                        None if normalized_asin else low_stock_by_account.get(account.id, 0)
                    ),
                    "selected_asin_inventory": selected_inventory_by_account.get(account.id),
                }
            )

        snapshot["top_asins_by_revenue"] = top_asins

        # --- product-level signals: Buy Box, fees/margins, listing quality,
        # catalog health, search terms. Each block is omitted when its source
        # has no data, so the prompt never grows with empty noise.
        signals = await self._collect_product_signals(
            account_ids,
            [t["asin"] for t in top_asins],
            normalized_asin,
            start_date,
            today,
        )
        if signals:
            snapshot["product_signals"] = signals

        return snapshot

    async def _collect_product_signals(
        self,
        account_ids: List[UUID],
        top_asins: List[str],
        selected_asin: Optional[str],
        start_date: date,
        today: date,
    ) -> Dict[str, Any]:
        """Cross-reference per-ASIN signals from the snapshot warehouses.

        All sources are best-effort: a missing table or an account type that
        never ingests a source (vendors have no pricing/fees snapshots) simply
        yields no block.
        """
        signals: Dict[str, Any] = {}
        recent_cutoff = today - timedelta(days=7)

        def _latest_per_asin(rows, date_attr: str):
            latest: Dict[str, Any] = {}
            for row in rows:
                current = latest.get(row.asin)
                if current is None or getattr(row, date_attr) > getattr(current, date_attr):
                    latest[row.asin] = row
            return latest

        # Buy Box ownership + price gap (price_snapshots, sellers only).
        price_stmt = select(PriceSnapshot).where(
            PriceSnapshot.account_id.in_(account_ids),
            PriceSnapshot.snapshot_date >= recent_cutoff,
        )
        if selected_asin:
            price_stmt = price_stmt.where(PriceSnapshot.asin == selected_asin)
        price_rows = _latest_per_asin(
            (await self.db.execute(price_stmt)).scalars().all(), "snapshot_date"
        )
        if price_rows:
            lost = []
            for row in price_rows.values():
                if row.is_buy_box_ours is False:
                    gap = None
                    if row.our_price and row.buy_box_price and float(row.our_price) > 0:
                        gap = round(
                            (float(row.our_price) - float(row.buy_box_price))
                            / float(row.our_price) * 100,
                            1,
                        )
                    lost.append(
                        {
                            "asin": row.asin,
                            "our_price": float(row.our_price) if row.our_price is not None else None,
                            "buy_box_price": float(row.buy_box_price) if row.buy_box_price is not None else None,
                            "our_price_vs_buy_box_pct": gap,
                            "offer_count": row.offer_count,
                        }
                    )
            lost.sort(key=lambda item: item.get("our_price_vs_buy_box_pct") or 0, reverse=True)
            signals["buy_box"] = {
                "asins_tracked": len(price_rows),
                "buy_box_owned": sum(1 for r in price_rows.values() if r.is_buy_box_ours),
                "buy_box_lost": len(lost),
                "buy_box_unknown": sum(
                    1 for r in price_rows.values() if r.is_buy_box_ours is None
                ),
                "lost_detail": lost[:10],
            }

        # Margins: prefer Amazon-computed economics (actuals) over fee estimates.
        margin_asins = [a for a in ([selected_asin] if selected_asin else top_asins) if a]
        if margin_asins:
            economics_rows = (
                await self.db.execute(
                    select(
                        AsinEconomics.asin,
                        func.sum(AsinEconomics.ordered_product_sales).label("sales"),
                        func.sum(AsinEconomics.total_fees).label("fees"),
                        func.sum(AsinEconomics.ads_spend).label("ads"),
                        func.sum(AsinEconomics.net_proceeds_total).label("proceeds"),
                    )
                    .where(
                        AsinEconomics.account_id.in_(account_ids),
                        AsinEconomics.asin.in_(margin_asins),
                        AsinEconomics.date >= start_date,
                    )
                    .group_by(AsinEconomics.asin)
                )
            ).all()
            margins = []
            for row in economics_rows:
                sales = float(row.sales or 0)
                proceeds = float(row.proceeds or 0)
                margins.append(
                    {
                        "asin": row.asin,
                        "sales": sales,
                        "amazon_fees": float(row.fees or 0),
                        "ads_spend": float(row.ads or 0),
                        "net_proceeds": proceeds,
                        "net_margin_pct": round(proceeds / sales * 100, 1) if sales > 0 else None,
                        "source": "amazon_economics_actuals",
                    }
                )
            if not margins:
                fee_stmt = select(FeeEstimate).where(
                    FeeEstimate.account_id.in_(account_ids),
                    FeeEstimate.asin.in_(margin_asins),
                    FeeEstimate.snapshot_date >= recent_cutoff,
                )
                fee_rows = _latest_per_asin(
                    (await self.db.execute(fee_stmt)).scalars().all(), "snapshot_date"
                )
                for row in fee_rows.values():
                    if row.estimated_fees is None or row.price_basis is None:
                        continue
                    price = float(row.price_basis)
                    fees = float(row.estimated_fees)
                    margins.append(
                        {
                            "asin": row.asin,
                            "price": price,
                            "estimated_amazon_fees": fees,
                            "estimated_margin_before_cogs_pct": (
                                round((price - fees) / price * 100, 1) if price > 0 else None
                            ),
                            "source": "fee_estimate_at_current_price",
                        }
                    )
            if margins:
                signals["fees_margins"] = margins[:8]

        # Listing quality: average + worst offenders with their missing components.
        quality_stmt = select(ListingQualitySnapshot).where(
            ListingQualitySnapshot.account_id.in_(account_ids),
            ListingQualitySnapshot.snapshot_date >= today - timedelta(days=14),
        )
        if selected_asin:
            quality_stmt = quality_stmt.where(ListingQualitySnapshot.asin == selected_asin)
        quality_rows = _latest_per_asin(
            (await self.db.execute(quality_stmt)).scalars().all(), "snapshot_date"
        )
        if quality_rows:
            worst = sorted(quality_rows.values(), key=lambda r: r.score)[:5]
            signals["listing_quality"] = {
                "asins_scored": len(quality_rows),
                "average_score": round(
                    sum(r.score for r in quality_rows.values()) / len(quality_rows), 1
                ),
                "worst": [
                    {
                        "asin": row.asin,
                        "score": row.score,
                        "missing_components": [
                            name
                            for name, detail in (row.components or {}).items()
                            if isinstance(detail, dict) and not detail.get("earned")
                        ],
                    }
                    for row in worst
                ],
            }

        # Catalog health for the top sellers: missing/weak social proof.
        if margin_asins:
            product_rows = (
                await self.db.execute(
                    select(Product.asin, Product.rating, Product.review_count)
                    .where(
                        Product.account_id.in_(account_ids),
                        Product.asin.in_(margin_asins),
                    )
                )
            ).all()
            weak = [
                {
                    "asin": row.asin,
                    "rating": float(row.rating) if row.rating is not None else None,
                    "review_count": row.review_count,
                }
                for row in product_rows
                if row.rating is None
                or float(row.rating) < 4.0
                or (row.review_count or 0) < 20
            ]
            if weak:
                signals["catalog_weak_social_proof"] = weak[:5]

        # Brand Analytics search terms: latest ingested week where our ASINs rank.
        latest_week = (
            await self.db.execute(
                select(func.max(BrandSearchTerm.week_start)).where(
                    BrandSearchTerm.account_id.in_(account_ids)
                )
            )
        ).scalar()
        if latest_week:
            term_rows = (
                (
                    await self.db.execute(
                        select(BrandSearchTerm)
                        .where(
                            BrandSearchTerm.account_id.in_(account_ids),
                            BrandSearchTerm.week_start == latest_week,
                            BrandSearchTerm.contains_account_asin.is_(True),
                        )
                        .order_by(BrandSearchTerm.search_frequency_rank.asc())
                        .limit(5)
                    )
                )
                .scalars()
                .all()
            )
            if term_rows:
                signals["search_terms"] = {
                    "week_start": latest_week.isoformat(),
                    "terms_where_own_asin_in_top3": [
                        {
                            "term": row.search_term,
                            "search_frequency_rank": row.search_frequency_rank,
                            "top_clicked": row.top_clicked,
                        }
                        for row in term_rows
                    ],
                }

        return signals

    async def _resolve_window(
        self,
        account_ids: List[UUID],
        lookback_days: int,
        today: date,
    ) -> tuple[int, Dict[str, Any]]:
        """Pick a window with data and report how trustworthy it is.

        Returns the (possibly widened) lookback plus a ``data_sufficiency`` block
        so the AI can tell apart "genuinely zero sales" from "the window simply
        predates the latest settled data" — the latter must never trigger a
        negative alarm.
        """
        if not account_ids:
            return lookback_days, {"status": "no_accounts"}

        latest = await self._latest_sales_date(account_ids)
        if latest is None:
            return lookback_days, {
                "status": "no_data",
                "latest_sale_date": None,
                "lookback_days": lookback_days,
            }

        ladders = [lookback_days] + [
            days for days in FALLBACK_LOOKBACK_LADDER if days > lookback_days
        ]
        for window in ladders:
            start = today - timedelta(days=window)
            units = await self._units_in_window(account_ids, start, today)
            if units > 0:
                widened = window != lookback_days
                return window, {
                    "status": "ok",
                    "latest_sale_date": latest.isoformat(),
                    "requested_lookback_days": lookback_days,
                    "lookback_days": window,
                    "window_widened": widened,
                    "note": (
                        "Requested window had no sales; widened to the most recent "
                        "window with settled data."
                        if widened
                        else None
                    ),
                }

        return lookback_days, {
            "status": "insufficient",
            "latest_sale_date": latest.isoformat(),
            "lookback_days": lookback_days,
            "note": (
                "No sales within the analysed windows; latest settled data is "
                f"{latest.isoformat()}. Do not infer stock-outs or dead listings."
            ),
        }

    async def _latest_sales_date(self, account_ids: List[UUID]) -> Optional[date]:
        result = await self.db.execute(
            select(func.max(SalesData.date)).where(
                SalesData.account_id.in_(account_ids),
                SalesData.asin != DAILY_TOTAL_ASIN,
            )
        )
        return result.scalar()

    async def _units_in_window(
        self, account_ids: List[UUID], start: date, end: date
    ) -> int:
        result = await self.db.execute(
            select(func.coalesce(func.sum(display_units_expr()), 0)).where(
                SalesData.account_id.in_(account_ids),
                SalesData.asin != DAILY_TOTAL_ASIN,
                SalesData.date >= start,
                SalesData.date <= end,
            )
        )
        return int(result.scalar() or 0)
