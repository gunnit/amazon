from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
SP_API_CLIENT_PATH = ROOT / "app" / "core" / "amazon" / "sp_api_client.py"


def _ensure_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules.setdefault(name, module)


_ensure_package("app", ROOT / "app")
_ensure_package("app.core", ROOT / "app" / "core")
_ensure_package("app.core.amazon", ROOT / "app" / "core" / "amazon")


class FakeMarketplace:
    def __init__(self, name: str):
        self.name = name
        self.marketplace_id = f"{name}-marketplace"


marketplaces_module = types.ModuleType("sp_api.base")
marketplaces_module.Marketplaces = types.SimpleNamespace(
    IT=FakeMarketplace("IT"),
    DE=FakeMarketplace("DE"),
    FR=FakeMarketplace("FR"),
    ES=FakeMarketplace("ES"),
    UK=FakeMarketplace("UK"),
    US=FakeMarketplace("US"),
    CA=FakeMarketplace("CA"),
    MX=FakeMarketplace("MX"),
    BR=FakeMarketplace("BR"),
    JP=FakeMarketplace("JP"),
    AU=FakeMarketplace("AU"),
    IN=FakeMarketplace("IN"),
    AE=FakeMarketplace("AE"),
    SG=FakeMarketplace("SG"),
    NL=FakeMarketplace("NL"),
    SE=FakeMarketplace("SE"),
    PL=FakeMarketplace("PL"),
    TR=FakeMarketplace("TR"),
    BE=FakeMarketplace("BE"),
)
marketplaces_module.SellingApiRequestThrottledException = type(
    "SellingApiRequestThrottledException",
    (Exception,),
    {},
)
sys.modules["sp_api.base"] = marketplaces_module

api_module = types.ModuleType("sp_api.api")
for class_name in ("Reports", "Inventories", "CatalogItems", "Products", "Orders", "VendorOrders"):
    setattr(api_module, class_name, type(class_name, (), {}))
sys.modules["sp_api.api"] = api_module

config_module = types.ModuleType("app.config")
config_module.settings = types.SimpleNamespace(
    SP_API_REPORT_POLL_INTERVAL_SECONDS=2,
    SP_API_REPORT_POLL_MAX_ATTEMPTS=5,
)
sys.modules["app.config"] = config_module

exceptions_module = types.ModuleType("app.core.exceptions")
exceptions_module.AmazonAPIError = type("AmazonAPIError", (Exception,), {})
sys.modules["app.core.exceptions"] = exceptions_module

SP_API_SPEC = spec_from_file_location("sp_api_client_under_test", SP_API_CLIENT_PATH)
SP_API_MODULE = module_from_spec(SP_API_SPEC)
assert SP_API_SPEC is not None and SP_API_SPEC.loader is not None
SP_API_SPEC.loader.exec_module(SP_API_MODULE)


def _make_client():
    return SP_API_MODULE.SPAPIClient(
        {
            "refresh_token": "refresh-token",
            "lwa_app_id": "lwa-app-id",
            "lwa_client_secret": "lwa-client-secret",
        },
        SP_API_MODULE.resolve_marketplace("IT"),
    )


def test_fetch_returns_report_parses_and_normalizes_rows(monkeypatch):
    client = _make_client()
    call_args = {}
    statuses = [
        {"processingStatus": "IN_PROGRESS"},
        {"processingStatus": "DONE", "reportDocumentId": "doc-1"},
    ]
    report_body = (
        "return-date\torder-id\tsku\tasin\tquantity\treason\tstatus\tdetailed-disposition\n"
        "2026-04-01\tORDER-1\tSKU-1\tB001TEST\t2\tno longer needed\tSELLABLE\tCustomer Damaged\n"
        "2026-04-02\t\tSKU-2\t\t1\tDAMAGED BY CARRIER\tDEFECTIVE\tWarehouse Damaged\n"
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
    monkeypatch.setattr(SP_API_MODULE.time, "sleep", lambda *_args, **_kwargs: None)

    rows = client.fetch_returns_report()

    assert call_args["reportType"] == "GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA"
    assert call_args["marketplaceIds"] == [client.marketplace.marketplace_id]
    assert rows == [
        {
            "amazon_order_id": "ORDER-1",
            "asin": "B001TEST",
            "sku": "SKU-1",
            "return_date": SP_API_MODULE.date(2026, 4, 1),
            "quantity": 2,
            "reason": "No Longer Needed",
            "disposition": "SELLABLE",
            "detailed_disposition": "Customer Damaged",
        },
        {
            "amazon_order_id": None,
            "asin": None,
            "sku": "SKU-2",
            "return_date": SP_API_MODULE.date(2026, 4, 2),
            "quantity": 1,
            "reason": "Damaged",
            "disposition": "DEFECTIVE",
            "detailed_disposition": "Warehouse Damaged",
        },
    ]


def test_fetch_returns_report_supports_eu_dates_and_uppercases_asin(monkeypatch):
    client = _make_client()
    statuses = [
        {"processingStatus": "DONE", "reportDocumentId": "doc-2"},
    ]
    report_body = (
        "return-date\torder-id\tsku\tasin\tquantity\treason\tstatus\tdetailed-disposition\n"
        "13/04/2026\tORDER-2\tSKU-3\tb00eu123\t1\twrong item\tSELLABLE\tCustomer Damaged\n"
    )

    monkeypatch.setattr(client, "_reports_api", lambda: object())
    monkeypatch.setattr(client, "_create_report_request", lambda _api, **_kwargs: {"reportId": "report-2"})
    monkeypatch.setattr(client, "_get_report_status", lambda _api, _report_id: statuses.pop(0))
    monkeypatch.setattr(
        client,
        "_download_report_document",
        lambda _api, _document_id: {"document": report_body},
    )
    monkeypatch.setattr(SP_API_MODULE.time, "sleep", lambda *_args, **_kwargs: None)

    rows = client.fetch_returns_report()

    assert rows == [
        {
            "amazon_order_id": "ORDER-2",
            "asin": "B00EU123",
            "sku": "SKU-3",
            "return_date": SP_API_MODULE.date(2026, 4, 13),
            "quantity": 1,
            "reason": "Wrong Item",
            "disposition": "SELLABLE",
            "detailed_disposition": "Customer Damaged",
        }
    ]
