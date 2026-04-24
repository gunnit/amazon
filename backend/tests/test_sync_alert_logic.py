from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.core.exceptions import AmazonAPIError
from app.core.sync_health import build_sync_incident, classify_sync_exception
from app.models.amazon_account import SyncStatus


def _account(**overrides):
    now = datetime(2026, 4, 2, 12, 0, 0)
    base = {
        "id": uuid4(),
        "account_name": "EU Seller",
        "created_at": now - timedelta(days=10),
        "last_sync_at": now - timedelta(hours=4),
        "last_sync_succeeded_at": now - timedelta(hours=4),
        "last_sync_failed_at": None,
        "last_sync_attempt_at": now - timedelta(hours=4),
        "last_sync_started_at": now - timedelta(hours=4),
        "last_sync_heartbeat_at": now - timedelta(hours=4),
        "sync_status": SyncStatus.SUCCESS,
        "sync_error_message": None,
        "sync_error_code": None,
        "sync_error_kind": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_sync_incident_detects_delayed_sync():
    now = datetime(2026, 4, 2, 12, 0, 0)
    account = _account(
        last_sync_at=now - timedelta(hours=27),
        last_sync_succeeded_at=now - timedelta(hours=27),
        last_sync_attempt_at=now - timedelta(hours=26),
    )

    incident = build_sync_incident(account, now=now)

    assert incident is not None
    assert incident["incident_type"] == "sync_delayed"
    assert incident["severity"] == "warning"
    assert incident["details"]["delay_hours"] == 27.0


def test_build_sync_incident_uses_account_override_thresholds():
    now = datetime(2026, 4, 2, 12, 0, 0)
    account = _account(
        last_sync_at=now - timedelta(hours=8),
        last_sync_succeeded_at=now - timedelta(hours=8),
    )

    incident = build_sync_incident(
        account,
        conditions={
            "stale_after_hours": 24,
            "account_threshold_overrides": {
                str(account.id): {"stale_after_hours": 6, "grace_period_minutes": 0},
            },
        },
        now=now,
    )

    assert incident is not None
    assert incident["incident_type"] == "sync_delayed"


def test_build_sync_incident_detects_stuck_sync():
    now = datetime(2026, 4, 2, 12, 0, 0)
    account = _account(
        sync_status=SyncStatus.SYNCING,
        last_sync_started_at=now - timedelta(hours=3),
        last_sync_attempt_at=now - timedelta(hours=3),
        last_sync_heartbeat_at=now - timedelta(hours=3),
        last_sync_at=now - timedelta(hours=2),
        last_sync_succeeded_at=now - timedelta(hours=2),
        sync_error_kind="transient",
    )

    incident = build_sync_incident(account, now=now)

    assert incident is not None
    assert incident["incident_type"] == "sync_stuck"
    assert incident["severity"] == "critical"


def test_build_sync_incident_detects_terminal_failure():
    now = datetime(2026, 4, 2, 12, 0, 0)
    account = _account(
        sync_status=SyncStatus.ERROR,
        sync_error_kind="terminal",
        sync_error_message="Auth failed",
        sync_error_code="AUTH_FAILED",
        last_sync_failed_at=now - timedelta(minutes=10),
    )

    incident = build_sync_incident(account, now=now)

    assert incident is not None
    assert incident["incident_type"] == "sync_failed"
    assert incident["severity"] == "critical"
    assert "Reconnect" in incident["details"]["recommended_action"]


def test_build_sync_incident_detects_never_synced_after_grace_window():
    now = datetime(2026, 4, 2, 12, 0, 0)
    account = _account(
        created_at=now - timedelta(hours=30),
        last_sync_at=None,
        last_sync_succeeded_at=None,
        last_sync_attempt_at=None,
        last_sync_started_at=None,
        last_sync_heartbeat_at=None,
        sync_status=SyncStatus.PENDING,
    )

    incident = build_sync_incident(account, now=now)

    assert incident is not None
    assert incident["incident_type"] == "sync_never_succeeded"


def test_classify_sync_exception_marks_auth_failures_as_terminal():
    decision = classify_sync_exception(
        AmazonAPIError("bad credentials", error_code="AUTH_FAILED"),
        retries=0,
        max_retries=3,
    )

    assert decision.kind == "terminal"
    assert decision.retry_delay is None


def test_classify_sync_exception_marks_throttling_as_retryable():
    throttled = type("SellingApiRequestThrottledException", (Exception,), {})("slow down")

    decision = classify_sync_exception(throttled, retries=1, max_retries=3)

    assert decision.kind == "transient"
    assert decision.retry_delay == 60


def test_classify_sync_exception_stops_retrying_after_max_retries():
    decision = classify_sync_exception(RuntimeError("boom"), retries=3, max_retries=3)

    assert decision.kind == "terminal"
    assert decision.retry_delay is None
