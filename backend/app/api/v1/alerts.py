"""Alert management endpoints."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from app.api.deps import CurrentOrganization, CurrentUser, DbSession
from app.models.alert import Alert, AlertRule

router = APIRouter()
ALLOWED_CHANNELS = {"email", "webhook"}


class AlertType(str, Enum):
    low_stock = "low_stock"
    bsr_drop = "bsr_drop"
    price_change = "price_change"
    sync_failure = "sync_failure"
    product_trend = "product_trend"


class AlertSeverity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AlertStatus(str, Enum):
    unread = "unread"
    read = "read"
    all = "all"


class AlertBulkScope(str, Enum):
    all = "all"


class AlertRuleCreate(BaseModel):
    name: str
    alert_type: AlertType
    conditions: dict[str, Any]
    applies_to_accounts: Optional[List[UUID]] = None
    applies_to_asins: Optional[List[str]] = None
    notification_channels: List[str] = Field(default_factory=lambda: ["email"])
    notification_emails: Optional[List[str]] = None
    webhook_url: Optional[str] = None


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    conditions: Optional[dict[str, Any]] = None
    applies_to_accounts: Optional[List[UUID]] = None
    applies_to_asins: Optional[List[str]] = None
    notification_channels: Optional[List[str]] = None
    notification_emails: Optional[List[str]] = None
    webhook_url: Optional[str] = None
    is_enabled: Optional[bool] = None


class AlertRuleResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    alert_type: AlertType
    conditions: dict[str, Any]
    applies_to_accounts: Optional[List[UUID]]
    applies_to_asins: Optional[List[str]]
    notification_channels: Optional[List[str]]
    notification_emails: Optional[List[str]]
    webhook_url: Optional[str]
    is_enabled: bool
    last_triggered_at: Optional[datetime] = None
    alert_count: int = 0

    class Config:
        from_attributes = True


class AlertSummaryResponse(BaseModel):
    unread_count: int
    critical_count: int
    active_rule_count: int
    total_rule_count: int


class AlertResponse(BaseModel):
    id: UUID
    rule_id: UUID
    account_id: Optional[UUID] = None
    asin: Optional[str] = None
    event_kind: str
    dedup_key: str
    message: str
    details: Dict[str, Any]
    severity: AlertSeverity
    is_read: bool
    triggered_at: datetime
    last_seen_at: datetime
    resolved_at: Optional[datetime] = None
    notification_status: str
    last_notification_attempt_at: Optional[datetime] = None
    notification_sent_at: Optional[datetime] = None
    notification_error: Optional[str] = None
    rule_name: Optional[str] = None
    alert_type: Optional[AlertType] = None

    class Config:
        from_attributes = True


class AlertListResponse(BaseModel):
    items: List[AlertResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


class AlertUnreadCountResponse(BaseModel):
    count: int


class AlertUpdateRequest(BaseModel):
    read: bool = True


class AlertBulkUpdateRequest(BaseModel):
    read: bool = True
    scope: AlertBulkScope = AlertBulkScope.all


class AlertMutationResponse(BaseModel):
    item: AlertResponse
    unread_count: int


class AlertBulkMutationResponse(BaseModel):
    updated: int
    unread_count: int


def _as_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be a number",
        ) from exc


def _validate_rule_payload(
    *,
    alert_type: AlertType,
    conditions: dict[str, Any],
    notification_channels: Optional[List[str]],
) -> dict[str, Any]:
    channels = notification_channels or []
    invalid_channels = [channel for channel in channels if channel not in ALLOWED_CHANNELS]
    if invalid_channels:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported notification channels: {', '.join(invalid_channels)}",
        )

    normalized = dict(conditions or {})
    if alert_type == AlertType.low_stock:
        threshold = int(_as_float(normalized.get("threshold", 10), "threshold"))
        recovery_buffer = int(_as_float(normalized.get("recovery_buffer", 2), "recovery_buffer"))
        if threshold < 0 or recovery_buffer < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="threshold and recovery_buffer must be >= 0",
            )
        return {"threshold": threshold, "recovery_buffer": recovery_buffer}

    if alert_type == AlertType.bsr_drop:
        drop_percent = _as_float(normalized.get("drop_percent", 20), "drop_percent")
        lookback_days = int(_as_float(normalized.get("lookback_days", 7), "lookback_days"))
        min_history_points = int(_as_float(normalized.get("min_history_points", 4), "min_history_points"))
        if drop_percent <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="drop_percent must be > 0",
            )
        if lookback_days < 3 or min_history_points < 3 or min_history_points > lookback_days:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="lookback_days must be >= 3 and min_history_points must be between 3 and lookback_days",
            )
        return {
            "drop_percent": drop_percent,
            "lookback_days": lookback_days,
            "min_history_points": min_history_points,
        }

    if alert_type == AlertType.price_change:
        min_price = normalized.get("min_price")
        max_price = normalized.get("max_price")
        if min_price is None and max_price is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="At least one of min_price or max_price is required",
            )

        validated: dict[str, Any] = {}
        if min_price is not None:
            validated["min_price"] = _as_float(min_price, "min_price")
            if validated["min_price"] < 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="min_price must be >= 0",
                )
        if max_price is not None:
            validated["max_price"] = _as_float(max_price, "max_price")
            if validated["max_price"] < 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="max_price must be >= 0",
                )
        if "min_price" in validated and "max_price" in validated and validated["min_price"] > validated["max_price"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="min_price must be <= max_price",
            )
        return validated

    if alert_type == AlertType.product_trend:
        trend_class = str(normalized.get("trend_class", "declining_fast"))
        if trend_class != "declining_fast":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="product_trend rules currently support only declining_fast",
            )
        cooldown_hours = int(_as_float(normalized.get("cooldown_hours", 12), "cooldown_hours"))
        if cooldown_hours <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="cooldown_hours must be > 0",
            )
        return {
            "trend_class": trend_class,
            "cooldown_hours": cooldown_hours,
            "auto_created": bool(normalized.get("auto_created", False)),
        }

    stale_after_hours = int(_as_float(
        normalized.get("stale_after_hours", normalized.get("stale_hours", 24)),
        "stale_after_hours",
    ))
    grace_period_minutes = int(_as_float(normalized.get("grace_period_minutes", 90), "grace_period_minutes"))
    stuck_after_minutes = int(_as_float(normalized.get("stuck_after_minutes", 120), "stuck_after_minutes"))
    if stale_after_hours <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="stale_after_hours must be > 0",
        )
    if grace_period_minutes < 0 or stuck_after_minutes <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="grace_period_minutes must be >= 0 and stuck_after_minutes must be > 0",
        )

    overrides = normalized.get("account_threshold_overrides") or {}
    validated_overrides: dict[str, dict[str, int]] = {}
    if overrides:
        if not isinstance(overrides, dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="account_threshold_overrides must be an object keyed by account id",
            )
        for account_id, override in overrides.items():
            if not isinstance(override, dict):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Override for account {account_id} must be an object",
                )
            override_stale = int(_as_float(
                override.get("stale_after_hours", stale_after_hours),
                f"account_threshold_overrides.{account_id}.stale_after_hours",
            ))
            override_grace = int(_as_float(
                override.get("grace_period_minutes", grace_period_minutes),
                f"account_threshold_overrides.{account_id}.grace_period_minutes",
            ))
            override_stuck = int(_as_float(
                override.get("stuck_after_minutes", stuck_after_minutes),
                f"account_threshold_overrides.{account_id}.stuck_after_minutes",
            ))
            if override_stale <= 0 or override_grace < 0 or override_stuck <= 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"Override for account {account_id} must use positive stale/stuck values "
                        "and a non-negative grace period"
                    ),
                )
            validated_overrides[str(account_id)] = {
                "stale_after_hours": override_stale,
                "grace_period_minutes": override_grace,
                "stuck_after_minutes": override_stuck,
            }

    return {
        "stale_after_hours": stale_after_hours,
        "grace_period_minutes": grace_period_minutes,
        "stuck_after_minutes": stuck_after_minutes,
        "account_threshold_overrides": validated_overrides,
    }


def serialize_rule(rule: AlertRule, alert_count: int = 0) -> AlertRuleResponse:
    return AlertRuleResponse(
        id=rule.id,
        organization_id=rule.organization_id,
        name=rule.name,
        alert_type=rule.alert_type,
        conditions=rule.conditions,
        applies_to_accounts=rule.applies_to_accounts,
        applies_to_asins=rule.applies_to_asins,
        notification_channels=rule.notification_channels,
        notification_emails=rule.notification_emails,
        webhook_url=rule.webhook_url,
        is_enabled=rule.is_enabled,
        last_triggered_at=rule.last_triggered_at,
        alert_count=alert_count,
    )


def _resolve_status_filter(
    status_value: Optional[AlertStatus],
    is_read: Optional[bool],
) -> Optional[AlertStatus]:
    if status_value is not None and is_read is not None:
        expected_status = AlertStatus.read if is_read else AlertStatus.unread
        if status_value != expected_status:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Use either 'status' or deprecated 'is_read', not conflicting values",
            )
        return status_value

    if status_value is not None:
        return status_value
    if is_read is None:
        return None
    return AlertStatus.read if is_read else AlertStatus.unread


def _resolve_alert_type_filter(
    type_value: Optional[AlertType],
    deprecated_alert_type: Optional[AlertType],
) -> Optional[AlertType]:
    if type_value is not None and deprecated_alert_type is not None and type_value != deprecated_alert_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Use either 'type' or deprecated 'alert_type', not conflicting values",
        )
    return type_value or deprecated_alert_type


def _build_alert_where_clauses(
    organization_id: UUID,
    *,
    severity: Optional[AlertSeverity],
    status_filter: Optional[AlertStatus],
    alert_type: Optional[AlertType],
    account_id: Optional[UUID],
    asin: Optional[str],
) -> list[Any]:
    read_state = func.coalesce(Alert.is_read, False)
    clauses: list[Any] = [AlertRule.organization_id == organization_id]

    if severity is not None:
        clauses.append(Alert.severity == severity.value)
    if status_filter == AlertStatus.unread:
        clauses.append(read_state.is_(False))
    elif status_filter == AlertStatus.read:
        clauses.append(read_state.is_(True))
    if alert_type is not None:
        clauses.append(AlertRule.alert_type == alert_type.value)
    if account_id is not None:
        clauses.append(Alert.account_id == account_id)
    if asin is not None:
        clauses.append(Alert.asin == asin)

    return clauses


def _alert_select():
    return (
        select(
            Alert,
            AlertRule.name.label("rule_name"),
            AlertRule.alert_type.label("rule_alert_type"),
        )
        .join(AlertRule, Alert.rule_id == AlertRule.id)
    )


def _row_to_alert_response(alert: Alert, rule_name: Optional[str], rule_alert_type: Optional[str]) -> AlertResponse:
    return AlertResponse(
        id=alert.id,
        rule_id=alert.rule_id,
        account_id=alert.account_id,
        asin=alert.asin,
        event_kind=alert.event_kind,
        dedup_key=alert.dedup_key,
        message=alert.message,
        details=alert.details or {},
        severity=alert.severity,
        is_read=bool(alert.is_read),
        triggered_at=alert.triggered_at,
        last_seen_at=alert.last_seen_at,
        resolved_at=alert.resolved_at,
        notification_status=alert.notification_status,
        last_notification_attempt_at=alert.last_notification_attempt_at,
        notification_sent_at=alert.notification_sent_at,
        notification_error=alert.notification_error,
        rule_name=rule_name,
        alert_type=rule_alert_type,
    )


def _rows_to_alert_items(rows: Sequence[tuple[Alert, Optional[str], Optional[str]]]) -> list[AlertResponse]:
    return [_row_to_alert_response(alert, rule_name, rule_alert_type) for alert, rule_name, rule_alert_type in rows]


async def _get_alert_row(
    db: DbSession,
    organization_id: UUID,
    alert_id: UUID,
) -> Optional[tuple[Alert, Optional[str], Optional[str]]]:
    result = await db.execute(
        _alert_select().where(
            Alert.id == alert_id,
            AlertRule.organization_id == organization_id,
        )
    )
    return result.one_or_none()


async def _get_unread_count(db: DbSession, organization_id: UUID) -> int:
    result = await db.execute(
        select(func.count(Alert.id))
        .join(AlertRule, Alert.rule_id == AlertRule.id)
        .where(
            AlertRule.organization_id == organization_id,
            func.coalesce(Alert.is_read, False).is_(False),
        )
    )
    return result.scalar_one()


@router.get("/rules", response_model=List[AlertRuleResponse])
async def list_alert_rules(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """List all alert rules."""
    result = await db.execute(
        select(AlertRule, func.count(Alert.id).label("alert_count"))
        .outerjoin(Alert, Alert.rule_id == AlertRule.id)
        .where(AlertRule.organization_id == organization.id)
        .group_by(AlertRule.id)
        .order_by(AlertRule.created_at.desc())
    )
    return [serialize_rule(rule, alert_count=alert_count) for rule, alert_count in result.all()]


@router.post("/rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    rule_in: AlertRuleCreate,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Create a new alert rule."""
    conditions = _validate_rule_payload(
        alert_type=rule_in.alert_type,
        conditions=rule_in.conditions,
        notification_channels=rule_in.notification_channels,
    )
    rule = AlertRule(
        organization_id=organization.id,
        name=rule_in.name,
        alert_type=rule_in.alert_type,
        conditions=conditions,
        applies_to_accounts=rule_in.applies_to_accounts,
        applies_to_asins=rule_in.applies_to_asins,
        notification_channels=rule_in.notification_channels,
        notification_emails=rule_in.notification_emails,
        webhook_url=rule_in.webhook_url,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)

    return serialize_rule(rule)


@router.get("/rules/{rule_id}", response_model=AlertRuleResponse)
async def get_alert_rule(
    rule_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get alert rule details."""
    result = await db.execute(
        select(AlertRule).where(
            AlertRule.id == rule_id,
            AlertRule.organization_id == organization.id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")

    return serialize_rule(rule)


@router.put("/rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: UUID,
    rule_in: AlertRuleUpdate,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Update an alert rule."""
    result = await db.execute(
        select(AlertRule).where(
            AlertRule.id == rule_id,
            AlertRule.organization_id == organization.id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")

    next_conditions = rule.conditions
    next_channels = rule.notification_channels

    if rule_in.name is not None:
        rule.name = rule_in.name
    if rule_in.conditions is not None:
        next_conditions = rule_in.conditions
    if rule_in.applies_to_accounts is not None:
        rule.applies_to_accounts = rule_in.applies_to_accounts
    if rule_in.applies_to_asins is not None:
        rule.applies_to_asins = rule_in.applies_to_asins
    if rule_in.notification_channels is not None:
        next_channels = rule_in.notification_channels
    if rule_in.notification_emails is not None:
        rule.notification_emails = rule_in.notification_emails
    if rule_in.webhook_url is not None:
        rule.webhook_url = rule_in.webhook_url
    if rule_in.is_enabled is not None:
        rule.is_enabled = rule_in.is_enabled

    rule.conditions = _validate_rule_payload(
        alert_type=rule.alert_type,
        conditions=next_conditions,
        notification_channels=next_channels,
    )
    rule.notification_channels = next_channels

    await db.flush()
    await db.refresh(rule)
    return serialize_rule(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Delete an alert rule."""
    result = await db.execute(
        select(AlertRule).where(
            AlertRule.id == rule_id,
            AlertRule.organization_id == organization.id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")

    await db.delete(rule)


@router.get("/summary", response_model=AlertSummaryResponse)
async def get_alert_summary(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get headline counts for alerts and rules."""
    unread_result = await db.execute(
        select(func.count(Alert.id))
        .join(AlertRule, Alert.rule_id == AlertRule.id)
        .where(
            AlertRule.organization_id == organization.id,
            func.coalesce(Alert.is_read, False).is_(False),
        )
    )
    critical_result = await db.execute(
        select(func.count(Alert.id))
        .join(AlertRule, Alert.rule_id == AlertRule.id)
        .where(
            AlertRule.organization_id == organization.id,
            func.coalesce(Alert.is_read, False).is_(False),
            Alert.severity == AlertSeverity.critical.value,
        )
    )
    active_rules_result = await db.execute(
        select(func.count(AlertRule.id)).where(
            AlertRule.organization_id == organization.id,
            AlertRule.is_enabled.is_(True),
        )
    )
    total_rules_result = await db.execute(
        select(func.count(AlertRule.id)).where(AlertRule.organization_id == organization.id)
    )

    return AlertSummaryResponse(
        unread_count=unread_result.scalar_one(),
        critical_count=critical_result.scalar_one(),
        active_rule_count=active_rules_result.scalar_one(),
        total_rule_count=total_rules_result.scalar_one(),
    )


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    severity: Optional[AlertSeverity] = None,
    status_filter: Optional[AlertStatus] = Query(default=None, alias="status"),
    alert_type_filter: Optional[AlertType] = Query(default=None, alias="type"),
    account_id: Optional[UUID] = None,
    asin: Optional[str] = Query(default=None, min_length=1, max_length=20),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    is_read: Optional[bool] = Query(default=None, deprecated=True),
    alert_type: Optional[AlertType] = Query(default=None, deprecated=True),
):
    """List alerts with filtering and pagination."""
    resolved_status = _resolve_status_filter(status_filter, is_read)
    resolved_alert_type = _resolve_alert_type_filter(alert_type_filter, alert_type)
    where_clauses = _build_alert_where_clauses(
        organization.id,
        severity=severity,
        status_filter=resolved_status,
        alert_type=resolved_alert_type,
        account_id=account_id,
        asin=asin,
    )

    items_result = await db.execute(
        _alert_select()
        .where(*where_clauses)
        .order_by(Alert.triggered_at.desc(), Alert.id.desc())
        .offset(offset)
        .limit(limit)
    )
    count_result = await db.execute(
        select(func.count(Alert.id))
        .join(AlertRule, Alert.rule_id == AlertRule.id)
        .where(*where_clauses)
    )

    rows = items_result.all()
    total = count_result.scalar_one()

    return AlertListResponse(
        items=_rows_to_alert_items(rows),
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(rows) < total,
    )


@router.get("/history", response_model=AlertListResponse, deprecated=True)
async def get_alert_history(
    response: Response,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    severity: Optional[AlertSeverity] = None,
    status_filter: Optional[AlertStatus] = Query(default=None, alias="status"),
    alert_type_filter: Optional[AlertType] = Query(default=None, alias="type"),
    account_id: Optional[UUID] = None,
    asin: Optional[str] = Query(default=None, min_length=1, max_length=20),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    is_read: Optional[bool] = Query(default=None, deprecated=True),
    alert_type: Optional[AlertType] = Query(default=None, deprecated=True),
):
    """Deprecated alias for alert list."""
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/v1/alerts>; rel="successor-version"'
    return await list_alerts(
        current_user=current_user,
        organization=organization,
        db=db,
        severity=severity,
        status_filter=status_filter,
        alert_type_filter=alert_type_filter,
        account_id=account_id,
        asin=asin,
        limit=limit,
        offset=offset,
        is_read=is_read,
        alert_type=alert_type,
    )


@router.get("/unread-count", response_model=AlertUnreadCountResponse)
async def get_unread_count(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get count of unread alerts."""
    return AlertUnreadCountResponse(count=await _get_unread_count(db, organization.id))


@router.patch("", response_model=AlertBulkMutationResponse)
async def update_alerts(
    payload: AlertBulkUpdateRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Bulk update alerts for the organization."""
    if payload.scope != AlertBulkScope.all:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported bulk update scope",
        )

    rule_ids_q = select(AlertRule.id).where(AlertRule.organization_id == organization.id)
    result = await db.execute(
        update(Alert)
        .where(
            Alert.rule_id.in_(rule_ids_q),
            func.coalesce(Alert.is_read, False).is_not(payload.read),
        )
        .values(is_read=payload.read)
        .execution_options(synchronize_session=False)
    )

    return AlertBulkMutationResponse(
        updated=result.rowcount or 0,
        unread_count=await _get_unread_count(db, organization.id),
    )


@router.post("/mark-all-read", response_model=AlertBulkMutationResponse, deprecated=True)
async def mark_all_alerts_read(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Deprecated alias for marking all alerts as read."""
    return await update_alerts(
        payload=AlertBulkUpdateRequest(read=True, scope=AlertBulkScope.all),
        current_user=current_user,
        organization=organization,
        db=db,
    )


@router.patch("/{alert_id}", response_model=AlertMutationResponse)
async def update_alert(
    alert_id: UUID,
    payload: AlertUpdateRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Update a single alert."""
    update_result = await db.execute(
        update(Alert)
        .where(
            Alert.id == alert_id,
            Alert.rule_id.in_(
                select(AlertRule.id).where(AlertRule.organization_id == organization.id)
            ),
            func.coalesce(Alert.is_read, False).is_not(payload.read),
        )
        .values(is_read=payload.read)
        .returning(Alert.id)
        .execution_options(synchronize_session=False)
    )
    updated_alert_id = update_result.scalar_one_or_none()

    row = await _get_alert_row(db, organization.id, updated_alert_id or alert_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    alert, rule_name, rule_alert_type = row
    return AlertMutationResponse(
        item=_row_to_alert_response(alert, rule_name, rule_alert_type),
        unread_count=await _get_unread_count(db, organization.id),
    )


@router.patch("/{alert_id}/read", response_model=AlertMutationResponse, deprecated=True)
async def mark_alert_read(
    alert_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Deprecated alias for marking a single alert as read."""
    return await update_alert(
        alert_id=alert_id,
        payload=AlertUpdateRequest(read=True),
        current_user=current_user,
        organization=organization,
        db=db,
    )
