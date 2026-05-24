from io import BytesIO
import asyncio
from datetime import date
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.brand_analysis_service import (  # noqa: E402
    BrandAnalysisNarrativeService,
    MissingColumnError,
    _canonical_mode,
    assess_data_completeness,
    build_brand_analysis_pptx,
    build_fallback_narrative,
    build_limitation_summary,
    build_metric_source_registry,
    build_metric_provenance,
    classify_sales_year_coverage,
    calculate_brand_metrics,
    parse_brand_export,
    validate_metric_provenance_for_deck,
    validate_pptx_bytes,
    yoy_percent,
)
from app.services.brand_analysis_capabilities import detect_brand_analysis_capabilities  # noqa: E402


def _csv_bytes(rows: list[dict]) -> bytes:
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")


def _xlsx_bytes(rows: list[dict]) -> bytes:
    output = BytesIO()
    pd.DataFrame(rows).to_excel(output, index=False)
    return output.getvalue()


def _source_rows_2024() -> list[dict]:
    return [
        {
            "ASIN": "B001",
            "Product Name": "Chef Knife",
            "Subcategory": "Knives",
            "Total Revenue": "1000",
            "Units Sold": "10",
            "Price": "100",
            "Rating": "4.5",
            "Reviews": "20",
            "Images": "6",
            "Seller Count": "1",
            "Buy Box Seller": "Amazon",
        },
        {
            "ASIN": "B002",
            "Product Name": "Pan Set",
            "Subcategory": "Pans",
            "Total Revenue": "500",
            "Units Sold": "5",
            "Price": "100",
            "Rating": "4.0",
            "Reviews": "10",
            "Images": "3",
            "Seller Count": "2",
            "Buy Box Seller": "Reseller A",
        },
        {
            "ASIN": "B004",
            "Product Name": "Old Cutlery",
            "Subcategory": "Cutlery",
            "Total Revenue": "300",
            "Units Sold": "3",
            "Price": "100",
            "Rating": "4.2",
            "Reviews": "30",
            "Images": "5",
            "Seller Count": "1",
            "Buy Box Seller": "Amazon",
        },
    ]


def _source_rows_2025() -> list[dict]:
    return [
        {
            "ASIN": "B001",
            "Product Name": "Chef Knife",
            "Subcategory": "Knives",
            "Total Revenue": "1500",
            "Units Sold": "15",
            "Price": "100",
            "Rating": "4.6",
            "Reviews": "25",
            "Images": "7",
            "Seller Count": "1",
            "Buy Box Seller": "Amazon",
        },
        {
            "ASIN": "B002",
            "Product Name": "Pan Set",
            "Subcategory": "Pans",
            "Total Revenue": "0",
            "Units Sold": "0",
            "Price": "100",
            "Rating": "4.1",
            "Reviews": "12",
            "Images": "4",
            "Seller Count": "3",
            "Buy Box Seller": "Reseller A",
        },
        {
            "ASIN": "B003",
            "Product Name": "Pot Set",
            "Subcategory": "Pots",
            "Total Revenue": "400",
            "Units Sold": "4",
            "Price": "100",
            "Rating": "5.0",
            "Reviews": "5",
            "Images": "2",
            "Seller Count": "1",
            "Buy Box Seller": "Amazon",
        },
    ]


def _metrics() -> dict:
    parsed_2024 = parse_brand_export(_csv_bytes(_source_rows_2024()), "2024.csv")
    parsed_2025 = parse_brand_export(_csv_bytes(_source_rows_2025()), "2025.csv")
    return calculate_brand_metrics(parsed_2024, parsed_2025, brand_name="Acme")


def _run(coro):
    return asyncio.run(coro)


def test_parse_brand_export_csv_and_xlsx_like_inputs():
    parsed_csv = parse_brand_export(_csv_bytes(_source_rows_2025()), "products.csv")
    parsed_xlsx = parse_brand_export(_xlsx_bytes(_source_rows_2025()), "products.xlsx")

    assert parsed_csv.row_count == 3
    assert parsed_xlsx.row_count == 3
    assert list(parsed_csv.rows["asin"]) == ["B001", "B002", "B003"]
    assert parsed_csv.rows.loc[0, "revenue"] == 1500
    assert parsed_xlsx.rows.loc[2, "product_name"] == "Pot Set"


def test_brand_metric_calculations_and_inactive_asin_logic():
    metrics = _metrics()

    assert metrics["total_revenue_2024"] == 1800
    assert metrics["total_revenue_2025"] == 1900
    assert metrics["yoy_percent"] == 5.6
    assert metrics["total_units_sold_2025"] == 19
    assert metrics["total_asins_2025"] == 3
    assert metrics["active_asins_2025"] == 2
    assert metrics["inactive_asins_2025"] == 1
    assert metrics["new_asins_yoy"] == 1
    assert metrics["percentage_inactive_asins"] == 33.3
    assert metrics["asins_with_more_than_1_seller"] == 1
    assert metrics["asins_with_fewer_than_5_images"] == 2
    assert metrics["asins_with_fewer_than_15_reviews"] == 2
    assert metrics["top_5_asins"][0]["asin"] == "B001"
    assert metrics["reseller_buy_box_distribution"][0]["reseller"] == "Amazon"


def test_yoy_percent_handles_zero_and_absent_previous_revenue():
    assert yoy_percent(100, 0) is None
    assert yoy_percent(100, None) is None
    assert yoy_percent(0, 0) == 0
    assert yoy_percent(75, 100) == -25.0


def test_legacy_external_provider_modes_are_not_normal_internal_flow():
    assert _canonical_mode("internal") == "internal"
    assert _canonical_mode("amazon_sp_api") == "internal"
    assert _canonical_mode("helium10_api") == "manual"
    assert _canonical_mode("helium10") == "manual"


def test_vine_suppression_rule_for_low_revenue_brand():
    metrics = _metrics()
    assert metrics["total_revenue_2025"] < 100000
    assert metrics["rules"]["can_mention_vine"] is False

    narrative = BrandAnalysisNarrativeService(api_key=None).generate(metrics, "en")
    serialized = str(narrative).lower()

    assert "vine" not in serialized


def test_pptx_generation_produces_valid_deck():
    metrics = _metrics()
    narrative = build_fallback_narrative(metrics)
    pptx_bytes = build_brand_analysis_pptx(metrics, narrative)

    from pptx import Presentation

    deck = Presentation(BytesIO(pptx_bytes))
    assert len(deck.slides) == 16
    assert pptx_bytes[:2] == b"PK"


def test_pptx_validate_helper_returns_structural_fingerprint():
    metrics = _metrics()
    narrative = build_fallback_narrative(metrics)
    pptx_bytes = build_brand_analysis_pptx(metrics, narrative)

    fingerprint = validate_pptx_bytes(pptx_bytes)
    assert fingerprint["slide_count"] == 16
    cover = fingerprint["slide_texts"][0].upper()
    assert "ACME" in cover and "AMAZON" in cover
    as_is = fingerprint["slide_texts"][1].upper()
    assert "CURRENT AMAZON PERFORMANCE" in as_is
    deck_text = "\n".join(fingerprint["slide_texts"]).upper()
    assert "MARKET SHARE" in deck_text
    assert "SEO & CONTENT" in deck_text


def test_validate_pptx_bytes_rejects_corrupted_artifact():
    """Pipeline validation must reject bytes that don't open as a deck.

    Guards against silently storing a broken artifact and handing it to
    the user. The processor wraps validate_pptx_bytes in a BrandAnalysisDataError
    so the job fails loudly instead.
    """
    try:
        validate_pptx_bytes(b"not a real pptx file")
    except Exception:
        return
    raise AssertionError("Expected validate_pptx_bytes to reject garbage bytes")


def test_pptx_pipeline_from_sample_2024_2025_data_produces_downloadable_artifact():
    """End-to-end: parse year exports, calculate metrics, build narrative,
    build PPTX, then validate the deck. Mirrors the process_brand_analysis_job
    pipeline without spinning up Celery or a real DB.
    """
    parsed_2024 = parse_brand_export(_csv_bytes(_source_rows_2024()), "sample_2024.csv", year=2024)
    parsed_2025 = parse_brand_export(_csv_bytes(_source_rows_2025()), "sample_2025.csv", year=2025)

    metrics = calculate_brand_metrics(parsed_2024, parsed_2025, brand_name="Acme")
    completeness = assess_data_completeness(parsed_2024, parsed_2025)
    metrics["data_completeness"] = completeness
    metrics["limitations"] = build_limitation_summary(metrics, capability_matrix=None, data_coverage=None)
    metrics["metric_source_registry"] = build_metric_source_registry(metrics, "manual_upload")

    narrative = build_fallback_narrative(metrics)
    pptx_bytes = build_brand_analysis_pptx(metrics, narrative)

    fingerprint = validate_pptx_bytes(pptx_bytes)
    assert fingerprint["slide_count"] == 16
    # The artifact bytes are what the API hands back from /download — make
    # sure they're a real OOXML zip and not, say, an HTML error page.
    assert pptx_bytes[:2] == b"PK"
    assert len(pptx_bytes) > 5_000


def test_column_validation_error_message_includes_available_columns():
    bad_rows = [{"ASIN": "B001", "Title": "X"}]  # missing revenue
    try:
        parse_brand_export(_csv_bytes(bad_rows), "2025.csv", year=2025)
    except MissingColumnError as exc:
        message = str(exc).lower()
        assert "revenue" in message
        assert "available columns" in message
        assert exc.year == 2025
    else:
        raise AssertionError("Expected MissingColumnError")


def test_column_validation_report_records_detected_mapping():
    parsed = parse_brand_export(_csv_bytes(_source_rows_2025()), "2025.csv", year=2025)
    assert parsed.validation is not None
    assert "asin" in parsed.validation.detected_mapping
    assert "revenue" in parsed.validation.detected_mapping
    assert "asin" in parsed.validation.required_found
    assert parsed.validation.required_missing == []
    assert parsed.year == 2025


def test_generic_manual_upload_aliases_support_external_export_formats():
    rows = [
        {
            "Child ASIN": "b00alias1",
            "Item Name": "Alias Knife",
            "Brand Name": "Acme",
            "Product Category": "Kitchen",
            "Sub Category": "Knives",
            "Ordered Product Sales": "EUR 1.234,50",
            "Quantity Sold": "12",
            "Average Rating": "4.7",
            "Review Count": "31",
            "Image Count": "8",
            "Reseller Count": "2",
            "Buy Box Owner": "Seller A",
            "Best Sellers Rank": "12345",
            "Listing Status": "active",
        }
    ]

    parsed = parse_brand_export(_csv_bytes(rows), "external_export.csv", year=2025)

    row = parsed.rows.iloc[0]
    assert row["asin"] == "B00ALIAS1"
    assert row["brand"] == "Acme"
    assert row["category"] == "Kitchen"
    assert row["subcategory"] == "Knives"
    assert row["revenue"] == 1234.5
    assert row["images"] == 8
    assert row["sellers"] == 2
    assert row["buy_box_owner"] == "Seller A"
    assert row["bsr"] == 12345
    assert row["status"] == "active"


def test_data_completeness_reports_missing_optional_fields_without_blocking_metrics():
    parsed_2024 = parse_brand_export(
        _csv_bytes([{"ASIN": "B001", "Total Revenue": "100"}]),
        "external_2024.csv",
        year=2024,
    )
    parsed_2025 = parse_brand_export(
        _csv_bytes([{"ASIN": "B001", "Total Revenue": "150"}]),
        "external_2025.csv",
        year=2025,
    )

    metrics = calculate_brand_metrics(parsed_2024, parsed_2025, brand_name="Acme")
    completeness = assess_data_completeness(parsed_2024, parsed_2025)

    assert metrics["total_revenue_2025"] == 150
    assert completeness["optional_fields_complete"] is False
    assert "reviews" in completeness["missing_optional_fields_2025"]
    assert "buy_box_owner" in completeness["missing_optional_fields_2025"]


def test_market_share_is_na_without_reliable_market_base():
    parsed_2024 = parse_brand_export(_csv_bytes(_source_rows_2024()), "2024.csv", year=2024)
    parsed_2025 = parse_brand_export(_csv_bytes(_source_rows_2025()), "2025.csv", year=2025)

    metrics = calculate_brand_metrics(parsed_2024, parsed_2025, brand_name="Acme")

    assert metrics["market_share_2025"] is None
    assert metrics["market_analysis"]["status"] == "not_available"
    assert "does not expose reliable revenue" in metrics["market_analysis"]["limitation"]


def test_market_share_uses_broad_external_export_when_brand_revenue_is_present():
    rows_2024 = [
        {"ASIN": "B001", "Brand Name": "Acme", "Product Name": "Knife", "Total Revenue": "100"},
        {"ASIN": "C001", "Brand Name": "Competitor", "Product Name": "Other", "Total Revenue": "300"},
    ]
    rows_2025 = [
        {"ASIN": "B001", "Brand Name": "Acme", "Product Name": "Knife", "Total Revenue": "200"},
        {"ASIN": "C001", "Brand Name": "Competitor", "Product Name": "Other", "Total Revenue": "600"},
    ]
    parsed_2024 = parse_brand_export(_csv_bytes(rows_2024), "market_2024.csv", year=2024)
    parsed_2025 = parse_brand_export(_csv_bytes(rows_2025), "market_2025.csv", year=2025)

    metrics = calculate_brand_metrics(parsed_2024, parsed_2025, brand_name="Acme")

    assert metrics["total_revenue_2025"] == 200
    assert metrics["market_size_2025"] == 800
    assert metrics["market_share_2025"] == 25.0
    assert metrics["market_analysis"]["competitive_brand_distribution"][0]["brand"] == "Competitor"


def test_content_and_seller_metrics_remain_na_when_source_fields_are_absent():
    parsed_2024 = parse_brand_export(_csv_bytes([{"ASIN": "B001", "Total Revenue": "100"}]), "2024.csv", year=2024)
    parsed_2025 = parse_brand_export(_csv_bytes([{"ASIN": "B001", "Total Revenue": "200"}]), "2025.csv", year=2025)

    metrics = calculate_brand_metrics(parsed_2024, parsed_2025, brand_name="Acme")

    assert metrics["content_health"]["asins_missing_bullets"] is None
    assert metrics["seller_buy_box_summary"]["buy_box_owner_available"] is False
    assert metrics["seller_buy_box_summary"]["asins_missing_buy_box_owner"] is None


def test_metric_provenance_includes_source_columns_and_formula():
    parsed_2024 = parse_brand_export(_csv_bytes(_source_rows_2024()), "2024.csv", year=2024)
    parsed_2025 = parse_brand_export(_csv_bytes(_source_rows_2025()), "2025.csv", year=2025)
    provenance = build_metric_provenance(parsed_2024, parsed_2025)

    assert provenance["total_revenue_2025"]["source_years"] == [2025]
    assert any("Total Revenue" in entry for entry in provenance["total_revenue_2025"]["source_columns"])
    assert "sum(revenue)" in provenance["total_revenue_2025"]["formula"]
    assert provenance["yoy_percent"]["source_years"] == [2024, 2025]
    assert "total_revenue_2025" in provenance["yoy_percent"]["formula"]
    assert "rating" in (provenance["weighted_average_rating"]["formula"] + provenance["weighted_average_rating"]["source_columns"][0])


def test_sales_coverage_classifies_complete_and_recoverable_gap():
    complete = classify_sales_year_coverage(
        year=2025,
        row_count=12,
        asin_count=3,
        dates=[date(2025, month, 15) for month in range(1, 13)],
        recoverable_start=date(2024, 5, 20),
        recoverable_end=date(2026, 5, 19),
    )
    assert complete["classification"] == "complete"
    assert complete["missing_months"] == []

    recoverable = classify_sales_year_coverage(
        year=2025,
        row_count=0,
        asin_count=0,
        dates=[],
        recoverable_start=date(2024, 5, 20),
        recoverable_end=date(2026, 5, 19),
    )
    assert recoverable["classification"] == "recoverable_gap"
    assert recoverable["recoverable_window"] == {"start_date": "2025-01-01", "end_date": "2025-12-31"}


def test_sales_coverage_marks_partial_usable_and_unavailable():
    partial = classify_sales_year_coverage(
        year=2024,
        row_count=4,
        asin_count=2,
        dates=[date(2024, 1, 15), date(2024, 2, 15), date(2024, 3, 15), date(2024, 4, 15)],
        recoverable_start=date(2025, 1, 1),
        recoverable_end=date(2026, 5, 19),
    )
    assert partial["classification"] == "partial_but_usable"
    assert "2024-05" in partial["missing_months"]

    unavailable = classify_sales_year_coverage(
        year=2024,
        row_count=0,
        asin_count=0,
        dates=[],
        recoverable_start=date(2025, 1, 1),
        recoverable_end=date(2026, 5, 19),
    )
    assert unavailable["classification"] == "unavailable"


def test_product_fees_estimate_is_marked_estimated_and_actual_overrides():
    estimated_rows = [
        {"ASIN": "B001", "Total Revenue": "100", "Estimated FBA Fees": "3.40"},
    ]
    actual_rows = [
        {"ASIN": "B001", "Total Revenue": "100", "Actual FBA Fees": "2.10", "Estimated FBA Fees": "3.40"},
    ]
    parsed_estimated = parse_brand_export(_csv_bytes(estimated_rows), "estimated.csv", year=2025)
    parsed_actual = parse_brand_export(_csv_bytes(actual_rows), "actual.csv", year=2025)
    parsed_2024 = parse_brand_export(_csv_bytes([{"ASIN": "B001", "Total Revenue": "90"}]), "2024.csv", year=2024)

    estimated_metrics = calculate_brand_metrics(parsed_2024, parsed_estimated, brand_name="Acme")
    actual_metrics = calculate_brand_metrics(parsed_2024, parsed_actual, brand_name="Acme")

    assert estimated_metrics["fee_summary"]["estimated_fba_fees"] == 3.4
    assert estimated_metrics["fee_summary"]["fee_confidence"] == "estimated"
    assert actual_metrics["fee_summary"]["actual_fba_fees"] == 2.1
    assert actual_metrics["fee_summary"]["fee_confidence"] == "actual"
    assert actual_metrics["average_fba_fees"] == 2.1


def test_brand_analytics_search_share_is_proxy_only_not_revenue_share():
    metrics = _metrics()
    registry = build_metric_source_registry(metrics, "internal")

    assert registry["market_revenue_share"]["quality"] == "unavailable"
    assert registry["search_purchase_share"]["quality"] == "unavailable"
    assert "never used as revenue share" in registry["search_purchase_share"]["formula"]


def test_metric_provenance_validation_fails_missing_numeric_family():
    metrics = _metrics()
    provenance = build_metric_provenance(
        parse_brand_export(_csv_bytes(_source_rows_2024()), "2024.csv", year=2024),
        parse_brand_export(_csv_bytes(_source_rows_2025()), "2025.csv", year=2025),
    )
    try:
        validate_metric_provenance_for_deck(metrics, provenance)
    except Exception as exc:
        assert "market_revenue_share" in str(exc)
    else:
        raise AssertionError("Expected provenance validation to fail")


def test_limitation_summary_includes_missing_roles_and_unavailable_market():
    metrics = _metrics()
    limitations = build_limitation_summary(
        metrics,
        {"missing_roles": ["Product Fees: 403 Forbidden"]},
        {"years": {"2024": {"classification": "partial_but_usable", "limitations": ["Partial year"]}}},
    )
    messages = " ".join(item["message"] for item in limitations["items"])
    assert limitations["has_limitations"] is True
    assert "403 Forbidden" in messages
    assert "Partial year" in messages


class _FakeResult:
    def __init__(self, *, scalar=None, row=None):
        self._scalar = scalar
        self._row = row

    def scalar_one(self):
        return self._scalar

    def first(self):
        return self._row


class _FakeDb:
    async def execute(self, statement):
        statement_text = str(statement)
        if "FROM products" in statement_text:
            return _FakeResult(row=SimpleNamespace(asin="B001", sku="SKU1", current_price=10.0))
        return _FakeResult(scalar=1)

    async def flush(self):
        return None


class _PayloadApi:
    def __init__(self, payload=None, exc=None):
        self.payload = payload or {}
        self.exc = exc

    def get_reports(self, **kwargs):
        if self.exc and "GET_BRAND_ANALYTICS" in str(kwargs.get("reportTypes")):
            raise self.exc
        return SimpleNamespace(payload=self.payload)

    def list_financial_event_groups(self, **kwargs):
        return SimpleNamespace(payload=self.payload)

    def get_queries(self, **kwargs):
        return SimpleNamespace(payload=self.payload)

    def get_catalog_item(self, **kwargs):
        return SimpleNamespace(payload=self.payload)

    def get_item_offers(self, **kwargs):
        return SimpleNamespace(payload=self.payload)

    def get_product_fees_estimate_for_asin(self, *args, **kwargs):
        if self.exc:
            raise self.exc
        return SimpleNamespace(payload=self.payload)

    def search_content_documents(self, **kwargs):
        if self.exc:
            raise self.exc
        return SimpleNamespace(payload=self.payload)

    def get_listings_item(self, **kwargs):
        return SimpleNamespace(payload=self.payload)


class _FakeCapabilityClient:
    is_vendor = False
    marketplace = SimpleNamespace(marketplace_id="APJ6JRA9NG5V4")

    def __init__(self, *, product_fees_exc=None, aplus_exc=None, reports_exc=None):
        self.product_fees_exc = product_fees_exc
        self.aplus_exc = aplus_exc
        self.reports_exc = reports_exc

    def _reports_api(self):
        return _PayloadApi({"reports": []}, exc=self.reports_exc)

    def _finances_api(self):
        return _PayloadApi({"groups": []})

    def _data_kiosk_api(self):
        return _PayloadApi({"queries": []})

    def _catalog_api(self):
        return _PayloadApi({"asin": "B001"})

    def _products_api(self):
        return _PayloadApi({"Offers": []})

    def _product_fees_api(self):
        return _PayloadApi({"FeesEstimateResult": {}}, exc=self.product_fees_exc)

    def _aplus_content_api(self):
        return _PayloadApi({"contentMetadataRecords": []}, exc=self.aplus_exc)

    def _listings_api(self):
        return _PayloadApi({"sku": "SKU1"})


def _fake_account():
    return SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        marketplace_id="APJ6JRA9NG5V4",
        marketplace_country="IT",
        account_type=SimpleNamespace(value="seller"),
        seller_id="SELLER1",
    )


def test_capability_detection_all_permissions_available():
    account = _fake_account()
    result = _run(
        detect_brand_analysis_capabilities(
            _FakeDb(),
            account,
            client_factory=lambda _account, _org: _FakeCapabilityClient(),
            force_refresh=True,
            persist=False,
        )
    )
    assert result.capabilities["sales_and_traffic_available"] is True
    assert result.capabilities["product_fees_available"] is True
    assert result.capabilities["aplus_available"] is True
    assert result.missing_roles == []


def test_capability_detection_stores_exact_missing_role_reason():
    account = _fake_account()
    result = _run(
        detect_brand_analysis_capabilities(
            _FakeDb(),
            account,
            client_factory=lambda _account, _org: _FakeCapabilityClient(
                product_fees_exc=Exception("403 Forbidden: Product Fees role missing"),
                aplus_exc=Exception("403 Forbidden: A+ Content role missing"),
                reports_exc=Exception("403 Forbidden: Brand Analytics role missing"),
            ),
            force_refresh=True,
            persist=False,
        )
    )
    assert result.capabilities["product_fees_available"] is False
    assert result.capabilities["aplus_available"] is False
    assert result.capabilities["brand_analytics_available"] is False
    joined = " ".join(result.missing_roles)
    assert "Product Fees role missing" in joined
    assert "A+ Content role missing" in joined
    assert "Brand Analytics role missing" in joined
