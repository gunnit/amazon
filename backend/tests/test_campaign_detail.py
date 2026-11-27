"""Exercise the campaign drill-down queries against isolated daily performance rows."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import Column, MetaData, Table, Uuid, create_engine
from sqlalchemy.orm import Session

from app.models.advertising import (
    AdvertisingCampaign, AdvertisingKeywordMetrics, AdvertisingMetrics, AdvertisingMetricsByAsin,
)
from app.models.amazon_account import AccountType, AmazonAccount
from app.services.campaign_detail import load_campaign_detail
from app.services.data_extraction import DataExtractionService


@pytest.mark.asyncio
async def test_drilldown_respects_account_period_and_missing_order_counts():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("organizations", metadata, Column("id", Uuid, primary_key=True))
    for model in (AmazonAccount, AdvertisingCampaign, AdvertisingMetrics,
                  AdvertisingMetricsByAsin, AdvertisingKeywordMetrics):
        table = model.__table__.to_metadata(metadata)
        for column in table.c:
            if isinstance(column.type, Uuid):
                column.type = Uuid(native_uuid=False)
        if model in (AdvertisingMetrics, AdvertisingMetricsByAsin):
            # SQLite does not implement sequence-backed composite primary keys.
            table.c.id.autoincrement = False
    metadata.create_all(engine)
    org, other_org = uuid4(), uuid4()
    day_one, day_two = date(2026, 11, 1), date(2026, 11, 2)
    with Session(engine) as session:
        db = SimpleNamespace(execute=AsyncMock(side_effect=session.execute))
        accounts = [
            AmazonAccount(organization_id=org_id, account_name="Demo", account_type=AccountType.VENDOR,
                          marketplace_id=country, marketplace_country=country)
            for org_id, country in [(org, "IT"), (other_org, "DE")]
        ]
        session.add_all(accounts)
        session.flush()
        campaigns = [
            AdvertisingCampaign(account_id=account.id, campaign_id="123", campaign_type="sponsoredProducts")
            for account in accounts
        ]
        session.add_all(campaigns)
        session.flush()
        campaign_id = campaigns[0].id
        session.add_all([
            AdvertisingMetrics(id=1, campaign_id=campaign_id, date=day_one, clicks=10,
                               impressions=100, cost=20, attributed_sales_7d=80, attributed_orders=2),
            AdvertisingMetrics(id=2, campaign_id=campaign_id, date=day_two, clicks=5, cost=5),
            AdvertisingMetrics(id=3, campaign_id=campaigns[1].id, date=day_one, cost=999),
            AdvertisingMetricsByAsin(id=1, campaign_id=campaign_id, account_id=accounts[0].id,
                                     date=day_one, asin="A", clicks=2, cost=5, attributed_orders=1),
            AdvertisingKeywordMetrics(campaign_id=campaign_id, date=day_one, keyword="test",
                                      match_type="EXACT", clicks=1, impressions=10, cost=2,
                                      attributed_sales_7d=0, attributed_units_ordered_7d=0, attributed_orders=0),
        ])
        session.flush()
        scope = (db, org, accounts[0].id, "123")
        detail = await load_campaign_detail(*scope, day_one, day_two)
        assert detail.totals.spend == 25
        assert detail.totals.orders is None and detail.totals.conversion_rate is None
        assert detail.currency == "EUR"
        assert [day.date for day in detail.daily] == [day_one, day_two]
        assert detail.products[0].conversion_rate == 50
        assert detail.keywords[0].conversion_rate == 0 and detail.keywords[0].acos is None
        detail = await load_campaign_detail(*scope, day_one, day_one)
        assert detail.totals.orders == 2 and detail.totals.conversion_rate == 20
        empty = await load_campaign_detail(*scope, date(2026, 10, 1), date(2026, 10, 3))
        assert empty.totals is None and empty.daily == empty.products == empty.keywords == []
        assert await load_campaign_detail(db, other_org, accounts[0].id, "123", day_one, day_two) is None


@pytest.mark.asyncio
async def test_sp_breakdowns_combine_ad_groups_and_keep_orders_distinct_from_units():
    promotion = {"date": "2026-11-01", "campaignId": "123", "advertisedAsin": "A", "clicks": 3,
                 "sales7d": 24, "unitsSoldClicks7d": 4, "purchases7d": 2}
    rows = [dict(promotion, adGroupId="first"), dict(promotion, adGroupId="second")]
    client = SimpleNamespace(download_report=lambda **kwargs: rows)
    service = DataExtractionService(SimpleNamespace(execute=AsyncMock()))
    service._upsert_advertising_asin_metrics = AsyncMock()
    scope = (SimpleNamespace(id=uuid4()), {"123": uuid4()})
    assert await service._process_sp_breakdown_report(client, "p", "sp_advertised_product", "r", *scope) == 1
    stored = service._upsert_advertising_asin_metrics.await_args.args[0]
    assert stored["attributed_units_ordered_7d"] == 8 and stored["attributed_orders"] == 4
    rows[:] = [
        dict(promotion, keyword="drill", matchType="EXACT", adGroupId="first"),
        dict(promotion, keyword="drill", matchType="EXACT", adGroupId="second"),
        dict(promotion, keyword="asin=A", matchType="TARGETING_EXPRESSION"),
    ]
    assert await service._process_sp_breakdown_report(client, "p", "sp_keyword_targeting", "r", *scope) == 1
    params = service.db.execute.await_args.args[0].compile().params
    assert params["clicks_m0"] == 6 and params["attributed_orders_m0"] == 4
