"""Per-ASIN economics ingestion via the SP-API Data Kiosk.

The economics dataset returns Amazon-computed fees, ad spend and net proceeds
per ASIN per day — the cheapest source of profitability data (no Finance role
required). Seller accounts only.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.amazon_account import AccountType, AmazonAccount
from app.models.economics import AsinEconomics

logger = logging.getLogger(__name__)

# Economics data publishes with a lag; never query up to today.
ECONOMICS_DATA_LAG_DAYS = 2
# Rolling window for the daily job; first run per account pulls a deeper one.
ECONOMICS_ROLLING_WINDOW_DAYS = 14
ECONOMICS_FIRST_SYNC_DAYS = 30


class EconomicsService:
    """Sync per-ASIN economics rows for one account."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _create_sp_api_client(self, account: AmazonAccount, organization=None):
        from app.core.amazon.credentials import resolve_credentials
        from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace

        credentials = resolve_credentials(account, organization)
        marketplace = resolve_marketplace(account.marketplace_country)
        return SPAPIClient(credentials, marketplace, account_type=account.account_type.value)

    @staticmethod
    def _build_query(marketplace_id: str, start_date: date, end_date: date) -> str:
        return f"""
query {{
  analytics_economics_2024_03_15 {{
    economics(
      startDate: "{start_date.isoformat()}"
      endDate: "{end_date.isoformat()}"
      aggregateBy: {{ date: DAY, productId: CHILD_ASIN }}
      marketplaceIds: ["{marketplace_id}"]
    ) {{
      startDate
      endDate
      marketplaceId
      childAsin
      sales {{
        orderedProductSales {{ amount currencyCode }}
        netProductSales {{ amount currencyCode }}
        unitsOrdered
        unitsRefunded
        netUnitsSold
      }}
      fees {{
        feeTypeName
        charges {{ aggregatedDetail {{ totalAmount {{ amount currencyCode }} }} }}
      }}
      ads {{
        adTypeName
        charge {{ totalAmount {{ amount currencyCode }} }}
      }}
      netProceeds {{
        total {{ amount currencyCode }}
        perUnit {{ amount currencyCode }}
      }}
    }}
  }}
}}
""".strip()

    @staticmethod
    def _money(node: Any) -> Optional[Decimal]:
        if not isinstance(node, dict):
            return None
        amount = node.get("amount")
        if amount is None:
            return None
        try:
            return Decimal(str(amount))
        except (InvalidOperation, ValueError, TypeError):
            return None

    @staticmethod
    def _currency(node: Any) -> Optional[str]:
        if isinstance(node, dict):
            value = node.get("currencyCode")
            return str(value) if value else None
        return None

    @classmethod
    def _normalize_row(cls, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Map one Data Kiosk economics JSONL row to asin_economics columns."""
        asin = row.get("childAsin") or row.get("parentAsin") or row.get("asin")
        row_date_raw = row.get("startDate") or row.get("date")
        if not asin or not row_date_raw:
            return None
        try:
            row_date = date.fromisoformat(str(row_date_raw)[:10])
        except ValueError:
            return None

        sales = row.get("sales") or {}
        net_proceeds = row.get("netProceeds") or {}

        # A FeeSummary's `charges` list can hold multiple Fee entries when the
        # window straddles an Amazon fee-change date — sum them all.
        fee_breakdown: Dict[str, float] = {}
        total_fees = Decimal("0")
        fees_seen = False
        for fee in row.get("fees") or []:
            if not isinstance(fee, dict):
                continue
            name = str(fee.get("feeTypeName") or "unknown")
            for charge in fee.get("charges") or []:
                if not isinstance(charge, dict):
                    continue
                detail = charge.get("aggregatedDetail") or {}
                amount = cls._money(detail.get("totalAmount"))
                if amount is None:
                    continue
                fees_seen = True
                total_fees += amount
                fee_breakdown[name] = float(fee_breakdown.get(name, 0) + float(amount))

        # `ads` is a list of AdSummary (one per ad type); spend = charge.totalAmount.
        ads_spend = Decimal("0")
        ads_seen = False
        ads_currency = None
        for ad in row.get("ads") or []:
            if not isinstance(ad, dict):
                continue
            charge = ad.get("charge") or {}
            amount = cls._money(charge.get("totalAmount"))
            if amount is None:
                continue
            ads_seen = True
            ads_spend += amount
            ads_currency = ads_currency or cls._currency(charge.get("totalAmount"))

        ordered_sales = cls._money(sales.get("orderedProductSales"))
        currency = (
            cls._currency(sales.get("orderedProductSales"))
            or ads_currency
            or cls._currency(net_proceeds.get("total"))
        )

        return {
            "date": row_date,
            "asin": str(asin),
            "units_ordered": sales.get("unitsOrdered"),
            "units_refunded": sales.get("unitsRefunded"),
            "net_units_sold": sales.get("netUnitsSold"),
            "ordered_product_sales": ordered_sales,
            "net_product_sales": cls._money(sales.get("netProductSales")),
            "currency": currency,
            "total_fees": total_fees if fees_seen else None,
            "ads_spend": ads_spend if ads_seen else None,
            "net_proceeds_total": cls._money(net_proceeds.get("total")),
            "net_proceeds_per_unit": cls._money(net_proceeds.get("perUnit")),
            "fee_breakdown": fee_breakdown or None,
        }

    async def _upsert_economics_record(self, values: Dict[str, Any]) -> None:
        stmt = pg_insert(AsinEconomics).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_asin_economics_account_date_asin",
            set_={
                "units_ordered": stmt.excluded.units_ordered,
                "units_refunded": stmt.excluded.units_refunded,
                "net_units_sold": stmt.excluded.net_units_sold,
                "ordered_product_sales": stmt.excluded.ordered_product_sales,
                "net_product_sales": stmt.excluded.net_product_sales,
                "currency": stmt.excluded.currency,
                "total_fees": stmt.excluded.total_fees,
                "ads_spend": stmt.excluded.ads_spend,
                "net_proceeds_total": stmt.excluded.net_proceeds_total,
                "net_proceeds_per_unit": stmt.excluded.net_proceeds_per_unit,
                "fee_breakdown": stmt.excluded.fee_breakdown,
            },
        )
        await self.db.execute(stmt)

    async def _resolve_window(
        self, account: AmazonAccount,
        start_date: Optional[date], end_date: Optional[date],
    ) -> tuple[date, date]:
        if start_date and end_date:
            return start_date, end_date
        end = end_date or (date.today() - timedelta(days=ECONOMICS_DATA_LAG_DAYS))
        if start_date:
            return start_date, end
        existing = await self.db.execute(
            select(func.count()).select_from(AsinEconomics).where(
                AsinEconomics.account_id == account.id
            )
        )
        has_rows = (existing.scalar() or 0) > 0
        days = ECONOMICS_ROLLING_WINDOW_DAYS if has_rows else ECONOMICS_FIRST_SYNC_DAYS
        return end - timedelta(days=days - 1), end

    async def sync_asin_economics(
        self,
        account: AmazonAccount,
        organization=None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> int:
        """Pull and upsert per-ASIN economics for the window. Idempotent."""
        if account.account_type == AccountType.VENDOR:
            return 0

        start, end = await self._resolve_window(account, start_date, end_date)
        client = self._create_sp_api_client(account, organization)
        query = self._build_query(account.marketplace_id, start, end)
        rows = client.run_data_kiosk_query(query)

        count = 0
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            values = self._normalize_row(raw)
            if values is None:
                continue
            values["account_id"] = account.id
            await self._upsert_economics_record(values)
            count += 1

        await self.db.flush()
        logger.info(
            "Synced %d economics rows for %s (%s..%s)",
            count, account.account_name, start, end,
        )
        return count
