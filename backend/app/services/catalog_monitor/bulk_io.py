"""Bulk export and import of the catalogue as Excel or CSV (R4).

Pure module: no database, no network. The export is also the import template:

    export  -> one row per product, ``attr:<name>`` columns for simple attributes
    upload  -> ``ParsedRow`` per row, with row errors for values Amazon would refuse
    diff    -> ``row_to_change_item`` keeps only cells that differ from the live
               content, so an upload never erases what the file does not mention

There is deliberately no "clear this field" marker: an empty cell keeps the current
value. ``main_keyword`` belongs to the tool, not to Amazon; the upload route stores it.
New items ("NIS") come from a second file and are checked against the product
type's required attributes by ``validate_new_item``.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from openpyxl import Workbook, load_workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from app.models.product import Product
from app.services.catalog_monitor.changes import ChangeItem, patches_from_content, text_value
from app.services.catalog_monitor.content import (
    VOLATILE_ATTRIBUTES,
    ListingContent,
    attribute_text,
)

BULLET_COUNT = 5
IMAGE_COUNT = 8
EXPORT_COLUMNS: list[str] = (
    ["asin", "sku", "product_type", "title"]
    + [f"bullet_{n}" for n in range(1, BULLET_COUNT + 1)]
    + ["description", "backend_keywords", "item_highlights", "main_keyword", "main_image_url"]
    + [f"image_{n}" for n in range(1, IMAGE_COUNT + 1)]
    + ["parent_asin", "parent_sku", "variation_theme"]
)
LIMITS = {
    "title": 200,
    "bullet": 500,
    "description": 2000,
    "item_highlights": 125,
    "backend_keywords_bytes": 250,
}
ATTR_PREFIX = "attr:"
SHEET = "Catalogo"
INSTRUCTIONS_SHEET = "Istruzioni"
_TEXT_FIELDS = ("title", "description", "backend_keywords", "item_highlights")
_BULLET_COLUMNS = [f"bullet_{n}" for n in range(1, BULLET_COUNT + 1)]
_IMAGE_COLUMNS = ["main_image_url"] + [f"image_{n}" for n in range(1, IMAGE_COUNT + 1)]
_IDENTITY_COLUMNS = ("asin", "sku", "product_type")
# Attributes that have a dedicated column and must not repeat as attr: columns.
_COVERED_ATTRIBUTES = frozenset(
    {"item_name", "bullet_point", "product_description", "generic_keyword", "item_highlights"}
    | {"main_product_image_locator", "swatch_product_image"}
    | {f"other_product_image_locator_{n}" for n in range(1, IMAGE_COUNT + 1)}
)
_SLOT_ATTRIBUTES = ["main_product_image_locator"] + [
    f"other_product_image_locator_{n}" for n in range(1, IMAGE_COUNT + 1)
]
_SIMPLE_VALUE_KEYS = {"value", "language_tag", "marketplace_id"}


# ---- helpers ----


def _norm(text: Optional[str]) -> str:
    return " ".join((text or "").split())


def _slot(variant: str) -> Optional[int]:
    """Image slot of a variant: 0 for MAIN, n for PTnn (1..8)."""
    if variant == "MAIN":
        return 0
    match = re.fullmatch(r"PT(\d+)", variant)
    if match and 1 <= int(match.group(1)) <= IMAGE_COUNT:
        return int(match.group(1))
    return None


def _live_image_slots(live: Optional[ListingContent]) -> list[str]:
    """Live image URLs by slot (MAIN, PT01..PT08), "" where the slot is empty."""
    slots = [""] * (IMAGE_COUNT + 1)
    for ref in (live.images if live else []) or []:
        index = _slot(ref.variant)
        if index is not None:
            slots[index] = ref.url
    return slots


def _simple_attribute(content: ListingContent, name: str) -> Optional[str]:
    """The attribute's single string/number value for the marketplace, else None.

    Complex values (dimensions, units) and multi-valued attributes are not editable
    in one cell, so they stay out of the file instead of being flattened and lost.
    """
    entries = [
        e
        for e in content.attributes.get(name) or []
        if isinstance(e, dict)
        and (not e.get("marketplace_id") or e["marketplace_id"] == content.marketplace_id)
    ]
    if len(entries) != 1 or not set(entries[0]) <= _SIMPLE_VALUE_KEYS:
        return None
    value = entries[0].get("value")
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    return _cell_text(value) or None


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _live_attribute_text(live: Optional[ListingContent], name: str) -> str:
    if live is None:
        return ""
    values = attribute_text(live.attributes, name, live.marketplace_id)
    if values:
        return values[0]
    return _simple_attribute(live, name) or ""


# ---- export ----


def _export_row(product: Product, content: Optional[ListingContent]) -> dict[str, str]:
    row: dict[str, str] = {
        "asin": product.asin or "",
        "sku": product.sku or "",
        "title": product.title or "",
        "main_keyword": product.main_keyword or "",
    }
    if content is not None:
        row["asin"] = content.asin or row["asin"]
        row["sku"] = content.sku or row["sku"]
        row["title"] = content.title or ""
        row["product_type"] = content.product_type or ""
        for n, bullet in enumerate(content.bullets[:BULLET_COUNT], start=1):
            row[f"bullet_{n}"] = bullet
        row["description"] = content.description or ""
        row["backend_keywords"] = content.backend_keywords or ""
        row["item_highlights"] = content.item_highlights or ""
        slots = _live_image_slots(content)
        row["main_image_url"] = slots[0]
        for n in range(1, IMAGE_COUNT + 1):
            row[f"image_{n}"] = slots[n]
        row["parent_asin"] = content.parent_asins[0] if content.parent_asins else ""
        row["variation_theme"] = content.variation_theme or ""
    return row


def export_attribute_names(contents: Iterable[Optional[ListingContent]]) -> set[str]:
    """Simple attributes of these contents that get an ``attr:`` column."""
    names: set[str] = set()
    for content in contents:
        if content is None:
            continue
        for name in content.attributes:
            if name in _COVERED_ATTRIBUTES or name in VOLATILE_ATTRIBUTES:
                continue
            if _simple_attribute(content, name) is not None:
                names.add(name)
    return names


_INSTRUCTIONS = [
    "Come usare questo file",
    "",
    "1. Modificate solo le celle che volete cambiare nel foglio \"Catalogo\" e ricaricate il file.",
    "2. Una cella vuota mantiene il valore attuale della scheda prodotto: il file non cancella mai nulla.",
    "3. Solo le celle diverse dal contenuto attuale diventano variazioni; ogni variazione viene validata da Amazon e approvata da un amministratore prima della scrittura.",
    "4. Per eliminare un contenuto usate Seller Central o Vendor Central: il file non ha un segnale di cancellazione.",
    "",
    "Colonne",
    "asin, sku: identificano la scheda (almeno uno dei due; non modificarli).",
    "product_type: tipo prodotto Amazon; se vuoto si usa quello attuale.",
    "title: titolo, massimo %d caratteri." % LIMITS["title"],
    "bullet_1 ... bullet_5: punti elenco, massimo %d caratteri ciascuno; ogni posizione e' indipendente: cambiando solo bullet_2 gli altri restano come sono." % LIMITS["bullet"],
    "description: descrizione, massimo %d caratteri." % LIMITS["description"],
    "backend_keywords: parole chiave nascoste, massimo %d byte (UTF-8, gli accenti contano doppio)." % LIMITS["backend_keywords_bytes"],
    "item_highlights: evidenze del prodotto, massimo %d caratteri." % LIMITS["item_highlights"],
    "main_keyword: parola chiave principale, salvata solo nello strumento (non va su Amazon).",
    "main_image_url, image_1 ... image_8: indirizzi delle immagini (devono iniziare con https://); main_image_url e' l'immagine principale, image_N e' la posizione PTN.",
    "parent_asin, parent_sku, variation_theme: informazioni sulle variazioni, solo in lettura; le variazioni si gestiscono dalla sezione dedicata.",
    "attr:<nome>: attributi semplici (testo o numero) con il nome Amazon. Gli attributi complessi (dimensioni, offerte, prezzi) non sono nel file.",
]


def text_cell(sheet: Any, value: Any, font: Optional[Font] = None) -> WriteOnlyCell:
    """A write-only cell; a string is stored as text, exactly as given.

    Text from Amazon or an operator that starts with =, +, - or @ would otherwise
    become a formula when the file is opened (formula injection). The value is
    not altered, so an untouched file uploads back without changes.
    """
    cell = WriteOnlyCell(sheet, value=value)
    if isinstance(value, str) and value:
        cell.data_type = "s"
    if font is not None:
        cell.font = font
    return cell


def _column_width(header: str) -> int:
    if header in ("asin", "sku"):
        return 16
    if header.startswith("bullet_") or header in ("title", "description"):
        return 40
    if header.startswith("image_") or header == "main_image_url":
        return 30
    return max(14, min(len(header) + 4, 30))


class CatalogExportWriter:
    """The export workbook, streamed: openpyxl write-only, rows added chunk by chunk.

    Sheet "Catalogo" (one row per product) and "Istruzioni" (Italian). The
    ``attr:`` columns must be known up front (``export_attribute_names``), since
    a streamed sheet cannot go back to its header row.
    """

    def __init__(self, attribute_names: list[str]):
        self.attribute_names = list(attribute_names)
        self.headers = EXPORT_COLUMNS + [f"{ATTR_PREFIX}{name}" for name in self.attribute_names]
        self.workbook = Workbook(write_only=True)
        self.sheet = self.workbook.create_sheet(SHEET)
        for index, header in enumerate(self.headers, start=1):
            self.sheet.column_dimensions[get_column_letter(index)].width = _column_width(header)
        self.sheet.freeze_panes = "A2"
        self.sheet.append([text_cell(self.sheet, h, Font(bold=True)) for h in self.headers])

    def add(self, rows: Iterable[tuple[Any, Optional[ListingContent]]]) -> None:
        """Append one row per (product, live content); the product needs asin, sku,
        title and main_keyword."""
        for product, content in rows:
            data = _export_row(product, content)
            for name in self.attribute_names:
                value = _simple_attribute(content, name) if content is not None else None
                data[f"{ATTR_PREFIX}{name}"] = value or ""
            self.sheet.append([text_cell(self.sheet, data.get(h, "")) for h in self.headers])

    def finish(self) -> bytes:
        """Write the instructions sheet and return the file."""
        _guide_sheet(self.workbook, _INSTRUCTIONS, {1: Font(bold=True, size=14), 8: Font(bold=True)})
        buf = io.BytesIO()
        self.workbook.save(buf)
        return buf.getvalue()


def _guide_sheet(workbook: Workbook, lines: list[str], fonts: dict[int, Font]) -> None:
    """The "Istruzioni" sheet of a write-only workbook: one wrapped line per row."""
    guide = workbook.create_sheet(INSTRUCTIONS_SHEET)
    guide.column_dimensions["A"].width = 120
    for number, line in enumerate(lines, start=1):
        cell = text_cell(guide, line, fonts.get(number))
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        guide.append([cell])


def build_export_workbook(rows: list[tuple[Any, Optional[ListingContent]]]) -> bytes:
    """The whole export in one call, for rows already in memory (small catalogues, tests)."""
    writer = CatalogExportWriter(sorted(export_attribute_names(c for _, c in rows)))
    writer.add(rows)
    return writer.finish()


# ---- upload parsing ----


def _read_table(file_bytes: bytes, filename: str) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    """Header names and (sheet row number, stripped non-empty cells) per data row."""
    if filename.lower().endswith(".csv"):
        text = file_bytes.decode("utf-8-sig")
        first = text.split("\n", 1)[0]
        delimiter = ";" if first.count(";") > first.count(",") else ","
        matrix: list[list[Any]] = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    else:
        wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        ws = wb[SHEET] if SHEET in wb.sheetnames else wb[wb.sheetnames[0]]
        matrix = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
    if not matrix:
        return [], []
    headers = [_cell_text(h).lower() for h in matrix[0]]
    out: list[tuple[int, dict[str, str]]] = []
    for number, raw in enumerate(matrix[1:], start=2):
        cells = {
            h: text
            for h, value in zip(headers, raw)
            if h and (text := _cell_text(value))
        }
        if cells:
            out.append((number, cells))
    return headers, out


@dataclass
class ParsedRow:
    row_number: int
    asin: Optional[str]
    sku: Optional[str]
    product_type: Optional[str]
    cells: dict[str, Any]
    errors: list[str] = field(default_factory=list)


def _row_errors(row: ParsedRow, skip: frozenset[str] = frozenset()) -> list[str]:
    """Identity and limit errors of the row; columns in ``skip`` are not checked."""
    errors: list[str] = []
    cells = {k: v for k, v in row.cells.items() if k not in skip}
    if not row.asin and not row.sku:
        errors.append("asin o sku mancante")
    if len(cells.get("title", "")) > LIMITS["title"]:
        errors.append(f"title supera {LIMITS['title']} caratteri")
    for column in _BULLET_COLUMNS:
        if len(cells.get(column, "")) > LIMITS["bullet"]:
            errors.append(f"{column} supera {LIMITS['bullet']} caratteri")
    if len(cells.get("description", "")) > LIMITS["description"]:
        errors.append(f"description supera {LIMITS['description']} caratteri")
    if len(cells.get("item_highlights", "")) > LIMITS["item_highlights"]:
        errors.append(f"item_highlights supera {LIMITS['item_highlights']} caratteri")
    if len(cells.get("backend_keywords", "").encode("utf-8")) > LIMITS["backend_keywords_bytes"]:
        errors.append(
            f"backend_keywords supera {LIMITS['backend_keywords_bytes']} byte (UTF-8)"
        )
    for column in _IMAGE_COLUMNS:
        if column in cells and not cells[column].startswith("https://"):
            errors.append(f"{column} deve iniziare con https://")
    return errors


def parse_upload(file_bytes: bytes, filename: str) -> list[ParsedRow]:
    """Rows of an edited export; empty cells are omitted, limit violations are row errors."""
    _, table = _read_table(file_bytes, filename)
    rows: list[ParsedRow] = []
    for number, cells in table:
        row = ParsedRow(
            row_number=number,
            asin=cells.get("asin"),
            sku=cells.get("sku"),
            product_type=cells.get("product_type"),
            cells={k: v for k, v in cells.items() if k not in _IDENTITY_COLUMNS},
        )
        row.errors = _row_errors(row)
        rows.append(row)
    return rows


def _unchanged_columns(row: ParsedRow, live: ListingContent) -> frozenset[str]:
    """Text, bullet and image cells equal to the live content: they become no patch."""
    same: set[str] = set()
    cells = row.cells
    for name in _TEXT_FIELDS:
        if name in cells and _norm(cells[name]) == _norm(getattr(live, name, None)):
            same.add(name)
    bullets = list(live.bullets)
    for n, column in enumerate(_BULLET_COLUMNS):
        if column in cells and n < len(bullets) and _norm(cells[column]) == _norm(bullets[n]):
            same.add(column)
    slots = _live_image_slots(live)
    for index, column in enumerate(_IMAGE_COLUMNS):
        if column in cells and cells[column] == slots[index]:
            same.add(column)
    return frozenset(same)


def upload_errors(row: ParsedRow, live: Optional[ListingContent]) -> list[str]:
    """The row's errors against its live content (``row.errors`` without it).

    A cell equal to the live value becomes no patch, so its limits do not apply:
    a listing whose live highlights are already too long can still change a bullet.
    """
    if live is None:
        return list(row.errors)
    return _row_errors(row, _unchanged_columns(row, live))


# ---- upload -> minimal change ----


def row_to_change_item(
    row: ParsedRow, live: Optional[ListingContent], marketplace_id: str
) -> Optional[ChangeItem]:
    """Only the cells that differ from the live content; ``None`` when nothing changes.

    Bullets are merged position by position with the live ones (a row that fills only
    ``bullet_2`` keeps the others, also bullets past the fifth). Images are replaced
    slot by slot: nothing is compacted, moved or deleted. With no live content
    every given cell counts as a change.
    """
    cells = row.cells
    fields: dict[str, Any] = {}
    summary: dict[str, dict] = {}

    def record(name: str, before: Any, after: Any) -> None:
        fields[name] = after
        summary[name] = {"before": before, "after": after}

    for name in _TEXT_FIELDS:
        given = cells.get(name)
        before = (getattr(live, name, None) if live else None) or ""
        if given and _norm(given) != _norm(before):
            record(name, before or None, given)

    live_all = list(live.bullets) if live else []
    live_bullets = [b for b in live_all if b.strip()]
    if any(c in cells for c in _BULLET_COLUMNS):
        head = live_all[:BULLET_COUNT]
        head += [""] * (BULLET_COUNT - len(head))
        for n, column in enumerate(_BULLET_COLUMNS):
            if column in cells:
                head[n] = cells[column]
        # Live bullets past the fifth are kept, unchanged.
        merged = [b for b in head + live_all[BULLET_COUNT:] if b.strip()]
        if [_norm(b) for b in merged] != [_norm(b) for b in live_bullets]:
            record("bullets", live_bullets, merged)

    live_slots = _live_image_slots(live)
    image_slots: dict[str, str] = {}
    image_changes: dict[str, dict] = {}
    for index, column in enumerate(_IMAGE_COLUMNS):
        given = cells.get(column)
        if given and given != live_slots[index]:
            name = _SLOT_ATTRIBUTES[index]
            image_slots[name] = given
            image_changes[name] = {"before": live_slots[index] or None, "after": given}
    if image_slots:
        fields["image_slots"] = image_slots
        summary["image_slots"] = image_changes

    for column, given in cells.items():
        if not column.startswith(ATTR_PREFIX) or len(column) == len(ATTR_PREFIX):
            continue
        name = column[len(ATTR_PREFIX) :]
        before = _live_attribute_text(live, name)
        if _norm(given) != _norm(before):
            fields[f"attribute:{name}"] = text_value(given, marketplace_id)
            summary[f"attribute:{name}"] = {"before": before or None, "after": given}

    if not fields:
        return None
    return ChangeItem(
        asin=row.asin or (live.asin if live else None),
        sku=row.sku or (live.sku if live else None),
        product_type=row.product_type or (live.product_type if live else None),
        kind="bulk_update",
        patches=patches_from_content(fields, marketplace_id),
        summary={"fields": summary},
    )


# ---- new items (NIS) ----


@dataclass
class NewItemRow:
    row_number: int
    sku: str
    product_type: str
    attributes: dict
    errors: list[str] = field(default_factory=list)


def parse_new_items(file_bytes: bytes, filename: str) -> list[NewItemRow]:
    """New items: ``sku``, ``product_type``, then attribute columns (dotted names nest)."""
    _, table = _read_table(file_bytes, filename)
    items: list[NewItemRow] = []
    for number, cells in table:
        attributes: dict = {}
        for column, value in cells.items():
            if column in ("sku", "product_type"):
                continue
            node = attributes
            *parents, leaf = column.split(".")
            for part in parents:
                child = node.setdefault(part, {})
                if not isinstance(child, dict):
                    child = node[part] = {}
                node = child
            node[leaf] = value
        row = NewItemRow(number, cells.get("sku", ""), cells.get("product_type", ""), attributes)
        if not row.sku:
            row.errors.append("sku mancante")
        if not row.product_type:
            row.errors.append("product_type mancante")
        items.append(row)
    return items


def validate_new_item(row: NewItemRow, required: Optional[list[str]]) -> list[str]:
    """Messages for required attributes the row does not fill (unknown schema: none)."""
    return [
        f"attributo obbligatorio mancante: {name}"
        for name in required or []
        if not row.attributes.get(name)
    ]


def wrap_new_item_attributes(attributes: dict, marketplace_id: str) -> dict:
    """Attributes of a new-item row as Listings Items values.

    A text cell becomes a language-tagged value (``text_value``); an attribute with
    dotted columns (``item_weight.value``, ``item_weight.unit``) becomes one object
    carrying those leaves and the marketplace id.
    """
    wrapped: dict = {}
    for name, value in attributes.items():
        if isinstance(value, dict):
            wrapped[name] = [{**value, "marketplace_id": marketplace_id}]
        else:
            wrapped[name] = text_value(str(value), marketplace_id)
    return wrapped


NEW_ITEMS_SHEET = "Nuovi articoli"

_NEW_ITEM_INSTRUCTIONS = [
    "Come usare questo file",
    "",
    "1. Compilate una riga per ogni nuovo articolo nel foglio \"Nuovi articoli\" e caricate il file.",
    "2. sku e product_type sono obbligatori; l'SKU non deve esistere gia' nell'account (per le schede esistenti usate l'aggiornamento massivo).",
    "3. Gli attributi obbligatori del tipo prodotto sono elencati qui sotto: una riga senza uno di essi non viene creata.",
    "4. Per un attributo con piu' campi usate colonne con il punto, per esempio item_weight.value e item_weight.unit.",
    "5. Ogni articolo viene validato da Amazon e approvato da un amministratore prima della creazione.",
    "",
]


def build_new_item_template(
    product_type: str, required: list[str], recommended: list[str]
) -> bytes:
    """Empty new-item sheet: sku, product_type, required attributes, then recommended ones.

    Names come from Amazon's product type definition: written as text, never formulas.
    """
    attributes = list(required) + [name for name in recommended if name not in required]
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(NEW_ITEMS_SHEET)
    headers = ["sku", "product_type"] + attributes
    for index, header in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(index)].width = max(16, min(len(header) + 4, 40))
    ws.freeze_panes = "A2"
    ws.append([text_cell(ws, header, Font(bold=True)) for header in headers])
    lines = list(_NEW_ITEM_INSTRUCTIONS)
    lines.append(f"Tipo prodotto: {product_type}")
    lines.append("Attributi obbligatori: " + (", ".join(required) or "nessuno"))
    lines.append("Attributi consigliati: " + (", ".join(n for n in recommended if n not in required) or "nessuno"))
    _guide_sheet(wb, lines, {1: Font(bold=True, size=14)})
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
