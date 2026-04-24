"""Pure helpers for sync health state and alerting."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Optional

from app.core.exceptions import AmazonAPIError

DEFAULT_SYNC_FAILURE_CONDITIONS = {
    "stale_after_hours": 24,
    "grace_period_minutes": 90,
    "stuck_after_minutes": 120,
}

SYNC_INCIDENT_LABELS = {
    "sync_failed": "Sync failed",
    "sync_delayed": "Sync delayed",
    "sync_stuck": "Sync stuck",
    "sync_never_succeeded": "Sync never completed",
}

TERMINAL_AMAZON_ERROR_CODES = {
    "MISSING_CREDENTIALS",
    "AUTH_FAILED",
    "INVALID_MARKETPLACE",
    "INVENTORY_REPORT_FATAL",
    "INVENTORY_REPORT_CANCELLED",
    "INVENTORY_NOT_AVAILABLE",
}
TERMINAL_SYNC_EXCEPTION_NAMES = {"SellingApiForbiddenException"}
TRANSIENT_SYNC_EXCEPTION_NAMES = {
    "SellingApiRequestThrottledException",
    "SellingApiServerException",
    "SellingApiTemporarilyUnavailableException",
}


def classify_sync_exception(exc: Exception, retries: int = 0, max_retries: int = 3):
    """Classify a sync failure into retryable vs terminal."""
    exc_name = type(exc).__name__
    error_code = getattr(exc, "error_code", None)
    if retries >= max_retries:
        return SimpleNamespace(kind="terminal", error_code=error_code or exc_name, retry_delay=None)

    if isinstance(exc, AmazonAPIError):
        if error_code in TERMINAL_AMAZON_ERROR_CODES:
            return SimpleNamespace(kind="terminal", error_code=error_code, retry_delay=None)
        return SimpleNamespace(kind="transient", error_code=error_code or "AMAZON_API_ERROR", retry_delay=300)

    if exc_name in TERMINAL_SYNC_EXCEPTION_NAMES:
        return SimpleNamespace(kind="terminal", error_code=exc_name, retry_delay=None)

    if exc_name == "SellingApiRequestThrottledException":
        return SimpleNamespace(kind="transient", error_code=exc_name, retry_delay=60)

    if exc_name in TRANSIENT_SYNC_EXCEPTION_NAMES:
        return SimpleNamespace(kind="transient", error_code=exc_name, retry_delay=300)

    return SimpleNamespace(kind="transient", error_code=exc_name, retry_delay=300)


def _coerce_positive_int(value: Any, fallback: int) -> int:
    """Parse positive integer values used in alert thresholds."""
    try:
        parsed = int(value)
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def to_utc_naive(value: Optional[datetime]) -> Optional[datetime]:
    """Normalize datetimes for safe arithmetic in workers."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def isoformat_utc(value: Optional[datetime]) -> Optional[str]:
    """Serialize timestamps for alert payloads."""
    normalized = to_utc_naive(value)
    return normalized.isoformat() + "Z" if normalized else None


def format_duration(delta: Optional[timedelta]) -> str:
    """Format a duration in a compact, user-facing way."""
    if delta is None:
        return "unknown"

    total_seconds = max(int(delta.total_seconds()), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60

    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    if minutes:
        return f"{minutes}m"
    return "0m"


def _enum_value(value: Any) -> str:
    """Return the raw enum/string value for comparisons."""
    return value.value if hasattr(value, "value") else str(value or "")


def normalize_sync_failure_conditions(conditions: Optional[dict]) -> dict:
    """Normalize sync_failure conditions and per-account overrides."""
    raw = conditions or {}
    normalized = {
        "stale_after_hours": _coerce_positive_int(
            raw.get("stale_after_hours"),
            DEFAULT_SYNC_FAILURE_CONDITIONS["stale_after_hours"],
        ),
        "grace_period_minutes": _coerce_positive_int(
            raw.get("grace_period_minutes"),
            DEFAULT_SYNC_FAILURE_CONDITIONS["grace_period_minutes"],
        ),
        "stuck_after_minutes": _coerce_positive_int(
            raw.get("stuck_after_minutes"),
            DEFAULT_SYNC_FAILURE_CONDITIONS["stuck_after_minutes"],
        ),
        "account_threshold_overrides": {},
    }

    overrides = raw.get("account_threshold_overrides")
    if isinstance(overrides, dict):
        for account_id, override in overrides.items():
            if not isinstance(override, dict):
                continue
            normalized["account_threshold_overrides"][str(account_id)] = {
                "stale_after_hours": _coerce_positive_int(
                    override.get("stale_after_hours"),
                    normalized["stale_after_hours"],
                ),
                "grace_period_minutes": _coerce_positive_int(
                    override.get("grace_period_minutes"),
                    normalized["grace_period_minutes"],
                ),
                "stuck_after_minutes": _coerce_positive_int(
                    override.get("stuck_after_minutes"),
                    normalized["stuck_after_minutes"],
                ),
            }

    return normalized


def _effective_sync_thresholds(account_id, conditions: dict) -> dict:
    """Resolve thresholds, honoring per-account overrides when configured."""
    override = (conditions.get("account_threshold_overrides") or {}).get(str(account_id), {})
    return {
        "stale_after_hours": _coerce_positive_int(
            override.get("stale_after_hours"),
            conditions["stale_after_hours"],
        ),
        "grace_period_minutes": _coerce_positive_int(
            override.get("grace_period_minutes"),
            conditions["grace_period_minutes"],
        ),
        "stuck_after_minutes": _coerce_positive_int(
            override.get("stuck_after_minutes"),
            conditions["stuck_after_minutes"],
        ),
    }


def build_sync_incident(
    account,
    conditions: Optional[dict] = None,
    now: Optional[datetime] = None,
) -> Optional[dict]:
    """Build the active sync incident for an account, if any."""
    now_value = to_utc_naive(now or datetime.utcnow())
    normalized = normalize_sync_failure_conditions(conditions)
    thresholds = _effective_sync_thresholds(account.id, normalized)
    stale_window = timedelta(hours=thresholds["stale_after_hours"], minutes=thresholds["grace_period_minutes"])
    stuck_window = timedelta(minutes=thresholds["stuck_after_minutes"])

    last_success = to_utc_naive(
        getattr(account, "last_sync_succeeded_at", None) or getattr(account, "last_sync_at", None)
    )
    last_attempt = to_utc_naive(getattr(account, "last_sync_attempt_at", None))
    last_started = to_utc_naive(getattr(account, "last_sync_started_at", None))
    last_heartbeat = to_utc_naive(getattr(account, "last_sync_heartbeat_at", None)) or last_started or last_attempt
    last_failure = to_utc_naive(getattr(account, "last_sync_failed_at", None))
    created_at = to_utc_naive(getattr(account, "created_at", None))
    sync_status = _enum_value(getattr(account, "sync_status", None))
    error_message = getattr(account, "sync_error_message", None)
    error_kind = getattr(account, "sync_error_kind", None)
    error_code = getattr(account, "sync_error_code", None)
    retrying = sync_status == "syncing" and error_kind == "transient"

    if sync_status == "error":
        recommended_action = (
            "Reconnect the account credentials and re-run sync."
            if error_kind == "terminal"
            else "Review the worker logs and trigger a manual sync."
        )
        details = {
            "incident_type": "sync_failed",
            "account_name": account.account_name,
            "incident_label": SYNC_INCIDENT_LABELS["sync_failed"],
            "status": sync_status,
            "retrying": False,
            "error_kind": error_kind,
            "error_code": error_code,
            "last_success_at": isoformat_utc(last_success),
            "last_attempt_at": isoformat_utc(last_attempt),
            "last_failure_at": isoformat_utc(last_failure),
            "last_heartbeat_at": isoformat_utc(last_heartbeat),
            "recommended_action": recommended_action,
        }
        message = (
            f"Sync failed for {account.account_name}: {error_message or 'Unknown error'}. "
            f"Recommended action: {recommended_action}"
        )
        return {"incident_type": "sync_failed", "severity": "critical", "message": message, "details": details}

    if sync_status == "syncing" and last_heartbeat and now_value - last_heartbeat > stuck_window:
        delay = now_value - last_heartbeat
        recommended_action = "Inspect the worker/queue, then retry the sync if no worker is processing it."
        details = {
            "incident_type": "sync_stuck",
            "account_name": account.account_name,
            "incident_label": SYNC_INCIDENT_LABELS["sync_stuck"],
            "status": sync_status,
            "retrying": retrying,
            "stuck_for_minutes": int(delay.total_seconds() // 60),
            "last_success_at": isoformat_utc(last_success),
            "last_attempt_at": isoformat_utc(last_attempt),
            "last_heartbeat_at": isoformat_utc(last_heartbeat),
            "recommended_action": recommended_action,
        }
        message = (
            f"Sync appears stuck for {account.account_name}: no heartbeat for {format_duration(delay)}. "
            f"Recommended action: {recommended_action}"
        )
        return {"incident_type": "sync_stuck", "severity": "critical", "message": message, "details": details}

    if last_success is None:
        reference = last_attempt or created_at
        if reference and now_value - reference > stale_window and sync_status != "syncing":
            age = now_value - reference
            recommended_action = "Run an initial sync and verify credentials if it fails again."
            details = {
                "incident_type": "sync_never_succeeded",
                "account_name": account.account_name,
                "incident_label": SYNC_INCIDENT_LABELS["sync_never_succeeded"],
                "status": sync_status or "pending",
                "retrying": retrying,
                "age_minutes": int(age.total_seconds() // 60),
                "last_attempt_at": isoformat_utc(last_attempt),
                "created_at": isoformat_utc(created_at),
                "recommended_action": recommended_action,
            }
            message = (
                f"Sync has never completed for {account.account_name} after {format_duration(age)}. "
                f"Recommended action: {recommended_action}"
            )
            return {
                "incident_type": "sync_never_succeeded",
                "severity": "warning",
                "message": message,
                "details": details,
            }
        return None

    if now_value - last_success > stale_window:
        delay = now_value - last_success
        recommended_action = (
            "Monitor the active retry if progress continues."
            if retrying
            else "Review credentials/worker health and trigger a manual sync."
        )
        details = {
            "incident_type": "sync_delayed",
            "account_name": account.account_name,
            "incident_label": SYNC_INCIDENT_LABELS["sync_delayed"],
            "status": sync_status or "pending",
            "retrying": retrying,
            "delay_hours": round(delay.total_seconds() / 3600, 1),
            "last_success_at": isoformat_utc(last_success),
            "last_attempt_at": isoformat_utc(last_attempt),
            "last_failure_at": isoformat_utc(last_failure),
            "last_heartbeat_at": isoformat_utc(last_heartbeat),
            "expected_by": isoformat_utc(last_success + stale_window),
            "recommended_action": recommended_action,
        }
        message = (
            f"Sync delayed for {account.account_name}: last successful sync was {format_duration(delay)} ago. "
            f"Recommended action: {recommended_action}"
        )
        return {"incident_type": "sync_delayed", "severity": "warning", "message": message, "details": details}

    return None
