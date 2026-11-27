"""Quarterly business review deck (R5) and all of its copy.

Slides drawn with the brand-analysis deck primitives: cover, KPI table (value,
change against the previous quarter and the same quarter last year, provenance
tag; the subtitle flags a quarter still in progress), monthly trend, top and
bottom ASINs, catalogue health, search terms (one slide per country),
competitors (twelve per slide), insights and actions, data notes. At least nine
slides: a section without data still gets its slide, with a "no data" card.
Text is Italian by default, English on request; data.py and insights.py take
their wording from ``COPY`` too.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Optional

from app.services.brand_analysis.deck.format import EMPTY, Formatter, truncate
from app.services.brand_analysis.deck.primitives import DeckBuilder, fit_size
from app.services.brand_analysis.deck.theme import DeckTheme

if TYPE_CHECKING:
    from app.services.quarterly_report.data import Metric, QuarterData
    from app.services.quarterly_report.insights import Insight

COPY: dict[str, dict[str, str]] = {
    "it": {
        # Provenance and KPI names
        "provenance_actual": "Dato effettivo",
        "provenance_estimated": "Stima",
        "kpi_revenue": "Ricavi",
        "kpi_units": "Unità vendute",
        "kpi_ad_spend": "Spesa pubblicitaria",
        "kpi_ad_sales": "Vendite da pubblicità",
        "kpi_roas": "ROAS",
        "kpi_acos": "ACoS",
        "kpi_tacos": "TACOS",
        "kpi_return_rate": "Tasso di reso",
        # Data gaps
        "gap_no_products": "Nessun prodotto corrisponde al filtro brand/categoria/ASIN",
        "gap_no_sales": "Nessun dato di vendita per {quarter}",
        "gap_no_sales_comparison": "Nessun dato di vendita per {quarter}: variazioni non calcolabili",
        "gap_ads_unavailable": "Dati pubblicitari non disponibili per {quarter}",
        "gap_report_coverage": "{quarter} · Retail copre {observed} giorni su {required} complessivi per gli account selezionati. Copertura Ads {ads}.",
        "coverage_full": "completa",
        "coverage_partial": "parziale",
        "coverage_none": "assente",
        "gap_ads_filter": "Spesa pubblicitaria non disponibile per filtro brand/categoria",
        "gap_roas_zero_spend": "ROAS non calcolabile: spesa pubblicitaria pari a zero",
        "gap_acos_zero_sales": "ACoS non calcolabile: vendite da pubblicità pari a zero",
        "gap_tacos_zero_revenue": "TACOS non calcolabile: ricavi pari a zero",
        "gap_return_rate_zero_units": "Tasso di reso non calcolabile: unità vendute pari a zero",
        "gap_quarter_in_progress": "{quarter} non è ancora concluso: dati fino al {today}",
        "gap_currency": "Importi di {countries} in valuta locale, sommati senza conversione in euro",
        "gap_catalogue_empty": "Nessuno stato del semaforo registrato per questo perimetro",
        "gap_search_terms_vendor": "Termini di ricerca Brand Analytics non disponibili per gli account vendor",
        "gap_search_terms_empty": "Nessun termine di ricerca Brand Analytics registrato",
        "gap_competitors_empty": "Nessun concorrente monitorato nei paesi selezionati",
        # Rule insights
        "ins_rev_down_prev_title": "Ricavi in calo rispetto al trimestre precedente",
        "ins_rev_up_prev_title": "Ricavi in crescita rispetto al trimestre precedente",
        "ins_rev_down_ly_title": "Ricavi in calo rispetto allo stesso trimestre dell'anno precedente",
        "ins_rev_up_ly_title": "Ricavi in crescita rispetto allo stesso trimestre dell'anno precedente",
        "ins_rev_body": "Ricavi {quarter}: {value} contro {base} in {base_quarter} ({change}).",
        "ins_rev_down_action": "Analizza gli ASIN in maggior calo (disponibilità, prezzo, Buy Box, "
                               "contenuti) e rivedi offerte e budget delle campagne che li sostengono.",
        "ins_rev_up_action": "Proteggi disponibilità e Buy Box degli ASIN che trainano la crescita e "
                             "sposta budget sulle campagne con il ROAS più alto.",
        "ins_rev_down_action_no_ads": "Analizza gli ASIN in maggior calo: disponibilità, prezzo, Buy Box "
                                      "e contenuti della scheda prodotto.",
        "ins_rev_up_action_no_ads": "Proteggi disponibilità e Buy Box degli ASIN che trainano la crescita "
                                    "e rafforzane i contenuti della scheda prodotto.",
        "ins_rev_drivers_up": "Contribuiscono di più: {items}.",
        "ins_rev_drivers_down": "Pesano di più i cali di {items}.",
        "ins_rev_leaders": "ASIN con più ricavi nel trimestre: {items}.",
        "ins_competitors_title": "Concorrenti più aggressivi",
        "ins_competitors_body": "Da inizio {quarter}: {items}.",
        "ins_competitor_price": "prezzo {change} a {price}",
        "ins_competitor_bsr": "BSR da {start} a {end}",
        "ins_competitors_action": "Confronta prezzo e offerta con questi concorrenti, valuta promozioni o "
                                  "coupon sugli ASIN in diretta concorrenza e controlla la Buy Box.",
        "ins_term_title": "Termine di ricerca da presidiare",
        "ins_term_body": "«{term}» ({country}, rank di ricerca {rank}): la nostra quota clic è {own}, "
                         "l'ASIN più cliccato ({top_asin}) ha {top}.",
        "ins_term_action": "Rafforza titolo, immagini e bullet point degli ASIN pertinenti per questo "
                           "termine e presidialo con campagne Sponsored Products.",
        "ins_term_action_no_ads": "Rafforza titolo, immagini e bullet point degli ASIN pertinenti per "
                                  "questo termine e verifica prezzo e Buy Box.",
        "ins_tacos_up_title": "TACOS in aumento",
        "ins_tacos_down_title": "TACOS in diminuzione",
        "ins_tacos_body": "TACOS {quarter}: {value} contro {base} in {base_quarter} ({change}).",
        "ins_tacos_up_action": "Riduci le offerte sulle parole chiave con ACoS sopra la media e "
                               "concentra il budget sugli ASIN che convertono meglio.",
        "ins_tacos_down_action": "La pubblicità pesa meno sui ricavi: valuta di reinvestire sugli "
                                 "ASIN con margine e ROAS più alti.",
        "ins_returns_up_title": "Tasso di reso in aumento",
        "ins_returns_body": "Tasso di reso {quarter}: {value} contro {base} in {base_quarter} ({change}).",
        "ins_returns_action": "Controlla i motivi di reso degli ASIN più venduti e verifica che scheda "
                              "prodotto, immagini e misure descrivano correttamente il prodotto.",
        "ins_decliners_title": "ASIN in maggior calo",
        "ins_decliners_body": "Rispetto a {base_quarter} questi ASIN perdono {total} ({share} dei "
                              "ricavi di {base_quarter}): {items}.",
        "ins_decliners_action": "Verifica disponibilità, prezzo, Buy Box e contenuti di questi ASIN e "
                                "controlla le anomalie di catalogo aperte.",
        "ins_red_title": "Schede prodotto con semaforo rosso",
        "ins_red_body": "{red} schede su {total} ({share}) hanno il semaforo rosso.",
        "ins_red_action": "Correggi per prime le regole obbligatorie in rosso, partendo dalle schede "
                          "con più ricavi.",
        "ins_anomalies_title": "Anomalie di catalogo aperte",
        "ins_anomalies_body": "{count} anomalie aperte: {kinds}.",
        "ins_anomalies_action": "Rivedi le anomalie nel Catalogo e richiedi il ripristino dei "
                                "contenuti approvati dove serve.",
        "ins_stable_title": "Trimestre stabile",
        "ins_stable_body": "Nessun indicatore supera le soglie di variazione rispetto ai periodi "
                           "di confronto.",
        "ins_stable_action": "Mantieni il monitoraggio settimanale di ricavi, TACOS e semaforo "
                             "delle schede prodotto.",
        # Anomaly kinds
        "anomaly_content_changed": "Contenuto modificato",
        "anomaly_child_detached": "Variante staccata",
        "anomaly_family_broken": "Famiglia di variazioni rotta",
        "anomaly_unexpected_child": "Variante inattesa",
        "anomaly_theme_changed": "Tema di variazione cambiato",
        # Slides
        "cover_title": "Business review trimestrale",
        "cover_countries": "Paesi: {countries}",
        "cover_brand": "Brand: {brand}",
        "cover_category": "Categoria: {category}",
        "cover_asins": "{count} ASIN selezionati",
        "cover_generated": "Generato il {date}",
        "kpi_title": "Indicatori chiave",
        "kpi_subtitle": "{quarter} rispetto a {previous} e a {last_year}",
        "kpi_partial": "trimestre in corso, dati fino al {today}",
        "kpi_note": "pp = punti percentuali. Dato effettivo: report Amazon (Vendor Central, Seller "
                    "Central, Amazon Ads, Brand Analytics). Stima: previsioni o Helium 10.",
        "col_indicator": "Indicatore",
        "col_delta": "Δ vs {quarter}",
        "col_source": "Fonte",
        "trend_title": "Andamento mensile",
        "trend_subtitle": "Ricavi per mese, {quarter} contro {last_year}",
        "asins_title": "ASIN migliori e peggiori",
        "asins_subtitle": "Ricavi {quarter} e variazione rispetto a {previous}",
        "top_heading": "Top 10 per ricavi",
        "bottom_heading": "Maggiori cali di ricavi",
        "no_decliners": "Nessun ASIN in calo rispetto a {previous}",
        "col_asin": "ASIN",
        "col_product": "Prodotto",
        "col_revenue": "Ricavi",
        "col_change": "Variazione",
        "catalogue_title": "Salute del catalogo",
        "catalogue_subtitle": "Semaforo delle schede prodotto (stato al {date}) e anomalie aperte",
        "state_green": "Verde",
        "state_yellow": "Giallo",
        "state_red": "Rosso",
        "state_grey": "Grigio",
        "anomalies_heading": "Anomalie aperte",
        "no_anomalies": "Nessuna anomalia aperta",
        "col_kind": "Tipo",
        "col_count": "Numero",
        "terms_title": "Termini di ricerca",
        "terms_subtitle": "Brand Analytics, {country}, settimana {start} – {end}",
        "col_term": "Termine",
        "col_country": "Paese",
        "col_rank": "Rank di ricerca",
        "col_top_asin": "ASIN più cliccato",
        "col_top_share": "Quota clic",
        "col_own_share": "Quota clic nostri ASIN",
        "competitors_title": "Concorrenti monitorati",
        "competitors_subtitle": "Ultimo valore nel trimestre e variazione da inizio {quarter}",
        "col_price": "Prezzo",
        "col_price_change": "Δ prezzo",
        "col_bsr": "BSR",
        "col_bsr_change": "Δ BSR",
        "col_rating": "Rating",
        "insights_title": "Insight e azioni",
        "insights_subtitle_ai": "Generati con AI dai dati del trimestre",
        "insights_subtitle_rules": "Generati da regole sui dati del trimestre",
        "action_prefix": "Azione",
        "notes_title": "Note sui dati",
        "notes_subtitle": "Dati mancanti e fonti",
        "gaps_heading": "Dati mancanti o parziali",
        "no_gaps": "Nessun dato mancante",
        "sources_heading": "Fonti",
        "source_sales": "Ricavi e unità: report vendite Amazon (Vendor Central: spediti, se assenti "
                        "ordinati; Seller Central: ordinati). Dato effettivo.",
        "source_ads": "Pubblicità: Amazon Ads, vendite attribuite a 7 giorni. Dato effettivo.",
        "source_returns": "Resi: report resi Amazon. Dato effettivo.",
        "source_terms": "Termini di ricerca: Brand Analytics, ultima settimana disponibile. "
                        "Dato effettivo.",
        "source_competitors": "Concorrenti: API Catalog e Pricing di Amazon. Dato effettivo.",
        "source_catalogue": "Semaforo e anomalie: scansione giornaliera del catalogo, ultimo stato.",
        "source_estimates": "Le stime (previsioni, Helium 10) sono marcate «Stima».",
        "no_data": "Nessun dato disponibile",
        "no_data_body": "Questa sezione non ha dati per il perimetro selezionato. Vedi le note "
                        "sui dati.",
    },
    "en": {
        "provenance_actual": "Actual",
        "provenance_estimated": "Estimate",
        "kpi_revenue": "Revenue",
        "kpi_units": "Units sold",
        "kpi_ad_spend": "Ad spend",
        "kpi_ad_sales": "Ad sales",
        "kpi_roas": "ROAS",
        "kpi_acos": "ACoS",
        "kpi_tacos": "TACOS",
        "kpi_return_rate": "Return rate",
        "gap_no_products": "No product matches the brand/category/ASIN filter",
        "gap_no_sales": "No sales data for {quarter}",
        "gap_no_sales_comparison": "No sales data for {quarter}: changes cannot be computed",
        "gap_ads_unavailable": "Advertising data not available for {quarter}",
        "gap_report_coverage": "{quarter} · Retail covers {observed} of {required} account-days. Ads coverage is {ads}.",
        "coverage_full": "complete",
        "coverage_partial": "partial",
        "coverage_none": "absent",
        "gap_ads_filter": "Ad spend not available for the brand/category filter",
        "gap_roas_zero_spend": "ROAS cannot be computed: zero ad spend",
        "gap_acos_zero_sales": "ACoS cannot be computed: zero ad sales",
        "gap_tacos_zero_revenue": "TACOS cannot be computed: zero revenue",
        "gap_return_rate_zero_units": "Return rate cannot be computed: zero units sold",
        "gap_quarter_in_progress": "{quarter} is not over yet: data up to {today}",
        "gap_currency": "Amounts for {countries} are in local currency, summed without conversion to euro",
        "gap_catalogue_empty": "No listing traffic light recorded for this scope",
        "gap_search_terms_vendor": "Brand Analytics search terms are not available for vendor accounts",
        "gap_search_terms_empty": "No Brand Analytics search term recorded",
        "gap_competitors_empty": "No tracked competitor in the selected countries",
        "ins_rev_down_prev_title": "Revenue down on the previous quarter",
        "ins_rev_up_prev_title": "Revenue up on the previous quarter",
        "ins_rev_down_ly_title": "Revenue down on the same quarter last year",
        "ins_rev_up_ly_title": "Revenue up on the same quarter last year",
        "ins_rev_body": "Revenue {quarter}: {value} against {base} in {base_quarter} ({change}).",
        "ins_rev_down_action": "Review the ASINs with the largest decline (stock, price, Buy Box, "
                               "content) and the bids and budgets of the campaigns behind them.",
        "ins_rev_up_action": "Protect stock and Buy Box of the ASINs driving growth and move budget "
                             "to the campaigns with the highest ROAS.",
        "ins_rev_down_action_no_ads": "Review the ASINs with the largest decline: stock, price, Buy Box "
                                      "and listing content.",
        "ins_rev_up_action_no_ads": "Protect stock and Buy Box of the ASINs driving growth and "
                                    "strengthen their listing content.",
        "ins_rev_drivers_up": "Largest contributors: {items}.",
        "ins_rev_drivers_down": "Largest declines: {items}.",
        "ins_rev_leaders": "Top ASINs by revenue in the quarter: {items}.",
        "ins_competitors_title": "Competitors gaining ground",
        "ins_competitors_body": "Since the start of {quarter}: {items}.",
        "ins_competitor_price": "price {change} to {price}",
        "ins_competitor_bsr": "BSR from {start} to {end}",
        "ins_competitors_action": "Compare price and offer with these competitors, consider promotions "
                                  "or coupons on the ASINs competing head-on and watch the Buy Box.",
        "ins_term_title": "Search term to win",
        "ins_term_body": "\"{term}\" ({country}, search rank {rank}): our click share is {own}; the "
                         "most clicked ASIN ({top_asin}) has {top}.",
        "ins_term_action": "Strengthen title, images and bullet points of the relevant ASINs for this "
                           "term and cover it with Sponsored Products campaigns.",
        "ins_term_action_no_ads": "Strengthen title, images and bullet points of the relevant ASINs for "
                                  "this term and check price and Buy Box.",
        "ins_tacos_up_title": "TACOS rising",
        "ins_tacos_down_title": "TACOS falling",
        "ins_tacos_body": "TACOS {quarter}: {value} against {base} in {base_quarter} ({change}).",
        "ins_tacos_up_action": "Lower bids on keywords with above-average ACoS and focus budget on "
                               "the best-converting ASINs.",
        "ins_tacos_down_action": "Advertising weighs less on revenue: consider reinvesting in the "
                                 "ASINs with the best margin and ROAS.",
        "ins_returns_up_title": "Return rate rising",
        "ins_returns_body": "Return rate {quarter}: {value} against {base} in {base_quarter} ({change}).",
        "ins_returns_action": "Check the return reasons of the best sellers and make sure listing, "
                              "images and sizes describe the product correctly.",
        "ins_decliners_title": "ASINs with the largest decline",
        "ins_decliners_body": "Against {base_quarter} these ASINs lose {total} ({share} of "
                              "{base_quarter} revenue): {items}.",
        "ins_decliners_action": "Check stock, price, Buy Box and content of these ASINs and review "
                                "the open catalogue anomalies.",
        "ins_red_title": "Listings with a red traffic light",
        "ins_red_body": "{red} of {total} listings ({share}) have a red traffic light.",
        "ins_red_action": "Fix the mandatory red rules first, starting with the highest-revenue listings.",
        "ins_anomalies_title": "Open catalogue anomalies",
        "ins_anomalies_body": "{count} open anomalies: {kinds}.",
        "ins_anomalies_action": "Review the anomalies in Catalogue and request a restore of the "
                                "approved content where needed.",
        "ins_stable_title": "Stable quarter",
        "ins_stable_body": "No indicator moved beyond the change thresholds against the comparison "
                           "periods.",
        "ins_stable_action": "Keep the weekly watch on revenue, TACOS and listing traffic lights.",
        "anomaly_content_changed": "Content changed",
        "anomaly_child_detached": "Child detached",
        "anomaly_family_broken": "Variation family broken",
        "anomaly_unexpected_child": "Unexpected child",
        "anomaly_theme_changed": "Variation theme changed",
        "cover_title": "Quarterly business review",
        "cover_countries": "Countries: {countries}",
        "cover_brand": "Brand: {brand}",
        "cover_category": "Category: {category}",
        "cover_asins": "{count} selected ASINs",
        "cover_generated": "Generated on {date}",
        "kpi_title": "Key indicators",
        "kpi_subtitle": "{quarter} against {previous} and {last_year}",
        "kpi_partial": "quarter in progress, data up to {today}",
        "kpi_note": "pp = percentage points. Actual: Amazon reports (Vendor Central, Seller Central, "
                    "Amazon Ads, Brand Analytics). Estimate: forecasts or Helium 10.",
        "col_indicator": "Indicator",
        "col_delta": "Δ vs {quarter}",
        "col_source": "Source",
        "trend_title": "Monthly trend",
        "trend_subtitle": "Revenue by month, {quarter} against {last_year}",
        "asins_title": "Top and bottom ASINs",
        "asins_subtitle": "Revenue {quarter} and change against {previous}",
        "top_heading": "Top 10 by revenue",
        "bottom_heading": "Largest revenue declines",
        "no_decliners": "No ASIN declined against {previous}",
        "col_asin": "ASIN",
        "col_product": "Product",
        "col_revenue": "Revenue",
        "col_change": "Change",
        "catalogue_title": "Catalogue health",
        "catalogue_subtitle": "Listing traffic lights (as of {date}) and open anomalies",
        "state_green": "Green",
        "state_yellow": "Yellow",
        "state_red": "Red",
        "state_grey": "Grey",
        "anomalies_heading": "Open anomalies",
        "no_anomalies": "No open anomalies",
        "col_kind": "Type",
        "col_count": "Count",
        "terms_title": "Search terms",
        "terms_subtitle": "Brand Analytics, {country}, week {start} – {end}",
        "col_term": "Term",
        "col_country": "Country",
        "col_rank": "Search rank",
        "col_top_asin": "Most clicked ASIN",
        "col_top_share": "Click share",
        "col_own_share": "Our click share",
        "competitors_title": "Tracked competitors",
        "competitors_subtitle": "Latest value in the quarter and change since the start of {quarter}",
        "col_price": "Price",
        "col_price_change": "Δ price",
        "col_bsr": "BSR",
        "col_bsr_change": "Δ BSR",
        "col_rating": "Rating",
        "insights_title": "Insights and actions",
        "insights_subtitle_ai": "Generated by AI from the quarter's data",
        "insights_subtitle_rules": "Generated by rules from the quarter's data",
        "action_prefix": "Action",
        "notes_title": "Data notes",
        "notes_subtitle": "Missing data and sources",
        "gaps_heading": "Missing or partial data",
        "no_gaps": "No missing data",
        "sources_heading": "Sources",
        "source_sales": "Revenue and units: Amazon sales reports (Vendor Central: shipped, ordered "
                        "when shipped is missing; Seller Central: ordered). Actual.",
        "source_ads": "Advertising: Amazon Ads, 7-day attributed sales. Actual.",
        "source_returns": "Returns: Amazon returns reports. Actual.",
        "source_terms": "Search terms: Brand Analytics, latest available week. Actual.",
        "source_competitors": "Competitors: Amazon Catalog and Pricing APIs. Actual.",
        "source_catalogue": "Traffic lights and anomalies: daily catalogue scan, latest state.",
        "source_estimates": "Estimates (forecasts, Helium 10) are tagged \"Estimate\".",
        "no_data": "No data available",
        "no_data_body": "This section has no data for the selected scope. See the data notes.",
    },
}

MONTHS = {
    "it": ("Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
}


def t(language: str, key: str, **values) -> str:
    """Copy for ``key`` in ``language`` (Italian when the language is unknown)."""
    template = COPY.get(language, COPY["it"]).get(key) or COPY["it"][key]
    return template.format(**values) if values else template


# --- value formatting --------------------------------------------------------------------


def format_value(fmt: Formatter, unit: str, value: Optional[float]) -> str:
    if value is None:
        return EMPTY
    if unit == "EUR":
        return fmt.currency(value)
    if unit == "x":
        return f"{fmt.number(value, 2)}x"
    if unit == "%":
        return fmt.share(value * 100)
    return fmt.integer(value)


def format_change(fmt: Formatter, unit: str, value: Optional[float], base: Optional[float]) -> str:
    """Signed change: percentage points for rates, percent for everything else."""
    from app.services.quarterly_report.data import point_change, relative_change

    if unit == "%":
        points = point_change(value, base)
        if points is None:
            return EMPTY
        return f"{'+' if points >= 0 else ''}{fmt.number(points, 1)} pp"
    return fmt.percent_signed(relative_change(value, base))


def signed_currency(fmt: Formatter, value: Optional[float]) -> str:
    if value is None:
        return EMPTY
    return f"{'-' if value < 0 else '+'}{fmt.currency(abs(value))}"


# --- slides ------------------------------------------------------------------------------

MAX_INSIGHTS = 6  # cards on the insights slide: two rows of three
_TABLE_ROWS = 12  # table rows that fit under a slide heading (DeckBuilder.table's cap)


@dataclass
class _Context:
    data: "QuarterData"
    insights: list["Insight"]
    fmt: Formatter
    current: str
    previous: str
    last_year: str
    in_progress: bool

    @property
    def language(self) -> str:
        return self.data.scope.language

    def t(self, key: str, **values) -> str:
        return t(self.language, key, **values)


_TOP = 1.7
_HALF_W = (DeckTheme.content_w() - 0.3) / 2


def _day(value: Optional[date]) -> str:
    return value.strftime("%d/%m/%Y") if value else EMPTY


def _chunks(rows: list, size: int = _TABLE_ROWS) -> list[list]:
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def _no_data(deck, slide, ctx: _Context, x=DeckTheme.MARGIN, y=_TOP, w=None, h=1.6,
             title: Optional[str] = None) -> None:
    deck.callout(slide, x, y, w or DeckTheme.content_w(), h, title or ctx.t("no_data"),
                 ctx.t("no_data_body"), accent=DeckTheme.NEUTRAL_BAR)


def _content_slide(deck, title: str, subtitle: str = ""):
    """A slide with chrome and heading; its page number is its position in the deck."""
    slide = deck.blank_slide()
    deck.chrome(slide, len(deck.prs.slides))
    deck.heading(slide, title, subtitle)
    return slide


def _cover(deck, ctx: _Context) -> None:
    scope = ctx.data.scope
    slide = deck.blank_slide()
    width = DeckTheme.SLIDE_W - 2.0
    deck.rect(slide, 0, 0, DeckTheme.SLIDE_W, DeckTheme.SLIDE_H, DeckTheme.BRAND_PRIMARY)
    title = ctx.t("cover_title").upper()
    deck.text(slide, 1.0, 1.5, width, 1.3, title,
              size=fit_size(title, width, DeckTheme.TYPE["cover_title"], minimum=32),
              bold=True, color=DeckTheme.WHITE, align="center", anchor="middle")
    deck.text(slide, 1.0, 2.9, width, 0.9, ctx.current, size=40, bold=True,
              color=DeckTheme.WHITE, align="center", anchor="middle")
    countries = sorted({a.get("country") for a in ctx.data.accounts if a.get("country")})
    lines = [ctx.t("cover_countries", countries=", ".join(countries))] if countries else []
    if scope.brand:
        lines.append(ctx.t("cover_brand", brand=scope.brand))
    if scope.category:
        lines.append(ctx.t("cover_category", category=scope.category))
    if scope.asins:
        lines.append(ctx.t("cover_asins", count=len(scope.asins)))
    if lines:
        deck.text(slide, 1.0, 4.1, width, 0.5, "  ·  ".join(lines),
                  size=DeckTheme.TYPE["cover_subtitle"], color=DeckTheme.WHITE, align="center")
    deck.text(slide, 1.0, 4.75, width, 0.4, ctx.t("cover_generated", date=_day(date.today())),
              size=DeckTheme.TYPE["subtitle"], color=DeckTheme.WHITE, align="center")
    deck.footer_strip(slide)


def _kpi_row(ctx: _Context, metric: "Metric") -> list[str]:
    fmt = ctx.fmt
    return [
        ctx.t(f"kpi_{metric.key}") if f"kpi_{metric.key}" in COPY["it"] else metric.key,
        format_value(fmt, metric.unit, metric.value),
        format_change(fmt, metric.unit, metric.value, metric.previous),
        format_change(fmt, metric.unit, metric.value, metric.last_year),
        ctx.t(f"provenance_{metric.provenance}"),
    ]


def _kpis(deck, ctx: _Context) -> None:
    subtitle = ctx.t("kpi_subtitle", quarter=ctx.current, previous=ctx.previous, last_year=ctx.last_year)
    if ctx.in_progress:
        subtitle = f"{subtitle}  ·  {ctx.t('kpi_partial', today=_day(date.today()))}"
    slide = _content_slide(deck, ctx.t("kpi_title"), subtitle)
    if not ctx.data.kpis:
        _no_data(deck, slide, ctx)
        return
    headers = [ctx.t("col_indicator"), ctx.current, ctx.t("col_delta", quarter=ctx.previous),
               ctx.t("col_delta", quarter=ctx.last_year), ctx.t("col_source")]
    rows = [_kpi_row(ctx, metric) for metric in ctx.data.kpis]
    deck.table(slide, DeckTheme.MARGIN, _TOP, headers, rows, [3.4, 2.5, 2.3, 2.3, 2.1])
    note_y = _TOP + 0.38 * (min(len(rows), _TABLE_ROWS) + 1) + 0.25
    note = ctx.t("kpi_note")
    if ctx.data.coverage_note:
        note += "\n" + ctx.data.coverage_note
    deck.text(slide, DeckTheme.MARGIN, note_y, DeckTheme.content_w(), 0.8, note,
              size=DeckTheme.TYPE["caption"] + 1, color=DeckTheme.MUTED)


def _monthly_chart(labels: list[str], current: list[Optional[float]], last_year: list[Optional[float]],
                   current_label: str, last_year_label: str, value_fmt) -> bytes:
    """Grouped columns: each month of the quarter next to the same month last year."""
    from app.services.brand_analysis.deck import charts  # noqa: F401  Agg backend and deck fonts

    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11.5, 4.6))
    width = 0.38
    span = max([v for v in current + last_year if v] or [1.0])
    series = ((-width / 2, last_year, DeckTheme.NEUTRAL_BAR, last_year_label),
              (width / 2, current, DeckTheme.BRAND_PRIMARY, current_label))
    for offset, values, color, name in series:
        heights = [float(v or 0) for v in values]
        bars = ax.bar([i + offset for i in range(len(labels))], heights, width=width,
                      color=DeckTheme.hex(color), label=name)
        for bar, value in zip(bars, heights):
            if value > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, value + span * 0.02, value_fmt(value),
                        ha="center", va="bottom", fontsize=9,
                        color=DeckTheme.hex(DeckTheme.SUBTLE_INK))
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=11, color=DeckTheme.hex(DeckTheme.INK))
    ax.set_yticks([])
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(DeckTheme.hex(DeckTheme.HAIRLINE))
    ax.set_ylim(0, span * 1.2)
    ax.legend(frameon=False, fontsize=10, loc="upper left")
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", transparent=True, bbox_inches="tight", pad_inches=0.04, dpi=220)
    plt.close(fig)
    return buffer.getvalue()


def _trend(deck, ctx: _Context) -> None:
    slide = _content_slide(deck, ctx.t("trend_title"),
                           ctx.t("trend_subtitle", quarter=ctx.current, last_year=ctx.last_year))
    months = ctx.data.monthly
    if not any(m.get("revenue") or m.get("revenue_last_year") for m in months):
        _no_data(deck, slide, ctx)
        return
    names = MONTHS.get(ctx.language, MONTHS["it"])
    png = _monthly_chart(
        [names[m["month"] - 1] for m in months],
        [m.get("revenue") for m in months],
        [m.get("revenue_last_year") for m in months],
        ctx.current, ctx.last_year, ctx.fmt.currency,
    )
    deck.picture(slide, png, DeckTheme.MARGIN + 0.3, _TOP, DeckTheme.content_w() - 0.6, 4.9)


def _asins(deck, ctx: _Context) -> None:
    slide = _content_slide(deck, ctx.t("asins_title"),
                           ctx.t("asins_subtitle", quarter=ctx.current, previous=ctx.previous))
    if not ctx.data.top_asins and not ctx.data.bottom_asins:
        _no_data(deck, slide, ctx)
        return
    fmt = ctx.fmt
    left, right = DeckTheme.MARGIN, DeckTheme.MARGIN + _HALF_W + 0.3
    widths = [1.45, 2.4, 1.2, 1.1]
    headers = [ctx.t("col_asin"), ctx.t("col_product"), ctx.t("col_revenue"), ctx.t("col_change")]
    for x, heading in ((left, ctx.t("top_heading")), (right, ctx.t("bottom_heading"))):
        deck.text(slide, x, _TOP - 0.1, _HALF_W, 0.35, heading, size=DeckTheme.TYPE["body"] + 2,
                  bold=True, color=DeckTheme.INK)
    if ctx.data.top_asins:
        rows = [[r["asin"], truncate(r.get("title") or "", 26), fmt.currency(r["revenue"]),
                 fmt.percent_signed(r.get("change_pct"))] for r in ctx.data.top_asins]
        deck.table(slide, left, _TOP + 0.35, headers, rows, widths)
    else:
        _no_data(deck, slide, ctx, x=left, y=_TOP + 0.35, w=_HALF_W)
    if ctx.data.bottom_asins:
        rows = [[r["asin"], truncate(r.get("title") or "", 26), fmt.currency(r["revenue"]),
                 signed_currency(fmt, r.get("change"))] for r in ctx.data.bottom_asins]
        deck.table(slide, right, _TOP + 0.35, headers, rows, widths)
    else:
        deck.callout(slide, right, _TOP + 0.35, _HALF_W, 1.2,
                     ctx.t("no_decliners", previous=ctx.previous), "", accent=DeckTheme.POSITIVE)


_STATE_COLORS = {
    "green": DeckTheme.POSITIVE,
    "yellow": DeckTheme.GOLD,
    "red": DeckTheme.BRAND_PRIMARY,
    "grey": DeckTheme.NEUTRAL_BAR,
}


def _anomaly_label(ctx: _Context, kind: str) -> str:
    key = f"anomaly_{kind}"
    return ctx.t(key) if key in COPY["it"] else kind


def _catalogue(deck, ctx: _Context) -> None:
    from app.services.brand_analysis.deck import charts

    catalogue = ctx.data.catalogue or {}
    slide = _content_slide(deck, ctx.t("catalogue_title"),
                           ctx.t("catalogue_subtitle", date=_day(catalogue.get("as_of"))))
    states = catalogue.get("states") or {}
    total = catalogue.get("total") or 0
    if total:
        segments = [(f"{ctx.t(f'state_{state}')} {states.get(state, 0)}", states.get(state, 0), color)
                    for state, color in _STATE_COLORS.items()]
        png = charts.donut(segments, center=ctx.fmt.integer(total), w_in=5.0, h_in=4.4)
        deck.picture(slide, png, DeckTheme.MARGIN, _TOP, 5.4, 4.75)
    else:
        _no_data(deck, slide, ctx, w=5.4)
    anomalies = catalogue.get("open_anomalies") or {}
    x = DeckTheme.MARGIN + 6.0
    deck.text(slide, x, _TOP - 0.1, 6.0, 0.35, ctx.t("anomalies_heading"),
              size=DeckTheme.TYPE["body"] + 2, bold=True, color=DeckTheme.INK)
    if anomalies:
        rows = [[_anomaly_label(ctx, kind), ctx.fmt.integer(count)]
                for kind, count in sorted(anomalies.items(), key=lambda item: -item[1])]
        deck.table(slide, x, _TOP + 0.35, [ctx.t("col_kind"), ctx.t("col_count")], rows, [4.6, 1.6])
    else:
        deck.callout(slide, x, _TOP + 0.35, 6.2, 1.2, ctx.t("no_anomalies"), "",
                     accent=DeckTheme.POSITIVE)


def _share(fmt: Formatter, value: Optional[float]) -> str:
    return EMPTY if value is None else fmt.share(value * 100)


def _search_terms(deck, ctx: _Context) -> None:
    """One slide per country: each account has its own latest Brand Analytics week."""
    terms = ctx.data.search_terms
    if not terms:
        _no_data(deck, _content_slide(deck, ctx.t("terms_title")), ctx)
        return
    by_country: dict[str, list[dict]] = {}
    for term in terms:
        by_country.setdefault(term.get("country") or EMPTY, []).append(term)
    fmt = ctx.fmt
    headers = ["#", ctx.t("col_term"), ctx.t("col_rank"), ctx.t("col_top_asin"),
               ctx.t("col_top_share"), ctx.t("col_own_share")]
    for country, rows in by_country.items():
        subtitle = ctx.t("terms_subtitle", country=country, start=_day(rows[0].get("week_start")),
                         end=_day(rows[0].get("week_end")))
        numbered = list(enumerate(rows, start=1))
        for chunk in _chunks(numbered):
            slide = _content_slide(deck, ctx.t("terms_title"), subtitle)
            table = [[str(i), truncate(term["term"], 50), fmt.integer(term.get("rank")),
                      term.get("top_asin") or EMPTY, _share(fmt, term.get("top_click_share")),
                      _share(fmt, term.get("own_click_share"))] for i, term in chunk]
            deck.table(slide, DeckTheme.MARGIN, _TOP, headers, table, [0.5, 5.3, 1.6, 2.0, 1.5, 1.7])


def _competitors(deck, ctx: _Context) -> None:
    """Every tracked competitor, twelve per slide."""
    title = ctx.t("competitors_title")
    subtitle = ctx.t("competitors_subtitle", quarter=ctx.current)
    competitors = ctx.data.competitors
    if not competitors:
        _no_data(deck, _content_slide(deck, title, subtitle), ctx)
        return
    fmt = ctx.fmt
    headers = [ctx.t("col_asin"), ctx.t("col_product"), ctx.t("col_country"), ctx.t("col_price"),
               ctx.t("col_price_change"), ctx.t("col_bsr"), ctx.t("col_bsr_change"), ctx.t("col_rating")]
    for chunk in _chunks(competitors):
        rows = []
        for comp in chunk:
            name = " · ".join(part for part in (comp.get("brand"), comp.get("title")) if part)
            bsr_change = comp.get("bsr_change")
            rows.append([
                comp["asin"], truncate(name, 34), comp.get("marketplace") or EMPTY,
                fmt.currency(comp.get("price"), 2), fmt.percent_signed(comp.get("price_change_pct")),
                fmt.integer(comp.get("bsr")),
                EMPTY if bsr_change is None else f"{'+' if bsr_change > 0 else ''}{fmt.integer(bsr_change)}",
                fmt.number(comp.get("rating"), 1),
            ])
        slide = _content_slide(deck, title, subtitle)
        deck.table(slide, DeckTheme.MARGIN, _TOP, headers, rows, [1.5, 3.3, 0.9, 1.3, 1.3, 1.3, 1.3, 1.7])


def _insights(deck, ctx: _Context) -> None:
    insights = ctx.insights[:MAX_INSIGHTS]  # rule_insights and build_insights never return more
    ai = any(insight.source == "ai" for insight in insights)
    slide = _content_slide(deck, ctx.t("insights_title"),
                           ctx.t("insights_subtitle_ai" if ai else "insights_subtitle_rules"))
    if not insights:
        _no_data(deck, slide, ctx)
        return
    gap, per_row = 0.3, 3
    card_w = (DeckTheme.content_w() - gap * (per_row - 1)) / per_row
    card_h = 2.6
    for idx, insight in enumerate(insights):
        row, col = divmod(idx, per_row)
        x, y = DeckTheme.MARGIN + col * (card_w + gap), 1.6 + row * (card_h + 0.2)
        # Like DeckBuilder.callout, with room for a two-line title.
        deck.rect(slide, x, y + 0.07, card_w, card_h - 0.07, DeckTheme.SURFACE, line=DeckTheme.HAIRLINE)
        deck.rect(slide, x, y, card_w, 0.07, DeckTheme.accent(idx))
        deck.text(slide, x + 0.25, y + 0.2, card_w - 0.5, 0.5, truncate(insight.title, 72),
                  size=DeckTheme.TYPE["body"], bold=True, color=DeckTheme.INK)
        deck.bullets(slide, x + 0.25, y + 0.9, card_w - 0.5, card_h - 1.05,
                     [truncate(insight.body, 300),
                      f"{ctx.t('action_prefix')}: {truncate(insight.action, 170)}"],
                     size=DeckTheme.TYPE["caption"] + 1)


def _notes(deck, ctx: _Context) -> None:
    slide = _content_slide(deck, ctx.t("notes_title"), ctx.t("notes_subtitle"))
    gaps = ctx.data.data_gaps[:12] or [ctx.t("no_gaps")]
    deck.callout(slide, DeckTheme.MARGIN, 1.6, _HALF_W, 5.2, ctx.t("gaps_heading"), gaps,
                 accent=DeckTheme.ORANGE)
    sources = [ctx.t(key) for key in ("source_sales", "source_ads", "source_returns", "source_terms",
                                      "source_competitors", "source_catalogue", "source_estimates")]
    deck.callout(slide, DeckTheme.MARGIN + _HALF_W + 0.3, 1.6, _HALF_W, 5.2,
                 ctx.t("sources_heading"), sources, accent=DeckTheme.STEEL_BLUE)


_SLIDES = (_cover, _kpis, _trend, _asins, _catalogue, _search_terms, _competitors, _insights, _notes)


def build_quarterly_deck(data: "QuarterData", insights: list["Insight"]) -> bytes:
    """The quarterly review as PPTX bytes."""
    from app.services.quarterly_report.data import previous_quarter, quarter_bounds, quarter_label

    scope = data.scope
    prev_year, prev_q = previous_quarter(scope.year, scope.quarter)
    ctx = _Context(
        data=data,
        insights=list(insights),
        fmt=Formatter(scope.language),
        current=quarter_label(scope.year, scope.quarter),
        previous=quarter_label(prev_year, prev_q),
        last_year=quarter_label(scope.year - 1, scope.quarter),
        in_progress=quarter_bounds(scope.year, scope.quarter)[1] >= date.today(),
    )
    deck = DeckBuilder(brand=" · ".join(part for part in (scope.brand, ctx.current) if part))
    for render in _SLIDES:
        render(deck, ctx)
    return deck.to_bytes()
