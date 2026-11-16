"""Prospect deck: metrics from Helium 10-style yearly exports and the deck built on them.

Synthetic data only: a made-up brand ("Testbrand") with B0TEST ASINs, shaped
like a Helium 10 Black Box export (Ratings, Buy Box, Best sales period,
Unit Sales, Total Revenue with thousands separators).
"""
from io import BytesIO
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.brand_analysis.prospect import (  # noqa: E402
    LIGHT_GREEN,
    LIGHT_RED,
    LIGHT_YELLOW,
    build_prospect_metrics,
)
from app.services.brand_analysis_service import (  # noqa: E402
    build_brand_analysis_pptx,
    calculate_brand_metrics,
    parse_brand_export,
    validate_pptx_bytes,
)

LONG_TAIL = "Lenisce e protegge la pelle delicata dei bambini con ingredienti naturali"


def _row(n, title, revenue, units, *, buy_box="Testbrand", sellers=3, rating=4.6,
         reviews=250, images=8, subcategory="Creme lenitive", category="Prima infanzia",
         period="2025-06", fulfillment="FBA", unit_count=1):
    return {
        "Product": title,
        "ASIN": f"B0TEST{n:04d}",
        "Brand": "Testbrand",
        "Price": round(revenue / units, 2) if units else 0,
        "BSR": 1000 + n,
        "Number of sellers": sellers,
        "Fulfillment": fulfillment,
        "Ratings": rating,
        "Review count": reviews,
        "Images": images,
        "Buy Box": buy_box,
        "Category": category,
        "Subcategory": subcategory,
        "Best sales period": period,
        "Unit count": unit_count,
        "Pack form": "Crema",
        "Manufacturer": "Testbrand Spa",
        "Unit Sales": f"{units:,}",
        "Total Revenue": f"{revenue:,.2f}",
    }


def _rows_2025():
    return [
        _row(1, f"Testbrand - Crema EMU - 100ml - CAMBIO PANNOLINO - {LONG_TAIL}", 300_000, 25_000,
             subcategory="Lavaggi e clisteri"),
        _row(2, f"Testbrand - Talco NON Talco - 120ml - SUDORAZIONE E ZANZARE - {LONG_TAIL}", 200_000, 20_000,
             period="2025-07"),
        _row(3, f"Testbrand - Spray Talco - 100ml - Sudorazione e Zanzare - {LONG_TAIL}", 150_000, 15_000,
             period="2026-08", buy_box="Farmacia Rossi", sellers=30),
        _row(4, f"Testbrand - Pasta CAMBIO - 50ml - CAMBIO PANNOLINO - {LONG_TAIL}", 120_000, 11_000,
             period="2025-02"),
        _row(5, "Testbrand Salviette Detergenti - 8 Confezioni da 60 pezzi", 80_000, 3_000,
             buy_box="Baby Shop", sellers=12, images=3, rating=3.8, reviews=12, period="2025-03",
             fulfillment="FBM"),
        _row(6, f"Testbrand - Crema seno - 15ml - ALLATTAMENTO - {LONG_TAIL}", 60_000, 5_000,
             period="2025-11"),
        _row(7, "Testbrand - COFANETTO NEONATO - Kit regalo con crema e detergente", 40_000, 1_500,
             period="2025-12", images=5, reviews=40),
        _row(8, "Testbrand Detergente corpo 400ml, confezione da 2", 30_000, 2_000,
             buy_box="Parafarmacia Bianchi", period="2025-01", fulfillment="FBM"),
        _row(9, "Testbrand Olio", 15_000, 1_000, period="2025-04", images=2, reviews=5, rating=4.1,
             fulfillment="FBM"),
        _row(10, f"Testbrand - Crema viso - 50ml - IDRATAZIONE - {LONG_TAIL}", 4_000, 400, period="2025-10"),
        _row(11, "Testbrand Gel", 500, 50, buy_box="", period="2025-09"),
        _row(12, "Testbrand Sapone", 0, 0, period="-"),
    ]


def _rows_2024():
    rows = _rows_2025()[:9]
    for row in rows:
        revenue = float(row["Total Revenue"].replace(",", "")) * 0.8
        row["Total Revenue"] = f"{revenue:,.2f}"
    return rows


def _csv(rows) -> bytes:
    buffer = BytesIO()
    pd.DataFrame(rows).to_csv(buffer, index=False)
    return buffer.getvalue()


def _parsed(rows, year):
    return parse_brand_export(_csv(rows), f"export_{year}.csv", year=year)


def _prospect():
    return build_prospect_metrics(
        _parsed(_rows_2024(), 2024).rows, _parsed(_rows_2025(), 2025).rows, brand_name="Testbrand"
    )


def test_parser_reads_helium10_ratings_and_keeps_deck_fields():
    rows = _parsed(_rows_2025(), 2025).rows.set_index("asin")
    first = rows.loc["B0TEST0001"]
    assert first["rating"] == 4.6
    assert first["best_sales_period"] == "2025-06"
    assert first["manufacturer"] == "Testbrand Spa"
    assert first["pack_form"] == "Crema"
    assert first["unit_count"] == 1
    assert first["revenue"] == 300_000


def test_totals_value_per_unit_and_yoy():
    prospect = _prospect()
    assert prospect["revenue_2025"] == 999_500
    assert prospect["units_2025"] == 83_950
    assert prospect["asins_with_sales_2025"] == 11
    assert prospect["asins_total_2025"] == 12
    assert round(prospect["value_per_unit_2025"], 2) == round(999_500 / 83_950, 2)
    assert round(prospect["yoy_revenue_pct"], 1) == round((999_500 / (995_000 * 0.8) - 1) * 100, 1)
    assert prospect["manufacturer"] == "Testbrand Spa"


def test_product_areas_come_from_uppercase_title_segments_case_insensitively():
    prospect = _prospect()
    assert prospect["area_source"] == "titles"
    areas = {area["name"]: area for area in prospect["areas"]}
    # The spray's mixed-case "Sudorazione e Zanzare" joins the uppercase area.
    assert areas["Sudorazione e zanzare"]["revenue"] == 350_000
    assert areas["Cambio pannolino"]["revenue"] == 420_000
    assert areas["Cambio pannolino"]["asins"] == 2
    assert round(sum(area["share"] for area in prospect["areas"]), 6) == 100.0


def test_product_areas_fall_back_to_subcategory_without_title_structure():
    rows = [_row(n, f"Testbrand prodotto {n}", 1000 * n, 100, subcategory=f"Sub {n % 2}") for n in range(1, 7)]
    prospect = build_prospect_metrics(_parsed(rows, 2024).rows, _parsed(rows, 2025).rows, brand_name="Testbrand")
    assert prospect["area_source"] == "subcategory"
    assert {area["name"] for area in prospect["areas"]} == {"Sub 0", "Sub 1"}


def test_concentration_counts_asins_to_reach_80_percent_and_the_long_tail():
    pareto = _prospect()["pareto"]
    # 300 + 200 + 150 + 120 + 80 = 850k of 999.5k = 85%: five ASINs reach 80%.
    assert pareto["asins_to_80"] == 5
    assert round(pareto["top5_share"], 1) == 85.0
    assert pareto["tail_under_1000_count"] == 1
    assert len(pareto["curve"]) == 11


def test_seasonality_groups_peak_months_across_years():
    seasonality = _prospect()["seasonality"]
    # June 300k + July 200k + August 150k (2026-08 counts as August).
    assert round(seasonality["summer_share"], 1) == round(650_000 / 999_500 * 100, 1)
    assert seasonality["peak_month"] == 6
    assert len(seasonality["by_month"]) == 12


def test_buy_box_split_between_brand_pharmacies_and_other_sellers():
    buy_box = _prospect()["buy_box"]
    assert buy_box["brand_asins"] == 8
    assert buy_box["brand_asins_fba"] == 7
    assert buy_box["pharmacy_sellers"] == 2
    assert buy_box["other_sellers"] == 1
    shares = buy_box["revenue_share_by_type"]
    assert round(shares["pharmacy"], 1) == round(180_000 / 999_500 * 100, 1)
    assert round(shares["none"], 2) == round(500 / 999_500 * 100, 2)


def test_formats_detect_multipacks_and_gift_sets_from_titles():
    formats = _prospect()["formats"]
    assert formats["multipack_asins"] == 2
    assert formats["set_asins"] == 1
    assert round(formats["multipack_share"], 1) == round(110_000 / 999_500 * 100, 1)
    assert formats["multipack_third_party_buy_box"] == 2


def test_listing_traffic_lights_score_each_top_product():
    health = _prospect()["listing_health"]
    by_asin = {item["asin"]: item for item in health["items"]}
    assert by_asin["B0TEST0001"]["overall"] == LIGHT_GREEN
    weak = by_asin["B0TEST0005"]
    assert weak["checks"]["images"] == LIGHT_RED
    assert weak["checks"]["rating"] == LIGHT_RED
    assert weak["checks"]["buy_box"] == LIGHT_YELLOW
    assert weak["overall"] == LIGHT_RED
    assert health["counts"][LIGHT_GREEN] + health["counts"][LIGHT_YELLOW] + health["counts"][LIGHT_RED] == len(health["items"])


def test_prospect_metrics_are_json_safe():
    json.dumps(_prospect())


def _prospect_deck_metrics(language="it"):
    parsed_2024 = _parsed(_rows_2024(), 2024)
    parsed_2025 = _parsed(_rows_2025(), 2025)
    metrics = calculate_brand_metrics(parsed_2024, parsed_2025, brand_name="Testbrand", language=language)
    metrics["prospect"] = build_prospect_metrics(parsed_2024.rows, parsed_2025.rows, brand_name="Testbrand")
    return metrics


def test_prospect_deck_replaces_the_managed_brand_template():
    deck = validate_pptx_bytes(build_brand_analysis_pptx(_prospect_deck_metrics(), {}, language="it"))
    text = "\n".join(deck["slide_texts"])
    assert deck["slide_count"] >= 12
    for expected in ("aree", "Buy Box", "multipack", "semafor", "Metodologia"):
        assert expected.lower() in text.lower(), expected
    # The managed-brand template slides must not appear in a prospect deck.
    for template_only in ("Roadmap operativa", "Scenari di crescita", "Il nostro approccio"):
        assert template_only not in text


def test_prospect_deck_renders_in_english_too():
    deck = validate_pptx_bytes(build_brand_analysis_pptx(_prospect_deck_metrics("en"), {}, language="en"))
    assert "Methodology" in "\n".join(deck["slide_texts"])


def test_deck_without_prospect_metrics_keeps_the_managed_brand_template():
    metrics = _prospect_deck_metrics()
    metrics.pop("prospect")
    text = "\n".join(validate_pptx_bytes(build_brand_analysis_pptx(metrics, {}, language="it"))["slide_texts"])
    assert "Sintesi esecutiva" in text
    assert "COSA EMERGE" not in text
