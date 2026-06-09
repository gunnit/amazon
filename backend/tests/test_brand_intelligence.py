"""Brand Intelligence pipeline + contract tests (DB-free).

Exercises aggregate -> diff -> generate(fallback) with a fake AnalyticsService,
and validates that the serialized report matches the API contract schemas.
"""
import asyncio
from datetime import date
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.schemas.brand_intelligence import ReportDetail, ReportSummary  # noqa: E402
from app.services.brand_intelligence_service import (  # noqa: E402
    SECTION_KEYS,
    aggregate_snapshot,
    build_exec_summary,
    build_fallback_sections,
    compute_next_weekly_run,
    diff_snapshot,
    generate_intelligence,
    report_to_detail,
    report_to_summary,
    resolve_week_period,
    week_label_for,
)


def _run(coro):
    return asyncio.run(coro)


class FakeAnalytics:
    """Stand-in for AnalyticsService returning canned, deterministic numbers."""

    def __init__(self, current_map, previous_map, ads, titles):
        self._current = current_map
        self._previous = previous_map
        self._ads = ads
        self._titles = titles

    async def compute_dashboard_kpis(self, account_ids, start, end):
        return {
            "current": {
                "revenue": 1200.0,
                "units": 60,
                "orders": 50,
                "average_order_value": 24.0,
                "active_asins": 3,
            },
            "previous": {
                "revenue": 1000.0,
                "units": 55,
                "orders": 48,
                "average_order_value": 20.83,
                "active_asins": 2,
            },
            "changes": {
                "revenue": {"absolute": 200.0, "percent": 20.0, "trend": "up"},
                "units": {"absolute": 5, "percent": 9.09, "trend": "up"},
                "orders": {"absolute": 2, "percent": 4.17, "trend": "stable"},
                "average_order_value": {"absolute": 3.17, "percent": 15.2, "trend": "up"},
            },
        }

    async def _asin_titles(self, account_ids, asins):
        return {a: self._titles.get(a) for a in asins}


class RoutingAnalytics(FakeAnalytics):
    """asin_sales_breakdown returns current vs previous based on the start date."""

    def __init__(self, cur_start, prev_start, current_map, previous_map, ads, titles):
        super().__init__(current_map, previous_map, ads, titles)
        self._cur_start = cur_start
        self._prev_start = prev_start

    async def asin_sales_breakdown(self, account_ids, start, end):
        if start == self._cur_start:
            return dict(self._current)
        return dict(self._previous)

    async def compute_advertising_metrics(self, account_ids, start, end):
        return self._ads


def _build_diff():
    from datetime import timedelta

    cur_start, cur_end = resolve_week_period(date(2026, 6, 8))  # last full week
    previous_end = cur_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)

    current_map = {"B001": 800.0, "B002": 300.0, "B003": 100.0}  # B003 is new
    previous_map = {"B001": 500.0, "B002": 450.0, "B004": 200.0}  # B004 dropped, B002 declined
    titles = {"B001": "Chef Knife", "B002": "Pan Set", "B003": "Whisk", "B004": "Ladle"}
    ads = {"impressions": 10000, "clicks": 200, "cost": 150.0, "sales": 1000.0, "acos": 15.0, "roas": 6.67}

    analytics = RoutingAnalytics(cur_start, previous_start, current_map, previous_map, ads, titles)
    snapshot = _run(
        aggregate_snapshot(
            analytics,
            [uuid4()],
            period_start=cur_start,
            period_end=cur_end,
            previous_start=previous_start,
            previous_end=previous_end,
        )
    )
    return snapshot, diff_snapshot(snapshot)


def test_aggregate_snapshot_shape():
    snapshot, _ = _build_diff()
    assert snapshot["overview"]["current"]["revenue"] == 1200.0
    assert snapshot["asin_sales"]["B001"] == 800.0
    assert snapshot["previous_asin_sales"]["B004"] == 200.0
    assert snapshot["ads"]["is_available"] is True


def test_diff_detects_movers_new_and_dropped():
    _, diff = _build_diff()
    # KPI deltas come straight from the changes block.
    assert diff["kpis"]["revenue"]["delta_percent"] == 20.0
    # B001 grew, B002 declined, B003 new, B004 dropped.
    gainer_asins = {r["asin"] for r in diff["gainers"]}
    decliner_asins = {r["asin"] for r in diff["decliners"]}
    new_asins = {r["asin"] for r in diff["new_asins"]}
    dropped_asins = {r["asin"] for r in diff["dropped_asins"]}
    assert "B001" in gainer_asins
    assert "B002" in decliner_asins  # -33% < -5% decline threshold
    assert "B003" in new_asins
    assert "B004" in dropped_asins


def test_fallback_generate_produces_all_sections_with_provenance():
    _, diff = _build_diff()
    intelligence, model = generate_intelligence("ZWILLING", diff, api_key=None)
    assert model == "deterministic-fallback"

    sections = intelligence["sections"]
    assert [s["key"] for s in sections] == SECTION_KEYS  # exact taxonomy + order

    # Every item carries Source / Confidence / Evidence — the guardrail contract.
    for section in sections:
        for item in section["items"]:
            assert item["source"]
            assert item["confidence"] in {"high", "medium", "low"}
            assert item["evidence"]

    # exec_summary headline + KPI cards present.
    exec_summary = intelligence["exec_summary"]
    assert exec_summary["headline"]
    assert {c["label"] for c in exec_summary["kpis"]} == {"Revenue", "Units", "Orders", "AOV"}

    # The decliner B002 surfaces as a risk; the gainer B001 as an opportunity/trend.
    risks = next(s for s in sections if s["key"] == "risks")
    assert any("B002" in i["title"] or "B002" in i["evidence"] for i in risks["items"])


def test_report_detail_matches_contract_schema():
    snapshot, diff = _build_diff()
    intelligence, model = generate_intelligence("ZWILLING", diff, api_key=None)
    cur_start, cur_end = resolve_week_period(date(2026, 6, 8))
    from datetime import datetime, timedelta

    previous_end = cur_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)

    report = SimpleNamespace(
        id=uuid4(),
        account_id=uuid4(),
        brand_label="ZWILLING",
        period_start=cur_start,
        period_end=cur_end,
        previous_start=previous_start,
        previous_end=previous_end,
        window_days=7,
        week_label=week_label_for(cur_start, cur_end),
        status="completed",
        generated_at=datetime.utcnow(),
        model=model,
        coverage_note=intelligence.get("coverage_note"),
        snapshot=snapshot,
        diff=diff,
        intelligence=intelligence,
    )

    detail = report_to_detail(report)
    # Pydantic validation enforces the full contract shape.
    parsed = ReportDetail.model_validate(detail)
    assert parsed.brand_label == "ZWILLING"
    assert parsed.period.week_label == report.week_label
    assert [s.key for s in parsed.sections] == SECTION_KEYS
    assert parsed.exec_summary.headline

    summary = ReportSummary.model_validate(report_to_summary(report))
    assert summary.status == "completed"
    assert summary.week_label == report.week_label


def test_coverage_note_set_when_ads_missing():
    snapshot, diff = _build_diff()
    diff["ads"]["is_available"] = False
    intelligence, _ = generate_intelligence("ZWILLING", diff, api_key=None)
    assert intelligence["coverage_note"]
    # And a "connect advertising" recommendation is surfaced.
    recs = next(s for s in intelligence["sections"] if s["key"] == "strategic_recommendations")
    assert any("Connect advertising data" == i["title"] for i in recs["items"])


def test_resolve_week_period_is_full_week_before_reference():
    start, end = resolve_week_period(date(2026, 6, 9))
    assert end == date(2026, 6, 8)
    assert (end - start).days == 6


def test_compute_next_weekly_run_is_in_future_and_correct_weekday():
    run_at = compute_next_weekly_run(0, "UTC")  # Monday
    assert run_at.weekday() == 0
    from datetime import datetime, timezone

    assert run_at > datetime.now(timezone.utc)


def test_exec_summary_headline_reports_direction():
    _, diff = _build_diff()
    summary = build_exec_summary("ZWILLING", diff)
    assert "up" in summary["headline"]  # revenue grew 20%
    assert "ZWILLING" in summary["headline"]


def test_fallback_competitor_section_degrades_gracefully():
    _, diff = _build_diff()
    sections = build_fallback_sections("ZWILLING", diff)
    competitor = next(s for s in sections if s["key"] == "competitor_activity")
    # No competitor data wired -> narrative explains, items empty (omit-not-fabricate).
    assert competitor["items"] == []
    assert "competitor" in competitor["narrative"].lower()
