"""Guards for the Amazon Advertising Reporting v3 request configs.

These lock the report column/groupBy sets to the names the live Reporting v3 API
accepts, so a future edit cannot silently reintroduce invalid columns (which make
``POST /reporting/reports`` return HTTP 400 and the whole sync persist zeros).
"""
import gzip
import json
import re
from datetime import date

import httpx
import pytest

from app.core.amazon.advertising_client import (
    ADS_REGION_BY_COUNTRY,
    DEFAULT_REPORT_CONFIGS,
    AdvertisingAPIClient,
)

# Known-valid Reporting v3 columns per reportTypeId (subset, from the official
# spec/Postman collection). Configs must request a subset of these.
VALID_COLUMNS = {
    "spCampaigns": {
        "date", "campaignName", "campaignId", "campaignStatus", "campaignBudgetAmount",
        "impressions", "clicks", "cost",
        "purchases1d", "purchases7d", "purchases14d", "purchases30d",
        "purchasesSameSku1d", "purchasesSameSku7d", "purchasesSameSku14d", "purchasesSameSku30d",
        "unitsSoldClicks1d", "unitsSoldClicks7d", "unitsSoldClicks14d", "unitsSoldClicks30d",
        "sales1d", "sales7d", "sales14d", "sales30d",
    },
    "spAdvertisedProduct": {
        "date", "campaignName", "campaignId", "adGroupName", "adGroupId", "adId",
        "impressions", "clicks", "cost", "campaignBudgetCurrencyCode", "advertisedAsin",
        "purchases1d", "purchases7d", "purchases14d", "purchases30d",
        "unitsSoldClicks1d", "unitsSoldClicks7d", "unitsSoldClicks14d", "unitsSoldClicks30d",
        "sales1d", "sales7d", "sales14d", "sales30d",
    },
    "sbCampaigns": {
        "date", "campaignBudgetCurrencyCode", "campaignId", "campaignName", "campaignStatus",
        "campaignBudgetAmount", "campaignBudgetType", "clicks", "cost", "impressions",
        "sales", "purchases", "unitsSold",
        "newToBrandPurchases", "newToBrandSales", "newToBrandUnitsSold",
    },
    "sdCampaigns": {
        "date", "campaignId", "campaignName", "campaignStatus", "campaignBudgetCurrencyCode",
        "campaignBudgetAmount", "clicks", "cost", "impressions", "impressionsViews",
        "sales", "salesClicks", "purchases", "purchasesClicks", "unitsSold", "unitsSoldClicks",
        "newToBrandPurchases", "newToBrandSales", "newToBrandUnitsSold",
    },
    "spSearchTerm": {
        "date", "campaignName", "campaignId", "adGroupName", "adGroupId",
        "keywordId", "keyword", "keywordType", "matchType", "searchTerm",
        "impressions", "clicks", "cost", "campaignBudgetCurrencyCode",
        "purchases1d", "purchases7d", "purchases14d", "purchases30d",
        "unitsSoldClicks1d", "unitsSoldClicks7d", "unitsSoldClicks14d", "unitsSoldClicks30d",
        "sales1d", "sales7d", "sales14d", "sales30d",
    },
    "spPurchasedProduct": {
        "date", "campaignName", "campaignId", "adGroupName", "adGroupId",
        "advertisedAsin", "advertisedSku", "purchasedAsin", "campaignBudgetCurrencyCode",
        "purchases1d", "purchases7d", "purchases14d", "purchases30d",
        "unitsSoldClicks1d", "unitsSoldClicks7d", "unitsSoldClicks14d", "unitsSoldClicks30d",
        "sales1d", "sales7d", "sales14d", "sales30d",
    },
}

VALID_GROUP_BY = {
    "spCampaigns": {"campaign", "adGroup"},
    "spAdvertisedProduct": {"advertiser"},
    "sbCampaigns": {"campaign"},
    "sdCampaigns": {"campaign"},
    "spSearchTerm": {"searchTerm"},
    "spPurchasedProduct": {"asin"},
}

VALID_AD_PRODUCTS = {"SPONSORED_PRODUCTS", "SPONSORED_BRANDS", "SPONSORED_DISPLAY"}


@pytest.mark.parametrize("key,config", sorted(DEFAULT_REPORT_CONFIGS.items()))
def test_report_configs_use_valid_v3_columns(key, config):
    assert config.ad_product in VALID_AD_PRODUCTS
    assert config.report_type_id in VALID_COLUMNS, f"{key}: unknown reportTypeId"

    valid = VALID_COLUMNS[config.report_type_id]
    unknown = [c for c in config.columns if c not in valid]
    assert not unknown, f"{key} requests non-v3 columns: {unknown}"

    assert set(config.group_by) <= VALID_GROUP_BY[config.report_type_id], (
        f"{key} groupBy {config.group_by} invalid for {config.report_type_id}"
    )

    # The historical defects: 'orders{N}d' / 'spend' / bare 'unitsSold7d'.
    for column in config.columns:
        assert not re.fullmatch(r"orders\d+d", column), f"{key}: '{column}' is not a v3 column"
        assert column != "spend", f"{key}: use 'cost', not 'spend'"
        assert column != "unitsSold7d", f"{key}: use 'unitsSoldClicks7d'"


def test_sp_campaign_configs_are_deduplicated():
    aliases = [DEFAULT_REPORT_CONFIGS[k] for k in ("sp_campaigns", "sponsored_products_campaigns", "spCampaigns")]
    assert all(a is aliases[0] for a in aliases), "SP campaign aliases must share one config"
    assert "unitsSoldClicks7d" in aliases[0].columns
    assert "sales7d" in aliases[0].columns


def test_sb_sd_campaign_metrics_are_unsuffixed():
    for key in ("sb_campaigns", "sd_campaigns"):
        cols = DEFAULT_REPORT_CONFIGS[key].columns
        assert "sales" in cols, f"{key} must request unsuffixed 'sales'"
        assert not any(re.search(r"\d+d$", c) for c in cols), f"{key} must not use day-window suffixes"


def test_advertised_product_uses_advertiser_grouping():
    config = DEFAULT_REPORT_CONFIGS["sp_advertised_product"]
    assert config.group_by == ["advertiser"]
    assert "advertisedAsin" in config.columns
    assert "unitsSoldClicks7d" in config.columns


def test_region_map_routes_india_and_uae_to_eu():
    assert ADS_REGION_BY_COUNTRY["IN"] == "EU"
    assert ADS_REGION_BY_COUNTRY["AE"] == "EU"
    assert ADS_REGION_BY_COUNTRY["JP"] == "FE"
    assert ADS_REGION_BY_COUNTRY["AU"] == "FE"
    assert ADS_REGION_BY_COUNTRY["SG"] == "FE"


def _mock_client(handler) -> AdvertisingAPIClient:
    # Pass an explicit base_url so the client never reads global settings (some
    # sibling test modules replace app.config.settings with a stub).
    client = AdvertisingAPIClient(
        client_id="amzn1.application-oa2-client.test",
        client_secret="secret",
        refresh_token="Atzr|test",
        marketplace_country="IT",
        base_url="https://advertising-api-eu.amazon.com",
    )
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def test_request_report_sends_v3_media_type_and_valid_body():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/o2/token"):
            return httpx.Response(200, json={"access_token": "Atza|x", "expires_in": 3600})
        if request.url.path == "/reporting/reports":
            captured["content_type"] = request.headers.get("Content-Type")
            captured["client_id"] = request.headers.get("Amazon-Advertising-API-ClientId")
            captured["scope"] = request.headers.get("Amazon-Advertising-API-Scope")
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"reportId": "rep-1", "status": "PENDING"})
        return httpx.Response(404)

    client = _mock_client(handler)
    try:
        report_id = client.request_report(
            profile_id="123456",
            report_type="sp_campaigns",
            date_range=(date(2026, 5, 1), date(2026, 5, 7)),
        )
    finally:
        client.close()

    assert report_id == "rep-1"
    assert captured["content_type"] == "application/vnd.createasyncreportrequest.v3+json"
    assert captured["client_id"] == "amzn1.application-oa2-client.test"
    assert captured["scope"] == "123456"

    config = captured["body"]["configuration"]
    assert config["adProduct"] == "SPONSORED_PRODUCTS"
    assert config["reportTypeId"] == "spCampaigns"
    assert config["format"] == "GZIP_JSON"
    assert config["timeUnit"] == "DAILY"
    assert config["groupBy"] == ["campaign"]
    assert captured["body"]["startDate"] == "2026-05-01"
    assert captured["body"]["endDate"] == "2026-05-07"
    # No invalid columns leak into the wire request.
    assert not any(re.fullmatch(r"orders\d+d", c) for c in config["columns"])


def test_download_report_decodes_gzip_json_from_presigned_url(monkeypatch):
    import app.core.amazon.advertising_client as ac

    monkeypatch.setattr(ac.settings, "AMAZON_ADS_REPORT_POLL_INTERVAL_SECONDS", 0, raising=False)
    monkeypatch.setattr(ac.settings, "AMAZON_ADS_REPORT_POLL_MAX_ATTEMPTS", 3, raising=False)

    rows = [{"date": "2026-05-01", "campaignId": "c1", "impressions": 10}]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/o2/token"):
            return httpx.Response(200, json={"access_token": "Atza|x", "expires_in": 3600})
        if request.url.path == "/reporting/reports/rep-1":
            return httpx.Response(200, json={"status": "COMPLETED", "url": "https://files.test/r.json.gz"})
        if request.url.host == "files.test":
            # The presigned S3 URL serves raw gzip bytes with no Content-Encoding
            # header (so httpx does not transparently inflate them).
            payload = gzip.compress(json.dumps(rows).encode("utf-8"))
            return httpx.Response(200, content=payload, headers={"Content-Type": "application/octet-stream"})
        return httpx.Response(404)

    client = _mock_client(handler)
    try:
        result = client.download_report(profile_id="123456", report_id="rep-1")
    finally:
        client.close()

    assert result == rows
