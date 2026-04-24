import pytest
from fastapi import HTTPException

from app.api.v1.alerts import (
    AlertStatus,
    AlertType,
    _resolve_alert_type_filter,
    _resolve_status_filter,
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
