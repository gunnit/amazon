"""Bulk export/import of the catalogue (R4).

Pure logic: the export is the import template, an upload becomes only the changed
cells, and nothing the file leaves empty is ever erased.
"""
import io

from openpyxl import Workbook, load_workbook

from app.models.product import Product
from app.services.catalog_monitor.bulk_io import (
    EXPORT_COLUMNS,
    LIMITS,
    NewItemRow,
    ParsedRow,
    build_export_workbook,
    parse_new_items,
    parse_upload,
    row_to_change_item,
    validate_new_item,
)
from app.services.catalog_monitor.content import ImageRef, ListingContent

MKT = "APJ6JRA9NG5V4"
LIVE_BULLETS = ["Bullet uno", "Bullet due", "Bullet tre", "Bullet quattro", "Bullet cinque"]


def _val(text):
    return [{"value": text, "language_tag": "it_IT", "marketplace_id": MKT}]


def _content(**kw) -> ListingContent:
    base = dict(
        asin="B0TEST0001",
        marketplace_id=MKT,
        sku="TEST-SKU-001",
        title="Titolo TESTBRAND",
        bullets=list(LIVE_BULLETS),
        description="Descrizione",
        backend_keywords="alfa beta",
        item_highlights="Evidenza",
        images=[
            ImageRef("MAIN", "https://img.test/main.jpg"),
            ImageRef("PT01", "https://img.test/1.jpg"),
            ImageRef("PT02", "https://img.test/2.jpg"),
        ],
        attributes={
            "item_name": _val("Titolo TESTBRAND"),
            "color": _val("Rosso"),
            "number_of_items": [{"value": 3, "marketplace_id": MKT}],
            "item_dimensions": [{"length": {"value": 1, "unit": "centimeters"}}],
            "list_price": [{"value": 10}],
        },
        product_type="PRODUCT",
        parent_asins=["B0TEST0000"],
        variation_theme="COLOR",
    )
    base.update(kw)
    return ListingContent(**base)


def _product(**kw) -> Product:
    base = dict(asin="B0TEST0001", sku="TEST-SKU-001", title="Titolo", main_keyword="kw")
    base.update(kw)
    return Product(**base)


def _xlsx(headers, rows, sheet="Catalogo") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_export_then_parse_round_trip_has_no_changes():
    live = _content()
    data = build_export_workbook([(_product(), live)])
    rows = parse_upload(data, "catalogo.xlsx")
    assert len(rows) == 1 and rows[0].errors == []
    assert rows[0].asin == "B0TEST0001"
    assert row_to_change_item(rows[0], live, MKT) is None


def test_export_layout_and_attribute_columns():
    wb = load_workbook(io.BytesIO(build_export_workbook([(_product(), _content())])))
    assert wb.sheetnames == ["Catalogo", "Istruzioni"]
    ws = wb["Catalogo"]
    headers = [c.value for c in ws[1]]
    assert headers[: len(EXPORT_COLUMNS)] == EXPORT_COLUMNS
    assert "attr:color" in headers and "attr:number_of_items" in headers
    assert "attr:item_dimensions" not in headers  # complex
    assert "attr:list_price" not in headers  # volatile
    assert "attr:item_name" not in headers  # dedicated column
    row = dict(zip(headers, [c.value for c in ws[2]]))
    assert row["bullet_2"] == "Bullet due" and row["image_2"] == "https://img.test/2.jpg"
    assert row["parent_asin"] == "B0TEST0000" and row["main_keyword"] == "kw"
    assert row["attr:number_of_items"] == "3"
    assert ws.freeze_panes == "A2" and ws["A1"].font.b


def test_export_without_content_uses_product():
    ws = load_workbook(io.BytesIO(build_export_workbook([(_product(), None)])))["Catalogo"]
    headers = [c.value for c in ws[1]]
    row = dict(zip(headers, [c.value for c in ws[2]]))
    assert row["asin"] == "B0TEST0001" and row["title"] == "Titolo"


def test_only_bullet_2_keeps_other_live_bullets():
    row = parse_upload(
        _xlsx(["asin", "bullet_2"], [["B0TEST0001", "Nuovo secondo"]]), "u.xlsx"
    )[0]
    item = row_to_change_item(row, _content(), MKT)
    assert item is not None and item.kind == "bulk_update"
    assert [p["path"] for p in item.patches] == ["/attributes/bullet_point"]
    values = [v["value"] for v in item.patches[0]["value"]]
    assert values == ["Bullet uno", "Nuovo secondo", "Bullet tre", "Bullet quattro", "Bullet cinque"]
    assert item.patches[0]["value"][0]["language_tag"] == "it_IT"
    assert item.summary["fields"]["bullets"]["after"][1] == "Nuovo secondo"
    assert item.sku == "TEST-SKU-001" and item.product_type == "PRODUCT"


def test_only_changed_cells_and_whitespace_normalised():
    row = parse_upload(
        _xlsx(
            ["asin", "title", "description", "attr:color", "attr:number_of_items"],
            [["B0TEST0001", "Titolo  TESTBRAND ", "Altra", "Rosso", 3]],
        ),
        "u.xlsx",
    )[0]
    assert row.cells["attr:number_of_items"] == "3"  # not "3.0"
    item = row_to_change_item(row, _content(), MKT)
    assert [p["path"] for p in item.patches] == ["/attributes/product_description"]
    assert list(item.summary["fields"]) == ["description"]


def test_images_merged_per_slot():
    row = parse_upload(
        _xlsx(["asin", "image_1"], [["B0TEST0001", "https://img.test/new.jpg"]]), "u.xlsx"
    )[0]
    item = row_to_change_item(row, _content(), MKT)
    paths = {p["path"]: p for p in item.patches}
    assert paths["/attributes/main_product_image_locator"]["value"][0]["media_location"].endswith("main.jpg")
    assert paths["/attributes/other_product_image_locator_1"]["value"][0]["media_location"].endswith("new.jpg")
    assert paths["/attributes/other_product_image_locator_2"]["value"][0]["media_location"].endswith("2.jpg")


def test_attribute_change_and_main_keyword_ignored():
    row = parse_upload(
        _xlsx(["asin", "attr:color", "main_keyword"], [["B0TEST0001", "Blu", "nuova"]]), "u.xlsx"
    )[0]
    item = row_to_change_item(row, _content(), MKT)
    assert [p["path"] for p in item.patches] == ["/attributes/color"]
    assert item.patches[0]["value"][0]["value"] == "Blu"
    only_kw = parse_upload(_xlsx(["asin", "main_keyword"], [["B0TEST0001", "x"]]), "u.xlsx")[0]
    assert row_to_change_item(only_kw, _content(), MKT) is None


def test_live_none_counts_every_cell_as_change():
    row = parse_upload(
        _xlsx(["sku", "product_type", "title"], [["TEST-SKU-009", "PRODUCT", "Nuovo"]]), "u.xlsx"
    )[0]
    item = row_to_change_item(row, None, MKT)
    assert item.sku == "TEST-SKU-009" and item.product_type == "PRODUCT"
    assert item.patches[0]["path"] == "/attributes/item_name"


def test_backend_keywords_over_250_bytes_is_row_error():
    # 130 two-byte characters = 260 bytes but only 130 characters
    row = parse_upload(_xlsx(["asin", "backend_keywords"], [["B0TEST0001", "è" * 130]]), "u.xlsx")[0]
    assert any("backend_keywords" in e for e in row.errors)
    ok = parse_upload(_xlsx(["asin", "backend_keywords"], [["B0TEST0001", "è" * 125]]), "u.xlsx")[0]
    assert ok.errors == []


def test_title_over_200_is_row_error():
    row = parse_upload(_xlsx(["asin", "title"], [["B0TEST0001", "t" * (LIMITS["title"] + 1)]]), "u.xlsx")[0]
    assert any("title" in e for e in row.errors)


def test_other_row_errors():
    headers = ["asin", "sku", "bullet_3", "description", "item_highlights", "image_1", "main_image_url", "title"]
    rows = [
        [None, None, "b" * 501, "d" * 2001, "h" * 126, "http://x/1.jpg", "ftp://x", "ok"],
        ["B0TEST0001", None, None, None, None, None, None, "ok"],
    ]
    bad, good = parse_upload(_xlsx(headers, rows), "u.xlsx")
    text = " ".join(bad.errors)
    for needle in ("asin", "bullet_3", "description", "item_highlights", "image_1", "main_image_url"):
        assert needle in text
    assert good.errors == [] and good.row_number == 3


def test_csv_semicolon_sniffed_with_bom():
    csv_bytes = "﻿asin;title;bullet_2\nB0TEST0001;Titolo, con virgola;Due\n".encode("utf-8")
    row = parse_upload(csv_bytes, "u.csv")[0]
    assert row.cells["title"] == "Titolo, con virgola" and row.cells["bullet_2"] == "Due"
    comma = parse_upload(b"asin,title\nB0TEST0001,Ciao\n", "u.csv")[0]
    assert comma.cells == {"title": "Ciao"}


def test_xlsx_uses_first_sheet_when_no_catalogo_and_skips_blank_rows():
    data = _xlsx(["asin", "title"], [["B0TEST0001", "A"], [None, None]], sheet="Foglio1")
    rows = parse_upload(data, "u.xlsx")
    assert len(rows) == 1


def test_new_items_nested_attributes_and_required_check():
    csv_bytes = (
        "sku,product_type,item_name,item_dimensions.length,item_dimensions.width\n"
        "TEST-SKU-100,PRODUCT,Nome,10,5\n"
        ",PRODUCT,Senza sku,,\n"
    ).encode()
    good, bad = parse_new_items(csv_bytes, "new.csv")
    assert good.sku == "TEST-SKU-100" and good.product_type == "PRODUCT"
    assert good.attributes == {
        "item_name": "Nome",
        "item_dimensions": {"length": "10", "width": "5"},
    }
    assert bad.errors
    assert validate_new_item(good, None) == []


def test_new_item_missing_required_attribute_reported():
    row = NewItemRow(2, "TEST-SKU-100", "PRODUCT", {"item_name": "Nome"}, [])
    missing = validate_new_item(row, ["item_name", "brand", "item_dimensions"])
    assert len(missing) == 2
    assert any("brand" in m for m in missing) and any("item_dimensions" in m for m in missing)
    assert validate_new_item(row, ["item_name"]) == []
    assert isinstance(ParsedRow(2, None, None, None, {}, []), ParsedRow)
