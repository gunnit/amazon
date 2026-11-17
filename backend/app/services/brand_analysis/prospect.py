"""Prospect metrics: a brand read from the outside, from estimated-sales exports.

A prospect is a brand Inthezon does not manage yet. Its numbers come from the
2024 and 2025 product exports a user uploads (Helium 10 Black Box / X-Ray
estimates), so the deck describes the brand as a market observer would:
assortment, product areas, concentration, seasonality, who holds the Buy Box,
formats, and the state of each top listing. Everything is deterministic; no
AI call is needed for the deck to make sense.

The Buy Box, sellers, rating, reviews and images columns are a snapshot taken
when the export was made, while revenue and units are yearly estimates.
"""
from __future__ import annotations

import math
import re
from typing import Any, Optional

import pandas as pd

LIGHT_GREEN = "green"
LIGHT_YELLOW = "yellow"
LIGHT_RED = "red"
LIGHT_NA = "na"

# Same bands as the in-app listing-quality score (GET /catalog/listing-quality):
# good from 80, fair from 50.
SCORE_GREEN = 80
SCORE_YELLOW = 50

# Per-check thresholds as (green from, yellow from).
TITLE_LENGTH = (80, 30)
IMAGES = (7, 4)
RATING = (4.3, 4.0)
REVIEWS = (100, 20)
# Points each check is worth out of 100.
CHECK_WEIGHTS = {"title": 25, "images": 25, "rating": 20, "reviews": 15, "buy_box": 15}

OTHER_AREA = "__other__"
AREA_MIN_SHARE = 2.0
AREA_MAX = 9
# Title-derived areas are used when they cover at least this share of revenue.
TITLE_AREA_MIN_COVERAGE = 0.5
SEASONALITY_MIN_COVERAGE = 0.5
SUMMER_MONTHS = (6, 7, 8)
PRICE_BANDS = ((0.0, 5.0), (5.0, 10.0), (10.0, 15.0), (15.0, 20.0), (20.0, 30.0), (30.0, None))
HIGH_VALUE_PER_UNIT = 20.0
LONG_TAIL_REVENUE = 1000.0
TOP_PRODUCTS = 8

# "farma" also catches eFarma, Farmaè, FARMATEAM-style shop names, not only Farmacia.
PHARMACY_PATTERN = re.compile(r"farma|sanitari|pharma|apothe|apotek|drugstore|erborister", re.I)
AMAZON_PATTERN = re.compile(r"^amazon(\.[a-z.]+)?$|^amazon\s+(eu|europe|retail)\b", re.I)
SET_PATTERN = re.compile(
    r"\b(cofanett\w*|kit|gift\s*set|set\s+regalo|confezione\s+regalo|box\s+regalo|idea\s+regalo)\b", re.I
)
_NOT_A_PACK_COUNT = r"(?!\s*(?:pezzi|pz|salviett\w*|ml|g|gr|kg|l|cm)\b)"
MULTIPACK_PATTERNS = (
    re.compile(r"\b(\d{1,2})\s*(?:confezioni|pacchi|flaconi|tubetti|barattoli|bottiglie)\b", re.I),
    re.compile(r"\b(?:confezion[ei]|pacco|pack)\s+(?:da|of)\s+(\d{1,2})\b" + _NOT_A_PACK_COUNT, re.I),
    re.compile(r"\b(\d{1,2})\s*[x×]\s*\d", re.I),
    re.compile(r"\b(\d{1,2})\s*-?\s*pack\b", re.I),
)
MULTIPACK_WORDS = re.compile(r"\b(bipacco|bi-pack|tripacco|multipack|multi-pack)\b", re.I)
_PERIOD = re.compile(r"(\d{4})-(\d{1,2})")


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(result) else result


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text if text and text not in {"-", "nan", "None"} else None


def _share(part: float, total: float) -> float:
    return part / total * 100.0 if total else 0.0


def _rows(df: Optional[pd.DataFrame]) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    return df.to_dict("records")


# Product areas ------------------------------------------------------------------

def _segments(title: Any) -> list[str]:
    return [part.strip() for part in re.split(r"\s+[-–—|]\s+", str(title or "")) if part.strip()]


def _is_area_label(segment: str, brand_norm: str) -> bool:
    letters = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ]", "", segment)
    if len(letters) < 4 or segment != segment.upper() or re.search(r"\d", segment):
        return False
    if len(segment.split()) > 5:
        return False
    norm = _norm(segment)
    return bool(norm) and norm != brand_norm and not (brand_norm and brand_norm in norm)


def _area_key(segment: str) -> str:
    return " ".join(segment.lower().split())


def _area_name(key: str) -> str:
    return key[:1].upper() + key[1:]


def _title_area_labels(rows: list[dict[str, Any]], brand_norm: str) -> set[str]:
    labels: set[str] = set()
    for row in rows:
        for segment in _segments(row.get("product_name"))[1:]:
            if _is_area_label(segment, brand_norm):
                labels.add(_area_key(segment))
    return labels


def _title_area(row: dict[str, Any], labels: set[str]) -> Optional[str]:
    for segment in _segments(row.get("product_name"))[1:]:
        key = _area_key(segment)
        if key in labels:
            return _area_name(key)
    return None


def _subcategory_area(row: dict[str, Any]) -> str:
    from app.services.brand_analysis.deck.format import real_category

    return real_category(row.get("subcategory")) or OTHER_AREA


def _assign_areas(rows25: list[dict[str, Any]], rows24: list[dict[str, Any]], brand_norm: str):
    """Map every ASIN to a product area. Titles first, Amazon subcategory as fallback."""
    labels = _title_area_labels(rows25, brand_norm)
    total = sum(r["revenue"] for r in rows25) or 0.0
    covered = sum(r["revenue"] for r in rows25 if labels and _title_area(r, labels))
    use_titles = bool(labels) and total > 0 and covered / total >= TITLE_AREA_MIN_COVERAGE

    def assign(row: dict[str, Any]) -> str:
        if use_titles:
            return _title_area(row, labels) or _subcategory_area(row)
        return _subcategory_area(row)

    mapping = {r["asin"]: assign(r) for r in rows25}
    for row in rows24:
        mapping.setdefault(row["asin"], assign(row))
    return mapping, ("titles" if use_titles else "subcategory")


def _areas(rows25, rows24, mapping, total25) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for row in rows25:
        if row["revenue"] <= 0:
            continue
        area = stats.setdefault(mapping[row["asin"]], {"revenue": 0.0, "revenue_2024": 0.0, "asins": 0, "top": None})
        area["revenue"] += row["revenue"]
        area["asins"] += 1
        if area["top"] is None or row["revenue"] > area["top"]["revenue"]:
            area["top"] = row
    for row in rows24:
        area = mapping.get(row["asin"])
        if area in stats:
            stats[area]["revenue_2024"] += row["revenue"]

    ranked = sorted(stats.items(), key=lambda item: item[1]["revenue"], reverse=True)
    kept, folded = [], {"revenue": 0.0, "revenue_2024": 0.0, "asins": 0, "top": None}
    for name, area in ranked:
        if name != OTHER_AREA and len(kept) < AREA_MAX and _share(area["revenue"], total25) >= AREA_MIN_SHARE:
            kept.append((name, area))
        else:
            for key in ("revenue", "revenue_2024", "asins"):
                folded[key] += area[key]
    if folded["asins"]:
        kept.append((OTHER_AREA, folded))

    result = []
    for name, area in kept:
        top = area.get("top")
        result.append({
            "name": name,
            "revenue": round(area["revenue"], 2),
            "share": _share(area["revenue"], total25),
            "asins": int(area["asins"]),
            "revenue_2024": round(area["revenue_2024"], 2),
            "yoy_pct": (_share(area["revenue"], area["revenue_2024"]) - 100.0) if area["revenue_2024"] > 0 else None,
            "top_product": top.get("product_name") if top else None,
        })
    return result


# Buy Box and formats ------------------------------------------------------------

def owner_type(owner: Any, brand_norm: str) -> str:
    name = _text(owner)
    if not name:
        return "none"
    norm = _norm(name)
    if brand_norm and (norm == brand_norm or brand_norm in norm or (len(norm) >= 4 and norm in brand_norm)):
        return "brand"
    if AMAZON_PATTERN.match(name):
        return "amazon"
    if PHARMACY_PATTERN.search(name):
        return "pharmacy"
    return "other"


def product_format(row: dict[str, Any]) -> str:
    title = str(row.get("product_name") or "")
    if SET_PATTERN.search(title):
        return "set"
    unit_count = _num(row.get("unit_count"))
    if unit_count is not None and unit_count > 1:
        return "multipack"
    if MULTIPACK_WORDS.search(title):
        return "multipack"
    for pattern in MULTIPACK_PATTERNS:
        for match in pattern.finditer(title):
            if 2 <= int(match.group(1)) <= 12:
                return "multipack"
    return "single"


# Listing traffic lights ---------------------------------------------------------

def _band(value: Optional[float], thresholds: tuple[float, float]) -> str:
    if value is None:
        return LIGHT_NA
    green_from, yellow_from = thresholds
    if value >= green_from:
        return LIGHT_GREEN
    if value >= yellow_from:
        return LIGHT_YELLOW
    return LIGHT_RED


def listing_checks(row: dict[str, Any], buy_box_type: str) -> dict[str, str]:
    title = _text(row.get("product_name"))
    title_length = None if not title or title == row.get("asin") else float(len(title))
    if buy_box_type in ("brand", "amazon"):
        buy_box = LIGHT_GREEN
    elif buy_box_type == "none":
        buy_box = LIGHT_RED
    else:
        buy_box = LIGHT_YELLOW
    return {
        "title": _band(title_length, TITLE_LENGTH),
        "images": _band(_num(row.get("images")), IMAGES),
        "rating": _band(_num(row.get("rating")), RATING),
        "reviews": _band(_num(row.get("reviews")), REVIEWS),
        "buy_box": buy_box,
    }


def listing_score(checks: dict[str, str]) -> Optional[float]:
    points = {LIGHT_GREEN: 1.0, LIGHT_YELLOW: 0.5, LIGHT_RED: 0.0}
    weighted = [(CHECK_WEIGHTS[name], points[light]) for name, light in checks.items() if light in points]
    total = sum(weight for weight, _ in weighted)
    if not total:
        return None
    return sum(weight * value for weight, value in weighted) / total * 100.0


def score_light(score: Optional[float]) -> str:
    if score is None:
        return LIGHT_NA
    if score >= SCORE_GREEN:
        return LIGHT_GREEN
    if score >= SCORE_YELLOW:
        return LIGHT_YELLOW
    return LIGHT_RED


# Entry point --------------------------------------------------------------------

def build_prospect_metrics(
    rows_2024: Optional[pd.DataFrame],
    rows_2025: Optional[pd.DataFrame],
    *,
    brand_name: str,
) -> dict[str, Any]:
    """Deterministic prospect metrics from the parsed 2024 and 2025 export rows."""
    brand_norm = _norm(brand_name)
    rows25 = _rows(rows_2025)
    rows24 = _rows(rows_2024)
    for row in rows25 + rows24:
        row["revenue"] = _num(row.get("revenue")) or 0.0
        row["units"] = _num(row.get("units"))

    selling = sorted((r for r in rows25 if r["revenue"] > 0), key=lambda r: r["revenue"], reverse=True)
    revenue25 = sum(r["revenue"] for r in selling)
    revenue24 = sum(r["revenue"] for r in rows24 if r["revenue"] > 0)
    units25 = sum(r["units"] or 0.0 for r in selling)
    units24 = sum(r["units"] or 0.0 for r in rows24 if r["revenue"] > 0)
    revenue_with_units = sum(r["revenue"] for r in selling if (r["units"] or 0) > 0)
    units_with_revenue = sum(r["units"] for r in selling if (r["units"] or 0) > 0)
    revenue24_by_asin = {r["asin"]: r["revenue"] for r in rows24}

    for row in rows25:
        row["buy_box_type"] = owner_type(row.get("buy_box_owner"), brand_norm)
        row["format"] = product_format(row)

    mapping, area_source = _assign_areas(rows25, rows24, brand_norm)

    return {
        "brand_name": brand_name,
        "revenue_2025": round(revenue25, 2),
        "revenue_2024": round(revenue24, 2),
        "units_2025": round(units25, 2),
        "units_2024": round(units24, 2),
        "yoy_revenue_pct": (_share(revenue25, revenue24) - 100.0) if revenue24 > 0 else None,
        "asins_total_2025": len(rows25),
        "asins_with_sales_2025": len(selling),
        "asins_with_sales_2024": sum(1 for r in rows24 if r["revenue"] > 0),
        "value_per_unit_2025": (revenue_with_units / units_with_revenue) if units_with_revenue else None,
        "manufacturer": _top_text(selling, "manufacturer"),
        "top_categories": _top_categories(selling, revenue25),
        "area_source": area_source,
        "areas": _areas(rows25, rows24, mapping, revenue25),
        "price_bands": _price_bands(selling, revenue25),
        "top_products": _top_products(selling, revenue25, revenue24_by_asin, mapping),
        "pareto": _pareto(selling, revenue25),
        "seasonality": _seasonality(selling, revenue25, mapping),
        "buy_box": _buy_box(rows25, selling, revenue25),
        "formats": _formats(selling, revenue25),
        "listing_health": _listing_health(selling, revenue25),
    }


def _top_text(rows, field: str) -> Optional[str]:
    totals: dict[str, float] = {}
    for row in rows:
        value = _text(row.get(field))
        if value:
            totals[value] = totals.get(value, 0.0) + row["revenue"]
    return max(totals, key=totals.get) if totals else None


def _top_categories(rows, total: float, limit: int = 3) -> list[dict[str, Any]]:
    totals: dict[str, float] = {}
    for row in rows:
        value = _text(row.get("category"))
        if value:
            totals[value] = totals.get(value, 0.0) + row["revenue"]
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [{"name": name, "share": _share(value, total)} for name, value in ranked]


def _price_bands(rows, total: float) -> dict[str, Any]:
    bands = []
    for low, high in PRICE_BANDS:
        members = [
            r for r in rows
            if (r["units"] or 0) > 0 and r["revenue"] / r["units"] >= low
            and (high is None or r["revenue"] / r["units"] < high)
        ]
        revenue = sum(r["revenue"] for r in members)
        bands.append({"low": low, "high": high, "revenue": round(revenue, 2),
                      "share": _share(revenue, total), "asins": len(members)})
    high_value = [r for r in rows if (r["units"] or 0) > 0 and r["revenue"] / r["units"] >= HIGH_VALUE_PER_UNIT]
    high_value_revenue = sum(r["revenue"] for r in high_value)
    packed = sum(r["revenue"] for r in high_value if r.get("format") in ("set", "multipack"))
    core = max(bands, key=lambda band: band["share"]) if bands else None
    return {
        "bands": bands,
        "core_band": core,
        "high_value_share": _share(high_value_revenue, total),
        "high_value_packed_share": _share(packed, high_value_revenue),
    }


def _top_products(rows, total: float, revenue24_by_asin: dict[str, float], mapping) -> list[dict[str, Any]]:
    result = []
    for row in rows[:TOP_PRODUCTS]:
        previous = revenue24_by_asin.get(row["asin"]) or 0.0
        result.append({
            "asin": row["asin"],
            "name": row.get("product_name") or row["asin"],
            "area": mapping.get(row["asin"]),
            "revenue": round(row["revenue"], 2),
            "share": _share(row["revenue"], total),
            "yoy_pct": (_share(row["revenue"], previous) - 100.0) if previous > 0 else None,
            "rating": _num(row.get("rating")),
            "reviews": _num(row.get("reviews")),
            "sellers": _num(row.get("sellers")),
            "price": _num(row.get("price")),
            "buy_box_owner": _text(row.get("buy_box_owner")),
            "buy_box_type": row["buy_box_type"],
            "format": row["format"],
        })
    return result


def _pareto(rows, total: float) -> dict[str, Any]:
    curve, running, to_80 = [], 0.0, None
    for index, row in enumerate(rows, start=1):
        running += row["revenue"]
        share = _share(running, total)
        curve.append(round(share, 2))
        if to_80 is None and share >= 80.0:
            to_80 = index
    tail = [r for r in rows if r["revenue"] < LONG_TAIL_REVENUE]
    return {
        "asins_to_80": to_80,
        "top5_share": _share(sum(r["revenue"] for r in rows[:5]), total),
        "top10_share": _share(sum(r["revenue"] for r in rows[:10]), total),
        "tail_under_1000_count": len(tail),
        "tail_under_1000_share": _share(sum(r["revenue"] for r in tail), total),
        "curve": curve,
    }


def _peak_month(row) -> Optional[int]:
    match = _PERIOD.search(str(row.get("best_sales_period") or ""))
    if not match:
        return None
    month = int(match.group(2))
    return month if 1 <= month <= 12 else None


def _seasonality(rows, total: float, mapping) -> Optional[dict[str, Any]]:
    by_month = [0.0] * 12
    area_total: dict[str, float] = {}
    area_summer: dict[str, float] = {}
    for row in rows:
        month = _peak_month(row)
        if month is None:
            continue
        by_month[month - 1] += row["revenue"]
        area = mapping.get(row["asin"], OTHER_AREA)
        area_total[area] = area_total.get(area, 0.0) + row["revenue"]
        if month in SUMMER_MONTHS:
            area_summer[area] = area_summer.get(area, 0.0) + row["revenue"]
    covered = sum(by_month)
    if not total or covered / total < SEASONALITY_MIN_COVERAGE:
        return None
    summer_areas = sorted(
        (area for area, value in area_summer.items()
         if area != OTHER_AREA and value / area_total[area] >= 0.5),
        key=lambda area: area_summer[area], reverse=True,
    )
    return {
        "by_month": [_share(value, total) for value in by_month],
        "summer_share": _share(sum(by_month[m - 1] for m in SUMMER_MONTHS), total),
        "peak_month": by_month.index(max(by_month)) + 1,
        "coverage": _share(covered, total),
        "summer_areas": summer_areas[:3],
    }


def _buy_box(all_rows, selling, total: float) -> dict[str, Any]:
    if not any(_text(r.get("buy_box_owner")) for r in all_rows):
        return {"available": False}
    by_type = {"brand": 0.0, "pharmacy": 0.0, "other": 0.0, "amazon": 0.0, "none": 0.0}
    for row in selling:
        by_type[row["buy_box_type"]] += row["revenue"]
    sellers: dict[str, dict[str, Any]] = {}
    for row in all_rows:
        if row["buy_box_type"] not in ("pharmacy", "other"):
            continue
        name = _text(row.get("buy_box_owner"))
        entry = sellers.setdefault(name, {"name": name, "type": row["buy_box_type"], "asins": 0, "revenue": 0.0})
        entry["asins"] += 1
        entry["revenue"] += row["revenue"]
    brand_rows = [r for r in all_rows if r["buy_box_type"] == "brand"]
    top_sellers_counts = [_num(r.get("sellers")) for r in selling[:4]]
    top_sellers_counts = [int(c) for c in top_sellers_counts if c is not None]
    seller_counts = [_num(r.get("sellers")) for r in selling]
    seller_counts = [c for c in seller_counts if c is not None]
    ranked = sorted(sellers.values(), key=lambda s: s["revenue"], reverse=True)
    return {
        "available": True,
        "brand_asins": len(brand_rows),
        # Amazon retail holding the Buy Box is the brand's own channel for a vendor brand.
        "amazon_asins": sum(1 for r in all_rows if r["buy_box_type"] == "amazon"),
        "first_party_share": _share(by_type["brand"] + by_type["amazon"], total),
        "brand_asins_fba": sum(1 for r in brand_rows if str(r.get("fulfillment") or "").upper() == "FBA"),
        "third_party_asins": sum(s["asins"] for s in sellers.values()),
        "third_party_sellers": len(sellers),
        "pharmacy_sellers": sum(1 for s in sellers.values() if s["type"] == "pharmacy"),
        "other_sellers": sum(1 for s in sellers.values() if s["type"] == "other"),
        "revenue_share_by_type": {key: _share(value, total) for key, value in by_type.items()},
        "top_sellers": [
            {"name": s["name"], "type": s["type"], "asins": s["asins"],
             "revenue": round(s["revenue"], 2), "share": _share(s["revenue"], total)}
            for s in ranked[:8]
        ],
        "top4_sellers_range": [min(top_sellers_counts), max(top_sellers_counts)] if top_sellers_counts else None,
        "average_sellers": (sum(seller_counts) / len(seller_counts)) if seller_counts else None,
    }


def _formats(rows, total: float) -> dict[str, Any]:
    revenue = {"single": 0.0, "multipack": 0.0, "set": 0.0}
    counts = {"single": 0, "multipack": 0, "set": 0}
    third_party_multipacks = 0
    set_brand_revenue = 0.0
    for row in rows:
        kind = row["format"]
        revenue[kind] += row["revenue"]
        counts[kind] += 1
        if kind == "multipack" and row["buy_box_type"] in ("pharmacy", "other"):
            third_party_multipacks += 1
        if kind == "set" and row["buy_box_type"] == "brand":
            set_brand_revenue += row["revenue"]
    return {
        "single_share": _share(revenue["single"], total),
        "multipack_share": _share(revenue["multipack"], total),
        "set_share": _share(revenue["set"], total),
        "single_asins": counts["single"],
        "multipack_asins": counts["multipack"],
        "set_asins": counts["set"],
        "multipack_third_party_buy_box": third_party_multipacks,
        "set_brand_buy_box_share": _share(set_brand_revenue, revenue["set"]),
    }


def _listing_health(rows, total: float) -> dict[str, Any]:
    items = []
    counts = {LIGHT_GREEN: 0, LIGHT_YELLOW: 0, LIGHT_RED: 0, LIGHT_NA: 0}
    red_revenue = 0.0
    for row in rows:
        checks = listing_checks(row, row["buy_box_type"])
        score = listing_score(checks)
        overall = score_light(score)
        counts[overall] += 1
        if overall == LIGHT_RED:
            red_revenue += row["revenue"]
        title = _text(row.get("product_name"))
        items.append({
            "asin": row["asin"],
            "name": title or row["asin"],
            "revenue": round(row["revenue"], 2),
            "score": round(score, 1) if score is not None else None,
            "overall": overall,
            "checks": checks,
            "values": {
                "title_length": len(title) if title else None,
                "images": _num(row.get("images")),
                "rating": _num(row.get("rating")),
                "reviews": _num(row.get("reviews")),
                "buy_box_owner": _text(row.get("buy_box_owner")),
            },
        })
    return {
        "items": items,
        "counts": counts,
        "red_revenue_share": _share(red_revenue, total),
        "thresholds": {
            "title_length": list(TITLE_LENGTH),
            "images": list(IMAGES),
            "rating": list(RATING),
            "reviews": list(REVIEWS),
            "score": [SCORE_GREEN, SCORE_YELLOW],
            "weights": dict(CHECK_WEIGHTS),
        },
    }
