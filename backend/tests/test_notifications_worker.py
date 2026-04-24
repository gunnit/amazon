from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.alerts import AlertType, _validate_rule_payload
from workers.tasks.notifications import (
    _bsr_baseline,
    _build_batch_payload,
    _build_dedup_key,
    _format_age,
)


def test_build_dedup_key_includes_event_scope():
    account_id = uuid4()

    key = _build_dedup_key("low_stock", account_id=account_id, asin="B001TEST")

    assert key == f"low_stock:{account_id}:B001TEST"


def test_format_age_returns_never_when_missing_timestamp():
    assert _format_age(None) == "never"


def test_bsr_baseline_uses_daily_best_rank_and_median():
    history_rows = [
        SimpleNamespace(date=datetime(2026, 4, 2).date(), bsr=2200),
        SimpleNamespace(date=datetime(2026, 4, 2).date(), bsr=2100),
        SimpleNamespace(date=datetime(2026, 4, 1).date(), bsr=1200),
        SimpleNamespace(date=datetime(2026, 3, 31).date(), bsr=1000),
        SimpleNamespace(date=datetime(2026, 3, 30).date(), bsr=1400),
    ]

    latest_bsr, baseline_bsr = _bsr_baseline(history_rows, min_history_points=4)

    assert latest_bsr == 2100
    assert baseline_bsr == pytest.approx(1200)


def test_build_batch_payload_summarizes_multiple_alerts():
    alerts = [
        SimpleNamespace(
            id=uuid4(),
            details={"account_name": "EU Store"},
            severity="warning",
            account_id=uuid4(),
            asin="B001",
            message="Low stock on B001",
        ),
        SimpleNamespace(
            id=uuid4(),
            details={"account_name": "EU Store"},
            severity="critical",
            account_id=uuid4(),
            asin="B002",
            message="Low stock on B002",
        ),
    ]
    rule = SimpleNamespace(name="Stock Guard")

    message, details = _build_batch_payload(rule, alerts)

    assert "2 alerts triggered" in message
    assert details["count"] == 2
    assert details["severity_counts"] == {"warning": 1, "critical": 1}
    assert len(details["alerts"]) == 2


def test_validate_rule_payload_normalizes_low_stock_defaults():
    conditions = _validate_rule_payload(
        alert_type=AlertType.low_stock,
        conditions={"threshold": "12"},
        notification_channels=["email"],
    )

    assert conditions == {"threshold": 12, "recovery_buffer": 2}


def test_validate_rule_payload_rejects_invalid_price_range():
    with pytest.raises(HTTPException) as exc_info:
        _validate_rule_payload(
            alert_type=AlertType.price_change,
            conditions={"min_price": 20, "max_price": 10},
            notification_channels=["email"],
        )

    assert exc_info.value.status_code == 422
    assert "min_price must be <=" in exc_info.value.detail


def test_validate_rule_payload_rejects_invalid_bsr_window():
    with pytest.raises(HTTPException) as exc_info:
        _validate_rule_payload(
            alert_type=AlertType.bsr_drop,
            conditions={"drop_percent": 15, "lookback_days": 3, "min_history_points": 5},
            notification_channels=["webhook"],
        )

    assert exc_info.value.status_code == 422
    assert "min_history_points" in exc_info.value.detail
