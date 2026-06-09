"""Invariant tests for the __DAILY_TOTAL__ sentinel double-count gotcha.

``__DAILY_TOTAL__`` (DAILY_TOTAL_ASIN) is a synthetic ASIN written into
``sales_data`` by the extraction layer for every account/date.  It carries
the accurate salesAndTrafficByDate daily totals used for dashboard KPIs.
Real per-ASIN rows carry the salesAndTrafficByASIN breakdown.

Double-count risk: any aggregation that sums all ``sales_data`` rows without
the ``asin != '__DAILY_TOTAL__'`` filter counts each day's revenue twice —
once via the sentinel and once (or more, for multi-day seller snapshots) via
the per-ASIN rows.

Scope of these tests:

1. BrandPulseService._top_asins / ._declining_asins — pure functions that
   receive an already-resolved {asin: revenue} map from asin_sales_breakdown.
   The DB query in _sum_asin_sales correctly excludes the sentinel at SQL level
   (analytics_service.py:643,666), so the map should never contain it.  These
   tests document what WOULD happen if that filter were ever dropped, and assert
   the invariants that must hold once the upstream filter is in place.

   Known gap (P0-5): _top_asins and _declining_asins have no in-function guard
   against the sentinel reaching them.  Tests asserting guard behaviour are
   marked xfail(strict=True) — they will be promoted to passing once the
   pure-function sentinel filter is added.

2. Brand Analysis parse_brand_export + calculate_brand_metrics — the manual
   upload path parses raw CSV rows and does not strip the sentinel.  If a
   user's CSV accidentally carries it, it inflates totals and leaks into
   top_5_asins.  Tests asserting correct filtering are marked xfail(strict=True)
   until parse_brand_export adds an explicit sentinel-strip guard.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.brand_pulse_service import (  # noqa: E402
    BrandPulseService,
    DECLINE_THRESHOLD_PCT,
    DECLINE_FAST_THRESHOLD_PCT,
)
from app.services.brand_analysis_service import (  # noqa: E402
    calculate_brand_metrics,
    parse_brand_export,
)

SENTINEL = "__DAILY_TOTAL__"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv_bytes(rows: list[dict]) -> bytes:
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")


def _pulse() -> BrandPulseService:
    return BrandPulseService.__new__(BrandPulseService)


def _titles(asins: list[str]) -> dict[str, str | None]:
    return {asin: f"Title {asin}" for asin in asins}


# ---------------------------------------------------------------------------
# Brand Pulse — _top_asins invariants
# ---------------------------------------------------------------------------

def test_top_asins_excludes_sentinel_when_present_in_map():
    current_map = {SENTINEL: 9999.0, "B001": 500.0, "B002": 300.0}
    previous_map = {"B001": 400.0, "B002": 200.0}
    titles = _titles(list(current_map))

    result = _pulse()._top_asins(current_map, previous_map, titles, limit=10)

    returned_asins = [row["asin"] for row in result]
    assert SENTINEL not in returned_asins


def test_top_asins_sum_does_not_exceed_overview_revenue():
    # overview revenue = 800 comes from the sentinel row alone in analytics_service;
    # B001+B002 per-ASIN rows sum to 800 too. Without sentinel in the map,
    # per_asin_total == 800 == overview_revenue. With sentinel: 800+500+300 = 1600.
    overview_revenue = 800.0
    current_map = {SENTINEL: overview_revenue, "B001": 500.0, "B002": 300.0}
    previous_map = {}
    titles = _titles(list(current_map))

    result = _pulse()._top_asins(current_map, previous_map, titles, limit=10)

    per_asin_total = sum(row["revenue"] for row in result)
    assert per_asin_total <= overview_revenue


def test_top_asins_without_sentinel_is_correct():
    current_map = {"B001": 700.0, "B002": 300.0}
    previous_map = {"B001": 600.0}
    titles = _titles(list(current_map))

    result = _pulse()._top_asins(current_map, previous_map, titles, limit=5)

    assert len(result) == 2
    assert result[0]["asin"] == "B001"
    assert result[0]["revenue"] == 700.0
    assert result[0]["previous_revenue"] == 600.0
    assert result[1]["asin"] == "B002"
    assert result[1]["previous_revenue"] == 0.0


def test_top_asins_real_asins_present_even_when_sentinel_in_map():
    # Even today (before the guard fix), real ASINs are still returned.
    current_map = {SENTINEL: 9999.0, "B001": 500.0, "B002": 300.0}
    previous_map = {}
    titles = _titles(list(current_map))

    result = _pulse()._top_asins(current_map, previous_map, titles, limit=10)

    returned_asins = [row["asin"] for row in result]
    assert "B001" in returned_asins
    assert "B002" in returned_asins


# ---------------------------------------------------------------------------
# Brand Pulse — _declining_asins invariants
# ---------------------------------------------------------------------------

def test_declining_asins_excludes_sentinel_when_present_in_map():
    previous_map = {SENTINEL: 5000.0, "B001": 800.0, "B002": 400.0}
    current_map = {SENTINEL: 0.0, "B001": 200.0}
    titles = _titles(list(previous_map))

    result = _pulse()._declining_asins(current_map, previous_map, titles, limit=10)

    returned_asins = [row["asin"] for row in result]
    assert SENTINEL not in returned_asins


def test_declining_asins_sentinel_only_in_both_maps_returns_empty():
    previous_map = {SENTINEL: 1000.0}
    current_map = {SENTINEL: 500.0}

    result = _pulse()._declining_asins(current_map, previous_map, {}, limit=10)

    assert result == []


def test_declining_asins_real_decline_detected():
    previous_map = {"B001": 1000.0, "B002": 500.0}
    current_map = {"B001": 600.0}  # B001: -40%, B002: absent → 0 (decline)

    result = _pulse()._declining_asins(current_map, previous_map, _titles(["B001", "B002"]), limit=10)

    returned_asins = [row["asin"] for row in result]
    assert "B001" in returned_asins
    assert "B002" in returned_asins
    assert all(row["change_percent"] <= DECLINE_THRESHOLD_PCT for row in result)


def test_declining_asins_fast_flag():
    previous_map = {"B001": 1000.0}
    current_map = {"B001": 50.0}  # -95%

    result = _pulse()._declining_asins(current_map, previous_map, _titles(["B001"]), limit=10)

    assert len(result) == 1
    assert result[0]["trend_class"] == "declining_fast"
    assert result[0]["change_percent"] < DECLINE_FAST_THRESHOLD_PCT


def test_declining_asins_stable_asin_not_returned():
    previous_map = {"B001": 1000.0}
    current_map = {"B001": 1000.0}  # 0% change — not declining

    result = _pulse()._declining_asins(current_map, previous_map, _titles(["B001"]), limit=10)

    assert result == []


# ---------------------------------------------------------------------------
# Brand Analysis — sentinel in parse_brand_export / calculate_brand_metrics
# ---------------------------------------------------------------------------

def _export_rows_with_sentinel() -> list[dict]:
    return [
        {"ASIN": "B001", "Product Name": "Chef Knife", "Total Revenue": "1000", "Units Sold": "10"},
        {"ASIN": SENTINEL, "Product Name": "Daily Total", "Total Revenue": "99999", "Units Sold": "999"},
        {"ASIN": "B002", "Product Name": "Pan Set", "Total Revenue": "500", "Units Sold": "5"},
    ]


def test_parse_brand_export_sentinel_present_means_real_asins_still_parsed():
    """parse_brand_export today does not strip the sentinel — document that
    real product rows are still parsed alongside it."""
    parsed = parse_brand_export(_csv_bytes(_export_rows_with_sentinel()), "export.csv", year=2025)

    real_asins = [asin for asin in parsed.rows["asin"] if asin != SENTINEL]
    assert len(real_asins) >= 2


def test_calculate_brand_metrics_sentinel_absent_from_top5():
    rows_clean = [
        {"ASIN": "B001", "Product Name": "Chef Knife", "Total Revenue": "1000", "Units Sold": "10"},
    ]
    parsed_current = parse_brand_export(_csv_bytes(_export_rows_with_sentinel()), "2025.csv", year=2025)
    parsed_prev = parse_brand_export(_csv_bytes(rows_clean), "2024.csv", year=2024)

    metrics = calculate_brand_metrics(parsed_prev, parsed_current, brand_name="Acme")

    top_asins = [item["asin"] for item in metrics.get("top_5_asins", [])]
    assert SENTINEL not in top_asins


def test_calculate_brand_metrics_sentinel_revenue_does_not_inflate_total():
    rows_clean = [{"ASIN": "B001", "Total Revenue": "1000"}]
    parsed_current = parse_brand_export(_csv_bytes(_export_rows_with_sentinel()), "2025.csv", year=2025)
    parsed_prev = parse_brand_export(_csv_bytes(rows_clean), "2024.csv", year=2024)

    metrics = calculate_brand_metrics(parsed_prev, parsed_current, brand_name="Acme")

    # Real rows: B001=1000, B002=500 → 1500 total. Sentinel: 99999.
    assert metrics["total_revenue_2025"] < 99999.0


def test_calculate_brand_metrics_clean_export_correct_total():
    """Baseline: no sentinel in CSV → metrics are correct."""
    rows_2025 = [
        {"ASIN": "B001", "Product Name": "Chef Knife", "Total Revenue": "1000", "Units Sold": "10"},
        {"ASIN": "B002", "Product Name": "Pan Set", "Total Revenue": "500", "Units Sold": "5"},
    ]
    rows_2024 = [
        {"ASIN": "B001", "Total Revenue": "800"},
    ]
    parsed_current = parse_brand_export(_csv_bytes(rows_2025), "2025.csv", year=2025)
    parsed_prev = parse_brand_export(_csv_bytes(rows_2024), "2024.csv", year=2024)

    metrics = calculate_brand_metrics(parsed_prev, parsed_current, brand_name="Acme")

    assert metrics["total_revenue_2025"] == 1500.0
    top_asins = [item["asin"] for item in metrics.get("top_5_asins", [])]
    assert SENTINEL not in top_asins
    assert "B001" in top_asins
