from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.alerts import (
    AlertStatus,
    AlertType,
    _resolve_alert_type_filter,
    _resolve_status_filter,
    _validate_rule_accounts,
)


def test_resolve_status_filter_maps_deprecated_is_read_true():
    assert _resolve_status_filter(None, True) == AlertStatus.read


def test_resolve_status_filter_maps_deprecated_is_read_false():
    assert _resolve_status_filter(None, False) == AlertStatus.unread


def test_resolve_status_filter_rejects_conflicting_params():
    with pytest.raises(HTTPException) as exc_info:
        _resolve_status_filter(AlertStatus.read, False)

    assert exc_info.value.status_code == 422


def test_resolve_alert_type_filter_prefers_canonical_value():
    assert _resolve_alert_type_filter(AlertType.low_stock, None) == AlertType.low_stock


def test_resolve_alert_type_filter_rejects_conflicting_values():
    with pytest.raises(HTTPException) as exc_info:
        _resolve_alert_type_filter(AlertType.low_stock, AlertType.sync_failure)

    assert exc_info.value.status_code == 422


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return [(row,) for row in self._rows]


class _FakeDb:
    def __init__(self, visible_account_ids):
        self._visible = visible_account_ids

    async def execute(self, statement):
        return _FakeResult(self._visible)


@pytest.mark.asyncio
async def test_validate_rule_accounts_rejects_foreign_account():
    own = uuid4()
    foreign = uuid4()
    db = _FakeDb([own])

    with pytest.raises(HTTPException) as exc_info:
        await _validate_rule_accounts(db, uuid4(), [own, foreign])

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_validate_rule_accounts_allows_own_accounts():
    own = [uuid4(), uuid4()]

    await _validate_rule_accounts(_FakeDb(own), uuid4(), own)


@pytest.mark.asyncio
async def test_validate_rule_accounts_noop_without_filter():
    await _validate_rule_accounts(_FakeDb([]), uuid4(), None)
