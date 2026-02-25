"""Data extraction service for Amazon data."""
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal
import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models.amazon_account import AmazonAccount, SyncStatus
from app.models.sales_data import SalesData
from app.models.inventory import InventoryData
from app.models.product import Product
from app.core.security import decrypt_value
from app.core.exceptions import AmazonAPIError

logger = logging.getLogger(__name__)


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
        return SPAPIClient(credentials, marketplace)

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

            # Validate SP-API auth before real sync
            if not settings.USE_MOCK_DATA:
                client = self._create_sp_api_client(account, organization)
                client.smoke_test()
                logger.info(f"SP-API auth validated for {account.account_name}")

            # Sync different data types
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

    async def sync_sales_data(
        self,
        account: AmazonAccount,
        organization=None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> int:
        """Sync sales data for an account."""
        if settings.USE_MOCK_DATA:
            return await self._mock_sync_sales_data(account, start_date, end_date)
        return await self._real_sync_sales_data(account, organization, start_date, end_date)

    async def _real_sync_sales_data(
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
        rows = client.get_sales_report(start_date, end_date)

        count = 0
        for entry in rows:
            asin = entry.get("childAsin") or entry.get("parentAsin")
            if not asin:
                continue

            sales_by_asin = entry.get("salesByAsin", {})
            ordered_sales = sales_by_asin.get("orderedProductSales", {})
            ordered_sales_b2b = sales_by_asin.get("orderedProductSalesB2B", {})

            # Parse date from the entry
            entry_date_str = entry.get("date")
            if entry_date_str:
                entry_date = date.fromisoformat(entry_date_str)
            else:
                entry_date = date.today()

            sales_record = SalesData(
                account_id=account.id,
                date=entry_date,
                asin=asin,
                sku=entry.get("sku"),
                units_ordered=sales_by_asin.get("unitsOrdered", 0),
                units_ordered_b2b=sales_by_asin.get("unitsOrderedB2B", 0),
                ordered_product_sales=Decimal(
                    str(ordered_sales.get("amount", 0))
                ),
                ordered_product_sales_b2b=Decimal(
                    str(ordered_sales_b2b.get("amount", 0))
                ),
                total_order_items=sales_by_asin.get("totalOrderItems", 0),
                currency=ordered_sales.get("currencyCode", "EUR"),
            )

            await self.db.merge(sales_record)
            count += 1

        await self.db.flush()
        logger.info(
            f"Synced {count} sales records for {account.account_name} "
            f"({start_date} to {end_date})"
        )
        return count

    async def _mock_sync_sales_data(
        self,
        account: AmazonAccount,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> int:
        """Generate mock sales data for demonstration."""
        import random

        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        sample_asins = [
            "B08N5WRWNW",
            "B08N5M7S6K",
            "B08MQZYSVC",
            "B09KMQV3QJ",
            "B09B8YWXWB",
        ]

        count = 0
        current_date = start_date
        while current_date <= end_date:
            for asin in sample_asins:
                units = random.randint(1, 50)
                price = Decimal(str(random.uniform(10, 100))).quantize(Decimal("0.01"))
                sales = price * units

                sales_record = SalesData(
                    account_id=account.id,
                    date=current_date,
                    asin=asin,
                    sku=f"SKU-{asin[-4:]}",
                    units_ordered=units,
                    units_ordered_b2b=random.randint(0, 5),
                    ordered_product_sales=sales,
                    ordered_product_sales_b2b=Decimal("0"),
                    total_order_items=units,
                    currency="EUR",
                )

                await self.db.merge(sales_record)
                count += 1

            current_date += timedelta(days=1)

        await self.db.flush()
        return count

    # ---- Inventory Data ----

    async def sync_inventory_data(self, account: AmazonAccount, organization=None) -> int:
        """Sync inventory data for an account."""
        if settings.USE_MOCK_DATA:
            return await self._mock_sync_inventory_data(account)
        return await self._real_sync_inventory_data(account, organization)

    async def _real_sync_inventory_data(self, account: AmazonAccount, organization=None) -> int:
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

            inventory_record = InventoryData(
                account_id=account.id,
                snapshot_date=snapshot_date,
                asin=asin,
                sku=item.get("sellerSku"),
                fnsku=item.get("fnSku"),
                afn_fulfillable_quantity=details.get("fulfillableQuantity", 0),
                afn_inbound_working_quantity=details.get("inboundWorkingQuantity", 0),
                afn_inbound_shipped_quantity=details.get("inboundShippedQuantity", 0),
                afn_reserved_quantity=reserved.get("totalReservedQuantity", 0),
                afn_total_quantity=item.get("totalQuantity", 0),
            )

            await self.db.merge(inventory_record)
            count += 1

        await self.db.flush()
        logger.info(f"Synced {count} inventory records for {account.account_name}")
        return count

    async def _mock_sync_inventory_data(self, account: AmazonAccount) -> int:
        """Generate mock inventory data for demonstration."""
        import random

        sample_asins = [
            "B08N5WRWNW",
            "B08N5M7S6K",
            "B08MQZYSVC",
            "B09KMQV3QJ",
            "B09B8YWXWB",
        ]

        count = 0
        snapshot_date = date.today()

        for asin in sample_asins:
            inventory_record = InventoryData(
                account_id=account.id,
                snapshot_date=snapshot_date,
                asin=asin,
                sku=f"SKU-{asin[-4:]}",
                fnsku=f"X00{asin[-5:]}",
                afn_fulfillable_quantity=random.randint(10, 500),
                afn_inbound_working_quantity=random.randint(0, 50),
                afn_inbound_shipped_quantity=random.randint(0, 100),
                afn_reserved_quantity=random.randint(0, 20),
                afn_total_quantity=random.randint(100, 600),
                mfn_fulfillable_quantity=random.randint(0, 50),
            )

            await self.db.merge(inventory_record)
            count += 1

        await self.db.flush()
        return count

    # ---- Products ----

    async def sync_products(self, account: AmazonAccount, organization=None) -> int:
        """Sync product catalog for an account."""
        if settings.USE_MOCK_DATA:
            return await self._mock_sync_products(account)
        return await self._real_sync_products(account, organization)

    async def _real_sync_products(self, account: AmazonAccount, organization=None) -> int:
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
                competitive_price = client.get_competitive_pricing(asin)

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
                        classifications = summary.get("classifications", [])
                        if classifications:
                            category = classifications[0].get("displayName")

                    sales_ranks = catalog_data.get("salesRanks", [])
                    if sales_ranks:
                        ranks = sales_ranks[0].get("ranks", [])
                        if ranks:
                            bsr = ranks[0].get("value")

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

                await self.db.merge(product)
                count += 1

            # Sleep between batches to respect rate limits
            if i + batch_size < len(asin_list):
                time.sleep(1)

        await self.db.flush()
        logger.info(f"Synced {count} products for {account.account_name}")
        return count

    async def _mock_sync_products(self, account: AmazonAccount) -> int:
        """Generate mock product data for demonstration."""
        import random

        sample_products = [
            {"asin": "B08N5WRWNW", "title": "Premium Wireless Earbuds", "brand": "TechBrand", "category": "Electronics"},
            {"asin": "B08N5M7S6K", "title": "Bluetooth Speaker", "brand": "SoundMax", "category": "Electronics"},
            {"asin": "B08MQZYSVC", "title": "Fitness Tracker Watch", "brand": "FitLife", "category": "Sports"},
            {"asin": "B09KMQV3QJ", "title": "Organic Coffee Beans", "brand": "CafeBio", "category": "Grocery"},
            {"asin": "B09B8YWXWB", "title": "Yoga Mat Premium", "brand": "ZenFit", "category": "Sports"},
        ]

        count = 0
        for prod in sample_products:
            product = Product(
                account_id=account.id,
                asin=prod["asin"],
                sku=f"SKU-{prod['asin'][-4:]}",
                title=prod["title"],
                brand=prod["brand"],
                category=prod["category"],
                current_price=Decimal(str(random.uniform(20, 150))).quantize(Decimal("0.01")),
                current_bsr=random.randint(1000, 50000),
                review_count=random.randint(50, 5000),
                rating=Decimal(str(random.uniform(3.5, 5.0))).quantize(Decimal("0.01")),
                is_active=True,
            )

            await self.db.merge(product)
            count += 1

        await self.db.flush()
        return count

    # ---- Advertising (unchanged - always mock for now) ----

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
