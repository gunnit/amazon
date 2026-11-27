from datetime import date
from enum import Enum
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
import sys
import types
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.sql import column, table


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "app" / "services" / "analytics_service.py"


def _ensure_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules.setdefault(name, module)


class _TableProxy:
    def __init__(self, table_name: str, *columns: str):
        self._table = table(table_name, *[column(name) for name in columns])
        for name in columns:
            setattr(self, name, getattr(self._table.c, name))

    def __clause_element__(self):
        return self._table


_ensure_package("app", ROOT / "app")
_ensure_package("app.models", ROOT / "app" / "models")
_ensure_package("app.services", ROOT / "app" / "services")

sales_module = types.ModuleType("app.models.sales_data")
sales_module.SalesData = _TableProxy(
    "sales_data",
    "account_id",
    "date",
    "asin",
    "ordered_product_sales",
    "units_ordered",
    "total_order_items",
    "shipped_revenue",
    "shipped_units",
)
sys.modules["app.models.sales_data"] = sales_module

advertising_module = types.ModuleType("app.models.advertising")
advertising_module.AdvertisingCampaign = _TableProxy(
    "advertising_campaigns",
    "id",
    "account_id",
)
advertising_module.AdvertisingMetrics = _TableProxy(
    "advertising_metrics",
    "campaign_id",
    "date",
    "attributed_sales_7d",
    "cost",
)
advertising_module.AdvertisingMetricsByAsin = _TableProxy(
    "advertising_metrics_by_asin",
    "account_id",
    "asin",
    "date",
    "cost",
    "attributed_sales_7d",
)
sys.modules["app.models.advertising"] = advertising_module

product_module = types.ModuleType("app.models.product")
product_module.Product = _TableProxy(
    "products",
    "account_id",
    "asin",
    "title",
    "category",
    "current_bsr",
    "review_count",
    "updated_at",
    "id",
)
product_module.BSRHistory = _TableProxy("bsr_history", "product_id", "date", "bsr")
sys.modules["app.models.product"] = product_module

data_extraction_module = types.ModuleType("app.services.data_extraction")
data_extraction_module.DAILY_TOTAL_ASIN = "__DAILY_TOTAL__"
sys.modules["app.services.data_extraction"] = data_extraction_module


class AccountType(str, Enum):
    SELLER = "seller"
    VENDOR = "vendor"


amazon_account_module = types.ModuleType("app.models.amazon_account")
amazon_account_module.AccountType = AccountType
amazon_account_module.AmazonAccount = _TableProxy(
    "amazon_accounts",
    "id",
    "organization_id",
    "account_type",
)
sys.modules["app.models.amazon_account"] = amazon_account_module


class Granularity(str, Enum):
    DAILY = "daily"
    MONTHLY = "monthly"
    MIXED = "mixed"
    UNKNOWN = "unknown"


def granularity_for_account_types(account_types) -> Granularity:
    has_seller = any(t == AccountType.SELLER for t in account_types)
    has_vendor = any(t == AccountType.VENDOR for t in account_types)
    if has_seller and has_vendor:
        return Granularity.MIXED
    if has_vendor:
        return Granularity.MONTHLY
    if has_seller:
        return Granularity.DAILY
    return Granularity.UNKNOWN


granularity_module = types.ModuleType("app.services.granularity")
granularity_module.Granularity = Granularity
granularity_module.granularity_for_account_types = granularity_for_account_types
sys.modules["app.services.granularity"] = granularity_module

service_spec = spec_from_file_location("analytics_service_under_test", SERVICE_PATH)
service_module = module_from_spec(service_spec)
assert service_spec is not None and service_spec.loader is not None
service_spec.loader.exec_module(service_module)
AnalyticsService = service_module.AnalyticsService

for module_name in (
    "app.models.sales_data",
    "app.models.advertising",
    "app.models.product",
    "app.models.amazon_account",
    "app.services.data_extraction",
    "app.services.granularity",
    "app.services.sales_metrics",
):
    sys.modules.pop(module_name, None)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def one(self):
        return self._rows[0]

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


class FakeAsyncSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.execute_calls = 0

    async def execute(self, query):
        self.execute_calls += 1
        if not self._responses:
            raise AssertionError("Unexpected execute call")
        return FakeResult(self._responses.pop(0))


def _sales_row(account_id, bucket_date: date, total_sales: float):
    return SimpleNamespace(account_id=account_id, bucket_date=bucket_date, total_sales=total_sales)


def _ads_row(account_id, bucket_date: date, ad_sales: float, ad_spend: float = 0.0):
    return SimpleNamespace(account_id=account_id, bucket_date=bucket_date, ad_sales=ad_sales, ad_spend=ad_spend)


def _bucket_ads_row(bucket_date: date, ad_sales: float):
    return SimpleNamespace(bucket_date=bucket_date, ad_sales=ad_sales, ad_spend=10.0)


def _coverage_row(ads_from=None, ads_until=None):
    return SimpleNamespace(ads_from=ads_from, ads_until=ads_until)


def _period_coverage_row(current_days=0, previous_days=0):
    return SimpleNamespace(current_days=current_days, previous_days=previous_days)


def _asin_row(asin: str, title: str, total_sales: float):
    return SimpleNamespace(asin=asin, title=title, total_sales=total_sales)


def _account_row(account_id, account_type=AccountType.VENDOR):
    return SimpleNamespace(id=account_id, account_type=account_type)


def _title_row(asin: str, title: str):
    return SimpleNamespace(asin=asin, title=title)


@pytest.mark.asyncio
async def test_get_ads_vs_organic_combines_sales_ads_and_breakdown():
    account_a = uuid4()
    account_b = uuid4()
    session = FakeAsyncSession(
        [
            [
                _account_row(account_a, AccountType.SELLER),
                _account_row(account_b, AccountType.SELLER),
            ],
            [
                _sales_row(account_a, date(2026, 3, 1), 100),
                _sales_row(account_b, date(2026, 3, 1), 50),
                _sales_row(account_a, date(2026, 3, 2), 80),
            ],
            [
                _ads_row(account_a, date(2026, 3, 1), 30),
                _ads_row(account_b, date(2026, 3, 1), 5),
                _ads_row(account_a, date(2026, 3, 2), 10),
            ],
            [
                _sales_row(account_a, date(2026, 2, 27), 90),
                _sales_row(account_b, date(2026, 2, 27), 40),
                _sales_row(account_a, date(2026, 2, 28), 70),
            ],
            [
                _ads_row(account_a, date(2026, 2, 27), 20),
                _ads_row(account_b, date(2026, 2, 27), 10),
                _ads_row(account_a, date(2026, 2, 28), 10),
            ],
            [_coverage_row(date(2026, 1, 15), date(2026, 3, 2))],
            [_period_coverage_row(current_days=3, previous_days=3)],
            [_period_coverage_row(current_days=3, previous_days=3)],
            [
                _asin_row("B0AAA", "Alpha", 120),
                _asin_row("B0BBB", "Beta", 110),
            ],
            [_title_row("B0AAA", "Alpha"), _title_row("B0BBB", "Beta")],
        ]
    )

    service = AnalyticsService(session)  # type: ignore[arg-type]
    result = await service.get_ads_vs_organic(
        account_ids=[account_a, account_b],
        date_from=date(2026, 3, 1),
        date_to=date(2026, 3, 2),
    )

    assert session.execute_calls == 10
    assert result["ads_data_from"] == date(2026, 1, 15)
    assert result["ads_data_until"] == date(2026, 3, 2)
    assert result["ads_coverage"] == "partial"
    assert result["previous_ads_coverage"] == "partial"
    assert [point["date"] for point in result["time_series"]] == [date(2026, 3, 1), date(2026, 3, 2)]
    assert result["time_series"][0]["total_sales"] == 150.0
    assert result["time_series"][0]["ad_sales"] == 35.0
    assert result["time_series"][0]["organic_sales"] is None
    assert result["summary"]["total_sales"]["value"] == 230.0
    assert result["summary"]["ad_sales"]["value"] == 45.0
    assert result["summary"]["organic_sales"]["value"] is None
    assert result["summary"]["ad_share_pct"]["value"] is None
    assert result["summary"]["organic_share_pct"]["value"] is None
    assert result["summary"]["total_sales"]["previous_value"] is None
    assert result["required_account_days"] == 4 and result["retail_account_days"] == 3
    assert result["asin_breakdown"][0]["asin"] == "B0AAA"
    assert result["asin_breakdown"][0]["sales_share_pct"] == pytest.approx(52.17, abs=0.01)
    assert any("7-day attribution" in note for note in result["attribution_notes"])


@pytest.mark.asyncio
async def test_get_ads_vs_organic_preserves_retail_when_ads_are_missing():
    account_id = uuid4()
    session = FakeAsyncSession(
        [
            [_account_row(account_id, AccountType.SELLER)],
            [_sales_row(account_id, date(2026, 3, 5), 100)],
            [],
            [],
            [],
            [_coverage_row()],
            [_period_coverage_row()],
            [_period_coverage_row(current_days=1)],
            [],
        ]
    )

    service = AnalyticsService(session)  # type: ignore[arg-type]
    result = await service.get_ads_vs_organic(
        account_ids=[account_id],
        date_from=date(2026, 3, 5),
        date_to=date(2026, 3, 5),
    )

    point = result["time_series"][0]
    assert point["total_sales"] == 100.0
    assert point["ad_sales"] is None
    assert point["organic_sales"] is None
    assert point["organic_share_pct"] is None
    assert result["ads_data_from"] is None
    assert result["ads_data_until"] is None
    assert result["ads_coverage"] == "none"
    assert result["previous_ads_coverage"] == "none"


@pytest.mark.asyncio
async def test_get_ads_vs_organic_supports_week_grouping():
    account_id = uuid4()
    session = FakeAsyncSession(
        [
            [_account_row(account_id, AccountType.SELLER)],
            [
                _sales_row(account_id, date(2026, 3, 2), 120),
                _sales_row(account_id, date(2026, 3, 9), 80),
            ],
            [
                _ads_row(account_id, date(2026, 3, 2), 30),
                _ads_row(account_id, date(2026, 3, 9), 10),
            ],
            [],
            [],
            [_coverage_row()],
            [_period_coverage_row(current_days=13)],
            [_period_coverage_row(current_days=13)],
            [],
        ]
    )

    service = AnalyticsService(session)  # type: ignore[arg-type]
    result = await service.get_ads_vs_organic(
        account_ids=[account_id],
        date_from=date(2026, 3, 3),
        date_to=date(2026, 3, 15),
        group_by="week",
    )

    assert [point["date"] for point in result["time_series"]] == [date(2026, 3, 2), date(2026, 3, 9)]
    assert result["time_series"][1]["organic_sales"] == 70.0


@pytest.mark.asyncio
async def test_vendor_ads_only_period_keeps_observed_sales_and_spend_and_withholds_split():
    from app.schemas.analytics import AdsVsOrganicResponse

    account = uuid4()
    start, end = date(2026, 11, 9), date(2026, 11, 15)
    session = FakeAsyncSession([
        [_account_row(account, AccountType.VENDOR)],
        [], [_ads_row(account, date(2026, 11, 1), 4286.95, 800)],
        [], [], [_coverage_row(start, end)],
        [_period_coverage_row(7, 0)], [_period_coverage_row(0, 0)], [],
    ])
    result = await AnalyticsService(session).get_ads_vs_organic([account], start, end)
    result = AdsVsOrganicResponse.model_validate(result).model_dump()
    assert result["retail_coverage"] == "none" and result["ads_coverage"] == "full"
    assert result["retail_account_days"] == 0 and result["required_account_days"] == 7
    assert result["summary"]["ad_sales"]["value"] == 4286.95 and result["summary"]["ad_spend"]["value"] == 800
    for name in ("total_sales", "organic_sales", "ad_share_pct", "organic_share_pct"):
        assert result["summary"][name]["value"] is None and not result["summary"][name]["is_available"]
        assert result["time_series"][0][name] is None


@pytest.mark.asyncio
async def test_current_split_and_standalone_ads_comparison_with_missing_previous_retail():
    account = uuid4()
    start, previous = date(2026, 11, 9), date(2026, 11, 8)
    session = FakeAsyncSession([
        [_account_row(account, AccountType.SELLER)],
        [_sales_row(account, start, 100)], [_ads_row(account, start, 30, 10)],
        [], [_ads_row(account, previous, 20, 8)], [_coverage_row(previous, start)],
        [_period_coverage_row(1, 1)], [_period_coverage_row(1, 0)], [],
    ])
    result = await AnalyticsService(session).get_ads_vs_organic([account], start, start)
    assert result["summary"]["organic_sales"]["value"] == 70
    assert result["summary"]["organic_share_pct"]["value"] == 70
    assert result["summary"]["organic_sales"]["previous_value"] is None
    assert result["summary"]["organic_share_pct"]["change_percent"] is None
    assert result["summary"]["ad_sales"]["previous_value"] == 20
    assert result["summary"]["ad_spend"]["change_percent"] == 25


@pytest.mark.asyncio
async def test_get_ads_vs_organic_supports_month_grouping():
    account_id = uuid4()
    session = FakeAsyncSession(
        [
            [_account_row(account_id, AccountType.SELLER)],
            [
                _sales_row(account_id, date(2026, 3, 1), 100),
                _sales_row(account_id, date(2026, 4, 1), 200),
            ],
            [
                _ads_row(account_id, date(2026, 3, 1), 40),
                _ads_row(account_id, date(2026, 4, 1), 50),
            ],
            [],
            [],
            [_coverage_row()],
            [_period_coverage_row(current_days=61)],
            [_period_coverage_row(current_days=61)],
            [],
        ]
    )

    service = AnalyticsService(session)  # type: ignore[arg-type]
    result = await service.get_ads_vs_organic(
        account_ids=[account_id],
        date_from=date(2026, 3, 1),
        date_to=date(2026, 4, 30),
        group_by="month",
    )

    assert [point["date"] for point in result["time_series"]] == [date(2026, 3, 1), date(2026, 4, 1)]
    assert result["summary"]["organic_sales"]["value"] == 210.0


@pytest.mark.asyncio
async def test_get_ads_vs_organic_applies_asin_filter_and_returns_note():
    account_id = uuid4()
    session = FakeAsyncSession(
        [
            [_account_row(account_id, AccountType.SELLER)],
            [SimpleNamespace(bucket_date=date(2026, 3, 5), total_sales=90)],
            [_bucket_ads_row(date(2026, 3, 5), 40)],
            [],
            [],
            [_coverage_row(date(2026, 2, 1), date(2026, 3, 5))],
            [_period_coverage_row(current_days=1)],
            [_period_coverage_row(current_days=1)],
        ]
    )

    service = AnalyticsService(session)  # type: ignore[arg-type]
    result = await service.get_ads_vs_organic(
        account_ids=[account_id],
        date_from=date(2026, 3, 5),
        date_to=date(2026, 3, 5),
        asin="B0TESTASIN",
    )

    assert session.execute_calls == 8
    assert result["asin"] == "B0TESTASIN"
    assert result["asin_breakdown"] is None
    assert result["summary"]["total_sales"]["value"] == 90.0
    assert result["summary"]["ad_sales"]["value"] == 40.0
    assert "Sponsored Products" in result["attribution_notes"][0]
    assert any("7-day attribution" in note for note in result["attribution_notes"])
    assert result["ads_data_from"] == date(2026, 2, 1)
    assert result["ads_data_until"] == date(2026, 3, 5)
    assert result["ads_coverage"] == "full"
    assert result["previous_ads_coverage"] == "none"


@pytest.mark.asyncio
async def test_get_ads_vs_organic_keeps_zero_for_an_unadvertised_asin_with_report_coverage():
    account_id = uuid4()
    session = FakeAsyncSession(
        [
            [_account_row(account_id, AccountType.SELLER)],
            [SimpleNamespace(bucket_date=date(2026, 3, 6), total_sales=25)],
            [],
            [],
            [],
            [_coverage_row()],
            [_period_coverage_row(current_days=1)],
            [_period_coverage_row(current_days=1)],
        ]
    )

    service = AnalyticsService(session)  # type: ignore[arg-type]
    result = await service.get_ads_vs_organic(
        account_ids=[account_id],
        date_from=date(2026, 3, 6),
        date_to=date(2026, 3, 6),
        asin="  b0mixed123  ",
    )

    assert session.execute_calls == 8
    assert result["asin"] == "B0MIXED123"
    assert result["asin_breakdown"] is None
    assert result["summary"]["ad_sales"]["value"] == 0.0
    assert result["ads_coverage"] == "full"


@pytest.mark.asyncio
async def test_ads_coverage_counts_distinct_scoped_account_days_using_the_matching_report_source():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE advertising_campaigns (id TEXT, account_id TEXT)")
        connection.exec_driver_sql("CREATE TABLE advertising_metrics (campaign_id TEXT, date TEXT)")
        connection.exec_driver_sql(
            "CREATE TABLE advertising_metrics_by_asin (account_id TEXT, asin TEXT, date TEXT)"
        )
        connection.exec_driver_sql(
            "INSERT INTO advertising_campaigns VALUES ('1', 'a'), ('2', 'a'), ('3', 'b'), ('4', 'other')"
        )
        connection.exec_driver_sql(
            "INSERT INTO advertising_metrics VALUES (?, ?)",
            [("1", f"2026-08-{day:02}") for day in range(1, 7)]
            + [("3", f"2026-08-{day:02}") for day in (1, 2, 3, 4, 6)]
            + [("2", "2026-08-04"), ("4", "2026-08-05"), ("3", "2026-08-07")],
        )
        connection.exec_driver_sql(
            "INSERT INTO advertising_metrics_by_asin VALUES (?, ?, ?)",
            [(account, "B0OTHER", f"2026-08-{day:02}") for account in ("a", "b") for day in range(4, 7)],
        )

        async def execute(query):
            return connection.execute(query)

        service = AnalyticsService(SimpleNamespace(execute=execute))  # type: ignore[arg-type]
        accounts = ["a", "b"]
        start, end, previous_start = date(2026, 8, 4), date(2026, 8, 6), date(2026, 8, 1)

        assert await service._ads_period_coverage(accounts, start, end, previous_start, by_asin=False) == (
            "partial", "full",
        )
        assert await service._ads_period_coverage(accounts, start, end, previous_start, by_asin=True) == (
            "full", "none",
        )


@pytest.mark.asyncio
async def test_asin_filter_sums_seller_rows_in_a_bucket():
    """Seller per-ASIN rows are daily (rebuilt from Orders), so a bucket sums
    them. They used to be trailing-window snapshots and were picked, not summed."""
    account_id = uuid4()
    session = FakeAsyncSession(
        [
            [_account_row(account_id, AccountType.SELLER)],
            [
                SimpleNamespace(bucket_date=date(2026, 3, 2), total_sales=50),
                SimpleNamespace(bucket_date=date(2026, 3, 2), total_sales=80),
            ],
            [_bucket_ads_row(date(2026, 3, 2), 30)],
            [],
            [],
            [_coverage_row()],
            [_period_coverage_row(current_days=1)],
            [_period_coverage_row(current_days=1)],
        ]
    )

    service = AnalyticsService(session)  # type: ignore[arg-type]
    result = await service.get_ads_vs_organic(
        account_ids=[account_id],
        date_from=date(2026, 3, 2),
        date_to=date(2026, 3, 8),
        group_by="week",
        asin="B0TESTASIN",
    )

    point = result["time_series"][0]
    assert point["total_sales"] == 130.0
    assert point["ad_sales"] == 30.0
    assert result["summary"]["total_sales"]["value"] == 130.0


@pytest.mark.asyncio
async def test_asin_filter_sums_vendor_rows_and_uses_by_asin_ads():
    account_id = uuid4()
    session = FakeAsyncSession(
        [
            [_account_row(account_id, AccountType.VENDOR)],
            [SimpleNamespace(bucket_date=date(2026, 3, 1), total_sales=70)],
            [_bucket_ads_row(date(2026, 3, 1), 45)],
            [],
            [],
            [_coverage_row()],
            [_period_coverage_row(current_days=1)],
            [_period_coverage_row(current_days=1)],
        ]
    )

    service = AnalyticsService(session)  # type: ignore[arg-type]
    result = await service.get_ads_vs_organic(
        account_ids=[account_id],
        date_from=date(2026, 3, 1),
        date_to=date(2026, 3, 31),
        asin="B0TESTASIN",
    )

    assert result["group_by"] == "month"
    point = result["time_series"][0]
    assert point["total_sales"] == 70.0
    assert point["ad_sales"] == 45.0


@pytest.mark.asyncio
async def test_get_ads_vs_organic_clamps_organic_sales_when_ads_exceed_total():
    account_id = uuid4()
    session = FakeAsyncSession(
        [
            [_account_row(account_id, AccountType.SELLER)],
            [_sales_row(account_id, date(2026, 3, 8), 50)],
            [_ads_row(account_id, date(2026, 3, 8), 80)],
            [],
            [],
            [_coverage_row()],
            [_period_coverage_row(current_days=1)],
            [_period_coverage_row(current_days=1)],
            [],
        ]
    )

    service = AnalyticsService(session)  # type: ignore[arg-type]
    result = await service.get_ads_vs_organic(
        account_ids=[account_id],
        date_from=date(2026, 3, 8),
        date_to=date(2026, 3, 8),
    )

    point = result["time_series"][0]
    assert point["ad_sales"] == 80.0
    assert point["organic_sales"] == 0.0
    assert point["ad_share_pct"] == 160.0
    assert result["summary"]["organic_sales"]["value"] == 0.0
