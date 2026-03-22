"""Data extraction service for Amazon data."""
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal
import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.amazon_account import AmazonAccount, SyncStatus
from app.models.sales_data import SalesData
from app.models.inventory import InventoryData
from app.models.product import Product
from app.core.security import decrypt_value
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

    async def sync_account(self, account_id: UUID) -> Dict[str, Any]:
        """Sync all data for an account."""
        result = await self.db.execute(
            select(AmazonAccount).where(AmazonAccount.id == account_id)
        )
        account = result.scalar_one_or_none()

        if not account:
            raise ValueError(f"Account {account_id} not found")

        try:
            account.sync_status = SyncStatus.SYNCING
            await self.db.flush()

            # Load org for credential resolution
            organization = await self._load_organization(account)

            # Validate SP-API auth before sync
            client = self._create_sp_api_client(account, organization)
            client.smoke_test()
            logger.info(f"SP-API auth validated for {account.account_name}")

            # Sync different data types based on account type
            from app.models.amazon_account import AccountType
            if account.account_type == AccountType.VENDOR:
                sales_count = await self.sync_vendor_sales_data(account, organization)
                inventory_count = 0  # Vendors don't use FBA inventory
                products_count = await self.sync_products(account, organization)
            else:
                sales_count = await self.sync_sales_data(account, organization)
                inventory_count = await self.sync_inventory_data(account, organization)
                products_count = await self.sync_products(account, organization)

            account.sync_status = SyncStatus.SUCCESS
            account.last_sync_at = datetime.utcnow()
            account.sync_error_message = None
            await self.db.flush()

            return {
                "status": "success",
                "sales_records": sales_count,
                "inventory_records": inventory_count,
                "products": products_count,
            }

        except Exception as e:
            logger.exception(f"Error syncing account {account_id}")
            account.sync_status = SyncStatus.ERROR
            account.sync_error_message = str(e)
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

    # ---- Inventory Data ----

    async def sync_inventory_data(self, account: AmazonAccount, organization=None) -> int:
        """Sync inventory data from SP-API Inventories API."""
        client = self._create_sp_api_client(account, organization)
        items = client.get_inventory_summaries()

        snapshot_date = date.today()
        count = 0

        for item in items:
            asin = item.get("asin")
            if not asin:
                continue

            details = item.get("inventoryDetails", {})
            reserved = details.get("reservedQuantity", {})

            values = {
                "account_id": account.id,
                "snapshot_date": snapshot_date,
                "asin": asin,
                "sku": item.get("sellerSku"),
                "fnsku": item.get("fnSku"),
                "afn_fulfillable_quantity": details.get("fulfillableQuantity", 0),
                "afn_inbound_working_quantity": details.get("inboundWorkingQuantity", 0),
                "afn_inbound_shipped_quantity": details.get("inboundShippedQuantity", 0),
                "afn_reserved_quantity": reserved.get("totalReservedQuantity", 0),
                "afn_total_quantity": item.get("totalQuantity", 0),
            }
            stmt = pg_insert(InventoryData).values(**values)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_inventory_account_date_asin",
                set_={
                    "sku": stmt.excluded.sku,
                    "fnsku": stmt.excluded.fnsku,
                    "afn_fulfillable_quantity": stmt.excluded.afn_fulfillable_quantity,
                    "afn_inbound_working_quantity": stmt.excluded.afn_inbound_working_quantity,
                    "afn_inbound_shipped_quantity": stmt.excluded.afn_inbound_shipped_quantity,
                    "afn_reserved_quantity": stmt.excluded.afn_reserved_quantity,
                    "afn_total_quantity": stmt.excluded.afn_total_quantity,
                },
            )
            await self.db.execute(stmt)
            count += 1

        await self.db.flush()
        logger.info(f"Synced {count} inventory records for {account.account_name}")
        return count

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
                else:
                    product = Product(
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
                    self.db.add(product)
                count += 1

            # Sleep between batches to respect rate limits
            if i + batch_size < len(asin_list):
                time.sleep(1)

        await self.db.flush()
        logger.info(f"Synced {count} products for {account.account_name}")
        return count

    # ---- Advertising ----
    # NOTE: No real Ads API integration yet. This method still generates
    # placeholder data. Replace with real Amazon Advertising API calls
    # once credentials and client are implemented.

    async def sync_advertising_data(self, account: AmazonAccount, organization=None) -> int:
        """Sync advertising data for an account."""
        from app.models.advertising import AdvertisingCampaign, AdvertisingMetrics
        import random

        sample_campaigns = [
            {"id": "CAMP001", "name": "Brand Awareness", "type": "sponsoredBrands"},
            {"id": "CAMP002", "name": "Product Launch", "type": "sponsoredProducts"},
            {"id": "CAMP003", "name": "Retargeting", "type": "sponsoredDisplay"},
        ]

        count = 0
        for camp in sample_campaigns:
            campaign = AdvertisingCampaign(
                account_id=account.id,
                campaign_id=camp["id"],
                campaign_name=camp["name"],
                campaign_type=camp["type"],
                state="enabled",
                daily_budget=Decimal(str(random.uniform(50, 500))).quantize(Decimal("0.01")),
                targeting_type="auto",
            )
            await self.db.merge(campaign)

            # Add metrics for last 30 days
            for days_ago in range(30):
                metric_date = date.today() - timedelta(days=days_ago)
                impressions = random.randint(1000, 50000)
                clicks = random.randint(10, 500)
                cost = Decimal(str(random.uniform(5, 100))).quantize(Decimal("0.01"))
                sales = cost * Decimal(str(random.uniform(1.5, 5)))

                metrics = AdvertisingMetrics(
                    campaign_id=campaign.id,
                    date=metric_date,
                    impressions=impressions,
                    clicks=clicks,
                    cost=cost,
                    attributed_sales_7d=sales,
                    attributed_units_ordered_7d=random.randint(1, 20),
                    ctr=Decimal(str(clicks / impressions * 100)).quantize(Decimal("0.0001")),
                    cpc=(cost / clicks).quantize(Decimal("0.0001")) if clicks > 0 else Decimal("0"),
                    acos=((cost / sales) * 100).quantize(Decimal("0.0001")) if sales > 0 else Decimal("0"),
                    roas=(sales / cost).quantize(Decimal("0.0001")) if cost > 0 else Decimal("0"),
                )
                await self.db.merge(metrics)
                count += 1

        await self.db.flush()
        return count
