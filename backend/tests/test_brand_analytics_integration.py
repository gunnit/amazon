"""Tests for the Brand Analytics fetch + metric wiring (P0-7 / P1-11)."""
import asyncio
import json
from datetime import date
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.amazon.sp_api_client import SPAPIClient  # noqa: E402
from app.services.brand_analysis_capabilities import (  # noqa: E402
    INTEGRATED_CAPABILITIES,
    CapabilityProbeResult,
)
from app.services.brand_analysis_service import (  # noqa: E402
    ParsedBrandExport,
    calculate_brand_metrics,
)
from app.services.brand_analysis_sources import AmazonAccountDataSource  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------
# Parser + report-poller reuse
# --------------------------------------------------------------------------

def test_search_terms_parser_normalizes_asins_and_aggregates_shares():
    payload = {
        "dataByDepartmentAndSearchTerm": [
            {
                "departmentName": "Kitchen",
                "searchTerm": "cast iron skillet",
                "searchFrequencyRank": "12",
                "clickedAsin1": "b001",
                "clickShare1": "0.18",
                "conversionShare1": "0.22",
            },
            {
                "searchTerm": "dutch oven",
                "searchFrequencyRank": "40",
                "clickedAsin1": "B999",
                "clickShare1": "0.30",
                "conversionShare1": "0.40",
            },
            {"searchTerm": ""},  # dropped: no term
        ]
    }
    out = SPAPIClient._parse_brand_analytics_search_terms(payload)
    assert out["source"] == "brand_analytics_search_terms"
    assert out["term_count"] == 2
    assert out["terms"][0]["top_clicked_asins"][0]["asin"] == "B001"  # upper-cased
    assert out["aggregate_click_share"] == pytest.approx((0.18 + 0.30) / 2, rel=1e-3)
    assert out["aggregate_conversion_share"] == pytest.approx((0.22 + 0.40) / 2, rel=1e-3)


def test_market_basket_parser_collects_copurchased_asins():
    payload = {
        "dataByAsin": [
            {
                "asin": "B100",
                "purchasedWithAsin1": "b200",
                "purchasedWithRate1": "0.15",
            }
        ]
    }
    out = SPAPIClient._parse_brand_analytics_market_basket(payload)
    assert out["basket_count"] == 1
    basket = out["baskets"][0]
    assert basket["asin"] == "B100"
    assert basket["purchased_with"][0]["asin"] == "B200"


def test_get_brand_analytics_search_terms_streams_document():
    client = SPAPIClient.__new__(SPAPIClient)
    captured = {}

    def fake_meta(report_type, start_date, end_date, report_options=None):
        captured["report_type"] = report_type
        captured["report_options"] = report_options
        return {"url": "https://example.test/doc", "compressionAlgorithm": None}

    def fake_stream(document_meta, fh):
        payload = json.dumps(
            {
                "dataByDepartmentAndSearchTerm": [
                    {"searchTerm": "widget", "clickedAsin1": "B1", "clickShare1": "0.5"}
                ]
            }
        ).encode()
        fh.write(payload)
        return len(payload)

    client._request_report_document_meta = fake_meta  # type: ignore[assignment]
    client._stream_report_document_to_file = fake_stream  # type: ignore[assignment]
    out = client.get_brand_analytics_search_terms(
        date(2026, 6, 1), date(2026, 6, 7), report_period="WEEK"
    )
    assert captured["report_type"] == "GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT"
    assert captured["report_options"] == {"reportPeriod": "WEEK"}
    assert out["term_count"] == 1


def test_search_terms_stream_parser_filters_and_caps():
    import io

    records = [
        {"searchTerm": f"term {i}", "clickedAsin1": f"B{i:03d}", "clickShare1": "0.10"}
        for i in range(50)
    ]
    fh = io.BytesIO(json.dumps({"dataByDepartmentAndSearchTerm": records}).encode())

    out = SPAPIClient._parse_brand_analytics_search_terms_stream(
        fh, keep_asins={"b001", "B005"}, max_terms=1
    )
    assert out["terms_scanned"] == 50
    # Only the two matching terms survive the filter; max_terms caps the list.
    assert out["term_count"] == 1
    assert out["terms"][0]["top_clicked_asins"][0]["asin"] == "B001"
    # Aggregates cover all KEPT terms (2), not just the capped list.
    assert out["aggregate_click_share"] == pytest.approx(0.10, rel=1e-3)


# --------------------------------------------------------------------------
# Sources adapter gating
# --------------------------------------------------------------------------

def _adapter(brand_analytics_available: bool) -> AmazonAccountDataSource:
    return AmazonAccountDataSource(
        db=SimpleNamespace(),
        account_id=uuid4(),
        organization_id=uuid4(),
        brand_analytics_available=brand_analytics_available,
    )


def test_brand_analytics_not_fetched_when_capability_absent():
    adapter = _adapter(brand_analytics_available=False)

    async def _fail_client():
        raise AssertionError("must not build a client when capability is absent")

    adapter._build_sp_api_client = _fail_client  # type: ignore[assignment]
    assert _run(adapter._fetch_brand_analytics()) is None


def test_brand_analytics_fetched_once_when_capability_present():
    adapter = _adapter(brand_analytics_available=True)
    calls = {"count": 0}

    class _Client:
        def get_brand_analytics_search_terms(self, start, end, report_period="WEEK", **kwargs):
            calls["count"] += 1
            return {
                "source": "brand_analytics_search_terms",
                "term_count": 1,
                "terms": [{"search_term": "widget", "top_clicked_asins": []}],
                "aggregate_click_share": 0.4,
                "aggregate_conversion_share": 0.25,
            }

    async def _client():
        return _Client()

    adapter._build_sp_api_client = _client  # type: ignore[assignment]
    first = _run(adapter._fetch_brand_analytics())
    second = _run(adapter._fetch_brand_analytics())
    assert first is second  # cached, fetched once
    assert calls["count"] == 1
    assert first["period"]["report_period"] == "WEEK"


def test_brand_analytics_failure_degrades_to_none():
    adapter = _adapter(brand_analytics_available=True)

    class _Client:
        def get_brand_analytics_search_terms(self, *args, **kwargs):
            raise RuntimeError("403 Forbidden: Brand Analytics role missing")

    async def _client():
        return _Client()

    adapter._build_sp_api_client = _client  # type: ignore[assignment]
    assert _run(adapter._fetch_brand_analytics()) is None
    assert "Brand Analytics role missing" in (adapter.brand_analytics_error or "")


# --------------------------------------------------------------------------
# Metric population
# --------------------------------------------------------------------------

def _export(year: int, brand_analytics=None) -> ParsedBrandExport:
    df = pd.DataFrame(
        [
            {
                "asin": "B001",
                "product_name": "Acme Skillet",
                "brand": "Acme",
                "subcategory": "Skillets",
                "revenue": 1000.0,
                "units": 50.0,
            }
        ]
    )
    return ParsedBrandExport(
        rows=df,
        columns=list(df.columns),
        row_count=len(df),
        source_name="internal",
        year=year,
        brand_analytics=brand_analytics,
    )


def test_search_shares_remain_none_without_brand_analytics():
    metrics = calculate_brand_metrics(_export(2024), _export(2025), brand_name="Acme")
    market = metrics["market_analysis"]
    assert market["search_purchase_share"] is None
    assert market["search_click_share"] is None
    assert market["search_cart_add_share"] is None
    assert market["search_share_source"] is None
    assert market["search_share_limitation"]


def test_search_shares_populated_from_brand_analytics_signal():
    signal = {
        "source": "brand_analytics_search_terms",
        "term_count": 2,
        "aggregate_click_share": 0.31,
        "aggregate_conversion_share": 0.24,
        "period": {"report_period": "WEEK", "start_date": "2026-06-01", "end_date": "2026-06-07"},
        "terms": [
            {"search_term": "skillet", "search_frequency_rank": 3, "top_clicked_asins": [{"asin": "B900"}]},
        ],
    }
    metrics = calculate_brand_metrics(
        _export(2024), _export(2025, brand_analytics=signal), brand_name="Acme"
    )
    market = metrics["market_analysis"]
    assert market["search_click_share"] == 0.31
    assert market["search_purchase_share"] == 0.24
    # Cart-add share is not in the search-terms report → stays N/A (no fabrication).
    assert market["search_cart_add_share"] is None
    assert market["search_share_source"] == "brand_analytics_search_terms"
    assert market["search_share_limitation"] is None
    assert market["search_term_competitors"][0]["search_term"] == "skillet"


def test_brand_analytics_search_share_never_proxies_revenue_market_share():
    signal = {
        "term_count": 1,
        "aggregate_click_share": 0.5,
        "aggregate_conversion_share": 0.5,
        "terms": [{"search_term": "x"}],
    }
    metrics = calculate_brand_metrics(
        _export(2024), _export(2025, brand_analytics=signal), brand_name="Acme"
    )
    market = metrics["market_analysis"]
    # Search share present but revenue market share stays unavailable.
    assert market["search_click_share"] == 0.5
    assert market["status"] == "not_available"
    assert market["market_share_2025"] is None


# --------------------------------------------------------------------------
# Capability detected-vs-integrated honesty (backward-compatible)
# --------------------------------------------------------------------------

def test_capability_to_dict_is_backward_compatible_and_adds_integration_status():
    result = CapabilityProbeResult(
        organization_id="org",
        account_id="acc",
        marketplace_id="APJ6JRA9NG5V4",
        checked_at=__import__("datetime").datetime(2026, 6, 9),
    )
    result.capabilities["brand_analytics_available"] = True
    result.capabilities["data_kiosk_available"] = True  # detected but not integrated

    out = result.to_dict()

    # Existing flat booleans preserved (the shape the frontend already reads).
    assert out["brand_analytics_available"] is True
    assert out["data_kiosk_available"] is True

    # New additive fields.
    assert out["capability_status"]["brand_analytics_available"] == {
        "detected": True,
        "integrated": True,
    }
    # Detected but not consumed → integrated False.
    assert out["capability_status"]["data_kiosk_available"] == {
        "detected": True,
        "integrated": False,
    }
    assert out["integrated_capabilities"]["brand_analytics_available"] is True
    assert out["integrated_capabilities"]["data_kiosk_available"] is False
    assert "brand_analytics_available" in INTEGRATED_CAPABILITIES
    assert "data_kiosk_available" not in INTEGRATED_CAPABILITIES
