"""Read daily campaign totals and advertising report breakdowns for a single marketplace."""
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.advertising import (
    AdvertisingCampaign, AdvertisingKeywordMetrics, AdvertisingMetrics, AdvertisingMetricsByAsin,
)
from app.models.amazon_account import AmazonAccount
from app.schemas.analytics import CampaignDay, CampaignDetail, CampaignKeyword, CampaignMetrics, CampaignProduct
from app.services.catalog_service import _marketplace_currency


def _ratio(numerator, denominator, multiplier=1):
    if numerator is None or not denominator:
        return None
    return (Decimal(numerator) * multiplier / Decimal(denominator)).quantize(Decimal("0.0001"))


def _metrics(*, impressions: int, clicks: int, spend: Decimal, sales: Decimal, units: int,
             orders: int | None) -> CampaignMetrics:
    return CampaignMetrics(
        impressions=impressions, clicks=clicks, spend=spend, sales=sales, units=units, orders=orders,
        ctr=_ratio(clicks, impressions, 100), cpc=_ratio(spend, clicks),
        acos=_ratio(spend, sales, 100), roas=_ratio(sales, spend),
        conversion_rate=_ratio(orders, clicks, 100),
    )


def _aggregate_query(model, campaign_id: UUID, start_date: date, end_date: date, *dimensions):
    return select(
        *dimensions,
        func.sum(model.impressions).label("impressions"),
        func.sum(model.clicks).label("clicks"),
        func.sum(model.cost).label("spend"),
        func.sum(model.attributed_sales_7d).label("sales"),
        func.sum(model.attributed_units_ordered_7d).label("units"),
        # COUNT(column) ignores NULL. A partial tally from a mix of historical
        # and refreshed reports would understate orders and conversion rate.
        case((func.count(model.attributed_orders) == func.count(), func.sum(model.attributed_orders))).label("orders"),
    ).where(
        model.campaign_id == campaign_id, model.date.between(start_date, end_date),
    ).group_by(*dimensions)


async def load_campaign_detail(
    db: AsyncSession, organization_id: UUID, account_id: UUID, campaign_id: str,
    start_date: date, end_date: date,
) -> CampaignDetail | None:
    campaign_row = (await db.execute(
        select(AdvertisingCampaign, AmazonAccount.marketplace_country)
        .join(AmazonAccount, AmazonAccount.id == AdvertisingCampaign.account_id)
        .where(
            AmazonAccount.organization_id == organization_id,
            AmazonAccount.id == account_id,
            AdvertisingCampaign.campaign_id == campaign_id,
        )
    )).one_or_none()
    if campaign_row is None:
        return None
    campaign, country = campaign_row
    scope = (campaign.id, start_date, end_date)
    daily_query = _aggregate_query(AdvertisingMetrics, *scope, AdvertisingMetrics.date).order_by(AdvertisingMetrics.date)
    daily = []
    for row in (await db.execute(daily_query)).mappings():
        values = dict(row)
        day = values.pop("date")
        daily.append(CampaignDay(date=day, **_metrics(**values).model_dump()))

    totals = None
    if daily:
        totals = _metrics(
            impressions=sum(day.impressions for day in daily), clicks=sum(day.clicks for day in daily),
            spend=sum(day.spend for day in daily), sales=sum(day.sales for day in daily),
            units=sum(day.units for day in daily),
            orders=sum(day.orders for day in daily) if all(day.orders is not None for day in daily) else None,
        )

    product_query = _aggregate_query(
        AdvertisingMetricsByAsin, *scope, AdvertisingMetricsByAsin.asin,
    ).where(AdvertisingMetricsByAsin.account_id == account_id).order_by(
        func.sum(AdvertisingMetricsByAsin.cost).desc(), AdvertisingMetricsByAsin.asin,
    )
    products = []
    for row in (await db.execute(product_query)).mappings():
        values = dict(row)
        asin = values.pop("asin")
        products.append(CampaignProduct(asin=asin, **_metrics(**values).model_dump()))

    keyword_model = AdvertisingKeywordMetrics
    keyword_query = _aggregate_query(
        keyword_model, *scope, keyword_model.keyword, keyword_model.match_type,
    ).order_by(func.sum(keyword_model.cost).desc(), keyword_model.keyword, keyword_model.match_type)
    keywords = []
    for row in (await db.execute(keyword_query)).mappings():
        values = dict(row)
        keyword = values.pop("keyword")
        match_type = values.pop("match_type")
        keywords.append(CampaignKeyword(keyword=keyword, match_type=match_type, **_metrics(**values).model_dump()))

    return CampaignDetail(
        account_id=account_id, campaign_id=campaign_id, campaign_name=campaign.campaign_name,
        campaign_type=campaign.campaign_type, state=campaign.state, marketplace_country=country,
        currency=_marketplace_currency(country), start_date=start_date, end_date=end_date,
        totals=totals, daily=daily, products=products, keywords=keywords,
    )
