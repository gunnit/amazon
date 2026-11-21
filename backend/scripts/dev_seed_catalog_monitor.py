"""Seed a local database with a demo catalogue for the catalogue monitor and the quarterly report (R1-R5).

Local development only: it refuses to run unless DATABASE_URL points at localhost,
and it never calls Amazon. Every Amazon answer comes from the fixture directory it
writes, read by ``FixtureClient`` (app/services/catalog_monitor/fixture_client.py).

What it creates; a re-run resets the demo to the same state:

* organization "TEST Demo" and one admin (email and password from --email and
  --password, or SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD; only the email is printed);
* seller account "TEST Seller IT" (seller id TESTSELLER) with 12 products
  B0TEST0001..B0TEST0012 (brands TESTBRAND and TESTBRAND2, two categories, one
  variation family: parent B0TEST0010 with children B0TEST0011 and B0TEST0012),
  nine months of daily sales (per ASIN plus the daily total row), Sponsored Products
  campaigns, returns and Brand Analytics search terms;
* vendor account "TEST Vendor IT" (vendor code TESTVENDOR) with B0TEST0001..B0TEST0004:
  the first three have vendor SKUs, so their writes are checked through Listings
  Items; B0TEST0004 has none, so its writes become "file only";
* two tracked competitors with price and BSR history;
* the fixture directory: Catalog and Listings payloads, one product type schema per
  product type, PNG images (one main image fills 60% of the frame, one sits on grey).

Then it checks each account's Amazon access, scans both accounts, approves the live
content as baseline, changes the fixtures the way a third party would (title of
B0TEST0002, a bullet of B0TEST0003, image order of B0TEST0004, child B0TEST0012
detached from its parent), scans again and prints the traffic lights and anomalies.

    cd backend
    set -a; . var/dev.env; set +a   # DATABASE_URL, SEED_ADMIN_EMAIL, SEED_ADMIN_PASSWORD, ...
    .venv/bin/python scripts/dev_seed_catalog_monitor.py

var/ is gitignored: keep the local secrets there, with TZ=UTC as in production
(timestamps come from naive datetime.utcnow(), read as local time). Start the API with
DEV_FIXTURE_AMAZON_DIR set to the same directory (default var/dev_fixtures) so
"Scan now", restores and submissions keep answering from the fixtures, and on port
8000, where the fixture image URLs point.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import re
import shutil
import sys
import zlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw  # noqa: E402
from sqlalchemy import delete, func, insert, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.core.security import get_password_hash  # noqa: E402
from app.models.advertising import (  # noqa: E402
    AdvertisingCampaign,
    AdvertisingMetrics,
    AdvertisingMetricsByAsin,
)
from app.models.amazon_account import AccountType, AmazonAccount  # noqa: E402
from app.models.brand_search_term import BrandSearchTerm  # noqa: E402
from app.models.catalog_monitor import (  # noqa: E402
    CatalogAnomaly,
    CatalogApiCapability,
    CatalogChangeRequest,
    ImageCheck,
    ListingContentBaseline,
    ListingContentVersion,
    ListingQualityRule,
    ProductTypeDefinitionCache,
    VariationFamilyBaseline,
)
from app.models.competitor import Competitor, CompetitorHistory  # noqa: E402
from app.models.listing_quality import ListingQualitySnapshot  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.returns_data import ReturnData  # noqa: E402
from app.models.sales_data import SalesData  # noqa: E402
from app.models.user import Organization, OrganizationMember, User, UserRole  # noqa: E402
from app.services.catalog_monitor.baselines import approve_live_as_baseline  # noqa: E402
from app.services.catalog_monitor.capabilities import check_account_capabilities  # noqa: E402
from app.services.catalog_monitor.fixture_client import IMAGES_ROUTE, FixtureClient  # noqa: E402
from app.services.catalog_monitor.repository import CatalogMonitorRepository  # noqa: E402
from app.services.catalog_monitor.scanner import CatalogScanService  # noqa: E402
from app.services.data_extraction import DAILY_TOTAL_ASIN  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_DIR = BACKEND_DIR / "var" / "dev_fixtures"
DEFAULT_IMAGE_BASE_URL = f"http://127.0.0.1:8000{IMAGES_ROUTE}"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
MP = "APJ6JRA9NG5V4"  # Amazon.it
LANG = "it_IT"
SALES_DAYS = 275  # about nine months
SEARCH_TERM_WEEKS = 8
SELLER_NAME = "TEST Seller IT"
VENDOR_NAME = "TEST Vendor IT"
VENDOR_CODE = "TESTVENDOR"
# Vendor products and their vendor SKU; None: no SKU, so writes are file only.
VENDOR_SKUS: dict[str, Optional[str]] = {
    "B0TEST0001": "TEST-VSKU-001",
    "B0TEST0002": "TEST-VSKU-002",
    "B0TEST0003": "TEST-VSKU-003",
    "B0TEST0004": None,
}
UTENSILS = "Utensili da cucina"
STORAGE = "Conservazione alimenti"
REQUIRED_BY_TYPE = {
    "KITCHEN": ["brand", "bullet_point", "item_name", "item_type_keyword", "material"],
    "FOOD_STORAGE_CONTAINER": [
        "brand", "bullet_point", "capacity", "item_name", "item_type_keyword", "material",
    ],
}
RECOMMENDED = [
    "color", "size", "material", "item_dimensions", "item_weight",
    "age_range_description", "number_of_items", "included_components",
]


# ---- the demo catalogue ----


@dataclass(frozen=True)
class DemoProduct:
    asin: str
    sku: str
    brand: str
    category: str
    product_type: str
    title: str
    bullets: tuple[str, ...]
    price: float
    units_per_day: float  # 0 = not sold (a variation parent)
    color: str
    material: str = "Acciaio inox"
    description: Optional[str] = None
    highlights: Optional[str] = None
    other_images: int = 7  # besides the main image
    main_image: str = "white"  # white (90% fill), small (60% fill), grey (grey background)
    aplus_modules: int = 4
    backend_keywords: Optional[str] = None
    keyword: Optional[str] = None  # set by the operator; else from Brand Analytics
    attributes: str = "full"  # full | recommended_missing | required_missing
    classified: bool = True
    node: str = "Utensili"
    parent: Optional[str] = None
    children: tuple[str, ...] = ()


def _desc(*sentences: str) -> str:
    return " ".join(sentences)


_LUNCH_BOX_BULLETS = (
    "Lunch box in acciaio inox 18/10 a due scomparti: primo e secondo restano separati",
    "Guarnizione in silicone a tenuta stagna, niente perdite di sugo nella borsa",
    "Posate in acciaio incluse, alloggiate nel coperchio",
    "Senza plastica a contatto con il cibo, non trattiene odori",
    "Lavabile in lavastoviglie, coperchio compreso",
)
_LUNCH_BOX_DESC = _desc(
    "La lunch box in acciaio di TESTBRAND2 porta in ufficio o a scuola un pasto completo:",
    "due scomparti a tenuta, posate incluse e una guarnizione che non lascia uscire nulla.",
    "L'acciaio inox 18/10 non trattiene odori e dura anni; tutto va in lavastoviglie.",
)

PRODUCTS: tuple[DemoProduct, ...] = (
    DemoProduct(
        asin="B0TEST0001", sku="TEST-SKU-001", brand="TESTBRAND", category=UTENSILS,
        product_type="KITCHEN", node="Mestoli", color="Rosso", material="Silicone",
        title="TESTBRAND Mestolo in silicone 32 cm, resistente fino a 230 °C",
        bullets=(
            "Mestolo in silicone alimentare senza BPA, non graffia pentole antiaderenti",
            "Resiste al calore fino a 230 °C: ideale per zuppe, sughi e brodi bollenti",
            "Anima in acciaio inox per una presa stabile anche con liquidi densi",
            "Manico lungo 32 cm con foro per appenderlo, comodo da riporre",
            "Lavabile in lavastoviglie, non trattiene odori né macchie",
        ),
        description=_desc(
            "Il mestolo in silicone TESTBRAND è pensato per chi cucina ogni giorno:",
            "la testa morbida non graffia le padelle antiaderenti, l'anima in acciaio",
            "lo rende rigido quanto serve e il silicone alimentare resiste fino a 230 °C.",
            "Si lava in lavastoviglie e si appende grazie al foro sul manico.",
        ),
        highlights="Silicone senza BPA, fino a 230 °C, lavabile in lavastoviglie",
        price=12.90, units_per_day=14, aplus_modules=5,
        backend_keywords=(
            "mestolo silicone cucina zuppa brodo sugo antiaderente resistente calore "
            "senza bpa utensili cucina mestolo grande regalo cucina"
        ),
        keyword="mestolo in silicone",
    ),
    DemoProduct(
        asin="B0TEST0002", sku="TEST-SKU-002", brand="TESTBRAND", category=UTENSILS,
        product_type="KITCHEN", node="Spatole", color="Naturale", material="Legno di faggio",
        title="TESTBRAND Set di 3 spatole in legno di faggio per cucina",
        bullets=(
            "Tre spatole in legno di faggio massello: piatta, forata e a cucchiaio",
            "Il legno non graffia pentole e padelle e non conduce il calore",
            "Finitura con olio alimentare, senza vernici",
            "Lunghezza 30 cm, per mescolare anche nelle pentole alte",
            "Lavare a mano e asciugare subito per conservarle a lungo",
        ),
        description=_desc(
            "Le spatole in legno TESTBRAND sono ricavate da faggio massello e trattate",
            "solo con olio alimentare. Tre forme per mescolare, girare e servire, lunghe",
            "30 cm per arrivare sul fondo delle pentole alte senza scottarsi le dita.",
        ),
        highlights=(
            "Set da tre spatole in legno di faggio massello, piatta, forata e a cucchiaio, "
            "finitura a olio alimentare senza vernici, lunghe 30 cm"
        ),
        price=15.50, units_per_day=9, aplus_modules=4,
        backend_keywords=(
            "spatole legno cucina set mestoli legno faggio utensili legno cucina "
            "cucchiaio legno spatola forata"
        ),
        keyword="spatole in legno",
    ),
    DemoProduct(
        asin="B0TEST0003", sku="TEST-SKU-003", brand="TESTBRAND", category=UTENSILS,
        product_type="KITCHEN", node="Fruste", color="Argento",
        title="TESTBRAND Frusta in acciaio inox 30 cm per panna, albumi e pastelle",
        bullets=(
            "Frusta in acciaio inox con 11 fili rinforzati per montare panna e albumi",
            "Manico ergonomico pieno, bilanciato per non stancare il polso",
            "Lunga 30 cm, adatta a ciotole capienti",
            "Non si arrugginisce e non si deforma nel tempo",
            "Lavabile in lavastoviglie",
        ),
        description=_desc(
            "La frusta in acciaio inox TESTBRAND monta panna e albumi in pochi minuti grazie",
            "agli undici fili rinforzati. Il manico pieno e bilanciato non affatica il polso",
            "e l'acciaio non arrugginisce: va in lavastoviglie senza problemi.",
        ),
        price=9.90, units_per_day=11, other_images=6, aplus_modules=4,
        backend_keywords="frusta cucina acciaio montare panna albumi frustino",
        attributes="recommended_missing",
    ),
    DemoProduct(
        asin="B0TEST0004", sku="TEST-SKU-004", brand="TESTBRAND", category=UTENSILS,
        product_type="KITCHEN", node="Pinze da cucina", color="Nero",
        title="TESTBRAND Pinza da cucina in acciaio con punte in silicone, set da 2",
        bullets=(
            "Due pinze da cucina, 23 e 30 cm, per griglia, padella e insalate",
            "Punte in silicone che non graffiano i rivestimenti antiaderenti",
            "Blocco a scorrimento per chiuderle e riporle in poco spazio",
            "Acciaio inox resistente e facile da pulire",
            "Lavabili in lavastoviglie",
        ),
        description=_desc(
            "Le pinze da cucina TESTBRAND hanno punte in silicone che proteggono le padelle",
            "antiaderenti e un blocco a scorrimento che le chiude per riporle nel cassetto.",
            "Due misure, 23 e 30 cm, per la griglia, la padella e per servire le insalate.",
        ),
        price=13.90, units_per_day=8, aplus_modules=3,
        backend_keywords=(
            "pinza cucina pinze barbecue griglia pinza insalata silicone acciaio "
            "pinze cucina antiaderente"
        ),
        keyword="pinza da cucina",
    ),
    DemoProduct(
        asin="B0TEST0005", sku="TEST-SKU-005", brand="TESTBRAND", category=UTENSILS,
        product_type="KITCHEN", node="Grattugie", color="Argento",
        title=(
            "TESTBRAND Grattugia a 4 lati in acciaio inossidabile con manico antiscivolo "
            "e contenitore raccogli formaggio, ideale per parmigiano, verdure e agrumi"
        ),
        bullets=(
            "Quattro superfici: fine, media, grossa e a lamelle",
            "Contenitore trasparente che raccoglie il formaggio grattugiato",
            "Manico antiscivolo e base gommata per una presa sicura",
            "Lame in acciaio inossidabile affilate a lungo",
            "Coperchio salvafreschezza per conservare il formaggio in frigo",
        ),
        description=_desc(
            "La grattugia TESTBRAND a quattro lati ha un contenitore che raccoglie il",
            "formaggio e lo conserva in frigo con il suo coperchio. Lame in acciaio",
            "inossidabile, base gommata e manico antiscivolo per grattugiare in sicurezza.",
        ),
        price=18.90, units_per_day=7, other_images=5, main_image="small", aplus_modules=0,
        backend_keywords=(
            "grattugia formaggio parmigiano grattugia 4 lati contenitore grattugia verdure "
            "zester agrumi grattugia acciaio inox"
        ),
        keyword="grattugia a 4 lati",
    ),
    DemoProduct(
        asin="B0TEST0006", sku="TEST-SKU-006", brand="TESTBRAND", category=UTENSILS,
        product_type="KITCHEN", node="Taglieri", color="Naturale", material="Bambù",
        title="TESTBRAND Tagliere in bambù 40 x 30 cm con scanalatura raccogli succhi",
        bullets=(
            "Tagliere in bambù naturale da 40 x 30 cm",
            "Scanalatura perimetrale che trattiene i succhi di carne e frutta",
            "Bambù compatto che non rovina il filo dei coltelli",
            "Maniglie laterali per spostarlo e servire in tavola",
            "Lavare a mano, oliare ogni tanto",
        ),
        price=22.50, units_per_day=6, other_images=3, main_image="grey", aplus_modules=0,
        backend_keywords="tagliere bambu legno cucina tagliere grande carne",
        keyword="tagliere in bambù",
    ),
    DemoProduct(
        asin="B0TEST0007", sku="TEST-SKU-007", brand="TESTBRAND", category=UTENSILS,
        product_type="KITCHEN", node="Coltelli", color="Nero",
        title="Coltello da pane 20 cm con lama seghettata in acciaio inox",
        bullets=(
            "Lama seghettata da 20 cm che taglia il pane senza schiacciarlo",
            "Manico in polipropilene antiscivolo",
        ),
        description=_desc(
            "Coltello da pane con lama seghettata da 20 cm in acciaio inox: taglia crosta",
            "e mollica senza schiacciare la pagnotta. Manico antiscivolo in polipropilene,",
            "comodo anche con le mani bagnate. Si lava a mano.",
        ),
        price=16.90, units_per_day=5, other_images=4, aplus_modules=0,
        backend_keywords=(
            "coltello pane coltello seghettato coltello cucina lama seghettata coltello "
            "pane professionale coltello pane acciaio coltello per pane casereccio "
            "coltello baguette coltello torta coltello panettone coltello pane lungo "
            "coltello da cucina seghettato regalo cuoco accessori cucina"
        ),
        keyword="coltello da pane",
    ),
    DemoProduct(
        asin="B0TEST0008", sku="TEST-SKU-008", brand="TESTBRAND", category=STORAGE,
        product_type="FOOD_STORAGE_CONTAINER", node="Contenitori", color="Trasparente",
        material="Vetro borosilicato",
        title="TESTBRAND Contenitori ermetici in vetro per alimenti, set da 5 con coperchi",
        bullets=(
            "Cinque contenitori in vetro borosilicato da 370 a 1520 ml",
            "Coperchi ermetici con quattro clip e guarnizione in silicone",
            "Vanno in forno, microonde, freezer e lavastoviglie",
            "Il vetro non assorbe odori né macchie di sugo",
            "Impilabili per risparmiare spazio in frigo",
        ),
        description=_desc(
            "I contenitori ermetici in vetro TESTBRAND conservano gli avanzi in frigo e li",
            "scaldano in forno o nel microonde senza cambiare contenitore. Il vetro",
            "borosilicato non trattiene odori e i coperchi a quattro clip non perdono.",
        ),
        price=29.90, units_per_day=10, aplus_modules=2,
        backend_keywords=(
            "contenitori vetro alimenti ermetici set contenitori frigo forno microonde "
            "porta pranzo vetro"
        ),
        attributes="recommended_missing",
    ),
    DemoProduct(
        asin="B0TEST0009", sku="TEST-SKU-009", brand="TESTBRAND2", category=STORAGE,
        product_type="FOOD_STORAGE_CONTAINER", node="Barattoli", color="Trasparente",
        material="Vetro",
        title="TESTBRAND2 Barattoli per spezie in vetro con coperchio in bambù, 12 pezzi",
        bullets=(
            "Dodici barattoli in vetro da 120 ml per spezie ed erbe",
            "Coperchi in bambù con guarnizione",
            "Etichette e pennarello inclusi",
            "Imbuto per riempirli senza sprechi",
            "Base piatta, stanno in qualsiasi cassetto",
        ),
        description=_desc(
            "Dodici barattoli per spezie in vetro con coperchio in bambù, etichette da",
            "scrivere e un imbuto per riempirli. Tengono in ordine il cassetto delle spezie",
            "e conservano gli aromi lontano dall'umidità.",
        ),
        price=24.90, units_per_day=6, other_images=5, aplus_modules=0,
        attributes="required_missing", classified=False,
        keyword="barattoli per spezie",
    ),
    DemoProduct(
        asin="B0TEST0010", sku="TEST-SKU-010", brand="TESTBRAND2", category=STORAGE,
        product_type="FOOD_STORAGE_CONTAINER", node="Porta pranzo", color="Assortiti",
        title="TESTBRAND2 Lunch box in acciaio inox a 2 scomparti con posate",
        bullets=_LUNCH_BOX_BULLETS, description=_LUNCH_BOX_DESC,
        price=27.90, units_per_day=0, other_images=4, aplus_modules=4,
        backend_keywords=(
            "lunch box acciaio porta pranzo acciaio inox schiscetta contenitore pranzo "
            "ufficio scuola"
        ),
        keyword="lunch box in acciaio",
        children=("B0TEST0011", "B0TEST0012"),
    ),
    DemoProduct(
        asin="B0TEST0011", sku="TEST-SKU-011", brand="TESTBRAND2", category=STORAGE,
        product_type="FOOD_STORAGE_CONTAINER", node="Porta pranzo", color="Verde salvia",
        title="TESTBRAND2 Lunch box in acciaio inox a 2 scomparti, verde salvia",
        bullets=_LUNCH_BOX_BULLETS, description=_LUNCH_BOX_DESC,
        price=27.90, units_per_day=9, aplus_modules=4,
        backend_keywords=(
            "lunch box acciaio porta pranzo acciaio inox schiscetta contenitore pranzo "
            "ufficio scuola verde"
        ),
        keyword="lunch box in acciaio", parent="B0TEST0010",
    ),
    DemoProduct(
        asin="B0TEST0012", sku="TEST-SKU-012", brand="TESTBRAND2", category=STORAGE,
        product_type="FOOD_STORAGE_CONTAINER", node="Porta pranzo", color="Blu notte",
        title="TESTBRAND2 Lunch box in acciaio inox a 2 scomparti, blu notte",
        bullets=_LUNCH_BOX_BULLETS, description=_LUNCH_BOX_DESC,
        price=27.90, units_per_day=7, aplus_modules=4,
        backend_keywords=(
            "lunch box acciaio porta pranzo acciaio inox schiscetta contenitore pranzo "
            "ufficio scuola blu"
        ),
        keyword="lunch box in acciaio", parent="B0TEST0010",
    ),
)
PRODUCT_BY_ASIN = {p.asin: p for p in PRODUCTS}

COMPETITORS = (
    ("B0TEST0901", "RIVALCO", "RIVALCO Mestolo in silicone 30 cm resistente al calore", 10.90, 1800),
    ("B0TEST0902", "RIVALCO", "RIVALCO Contenitori in vetro per alimenti, set da 4", 26.90, 950),
)
TITLE_BY_ASIN = {**{p.asin: p.title for p in PRODUCTS}, **{c[0]: c[2] for c in COMPETITORS}}
# (term, search frequency rank, [(ASIN, click share)])
SEARCH_TERMS = (
    ("mestolo silicone", 2150, [("B0TEST0001", 0.21), ("B0TEST0901", 0.17)]),
    ("frusta in acciaio", 8420, [("B0TEST0003", 0.24), ("B0TEST0901", 0.08)]),
    ("spatole legno cucina", 5310, [("B0TEST0002", 0.18)]),
    ("contenitori vetro alimenti", 1240, [("B0TEST0902", 0.22), ("B0TEST0008", 0.15)]),
    ("lunch box acciaio", 3980, [("B0TEST0011", 0.19), ("B0TEST0012", 0.11)]),
    ("grattugia formaggio", 2760, [("B0TEST0005", 0.12)]),
)


# ---- configuration ----


@dataclass
class SeedConfig:
    admin_email: str
    admin_password: str
    fixture_dir: Path = DEFAULT_FIXTURE_DIR
    image_base_url: str = DEFAULT_IMAGE_BASE_URL
    org_name: str = "TEST Demo"
    org_slug: str = "test-demo"
    today: date = field(default_factory=date.today)


@dataclass
class Seeded:
    organization: Organization
    user: User
    seller: AmazonAccount
    vendor: AmazonAccount


def refuse_non_local(database_url: str) -> None:
    """Exit unless the database is on this machine: the seed rewrites demo data."""
    host = make_url(database_url).host or ""
    if host not in LOCAL_HOSTS:
        raise SystemExit(
            f"Refusing to seed: DATABASE_URL host is {host or '(none)'!r}, not localhost."
        )


# ---- fixture files ----


def _text(value: str) -> list[dict]:
    return [{"value": value, "language_tag": LANG, "marketplace_id": MP}]


def _value(value: Any, **extra: Any) -> list[dict]:
    return [{"value": value, "marketplace_id": MP, **extra}]


def _attributes(p: DemoProduct) -> dict:
    attrs: dict[str, Any] = {
        "item_name": _text(p.title),
        "brand": _text(p.brand),
        "bullet_point": [_text(b)[0] for b in p.bullets],
        "item_type_keyword": _value(re.sub(r"[^a-z]+", "-", p.node.lower()).strip("-")),
        "list_price": [{"value": p.price, "currency": "EUR", "marketplace_id": MP}],
        "color": _text(p.color),
        "size": _text("Standard"),
        "number_of_items": _value(1),
        "item_weight": _value(0.35, unit="kilograms"),
        "item_dimensions": [{
            "length": {"value": 32, "unit": "centimeters"},
            "width": {"value": 9, "unit": "centimeters"},
            "height": {"value": 5, "unit": "centimeters"},
            "marketplace_id": MP,
        }],
        "age_range_description": _text("Adulto"),
        "included_components": _text("1 pezzo"),
    }
    if p.attributes != "required_missing":
        attrs["material"] = _text(p.material)
    if p.product_type == "FOOD_STORAGE_CONTAINER":
        attrs["capacity"] = _value(750, unit="milliliters")
    if p.attributes in ("recommended_missing", "required_missing"):
        attrs.pop("age_range_description")
        attrs.pop("included_components")
    if p.description:
        attrs["product_description"] = _text(p.description)
    if p.highlights:
        attrs["item_highlights"] = _text(p.highlights)
    return attrs


def _image_urls(p: DemoProduct, base_url: str) -> list[tuple[str, str]]:
    images = [("MAIN", f"{base_url}/{p.asin}-main.png")]
    images += [(f"PT{n:02d}", f"{base_url}/{p.asin}-pt{n:02d}.png") for n in range(1, p.other_images + 1)]
    return images


def _classification(p: DemoProduct) -> list[dict]:
    if not p.classified:
        return []
    return [{
        "marketplaceId": MP,
        "classifications": [{
            "displayName": p.node,
            "classificationId": str(zlib.crc32(p.node.encode())),
            "parent": {
                "displayName": p.category,
                "classificationId": str(zlib.crc32(p.category.encode())),
                "parent": {"displayName": "Casa e cucina", "classificationId": "524015031"},
            },
        }],
    }]


def _relationships(p: DemoProduct) -> list[dict]:
    rels = []
    theme = {"attributes": ["color"], "theme": "COLOR"}
    if p.children:
        rels.append({"type": "VARIATION", "childAsins": list(p.children), "variationTheme": theme})
    if p.parent:
        rels.append({"type": "VARIATION", "parentAsins": [p.parent], "variationTheme": theme})
    return [{"marketplaceId": MP, "relationships": rels}]


def catalog_payload(p: DemoProduct, image_base_url: str) -> dict:
    """A Catalog Items v2022-04-01 payload with every section the monitor reads."""
    return {
        "asin": p.asin,
        "attributes": _attributes(p),
        "classifications": _classification(p),
        "identifiers": [{"marketplaceId": MP, "identifiers": []}],
        "images": [{
            "marketplaceId": MP,
            "images": [
                {"variant": v, "link": url, "height": 1000, "width": 1000}
                for v, url in _image_urls(p, image_base_url)
            ],
        }],
        "productTypes": [{"marketplaceId": MP, "productType": p.product_type}],
        "relationships": _relationships(p),
        "salesRanks": [],
        "summaries": [{
            "marketplaceId": MP, "brand": p.brand, "itemName": p.title,
            "itemClassification": "VARIATION_PARENT" if p.children else "BASE_PRODUCT",
        }],
    }


def listing_payload(p: DemoProduct, sku: Optional[str] = None) -> dict:
    """A Listings Items payload (the seller's SKU, or ``sku``): backend keywords, status, issues."""
    attributes: dict[str, Any] = {"item_name": _text(p.title), "brand": _text(p.brand)}
    if p.backend_keywords:
        attributes["generic_keyword"] = _text(p.backend_keywords)
    issues = []
    if p.attributes == "required_missing":
        issues.append({
            "code": "90000900",
            "message": "Manca un attributo obbligatorio: material",
            "severity": "WARNING",
            "attributeNames": ["material"],
        })
    return {
        "sku": sku or p.sku,
        "summaries": [{
            "marketplaceId": MP,
            "asin": p.asin,
            "productType": p.product_type,
            "conditionType": "new_new",
            "status": ["DISCOVERABLE"] if p.children else ["BUYABLE", "DISCOVERABLE"],
            "itemName": p.title,
        }],
        "attributes": attributes,
        "issues": issues,
    }


def product_type_schema(product_type: str) -> dict:
    required = REQUIRED_BY_TYPE[product_type] + ["externally_assigned_product_identifier", "list_price"]
    names = sorted(set(required) | set(RECOMMENDED) | {
        "product_description", "generic_keyword", "item_highlights",
        "main_product_image_locator", "other_product_image_locator_1",
    })
    return {
        "$schema": "https://schemas.amazon.com/selling-partners/definitions/product-types/meta-schema/v1",
        "title": product_type,
        "type": "object",
        "required": sorted(required),
        "properties": {name: {"title": name, "type": "array"} for name in names},
    }


def _main_png(path: Path, style: str, color: tuple[int, int, int]) -> None:
    background = (200, 200, 200) if style == "grey" else (255, 255, 255)
    img = Image.new("RGB", (1000, 1000), background)
    draw = ImageDraw.Draw(img)
    span = 600 if style == "small" else 900
    top = (1000 - span) // 2
    left, right = 330, 670
    draw.rounded_rectangle((left, top, right, top + span), radius=60, fill=color)
    draw.ellipse((left + 40, top + 40, right - 40, top + 300), fill=tuple(max(0, c - 60) for c in color))
    img.save(path, format="PNG")


def _other_png(path: Path, number: int, color: tuple[int, int, int]) -> None:
    img = Image.new("RGB", (600, 600), (245, 241, 232))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 420, 600, 600), fill=(222, 214, 196))
    draw.rounded_rectangle((180 + number * 6, 120, 420 - number * 6, 470), radius=30, fill=color)
    draw.text((24, 24), f"Immagine {number}", fill=(60, 60, 60))
    img.save(path, format="PNG")


def _color_of(p: DemoProduct) -> tuple[int, int, int]:
    rng = random.Random(p.asin)
    return (rng.randint(40, 200), rng.randint(40, 200), rng.randint(40, 200))


def write_fixtures(config: SeedConfig) -> None:
    """(Re)write the fixture directory from scratch: catalog, listings, schemas, images."""
    root = config.fixture_dir
    for folder in ("catalog", "listings", "product_types", "feeds", "images"):
        shutil.rmtree(root / folder, ignore_errors=True)
        (root / folder).mkdir(parents=True, exist_ok=True)
    for p in PRODUCTS:
        _dump(root / "catalog" / f"{p.asin}.json", catalog_payload(p, config.image_base_url))
        _dump(root / "listings" / f"{p.sku}.json", listing_payload(p))
        color = _color_of(p)
        _main_png(root / "images" / f"{p.asin}-main.png", p.main_image, color)
        for n in range(1, p.other_images + 1):
            _other_png(root / "images" / f"{p.asin}-pt{n:02d}.png", n, color)
    for asin, sku in VENDOR_SKUS.items():
        if sku:
            _dump(root / "listings" / f"{sku}.json", listing_payload(PRODUCT_BY_ASIN[asin], sku))
    for product_type in REQUIRED_BY_TYPE:
        _dump(root / "product_types" / f"{product_type}.json", product_type_schema(product_type))
    _dump(root / "client.json", {
        "vendor_code": VENDOR_CODE,
        "aplus_modules": {p.asin: p.aplus_modules for p in PRODUCTS},
    })


def _dump(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def mutate_fixtures(fixture_dir: Path) -> None:
    """What a third party or Amazon might do to live pages after the baseline."""
    catalog = fixture_dir / "catalog"

    two = _load(catalog / "B0TEST0002.json")
    title = "Spatole legno cucina 3 pezzi OFFERTA spedizione veloce"
    two["attributes"]["item_name"] = _text(title)
    two["summaries"][0]["itemName"] = title
    _dump(catalog / "B0TEST0002.json", two)

    three = _load(catalog / "B0TEST0003.json")
    three["attributes"]["bullet_point"] = three["attributes"]["bullet_point"][:-1]
    _dump(catalog / "B0TEST0003.json", three)

    four = _load(catalog / "B0TEST0004.json")
    images = four["images"][0]["images"]
    links = {i["variant"]: i["link"] for i in images}
    for image in images:
        if image["variant"] == "PT01":
            image["link"] = links["PT02"]
        elif image["variant"] == "PT02":
            image["link"] = links["PT01"]
    _dump(catalog / "B0TEST0004.json", four)

    child = _load(catalog / "B0TEST0012.json")
    child["relationships"] = [{"marketplaceId": MP, "relationships": []}]
    _dump(catalog / "B0TEST0012.json", child)
    parent = _load(catalog / "B0TEST0010.json")
    for rel in parent["relationships"][0]["relationships"]:
        rel["childAsins"] = [a for a in rel.get("childAsins") or [] if a != "B0TEST0012"]
    _dump(catalog / "B0TEST0010.json", parent)


def fixture_client_factory(fixture_dir: Path) -> Callable[[Any, Any], FixtureClient]:
    def factory(account: Any, organization: Any) -> FixtureClient:
        return FixtureClient(str(fixture_dir), account.marketplace_id, account.account_type.value)
    return factory


def local_image_fetch(fixture_dir: Path, image_base_url: str) -> Callable[[str], Awaitable[bytes]]:
    """Image download for scans run here, with no API serving the fixture images."""
    prefix = image_base_url.rstrip("/") + "/"

    async def fetch(url: str) -> bytes:
        if not url.startswith(prefix):
            raise ValueError("not a fixture image")
        return (fixture_dir / "images" / url[len(prefix):]).read_bytes()

    return fetch


# ---- database rows ----


async def _one_or_none(db: AsyncSession, query) -> Any:
    return (await db.execute(query)).scalar_one_or_none()


async def _organization_and_admin(db: AsyncSession, config: SeedConfig) -> tuple[Organization, User]:
    org = await _one_or_none(db, select(Organization).where(Organization.slug == config.org_slug))
    if org is None:
        org = Organization(name=config.org_name, slug=config.org_slug, settings={"timezone": "Europe/Rome"})
        db.add(org)
        await db.flush()
    user = await _one_or_none(db, select(User).where(User.email == config.admin_email))
    if user is None:
        user = User(email=config.admin_email, full_name="Demo Admin", is_active=True,
                    hashed_password=get_password_hash(config.admin_password))
        db.add(user)
        await db.flush()
    else:
        user.hashed_password = get_password_hash(config.admin_password)
        user.is_active = True
    member = await _one_or_none(db, select(OrganizationMember).where(
        OrganizationMember.user_id == user.id, OrganizationMember.organization_id == org.id
    ))
    if member is None:
        db.add(OrganizationMember(user_id=user.id, organization_id=org.id, role=UserRole.ADMIN))
    else:
        member.role = UserRole.ADMIN
    return org, user


async def _account(db: AsyncSession, org: Organization, name: str, account_type: AccountType,
                   seller_id: Optional[str]) -> AmazonAccount:
    account = await _one_or_none(db, select(AmazonAccount).where(
        AmazonAccount.organization_id == org.id, AmazonAccount.account_name == name
    ))
    if account is None:
        account = AmazonAccount(organization_id=org.id, account_name=name, account_type=account_type,
                                marketplace_id=MP, marketplace_country="IT")
        db.add(account)
    account.seller_id = seller_id
    account.is_active = True
    await db.flush()
    return account


async def _products(db: AsyncSession, account: AmazonAccount, products: list[DemoProduct],
                    skus: dict[str, Optional[str]]) -> None:
    existing = {
        p.asin: p for p in (await db.execute(
            select(Product).where(Product.account_id == account.id)
        )).scalars().all()
    }
    for spec in products:
        row = existing.get(spec.asin)
        if row is None:
            row = Product(account_id=account.id, asin=spec.asin)
            db.add(row)
        row.sku = skus.get(spec.asin)
        row.title = spec.title
        row.brand = spec.brand
        row.category = spec.category
        row.subcategory = spec.node
        row.current_price = spec.price
        row.is_active = True
        row.is_available = True
        row.main_keyword = spec.keyword
        row.main_keyword_source = "manual" if spec.keyword else None
    await db.flush()


async def _reset_monitor(db: AsyncSession, org: Organization, account_ids: list, config: SeedConfig) -> None:
    """Forget earlier scans of the demo accounts so a re-run starts from the same state."""
    for model in (CatalogAnomaly, CatalogChangeRequest, ListingContentBaseline, ListingContentVersion,
                  VariationFamilyBaseline, ListingQualitySnapshot, CatalogApiCapability):
        await db.execute(delete(model).where(model.account_id.in_(account_ids)))
    await db.execute(delete(ListingQualityRule).where(ListingQualityRule.organization_id == org.id))
    await db.execute(delete(ImageCheck).where(ImageCheck.url.startswith(config.image_base_url)))
    await db.execute(delete(ProductTypeDefinitionCache).where(
        ProductTypeDefinitionCache.marketplace_id == MP,
        ProductTypeDefinitionCache.product_type.in_(list(REQUIRED_BY_TYPE)),
    ))


def _season(day: date) -> float:
    return {11: 1.35, 12: 1.5, 1: 0.85, 7: 0.9, 8: 0.85}.get(day.month, 1.0)


def _weekday(day: date) -> float:
    return {5: 1.15, 6: 1.2, 0: 0.95}.get(day.weekday(), 1.0)


def _sales_rows(account_id, start: date, days: int) -> tuple[list[dict], dict[tuple[str, date], int]]:
    rows: list[dict] = []
    units_by: dict[tuple[str, date], int] = {}
    for offset in range(days):
        day = start + timedelta(days=offset)
        trend = 1 + 0.2 * offset / days
        totals = {"units": 0, "sales": 0.0, "sessions": 0, "views": 0, "items": 0}
        for p in PRODUCTS:
            if not p.units_per_day:
                continue
            rng = random.Random(f"{p.asin}-{day.isoformat()}")
            units = max(0, round(p.units_per_day * _season(day) * _weekday(day) * trend
                                 * rng.uniform(0.7, 1.3)))
            sales = round(units * p.price, 2)
            sessions = units * rng.randint(7, 13) + rng.randint(5, 30)
            views = round(sessions * rng.uniform(1.2, 1.6))
            items = max(0, units - rng.randint(0, 2)) if units else 0
            units_by[(p.asin, day)] = units
            rows.append({
                "account_id": account_id, "date": day, "asin": p.asin, "sku": p.sku,
                "units_ordered": units, "units_ordered_b2b": 0, "ordered_product_sales": sales,
                "ordered_product_sales_b2b": 0, "total_order_items": items,
                "browser_sessions": sessions // 3, "mobile_sessions": sessions - sessions // 3,
                "page_views": views, "currency": "EUR",
            })
            totals["units"] += units
            totals["sales"] += sales
            totals["sessions"] += sessions
            totals["views"] += views
            totals["items"] += items
        rows.append({
            "account_id": account_id, "date": day, "asin": DAILY_TOTAL_ASIN, "sku": None,
            "units_ordered": totals["units"], "units_ordered_b2b": 0,
            "ordered_product_sales": round(totals["sales"], 2), "ordered_product_sales_b2b": 0,
            "total_order_items": totals["items"], "browser_sessions": totals["sessions"] // 3,
            "mobile_sessions": totals["sessions"] - totals["sessions"] // 3,
            "page_views": totals["views"], "currency": "EUR",
        })
    return rows, units_by


CAMPAIGNS = (
    ("TESTSP001", "SP - Utensili - Automatica", ("B0TEST0001", "B0TEST0002", "B0TEST0003", "B0TEST0004")),
    ("TESTSP002", "SP - Grattugie e taglieri - Manuale", ("B0TEST0005", "B0TEST0006", "B0TEST0007")),
    ("TESTSP003", "SP - Contenitori - Manuale", ("B0TEST0008", "B0TEST0009", "B0TEST0011", "B0TEST0012")),
)


async def _advertising(db: AsyncSession, account: AmazonAccount, units_by: dict, start: date,
                       days: int) -> None:
    await db.execute(delete(AdvertisingCampaign).where(AdvertisingCampaign.account_id == account.id))
    by_asin_rows: list[dict] = []
    metric_rows: list[dict] = []
    for campaign_id, name, asins in CAMPAIGNS:
        campaign = AdvertisingCampaign(account_id=account.id, campaign_id=campaign_id, campaign_name=name,
                                       campaign_type="sponsoredProducts", state="enabled",
                                       daily_budget=40, targeting_type="AUTO" if "Auto" in name else "MANUAL")
        db.add(campaign)
        await db.flush()
        for offset in range(days):
            day = start + timedelta(days=offset)
            day_total = {"impressions": 0, "clicks": 0, "cost": 0.0, "sales": 0.0, "units": 0}
            for asin in asins:
                rng = random.Random(f"ads-{asin}-{day.isoformat()}")
                ad_units = round(units_by.get((asin, day), 0) * rng.uniform(0.15, 0.3))
                sales = round(ad_units * PRODUCT_BY_ASIN[asin].price, 2)
                cost = round(max(sales, 4.0) * rng.uniform(0.18, 0.34), 2)
                clicks = max(1, round(cost / rng.uniform(0.45, 0.8)))
                impressions = round(clicks / rng.uniform(0.003, 0.006))
                by_asin_rows.append({
                    "account_id": account.id, "campaign_id": campaign.id, "asin": asin, "date": day,
                    "impressions": impressions, "clicks": clicks, "cost": cost,
                    "attributed_sales_7d": sales, "attributed_units_ordered_7d": ad_units,
                    "ctr": round(clicks / impressions, 4), "cpc": round(cost / clicks, 4),
                    "acos": round(cost / sales, 4) if sales else None,
                    "roas": round(sales / cost, 4) if cost else None,
                })
                for key, value in (("impressions", impressions), ("clicks", clicks), ("cost", cost),
                                   ("sales", sales), ("units", ad_units)):
                    day_total[key] += value
            cost, sales = round(day_total["cost"], 2), round(day_total["sales"], 2)
            metric_rows.append({
                "campaign_id": campaign.id, "date": day, "impressions": day_total["impressions"],
                "clicks": day_total["clicks"], "cost": cost,
                "attributed_sales_1d": round(sales * 0.8, 2), "attributed_sales_7d": sales,
                "attributed_sales_14d": round(sales * 1.05, 2), "attributed_sales_30d": round(sales * 1.08, 2),
                "attributed_units_ordered_1d": round(day_total["units"] * 0.8),
                "attributed_units_ordered_7d": day_total["units"],
                "attributed_units_ordered_14d": day_total["units"],
                "attributed_units_ordered_30d": day_total["units"],
                "ctr": round(day_total["clicks"] / day_total["impressions"], 4),
                "cpc": round(cost / day_total["clicks"], 4),
                "acos": round(cost / sales, 4) if sales else None,
                "roas": round(sales / cost, 4) if cost else None,
            })
    await db.execute(insert(AdvertisingMetrics), metric_rows)
    await db.execute(insert(AdvertisingMetricsByAsin), by_asin_rows)


def _return_rows(account_id, units_by: dict) -> list[dict]:
    reasons = ("DEFECTIVE", "NOT_AS_DESCRIBED", "UNWANTED_ITEM", "DAMAGED_BY_CARRIER")
    rows = []
    for (asin, day), units in sorted(units_by.items()):
        rng = random.Random(f"ret-{asin}-{day.isoformat()}")
        quantity = sum(1 for _ in range(units) if rng.random() < 0.025)
        if quantity:
            rows.append({
                "account_id": account_id, "asin": asin, "sku": PRODUCT_BY_ASIN[asin].sku,
                "amazon_order_id": f"TEST-{rng.randint(100, 999)}-{rng.randint(1000000, 9999999)}",
                "return_date": day + timedelta(days=rng.randint(3, 20)), "quantity": quantity,
                "reason": rng.choice(reasons), "disposition": "SELLABLE",
            })
    return rows


def _search_term_rows(account_id, today: date) -> list[dict]:
    own = set(PRODUCT_BY_ASIN)
    last_sunday = today - timedelta(days=(today.weekday() + 1) % 7 + 7)
    rows = []
    for week in range(SEARCH_TERM_WEEKS):
        start = last_sunday - timedelta(weeks=week)
        for term, rank, clicked in SEARCH_TERMS:
            rng = random.Random(f"{term}-{start.isoformat()}")
            top = [
                {"rank": n, "asin": asin, "product_title": TITLE_BY_ASIN[asin],
                 "click_share": round(share * rng.uniform(0.85, 1.15), 4),
                 "conversion_share": round(share * rng.uniform(0.6, 1.0), 4)}
                for n, (asin, share) in enumerate(clicked, start=1)
            ]
            rows.append({
                "account_id": account_id, "week_start": start, "week_end": start + timedelta(days=6),
                "search_term": term, "search_frequency_rank": round(rank * rng.uniform(0.9, 1.1)),
                "department": "Casa e cucina", "top_clicked": top,
                "contains_account_asin": any(e["asin"] in own for e in top),
            })
    return rows


async def _competitors(db: AsyncSession, org: Organization, start: date, days: int) -> None:
    await db.execute(delete(Competitor).where(
        Competitor.organization_id == org.id, Competitor.asin.in_([c[0] for c in COMPETITORS])
    ))
    for asin, brand, title, price, bsr in COMPETITORS:
        competitor = Competitor(organization_id=org.id, asin=asin, marketplace="IT", title=title,
                                brand=brand, current_price=price, current_bsr=bsr, rating=4.3,
                                review_count=812, is_tracking=True)
        db.add(competitor)
        await db.flush()
        history = []
        for offset in range(days):
            day = start + timedelta(days=offset)
            rng = random.Random(f"{asin}-{day.isoformat()}")
            history.append({
                "competitor_id": competitor.id, "date": day,
                "price": round(price * (0.92 if day.month in (11, 12) else 1.0) * rng.uniform(0.97, 1.03), 2),
                "bsr": round(bsr * (1 + 0.3 * math.sin(offset / 20)) * rng.uniform(0.85, 1.15)),
                "review_count": 600 + offset, "rating": 4.3,
            })
        await db.execute(insert(CompetitorHistory), history)


async def seed_database(db: AsyncSession, config: SeedConfig) -> Seeded:
    """Organization, admin, accounts, products, history. Commits."""
    org, user = await _organization_and_admin(db, config)
    seller = await _account(db, org, SELLER_NAME, AccountType.SELLER, "TESTSELLER")
    vendor = await _account(db, org, VENDOR_NAME, AccountType.VENDOR, None)
    await _products(db, seller, list(PRODUCTS), {p.asin: p.sku for p in PRODUCTS})
    await _products(db, vendor, [PRODUCT_BY_ASIN[a] for a in VENDOR_SKUS], VENDOR_SKUS)
    await _reset_monitor(db, org, [seller.id, vendor.id], config)

    start = config.today - timedelta(days=SALES_DAYS)
    await db.execute(delete(SalesData).where(SalesData.account_id == seller.id))
    rows, units_by = _sales_rows(seller.id, start, SALES_DAYS)
    for chunk in range(0, len(rows), 2000):
        await db.execute(insert(SalesData), rows[chunk:chunk + 2000])
    await _advertising(db, seller, units_by, start, SALES_DAYS)
    await db.execute(delete(ReturnData).where(ReturnData.account_id == seller.id))
    returns = _return_rows(seller.id, units_by)
    if returns:
        await db.execute(insert(ReturnData), returns)
    await db.execute(delete(BrandSearchTerm).where(BrandSearchTerm.account_id == seller.id))
    await db.execute(insert(BrandSearchTerm), _search_term_rows(seller.id, config.today))
    await _competitors(db, org, start, SALES_DAYS)
    await db.commit()
    return Seeded(organization=org, user=user, seller=seller, vendor=vendor)


# ---- scans ----


async def _rule_states(db: AsyncSession, account_id) -> tuple[dict, dict]:
    rows = (await db.execute(
        select(ListingQualitySnapshot.components).where(
            ListingQualitySnapshot.account_id == account_id,
            ListingQualitySnapshot.snapshot_date == select(func.max(ListingQualitySnapshot.snapshot_date))
            .where(ListingQualitySnapshot.account_id == account_id).scalar_subquery(),
        )
    )).scalars().all()
    overall: dict[str, int] = {}
    per_rule: dict[str, dict[str, int]] = {}
    for components in rows:
        overall[components["state"]] = overall.get(components["state"], 0) + 1
        for result in components["results"]:
            bucket = per_rule.setdefault(result["key"], {})
            bucket[result["state"]] = bucket.get(result["state"], 0) + 1
    return overall, per_rule


async def run_scans(db: AsyncSession, seeded: Seeded, config: SeedConfig) -> dict:
    """Access check, first scan, baselines, fixture changes, second scan. Commits."""
    factory = fixture_client_factory(config.fixture_dir)
    fetch = local_image_fetch(config.fixture_dir, config.image_base_url)
    accounts = (seeded.seller, seeded.vendor)
    for account in accounts:
        await check_account_capabilities(db, account, factory)
    await db.commit()

    def scanner() -> CatalogScanService:
        return CatalogScanService(db, client_factory=factory, image_fetch=fetch, sleep=lambda _: None,
                                  today=lambda: config.today)

    first = {a.account_name: await scanner().scan_account(a) for a in accounts}
    repo = CatalogMonitorRepository(db)
    baselines = {}
    for account in accounts:
        baselines[account.account_name] = await approve_live_as_baseline(
            repo, account.id, None, seeded.user.id
        )
    await db.commit()
    mutate_fixtures(config.fixture_dir)
    second = {a.account_name: await scanner().scan_account(a) for a in accounts}

    report: dict = {}
    for account in accounts:
        overall, per_rule = await _rule_states(db, account.id)
        anomalies = (await db.execute(
            select(CatalogAnomaly.asin, CatalogAnomaly.kind, CatalogAnomaly.field)
            .where(CatalogAnomaly.account_id == account.id, CatalogAnomaly.status == "open")
            .order_by(CatalogAnomaly.asin, CatalogAnomaly.field)
        )).all()
        report[account.account_name] = {
            "first_scan": first[account.account_name].to_dict(),
            "baselines": baselines[account.account_name],
            "second_scan": second[account.account_name].to_dict(),
            "states": overall,
            "rules": per_rule,
            "open_anomalies": [tuple(a) for a in anomalies],
        }
    return report


def print_report(report: dict) -> None:
    for name, data in report.items():
        scan = data["second_scan"]
        print(f"\n{name}: {scan['scanned']} scanned, {scan['failed']} failed, "
              f"{data['baselines']} baselines approved")
        print("  overall: " + ", ".join(f"{k} {v}" for k, v in sorted(data["states"].items())))
        for rule, states in data["rules"].items():
            print(f"  {rule:<17}" + ", ".join(f"{k} {v}" for k, v in sorted(states.items())))
        print(f"  anomalies opened by the second scan: {scan['anomalies_opened']}")
        for asin, kind, field_name in data["open_anomalies"]:
            print(f"    {asin} {kind} {field_name}")
        for error in scan["errors"]:
            print(f"  error: {error}")


# ---- command line ----


def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the local catalogue monitor demo.")
    parser.add_argument("--email", default=os.environ.get("SEED_ADMIN_EMAIL"))
    parser.add_argument("--password", default=os.environ.get("SEED_ADMIN_PASSWORD"),
                        help="better passed as SEED_ADMIN_PASSWORD, out of the shell history")
    parser.add_argument("--fixtures-dir", default=os.environ.get("DEV_FIXTURE_AMAZON_DIR")
                        or str(DEFAULT_FIXTURE_DIR))
    parser.add_argument("--image-base-url", default=DEFAULT_IMAGE_BASE_URL)
    return parser.parse_args(argv)


async def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    database_url = os.environ.get("DATABASE_URL") or ""
    refuse_non_local(database_url)
    if not args.email or not args.password:
        raise SystemExit("Set --email and SEED_ADMIN_PASSWORD (or --password).")
    if len(args.password) < 8:
        raise SystemExit("The admin password must be at least 8 characters.")
    config = SeedConfig(admin_email=args.email, admin_password=args.password,
                        fixture_dir=Path(args.fixtures_dir).resolve(),
                        image_base_url=args.image_base_url.rstrip("/"))
    write_fixtures(config)
    engine = create_async_engine(database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            seeded = await seed_database(db, config)
            report = await run_scans(db, seeded, config)
    finally:
        await engine.dispose()
    print(f"Organization {config.org_name!r}, admin {config.admin_email} (password not shown)")
    print(f"Fixtures in {config.fixture_dir}")
    print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
