"""Unit tests for CatalogService, ImageService, and catalog schemas.

SP-API and S3 are mocked. The pattern mirrors test_product_trends_service.py:
FakeAsyncSession with a queue of pre-built responses, and SimpleNamespace
stand-ins for ORM rows.
"""
from __future__ import annotations

import importlib.metadata
import io
import sys
import types
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _ensure_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules.setdefault(name, module)


_ensure_package("app", ROOT / "app")
_ensure_package("app.api", ROOT / "app" / "api")
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
    UK=_Marketplace("A1F83G8C2ARO7P"),
    US=_Marketplace("ATVPDKIKX0DER"),
)
sp_api_base_stub.SellingApiRequestThrottledException = type(
    "SellingApiRequestThrottledException", (Exception,), {}
)
sys.modules.setdefault("sp_api.base", sp_api_base_stub)


sp_api_api_stub = types.ModuleType("sp_api.api")


class _ApiStub:
    def __init__(self, **_kwargs):
        pass


for _name in ("Reports", "Inventories", "CatalogItems", "Products", "Orders", "ListingsItems"):
    setattr(sp_api_api_stub, _name, _ApiStub)
sys.modules.setdefault("sp_api.api", sp_api_api_stub)


email_validator_stub = types.ModuleType("email_validator")


class _EmailNotValidError(ValueError):
    pass


def _validate_email(value, *args, **kwargs):
    return SimpleNamespace(normalized=value)


email_validator_stub.EmailNotValidError = _EmailNotValidError
email_validator_stub.validate_email = _validate_email
sys.modules.setdefault("email_validator", email_validator_stub)
_real_version = importlib.metadata.version


def _fake_version(name: str) -> str:
    if name == "email-validator":
        return "2.0.0"
    return _real_version(name)


importlib.metadata.version = _fake_version


sys.path.insert(0, str(ROOT))

# Stub boto3 so importing image_service does not require AWS creds.
boto3_stub = types.ModuleType("boto3")
boto3_stub.client = lambda *_a, **_kw: MagicMock()
sys.modules.setdefault("boto3", boto3_stub)

botocore_exceptions = types.ModuleType("botocore.exceptions")


class _BotoCoreError(Exception):
    pass


class _ClientError(Exception):
    pass


botocore_exceptions.BotoCoreError = _BotoCoreError
botocore_exceptions.ClientError = _ClientError
botocore_stub = types.ModuleType("botocore")
sys.modules.setdefault("botocore", botocore_stub)
sys.modules.setdefault("botocore.exceptions", botocore_exceptions)


from app.core.exceptions import AmazonAPIError  # noqa: E402
from app.models.amazon_account import AccountType  # noqa: E402
from app.schemas.catalog import (  # noqa: E402
    AvailabilityUpdateRequest,
    BulkErrorCode,
    BulkPriceUpdateRequest,
    CatalogChangeField,
    CatalogChangeStatus,
    PriceUpdate,
)
from app.services.catalog_service import (  # noqa: E402
    CatalogOperationError,
    CatalogService,
    import_template_bytes,
    parse_import_rows,
)
from app.services.image_service import (  # noqa: E402
    ALLOWED_CONTENT_TYPES,
    MAX_IMAGE_BYTES,
    ImageService,
    ImageUpload,
)


# ---------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def one_or_none(self):
        if len(self._rows) > 1:
            raise AssertionError("Expected zero or one row")
        return self._rows[0] if self._rows else None


class FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return FakeScalarResult(self._rows).one_or_none()

    def scalars(self):
        return FakeScalarResult(self._rows)


class FakeAsyncSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.added = []
        self.flushes = 0

    async def execute(self, _query):
        if not self._responses:
            raise AssertionError("Unexpected execute call")
        return FakeResult(self._responses.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushes += 1


def _account(
    *,
    account_id=None,
    organization_id=None,
    account_type=AccountType.SELLER,
    seller_id="SELLER1",
):
    return SimpleNamespace(
        id=account_id or uuid4(),
        organization_id=organization_id or uuid4(),
        account_type=account_type,
        seller_id=seller_id,
        marketplace_country="IT",
        account_name="Test Acct",
    )


def _product(*, asin="B000000001", sku="SKU-1", current_price=None, is_available=True):
    return SimpleNamespace(
        asin=asin,
        sku=sku,
        title="Old title",
        brand=None,
        category=None,
        current_price=current_price,
        is_available=is_available,
        is_active=True,
    )


def _patch_account_resolution(monkeypatch, service: CatalogService, account):
    async def _require(*_a, **_kw):
        return account

    async def _load_org(*_a, **_kw):
        return SimpleNamespace(id=account.organization_id)

    monkeypatch.setattr(service, "_require_seller_account", _require)
    monkeypatch.setattr(service, "_load_organization", _load_org)
    monkeypatch.setattr(service, "_create_sp_api_client", lambda *_a, **_kw: MagicMock())


# ---------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------


def test_price_update_rejects_negative_price():
    with pytest.raises(Exception):
        PriceUpdate(asin="B00ABCDEFG", price=Decimal("-1.00"))


def test_price_update_rejects_bad_asin():
    with pytest.raises(Exception):
        PriceUpdate(asin="not-an-asin", price=Decimal("10.00"))


def test_price_update_requires_asin_or_sku():
    with pytest.raises(Exception):
        PriceUpdate(price=Decimal("5.00"))


def test_price_update_rejects_more_than_two_decimal_places():
    with pytest.raises(Exception):
        PriceUpdate(asin="B00ABCDEFG", price=Decimal("9.999"))


def test_price_update_accepts_two_decimal_places():
    pu = PriceUpdate(asin="B00ABCDEFG", price=Decimal("9.99"))
    assert pu.price == Decimal("9.99")


def test_bulk_price_update_request_rejects_empty_updates():
    with pytest.raises(Exception):
        BulkPriceUpdateRequest(account_id=uuid4(), updates=[])


def test_availability_request_rejects_negative_quantity():
    with pytest.raises(Exception):
        AvailabilityUpdateRequest(account_id=uuid4(), is_available=True, quantity=-1)


# ---------------------------------------------------------------------
# update_prices_bulk
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_prices_bulk_mixed_results(monkeypatch):
    account = _account()
    user_id = uuid4()

    products = {
        "B0OK000001": _product(asin="B0OK000001", sku="SKU-A", current_price=Decimal("12.00")),
        "B0OK000002": _product(asin="B0OK000002", sku="SKU-B", current_price=Decimal("8.00")),
        "B0OK000003": _product(asin="B0OK000003", sku=None, current_price=Decimal("5.00")),
    }

    session = FakeAsyncSession([])
    service = CatalogService(session, user_id=user_id)
    _patch_account_resolution(monkeypatch, service, account)

    async def _resolve(_self, account_id, asin=None, sku=None):
        if asin == "B0MISSING1":
            return None
        return products.get(asin)

    monkeypatch.setattr(CatalogService, "_resolve_product", _resolve)

    sp_client = MagicMock()

    def _update_price(seller_id, sku, product_type, price, currency):
        if sku == "SKU-B":
            raise AmazonAPIError("SP-API throttled")
        return {"ok": True}

    sp_client.update_listing_price.side_effect = _update_price
    monkeypatch.setattr(service, "_create_sp_api_client", lambda *_a, **_kw: sp_client)

    payload = [
        PriceUpdate(asin="B0OK000001", price=Decimal("15.00")),
        PriceUpdate(asin="B0OK000002", price=Decimal("9.50")),
        PriceUpdate(asin="B0OK000003", price=Decimal("6.00")),
        PriceUpdate(asin="B0MISSING1", price=Decimal("4.00")),
    ]

    result = await service.update_prices_bulk(account.id, payload)

    assert result.succeeded == 1
    assert result.failed == 3
    assert result.total == 4
    assert {s.asin for s in result.successes} == {"B0OK000001"}

    codes = {e.code for e in result.errors}
    assert codes == {
        BulkErrorCode.SP_API_ERROR,
        BulkErrorCode.MISSING_SKU,
        BulkErrorCode.PRODUCT_NOT_FOUND,
    }

    audit_rows = [obj for obj in session.added if obj.__class__.__name__ == "CatalogChangeLog"]
    assert len(audit_rows) == 2
    statuses = {row.sp_api_status for row in audit_rows}
    assert statuses == {CatalogChangeStatus.SUCCESS.value, CatalogChangeStatus.FAILED.value}
    for row in audit_rows:
        assert row.user_id == user_id
        assert row.field == CatalogChangeField.PRICE.value


# ---------------------------------------------------------------------
# toggle_availability
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_availability_success_records_audit(monkeypatch):
    account = _account()
    product = _product(asin="B0PROD0001", sku="SKU-X", is_available=False)
    session = FakeAsyncSession([])
    service = CatalogService(session, user_id=uuid4())
    _patch_account_resolution(monkeypatch, service, account)

    async def _load(_self, _account_id, _asin):
        return product

    monkeypatch.setattr(CatalogService, "_load_product", _load)
    sp_client = MagicMock()
    monkeypatch.setattr(service, "_create_sp_api_client", lambda *_a, **_kw: sp_client)

    result = await service.toggle_availability(
        account_id=account.id, asin="B0PROD0001", is_available=True, quantity=5
    )

    assert result.is_available is True
    assert result.pushed_quantity == 5
    sp_client.set_listing_quantity.assert_called_once()

    audit = [o for o in session.added if o.__class__.__name__ == "CatalogChangeLog"]
    assert len(audit) == 1
    assert audit[0].sp_api_status == CatalogChangeStatus.SUCCESS.value
    assert audit[0].old_value == {"is_available": False, "is_active": True}


@pytest.mark.asyncio
async def test_toggle_availability_failure_records_and_raises(monkeypatch):
    account = _account()
    product = _product(asin="B0PROD0002", sku="SKU-Y")
    session = FakeAsyncSession([])
    service = CatalogService(session, user_id=uuid4())
    _patch_account_resolution(monkeypatch, service, account)

    async def _load(_self, _account_id, _asin):
        return product

    monkeypatch.setattr(CatalogService, "_load_product", _load)

    sp_client = MagicMock()
    sp_client.set_listing_quantity.side_effect = AmazonAPIError("Boom")
    monkeypatch.setattr(service, "_create_sp_api_client", lambda *_a, **_kw: sp_client)

    with pytest.raises(CatalogOperationError):
        await service.toggle_availability(
            account_id=account.id, asin="B0PROD0002", is_available=False
        )

    audit = [o for o in session.added if o.__class__.__name__ == "CatalogChangeLog"]
    assert len(audit) == 1
    assert audit[0].sp_api_status == CatalogChangeStatus.FAILED.value
    assert audit[0].sp_api_error == "Boom"


# ---------------------------------------------------------------------
# bulk_update_from_excel
# ---------------------------------------------------------------------


def _make_excel_bytes(rows):
    import pandas as pd

    df = pd.DataFrame(rows)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="listings")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_bulk_update_from_excel_mixed_results(monkeypatch):
    account = _account()
    session = FakeAsyncSession(
        # _mirror_local_listing performs one select per processed sku.
        # Snapshot lookup before SP-API also queries once per sku.
        [[]] * 20
    )
    service = CatalogService(session, user_id=uuid4())
    _patch_account_resolution(monkeypatch, service, account)

    sp_client = MagicMock()

    def _update(seller_id, sku, product_type, attributes):
        if sku == "SKU-FAIL":
            raise AmazonAPIError("Bad attribute")
        return {"ok": True}

    sp_client.update_listing_attributes.side_effect = _update
    monkeypatch.setattr(service, "_create_sp_api_client", lambda *_a, **_kw: sp_client)

    rows = [
        {"sku": "SKU-OK", "title": "New title"},
        {"sku": "SKU-FAIL", "title": "Other title"},
        {"sku": "SKU-EMPTY"},  # no actual attributes -> skipped
    ]
    payload = _make_excel_bytes(rows)

    result = await service.bulk_update_from_excel(account.id, payload)

    assert result.succeeded == 1
    assert result.failed == 1
    assert result.skipped == 1
    assert result.total == 3
    successes_skus = {s.sku for s in result.successes}
    assert successes_skus == {"SKU-OK"}
    error_codes = {e.code for e in result.errors}
    assert error_codes == {BulkErrorCode.SP_API_ERROR}
    # Row 2 (header at row 1) is the failing one.
    assert result.errors[0].row == 3

    audit = [o for o in session.added if o.__class__.__name__ == "CatalogChangeLog"]
    assert len(audit) == 2  # one success + one failed; the empty row is skipped


@pytest.mark.asyncio
async def test_bulk_update_from_excel_rejects_missing_sku_column():
    session = FakeAsyncSession([])
    service = CatalogService(session)
    payload = _make_excel_bytes([{"title": "No sku column"}])

    async def _req(_account_id):
        return _account()

    async def _load_org(*_a, **_kw):
        return None

    service._require_seller_account = _req
    service._load_organization = _load_org
    service._create_sp_api_client = lambda *_a, **_kw: MagicMock()

    with pytest.raises(CatalogOperationError, match="sku"):
        await service.bulk_update_from_excel(uuid4(), payload)


# ---------------------------------------------------------------------
# Manual catalog import — parser
# ---------------------------------------------------------------------


def _make_csv_bytes(text: str, *, bom: bool = False) -> bytes:
    prefix = "﻿" if bom else ""
    return (prefix + text).encode("utf-8")


def test_parse_import_rows_accepts_clean_csv():
    csv = "asin,sku,title,brand,category\nB000000001,SKU-1,Title 1,Acme,Home\n"
    rows, errors = parse_import_rows(_make_csv_bytes(csv), "import.csv")
    assert errors == []
    assert len(rows) == 1
    assert rows[0] == {
        "asin": "B000000001",
        "sku": "SKU-1",
        "title": "Title 1",
        "brand": "Acme",
        "category": "Home",
    }


def test_parse_import_rows_accepts_excel():
    payload = _make_excel_bytes(
        [{"asin": "B000000002", "sku": "SKU-2", "title": "T2", "brand": "B", "category": "C"}]
    )
    rows, errors = parse_import_rows(payload, "import.xlsx")
    assert errors == []
    assert rows[0]["asin"] == "B000000002"
    assert rows[0]["title"] == "T2"


def test_parse_import_rows_handles_bom_and_whitespace_headers():
    csv = "  ASIN , Title \nB000000003, Hello \n"
    rows, errors = parse_import_rows(_make_csv_bytes(csv, bom=True), "import.csv")
    assert errors == []
    assert rows[0]["asin"] == "B000000003"
    assert rows[0]["title"] == "Hello"


def test_parse_import_rows_rejects_malformed_asin():
    csv = "asin,title\nb000000001,lowercase\nSHORT,too short\nB000000004,Good\n"
    rows, errors = parse_import_rows(_make_csv_bytes(csv), "import.csv")
    assert {r["asin"] for r in rows} == {"B000000004"}
    assert len(errors) == 2
    assert {e.code for e in errors} == {BulkErrorCode.INVALID_INPUT}
    # Header on row 1 -> first data row is 2.
    assert errors[0].row == 2


def test_parse_import_rows_dedups_within_file():
    csv = "asin,title\nB000000005,First\nB000000005,Second\n"
    rows, errors = parse_import_rows(_make_csv_bytes(csv), "import.csv")
    assert errors == []
    assert len(rows) == 1
    assert rows[0]["title"] == "First"


def test_parse_import_rows_requires_asin_column():
    csv = "sku,title\nSKU-1,No asin column\n"
    with pytest.raises(CatalogOperationError, match="asin"):
        parse_import_rows(_make_csv_bytes(csv), "import.csv")


def test_import_template_bytes_has_header_and_example():
    content = import_template_bytes().decode("utf-8-sig")
    lines = content.strip().splitlines()
    assert lines[0] == "asin,sku,title,brand,category"
    assert len(lines) == 2


# ---------------------------------------------------------------------
# import_products_from_file — upsert
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_creates_and_updates_products(monkeypatch):
    account_id = uuid4()
    existing = _product(asin="B000000010", sku="OLD-SKU")
    existing.title = "Existing title"
    existing.source = "amazon_sync"
    session = FakeAsyncSession([])
    service = CatalogService(session, user_id=uuid4())

    async def _load(_self, _account_id, asin):
        return existing if asin == "B000000010" else None

    monkeypatch.setattr(CatalogService, "_load_product", _load)

    csv = (
        "asin,sku,title,brand,category\n"
        "B000000010,NEW-SKU,Updated title,Acme,Home\n"  # update existing
        "B000000011,FRESH,Brand new,NewCo,Garden\n"      # create new
        "bad,,no asin,,\n"                               # invalid -> error
    )
    result = await service.import_products_from_file(account_id, _make_csv_bytes(csv), "import.csv")

    assert result.total == 3
    assert result.succeeded == 2
    assert result.failed == 1
    assert result.skipped == 0

    # Existing row updated in place and stamped as manual import.
    assert existing.title == "Updated title"
    assert existing.sku == "NEW-SKU"
    assert existing.source == "manual_import"
    assert existing.is_active is True

    created = [o for o in session.added if o.__class__.__name__ == "Product"]
    assert len(created) == 1
    assert created[0].asin == "B000000011"
    assert created[0].source == "manual_import"


@pytest.mark.asyncio
async def test_import_never_blanks_existing_title(monkeypatch):
    account_id = uuid4()
    existing = _product(asin="B000000020", sku="KEEP-SKU")
    existing.title = "Keep me"
    session = FakeAsyncSession([])
    service = CatalogService(session, user_id=uuid4())

    async def _load(_self, _account_id, _asin):
        return existing

    monkeypatch.setattr(CatalogService, "_load_product", _load)

    # Empty title / sku cells must not wipe synced data.
    csv = "asin,sku,title,brand,category\nB000000020,,,Acme,\n"
    result = await service.import_products_from_file(account_id, _make_csv_bytes(csv), "import.csv")

    assert result.succeeded == 1
    assert existing.title == "Keep me"
    assert existing.sku == "KEEP-SKU"
    assert existing.brand == "Acme"
    assert existing.source == "manual_import"


# ---------------------------------------------------------------------
# ImageService validation
# ---------------------------------------------------------------------


def _image(content_type="image/png", size=1024, is_main=False):
    return ImageUpload(
        filename="x.png",
        content_type=content_type,
        data=b"\x00" * size,
        is_main=is_main,
    )


def test_image_service_validates_allowed_mime():
    svc = ImageService(db=MagicMock())
    svc.validate_upload(_image(content_type="image/png"))
    assert "image/png" in ALLOWED_CONTENT_TYPES


def test_image_service_rejects_unsupported_mime():
    svc = ImageService(db=MagicMock())
    with pytest.raises(CatalogOperationError, match="Unsupported"):
        svc.validate_upload(_image(content_type="application/pdf"))


def test_image_service_rejects_empty():
    svc = ImageService(db=MagicMock())
    with pytest.raises(CatalogOperationError, match="Empty"):
        svc.validate_upload(_image(size=0))


def test_image_service_rejects_too_large():
    svc = ImageService(db=MagicMock())
    with pytest.raises(CatalogOperationError, match="exceeds"):
        svc.validate_upload(_image(size=MAX_IMAGE_BYTES + 1))


# ---------------------------------------------------------------------
# ImageService.upload_images writes an audit row
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_image_service_upload_writes_audit_row(monkeypatch):
    account = _account()
    product = _product(asin="B0IMG00001", sku="SKU-IMG")
    session = FakeAsyncSession([])
    svc = ImageService(db=session, user_id=uuid4())

    async def _req(*_a, **_kw):
        return account

    async def _load_product(_self, _account_id, _asin):
        return product

    async def _load_org(*_a, **_kw):
        return SimpleNamespace(id=account.organization_id)

    monkeypatch.setattr(svc, "_require_seller_account", _req)
    monkeypatch.setattr(ImageService, "_load_product", _load_product)
    monkeypatch.setattr(svc, "_load_organization", _load_org)
    monkeypatch.setattr(
        svc,
        "_upload_to_s3",
        lambda org_id, acc_id, asin, upload: f"catalog/{org_id}/{acc_id}/{asin}/abc.png",
    )

    sp_client = MagicMock()
    sp_client.update_listing_images.return_value = {"ok": True}
    monkeypatch.setattr(svc, "_create_sp_api_client", lambda *_a, **_kw: sp_client)

    uploads = [_image(is_main=True), _image()]
    result = await svc.upload_images(account.id, "B0IMG00001", uploads)

    assert result["main_image_url"]
    assert result["sp_api_error"] is None

    audit = [o for o in session.added if o.__class__.__name__ == "CatalogChangeLog"]
    assert len(audit) == 1
    assert audit[0].sp_api_status == CatalogChangeStatus.SUCCESS.value
    assert audit[0].field == CatalogChangeField.IMAGE.value
    assert audit[0].asin == "B0IMG00001"


@pytest.mark.asyncio
async def test_image_service_upload_records_sp_api_failure(monkeypatch):
    account = _account()
    product = _product(asin="B0IMG00002", sku="SKU-IMG2")
    session = FakeAsyncSession([])
    svc = ImageService(db=session, user_id=uuid4())

    async def _req(*_a, **_kw):
        return account

    async def _load_product(_self, _account_id, _asin):
        return product

    async def _load_org(*_a, **_kw):
        return SimpleNamespace(id=account.organization_id)

    monkeypatch.setattr(svc, "_require_seller_account", _req)
    monkeypatch.setattr(ImageService, "_load_product", _load_product)
    monkeypatch.setattr(svc, "_load_organization", _load_org)
    monkeypatch.setattr(
        svc,
        "_upload_to_s3",
        lambda org_id, acc_id, asin, upload: f"catalog/{org_id}/{acc_id}/{asin}/x.png",
    )

    sp_client = MagicMock()
    sp_client.update_listing_images.side_effect = AmazonAPIError("Image too big")
    monkeypatch.setattr(svc, "_create_sp_api_client", lambda *_a, **_kw: sp_client)

    result = await svc.upload_images(account.id, "B0IMG00002", [_image(is_main=True)])

    assert result["sp_api_error"] == "Image too big"
    audit = [o for o in session.added if o.__class__.__name__ == "CatalogChangeLog"]
    assert len(audit) == 1
    assert audit[0].sp_api_status == CatalogChangeStatus.FAILED.value
    assert audit[0].sp_api_error == "Image too big"


@pytest.mark.asyncio
async def test_image_service_delete_writes_audit_row(monkeypatch):
    account = _account()
    product = _product(asin="B0IMG00003", sku="SKU-IMG3")
    session = FakeAsyncSession([])
    svc = ImageService(db=session, user_id=uuid4())

    async def _req(*_a, **_kw):
        return account

    async def _load_product(_self, _account_id, _asin):
        return product

    monkeypatch.setattr(svc, "_require_seller_account", _req)
    monkeypatch.setattr(ImageService, "_load_product", _load_product)
    monkeypatch.setattr(svc, "_delete_key", lambda _key: None)

    key = f"catalog/{account.organization_id}/{account.id}/B0IMG00003/old.png"
    result = await svc.delete_image(account.id, "B0IMG00003", key)

    assert result == {"deleted": key, "amazon_listing_updated": False}
    audit = [o for o in session.added if o.__class__.__name__ == "CatalogChangeLog"]
    assert len(audit) == 1
    assert audit[0].sp_api_status == CatalogChangeStatus.SUCCESS.value
    assert audit[0].field == CatalogChangeField.IMAGE.value
    assert audit[0].old_value["key"] == key
    assert audit[0].new_value is None
