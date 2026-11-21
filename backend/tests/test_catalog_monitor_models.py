"""Catalogue monitoring data model (R1-R4)."""
import importlib

from app.db.base import Base
from app.models import Product
import app.models  # noqa: F401  (registers tables)

TABLES = {
    "listing_content_versions",
    "listing_content_baselines",
    "variation_family_baselines",
    "catalog_anomalies",
    "catalog_change_requests",
    "listing_quality_rules",
    "product_type_definitions_cache",
    "image_checks",
    "catalog_api_capabilities",
}


def test_tables_registered():
    assert TABLES <= set(Base.metadata.tables)


def test_open_anomaly_unique_index_is_partial():
    table = Base.metadata.tables["catalog_anomalies"]
    unique = [i for i in table.indexes if i.unique]
    assert len(unique) == 1
    assert unique[0].dialect_options["postgresql"]["where"] is not None
    assert [c.name for c in unique[0].columns] == ["account_id", "asin", "kind", "field"]


def test_product_has_main_keyword():
    assert "main_keyword" in Product.__table__.c
    assert "main_keyword_source" in Product.__table__.c


def test_migration_chain():
    mod = importlib.import_module("app.db.migrations.versions.034_catalog_monitor")
    assert mod.revision == "034_catalog_monitor"
    assert mod.down_revision == "033_ingestion_expansion"


def test_settings_defaults():
    from app.config import Settings

    s = Settings()
    assert s.CATALOG_SCAN_HOUR_UTC == 5
    assert s.CATALOG_SCAN_MINUTE_UTC == 0
    assert s.CATALOG_SCAN_REQUEST_INTERVAL_S == 0.55
    assert s.CATALOG_FEED_THRESHOLD == 50
    assert s.PTD_CACHE_DAYS == 7
