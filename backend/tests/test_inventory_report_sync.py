from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import importlib.metadata
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types
from types import SimpleNamespace
from uuid import uuid4

import pytest


ROOT = Path(__file__).resolve().parents[1]
REPORTS_PATH = ROOT / "app" / "api" / "v1" / "reports.py"


def _ensure_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules.setdefault(name, module)


_ensure_package("app", ROOT / "app")
_ensure_package("app.api", ROOT / "app" / "api")
_ensure_package("app.api.v1", ROOT / "app" / "api" / "v1")
_ensure_package("app.core", ROOT / "app" / "core")
_ensure_package("app.models", ROOT / "app" / "models")
_ensure_package("app.schemas", ROOT / "app" / "schemas")
_ensure_package("app.services", ROOT / "app" / "services")

sp_api_base_stub = types.ModuleType("sp_api.base")


class _Marketplace:
    def __init__(self, marketplace_id: str):
        self.marketplace_id = marketplace_id


sp_api_base_stub.Marketplaces = SimpleNamespace(
    IT=_Marketplace("A21TJRUUN4KGV"),
    DE=_Marketplace("A1PA6795UKMFR9"),
    FR=_Marketplace("A13V1IB3VIYZZH"),
    ES=_Marketplace("A1RKKUPIHCS9HS"),
    UK=_Marketplace("A1F83G8C2ARO7P"),
    US=_Marketplace("ATVPDKIKX0DER"),
    CA=_Marketplace("A2EUQ1WTGCTBG2"),
    MX=_Marketplace("A1AM78C64UM0Y8"),
    BR=_Marketplace("A2Q3Y263D00KWC"),
    JP=_Marketplace("A1VC38T7YXB528"),
    AU=_Marketplace("A39IBJ37TRP1C6"),
    IN=_Marketplace("A21TJRUUN4KGV"),
    AE=_Marketplace("A2VIGQ35RCS4UG"),
    SG=_Marketplace("A19VAU5U5O7RUS"),
    NL=_Marketplace("A1805IZSGTT6HS"),
    SE=_Marketplace("A2NODRKZP88ZB9"),
    PL=_Marketplace("A1C3SOZRARQ6R3"),
    TR=_Marketplace("A33AVAJ2PDY3EV"),
    BE=_Marketplace("AMEN7PMS3EDWL"),
)
sp_api_base_stub.SellingApiRequestThrottledException = type(
    "SellingApiRequestThrottledException",
    (Exception,),
    {},
)
sys.modules.setdefault("sp_api.base", sp_api_base_stub)

sp_api_api_stub = types.ModuleType("sp_api.api")


class _ApiStub:
    def __init__(self, **_kwargs):
        pass


for _name in ("Reports", "Inventories", "CatalogItems", "Products", "Orders", "VendorOrders", "ListingsItems"):
    setattr(sp_api_api_stub, _name, _ApiStub)
sys.modules.setdefault("sp_api.api", sp_api_api_stub)

email_validator_stub = types.ModuleType("email_validator")


class EmailNotValidError(ValueError):
    pass


def _validate_email(value, *args, **kwargs):
    return SimpleNamespace(normalized=value)


email_validator_stub.EmailNotValidError = EmailNotValidError
email_validator_stub.validate_email = _validate_email
sys.modules.setdefault("email_validator", email_validator_stub)
_real_distribution_version = importlib.metadata.version


def _fake_distribution_version(name: str) -> str:
    if name == "email-validator":
        return "2.0.0"
    return _real_distribution_version(name)


importlib.metadata.version = _fake_distribution_version

deps_stub = types.ModuleType("app.api.deps")
deps_stub.CurrentUser = object
deps_stub.CurrentOrganization = object
deps_stub.DbSession = object
sys.modules["app.api.deps"] = deps_stub

data_extraction_stub = types.ModuleType("app.services.data_extraction")
data_extraction_stub.DAILY_TOTAL_ASIN = "__DAILY_TOTAL__"
sys.modules["app.services.data_extraction"] = data_extraction_stub

scheduled_report_stub = types.ModuleType("app.services.scheduled_report_service")
scheduled_report_stub.ScheduledReportService = type("ScheduledReportService", (), {})
scheduled_report_stub.enqueue_scheduled_run_processing = lambda *_args, **_kwargs: None
scheduled_report_stub.scheduled_report_run_to_response = lambda *_args, **_kwargs: None
scheduled_report_stub.scheduled_report_to_response = lambda *_args, **_kwargs: None
sys.modules["app.services.scheduled_report_service"] = scheduled_report_stub

REPORTS_SPEC = spec_from_file_location("reports_under_test", REPORTS_PATH)
REPORTS_MODULE = module_from_spec(REPORTS_SPEC)
assert REPORTS_SPEC is not None and REPORTS_SPEC.loader is not None
REPORTS_SPEC.loader.exec_module(REPORTS_MODULE)

sys.path.insert(0, str(ROOT))

from app.core.amazon import sp_api_client as sp_api_client_module  # noqa: E402
from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace  # noqa: E402


class FakeScalarCollection:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class FakeResult:
    def __init__(self, *, scalar_value=None, values=None):
        self._scalar_value = scalar_value
        self._values = values or []

    def scalar(self):
        return self._scalar_value

    def all(self):
        return self._values

    def scalars(self):
        return FakeScalarCollection(self._values)


class FakeDb:
    def __init__(self, responses):
        self._responses = list(responses)
        self.queries = []

    async def execute(self, query):
        self.queries.append(query)
        return self._responses.pop(0)


def _make_client() -> SPAPIClient:
    return SPAPIClient(
        {
            "refresh_token": "refresh-token",
            "lwa_app_id": "lwa-app-id",
            "lwa_client_secret": "lwa-client-secret",
        },
        resolve_marketplace("IT"),
    )


def test_fetch_inventory_report_parses_fba_report(monkeypatch):
    client = _make_client()
    call_args = {}
    statuses = [
        {"processingStatus": "IN_PROGRESS"},
        {"processingStatus": "DONE", "reportDocumentId": "doc-1"},
    ]
    report_body = (
        "asin\tsku\tfulfillment-channel\tafn-fulfillable-quantity\t"
        "afn-reserved-quantity\tafn-inbound-working-quantity\t"
        "afn-inbound-shipped-quantity\tafn-inbound-receiving-quantity\n"
        "B001TEST\tSKU-1\tAFN\t10\t2\t3\t4\t1\n"
    )

    monkeypatch.setattr(client, "_reports_api", lambda: object())

    def fake_create_report(_api, **kwargs):
        call_args.update(kwargs)
        return {"reportId": "report-1"}

    monkeypatch.setattr(client, "_create_report_request", fake_create_report)
    monkeypatch.setattr(client, "_get_report_status", lambda _api, _report_id: statuses.pop(0))
    monkeypatch.setattr(
        client,
        "_download_report_document",
        lambda _api, _document_id: {"document": report_body},
    )
    monkeypatch.setattr(sp_api_client_module.time, "sleep", lambda *_args, **_kwargs: None)

    rows = client.fetch_inventory_report()

    assert call_args["reportType"] == "GET_FBA_MYI_ALL_INVENTORY_DATA"
    assert call_args["marketplaceIds"] == [client.marketplace.marketplace_id]
    assert rows == [
        {
            "asin": "B001TEST",
            "sku": "SKU-1",
            "fnsku": None,
            "fulfillment_channel": "AFN",
            "quantity": 10,
            "reserved_quantity": 2,
            "inbound_working_quantity": 4,
            "inbound_shipped_quantity": 4,
            "inbound_quantity": 8,
        }
    ]


def test_fetch_inventory_report_uses_inventory_specific_error_codes(monkeypatch):
    client = _make_client()

    monkeypatch.setattr(client, "_reports_api", lambda: object())
    monkeypatch.setattr(client, "_create_report_request", lambda _api, **_kwargs: {"reportId": "report-1"})
    monkeypatch.setattr(
        client,
        "_get_report_status",
        lambda _api, _report_id: {"processingStatus": "FATAL"},
    )
    monkeypatch.setattr(sp_api_client_module.time, "sleep", lambda *_args, **_kwargs: None)

    with pytest.raises(sp_api_client_module.AmazonAPIError) as exc_info:
        client.fetch_inventory_report()

    assert exc_info.value.error_code == "INVENTORY_REPORT_FATAL"
    assert "GET_FBA_MYI_ALL_INVENTORY_DATA" in exc_info.value.message


def test_format_datetime_normalizes_to_utc_z():
    aware_value = datetime(2026, 4, 13, 10, 30, tzinfo=timezone(timedelta(hours=2)))
    naive_value = datetime(2026, 4, 13, 10, 30)

    assert SPAPIClient._format_datetime(aware_value) == "2026-04-13T08:30:00Z"
    assert SPAPIClient._format_datetime(naive_value) == "2026-04-13T10:30:00Z"


@pytest.mark.asyncio
async def test_inventory_endpoint_uses_date_range_filters():
    db = FakeDb([FakeResult(values=[])])
    organization = SimpleNamespace(id=uuid4())
    account_id = uuid4()

    rows = await REPORTS_MODULE.get_inventory_data(
        current_user=None,
        organization=organization,
        db=db,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 7),
        account_id=account_id,
        asin="B001TEST",
        snapshot_date=None,
        account_ids=None,
        asins=None,
        low_stock_only=False,
        limit=50,
    )

    query = db.queries[0]
    compiled = query.compile()

    assert rows == []
    assert len(db.queries) == 1
    assert compiled.params["snapshot_date_1"] == date(2026, 4, 1)
    assert compiled.params["snapshot_date_2"] == date(2026, 4, 7)
    assert "inventory_data.snapshot_date >=" in str(query)
    assert "inventory_data.snapshot_date <=" in str(query)
    assert "inventory_data.asin IN" in str(query)


@pytest.mark.asyncio
async def test_inventory_endpoint_defaults_to_latest_snapshot_when_no_date_filters():
    db = FakeDb(
        [
            FakeResult(scalar_value=date(2026, 4, 13)),
            FakeResult(values=[]),
        ]
    )

    rows = await REPORTS_MODULE.get_inventory_data(
        current_user=None,
        organization=SimpleNamespace(id=uuid4()),
        db=db,
        snapshot_date=None,
        start_date=None,
        end_date=None,
        account_id=None,
        account_ids=None,
        asin=None,
        asins=None,
        low_stock_only=False,
        limit=100,
    )

    latest_query = db.queries[0]
    inventory_query = db.queries[1]
    compiled = inventory_query.compile()

    assert rows == []
    assert "max(inventory_data.snapshot_date)" in str(latest_query)
    assert compiled.params["snapshot_date_1"] == date(2026, 4, 13)


@pytest.mark.asyncio
async def test_advertising_endpoint_returns_external_campaign_id():
    row = SimpleNamespace(
        AdvertisingMetrics=SimpleNamespace(
            id=1,
            campaign_id=uuid4(),
            date=date(2026, 4, 13),
            impressions=1000,
            clicks=25,
            cost=Decimal("12.34"),
            attributed_sales_7d=Decimal("56.78"),
            attributed_units_ordered_7d=4,
            ctr=Decimal("2.5000"),
            cpc=Decimal("0.4936"),
            acos=Decimal("21.7300"),
            roas=Decimal("4.6013"),
        ),
        external_campaign_id="1234567890",
        campaign_name="Sponsored Products",
        campaign_type="sponsoredProducts",
    )
    db = FakeDb([FakeResult(values=[row])])

    rows = await REPORTS_MODULE.get_advertising_data(
        current_user=None,
        organization=SimpleNamespace(id=uuid4()),
        db=db,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 13),
        account_ids=None,
        campaign_types=["sponsoredProducts"],
        limit=25,
        offset=5,
    )

    assert len(rows) == 1
    assert rows[0].campaign_id == "1234567890"
    assert rows[0].campaign_name == "Sponsored Products"
    assert len(db.queries) == 1


@pytest.mark.asyncio
async def test_advertising_endpoint_rejects_invalid_date_range():
    db = FakeDb([])

    with pytest.raises(REPORTS_MODULE.HTTPException) as exc:
        await REPORTS_MODULE.get_advertising_data(
            current_user=None,
            organization=SimpleNamespace(id=uuid4()),
            db=db,
            start_date=date(2026, 4, 13),
            end_date=date(2026, 4, 1),
            account_ids=None,
            campaign_types=None,
            limit=25,
            offset=0,
        )

    assert exc.value.status_code == 422
