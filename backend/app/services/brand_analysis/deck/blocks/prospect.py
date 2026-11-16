"""Prospect deck: a brand read from estimated-sales exports, one finding per slide.

Used for analyses built from uploaded yearly exports (Helium 10 Black Box /
X-Ray), and modelled on the scenario deck Inthezon prepares for new-business
calls: each slide states its finding in the title, shows one chart, and lists
what emerges. Every number comes from ``metrics["prospect"]``
(``app.services.brand_analysis.prospect``); the wording is deterministic, so
the deck reads the same with or without the AI provider.
"""
from __future__ import annotations

import re
import struct
from typing import Any, Optional

from pptx.util import Pt

from app.services.brand_analysis.deck import charts
from app.services.brand_analysis.deck import format as fmt
from app.services.brand_analysis.deck.block import BaseBlock, BlockResult, Section
from app.services.brand_analysis.deck.theme import DeckTheme
from app.services.brand_analysis.prospect import (
    CHECK_WEIGHTS,
    IMAGES,
    LIGHT_GREEN,
    LIGHT_NA,
    LIGHT_RED,
    LIGHT_YELLOW,
    OTHER_AREA,
    RATING,
    REVIEWS,
    SCORE_GREEN,
    SCORE_YELLOW,
    SUMMER_MONTHS,
    TITLE_LENGTH,
)

M = DeckTheme.MARGIN
CW = DeckTheme.content_w()
PANEL_X = 8.95
PANEL_W = DeckTheme.SLIDE_W - M - PANEL_X
LEFT_W = PANEL_X - M - 0.3
BODY_Y = 2.0
BODY_BOTTOM = 6.75

LIGHT_COLORS = {
    LIGHT_GREEN: (58, 125, 68),
    LIGHT_YELLOW: (232, 168, 20),
    LIGHT_RED: (204, 1, 0),
    LIGHT_NA: (205, 205, 205),
}
THIRD_PARTY = DeckTheme.NEUTRAL_BAR
TYPE_COLORS = {
    "brand": DeckTheme.BRAND_PRIMARY,
    "pharmacy": DeckTheme.STEEL_BLUE,
    "other": DeckTheme.NEUTRAL_BAR,
    "amazon": DeckTheme.GOLD,
    "none": DeckTheme.HAIRLINE,
}

STRINGS: dict[str, dict[str, Any]] = {
    "it": {
        "what_emerges": "COSA EMERGE",
        "work_space": "SPAZIO DI LAVORO",
        "other_area": "Altro",
        "months": ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"],
        "months_long": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
                        "agosto", "settembre", "ottobre", "novembre", "dicembre"],
        "million": "€ {v} mln",
        "cover_eyebrow": "ANALISI DI SCENARIO · AMAZON.IT",
        "cover_title": "{brand} su Amazon.it",
        "cover_subtitle": "Posizionamento, assortimento e offerta osservata",
        "cover_meta": "Vendite stimate 2024 e 2025 · fonte: export di prodotto caricati",
        "cover_footer": "Inthezon · Libera Brand Building Group",
        "eyebrow_overview": "IL BRAND",
        "eyebrow_sales": "VENDITE",
        "eyebrow_areas": "AREE DI PRODOTTO",
        "eyebrow_top": "PRODOTTI PRINCIPALI",
        "eyebrow_concentration": "CONCENTRAZIONE",
        "eyebrow_seasonality": "STAGIONALITÀ",
        "eyebrow_buy_box": "BUY BOX E VENDITORI",
        "eyebrow_formats": "FORMATI",
        "eyebrow_yoy": "ANDAMENTO 2024 → 2025",
        "eyebrow_listing": "STATO DEI LISTING",
        "eyebrow_synthesis": "SINTESI",
        "eyebrow_method": "METODOLOGIA",
        "overview_title": "{brand}: {asins} ASIN con vendite stimate nel 2025, in {areas} aree di prodotto",
        "kpi_revenue": "Vendite stimate 2025",
        "kpi_yoy": "Variazione sul 2024",
        "kpi_asins": "ASIN con vendite",
        "kpi_brand_bb": "Vendite con Buy Box del marchio",
        "card_who": "Chi produce",
        "card_where": "Dove si vende",
        "card_growth": "Come cresce",
        "overview_areas": "Prime aree di prodotto: {areas}.",
        "who_manufacturer": "Produttore indicato nelle schede: {name}.",
        "who_categories": "Categorie Amazon principali: {cats}.",
        "where_brand": "Il {share} delle vendite stimate passa da schede con Buy Box del marchio.",
        "where_third": "{sellers} venditori terzi detengono la Buy Box su {asins} ASIN.",
        "where_missing": "L'export non riporta la Buy Box.",
        "growth_total": "Vendite stimate da {a} a {b} ({pct}).",
        "growth_area": "Area più dinamica: {area} ({pct}).",
        "growth_missing": "Manca l'export 2024 per il confronto.",
        "sales_title": "Circa {rev} di vendite stimate nel 2025, con un valore medio per unità di {vpu}",
        "kpi_units": "Unità stimate 2025",
        "kpi_vpu": "Valore medio per unità",
        "chart_bands": "Quota delle vendite stimate per valore per unità",
        "band_open": "€ {low}+",
        "band": "€ {low}–{high}",
        "sales_core": "La fascia {band} per unità concentra il {share} delle vendite stimate ({n} ASIN).",
        "sales_high": "Il {share} delle vendite viene da prodotti sopra € 20 per unità",
        "sales_high_packed": ", per il {share} cofanetti o confezioni multiple.",
        "sales_units": "Unità stimate: {units} nel 2025 ({pct} sul 2024).",
        "areas_title_two": "{a} e {b} sostengono il {share}% delle vendite stimate",
        "areas_title_one": "{a} sostiene il {share}% delle vendite stimate",
        "areas_top": "{a}: {sa} delle vendite con {na} ASIN; {b}: {sb} con {nb} ASIN.",
        "areas_long_tail": "{area} conta {n} ASIN con vendite ma pesa il {share}: molte referenze, ciascuna con volumi contenuti.",
        "areas_growth": "L'area che cresce di più sul 2024 è {area} ({pct}).",
        "areas_other": "«Altro» raccoglie {n} ASIN di aree minori ({share}).",
        "source_areas_titles": "Vendite stimate · Amazon.it · 2025 · aree definite dai titoli degli ASIN",
        "source_areas_subcategory": "Vendite stimate · Amazon.it · 2025 · aree = sottocategorie Amazon",
        "top_title": "I primi {n} ASIN valgono il {share}% delle vendite stimate",
        "top_title_rating": ", con valutazioni tra {low} e {high}",
        "legend_brand": "Buy Box del marchio",
        "legend_third": "Buy Box di un venditore terzo",
        "top_first": "{name} pesa da solo il {share} delle vendite stimate",
        "top_first_reviews": ", con {n} recensioni.",
        "top_brand_bb": "{k} ASIN su {n} hanno la Buy Box del marchio.",
        "top_exception": "Fa eccezione {name}, con Buy Box di {owner}.",
        "top_growth": "Crescita più forte tra i primi: {name} ({pct}).",
        "source_snapshot": "Vendite stimate Amazon.it 2025 · prezzo, valutazioni e Buy Box: istantanea al momento dell'export",
        "conc_title": "{n80} ASIN su {n} raggiungono l'80% delle vendite stimate",
        "conc_title_tail": "; la lunga coda amplia la gamma",
        "kpi_to_80": "ASIN per l'80% delle vendite",
        "kpi_tail": "ASIN sotto € 1.000 ciascuno",
        "conc_mark": "{n} ASIN",
        "conc_axis": "ASIN ordinati per vendite stimate",
        "conc_top": "I primi cinque ASIN valgono il {top5}, i primi dieci il {top10}.",
        "conc_tail": "{n} ASIN vendono meno di € 1.000 ciascuno e insieme pesano il {share}.",
        "conc_level_high": "La concentrazione è molto marcata: pochi prodotti reggono il portafoglio.",
        "conc_level_mid": "La concentrazione è marcata ma non estrema.",
        "conc_level_low": "Le vendite sono distribuite su molti prodotti.",
        "source_sales": "Vendite stimate · Amazon.it · 2025 · ASIN con vendite ordinati per vendite",
        "season_title_summer": "Il {share}% delle vendite stimate viene da prodotti con picco estivo",
        "season_title_peak": "Le vendite stimate si concentrano su prodotti con picco a {month}",
        "season_peak": "Mese di picco con più valore: {month}.",
        "season_areas": "Picco estivo per {areas}.",
        "season_rest": "Il resto del portafoglio ha picchi distribuiti nell'anno, legati a bisogni non stagionali.",
        "source_season": "Vendite stimate Amazon.it 2025 · ASIN raggruppati per mese di picco storico (Best sales period)",
        "bb_title": "Buy Box del marchio su {b} ASIN; altri {k} ASIN fanno capo a {s} venditori terzi",
        "bb_types": {"brand": "Marchio", "pharmacy": "Farmacie e parafarmacie", "other": "Altri rivenditori",
                     "amazon": "Amazon", "none": "Nessuna Buy Box"},
        "bb_col_seller": "Venditore", "bb_col_type": "Tipo", "bb_col_asins": "ASIN", "bb_col_share": "Vendite",
        "bb_type_short": {"pharmacy": "Farmacia", "other": "Rivenditore"},
        "bb_brand": "Le schede con Buy Box del marchio valgono il {share} delle vendite stimate",
        "bb_brand_fba_all": ", tutte in FBA.",
        "bb_brand_fba": "; {n} sono in FBA.",
        "bb_sellers": "Venditori terzi: {pharm} farmacie e parafarmacie, {other} altri rivenditori.",
        "bb_range": "Sui quattro ASIN principali sono attivi da {a} a {b} venditori.",
        "formats_title_mp": "I multipack valgono il {share}% delle vendite stimate; {k} su {n} hanno Buy Box di terzi",
        "formats_title_set": "Cofanetti e kit valgono il {share}% delle vendite stimate",
        "format_labels": ["Formato singolo", "Multipack", "Cofanetti e kit"],
        "formats_single": "Il formato singolo vale il {share} delle vendite stimate ({n} ASIN).",
        "formats_sets": "{n} cofanetti e kit valgono il {share}; il marchio ne detiene la Buy Box per il {brand} del valore.",
        "formats_gap": "Multipack e cofanetti sono un'area in cui il marchio presidia poco l'offerta.",
        "source_formats": "Vendite stimate Amazon.it 2025 · formati riconosciuti dal titolo e dal numero di unità",
        "yoy_title": "Vendite stimate da {a} a {b} ({pct}) tra 2024 e 2025",
        "yoy_col_area": "Area", "yoy_col_change": "Variazione",
        "yoy_up_down": "Cresce di più {up} ({up_pct}); in calo {down} ({down_pct}).",
        "yoy_up": "Cresce di più {up} ({up_pct}).",
        "source_yoy": "Vendite stimate Amazon.it 2024 e 2025 dagli export caricati",
        "listing_title": "Stato dei listing: {g} in verde, {y} in giallo e {r} in rosso sui {n} ASIN con vendite",
        "listing_cols": ["Prodotto", "Vendite 2025", "Titolo", "Immagini", "Valutazione", "Recensioni", "Buy Box", "Punteggio"],
        "listing_more": "Mostrati i primi {shown} ASIN per vendite; l'elenco completo è nel tool.",
        "listing_criteria": (
            "Criteri: titolo verde da {t1} caratteri, giallo da {t2}; immagini verde da {i1}, giallo da {i2}; "
            "valutazione verde da {r1}, giallo da {r2}; recensioni verde da {v1}, giallo da {v2}; "
            "Buy Box del marchio o di Amazon verde, di terzi giallo, assente rosso. "
            "Punteggio pesato su 100 (titolo {wt}, immagini {wi}, valutazione {wr}, recensioni {wv}, Buy Box {wb}): "
            "verde da {s1}, giallo da {s2}. Grigio: dato assente nell'export."
        ),
        "synth_title": "In sintesi: il {share}% delle vendite stimate in due aree",
        "synth_title_bb": ", il {share}% su schede con Buy Box di terzi",
        "synth_conc_label": "delle vendite stimate in {a} e {b}",
        "synth_conc_detail": "{n80} ASIN su {n} raggiungono l'80% delle vendite.",
        "synth_conc_work": "Coerenza di contenuti, varianti e formati sulle schede principali.",
        "synth_season_label": "con picco tra giugno e agosto",
        "synth_season_detail": "Picco estivo per {areas}.",
        "synth_season_work": "Presidio di ricerca e offerta nella finestra di domanda stagionale.",
        "synth_bb_label": "delle vendite con Buy Box di terzi",
        "synth_bb_detail": "{s} venditori terzi su {k} ASIN.",
        "synth_bb_work": "Presidio della Buy Box sulle schede gestite da rivenditori.",
        "synth_listing_label": "schede in rosso, {y} in giallo",
        "synth_listing_detail": "Su {n} ASIN con vendite.",
        "synth_listing_work": "Priorità a immagini, recensioni e titoli delle schede in rosso e giallo.",
        "synth_close": "Per {brand} il margine di lavoro sta soprattutto attorno ai {n80} ASIN che fanno l'80% delle vendite: schede, formati e venditori.",
        "method_title": "Metodologia e fonti",
        "method_sources": "Fonti",
        "method_definitions": "Definizioni",
        "method_source_items": [
            "Vendite e unità: stime annuali 2024 e 2025 dagli export di prodotto caricati (ad esempio Helium 10).",
            "Buy Box, venditori, prezzo, valutazioni, recensioni e immagini: istantanea al momento dell'export.",
            "Valori stimati: non sono dati di vendita del marchio.",
        ],
        "method_definition_items": [
            "Aree di prodotto: dai segmenti in maiuscolo dei titoli degli ASIN; dove mancano, sottocategoria Amazon.",
            "Multipack: titoli con più confezioni o numero di unità superiore a uno. Cofanetti e kit: titoli con cofanetto, kit o set regalo.",
            "Stagionalità: mese di picco storico registrato per ciascun ASIN.",
            "Venditori farmacia: nomi che contengono farma, sanitaria o pharma.",
            "Semafori: criteri riportati nella slide sullo stato dei listing.",
        ],
    },
    "en": {
        "what_emerges": "WHAT EMERGES",
        "work_space": "WHERE TO WORK",
        "other_area": "Other",
        "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        "months_long": ["January", "February", "March", "April", "May", "June", "July", "August",
                        "September", "October", "November", "December"],
        "million": "€{v}M",
        "cover_eyebrow": "SCENARIO ANALYSIS · AMAZON",
        "cover_title": "{brand} on Amazon",
        "cover_subtitle": "Positioning, assortment and observed offer",
        "cover_meta": "Estimated sales 2024 and 2025 · source: uploaded product exports",
        "cover_footer": "Inthezon · Libera Brand Building Group",
        "eyebrow_overview": "THE BRAND",
        "eyebrow_sales": "SALES",
        "eyebrow_areas": "PRODUCT AREAS",
        "eyebrow_top": "TOP PRODUCTS",
        "eyebrow_concentration": "CONCENTRATION",
        "eyebrow_seasonality": "SEASONALITY",
        "eyebrow_buy_box": "BUY BOX AND SELLERS",
        "eyebrow_formats": "FORMATS",
        "eyebrow_yoy": "2024 → 2025",
        "eyebrow_listing": "LISTING STATUS",
        "eyebrow_synthesis": "SYNTHESIS",
        "eyebrow_method": "METHODOLOGY",
        "overview_title": "{brand}: {asins} ASINs with estimated sales in 2025, across {areas} product areas",
        "kpi_revenue": "Estimated sales 2025",
        "kpi_yoy": "Change vs 2024",
        "kpi_asins": "ASINs with sales",
        "kpi_brand_bb": "Sales with the brand's Buy Box",
        "card_who": "Who makes it",
        "card_where": "Where it sells",
        "card_growth": "How it grows",
        "overview_areas": "Leading product areas: {areas}.",
        "who_manufacturer": "Manufacturer on the listings: {name}.",
        "who_categories": "Main Amazon categories: {cats}.",
        "where_brand": "{share} of estimated sales comes from listings with the brand's Buy Box.",
        "where_third": "{sellers} third-party sellers hold the Buy Box on {asins} ASINs.",
        "where_missing": "The export carries no Buy Box data.",
        "growth_total": "Estimated sales moved from {a} to {b} ({pct}).",
        "growth_area": "Fastest-moving area: {area} ({pct}).",
        "growth_missing": "No 2024 export to compare against.",
        "sales_title": "About {rev} of estimated sales in 2025, at an average {vpu} per unit",
        "kpi_units": "Estimated units 2025",
        "kpi_vpu": "Average value per unit",
        "chart_bands": "Share of estimated sales by value per unit",
        "band_open": "€{low}+",
        "band": "€{low}–{high}",
        "sales_core": "The {band} per-unit band carries {share} of estimated sales ({n} ASINs).",
        "sales_high": "{share} of sales comes from products above €20 per unit",
        "sales_high_packed": ", {share} of it gift sets or multipacks.",
        "sales_units": "Estimated units: {units} in 2025 ({pct} vs 2024).",
        "areas_title_two": "{a} and {b} carry {share}% of estimated sales",
        "areas_title_one": "{a} carries {share}% of estimated sales",
        "areas_top": "{a}: {sa} of sales from {na} ASINs; {b}: {sb} from {nb} ASINs.",
        "areas_long_tail": "{area} has {n} ASINs with sales but weighs {share}: many references, each with small volumes.",
        "areas_growth": "The fastest-growing area vs 2024 is {area} ({pct}).",
        "areas_other": "“Other” groups {n} ASINs from smaller areas ({share}).",
        "source_areas_titles": "Estimated sales · Amazon · 2025 · areas defined from ASIN titles",
        "source_areas_subcategory": "Estimated sales · Amazon · 2025 · areas = Amazon subcategories",
        "top_title": "The top {n} ASINs make {share}% of estimated sales",
        "top_title_rating": ", rated between {low} and {high}",
        "legend_brand": "Brand's Buy Box",
        "legend_third": "Third-party Buy Box",
        "top_first": "{name} alone makes {share} of estimated sales",
        "top_first_reviews": ", with {n} reviews.",
        "top_brand_bb": "{k} of {n} ASINs have the brand's Buy Box.",
        "top_exception": "The exception is {name}, with the Buy Box held by {owner}.",
        "top_growth": "Strongest growth among the top: {name} ({pct}).",
        "source_snapshot": "Estimated Amazon sales 2025 · price, ratings and Buy Box: snapshot at export time",
        "conc_title": "{n80} of {n} ASINs reach 80% of estimated sales",
        "conc_title_tail": "; the long tail widens the range",
        "kpi_to_80": "ASINs for 80% of sales",
        "kpi_tail": "ASINs under €1,000 each",
        "conc_mark": "{n} ASINs",
        "conc_axis": "ASINs ranked by estimated sales",
        "conc_top": "The top five ASINs make {top5}, the top ten {top10}.",
        "conc_tail": "{n} ASINs sell under €1,000 each and together weigh {share}.",
        "conc_level_high": "Concentration is very high: a few products carry the portfolio.",
        "conc_level_mid": "Concentration is marked but not extreme.",
        "conc_level_low": "Sales are spread across many products.",
        "source_sales": "Estimated sales · Amazon · 2025 · ASINs with sales ranked by sales",
        "season_title_summer": "{share}% of estimated sales comes from products peaking in summer",
        "season_title_peak": "Estimated sales concentrate on products peaking in {month}",
        "season_peak": "Peak month with the most value: {month}.",
        "season_areas": "Summer peak for {areas}.",
        "season_rest": "The rest of the portfolio peaks across the year, on non-seasonal needs.",
        "source_season": "Estimated Amazon sales 2025 · ASINs grouped by historical peak month (Best sales period)",
        "bb_title": "Brand's Buy Box on {b} ASINs; another {k} ASINs belong to {s} third-party sellers",
        "bb_types": {"brand": "Brand", "pharmacy": "Pharmacies", "other": "Other resellers",
                     "amazon": "Amazon", "none": "No Buy Box"},
        "bb_col_seller": "Seller", "bb_col_type": "Type", "bb_col_asins": "ASINs", "bb_col_share": "Sales",
        "bb_type_short": {"pharmacy": "Pharmacy", "other": "Reseller"},
        "bb_brand": "Listings with the brand's Buy Box make {share} of estimated sales",
        "bb_brand_fba_all": ", all fulfilled by Amazon.",
        "bb_brand_fba": "; {n} are fulfilled by Amazon.",
        "bb_sellers": "Third-party sellers: {pharm} pharmacies, {other} other resellers.",
        "bb_range": "{a} to {b} sellers are active on the four main ASINs.",
        "formats_title_mp": "Multipacks make {share}% of estimated sales; {k} of {n} have a third-party Buy Box",
        "formats_title_set": "Gift sets and kits make {share}% of estimated sales",
        "format_labels": ["Single unit", "Multipack", "Gift sets and kits"],
        "formats_single": "Single units make {share} of estimated sales ({n} ASINs).",
        "formats_sets": "{n} gift sets and kits make {share}; the brand holds their Buy Box for {brand} of the value.",
        "formats_gap": "Multipacks and gift sets are where the brand controls the offer least.",
        "source_formats": "Estimated Amazon sales 2025 · formats read from the title and the unit count",
        "yoy_title": "Estimated sales from {a} to {b} ({pct}) between 2024 and 2025",
        "yoy_col_area": "Area", "yoy_col_change": "Change",
        "yoy_up_down": "Growing most: {up} ({up_pct}); declining: {down} ({down_pct}).",
        "yoy_up": "Growing most: {up} ({up_pct}).",
        "source_yoy": "Estimated Amazon sales 2024 and 2025 from the uploaded exports",
        "listing_title": "Listing status: {g} green, {y} yellow and {r} red across {n} ASINs with sales",
        "listing_cols": ["Product", "Sales 2025", "Title", "Images", "Rating", "Reviews", "Buy Box", "Score"],
        "listing_more": "Showing the top {shown} ASINs by sales; the full list is in the tool.",
        "listing_criteria": (
            "Criteria: title green from {t1} characters, yellow from {t2}; images green from {i1}, yellow from {i2}; "
            "rating green from {r1}, yellow from {r2}; reviews green from {v1}, yellow from {v2}; "
            "brand or Amazon Buy Box green, third-party yellow, none red. "
            "Weighted score out of 100 (title {wt}, images {wi}, rating {wr}, reviews {wv}, Buy Box {wb}): "
            "green from {s1}, yellow from {s2}. Grey: not in the export."
        ),
        "synth_title": "In short: {share}% of estimated sales in two areas",
        "synth_title_bb": ", {share}% on listings with a third-party Buy Box",
        "synth_conc_label": "of estimated sales in {a} and {b}",
        "synth_conc_detail": "{n80} of {n} ASINs reach 80% of sales.",
        "synth_conc_work": "Consistent content, variants and formats on the main listings.",
        "synth_season_label": "peaking between June and August",
        "synth_season_detail": "Summer peak for {areas}.",
        "synth_season_work": "Own search and offer during the seasonal demand window.",
        "synth_bb_label": "of sales with a third-party Buy Box",
        "synth_bb_detail": "{s} third-party sellers on {k} ASINs.",
        "synth_bb_work": "Win back the Buy Box on reseller-held listings.",
        "synth_listing_label": "red listings, {y} yellow",
        "synth_listing_detail": "Across {n} ASINs with sales.",
        "synth_listing_work": "Images, reviews and titles first on red and yellow listings.",
        "synth_close": "For {brand}, the room to work sits mostly around the {n80} ASINs that make 80% of sales: listings, formats and sellers.",
        "method_title": "Methodology and sources",
        "method_sources": "Sources",
        "method_definitions": "Definitions",
        "method_source_items": [
            "Sales and units: 2024 and 2025 yearly estimates from the uploaded product exports (e.g. Helium 10).",
            "Buy Box, sellers, price, ratings, reviews and images: snapshot at export time.",
            "Estimated values: not the brand's own sales data.",
        ],
        "method_definition_items": [
            "Product areas: from the upper-case segments of ASIN titles; where missing, the Amazon subcategory.",
            "Multipacks: titles with several packs or a unit count above one. Gift sets and kits: titles with gift box, kit or gift set.",
            "Seasonality: each ASIN's historical peak month.",
            "Pharmacy sellers: names containing farma, sanitaria or pharma.",
            "Traffic lights: criteria on the listing status slide.",
        ],
    },
}


# Shared helpers -----------------------------------------------------------------

def _s(ctx, key: str) -> Any:
    table = STRINGS["it" if ctx.language == "it" else "en"]
    return table.get(key, STRINGS["en"].get(key, key))


def _p(ctx) -> dict[str, Any]:
    return ctx.metrics.get("prospect") or {}


def _brand(ctx) -> str:
    return str(_p(ctx).get("brand_name") or ctx.metrics.get("brand_name") or ctx.brand)


def _area(ctx, name: Optional[str]) -> str:
    return _s(ctx, "other_area") if name in (None, OTHER_AREA) else str(name)


def _pct0(value) -> str:
    return f"{round(float(value or 0)):d}"


def _money_compact(ctx, value) -> str:
    number = float(value or 0)
    if number >= 1_000_000:
        compact = f"{number / 1_000_000:.1f}"
        if ctx.language == "it":
            compact = compact.replace(".", ",")
        return _s(ctx, "million").format(v=compact)
    return ctx.fmt.currency(number)


def _short(name: Any, brand: str, limit: int = 40) -> str:
    """Product name without the brand prefix, cut at a " - " segment boundary
    ("Detergente Intimo MIODERM - 240ml") rather than mid-word."""
    label = fmt.product_label(name, brand, 1000)
    parts = [part for part in re.split(r"\s+[-–—|]\s+", label) if part]
    if not parts:
        return fmt.truncate(label, limit)
    short = parts[0]
    for part in parts[1:]:
        if len(short) + 3 + len(part) > limit:
            break
        short = f"{short} - {part}"
    return fmt.truncate(short, limit)


def _rating(ctx, value) -> str:
    return ctx.fmt.number(value, 1)


def _png_size(png: bytes) -> tuple[int, int]:
    return struct.unpack(">II", png[16:24])


def _picture(deck, slide, png: bytes, x: float, y: float, max_w: float, max_h: float) -> None:
    """Place a chart at its own aspect ratio inside the box, never stretched."""
    width, height = _png_size(png)
    ratio = width / height if height else 1.0
    w, h = max_w, max_w / ratio
    if h > max_h:
        h, w = max_h, max_h * ratio
    deck.picture(slide, png, x, y, w, h)


def _frame(ctx, deck, page: int, eyebrow_key: str, headline: str, source: str = ""):
    slide = deck.blank_slide()
    deck.chrome(slide, page)
    deck.text(slide, M, 0.58, CW, 0.26, _s(ctx, eyebrow_key), size=11, bold=True,
              color=DeckTheme.BRAND_PRIMARY)
    size = 26 if len(headline) <= 72 else 22
    deck.text(slide, M, 0.88, CW, 1.0, headline, size=size, bold=True, color=DeckTheme.INK)
    if source:
        deck.text(slide, M, 6.9, CW - 0.9, 0.24, source, size=9, color=DeckTheme.MUTED)
    return slide


def _emerges(ctx, deck, slide, bullets: list[str], *, x: float = PANEL_X, y: float = BODY_Y,
             w: float = PANEL_W, h: float = BODY_BOTTOM - BODY_Y) -> None:
    deck.rect(slide, x, y, w, h, DeckTheme.SURFACE, line=DeckTheme.HAIRLINE)
    deck.rect(slide, x, y, 0.07, h, DeckTheme.BRAND_PRIMARY)
    deck.text(slide, x + 0.3, y + 0.22, w - 0.5, 0.3, _s(ctx, "what_emerges"), size=11, bold=True,
              color=DeckTheme.BRAND_PRIMARY)
    box = deck.bullets(slide, x + 0.3, y + 0.68, w - 0.55, h - 0.85,
                       [b for b in bullets if b], size=12, color=DeckTheme.INK)
    for paragraph in box.text_frame.paragraphs:
        paragraph.space_after = Pt(10)


def _kpi_row(deck, slide, tiles: list[tuple[str, str]], *, x: float, y: float, w: float, h: float = 1.2) -> None:
    gap = 0.2
    tile_w = (w - gap * (len(tiles) - 1)) / len(tiles)
    for index, (label, value) in enumerate(tiles):
        deck.kpi(slide, x + index * (tile_w + gap), y, tile_w, h, label, value, fill=DeckTheme.kpi_fill(index))


def _legend(deck, slide, x: float, y: float, items: list[tuple[str, tuple[int, int, int]]]) -> None:
    for label, color in items:
        deck.rect(slide, x, y + 0.05, 0.16, 0.16, color)
        deck.text(slide, x + 0.24, y, 2.6, 0.26, label, size=10, color=DeckTheme.SUBTLE_INK)
        x += 0.45 + len(label) * 0.075


class ProspectBlock(BaseBlock):
    """Base for prospect slides: available only when the prospect metrics exist."""

    def is_available(self, ctx) -> bool:
        return bool(_p(ctx)) and self.has_data(_p(ctx))

    def has_data(self, prospect: dict[str, Any]) -> bool:
        return True


# Slides -------------------------------------------------------------------------

class ProspectCoverBlock(ProspectBlock):
    id = "prospect_cover"
    section = Section.FRONT

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.rect(slide, 0, 0, DeckTheme.SLIDE_W, DeckTheme.SLIDE_H, DeckTheme.BRAND_PRIMARY)
        deck.text(slide, 1.0, 1.55, DeckTheme.SLIDE_W - 2.0, 0.4, _s(ctx, "cover_eyebrow"),
                  size=14, bold=True, color=DeckTheme.WHITE)
        deck.text(slide, 1.0, 2.05, DeckTheme.SLIDE_W - 2.0, 1.5,
                  _s(ctx, "cover_title").format(brand=_brand(ctx)),
                  size=54, bold=True, color=DeckTheme.WHITE)
        deck.text(slide, 1.0, 3.65, DeckTheme.SLIDE_W - 2.0, 0.5, _s(ctx, "cover_subtitle"),
                  size=20, color=DeckTheme.WHITE)
        deck.text(slide, 1.0, 4.45, DeckTheme.SLIDE_W - 2.0, 0.4, _s(ctx, "cover_meta"),
                  size=13, color=DeckTheme.WHITE)
        deck.text(slide, 1.0, 6.45, DeckTheme.SLIDE_W - 2.0, 0.35, _s(ctx, "cover_footer"),
                  size=12, bold=True, color=DeckTheme.WHITE)
        deck.footer_strip(slide)
        return BlockResult(rendered=True)


class ProspectOverviewBlock(ProspectBlock):
    id = "prospect_overview"
    section = Section.FRONT

    def has_data(self, p) -> bool:
        return float(p.get("revenue_2025") or 0) > 0

    def render(self, ctx, deck, page: int) -> BlockResult:
        p = _p(ctx)
        areas = [a for a in p.get("areas") or [] if a["name"] != OTHER_AREA]
        headline = _s(ctx, "overview_title").format(
            brand=_brand(ctx), asins=ctx.fmt.integer(p.get("asins_with_sales_2025")), areas=len(areas))
        slide = _frame(ctx, deck, page, "eyebrow_overview", headline, _s(ctx, "source_snapshot"))
        buy_box = p.get("buy_box") or {}
        brand_share = (buy_box.get("revenue_share_by_type") or {}).get("brand") if buy_box.get("available") else None
        tiles = [
            (_s(ctx, "kpi_revenue"), ctx.fmt.currency(p.get("revenue_2025"))),
            (_s(ctx, "kpi_yoy"), ctx.fmt.percent_signed(p.get("yoy_revenue_pct"))),
            (_s(ctx, "kpi_asins"), ctx.fmt.integer(p.get("asins_with_sales_2025"))),
        ]
        if brand_share is not None:
            tiles.append((_s(ctx, "kpi_brand_bb"), ctx.fmt.share(brand_share)))
        _kpi_row(deck, slide, tiles, x=M, y=BODY_Y, w=CW, h=1.3)

        who = []
        if p.get("manufacturer"):
            who.append(_s(ctx, "who_manufacturer").format(name=p["manufacturer"]))
        cats = [f"{c['name']} ({ctx.fmt.share(c['share'])})" for c in p.get("top_categories") or []]
        if cats:
            who.append(_s(ctx, "who_categories").format(cats=", ".join(cats)))
        if buy_box.get("available"):
            where = [
                _s(ctx, "where_brand").format(share=ctx.fmt.share(brand_share)),
                _s(ctx, "where_third").format(sellers=buy_box.get("third_party_sellers", 0),
                                               asins=buy_box.get("third_party_asins", 0)),
            ]
        else:
            where = [_s(ctx, "where_missing")]
        growth = []
        if float(p.get("revenue_2024") or 0) > 0:
            growth.append(_s(ctx, "growth_total").format(
                a=_money_compact(ctx, p["revenue_2024"]), b=_money_compact(ctx, p["revenue_2025"]),
                pct=ctx.fmt.percent_signed(p.get("yoy_revenue_pct"))))
            fastest = _fastest_area(areas)
            if fastest:
                growth.append(_s(ctx, "growth_area").format(area=fastest["name"],
                                                            pct=ctx.fmt.percent_signed(fastest["yoy_pct"])))
        else:
            growth.append(_s(ctx, "growth_missing"))
        card_w = (CW - 0.4) / 3
        for index, (title, body) in enumerate((
            (_s(ctx, "card_who"), who), (_s(ctx, "card_where"), where), (_s(ctx, "card_growth"), growth),
        )):
            deck.callout(slide, M + index * (card_w + 0.2), 3.6, card_w, 2.3, title, body,
                         accent=DeckTheme.accent(index))
        if areas:
            leading = ", ".join(f"{a['name']} {ctx.fmt.share(a['share'])}" for a in areas[:4])
            deck.rect(slide, M, 6.12, CW, 0.5, DeckTheme.SURFACE, line=DeckTheme.HAIRLINE)
            deck.text(slide, M + 0.18, 6.25, CW - 0.36, 0.3, _s(ctx, "overview_areas").format(areas=leading),
                      size=11, color=DeckTheme.INK)
        return BlockResult(rendered=True)


def _fastest_area(areas: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    candidates = [a for a in areas if a.get("yoy_pct") is not None and a["share"] >= 3]
    return max(candidates, key=lambda a: a["yoy_pct"]) if candidates else None


class ProspectSalesBlock(ProspectBlock):
    id = "prospect_sales"
    section = Section.PERFORMANCE

    def has_data(self, p) -> bool:
        return float(p.get("revenue_2025") or 0) > 0 and p.get("value_per_unit_2025") is not None

    def render(self, ctx, deck, page: int) -> BlockResult:
        p = _p(ctx)
        vpu = ctx.fmt.currency(p["value_per_unit_2025"], 2 if p["value_per_unit_2025"] < 10 else 0)
        headline = _s(ctx, "sales_title").format(rev=_money_compact(ctx, p["revenue_2025"]), vpu=vpu)
        slide = _frame(ctx, deck, page, "eyebrow_sales", headline, _s(ctx, "source_sales"))
        _kpi_row(deck, slide, [
            (_s(ctx, "kpi_revenue"), _money_compact(ctx, p["revenue_2025"])),
            (_s(ctx, "kpi_units"), ctx.fmt.integer(p.get("units_2025"))),
            (_s(ctx, "kpi_vpu"), vpu),
        ], x=M, y=BODY_Y, w=LEFT_W, h=1.15)

        bands = (p.get("price_bands") or {}).get("bands") or []
        labels = [self._band_label(ctx, b) for b in bands]
        shares = [b["share"] for b in bands]
        core = (p.get("price_bands") or {}).get("core_band")
        colors = [DeckTheme.BRAND_PRIMARY if core and b["low"] == core["low"] else THIRD_PARTY for b in bands]
        deck.text(slide, M, 3.4, LEFT_W, 0.26, _s(ctx, "chart_bands"), size=10, bold=True,
                  color=DeckTheme.SUBTLE_INK)
        png = charts.columns(labels, shares, value_fmt=lambda v: ctx.fmt.share(v), colors=colors,
                             w_in=LEFT_W, h_in=3.0)
        _picture(deck, slide, png, M, 3.7, LEFT_W, 3.05)

        bullets = []
        if core:
            bullets.append(_s(ctx, "sales_core").format(band=self._band_label(ctx, core),
                                                       share=ctx.fmt.share(core["share"]), n=core["asins"]))
        high = (p.get("price_bands") or {}).get("high_value_share") or 0
        if high >= 3:
            text = _s(ctx, "sales_high").format(share=ctx.fmt.share(high))
            packed = (p.get("price_bands") or {}).get("high_value_packed_share") or 0
            text += _s(ctx, "sales_high_packed").format(share=ctx.fmt.share(packed)) if packed >= 10 else "."
            bullets.append(text)
        if float(p.get("units_2024") or 0) > 0:
            units_yoy = (float(p["units_2025"]) / float(p["units_2024"]) - 1) * 100
            bullets.append(_s(ctx, "sales_units").format(units=ctx.fmt.integer(p["units_2025"]),
                                                        pct=ctx.fmt.percent_signed(units_yoy)))
        _emerges(ctx, deck, slide, bullets)
        return BlockResult(rendered=True)

    @staticmethod
    def _band_label(ctx, band) -> str:
        low = ctx.fmt.integer(band["low"])
        if band.get("high") is None:
            return _s(ctx, "band_open").format(low=low)
        return _s(ctx, "band").format(low=low, high=ctx.fmt.integer(band["high"]))


class ProspectAreasBlock(ProspectBlock):
    id = "prospect_areas"
    section = Section.CATALOG

    def has_data(self, p) -> bool:
        return len([a for a in p.get("areas") or [] if a["name"] != OTHER_AREA]) >= 2

    def render(self, ctx, deck, page: int) -> BlockResult:
        p = _p(ctx)
        areas = p["areas"]
        named = [a for a in areas if a["name"] != OTHER_AREA]
        first, second = named[0], named[1]
        headline = _s(ctx, "areas_title_two").format(
            a=first["name"], b=second["name"], share=_pct0(first["share"] + second["share"]))
        source = _s(ctx, "source_areas_titles" if p.get("area_source") == "titles" else "source_areas_subcategory")
        slide = _frame(ctx, deck, page, "eyebrow_areas", headline, source)

        labels = [fmt.truncate(_area(ctx, a["name"]), 34) for a in areas]
        colors = [DeckTheme.BRAND_PRIMARY if a in (first, second) else THIRD_PARTY for a in areas]
        png = charts.hbar(labels, [a["share"] for a in areas], value_fmt=lambda v: ctx.fmt.share(v),
                          colors=colors, sort=False, w_in=LEFT_W, h_in=4.6)
        _picture(deck, slide, png, M, BODY_Y, LEFT_W, BODY_BOTTOM - BODY_Y)

        bullets = [_s(ctx, "areas_top").format(
            a=first["name"], sa=ctx.fmt.share(first["share"]), na=first["asins"],
            b=second["name"], sb=ctx.fmt.share(second["share"]), nb=second["asins"])]
        many = [a for a in named if a["share"] < 10 and a["asins"] >= 8]
        if many:
            area = max(many, key=lambda a: a["asins"])
            bullets.append(_s(ctx, "areas_long_tail").format(area=area["name"], n=area["asins"],
                                                            share=ctx.fmt.share(area["share"])))
        fastest = _fastest_area(named)
        if fastest:
            bullets.append(_s(ctx, "areas_growth").format(area=fastest["name"],
                                                         pct=ctx.fmt.percent_signed(fastest["yoy_pct"])))
        other = next((a for a in areas if a["name"] == OTHER_AREA), None)
        if other and other["share"] >= 5:
            bullets.append(_s(ctx, "areas_other").format(n=other["asins"], share=ctx.fmt.share(other["share"])))
        _emerges(ctx, deck, slide, bullets)
        return BlockResult(rendered=True)


class ProspectTopProductsBlock(ProspectBlock):
    id = "prospect_top_products"
    section = Section.PERFORMANCE

    def has_data(self, p) -> bool:
        return len(p.get("top_products") or []) >= 3

    def render(self, ctx, deck, page: int) -> BlockResult:
        p = _p(ctx)
        top = p["top_products"]
        share = sum(item["share"] for item in top)
        headline = _s(ctx, "top_title").format(n=len(top), share=_pct0(share))
        ratings = [item["rating"] for item in top if item.get("rating") is not None]
        if ratings:
            headline += _s(ctx, "top_title_rating").format(low=_rating(ctx, min(ratings)), high=_rating(ctx, max(ratings)))
        slide = _frame(ctx, deck, page, "eyebrow_top", headline, _s(ctx, "source_snapshot"))

        brand = _brand(ctx)
        labels = [_short(item["name"], brand, 40) for item in top]
        colors = [DeckTheme.BRAND_PRIMARY if item["buy_box_type"] in ("brand", "amazon") else THIRD_PARTY
                  for item in top]
        png = charts.hbar(labels, [item["revenue"] for item in top], value_fmt=lambda v: ctx.fmt.currency(v),
                          colors=colors, w_in=LEFT_W, h_in=4.2)
        _picture(deck, slide, png, M, BODY_Y, LEFT_W, 4.3)
        if (p.get("buy_box") or {}).get("available"):
            _legend(deck, slide, M, 6.45, [(_s(ctx, "legend_brand"), DeckTheme.BRAND_PRIMARY),
                                          (_s(ctx, "legend_third"), THIRD_PARTY)])

        first = top[0]
        lead = _s(ctx, "top_first").format(name=_short(first["name"], brand, 34),
                                           share=ctx.fmt.share(first["share"]))
        lead += (_s(ctx, "top_first_reviews").format(n=ctx.fmt.integer(first["reviews"]))
                 if first.get("reviews") else ".")
        bullets = [lead]
        if (p.get("buy_box") or {}).get("available"):
            branded = [item for item in top if item["buy_box_type"] in ("brand", "amazon")]
            bullets.append(_s(ctx, "top_brand_bb").format(k=len(branded), n=len(top)))
            exceptions = [item for item in top if item not in branded]
            if len(exceptions) == 1 and exceptions[0].get("buy_box_owner"):
                bullets.append(_s(ctx, "top_exception").format(
                    name=_short(exceptions[0]["name"], brand, 34), owner=exceptions[0]["buy_box_owner"]))
        growing = [item for item in top if item.get("yoy_pct") is not None]
        if growing:
            best = max(growing, key=lambda item: item["yoy_pct"])
            bullets.append(_s(ctx, "top_growth").format(name=_short(best["name"], brand, 34),
                                                       pct=ctx.fmt.percent_signed(best["yoy_pct"])))
        _emerges(ctx, deck, slide, bullets)
        return BlockResult(rendered=True)


class ProspectConcentrationBlock(ProspectBlock):
    id = "prospect_concentration"
    section = Section.PERFORMANCE

    def has_data(self, p) -> bool:
        pareto = p.get("pareto") or {}
        return int(p.get("asins_with_sales_2025") or 0) >= 5 and pareto.get("asins_to_80")

    def render(self, ctx, deck, page: int) -> BlockResult:
        p = _p(ctx)
        pareto = p["pareto"]
        n80, total = pareto["asins_to_80"], p["asins_with_sales_2025"]
        headline = _s(ctx, "conc_title").format(n80=n80, n=total)
        if pareto.get("tail_under_1000_count", 0) >= 5:
            headline += _s(ctx, "conc_title_tail")
        slide = _frame(ctx, deck, page, "eyebrow_concentration", headline, _s(ctx, "source_sales"))
        _kpi_row(deck, slide, [
            (_s(ctx, "kpi_to_80"), f"{n80} / {total}"),
            (_s(ctx, "kpi_tail"), ctx.fmt.integer(pareto.get("tail_under_1000_count"))),
        ], x=M, y=BODY_Y, w=LEFT_W, h=1.15)
        png = charts.pareto(pareto["curve"], mark_at=n80, mark_label=_s(ctx, "conc_mark").format(n=n80),
                            x_label=_s(ctx, "conc_axis"), w_in=LEFT_W, h_in=3.2)
        _picture(deck, slide, png, M, 3.4, LEFT_W, 3.35)

        top5 = pareto.get("top5_share") or 0
        bullets = [
            _s(ctx, "conc_top").format(top5=ctx.fmt.share(top5), top10=ctx.fmt.share(pareto.get("top10_share"))),
        ]
        if pareto.get("tail_under_1000_count"):
            bullets.append(_s(ctx, "conc_tail").format(n=pareto["tail_under_1000_count"],
                                                      share=ctx.fmt.share(pareto.get("tail_under_1000_share"))))
        level = "conc_level_high" if top5 >= 60 else "conc_level_mid" if top5 >= 35 else "conc_level_low"
        bullets.append(_s(ctx, level))
        _emerges(ctx, deck, slide, bullets)
        return BlockResult(rendered=True)


class ProspectSeasonalityBlock(ProspectBlock):
    id = "prospect_seasonality"
    section = Section.MARKET

    def has_data(self, p) -> bool:
        return bool(p.get("seasonality"))

    def render(self, ctx, deck, page: int) -> BlockResult:
        p = _p(ctx)
        season = p["seasonality"]
        months_long = _s(ctx, "months_long")
        peak = months_long[season["peak_month"] - 1]
        if season["summer_share"] >= 25:
            headline = _s(ctx, "season_title_summer").format(share=_pct0(season["summer_share"]))
        else:
            headline = _s(ctx, "season_title_peak").format(month=peak)
        slide = _frame(ctx, deck, page, "eyebrow_seasonality", headline, _s(ctx, "source_season"))
        colors = [DeckTheme.BRAND_PRIMARY if month in SUMMER_MONTHS else THIRD_PARTY for month in range(1, 13)]
        png = charts.columns(_s(ctx, "months"), season["by_month"], value_fmt=lambda v: _pct0(v) + "%",
                             colors=colors, w_in=LEFT_W, h_in=4.4)
        _picture(deck, slide, png, M, BODY_Y, LEFT_W, BODY_BOTTOM - BODY_Y)
        bullets = [_s(ctx, "season_peak").format(month=peak)]
        if season.get("summer_areas"):
            bullets.append(_s(ctx, "season_areas").format(areas=", ".join(season["summer_areas"])))
        if season["summer_share"] < 60:
            bullets.append(_s(ctx, "season_rest"))
        _emerges(ctx, deck, slide, bullets)
        return BlockResult(rendered=True)


class ProspectBuyBoxBlock(ProspectBlock):
    id = "prospect_buy_box"
    section = Section.CHANNEL

    def has_data(self, p) -> bool:
        return bool((p.get("buy_box") or {}).get("available"))

    def render(self, ctx, deck, page: int) -> BlockResult:
        p = _p(ctx)
        bb = p["buy_box"]
        headline = _s(ctx, "bb_title").format(b=bb["brand_asins"], k=bb["third_party_asins"],
                                              s=bb["third_party_sellers"])
        slide = _frame(ctx, deck, page, "eyebrow_buy_box", headline, _s(ctx, "source_snapshot"))
        types = _s(ctx, "bb_types")
        shares = bb.get("revenue_share_by_type") or {}
        segments = [(types[key], shares.get(key, 0), TYPE_COLORS[key])
                    for key in ("brand", "pharmacy", "other", "amazon", "none") if shares.get(key, 0) >= 0.5]
        png = charts.donut(segments, center=ctx.fmt.share(shares.get("brand", 0)), w_in=3.6, h_in=3.6)
        _picture(deck, slide, png, M, BODY_Y + 0.2, 3.7, 4.4)

        sellers = bb.get("top_sellers") or []
        if sellers:
            short = _s(ctx, "bb_type_short")
            rows = [[fmt.truncate(s["name"], 24), short.get(s["type"], s["type"]), str(s["asins"]),
                     ctx.fmt.share(s["share"])] for s in sellers[:7]]
            deck.table(slide, 4.25, BODY_Y + 0.1,
                       [_s(ctx, "bb_col_seller"), _s(ctx, "bb_col_type"), _s(ctx, "bb_col_asins"), _s(ctx, "bb_col_share")],
                       rows, [2.0, 1.1, 0.55, 0.85], max_rows=7)

        lead = _s(ctx, "bb_brand").format(share=ctx.fmt.share(shares.get("brand", 0)))
        if bb["brand_asins"] and bb["brand_asins_fba"] == bb["brand_asins"]:
            lead += _s(ctx, "bb_brand_fba_all")
        else:
            lead += _s(ctx, "bb_brand_fba").format(n=bb["brand_asins_fba"])
        bullets = [lead, _s(ctx, "bb_sellers").format(pharm=bb["pharmacy_sellers"], other=bb["other_sellers"])]
        if bb.get("top4_sellers_range"):
            low, high = bb["top4_sellers_range"]
            bullets.append(_s(ctx, "bb_range").format(a=low, b=high))
        _emerges(ctx, deck, slide, bullets)
        return BlockResult(rendered=True)


class ProspectFormatsBlock(ProspectBlock):
    id = "prospect_formats"
    section = Section.CATALOG

    def has_data(self, p) -> bool:
        formats = p.get("formats") or {}
        return (formats.get("multipack_asins") or 0) + (formats.get("set_asins") or 0) > 0

    def render(self, ctx, deck, page: int) -> BlockResult:
        p = _p(ctx)
        f = p["formats"]
        if f["multipack_asins"]:
            headline = _s(ctx, "formats_title_mp").format(share=_pct0(f["multipack_share"]),
                                                         k=f["multipack_third_party_buy_box"], n=f["multipack_asins"])
        else:
            headline = _s(ctx, "formats_title_set").format(share=_pct0(f["set_share"]))
        slide = _frame(ctx, deck, page, "eyebrow_formats", headline, _s(ctx, "source_formats"))
        png = charts.columns(_s(ctx, "format_labels"), [f["single_share"], f["multipack_share"], f["set_share"]],
                             value_fmt=lambda v: ctx.fmt.share(v),
                             colors=[THIRD_PARTY, DeckTheme.BRAND_PRIMARY, DeckTheme.ORANGE],
                             w_in=LEFT_W, h_in=4.4)
        _picture(deck, slide, png, M, BODY_Y, LEFT_W, BODY_BOTTOM - BODY_Y)
        bullets = [_s(ctx, "formats_single").format(share=ctx.fmt.share(f["single_share"]), n=f["single_asins"])]
        if f["set_asins"]:
            bullets.append(_s(ctx, "formats_sets").format(n=f["set_asins"], share=ctx.fmt.share(f["set_share"]),
                                                         brand=ctx.fmt.share(f["set_brand_buy_box_share"])))
        mostly_third = f["multipack_asins"] and f["multipack_third_party_buy_box"] / f["multipack_asins"] >= 0.7
        if mostly_third or (f["set_asins"] and f["set_brand_buy_box_share"] < 50):
            bullets.append(_s(ctx, "formats_gap"))
        _emerges(ctx, deck, slide, bullets)
        return BlockResult(rendered=True)


class ProspectYoYBlock(ProspectBlock):
    id = "prospect_yoy"
    section = Section.PERFORMANCE

    def has_data(self, p) -> bool:
        return float(p.get("revenue_2024") or 0) > 0 and float(p.get("revenue_2025") or 0) > 0

    def render(self, ctx, deck, page: int) -> BlockResult:
        p = _p(ctx)
        headline = _s(ctx, "yoy_title").format(a=_money_compact(ctx, p["revenue_2024"]),
                                               b=_money_compact(ctx, p["revenue_2025"]),
                                               pct=ctx.fmt.percent_signed(p.get("yoy_revenue_pct")))
        slide = _frame(ctx, deck, page, "eyebrow_yoy", headline, _s(ctx, "source_yoy"))
        png = charts.waterfall("2024", float(p["revenue_2024"]), "2025", float(p["revenue_2025"]),
                               value_fmt=lambda v: _money_compact(ctx, v), w_in=5.4, h_in=3.9)
        _picture(deck, slide, png, M, BODY_Y, 5.5, 4.1)

        areas = [a for a in p.get("areas") or [] if a["name"] != OTHER_AREA][:8]
        if areas:
            rows = [[fmt.truncate(a["name"], 28), ctx.fmt.currency(a["revenue_2024"]), ctx.fmt.currency(a["revenue"]),
                     ctx.fmt.percent_signed(a.get("yoy_pct"))] for a in areas]
            deck.table(slide, 6.3, BODY_Y, [_s(ctx, "yoy_col_area"), "2024", "2025", _s(ctx, "yoy_col_change")],
                       rows, [2.75, 1.35, 1.35, 1.22], accent_columns={3}, max_rows=8)
        moving = [a for a in areas if a.get("yoy_pct") is not None and a["share"] >= 3]
        if moving:
            up = max(moving, key=lambda a: a["yoy_pct"])
            down = min(moving, key=lambda a: a["yoy_pct"])
            if down["yoy_pct"] < 0:
                line = _s(ctx, "yoy_up_down").format(up=up["name"], up_pct=ctx.fmt.percent_signed(up["yoy_pct"]),
                                                    down=down["name"], down_pct=ctx.fmt.percent_signed(down["yoy_pct"]))
            else:
                line = _s(ctx, "yoy_up").format(up=up["name"], up_pct=ctx.fmt.percent_signed(up["yoy_pct"]))
            deck.rect(slide, M, 6.25, CW, 0.5, DeckTheme.SURFACE, line=DeckTheme.HAIRLINE)
            deck.text(slide, M + 0.18, 6.38, CW - 0.36, 0.3, line, size=11, color=DeckTheme.INK)
        return BlockResult(rendered=True)


class ProspectListingHealthBlock(ProspectBlock):
    id = "prospect_listing_health"
    section = Section.CATALOG
    MAX_ROWS = 12

    def has_data(self, p) -> bool:
        return bool((p.get("listing_health") or {}).get("items"))

    def render(self, ctx, deck, page: int) -> BlockResult:
        p = _p(ctx)
        health = p["listing_health"]
        counts = health["counts"]
        items = health["items"]
        headline = _s(ctx, "listing_title").format(g=counts[LIGHT_GREEN], y=counts[LIGHT_YELLOW],
                                                   r=counts[LIGHT_RED], n=len(items))
        slide = _frame(ctx, deck, page, "eyebrow_listing", headline)

        columns = _s(ctx, "listing_cols")
        xs = [M, M + 4.55, M + 6.0, M + 7.05, M + 8.1, M + 9.15, M + 10.2, M + 11.3]
        widths = [4.45, 1.35, 1.0, 1.0, 1.0, 1.0, 1.0, 1.3]
        top = 1.95
        deck.rect(slide, M, top, CW, 0.36, DeckTheme.TABLE_HEADER)
        for index, label in enumerate(columns):
            align = "left" if index == 0 else "center"
            deck.text(slide, xs[index] + (0.1 if index == 0 else 0), top + 0.08, widths[index] - 0.1, 0.24,
                      label, size=10, bold=True, color=DeckTheme.WHITE, align=align)
        brand = _brand(ctx)
        row_h = 0.33
        for row, item in enumerate(items[: self.MAX_ROWS]):
            y = top + 0.36 + row * row_h
            if row % 2:
                deck.rect(slide, M, y, CW, row_h, DeckTheme.SURFACE)
            deck.text(slide, xs[0] + 0.1, y + 0.07, widths[0] - 0.15, 0.22,
                      _short(item["name"], brand, 58), size=9.5, color=DeckTheme.INK)
            deck.text(slide, xs[1], y + 0.07, widths[1], 0.22, ctx.fmt.currency(item["revenue"]),
                      size=9.5, color=DeckTheme.INK, align="center")
            for col, check in enumerate(("title", "images", "rating", "reviews", "buy_box"), start=2):
                self._dot(deck, slide, xs[col] + widths[col] / 2, y + row_h / 2, item["checks"][check])
            score_x = xs[7] + 0.28
            self._dot(deck, slide, score_x, y + row_h / 2, item["overall"])
            score = "—" if item.get("score") is None else ctx.fmt.integer(item["score"])
            deck.text(slide, score_x + 0.18, y + 0.07, 0.6, 0.22, score, size=9.5, bold=True, color=DeckTheme.INK)

        shown = min(len(items), self.MAX_ROWS)
        footer_y = top + 0.36 + shown * row_h + 0.12
        thresholds = dict(health.get("thresholds") or {})
        weights = thresholds.get("weights") or CHECK_WEIGHTS
        criteria = _s(ctx, "listing_criteria").format(
            t1=TITLE_LENGTH[0], t2=TITLE_LENGTH[1], i1=IMAGES[0], i2=IMAGES[1],
            r1=_rating(ctx, RATING[0]), r2=_rating(ctx, RATING[1]), v1=REVIEWS[0], v2=REVIEWS[1],
            wt=weights["title"], wi=weights["images"], wr=weights["rating"], wv=weights["reviews"],
            wb=weights["buy_box"], s1=SCORE_GREEN, s2=SCORE_YELLOW)
        if len(items) > shown:
            criteria = _s(ctx, "listing_more").format(shown=shown) + " " + criteria
        deck.text(slide, M, max(footer_y, 6.2), CW, 0.75, criteria, size=8.5, color=DeckTheme.SUBTLE_INK)
        return BlockResult(rendered=True)

    @staticmethod
    def _dot(deck, slide, cx: float, cy: float, light: str) -> None:
        size = 0.17
        deck.oval(slide, cx - size / 2, cy - size / 2, size, size, LIGHT_COLORS.get(light, LIGHT_COLORS[LIGHT_NA]))


class ProspectSynthesisBlock(ProspectBlock):
    id = "prospect_synthesis"
    section = Section.STRATEGY

    def has_data(self, p) -> bool:
        return len([a for a in p.get("areas") or [] if a["name"] != OTHER_AREA]) >= 2 and (p.get("pareto") or {}).get("asins_to_80")

    def render(self, ctx, deck, page: int) -> BlockResult:
        p = _p(ctx)
        named = [a for a in p["areas"] if a["name"] != OTHER_AREA]
        first, second = named[0], named[1]
        two_share = first["share"] + second["share"]
        bb = p.get("buy_box") or {}
        third_share = None
        if bb.get("available"):
            shares = bb.get("revenue_share_by_type") or {}
            third_share = (shares.get("pharmacy") or 0) + (shares.get("other") or 0)
        headline = _s(ctx, "synth_title").format(share=_pct0(two_share))
        if third_share is not None:
            headline += _s(ctx, "synth_title_bb").format(share=_pct0(third_share))
        slide = _frame(ctx, deck, page, "eyebrow_synthesis", headline)

        pareto = p["pareto"]
        cards = [(
            f"{_pct0(two_share)}%",
            _s(ctx, "synth_conc_label").format(a=first["name"], b=second["name"]),
            _s(ctx, "synth_conc_detail").format(n80=pareto["asins_to_80"], n=p["asins_with_sales_2025"]),
            _s(ctx, "synth_conc_work"),
        )]
        season = p.get("seasonality")
        if season and season["summer_share"] >= 25:
            cards.append((
                f"{_pct0(season['summer_share'])}%",
                _s(ctx, "synth_season_label"),
                _s(ctx, "synth_season_detail").format(areas=", ".join(season.get("summer_areas") or [])) if season.get("summer_areas") else "",
                _s(ctx, "synth_season_work"),
            ))
        elif third_share is not None:
            cards.append((
                f"{_pct0(third_share)}%",
                _s(ctx, "synth_bb_label"),
                _s(ctx, "synth_bb_detail").format(s=bb["third_party_sellers"], k=bb["third_party_asins"]),
                _s(ctx, "synth_bb_work"),
            ))
        health = p.get("listing_health") or {}
        if health.get("items"):
            counts = health["counts"]
            cards.append((
                str(counts[LIGHT_RED]),
                _s(ctx, "synth_listing_label").format(y=counts[LIGHT_YELLOW]),
                _s(ctx, "synth_listing_detail").format(n=len(health["items"])),
                _s(ctx, "synth_listing_work"),
            ))

        gap = 0.25
        card_w = (CW - gap * (len(cards) - 1)) / len(cards)
        for index, (number, label, detail, work) in enumerate(cards):
            x = M + index * (card_w + gap)
            accent = DeckTheme.accent(index)
            deck.rect(slide, x, BODY_Y, card_w, 3.85, DeckTheme.SURFACE, line=DeckTheme.HAIRLINE)
            deck.rect(slide, x, BODY_Y, card_w, 0.07, accent)
            deck.text(slide, x + 0.3, BODY_Y + 0.3, card_w - 0.6, 0.8, number, size=40, bold=True, color=accent)
            deck.text(slide, x + 0.3, BODY_Y + 1.15, card_w - 0.6, 0.6, label, size=13, bold=True, color=DeckTheme.INK)
            if detail:
                deck.text(slide, x + 0.3, BODY_Y + 1.8, card_w - 0.6, 0.7, detail, size=11, color=DeckTheme.SUBTLE_INK)
            deck.text(slide, x + 0.3, BODY_Y + 2.6, card_w - 0.6, 0.26, _s(ctx, "work_space"), size=9.5, bold=True,
                      color=accent)
            deck.text(slide, x + 0.3, BODY_Y + 2.9, card_w - 0.6, 0.85, work, size=11, color=DeckTheme.INK)
        deck.text(slide, M, 6.15, CW, 0.6,
                  _s(ctx, "synth_close").format(brand=_brand(ctx), n80=pareto["asins_to_80"]),
                  size=13, bold=True, color=DeckTheme.INK)
        return BlockResult(rendered=True)


class ProspectMethodologyBlock(ProspectBlock):
    id = "prospect_methodology"
    section = Section.APPENDIX

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.text(slide, M, 0.58, CW, 0.26, _s(ctx, "eyebrow_method"), size=11, bold=True,
                  color=DeckTheme.BRAND_PRIMARY)
        deck.text(slide, M, 0.88, CW, 0.7, _s(ctx, "method_title"), size=26, bold=True, color=DeckTheme.INK)
        half = (CW - 0.3) / 2
        deck.callout(slide, M, BODY_Y, half, 2.9, _s(ctx, "method_sources"), _s(ctx, "method_source_items"))
        deck.callout(slide, M + half + 0.3, BODY_Y, half, 2.9, _s(ctx, "method_definitions"),
                     _s(ctx, "method_definition_items"), accent=DeckTheme.NAVY)
        return BlockResult(rendered=True)
