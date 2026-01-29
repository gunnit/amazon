"""Data extraction service for Amazon data."""
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.amazon_account import AmazonAccount, SyncStatus
from app.models.sales_data import SalesData
from app.models.inventory import InventoryData
from app.models.product import Product
from app.core.security import decrypt_value

logger = logging.getLogger(__name__)


class DataExtractionService:
    """Service for extracting data from Amazon."""

    def __init__(self, db: AsyncSession):
        self.db = db

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

            # Sync different data types
            sales_count = await self.sync_sales_data(account)
            inventory_count = await self.sync_inventory_data(account)
            products_count = await self.sync_products(account)

            account.sync_status = SyncStatus.SUCCESS
            account.last_sync_at = datetime.utcnow()
            account.sync_error_message = None

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
            raise

    async def sync_sales_data(
        self,
        account: AmazonAccount,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> int:
        """Sync sales data for an account."""
        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        # In production, this would call Amazon SP-API
        # For now, generate sample data for demonstration
        import random
        from decimal import Decimal

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

                # Use merge to handle duplicates
                await self.db.merge(sales_record)
                count += 1

            current_date += timedelta(days=1)

        await self.db.flush()
        return count

    async def sync_inventory_data(self, account: AmazonAccount) -> int:
        """Sync inventory data for an account."""
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

    async def sync_products(self, account: AmazonAccount) -> int:
        """Sync product catalog for an account."""
        import random
        from decimal import Decimal

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

    async def sync_advertising_data(self, account: AmazonAccount) -> int:
        """Sync advertising data for an account."""
        from app.models.advertising import AdvertisingCampaign, AdvertisingMetrics
        import random
        from decimal import Decimal

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


class AmazonSPAPIClient:
    """Client for Amazon Selling Partner API."""

    def __init__(self, refresh_token: str, client_id: str, client_secret: str):
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None

    async def authenticate(self):
        """Authenticate with Amazon SP-API."""
        # In production, this would call Amazon's OAuth endpoint
        pass

    async def get_sales_report(self, start_date: date, end_date: date) -> List[Dict]:
        """Get sales report from SP-API."""
        # In production, this would call the Reports API
        return []

    async def get_inventory(self) -> List[Dict]:
        """Get FBA inventory from SP-API."""
        # In production, this would call the FBA Inventory API
        return []

    async def get_catalog_items(self, asins: List[str]) -> List[Dict]:
        """Get catalog item details from SP-API."""
        # In production, this would call the Catalog Items API
        return []
