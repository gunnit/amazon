"""Data extraction service for Amazon data."""
from __future__ import annotations
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal
import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.amazon_account import AmazonAccount, SyncStatus
from app.models.advertising import AdvertisingCampaign, AdvertisingMetrics
from app.models.order import Order, OrderItem
from app.models.returns_data import ReturnData
from app.models.sales_data import SalesData
from app.models.inventory import InventoryData
from app.models.product import BSRHistory, Product
from app.core.exceptions import AmazonAPIError

logger = logging.getLogger(__name__)

# Sentinel ASIN used for daily aggregate records (from salesAndTrafficByDate).
# These rows carry accurate per-day totals and are used for dashboard KPIs,
# trends, and comparison queries.  Real per-ASIN rows use actual ASINs.
DAILY_TOTAL_ASIN = "__DAILY_TOTAL__"


class DataExtractionService:
    """Service for extracting data from Amazon."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_organization(self, account: AmazonAccount):
        """Load the organization for an account."""
        from app.models.user import Organization
        result = await self.db.execute(
            select(Organization).where(Organization.id == account.organization_id)
        )
        return result.scalar_one_or_none()

    def _create_sp_api_client(self, account: AmazonAccount, organization=None):
        """Create an SP-API client for the given account."""
        from app.core.amazon.credentials import resolve_credentials
        from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace

        credentials = resolve_credentials(account, organization)
        marketplace = resolve_marketplace(account.marketplace_country)
        return SPAPIClient(credentials, marketplace, account_type=account.account_type.value)

    def _create_advertising_api_client(self, account: AmazonAccount, organization=None):
        """Create an Advertising API client for the given account."""
        from app.core.amazon.credentials import resolve_advertising_credentials
        from app.core.amazon.advertising_client import AdvertisingAPIClient

        credentials = resolve_advertising_credentials(account, organization)
        client = AdvertisingAPIClient(
            client_id=credentials["client_id"],
            client_secret=credentials["client_secret"],
            refresh_token=credentials["refresh_token"],
            marketplace_country=account.marketplace_country,
            base_url=credentials.get("base_url"),
        )
        return client, credentials["profile_id"]

    async def _touch_sync(self, account: AmazonAccount) -> None:
        """Persist a heartbeat for long-running syncs."""
        account.last_sync_heartbeat_at = datetime.utcnow()
        await self.db.flush()

    @staticmethod
    def _normalize_utc_datetime(value: Optional[datetime]) -> Optional[datetime]:
        """Convert aware datetimes to naive UTC for safe comparisons."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _parse_sp_api_datetime(value: Any) -> Optional[datetime]:
        """Parse an SP-API timestamp."""
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_int(value: Any, default: int = 0) -> int:
        """Parse an integer-like value safely."""
        if value in (None, ""):
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _parse_decimal(value: Any) -> Optional[Decimal]:
        """Parse a decimal-like value safely."""
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    @classmethod
    def _normalize_inventory_summary_item(cls, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Map the Inventories API payload into the report row shape used by sync_inventory."""
        asin = (item.get("asin") or "").strip()
        if not asin:
            return None

        details = item.get("inventoryDetails") or {}
        reserved = details.get("reservedQuantity") or {}
        inbound_working = cls._parse_int(details.get("inboundWorkingQuantity"))
        inbound_shipped = cls._parse_int(details.get("inboundShippedQuantity"))
        inbound_receiving = cls._parse_int(details.get("inboundReceivingQuantity"))

        return {
            "asin": asin,
            "sku": item.get("sellerSku"),
            "fnsku": item.get("fnSku"),
            "fulfillment_channel": "AFN",
            "quantity": cls._parse_int(details.get("fulfillableQuantity")),
            "reserved_quantity": cls._parse_int(reserved.get("totalReservedQuantity")),
            "inbound_working_quantity": inbound_working + inbound_receiving,
            "inbound_shipped_quantity": inbound_shipped,
            "inbound_quantity": inbound_working + inbound_shipped + inbound_receiving,
        }

    @classmethod
    def _extract_money(cls, value: Any) -> tuple[Optional[Decimal], Optional[str]]:
        """Extract amount and currency from an SP-API money object."""
        if not isinstance(value, dict):
            return None, None

        amount = value.get("Amount")
        if amount is None:
            amount = value.get("amount")

        currency = value.get("CurrencyCode") or value.get("currencyCode")
        return cls._parse_decimal(amount), currency

    def _resolve_orders_sync_window(
        self,
        account: AmazonAccount,
        *,
        last_sync_started_at: Optional[datetime] = None,
        last_sync_succeeded_at: Optional[datetime] = None,
    ) -> tuple[datetime, datetime]:
        """Resolve the incremental sync window for Orders API calls."""
        created_before = datetime.utcnow() - timedelta(minutes=2)
        default_created_after = created_before - timedelta(days=7)
        previous_started_at = self._normalize_utc_datetime(
            last_sync_started_at if last_sync_started_at is not None else account.last_sync_started_at
        )
        previous_succeeded_at = self._normalize_utc_datetime(
            last_sync_succeeded_at
            if last_sync_succeeded_at is not None
            else (account.last_sync_succeeded_at or account.last_sync_at)
        )

        if previous_succeeded_at is None:
            return default_created_after, created_before

        if previous_started_at and previous_started_at <= previous_succeeded_at:
            created_after = previous_started_at
        else:
            # Orders sync runs before the full account sync completes, so using
            # the last successful completion timestamp directly can leave a gap.
            created_after = previous_succeeded_at - timedelta(minutes=30)

        return max(default_created_after, created_after), created_before

    async def _upsert_order_record(self, values: dict) -> int:
        """Insert or update an order row and return its primary key."""
        stmt = pg_insert(Order).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["amazon_order_id"],
            set_={
                "account_id": stmt.excluded.account_id,
                "purchase_date": stmt.excluded.purchase_date,
                "order_status": stmt.excluded.order_status,
                "fulfillment_channel": stmt.excluded.fulfillment_channel,
                "order_total": stmt.excluded.order_total,
                "currency": stmt.excluded.currency,
                "marketplace_id": stmt.excluded.marketplace_id,
                "number_of_items": stmt.excluded.number_of_items,
            },
        ).returning(Order.id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def _replace_order_items(self, order_id: int, item_values: List[dict]) -> None:
        """Replace stored order items with the latest payload."""
        await self.db.execute(delete(OrderItem).where(OrderItem.order_id == order_id))
        if item_values:
            await self.db.execute(pg_insert(OrderItem).values(item_values))

    def _decimal(self, value: Any, default: str = "0") -> Decimal:
        """Normalize arbitrary numeric input to Decimal."""
        if value in (None, ""):
            return Decimal(default)
        return Decimal(str(value))

    def _int_value(self, value: Any, default: int = 0) -> int:
        """Normalize arbitrary numeric input to int."""
        if value in (None, ""):
            return default
        return int(self._decimal(value))

    def _metric_ratio(self, numerator: Decimal, denominator: Decimal) -> Decimal:
        """Return a 4-decimal ratio with zero protection."""
        if not denominator:
            return Decimal("0")
        return (numerator / denominator).quantize(Decimal("0.0001"))

    def _normalize_campaign_id(self, payload: dict[str, Any]) -> str | None:
        """Extract the external campaign id from varying Ads API payloads."""
        campaign_id = payload.get("campaignId") or payload.get("campaign_id") or payload.get("id")
        if campaign_id in (None, ""):
            return None
        return str(campaign_id)

    async def _upsert_advertising_campaign(self, account: AmazonAccount, payload: dict[str, Any]) -> UUID | None:
        """Insert or update a campaign and return its internal id."""
        campaign_id = self._normalize_campaign_id(payload)
        if not campaign_id:
            return None

        budget = (
            payload.get("dailyBudget")
            or payload.get("budget")
            or payload.get("budgetAmount")
        )
        if isinstance(budget, dict):
            budget = budget.get("amount")

        values = {
            "account_id": account.id,
            "campaign_id": campaign_id,
            "campaign_name": payload.get("campaignName") or payload.get("name"),
            "campaign_type": payload.get("campaignType") or payload.get("adProduct"),
            "state": (payload.get("state") or payload.get("campaignStatus") or payload.get("status") or "").lower() or None,
            "daily_budget": self._decimal(budget) if budget not in (None, "") else None,
            "targeting_type": payload.get("targetingType") or payload.get("targeting_type"),
        }

        stmt = pg_insert(AdvertisingCampaign).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_ad_campaign_account_campaign",
            set_={
                "campaign_name": stmt.excluded.campaign_name,
                "campaign_type": stmt.excluded.campaign_type,
                "state": stmt.excluded.state,
                "daily_budget": stmt.excluded.daily_budget,
                "targeting_type": stmt.excluded.targeting_type,
            },
        ).returning(AdvertisingCampaign.id)

        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def _upsert_advertising_metrics(self, values: dict[str, Any]) -> None:
        """Insert or update campaign/day metrics."""
        stmt = pg_insert(AdvertisingMetrics).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_ad_metrics_campaign_date",
            set_={
                "impressions": stmt.excluded.impressions,
                "clicks": stmt.excluded.clicks,
                "cost": stmt.excluded.cost,
                "attributed_sales_1d": stmt.excluded.attributed_sales_1d,
                "attributed_sales_7d": stmt.excluded.attributed_sales_7d,
                "attributed_sales_14d": stmt.excluded.attributed_sales_14d,
                "attributed_sales_30d": stmt.excluded.attributed_sales_30d,
                "attributed_units_ordered_1d": stmt.excluded.attributed_units_ordered_1d,
                "attributed_units_ordered_7d": stmt.excluded.attributed_units_ordered_7d,
                "attributed_units_ordered_14d": stmt.excluded.attributed_units_ordered_14d,
                "attributed_units_ordered_30d": stmt.excluded.attributed_units_ordered_30d,
                "ctr": stmt.excluded.ctr,
                "cpc": stmt.excluded.cpc,
                "acos": stmt.excluded.acos,
                "roas": stmt.excluded.roas,
            },
        )
        await self.db.execute(stmt)

    async def _campaign_ids_by_external_id(self, account: AmazonAccount) -> dict[str, UUID]:
        """Load a map from external Ads campaign id to internal UUID."""
        rows = (
            await self.db.execute(
                select(AdvertisingCampaign.campaign_id, AdvertisingCampaign.id).where(
                    AdvertisingCampaign.account_id == account.id
                )
            )
        ).all()
        return {str(row.campaign_id): row.id for row in rows}

    async def _sync_advertising_campaigns(
        self,
        account: AmazonAccount,
        campaigns: list[dict[str, Any]],
    ) -> int:
        """Upsert campaigns returned by the Ads API."""
        count = 0
        for campaign in campaigns:
            campaign_id = await self._upsert_advertising_campaign(account, campaign)
            if campaign_id:
                count += 1
        return count

    async def sync_account(self, account_id: UUID) -> Dict[str, Any]:
        """Sync all data for an account."""
        result = await self.db.execute(
            select(AmazonAccount).where(AmazonAccount.id == account_id)
        )
        account = result.scalar_one_or_none()

        if not account:
            raise ValueError(f"Account {account_id} not found")

        try:
            warning_messages: list[str] = []
            warning_codes: list[str] = []

            async def _run_optional_step(label: str, operation):
                """Run a best-effort sync step without aborting the full account sync."""
                try:
                    return await operation()
                except Exception as exc:
                    detail = getattr(exc, "message", str(exc))
                    warning_message = f"{label} sync warning for {account.account_name}: {detail}"
                    logger.warning(warning_message)
                    warning_messages.append(warning_message)
                    warning_codes.append(getattr(exc, "error_code", type(exc).__name__))
                    account.last_sync_heartbeat_at = datetime.utcnow()
                    await self.db.flush()
                    return 0

            previous_sync_started_at = account.last_sync_started_at
            previous_sync_succeeded_at = account.last_sync_succeeded_at or account.last_sync_at
            started_at = datetime.utcnow()
            account.sync_status = SyncStatus.SYNCING
            account.last_sync_started_at = started_at
            account.last_sync_attempt_at = started_at
            account.last_sync_heartbeat_at = started_at
            account.sync_error_message = None
            account.sync_error_code = None
            account.sync_error_kind = None
            await self.db.flush()

            # Load org for credential resolution
            organization = await self._load_organization(account)

            # Validate SP-API auth before sync
            client = self._create_sp_api_client(account, organization)
            client.smoke_test()
            logger.info(f"SP-API auth validated for {account.account_name}")
            await self._touch_sync(account)

            # Sync different data types based on account type
            from app.models.amazon_account import AccountType
            if account.account_type == AccountType.VENDOR:
                sales_count = await self.sync_vendor_sales_data(account, organization)
                await self._touch_sync(account)
                inventory_count = 0  # Vendors don't use FBA inventory
                orders_count = 0
                returns_count = 0
                advertising_count = await _run_optional_step(
                    "Advertising",
                    lambda: self.sync_advertising(account, organization),
                )
                await self._touch_sync(account)
                products_count = await _run_optional_step(
                    "Product",
                    lambda: self.sync_products(account, organization),
                )
            else:
                sales_count = await self.sync_sales_data(account, organization)
                await self._touch_sync(account)
                inventory_count = await _run_optional_step(
                    "Inventory",
                    lambda: self.sync_inventory(account, organization),
                )
                await self._touch_sync(account)
                orders_count = await _run_optional_step(
                    "Orders",
                    lambda: self.sync_orders(
                        account,
                        organization,
                        last_sync_started_at=previous_sync_started_at,
                        last_sync_succeeded_at=previous_sync_succeeded_at,
                    ),
                )
                await self._touch_sync(account)
                returns_count = await _run_optional_step(
                    "Returns",
                    lambda: self.sync_returns(account, organization),
                )
                await self._touch_sync(account)
                advertising_count = await _run_optional_step(
                    "Advertising",
                    lambda: self.sync_advertising(account, organization),
                )
                await self._touch_sync(account)
                products_count = await _run_optional_step(
                    "Product",
                    lambda: self.sync_products(account, organization),
                )

            completed_at = datetime.utcnow()
            account.sync_status = SyncStatus.SUCCESS
            account.last_sync_at = completed_at
            account.last_sync_succeeded_at = completed_at
            account.last_sync_heartbeat_at = completed_at
            account.sync_error_message = " | ".join(warning_messages) if warning_messages else None
            account.sync_error_code = warning_codes[0] if warning_codes else None
            account.sync_error_kind = "warning" if warning_messages else None
            await self.db.flush()

            return {
                "status": "success",
                "sales_records": sales_count,
                "inventory_records": inventory_count,
                "order_records": orders_count,
                "return_records": returns_count,
                "products": products_count,
                "advertising_records": advertising_count,
                "warnings": warning_messages,
            }

        except Exception as e:
            logger.exception(f"Error syncing account {account_id}")
            account.last_sync_heartbeat_at = datetime.utcnow()
            await self.db.flush()
            raise

    # ---- Sales Data ----

    async def _upsert_sales_record(self, values: dict) -> None:
        """Insert or update a sales record using ON CONFLICT DO UPDATE."""
        stmt = pg_insert(SalesData).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_sales_data_account_date_asin",
            set_={
                "sku": stmt.excluded.sku,
                "units_ordered": stmt.excluded.units_ordered,
                "units_ordered_b2b": stmt.excluded.units_ordered_b2b,
                "ordered_product_sales": stmt.excluded.ordered_product_sales,
                "ordered_product_sales_b2b": stmt.excluded.ordered_product_sales_b2b,
                "total_order_items": stmt.excluded.total_order_items,
                "currency": stmt.excluded.currency,
            },
        )
        await self.db.execute(stmt)

    async def sync_sales_data(
        self,
        account: AmazonAccount,
        organization=None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> int:
        """Sync sales data from SP-API Reports API."""
        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        client = self._create_sp_api_client(account, organization)
        report = client.get_sales_report(start_date, end_date)

        count = 0

        # --- Daily aggregate rows (salesAndTrafficByDate) ---
        for entry in report.get("by_date", []):
            entry_date_str = entry.get("date")
            if not entry_date_str:
                continue
            entry_date = date.fromisoformat(entry_date_str)

            sales_by_date = entry.get("salesByDate", {})
            ordered_sales = sales_by_date.get("orderedProductSales", {})
            ordered_sales_b2b = sales_by_date.get("orderedProductSalesB2B", {})

            await self._upsert_sales_record({
                "account_id": account.id,
                "date": entry_date,
                "asin": DAILY_TOTAL_ASIN,
                "sku": None,
                "units_ordered": sales_by_date.get("unitsOrdered", 0),
                "units_ordered_b2b": sales_by_date.get("unitsOrderedB2B", 0),
                "ordered_product_sales": Decimal(str(ordered_sales.get("amount", 0))),
                "ordered_product_sales_b2b": Decimal(str(ordered_sales_b2b.get("amount", 0))),
                "total_order_items": sales_by_date.get("totalOrderItems", 0),
                "currency": ordered_sales.get("currencyCode", "EUR"),
            })
            count += 1

        # --- Per-ASIN aggregate rows (salesAndTrafficByAsin) ---
        for entry in report.get("by_asin", []):
            asin = entry.get("childAsin") or entry.get("parentAsin")
            if not asin:
                continue

            sales_by_asin = entry.get("salesByAsin", {})
            ordered_sales = sales_by_asin.get("orderedProductSales", {})
            ordered_sales_b2b = sales_by_asin.get("orderedProductSalesB2B", {})

            await self._upsert_sales_record({
                "account_id": account.id,
                "date": end_date,
                "asin": asin,
                "sku": entry.get("sku"),
                "units_ordered": sales_by_asin.get("unitsOrdered", 0),
                "units_ordered_b2b": sales_by_asin.get("unitsOrderedB2B", 0),
                "ordered_product_sales": Decimal(str(ordered_sales.get("amount", 0))),
                "ordered_product_sales_b2b": Decimal(str(ordered_sales_b2b.get("amount", 0))),
                "total_order_items": sales_by_asin.get("totalOrderItems", 0),
                "currency": ordered_sales.get("currencyCode", "EUR"),
            })
            count += 1

        await self.db.flush()
        logger.info(
            f"Synced {count} sales records for {account.account_name} "
            f"({start_date} to {end_date})"
        )
        return count

    # ---- Vendor Sales Data ----

    async def sync_vendor_sales_data(
        self,
        account: AmazonAccount,
        organization=None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> int:
        """Sync sales data from vendor purchase orders."""
        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        client = self._create_sp_api_client(account, organization)

        # Accumulate daily totals for DAILY_TOTAL_ASIN sentinel records.
        # Keys are dates; values are dicts with running totals.
        daily_totals: Dict[date, dict] = {}

        def _accumulate_daily(entry_date: date, units: int, sales: Decimal, order_items: int, currency: str):
            if entry_date in daily_totals:
                dt = daily_totals[entry_date]
                dt["units_ordered"] += units
                dt["ordered_product_sales"] += sales
                dt["total_order_items"] += order_items
            else:
                daily_totals[entry_date] = {
                    "units_ordered": units,
                    "ordered_product_sales": sales,
                    "total_order_items": order_items,
                    "currency": currency,
                }

        # Try vendor sales diagnostic report first; fall back to purchase orders
        count = 0
        try:
            report = client.get_vendor_sales_report(start_date, end_date)
            sales_data_rows = report.get("salesDiagnosticData", report.get("salesByAsin", []))
            for entry in sales_data_rows:
                asin = entry.get("asin")
                entry_date_str = entry.get("date") or entry.get("startDate")
                if not asin or not entry_date_str:
                    continue
                try:
                    entry_date = date.fromisoformat(entry_date_str[:10])
                except ValueError:
                    continue

                ordered_revenue = entry.get("orderedRevenue", {})
                amount = Decimal(str(ordered_revenue.get("amount", 0))) if isinstance(ordered_revenue, dict) else Decimal("0")
                currency = ordered_revenue.get("currencyCode", "EUR") if isinstance(ordered_revenue, dict) else "EUR"
                units = entry.get("orderedUnits", 0)

                await self._upsert_sales_record({
                    "account_id": account.id,
                    "date": entry_date,
                    "asin": asin,
                    "sku": None,
                    "units_ordered": units,
                    "units_ordered_b2b": 0,
                    "ordered_product_sales": amount,
                    "ordered_product_sales_b2b": Decimal("0"),
                    "total_order_items": units,
                    "currency": currency,
                })
                count += 1
                _accumulate_daily(entry_date, units, amount, units, currency)

        except AmazonAPIError:
            logger.info(
                f"Vendor sales report not available for {account.account_name}, "
                "falling back to purchase orders"
            )
            # Fall back to purchase orders — aggregate by (date, asin) since
            # multiple POs can contain the same ASIN on the same day
            orders = client.get_vendor_purchase_orders(start_date, end_date)
            aggregated: Dict[tuple, dict] = {}

            for order in orders:
                po_date_str = order.get("orderDetails", {}).get("purchaseOrderDate")
                if not po_date_str:
                    continue
                try:
                    po_date = date.fromisoformat(po_date_str[:10])
                except ValueError:
                    continue

                items = order.get("orderDetails", {}).get("items", [])
                for item in items:
                    asin = item.get("amazonProductIdentifier")
                    if not asin:
                        continue

                    cost = item.get("netCost", {})
                    amount = Decimal(str(cost.get("amount", 0))) if isinstance(cost, dict) else Decimal("0")
                    currency = cost.get("currencyCode", "EUR") if isinstance(cost, dict) else "EUR"
                    qty = item.get("orderedQuantity", {}).get("amount", 0) if isinstance(item.get("orderedQuantity"), dict) else 0

                    key = (po_date, asin)
                    if key in aggregated:
                        agg = aggregated[key]
                        agg["units_ordered"] += qty
                        agg["ordered_product_sales"] += amount * qty if qty else amount
                        agg["total_order_items"] += qty
                    else:
                        aggregated[key] = {
                            "account_id": account.id,
                            "date": po_date,
                            "asin": asin,
                            "sku": item.get("vendorProductIdentifier"),
                            "units_ordered": qty,
                            "units_ordered_b2b": 0,
                            "ordered_product_sales": amount * qty if qty else amount,
                            "ordered_product_sales_b2b": Decimal("0"),
                            "total_order_items": qty,
                            "currency": currency,
                        }

            for values in aggregated.values():
                await self._upsert_sales_record(values)
                count += 1
                _accumulate_daily(
                    values["date"],
                    values["units_ordered"],
                    values["ordered_product_sales"],
                    values["total_order_items"],
                    values["currency"],
                )

        # --- Write DAILY_TOTAL_ASIN sentinel records for vendor data ---
        # These are required for dashboard KPIs, trends, and comparisons.
        for dt_date, totals in daily_totals.items():
            await self._upsert_sales_record({
                "account_id": account.id,
                "date": dt_date,
                "asin": DAILY_TOTAL_ASIN,
                "sku": None,
                "units_ordered": totals["units_ordered"],
                "units_ordered_b2b": 0,
                "ordered_product_sales": totals["ordered_product_sales"],
                "ordered_product_sales_b2b": Decimal("0"),
                "total_order_items": totals["total_order_items"],
                "currency": totals["currency"],
            })
            count += 1

        await self.db.flush()
        logger.info(
            f"Synced {count} vendor sales records for {account.account_name} "
            f"({start_date} to {end_date})"
        )
        return count

    # ---- Orders ----

    async def sync_orders(
        self,
        account: AmazonAccount,
        organization=None,
        *,
        last_sync_started_at: Optional[datetime] = None,
        last_sync_succeeded_at: Optional[datetime] = None,
    ) -> int:
        """Sync seller orders and order items from the SP-API Orders API."""
        from app.models.amazon_account import AccountType

        if account.account_type == AccountType.VENDOR:
            logger.info("Skipping Orders API sync for vendor account %s", account.account_name)
            return 0

        created_after, created_before = self._resolve_orders_sync_window(
            account,
            last_sync_started_at=last_sync_started_at,
            last_sync_succeeded_at=last_sync_succeeded_at,
        )
        if created_after >= created_before:
            logger.info(
                "Skipping Orders API sync for %s because the computed sync window is empty",
                account.account_name,
            )
            return 0

        client = self._create_sp_api_client(account, organization)
        raw_orders = client.fetch_orders(created_after, created_before)
        synced_orders = 0
        synced_items = 0
        last_orders_request_at = time.monotonic() - 1.0

        await self._touch_sync(account)

        for index, raw_order in enumerate(raw_orders, start=1):
            amazon_order_id = raw_order.get("AmazonOrderId") or raw_order.get("amazonOrderId")
            purchase_date = self._parse_sp_api_datetime(
                raw_order.get("PurchaseDate") or raw_order.get("purchaseDate")
            )

            if not amazon_order_id or purchase_date is None:
                logger.debug("Skipping order without required identifiers: %s", raw_order)
                continue

            elapsed = time.monotonic() - last_orders_request_at
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)

            raw_items = client.fetch_order_items(amazon_order_id)
            last_orders_request_at = time.monotonic()

            order_total, currency = self._extract_money(
                raw_order.get("OrderTotal") or raw_order.get("orderTotal")
            )
            number_of_items = (
                self._parse_int(raw_order.get("NumberOfItemsShipped"))
                + self._parse_int(raw_order.get("NumberOfItemsUnshipped"))
            )

            item_values = []
            for raw_item in raw_items:
                item_price, _ = self._extract_money(
                    raw_item.get("ItemPrice") or raw_item.get("itemPrice")
                )
                item_tax, _ = self._extract_money(
                    raw_item.get("ItemTax") or raw_item.get("itemTax")
                )
                quantity = self._parse_int(
                    raw_item.get("QuantityOrdered") or raw_item.get("quantityOrdered")
                )
                if quantity == 0:
                    quantity = self._parse_int(
                        raw_item.get("QuantityShipped") or raw_item.get("quantityShipped")
                    )

                item_values.append({
                    "asin": raw_item.get("ASIN") or raw_item.get("asin"),
                    "sku": raw_item.get("SellerSKU") or raw_item.get("sellerSku"),
                    "title": raw_item.get("Title") or raw_item.get("title"),
                    "quantity": quantity,
                    "item_price": item_price,
                    "item_tax": item_tax,
                })

            if number_of_items == 0 and item_values:
                number_of_items = sum(item["quantity"] for item in item_values)

            order_id = await self._upsert_order_record({
                "account_id": account.id,
                "amazon_order_id": amazon_order_id,
                "purchase_date": purchase_date,
                "order_status": raw_order.get("OrderStatus") or raw_order.get("orderStatus") or "Unknown",
                "fulfillment_channel": raw_order.get("FulfillmentChannel") or raw_order.get("fulfillmentChannel"),
                "order_total": order_total,
                "currency": currency,
                "marketplace_id": raw_order.get("MarketplaceId") or raw_order.get("marketplaceId") or account.marketplace_id,
                "number_of_items": number_of_items,
            })
            await self._replace_order_items(
                order_id,
                [{"order_id": order_id, **item_value} for item_value in item_values],
            )

            synced_orders += 1
            synced_items += len(item_values)

            if index % 10 == 0 or index == len(raw_orders):
                await self._touch_sync(account)

        await self.db.flush()
        logger.info(
            "Synced %s orders and %s order items for %s (%s to %s)",
            synced_orders,
            synced_items,
            account.account_name,
            created_after.isoformat(),
            created_before.isoformat(),
        )
        return synced_orders

    # ---- Returns ----

    async def _upsert_return_record(self, values: dict) -> None:
        """Insert or update a return event using a stable event identity."""
        stmt = pg_insert(ReturnData).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                ReturnData.account_id,
                ReturnData.return_date,
                func.coalesce(ReturnData.amazon_order_id, ""),
                func.coalesce(ReturnData.asin, ""),
                func.coalesce(ReturnData.sku, ""),
                func.coalesce(ReturnData.reason, ""),
                func.coalesce(ReturnData.disposition, ""),
                func.coalesce(ReturnData.detailed_disposition, ""),
            ],
            set_={
                "quantity": stmt.excluded.quantity,
                "amazon_order_id": stmt.excluded.amazon_order_id,
                "asin": stmt.excluded.asin,
                "sku": stmt.excluded.sku,
                "reason": stmt.excluded.reason,
                "disposition": stmt.excluded.disposition,
                "detailed_disposition": stmt.excluded.detailed_disposition,
            },
        )
        await self.db.execute(stmt)

    async def sync_returns(self, account: AmazonAccount, organization=None) -> int:
        """Sync seller FBA return events from the returns report."""
        from app.models.amazon_account import AccountType

        if account.account_type == AccountType.VENDOR:
            logger.info("Skipping returns sync for vendor account %s", account.account_name)
            return 0

        client = self._create_sp_api_client(account, organization)
        raw_rows = client.fetch_returns_report()

        deduped_rows: Dict[tuple[Any, ...], dict] = {}
        failed_rows = 0

        for raw_row in raw_rows:
            try:
                return_date = raw_row.get("return_date")
                quantity = self._parse_int(raw_row.get("quantity"))

                if return_date is None:
                    failed_rows += 1
                    logger.debug("Skipping return row without return_date: %s", raw_row)
                    continue
                if quantity <= 0:
                    logger.debug("Skipping return row with non-positive quantity: %s", raw_row)
                    continue

                values = {
                    "account_id": account.id,
                    "amazon_order_id": raw_row.get("amazon_order_id") or None,
                    "asin": (
                        raw_row.get("asin").strip().upper() or None
                        if isinstance(raw_row.get("asin"), str)
                        else raw_row.get("asin") or None
                    ),
                    "sku": raw_row.get("sku") or None,
                    "return_date": return_date,
                    "quantity": quantity,
                    "reason": raw_row.get("reason") or None,
                    "disposition": raw_row.get("disposition") or None,
                    "detailed_disposition": raw_row.get("detailed_disposition") or None,
                }
                dedupe_key = (
                    values["return_date"],
                    values["amazon_order_id"] or "",
                    values["asin"] or "",
                    values["sku"] or "",
                    values["reason"] or "",
                    values["disposition"] or "",
                    values["detailed_disposition"] or "",
                )

                existing = deduped_rows.get(dedupe_key)
                if existing:
                    existing["quantity"] = max(existing["quantity"], values["quantity"])
                    for field in (
                        "amazon_order_id",
                        "asin",
                        "sku",
                        "reason",
                        "disposition",
                        "detailed_disposition",
                    ):
                        if not existing.get(field) and values.get(field):
                            existing[field] = values[field]
                    continue

                deduped_rows[dedupe_key] = values
            except Exception:
                failed_rows += 1
                logger.exception("Failed to normalize return row for %s: %s", account.account_name, raw_row)

        for index, values in enumerate(deduped_rows.values(), start=1):
            await self._upsert_return_record(values)
            if index % 250 == 0 or index == len(deduped_rows):
                await self._touch_sync(account)

        await self.db.flush()
        logger.info(
            "Synced %s return rows for %s from %s report rows (%s failed)",
            len(deduped_rows),
            account.account_name,
            len(raw_rows),
            failed_rows,
        )
        return len(deduped_rows)

    # ---- Inventory Data ----

    async def _upsert_inventory_record(self, values: dict) -> None:
        """Insert or update a single inventory snapshot row."""
        stmt = pg_insert(InventoryData).values(**values)
        set_values = {
            "afn_fulfillable_quantity": stmt.excluded.afn_fulfillable_quantity,
            "afn_inbound_working_quantity": stmt.excluded.afn_inbound_working_quantity,
            "afn_inbound_shipped_quantity": stmt.excluded.afn_inbound_shipped_quantity,
            "afn_reserved_quantity": stmt.excluded.afn_reserved_quantity,
            "afn_total_quantity": stmt.excluded.afn_total_quantity,
            "mfn_fulfillable_quantity": stmt.excluded.mfn_fulfillable_quantity,
        }
        if values.get("sku"):
            set_values["sku"] = stmt.excluded.sku
        if values.get("fnsku") is not None:
            set_values["fnsku"] = stmt.excluded.fnsku

        stmt = stmt.on_conflict_do_update(
            constraint="uq_inventory_account_date_asin",
            set_=set_values,
        )
        await self.db.execute(stmt)

    async def sync_inventory(self, account: AmazonAccount, organization=None) -> int:
        """Sync inventory data from the FBA inventory report."""
        client = self._create_sp_api_client(account, organization)
        try:
            items = client.fetch_inventory_report()
        except AmazonAPIError as exc:
            if exc.error_code not in {"INVENTORY_REPORT_FATAL", "INVENTORY_REPORT_CANCELLED"}:
                raise

            logger.warning(
                "Inventory report failed for %s (%s). Falling back to inventory summaries.",
                account.account_name,
                exc.error_code,
            )
            summary_items = [
                normalized
                for raw_item in client.get_inventory_summaries()
                if (normalized := self._normalize_inventory_summary_item(raw_item))
            ]
            if not summary_items:
                raise AmazonAPIError(
                    (
                        f"Inventory sync failed for {account.account_name}: Amazon did not return "
                        f"inventory data for marketplace {account.marketplace_country}. "
                        f"{exc.message} The inventory summaries API returned 0 items."
                    ),
                    error_code="INVENTORY_NOT_AVAILABLE",
                ) from exc
            items = summary_items
        else:
            if not items:
                summary_items = [
                    normalized
                    for raw_item in client.get_inventory_summaries()
                    if (normalized := self._normalize_inventory_summary_item(raw_item))
                ]
                if summary_items:
                    logger.info(
                        "Inventory report returned no rows for %s; using %d rows from inventory summaries.",
                        account.account_name,
                        len(summary_items),
                    )
                    items = summary_items

        snapshot_date = date.today()
        # The current schema stores one row per (account, date, asin), so
        # multiple report rows for the same ASIN are folded into a single snapshot.
        aggregated: Dict[str, dict] = {}

        for item in items:
            asin = item.get("asin")
            if not asin:
                continue

            quantity = int(item.get("quantity") or 0)
            reserved_quantity = int(item.get("reserved_quantity") or 0)
            inbound_working_quantity = int(item.get("inbound_working_quantity") or 0)
            inbound_shipped_quantity = int(item.get("inbound_shipped_quantity") or 0)
            inbound_quantity = int(
                item.get("inbound_quantity")
                or (inbound_working_quantity + inbound_shipped_quantity)
            )
            fulfillment_channel = str(item.get("fulfillment_channel") or "AFN").upper()

            values = aggregated.setdefault(
                asin,
                {
                    "account_id": account.id,
                    "snapshot_date": snapshot_date,
                    "asin": asin,
                    "sku": item.get("sku"),
                    "fnsku": item.get("fnsku"),
                    "afn_fulfillable_quantity": 0,
                    "afn_inbound_working_quantity": 0,
                    "afn_inbound_shipped_quantity": 0,
                    "afn_reserved_quantity": 0,
                    "afn_total_quantity": 0,
                    "mfn_fulfillable_quantity": 0,
                },
            )

            if not values.get("sku") and item.get("sku"):
                values["sku"] = item.get("sku")
            if not values.get("fnsku") and item.get("fnsku"):
                values["fnsku"] = item.get("fnsku")

            if fulfillment_channel == "MFN":
                values["mfn_fulfillable_quantity"] += quantity
                continue

            values["afn_fulfillable_quantity"] += quantity
            values["afn_inbound_working_quantity"] += inbound_working_quantity
            values["afn_inbound_shipped_quantity"] += inbound_shipped_quantity
            values["afn_reserved_quantity"] += reserved_quantity
            values["afn_total_quantity"] += quantity + reserved_quantity + inbound_quantity

        for values in aggregated.values():
            await self._upsert_inventory_record(values)

        await self.db.flush()
        logger.info(
            "Synced %d inventory records for %s from %d report rows",
            len(aggregated),
            account.account_name,
            len(items),
        )
        return len(aggregated)

    async def sync_inventory_data(self, account: AmazonAccount, organization=None) -> int:
        """Backward-compatible alias for inventory sync."""
        return await self.sync_inventory(account, organization)

    # ---- Products ----

    async def sync_products(self, account: AmazonAccount, organization=None) -> int:
        """Sync product catalog from SP-API CatalogItems + Products API."""
        # Gather distinct ASINs from sales and inventory data
        sales_asins = await self.db.execute(
            select(SalesData.asin)
            .where(SalesData.account_id == account.id)
            .distinct()
        )
        inv_asins = await self.db.execute(
            select(InventoryData.asin)
            .where(InventoryData.account_id == account.id)
            .distinct()
        )

        all_asins = set()
        for row in sales_asins:
            if row[0] != DAILY_TOTAL_ASIN:
                all_asins.add(row[0])
        for row in inv_asins:
            all_asins.add(row[0])

        if not all_asins:
            logger.info(f"No ASINs found for product sync on {account.account_name}")
            return 0

        client = self._create_sp_api_client(account, organization)
        asin_list = sorted(all_asins)
        batch_size = 5
        count = 0

        for i in range(0, len(asin_list), batch_size):
            batch = asin_list[i : i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(asin_list) + batch_size - 1) // batch_size
            logger.info(
                f"Syncing products batch {batch_num}/{total_batches} "
                f"for {account.account_name}"
            )

            for asin in batch:
                catalog_data = client.get_catalog_item_details(asin)
                # Competitive pricing API is seller-only; skip for vendor accounts
                competitive_price = None if client.is_vendor else client.get_competitive_pricing(asin)

                # Parse catalog data
                title = None
                brand = None
                category = None
                bsr = None

                if catalog_data:
                    summaries = catalog_data.get("summaries", [])
                    if summaries:
                        summary = summaries[0]
                        title = summary.get("itemName")
                        brand = summary.get("brand")

                    # Classifications is a top-level field, not nested in summaries
                    classifications = catalog_data.get("classifications", [])
                    if classifications:
                        classification = classifications[0]
                        # Try displayName first, then classificationId
                        category = (
                            classification.get("displayName")
                            or classification.get("classification", {}).get("displayName")
                        )

                    sales_ranks = catalog_data.get("salesRanks", [])
                    if sales_ranks:
                        ranks = sales_ranks[0].get("ranks", [])
                        if ranks:
                            bsr = ranks[0].get("value")

                # Upsert: find existing product by (account_id, asin) or create new
                existing = (await self.db.execute(
                    select(Product).where(
                        Product.account_id == account.id,
                        Product.asin == asin,
                    )
                )).scalar_one_or_none()

                if existing:
                    existing.title = title or existing.title
                    existing.brand = brand or existing.brand
                    existing.category = category or existing.category
                    existing.current_price = competitive_price if competitive_price is not None else existing.current_price
                    existing.current_bsr = bsr if bsr is not None else existing.current_bsr
                    existing.is_active = True
                    product_record = existing
                else:
                    product_record = Product(
                        account_id=account.id,
                        asin=asin,
                        title=title,
                        brand=brand,
                        category=category,
                        current_price=competitive_price,
                        current_bsr=bsr,
                        review_count=None,
                        rating=None,
                        is_active=True,
                    )
                    self.db.add(product_record)
                    await self.db.flush()

                if bsr is not None:
                    bsr_history = (
                        await self.db.execute(
                            select(BSRHistory).where(
                                BSRHistory.product_id == product_record.id,
                                BSRHistory.date == date.today(),
                                BSRHistory.category == (category or product_record.category),
                            )
                        )
                    ).scalar_one_or_none()

                    if bsr_history:
                        bsr_history.bsr = bsr
                    else:
                        self.db.add(
                            BSRHistory(
                                product_id=product_record.id,
                                date=date.today(),
                                category=category or product_record.category,
                                bsr=bsr,
                            )
                        )
                count += 1

            # Sleep between batches to respect rate limits
            if i + batch_size < len(asin_list):
                time.sleep(1)

        await self.db.flush()
        logger.info(f"Synced {count} products for {account.account_name}")
        return count

    # ---- Advertising ----

    def _extract_report_rows(self, report_payload: Any) -> list[dict[str, Any]]:
        """Extract the row collection from a report response."""
        if isinstance(report_payload, list):
            return report_payload
        if isinstance(report_payload, dict):
            for key in ("rows", "report", "records", "data"):
                rows = report_payload.get(key)
                if isinstance(rows, list):
                    return rows
                if isinstance(rows, dict):
                    nested_rows = self._extract_report_rows(rows)
                    if nested_rows:
                        return nested_rows
        return []

    def _extract_report_date(self, row: dict[str, Any]) -> date | None:
        """Normalize report row date fields to a date."""
        value = row.get("date") or row.get("reportDate") or row.get("startDate")
        if not value:
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    def _extract_order_count(self, row: dict[str, Any], window: str) -> int:
        """Read attributed order fields across the different Ads report spellings."""
        keys = (
            f"orders{window}",
            f"purchases{window}",
            f"attributedConversions{window}",
            f"purchasesClicks{window}",
            f"unitsSoldClicks{window}",
            f"attributedUnitsOrdered{window}",
        )
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return self._int_value(value)
        return 0

    def _extract_sales_amount(self, row: dict[str, Any], window: str) -> Decimal:
        """Read attributed sales fields across the different Ads report spellings."""
        keys = (
            f"sales{window}",
            f"attributedSales{window}",
            f"purchasesSales{window}",
        )
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return self._decimal(value)
        return Decimal("0")

    async def sync_advertising(self, account: AmazonAccount, organization=None) -> int:
        """Sync advertising campaigns and daily Sponsored Products metrics."""
        if not account.advertising_refresh_token_encrypted:
            logger.info(
                "Skipping advertising sync for %s: missing refresh token",
                account.account_name,
            )
            return 0

        try:
            client, profile_id = self._create_advertising_api_client(account, organization)
        except AmazonAPIError as exc:
            if exc.error_code in {"MISSING_ADVERTISING_CREDENTIALS", "MISSING_ADVERTISING_PROFILE"}:
                logger.info("Skipping advertising sync for %s: %s", account.account_name, exc)
                return 0
            raise

        try:
            campaigns = client.list_campaigns(profile_id)
            campaign_count = await self._sync_advertising_campaigns(account, campaigns)
            await self.db.flush()

            end_date = date.today()
            start_date = end_date - timedelta(days=6)
            report_id = client.request_report(
                profile_id=profile_id,
                report_type="sp_campaigns",
                date_range=(start_date, end_date),
            )
            report_payload = client.download_report(profile_id=profile_id, report_id=report_id)
        finally:
            client.close()

        campaign_id_map = await self._campaign_ids_by_external_id(account)
        metric_count = 0

        for row in self._extract_report_rows(report_payload):
            external_campaign_id = self._normalize_campaign_id(row)
            if not external_campaign_id:
                continue

            internal_campaign_id = campaign_id_map.get(external_campaign_id)
            if internal_campaign_id is None:
                internal_campaign_id = await self._upsert_advertising_campaign(
                    account,
                    {
                        "campaignId": external_campaign_id,
                        "campaignName": row.get("campaignName") or row.get("name"),
                        "campaignType": "sponsoredProducts",
                        "campaignStatus": row.get("campaignStatus") or row.get("state"),
                    },
                )
                if internal_campaign_id is None:
                    continue
                campaign_id_map[external_campaign_id] = internal_campaign_id
                campaign_count += 1

            metric_date = self._extract_report_date(row)
            if not metric_date:
                continue

            impressions = self._int_value(row.get("impressions"))
            clicks = self._int_value(row.get("clicks"))
            cost = self._decimal(row.get("cost"))
            sales_1d = self._extract_sales_amount(row, "1d")
            sales_7d = self._extract_sales_amount(row, "7d")
            sales_14d = self._extract_sales_amount(row, "14d")
            sales_30d = self._extract_sales_amount(row, "30d")
            orders_1d = self._extract_order_count(row, "1d")
            orders_7d = self._extract_order_count(row, "7d")
            orders_14d = self._extract_order_count(row, "14d")
            orders_30d = self._extract_order_count(row, "30d")

            ctr = self._metric_ratio(Decimal(clicks) * Decimal("100"), Decimal(impressions)) if impressions > 0 else Decimal("0")
            cpc = self._metric_ratio(cost, Decimal(clicks)) if clicks > 0 else Decimal("0")
            acos = self._metric_ratio(cost * Decimal("100"), sales_7d) if sales_7d > 0 else Decimal("0")
            roas = self._metric_ratio(sales_7d, cost) if cost > 0 else Decimal("0")

            await self._upsert_advertising_metrics(
                {
                    "campaign_id": internal_campaign_id,
                    "date": metric_date,
                    "impressions": impressions,
                    "clicks": clicks,
                    "cost": cost,
                    "attributed_sales_1d": sales_1d,
                    "attributed_sales_7d": sales_7d,
                    "attributed_sales_14d": sales_14d,
                    "attributed_sales_30d": sales_30d,
                    "attributed_units_ordered_1d": orders_1d,
                    "attributed_units_ordered_7d": orders_7d,
                    "attributed_units_ordered_14d": orders_14d,
                    "attributed_units_ordered_30d": orders_30d,
                    "ctr": ctr,
                    "cpc": cpc,
                    "acos": acos,
                    "roas": roas,
                }
            )
            metric_count += 1

        await self.db.flush()
        logger.info(
            "Synced %d advertising campaigns and %d metric rows for %s",
            campaign_count,
            metric_count,
            account.account_name,
        )
        return metric_count

    async def sync_advertising_data(self, account: AmazonAccount, organization=None) -> int:
        """Backward-compatible alias for advertising sync."""
        return await self.sync_advertising(account, organization)
