"""Quarterly business review (R5): data, insights and deck."""
import io
import json
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from pptx import Presentation

from app.services.quarterly_report import data as qdata
from app.services.quarterly_report import insights as qinsights
from app.services.quarterly_report.data import (
    Metric,
    QuarterData,
    QuarterScope,
    collect_quarter_data,
    previous_quarter,
    quarter_bounds,
)
from app.services.quarterly_report.deck import build_quarterly_deck
from app.services.quarterly_report.insights import Insight, build_insights, rule_insights

ORG = uuid.UUID(int=1)
ACC = uuid.UUID(int=2)
Q3_2026 = date(2026, 7, 1)
Q2_2026 = date(2026, 4, 1)
Q3_2025 = date(2025, 7, 1)
ADS_FILTER_GAP = "Spesa pubblicitaria non disponibile per filtro brand/categoria"


def _day(day, revenue, units):
    return SimpleNamespace(day=day, revenue=revenue, units=units)


def _asin(asin, revenue, units=1, title=None):
    return SimpleNamespace(asin=asin, title=title or f"Prodotto {asin}", revenue=revenue, units=units)


def _install(monkeypatch, *, accounts=None, scope_asins=None, daily=None, asin_sales=None,
             campaign_ads=None, asin_ads=None, returns=None, states=None, anomalies=None,
             terms=None, owned=None, competitors=None, history=None):
    """Replace every query of data.py with canned rows keyed by period start."""
    calls: dict[str, list] = {}

    def record(name, value):
        calls.setdefault(name, []).append(value)

    async def fake_accounts(db, organization_id, account_ids):
        return accounts if accounts is not None else [
            {"id": ACC, "name": "TEST IT", "type": "seller", "country": "IT"}
        ]

    async def fake_scope_asins(db, account_ids, brand, category, asins):
        record("scope_asins", (brand, category, asins))
        return list(scope_asins or [])

    async def fake_daily(db, account_ids, start, end, asins):
        record("daily", asins)
        return (daily or {}).get(start, [])

    async def fake_asin_sales(db, account_ids, start, end, asins):
        return (asin_sales or {}).get(start, [])

    async def fake_campaign_ads(db, account_ids, start, end):
        record("campaign_ads", start)
        return (campaign_ads or {}).get(start)

    async def fake_asin_ads(db, account_ids, start, end, asins):
        record("asin_ads", asins)
        return (asin_ads or {}).get(start)

    async def fake_returns(db, account_ids, start, end, asins):
        return (returns or {}).get(start, 0)

    async def fake_states(db, account_ids, asins):
        return list(states or [])

    async def fake_anomalies(db, account_ids, asins):
        return dict(anomalies or {})

    async def fake_terms(db, account_ids, limit):
        record("terms", (account_ids, limit))
        return list(terms or [])

    async def fake_owned(db, account_ids, asins):
        return set(owned or set()) & set(asins)

    async def fake_competitors(db, organization_id, marketplaces):
        record("competitors", marketplaces)
        return list(competitors or [])

    async def fake_history(db, competitor_ids, start, end):
        return list(history or [])

    for name, fake in {
        "fetch_accounts": fake_accounts,
        "fetch_scope_asins": fake_scope_asins,
        "fetch_daily_sales": fake_daily,
        "fetch_asin_sales": fake_asin_sales,
        "fetch_campaign_ads": fake_campaign_ads,
        "fetch_asin_ads": fake_asin_ads,
        "fetch_returned_units": fake_returns,
        "fetch_quality_states": fake_states,
        "fetch_open_anomalies": fake_anomalies,
        "fetch_search_terms": fake_terms,
        "fetch_owned_asins": fake_owned,
        "fetch_competitors": fake_competitors,
        "fetch_competitor_history": fake_history,
    }.items():
        monkeypatch.setattr(qdata, name, fake)
    return calls


def _kpis(data: QuarterData) -> dict[str, Metric]:
    return {metric.key: metric for metric in data.kpis}


def _quarter_data(*, kpis=None, top=None, bottom=None, catalogue=None, terms=None,
                  competitors=None, gaps=None, monthly=None, language="it") -> QuarterData:
    return QuarterData(
        scope=QuarterScope(organization_id=ORG, account_ids=[ACC], year=2026, quarter=3,
                           language=language),
        kpis=kpis or [],
        monthly=monthly or [],
        top_asins=top or [],
        bottom_asins=bottom or [],
        catalogue=catalogue or {"states": {"green": 0, "yellow": 0, "red": 0, "grey": 0},
                                "total": 0, "as_of": None, "open_anomalies": {}},
        search_terms=terms or [],
        competitors=competitors or [],
        data_gaps=gaps or [],
    )


def _metric(key, value, previous=None, last_year=None, unit="EUR", provenance="actual"):
    return Metric(key=key, value=value, previous=previous, last_year=last_year,
                  provenance=provenance, unit=unit)


# --- periods ---------------------------------------------------------------------------


def test_quarter_bounds_q1_and_q4():
    assert quarter_bounds(2026, 1) == (date(2026, 1, 1), date(2026, 3, 31))
    assert quarter_bounds(2026, 4) == (date(2026, 10, 1), date(2026, 12, 31))
    assert quarter_bounds(2024, 3) == (date(2024, 7, 1), date(2024, 9, 30))
    with pytest.raises(ValueError):
        quarter_bounds(2026, 5)


def test_previous_quarter_wraps_year():
    assert previous_quarter(2026, 1) == (2025, 4)
    assert previous_quarter(2026, 3) == (2026, 2)


# --- data ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tacos_from_spend_and_revenue(monkeypatch):
    _install(
        monkeypatch,
        daily={
            Q3_2026: [_day(date(2026, 7, 10), 600, 60), _day(date(2026, 8, 10), 400, 40)],
            Q2_2026: [_day(date(2026, 5, 1), 800, 80)],
            Q3_2025: [_day(date(2025, 7, 3), 500, 50)],
        },
        campaign_ads={Q3_2026: (150.0, 600.0), Q2_2026: (80.0, 400.0), Q3_2025: (50.0, 100.0)},
        returns={Q3_2026: 5, Q2_2026: 8},
    )

    data = await collect_quarter_data(None, QuarterScope(ORG, [ACC], 2026, 3))
    kpis = _kpis(data)

    assert [m.key for m in data.kpis] == [
        "revenue", "units", "ad_spend", "ad_sales", "roas", "acos", "tacos", "return_rate",
    ]
    assert kpis["revenue"].value == 1000
    assert kpis["revenue"].previous == 800
    assert kpis["revenue"].last_year == 500
    assert kpis["units"].value == 100
    assert kpis["tacos"].value == pytest.approx(150 / 1000)
    assert kpis["tacos"].previous == pytest.approx(80 / 800)
    assert kpis["tacos"].last_year == pytest.approx(50 / 500)
    assert kpis["roas"].value == pytest.approx(4.0)
    assert kpis["acos"].value == pytest.approx(0.25)
    assert kpis["return_rate"].value == pytest.approx(0.05)
    assert kpis["return_rate"].previous == pytest.approx(0.10)
    assert all(m.provenance == "actual" for m in data.kpis)
    july, august, september = data.monthly
    assert (july["month"], july["revenue"], july["revenue_last_year"]) == (7, 600, 500)
    assert (august["revenue"], august["revenue_last_year"]) == (400, None)
    assert (september["revenue"], september["revenue_last_year"]) == (None, None)


@pytest.mark.asyncio
async def test_metric_without_data_is_none_and_reported_in_gaps(monkeypatch):
    _install(
        monkeypatch,
        daily={Q3_2026: [_day(date(2026, 7, 10), 1000, 0)], Q2_2026: [_day(date(2026, 5, 1), 900, 9)]},
    )

    data = await collect_quarter_data(None, QuarterScope(ORG, [ACC], 2026, 3))
    kpis = _kpis(data)

    for key in ("ad_spend", "ad_sales", "roas", "acos", "tacos"):
        assert kpis[key].value is None, key
    assert kpis["return_rate"].value is None  # zero units sold
    assert kpis["revenue"].last_year is None
    gaps = " | ".join(data.data_gaps)
    assert "Dati pubblicitari non disponibili" in gaps
    assert "Tasso di reso non calcolabile" in gaps
    assert "Q3 2025" in gaps


@pytest.mark.asyncio
async def test_brand_filter_uses_asin_rows_and_reports_missing_ad_spend(monkeypatch):
    calls = _install(
        monkeypatch,
        scope_asins=["B0TEST0001", "B0TEST0002"],
        daily={Q3_2026: [_day(date(2026, 7, 10), 300, 3)]},
        campaign_ads={Q3_2026: (999.0, 999.0)},
    )
    scope = QuarterScope(ORG, [ACC], 2026, 3, brand="TESTBRAND")

    data = await collect_quarter_data(None, scope)
    kpis = _kpis(data)

    assert calls["scope_asins"] == [("TESTBRAND", None, None)]
    assert calls["daily"] == [["B0TEST0001", "B0TEST0002"]] * 3
    assert "campaign_ads" not in calls
    assert calls["asin_ads"] == [["B0TEST0001", "B0TEST0002"]] * 3
    assert kpis["revenue"].value == 300
    assert kpis["ad_spend"].value is None
    assert ADS_FILTER_GAP in data.data_gaps


@pytest.mark.asyncio
async def test_filter_matching_no_product_is_reported(monkeypatch):
    _install(monkeypatch, scope_asins=[])

    data = await collect_quarter_data(None, QuarterScope(ORG, [ACC], 2026, 3, category="Cucina"))

    assert _kpis(data)["revenue"].value is None
    assert any("Nessun prodotto" in gap for gap in data.data_gaps)


@pytest.mark.asyncio
async def test_top_and_bottom_asins_compare_with_previous_quarter(monkeypatch):
    _install(
        monkeypatch,
        asin_sales={
            Q3_2026: [_asin("B0TEST0001", 500), _asin("B0TEST0002", 100), _asin("B0TEST0003", 300)],
            Q2_2026: [_asin("B0TEST0001", 400), _asin("B0TEST0002", 600), _asin("B0TEST0004", 50)],
        },
    )

    data = await collect_quarter_data(None, QuarterScope(ORG, [ACC], 2026, 3))

    assert [row["asin"] for row in data.top_asins] == ["B0TEST0001", "B0TEST0003", "B0TEST0002"]
    assert data.top_asins[0]["previous_revenue"] == 400
    assert data.top_asins[0]["title"] == "Prodotto B0TEST0001"
    assert [(row["asin"], row["change"]) for row in data.bottom_asins] == [
        ("B0TEST0002", -500),
        ("B0TEST0004", -50),
    ]


@pytest.mark.asyncio
async def test_catalogue_counts_and_vendor_search_terms_gap(monkeypatch):
    calls = _install(
        monkeypatch,
        accounts=[{"id": ACC, "name": "TEST VC", "type": "vendor", "country": "IT"}],
        states=[
            SimpleNamespace(components={"state": "red"}, snapshot_date=date(2026, 11, 20)),
            SimpleNamespace(components={"state": "green"}, snapshot_date=date(2026, 11, 21)),
            SimpleNamespace(components={"state": "green"}, snapshot_date=date(2026, 11, 21)),
            SimpleNamespace(components={"title": {"earned": 10, "max": 20}}, snapshot_date=date(2026, 1, 5)),
        ],
        anomalies={"content_changed": 3, "child_detached": 1},
    )

    data = await collect_quarter_data(None, QuarterScope(ORG, [ACC], 2026, 3))

    assert data.catalogue["states"] == {"green": 2, "yellow": 0, "red": 1, "grey": 1}
    assert data.catalogue["total"] == 4
    assert data.catalogue["as_of"] == date(2026, 11, 21)
    assert data.catalogue["open_anomalies"] == {"content_changed": 3, "child_detached": 1}
    assert "terms" not in calls
    assert data.search_terms == []
    assert any("vendor" in gap for gap in data.data_gaps)


@pytest.mark.asyncio
async def test_search_terms_and_competitors_are_shaped(monkeypatch):
    comp_id = uuid.UUID(int=9)
    _install(
        monkeypatch,
        terms=[
            SimpleNamespace(
                account_id=ACC, week_start=date(2026, 11, 8), week_end=date(2026, 11, 14),
                search_term="test term", search_frequency_rank=120,
                top_clicked=[
                    {"rank": 1, "asin": "B0TEST0100", "click_share": 0.3},
                    {"rank": 2, "asin": "B0TEST0001", "click_share": 0.2},
                ],
            )
        ],
        owned={"B0TEST0001"},
        competitors=[
            SimpleNamespace(id=comp_id, asin="B0TEST0200", title="Rival", brand="OTHERBRAND",
                            marketplace="IT", current_price=Decimal("21.00"), current_bsr=900,
                            rating=Decimal("4.20"))
        ],
        history=[
            SimpleNamespace(competitor_id=comp_id, date=date(2026, 7, 2), price=Decimal("20.00"),
                            bsr=1000, rating=Decimal("4.00")),
            SimpleNamespace(competitor_id=comp_id, date=date(2026, 9, 29), price=Decimal("22.00"),
                            bsr=800, rating=Decimal("4.10")),
        ],
    )

    data = await collect_quarter_data(None, QuarterScope(ORG, [ACC], 2026, 3))

    term = data.search_terms[0]
    assert term["term"] == "test term"
    assert term["country"] == "IT"
    assert term["top_asin"] == "B0TEST0100"
    assert term["own_click_share"] == pytest.approx(0.2)
    competitor = data.competitors[0]
    assert competitor["price"] == pytest.approx(22.0)
    assert competitor["price_change_pct"] == pytest.approx(10.0)
    assert competitor["bsr"] == 800
    assert competitor["bsr_change"] == -200


def test_account_totals_use_daily_total_rows_and_filters_use_asin_rows():
    from sqlalchemy.dialects import postgresql

    captured = []

    class Session:
        async def execute(self, query):
            captured.append(query)
            return SimpleNamespace(all=lambda: [])

    import asyncio

    async def run():
        await qdata.fetch_daily_sales(Session(), [ACC], Q3_2026, date(2026, 9, 30), None)
        await qdata.fetch_daily_sales(Session(), [ACC], Q3_2026, date(2026, 9, 30), ["B0TEST0001"])
        assert await qdata.fetch_daily_sales(Session(), [ACC], Q3_2026, date(2026, 9, 30), []) == []

    asyncio.run(run())

    def sql(query):
        return str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    assert len(captured) == 2
    assert "'__DAILY_TOTAL__'" in sql(captured[0])
    assert "B0TEST0001" not in sql(captured[0])
    assert "'B0TEST0001'" in sql(captured[1])
    assert "'__DAILY_TOTAL__'" not in sql(captured[1])


# --- insights --------------------------------------------------------------------------


def test_rule_insights_flags_decline():
    data = _quarter_data(
        kpis=[
            _metric("revenue", 80.0, previous=100.0, last_year=70.0),
            _metric("tacos", 0.15, previous=0.10, unit="%"),
        ],
        bottom=[{"asin": "B0TEST0002", "title": "Two", "revenue": 10.0,
                 "previous_revenue": 40.0, "change": -30.0}],
        catalogue={"states": {"green": 6, "yellow": 1, "red": 3, "grey": 0}, "total": 10,
                   "as_of": date(2026, 11, 21), "open_anomalies": {"content_changed": 2}},
    )

    insights = rule_insights(data)
    titles = [insight.title for insight in insights]

    assert "Ricavi in calo rispetto al trimestre precedente" in titles
    assert "Ricavi in crescita rispetto allo stesso trimestre dell'anno precedente" in titles
    assert "TACOS in aumento" in titles
    assert "ASIN in maggior calo" in titles
    assert "Schede prodotto con semaforo rosso" in titles
    assert "Anomalie di catalogo aperte" in titles
    assert all(insight.source == "rules" and insight.action for insight in insights)
    decline = insights[titles.index("Ricavi in calo rispetto al trimestre precedente")]
    assert "-20,0%" in decline.body


def test_rule_insights_without_signals_still_returns_one_insight_in_english():
    insights = rule_insights(_quarter_data(language="en"))
    assert len(insights) == 1
    assert insights[0].title == "Stable quarter"


def test_build_insights_falls_back_without_key(monkeypatch):
    def no_client(api_key):
        raise AssertionError("no AI call without a key")

    monkeypatch.setattr(qinsights.settings, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(qinsights, "_anthropic_client", no_client)
    data = _quarter_data(kpis=[_metric("revenue", 80.0, previous=100.0)])

    insights = build_insights(data)

    assert insights == rule_insights(data)
    assert all(insight.source == "rules" for insight in insights)


def test_build_insights_falls_back_when_provider_fails(monkeypatch):
    class Messages:
        def create(self, **kwargs):
            raise RuntimeError("credit balance is too low")

    monkeypatch.setattr(qinsights.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(qinsights, "_anthropic_client", lambda key: SimpleNamespace(messages=Messages()))
    data = _quarter_data(kpis=[_metric("revenue", 80.0, previous=100.0)])

    assert build_insights(data) == rule_insights(data)


def test_build_insights_uses_ai_answer(monkeypatch):
    sent = {}

    class Messages:
        def create(self, **kwargs):
            sent.update(kwargs)
            payload = {"insights": [{"title": "Spingi B0TEST0001", "body": "Ricavi +25%.",
                                     "action": "Aumenta il budget."}]}
            return SimpleNamespace(content=[SimpleNamespace(text="```json\n" + json.dumps(payload) + "\n```")])

    monkeypatch.setattr(qinsights.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(qinsights, "_anthropic_client", lambda key: SimpleNamespace(messages=Messages()))

    insights = build_insights(_quarter_data(kpis=[_metric("revenue", 125.0, previous=100.0)]))

    assert insights == [Insight("Spingi B0TEST0001", "Ricavi +25%.", "Aumenta il budget.", "ai")]
    assert sent["model"] == qinsights.AI_MODEL
    assert "Italian" in sent["messages"][0]["content"]


# --- deck ------------------------------------------------------------------------------


def _full_data(language="it") -> QuarterData:
    return _quarter_data(
        language=language,
        kpis=[
            _metric("revenue", 12000.0, previous=10000.0, last_year=9000.0),
            _metric("units", 900.0, previous=800.0, last_year=None, unit="units"),
            _metric("ad_spend", 1500.0, previous=1000.0, last_year=900.0),
            _metric("ad_sales", 6000.0, previous=5000.0, last_year=4000.0),
            _metric("roas", 4.0, previous=5.0, last_year=None, unit="x"),
            _metric("acos", 0.25, previous=0.2, last_year=None, unit="%"),
            _metric("tacos", 0.125, previous=0.1, last_year=0.1, unit="%"),
            _metric("return_rate", 0.03, previous=0.02, last_year=None, unit="%",
                    provenance="estimated"),
        ],
        monthly=[
            {"month": 7, "revenue": 4000.0, "units": 300.0, "revenue_last_year": 3000.0,
             "units_last_year": 250.0},
            {"month": 8, "revenue": 5000.0, "units": 350.0, "revenue_last_year": None,
             "units_last_year": None},
            {"month": 9, "revenue": 3000.0, "units": 250.0, "revenue_last_year": 3500.0,
             "units_last_year": 260.0},
        ],
        top=[{"asin": f"B0TEST000{i}", "title": f"Prodotto {i}", "revenue": 1000.0 - i,
              "units": 10.0, "previous_revenue": 900.0, "change_pct": 11.0} for i in range(1, 10)],
        bottom=[{"asin": "B0TEST0010", "title": "Prodotto 10", "revenue": 100.0,
                 "previous_revenue": 400.0, "change": -300.0}],
        catalogue={"states": {"green": 6, "yellow": 1, "red": 3, "grey": 2}, "total": 12,
                   "as_of": date(2026, 11, 21), "open_anomalies": {"content_changed": 2}},
        terms=[{"term": "test term", "country": "IT", "rank": 120, "week_start": date(2026, 11, 8),
                "week_end": date(2026, 11, 14), "top_asin": "B0TEST0100", "top_click_share": 0.3,
                "own_click_share": 0.2}],
        competitors=[{"asin": "B0TEST0200", "title": "Rival", "brand": "OTHERBRAND",
                      "marketplace": "IT", "price": 22.0, "price_change_pct": 10.0, "bsr": 800,
                      "bsr_change": -200, "rating": 4.1, "rating_change": 0.1}],
        gaps=["Dati pubblicitari non disponibili per Q3 2025"],
    )


def _slide_text(slide) -> str:
    parts = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            parts.append(shape.text_frame.text)
        if shape.has_table:
            for row in shape.table.rows:
                parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


def test_deck_is_valid_pptx_with_expected_slide_count():
    data = _full_data()
    insights = rule_insights(data)

    deck = build_quarterly_deck(data, insights)
    prs = Presentation(io.BytesIO(deck))
    texts = [_slide_text(slide) for slide in prs.slides]

    assert len(prs.slides) >= 8
    kpi_slide = next(text for text in texts if "Indicatori chiave" in text)
    assert "Dato effettivo" in kpi_slide
    assert "Stima" in kpi_slide
    assert "+20,0%" in kpi_slide  # revenue vs previous quarter
    assert "+2,5 pp" in kpi_slide  # TACOS vs previous quarter, in points
    assert any("B0TEST0010" in text for text in texts)
    assert any("test term" in text for text in texts)
    assert any("OTHERBRAND" in text for text in texts)
    assert any(insights[0].title in text for text in texts)
    assert any("Dati pubblicitari non disponibili per Q3 2025" in text for text in texts)


def test_empty_deck_in_english_still_has_every_section():
    deck = build_quarterly_deck(_quarter_data(language="en"), [])
    prs = Presentation(io.BytesIO(deck))
    texts = "\n".join(_slide_text(slide) for slide in prs.slides)

    assert len(prs.slides) >= 8
    assert "Key indicators" in texts
    assert "No data available" in texts


# --- Postgres ----------------------------------------------------------------------------


@pytest_asyncio.fixture
async def pg():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")
@pytest.mark.asyncio
async def test_collect_quarter_data_against_postgres(pg):
    from app.models.advertising import (
        AdvertisingCampaign,
        AdvertisingMetrics,
        AdvertisingMetricsByAsin,
    )
    from app.models.amazon_account import AccountType, AmazonAccount
    from app.models.brand_search_term import BrandSearchTerm
    from app.models.catalog_monitor import CatalogAnomaly
    from app.models.competitor import Competitor, CompetitorHistory
    from app.models.listing_quality import ListingQualitySnapshot
    from app.models.product import Product
    from app.models.returns_data import ReturnData
    from app.models.sales_data import SalesData
    from app.models.user import Organization
    from app.services.data_extraction import DAILY_TOTAL_ASIN

    tag = uuid.uuid4().hex[:12]
    org = Organization(name=f"Org {tag}", slug=f"org-{tag}")
    pg.add(org)
    await pg.flush()
    account = AmazonAccount(organization_id=org.id, account_name=f"Acc {tag}",
                            account_type=AccountType.SELLER, marketplace_id="APJ6JRA9NG5V4",
                            marketplace_country="IT", seller_id="SELLER1")
    pg.add(account)
    await pg.flush()
    acc = account.id
    pg.add_all([
        Product(account_id=acc, asin="B0TEST0001", title="Uno", brand="TESTBRAND", category="Cucina"),
        Product(account_id=acc, asin="B0TEST0002", title="Due", brand="OTHERBRAND", category="Cucina"),
    ])

    def sale(day, asin, ordered, shipped=None, units=1):
        return SalesData(account_id=acc, date=day, asin=asin, ordered_product_sales=Decimal(ordered),
                         shipped_revenue=None if shipped is None else Decimal(shipped),
                         units_ordered=units, total_order_items=units)

    pg.add_all([
        sale(date(2026, 7, 5), DAILY_TOTAL_ASIN, "1000", units=10),
        sale(date(2026, 8, 5), DAILY_TOTAL_ASIN, "500", shipped="400", units=5),
        sale(date(2026, 7, 5), "B0TEST0001", "700", units=7),
        sale(date(2026, 8, 5), "B0TEST0001", "300", shipped="250", units=2),
        sale(date(2026, 7, 5), "B0TEST0002", "300", units=3),
        sale(date(2026, 5, 5), DAILY_TOTAL_ASIN, "2000", units=20),
        sale(date(2026, 5, 5), "B0TEST0002", "1500", units=15),
        sale(date(2025, 7, 5), DAILY_TOTAL_ASIN, "800", units=8),
    ])
    campaign = AdvertisingCampaign(account_id=acc, campaign_id=f"c-{tag}", campaign_type="sponsoredProducts",
                                   state="enabled")
    pg.add(campaign)
    await pg.flush()
    pg.add_all([
        AdvertisingMetrics(campaign_id=campaign.id, date=date(2026, 7, 5), cost=Decimal("140"),
                           attributed_sales_7d=Decimal("560")),
        AdvertisingMetricsByAsin(account_id=acc, campaign_id=campaign.id, asin="B0TEST0001",
                                 date=date(2026, 7, 5), cost=Decimal("50"),
                                 attributed_sales_7d=Decimal("200")),
        ReturnData(account_id=acc, asin="B0TEST0001", return_date=date(2026, 7, 9), quantity=3),
        ReturnData(account_id=acc, asin="B0TEST0002", return_date=date(2026, 7, 9), quantity=1),
        ListingQualitySnapshot(account_id=acc, asin="B0TEST0001", snapshot_date=date(2026, 11, 1),
                               score=20, components={"state": "red", "results": []}),
        ListingQualitySnapshot(account_id=acc, asin="B0TEST0001", snapshot_date=date(2026, 11, 20),
                               score=90, components={"state": "green", "results": []}),
        ListingQualitySnapshot(account_id=acc, asin="B0TEST0002", snapshot_date=date(2026, 11, 20),
                               score=40, components={"state": "yellow", "results": []}),
        CatalogAnomaly(account_id=acc, asin="B0TEST0001", kind="content_changed", field="title"),
        CatalogAnomaly(account_id=acc, asin="B0TEST0002", kind="content_changed", field="title",
                       status="resolved", resolved_at=datetime(2026, 11, 2, tzinfo=timezone.utc)),
        BrandSearchTerm(account_id=acc, week_start=date(2026, 11, 8), week_end=date(2026, 11, 14),
                        search_term="pentola test", search_frequency_rank=50,
                        top_clicked=[{"rank": 1, "asin": "B0TEST0001", "click_share": 0.25}],
                        contains_account_asin=True),
        BrandSearchTerm(account_id=acc, week_start=date(2026, 11, 1), week_end=date(2026, 11, 7),
                        search_term="old week", search_frequency_rank=1,
                        top_clicked=[], contains_account_asin=True),
    ])
    competitor = Competitor(organization_id=org.id, asin="B0TEST0300", marketplace="IT",
                            brand="OTHERBRAND", current_price=Decimal("30"), current_bsr=500)
    pg.add(competitor)
    await pg.flush()
    pg.add_all([
        CompetitorHistory(competitor_id=competitor.id, date=date(2026, 7, 1), price=Decimal("25"), bsr=700),
        CompetitorHistory(competitor_id=competitor.id, date=date(2026, 9, 30), price=Decimal("30"), bsr=500),
    ])
    await pg.flush()

    whole = await collect_quarter_data(pg, QuarterScope(org.id, [], 2026, 3))
    kpis = _kpis(whole)
    assert kpis["revenue"].value == pytest.approx(1400)  # 1000 ordered + 400 shipped
    assert kpis["revenue"].previous == pytest.approx(2000)
    assert kpis["revenue"].last_year == pytest.approx(800)
    assert kpis["units"].value == pytest.approx(15)
    assert kpis["ad_spend"].value == pytest.approx(140)
    assert kpis["tacos"].value == pytest.approx(140 / 1400)
    assert kpis["return_rate"].value == pytest.approx(4 / 15)
    assert [row["asin"] for row in whole.top_asins] == ["B0TEST0001", "B0TEST0002"]
    assert whole.top_asins[0]["revenue"] == pytest.approx(950)
    assert whole.top_asins[0]["title"] == "Uno"
    assert whole.bottom_asins[0]["asin"] == "B0TEST0002"
    assert whole.catalogue["states"] == {"green": 1, "yellow": 1, "red": 0, "grey": 0}
    assert whole.catalogue["open_anomalies"] == {"content_changed": 1}
    assert [term["term"] for term in whole.search_terms] == ["pentola test"]
    assert whole.search_terms[0]["own_click_share"] == pytest.approx(0.25)
    assert whole.competitors[0]["price_change_pct"] == pytest.approx(20.0)

    branded = await collect_quarter_data(pg, QuarterScope(org.id, [acc], 2026, 3, brand="testbrand"))
    kpis = _kpis(branded)
    assert kpis["revenue"].value == pytest.approx(950)
    assert kpis["revenue"].previous is None
    assert kpis["ad_spend"].value == pytest.approx(50)
    assert kpis["return_rate"].value == pytest.approx(3 / 9)
    assert branded.catalogue["states"]["yellow"] == 0
    assert ADS_FILTER_GAP not in branded.data_gaps
