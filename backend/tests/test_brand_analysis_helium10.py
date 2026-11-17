"""Prospect deck from a Helium 10 Market Tracker 360 market (no network).

Synthetic rows only: made-up brands ("Testbrand", "Otherbrand") and B0TEST
ASINs in the shape ``get_market_products`` returns.
"""
import asyncio
from datetime import date
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.brand_analysis import BrandAnalysisCreate  # noqa: E402
from app.services.brand_analysis.prospect import build_prospect_metrics  # noqa: E402
from app.services.brand_analysis_service import (  # noqa: E402
    BrandAnalysisDataError,
    brand_rows,
    build_brand_analysis_pptx,
    calculate_brand_metrics,
    validate_pptx_bytes,
)
from app.services.brand_analysis_sources import (  # noqa: E402
    EXPORT_ROW_KEYS,
    Helium10MarketDataSource,
    mt360_latest_end,
    mt360_row,
)

MARKET = {"id": 42, "name": "Testbrand", "marketplace": "IT", "type": 2, "parentDataMode": False}


def _item(n, revenue, units, *, brand="Testbrand", bb="Amazon", best="2025-07", pack=1, title=None):
    return {
        "asin": f"B0TEST{n:04d}",
        "title": title or f"Testbrand, Pasta di legumi {n}, Confezione da 250 g",
        "brand": brand,
        "manufacturer": "Testbrand Spa",
        "totalRevenue": revenue,
        "totalSales": units,
        "price": round(revenue / units, 2) if units else None,
        "rating": 4.5,
        "reviews": 120 + n,
        "numberOfImages": 7,
        "sellersQty": 2,
        "bbSeller": bb,
        "bsr": 1000 + n,
        "FBA": "AMZ",
        "fbaFee": 3.5,
        "bestMonth": best,
        "packageQuantity": pack,
        "subCategories": [
            {"nodeId": "1", "title": "Pasta corta", "pathByName": ["Alimentari e cura della casa", "Pasta"]}
        ],
    }


YEARS = {
    2025: [
        _item(1, 30000.0, 10000),
        _item(2, 12000.0, 4000, bb="Farmacia Test"),
        _item(3, 6000.0, 1000, pack=6, title="Testbrand Pasta 6 confezioni da 250 g"),
        _item(4, 0.0, 0),
        _item(9, 50000.0, 20000, brand="Otherbrand"),
    ],
    2024: [
        _item(1, 20000.0, 7000),
        _item(2, 10000.0, 3500, bb="Farmacia Test"),
        _item(9, 40000.0, 16000, brand="Otherbrand"),
    ],
}


class FakeClient:
    def __init__(self, years=YEARS, markets=(MARKET,)):
        self.years = years
        self.markets = list(markets)
        self.calls = []

    def list_markets(self):
        self.calls.append(("list_markets",))
        return self.markets

    def market_products(self, market_id, date_from, date_to, *, parent_data_mode=False):
        self.calls.append(("market_products", market_id, date_from, date_to, parent_data_mode))
        return self.years.get(int(date_from[:4]), [])


def _source(client=None, today=date(2026, 11, 17)):
    return Helium10MarketDataSource(market_id=42, client=client or FakeClient(), today=today)


def test_latest_end_follows_the_saturday_cutoff():
    assert mt360_latest_end(date(2026, 11, 17)) == date(2026, 11, 7)  # Tuesday
    assert mt360_latest_end(date(2026, 11, 14)) == date(2026, 11, 14)  # Saturday
    assert mt360_latest_end(date(2026, 11, 15)) == date(2026, 11, 14)  # Sunday


def test_row_mapping_matches_the_export_shape():
    row = mt360_row(_item(3, 6000.0, 1000, pack=6))
    assert set(row) == set(EXPORT_ROW_KEYS)
    assert row["asin"] == "B0TEST0003"
    assert row["revenue"] == 6000.0 and row["units"] == 1000.0
    assert row["subcategory"] == "Pasta corta"
    assert row["category"] == "Alimentari e cura della casa"
    assert row["buy_box_owner"] == "Amazon"
    assert row["best_sales_period"] == "2025-07"
    assert row["unit_count"] == 6.0


def test_fetch_year_reads_the_calendar_year_of_the_market():
    client = FakeClient()
    parsed = asyncio.run(_source(client).fetch_year(2025))
    assert parsed.source_name == "helium10_mt360"
    assert parsed.row_count == 5
    assert ("market_products", 42, "2025-01-01", "2025-12-31", False) in client.calls
    assert parsed.rows["revenue"].sum() == pytest.approx(98000.0)


def test_unknown_market_is_a_clear_error():
    source = _source(FakeClient(markets=()))
    with pytest.raises(BrandAnalysisDataError, match="not in the connected Helium 10 account"):
        asyncio.run(source.fetch_year(2025))


def test_year_without_sales_is_a_clear_error():
    source = _source(FakeClient(years={2025: [_item(1, 0.0, 0)]}))
    with pytest.raises(BrandAnalysisDataError, match="no 2025 sales"):
        asyncio.run(source.fetch_year(2025))


def test_brand_rows_keep_the_brand_or_the_whole_market():
    parsed = asyncio.run(_source().fetch_year(2025))
    assert set(brand_rows(parsed.rows, "testbrand")["brand"]) == {"Testbrand"}
    assert len(brand_rows(parsed.rows, "Nobrand")) == len(parsed.rows)


def _deck_metrics(language="it"):
    source = _source()
    parsed_2024 = asyncio.run(source.fetch_year(2024))
    parsed_2025 = asyncio.run(source.fetch_year(2025))
    metrics = calculate_brand_metrics(parsed_2024, parsed_2025, brand_name="Testbrand", language=language)
    metrics["prospect"] = build_prospect_metrics(
        brand_rows(parsed_2024.rows, "Testbrand"), brand_rows(parsed_2025.rows, "Testbrand"),
        brand_name="Testbrand",
    )
    metrics["prospect"]["source"] = {"kind": "helium10_mt360", "market_name": "Testbrand"}
    return metrics


def test_prospect_metrics_exclude_other_brands_in_the_market():
    prospect = _deck_metrics()["prospect"]
    assert prospect["revenue_2025"] == pytest.approx(48000.0)
    assert prospect["revenue_2024"] == pytest.approx(30000.0)


def test_deck_names_helium10_as_the_source():
    deck = validate_pptx_bytes(build_brand_analysis_pptx(_deck_metrics(), {}, language="it"))
    text = "\n".join(deck["slide_texts"])
    assert "Helium 10 Market Tracker 360" in text
    assert "export di prodotto caricati" not in text


def test_create_payload_accepts_a_market_id():
    payload = BrandAnalysisCreate(brand_name="Testbrand", mode="helium10_mt360", helium10_market_id=42)
    assert payload.helium10_market_id == 42
    with pytest.raises(ValueError):
        BrandAnalysisCreate(brand_name="Testbrand", mode="helium10_mt360", helium10_market_id=0)


def test_markets_endpoint_lists_and_caches(monkeypatch):
    from app.api.v1 import brand_analysis as api
    from app.core import helium10

    client = FakeClient()
    monkeypatch.setattr(helium10, "get_client", lambda: client)
    monkeypatch.setattr(api, "_markets_cache", {"at": 0.0, "markets": None})

    first = asyncio.run(api.list_helium10_markets(current_user=None, organization=None))
    second = asyncio.run(api.list_helium10_markets(current_user=None, organization=None))

    assert first == second
    assert first["connected"] is True
    assert first["markets"] == [
        {"id": 42, "name": "Testbrand", "marketplace": "IT", "type": "brands", "products": None}
    ]
    assert client.calls.count(("list_markets",)) == 1  # second call served from cache


def test_markets_endpoint_when_not_connected(monkeypatch):
    from app.api.v1 import brand_analysis as api
    from app.core import helium10

    monkeypatch.setattr(helium10, "get_client", lambda: None)
    result = asyncio.run(api.list_helium10_markets(current_user=None, organization=None))
    assert result == {"connected": False, "markets": [], "error": None}


def test_amazon_held_buy_box_counts_with_the_brand_on_every_slide():
    deck = validate_pptx_bytes(build_brand_analysis_pptx(_deck_metrics(), {}, language="it"))
    text = "\n".join(deck["slide_texts"])
    # Testbrand rows: Amazon holds the Buy Box on 3 ASINs, a pharmacy on 1.
    assert "Buy Box del marchio o di Amazon su 3 ASIN" in text
    assert "Buy Box del marchio su 0 ASIN" not in text
