"""Tests for workers.tasks.maintenance partition management.

PostgreSQL `PARTITION BY` is not supported by SQLite, so we mock the DB
connection and assert on the SQL that would be issued. The goal is to
catch regressions in:

* number and parameters of `ensure_monthly_partition` calls,
* the partition-name regex (do not touch `_default` or unrelated tables),
* the upper-bound math (only drop partitions whose end date <= cutoff).
"""
from __future__ import annotations

from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types
from unittest.mock import MagicMock

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAINTENANCE_PATH = ROOT / "workers" / "tasks" / "maintenance.py"


def _ensure_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules.setdefault(name, module)


@pytest.fixture
def maintenance_module(monkeypatch):
    """Load workers.tasks.maintenance with stubbed dependencies."""
    _ensure_package("app", ROOT / "app")
    _ensure_package("workers", ROOT / "workers")
    _ensure_package("workers.tasks", ROOT / "workers" / "tasks")

    # Stub app.config.settings
    config_stub = types.ModuleType("app.config")

    class _Settings:
        DATABASE_URL = "postgresql+psycopg2://test:test@localhost/test"
        APP_DEBUG = False
        DATA_RETENTION_MONTHS = 24
        PARTITION_FUTURE_MONTHS = 3
        PARTITION_MANAGED_TABLES = [
            "sales_data",
            "advertising_metrics",
            "advertising_metrics_by_asin",
            "bsr_history",
        ]

    config_stub.settings = _Settings()
    sys.modules["app.config"] = config_stub

    # Stub workers.celery_app
    celery_stub = types.ModuleType("workers.celery_app")

    def _identity_task(fn):  # decorator that passes the function through
        return fn

    celery_stub.celery_app = types.SimpleNamespace(task=_identity_task)
    sys.modules["workers.celery_app"] = celery_stub

    # Replace SQLAlchemy create_engine so module import does not open a real
    # connection. We patch it back to a MagicMock that returns the engine
    # we will further customize in each test.
    fake_engine = MagicMock(name="sync_engine")
    monkeypatch.setattr(
        "sqlalchemy.create_engine",
        lambda *args, **kwargs: fake_engine,
    )
    # sessionmaker is called at import time as well; return a no-op factory.
    monkeypatch.setattr(
        "sqlalchemy.orm.sessionmaker",
        lambda *args, **kwargs: MagicMock(name="SessionLocal"),
    )

    spec = spec_from_file_location("workers.tasks.maintenance", MAINTENANCE_PATH)
    module = module_from_spec(spec)
    sys.modules["workers.tasks.maintenance"] = module
    spec.loader.exec_module(module)
    return module


def _make_connection_ctx(execute_side_effect, scalars_side_effect=None):
    """Build a context-manager-like object that yields a mock connection.

    `execute_side_effect`: callable receiving the SQLAlchemy text() and bound
    params, returning an object whose `.scalar()` and `.scalars().all()`
    behave appropriately for the call.
    """
    connection = MagicMock()
    connection.execution_options.return_value = connection
    connection.execute.side_effect = execute_side_effect

    ctx = MagicMock()
    ctx.__enter__.return_value = connection
    ctx.__exit__.return_value = False
    return ctx, connection


def test_manage_partitions_creates_current_plus_future_months(maintenance_module, monkeypatch):
    """manage_partitions should call ensure_monthly_partition for current + N future months per table."""
    calls: list[dict] = []

    def fake_execute(stmt, params=None):
        result = MagicMock()
        if params and "table" in params:
            calls.append({"table": params["table"], "year": params["year"], "month": params["month"]})
            result.scalar.return_value = f"created: {params['table']}_y{params['year']}m{params['month']:02d}"
        else:
            # Drop-side: no partitions exist yet, so _list_partitions returns []
            result.scalars.return_value.all.return_value = []
        return result

    ctx, _ = _make_connection_ctx(fake_execute)
    maintenance_module.sync_engine.connect.return_value = ctx

    # Pin "today" so the test is deterministic.
    fixed_today = date(2026, 5, 28)

    class _FakeDate(date):
        @classmethod
        def today(cls):
            return fixed_today

    monkeypatch.setattr(maintenance_module, "date", _FakeDate)

    result = maintenance_module.manage_partitions()

    # 4 tables × (1 current + 3 future) = 16 create calls
    assert len(calls) == 16
    # First-table sample: (2026,5), (2026,6), (2026,7), (2026,8)
    sales_calls = [c for c in calls if c["table"] == "sales_data"]
    assert [(c["year"], c["month"]) for c in sales_calls] == [
        (2026, 5),
        (2026, 6),
        (2026, 7),
        (2026, 8),
    ]
    # Year-crossing case: today is 2026-05; +3 = Aug 2026. Move "today" forward
    # implicitly: covered separately below.
    assert result["months_ahead"] == 3
    assert result["retention_cutoff"] == "2024-05-28"
    assert set(result["created"].keys()) == {
        "sales_data",
        "advertising_metrics",
        "advertising_metrics_by_asin",
        "bsr_history",
    }
    for table_name in result["created"]:
        assert result["dropped"][table_name] == []


def test_manage_partitions_wraps_year_at_december(maintenance_module, monkeypatch):
    """When current month is Nov, +3 future months should wrap into the next year."""
    calls: list[dict] = []

    def fake_execute(stmt, params=None):
        result = MagicMock()
        if params and "table" in params:
            calls.append({"year": params["year"], "month": params["month"]})
            result.scalar.return_value = "created: x"
        else:
            result.scalars.return_value.all.return_value = []
        return result

    ctx, _ = _make_connection_ctx(fake_execute)
    maintenance_module.sync_engine.connect.return_value = ctx

    fixed_today = date(2026, 11, 15)

    class _FakeDate(date):
        @classmethod
        def today(cls):
            return fixed_today

    monkeypatch.setattr(maintenance_module, "date", _FakeDate)
    # Limit the table set for this test by patching settings.
    maintenance_module.settings.PARTITION_MANAGED_TABLES = ["sales_data"]

    maintenance_module.manage_partitions()

    # Expected sequence for sales_data: (2026,11), (2026,12), (2027,1), (2027,2)
    assert [(c["year"], c["month"]) for c in calls] == [
        (2026, 11),
        (2026, 12),
        (2027, 1),
        (2027, 2),
    ]


def test_drop_expired_partitions_skips_default_and_other_parents(maintenance_module, monkeypatch):
    """_drop_expired_partitions_for must not touch _default or partitions of other parents."""
    dropped_sql: list[str] = []
    listed = [
        "sales_data_y2023m01",  # expired (upper=2023-02-01 <= cutoff 2024-05-28)
        "sales_data_y2024m05",  # boundary — upper=2024-06-01, > cutoff, keep
        "sales_data_y2025m12",  # current-ish, keep
        "sales_data_default",  # must NEVER be dropped
        "advertising_metrics_y2022m12",  # wrong parent: must be ignored
    ]

    def fake_execute(stmt, params=None):
        sql = str(stmt)
        result = MagicMock()
        if "pg_inherits" in sql:
            # _list_partitions(parent='sales_data')
            result.scalars.return_value.all.return_value = listed
        elif sql.strip().startswith("DROP TABLE"):
            dropped_sql.append(sql)
        return result

    ctx, connection = _make_connection_ctx(fake_execute)

    cutoff = date(2024, 5, 28)
    dropped = maintenance_module._drop_expired_partitions_for(connection, "sales_data", cutoff)

    assert dropped == ["sales_data_y2023m01"]
    # Exactly one DROP TABLE issued, and only for the expired partition.
    assert len(dropped_sql) == 1
    assert "sales_data_y2023m01" in dropped_sql[0]
    # The default partition must NOT appear in any DROP statement.
    assert all("sales_data_default" not in s for s in dropped_sql)


def test_partition_name_regex_does_not_match_default():
    """Explicit guard: the partition-name regex used for drop decisions must reject *_default."""
    from workers.tasks.maintenance import PARTITION_NAME_RE

    assert PARTITION_NAME_RE.match("sales_data_y2025m12") is not None
    assert PARTITION_NAME_RE.match("sales_data_default") is None
    assert PARTITION_NAME_RE.match("advertising_metrics_y2024m07") is not None
    # No partial matches.
    assert PARTITION_NAME_RE.match("sales_data_y2025m1") is None
    assert PARTITION_NAME_RE.match("sales_data_y20a5m12") is None


def test_drop_expired_upper_bound_math_treats_month_end_correctly(maintenance_module):
    """A partition for May 2024 has upper_bound = 2024-06-01.

    Cutoff exactly equal to the upper bound should still drop (<=).
    """
    listed = ["sales_data_y2024m05"]
    dropped_sql: list[str] = []

    def fake_execute(stmt, params=None):
        sql = str(stmt)
        result = MagicMock()
        if "pg_inherits" in sql:
            result.scalars.return_value.all.return_value = listed
        elif sql.strip().startswith("DROP TABLE"):
            dropped_sql.append(sql)
        return result

    _, connection = _make_connection_ctx(fake_execute)

    # Cutoff exactly on the upper bound: drop (boundary inclusive).
    dropped = maintenance_module._drop_expired_partitions_for(connection, "sales_data", date(2024, 6, 1))
    assert dropped == ["sales_data_y2024m05"]

    # Cutoff one day before the upper bound: keep.
    dropped_sql.clear()
    dropped = maintenance_module._drop_expired_partitions_for(connection, "sales_data", date(2024, 5, 31))
    assert dropped == []
    assert dropped_sql == []
