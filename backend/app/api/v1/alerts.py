"""Alert management endpoints."""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from pydantic import BaseModel

from app.api.deps import CurrentUser, CurrentOrganization, DbSession
from app.models.alert import AlertRule

router = APIRouter()


class AlertRuleCreate(BaseModel):
    name: str
    alert_type: str  # low_stock, bsr_drop, price_change, sync_failure
    conditions: dict
    applies_to_accounts: Optional[List[UUID]] = None
    applies_to_asins: Optional[List[str]] = None
    notification_channels: List[str] = ["email"]
    notification_emails: Optional[List[str]] = None
    webhook_url: Optional[str] = None


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    conditions: Optional[dict] = None
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
    alert_type: str
    conditions: dict
    applies_to_accounts: Optional[List[UUID]]
    applies_to_asins: Optional[List[str]]
    notification_channels: Optional[List[str]]
    notification_emails: Optional[List[str]]
    webhook_url: Optional[str]
    is_enabled: bool

    class Config:
        from_attributes = True


@router.get("/rules", response_model=List[AlertRuleResponse])
async def list_alert_rules(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """List all alert rules."""
    result = await db.execute(
        select(AlertRule)
        .where(AlertRule.organization_id == organization.id)
        .order_by(AlertRule.created_at.desc())
    )
    return result.scalars().all()


@router.post("/rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    rule_in: AlertRuleCreate,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Create a new alert rule."""
    rule = AlertRule(
        organization_id=organization.id,
        name=rule_in.name,
        alert_type=rule_in.alert_type,
        conditions=rule_in.conditions,
        applies_to_accounts=rule_in.applies_to_accounts,
        applies_to_asins=rule_in.applies_to_asins,
        notification_channels=rule_in.notification_channels,
        notification_emails=rule_in.notification_emails,
        webhook_url=rule_in.webhook_url,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)

    return rule


@router.get("/rules/{rule_id}", response_model=AlertRuleResponse)
async def get_alert_rule(
    rule_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get alert rule details."""
    result = await db.execute(
        select(AlertRule)
        .where(
            AlertRule.id == rule_id,
            AlertRule.organization_id == organization.id,
        )
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert rule not found"
        )

    return rule


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
        select(AlertRule)
        .where(
            AlertRule.id == rule_id,
            AlertRule.organization_id == organization.id,
        )
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert rule not found"
        )

    if rule_in.name is not None:
        rule.name = rule_in.name
    if rule_in.conditions is not None:
        rule.conditions = rule_in.conditions
    if rule_in.applies_to_accounts is not None:
        rule.applies_to_accounts = rule_in.applies_to_accounts
    if rule_in.applies_to_asins is not None:
        rule.applies_to_asins = rule_in.applies_to_asins
    if rule_in.notification_channels is not None:
        rule.notification_channels = rule_in.notification_channels
    if rule_in.notification_emails is not None:
        rule.notification_emails = rule_in.notification_emails
    if rule_in.webhook_url is not None:
        rule.webhook_url = rule_in.webhook_url
    if rule_in.is_enabled is not None:
        rule.is_enabled = rule_in.is_enabled

    await db.flush()
    await db.refresh(rule)

    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Delete an alert rule."""
    result = await db.execute(
        select(AlertRule)
        .where(
            AlertRule.id == rule_id,
            AlertRule.organization_id == organization.id,
        )
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert rule not found"
        )

    await db.delete(rule)


@router.get("/history")
async def get_alert_history(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    limit: int = 50,
):
    """Get alert history."""
    # This would query an alert_history table in production
    return []
