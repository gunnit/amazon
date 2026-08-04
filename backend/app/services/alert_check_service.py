"""In-process alert-rule evaluation, delivery, and daily digest.

Ported from ``workers/tasks/notifications.py`` so deployments without
Celery/Redis (prod runs APScheduler inside the API process) still evaluate
configurable alert rules — low_stock, price_change, bsr_drop, sync_failure —
and send the daily digest. The Celery tasks delegate here so there is a
single implementation.

Uses a private engine + event loop per run, like the other ``run_*``
entrypoints, because APScheduler executes jobs in worker threads and the
shared asyncpg pool is bound to the API event loop.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.core.sync_health import build_sync_incident, normalize_sync_failure_conditions

logger = logging.getLogger(__name__)

MAX_ALERTS_PER_BATCH = 25
DELIVERY_RETRY_AFTER = timedelta(minutes=15)


def _build_dedup_key(event_kind: str, account_id=None, asin: Optional[str] = None) -> str:
    return f"{event_kind}:{account_id or '-'}:{asin or '-'}"


async def _rule_account_ids(db, rule) -> List[UUID]:
    """Account ids a rule may evaluate: its own org's, never another tenant's."""
    from app.models.amazon_account import AmazonAccount

    result = await db.execute(
        select(AmazonAccount.id).where(
            AmazonAccount.organization_id == rule.organization_id
        )
    )
    org_account_ids = set(result.scalars().all())
    if rule.applies_to_accounts:
        org_account_ids &= {UUID(str(a)) for a in rule.applies_to_accounts}
    return list(org_account_ids)


def _serialize_detail(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "hex") and hasattr(value, "version"):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _serialize_detail(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_detail(item) for item in value]
    return value


def _chunked(items: List[Any], size: int) -> Iterable[List[Any]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]


def _has_delivery_target(rule) -> bool:
    channels = set(rule.notification_channels or [])
    if "email" in channels and rule.notification_emails:
        return True
    if "webhook" in channels and rule.webhook_url:
        return True
    return False


def _build_batch_payload(rule, alerts) -> tuple[str, Dict[str, Any]]:
    if len(alerts) == 1:
        alert = alerts[0]
        details = dict(alert.details or {})
        details.update(
            {
                "alert_id": str(alert.id),
                "severity": alert.severity,
                "account_id": str(alert.account_id) if alert.account_id else None,
                "asin": alert.asin,
            }
        )
        return alert.message, details

    severity_counts: Dict[str, int] = defaultdict(int)
    for alert in alerts:
        severity_counts[alert.severity] += 1

    return (
        f"{len(alerts)} avvisi attivati per la regola '{rule.name}'",
        {
            "count": len(alerts),
            "rule_name": rule.name,
            "severity_counts": dict(severity_counts),
            "alerts": [
                {
                    "alert_id": str(alert.id),
                    "message": alert.message,
                    "severity": alert.severity,
                    "account_id": str(alert.account_id) if alert.account_id else None,
                    "asin": alert.asin,
                }
                for alert in alerts[:10]
            ],
        },
    )


def _bsr_baseline(history_rows, min_history_points: int):
    by_day: Dict[Any, int] = {}
    for row in history_rows:
        if row.bsr is None or row.bsr <= 0:
            continue
        current = by_day.get(row.date)
        if current is None or row.bsr < current:
            by_day[row.date] = row.bsr

    ordered = sorted(by_day.items(), key=lambda item: item[0], reverse=True)
    if len(ordered) < min_history_points:
        return None

    baseline_values = [bsr for _, bsr in ordered[1:]]
    if not baseline_values:
        return None

    return ordered[0][1], float(median(baseline_values))


async def _create_alert(
    db,
    rule,
    event_kind,
    message,
    severity="warning",
    account_id=None,
    asin=None,
    details=None,
):
    """Create or refresh an unresolved alert for the same incident."""
    from app.models.alert import Alert

    now = datetime.utcnow()
    dedup_key = _build_dedup_key(event_kind, account_id=account_id, asin=asin)
    existing = (
        await db.execute(
            select(Alert).where(
                Alert.rule_id == rule.id,
                Alert.dedup_key == dedup_key,
                Alert.resolved_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.message = message
        existing.details = _serialize_detail(details or {})
        existing.severity = severity
        existing.last_seen_at = now
        return existing, False

    alert = Alert(
        rule_id=rule.id,
        account_id=account_id,
        asin=asin,
        event_kind=event_kind,
        dedup_key=dedup_key,
        message=message,
        details=_serialize_detail(details or {}),
        severity=severity,
        is_read=False,
        last_seen_at=now,
        notification_status="pending",
    )
    db.add(alert)
    rule.last_triggered_at = now
    return alert, True


async def _resolve_missing_alerts(db, rule, event_kinds, hold_keys):
    """Resolve stale alerts whose incident is no longer active."""
    from app.models.alert import Alert

    result = await db.execute(
        select(Alert).where(
            Alert.rule_id == rule.id,
            Alert.resolved_at.is_(None),
            Alert.event_kind.in_(event_kinds),
        )
    )
    resolved = 0
    now = datetime.utcnow()
    for alert in result.scalars().all():
        if alert.dedup_key in hold_keys:
            continue
        alert.resolved_at = now
        alert.last_seen_at = now
        resolved += 1
    return resolved


async def _evaluate_low_stock(db, rule):
    from app.models.amazon_account import AmazonAccount
    from app.models.inventory import InventoryData

    threshold = int(rule.conditions.get("threshold", 10))
    recovery_buffer = max(int(rule.conditions.get("recovery_buffer", 2)), 0)

    account_ids = await _rule_account_ids(db, rule)
    if not account_ids:
        return 0

    latest_date_q = select(func.max(InventoryData.snapshot_date)).where(
        InventoryData.account_id.in_(account_ids)
    )
    result = await db.execute(latest_date_q)
    latest_date = result.scalar_one_or_none()
    if not latest_date:
        return 0

    query = select(InventoryData, AmazonAccount.account_name).join(
        AmazonAccount, AmazonAccount.id == InventoryData.account_id
    ).where(
        InventoryData.snapshot_date == latest_date,
        InventoryData.account_id.in_(account_ids),
    )
    if rule.applies_to_asins:
        query = query.where(InventoryData.asin.in_(rule.applies_to_asins))

    result = await db.execute(query)
    items = result.all()

    created_count = 0
    hold_keys = set()
    for item, account_name in items:
        quantity = int(item.afn_fulfillable_quantity or 0)
        dedup_key = _build_dedup_key("low_stock", account_id=item.account_id, asin=item.asin)
        if quantity < threshold + recovery_buffer:
            hold_keys.add(dedup_key)
        if quantity >= threshold:
            continue

        severity = "critical" if quantity == 0 else "warning"
        _, was_created = await _create_alert(
            db,
            rule,
            event_kind="low_stock",
            message=(
                f"Scorte in esaurimento: {item.asin} ha {quantity} unità in {account_name} "
                f"(soglia: {threshold})"
            ),
            severity=severity,
            account_id=item.account_id,
            asin=item.asin,
            details={
                "account_name": account_name,
                "threshold": threshold,
                "recovery_buffer": recovery_buffer,
                "units": quantity,
                "snapshot_date": latest_date,
                "recommended_action": "Rifornisci o verifica le spedizioni in entrata prima che il prodotto vada esaurito.",
            },
        )
        if was_created:
            created_count += 1

    await _resolve_missing_alerts(db, rule, ["low_stock"], hold_keys)
    return created_count


async def _evaluate_sync_failure(db, rule):
    from app.models.alert import Alert
    from app.models.amazon_account import AmazonAccount

    conditions = normalize_sync_failure_conditions(rule.conditions)

    account_ids = await _rule_account_ids(db, rule)
    if not account_ids:
        return 0

    query = select(AmazonAccount).where(
        AmazonAccount.is_active == True,  # noqa: E712
        AmazonAccount.id.in_(account_ids),
    )

    result = await db.execute(query)
    accounts = result.scalars().all()
    account_ids = {account.id for account in accounts}
    now = datetime.utcnow()

    open_result = await db.execute(
        select(Alert).where(
            Alert.rule_id == rule.id,
            Alert.resolved_at.is_(None),
        )
    )
    open_alerts = open_result.scalars().all()
    open_by_account = {}
    for alert in open_alerts:
        incident_type = alert.event_kind or (alert.details or {}).get("incident_type", "sync_issue")
        open_by_account.setdefault(alert.account_id, {})[incident_type] = alert

    created_count = 0
    for account in accounts:
        incident = build_sync_incident(account, conditions=conditions, now=now)
        existing_alerts = open_by_account.get(account.id, {})

        if incident is None:
            for open_alert in existing_alerts.values():
                open_alert.resolved_at = now
                open_alert.last_seen_at = now
            continue

        incident_type = incident["incident_type"]
        for other_type, open_alert in existing_alerts.items():
            if other_type != incident_type:
                open_alert.resolved_at = now
                open_alert.last_seen_at = now

        current_alert = existing_alerts.get(incident_type)
        if current_alert:
            current_alert.message = incident["message"]
            current_alert.details = _serialize_detail(incident["details"])
            current_alert.severity = incident["severity"]
            current_alert.last_seen_at = now
            continue

        alert = Alert(
            rule_id=rule.id,
            account_id=account.id,
            asin=None,
            event_kind=incident_type,
            dedup_key=_build_dedup_key(incident_type, account_id=account.id),
            message=incident["message"],
            details=_serialize_detail(incident["details"]),
            severity=incident["severity"],
            is_read=False,
            last_seen_at=now,
            notification_status="pending",
        )
        db.add(alert)
        rule.last_triggered_at = now
        created_count += 1

    for account_id, incidents in open_by_account.items():
        if account_id not in account_ids:
            for open_alert in incidents.values():
                open_alert.resolved_at = now
                open_alert.last_seen_at = now

    return created_count


async def _evaluate_price_change(db, rule):
    from app.models.amazon_account import AmazonAccount
    from app.models.product import Product

    min_price = rule.conditions.get("min_price")
    max_price = rule.conditions.get("max_price")
    if min_price is None and max_price is None:
        return 0

    account_ids = await _rule_account_ids(db, rule)
    if not account_ids:
        return 0

    query = select(Product, AmazonAccount.account_name).join(
        AmazonAccount, AmazonAccount.id == Product.account_id
    ).where(
        Product.is_active == True,  # noqa: E712
        Product.current_price.isnot(None),
        Product.account_id.in_(account_ids),
    )
    if rule.applies_to_asins:
        query = query.where(Product.asin.in_(rule.applies_to_asins))

    filters = []
    if min_price is not None:
        filters.append(Product.current_price < min_price)
    if max_price is not None:
        filters.append(Product.current_price > max_price)

    query = query.where(or_(*filters)) if len(filters) == 2 else query.where(filters[0])

    result = await db.execute(query)
    products = result.all()

    count = 0
    hold_keys = set()
    for product, account_name in products:
        current_price = float(product.current_price)
        if min_price is not None and current_price < float(min_price):
            event_kind = "price_below_min"
            message = (
                f"Prezzo sotto il minimo: {product.asin} è ora a {current_price:.2f} "
                f"in {account_name} (min: {float(min_price):.2f})"
            )
        elif max_price is not None and current_price > float(max_price):
            event_kind = "price_above_max"
            message = (
                f"Prezzo sopra il massimo: {product.asin} è ora a {current_price:.2f} "
                f"in {account_name} (max: {float(max_price):.2f})"
            )
        else:
            continue

        hold_keys.add(_build_dedup_key(event_kind, account_id=product.account_id, asin=product.asin))
        _, was_created = await _create_alert(
            db,
            rule,
            event_kind=event_kind,
            message=message,
            severity="warning",
            account_id=product.account_id,
            asin=product.asin,
            details={
                "account_name": account_name,
                "current_price": current_price,
                "min_price": min_price,
                "max_price": max_price,
                "recommended_action": "Controlla le regole di repricing o le modifiche recenti alla scheda prodotto.",
            },
        )
        if was_created:
            count += 1
    await _resolve_missing_alerts(db, rule, ["price_below_min", "price_above_max"], hold_keys)
    return count


async def _evaluate_bsr_drop(db, rule):
    from app.models.amazon_account import AmazonAccount
    from app.models.product import BSRHistory, Product

    drop_percent = float(rule.conditions.get("drop_percent", 20))
    lookback_days = max(int(rule.conditions.get("lookback_days", 7)), 3)
    min_history_points = max(int(rule.conditions.get("min_history_points", 4)), 3)

    account_ids = await _rule_account_ids(db, rule)
    if not account_ids:
        return 0

    query = select(Product, AmazonAccount.account_name).join(
        AmazonAccount, AmazonAccount.id == Product.account_id
    ).where(
        Product.is_active == True,  # noqa: E712
        Product.current_bsr.isnot(None),
        Product.account_id.in_(account_ids),
    )
    if rule.applies_to_asins:
        query = query.where(Product.asin.in_(rule.applies_to_asins))

    result = await db.execute(query)
    products = result.all()

    count = 0
    hold_keys = set()
    for product, account_name in products:
        bsr_query = (
            select(BSRHistory)
            .where(BSRHistory.product_id == product.id)
            .order_by(BSRHistory.date.desc())
            .limit(lookback_days)
        )
        bsr_result = await db.execute(bsr_query)
        baseline = _bsr_baseline(bsr_result.scalars().all(), min_history_points=min_history_points)
        if baseline is None:
            continue

        latest_bsr, baseline_bsr = baseline
        if baseline_bsr <= 0:
            continue

        change_pct = ((latest_bsr - baseline_bsr) / baseline_bsr) * 100
        if change_pct > drop_percent:
            hold_keys.add(_build_dedup_key("bsr_drop", account_id=product.account_id, asin=product.asin))
            _, was_created = await _create_alert(
                db,
                rule,
                event_kind="bsr_drop",
                message=(
                    f"BSR peggiorato per {product.asin} in {account_name}: "
                    f"#{latest_bsr} contro baseline #{baseline_bsr:.0f} ({change_pct:.0f}% peggiore)"
                ),
                severity="warning",
                account_id=product.account_id,
                asin=product.asin,
                details={
                    "account_name": account_name,
                    "baseline_bsr": baseline_bsr,
                    "latest_bsr": latest_bsr,
                    "change_pct": round(change_pct, 1),
                    "threshold_pct": drop_percent,
                    "lookback_days": lookback_days,
                    "recommended_action": "Verifica ranking, prezzo e attività pubblicitaria per capire se il calo è persistente.",
                },
            )
            if was_created:
                count += 1
    await _resolve_missing_alerts(db, rule, ["bsr_drop"], hold_keys)
    return count


EVALUATORS = {
    "low_stock": _evaluate_low_stock,
    "sync_failure": _evaluate_sync_failure,
    "price_change": _evaluate_price_change,
    "bsr_drop": _evaluate_bsr_drop,
}


async def _deliver_pending_alerts(db) -> int:
    """Deliver unsent alerts through their rule's channels, inline.

    Replaces the Celery ``send_alert`` fan-out: without a broker the delivery
    happens in the same run, so statuses go straight to sent/failed/skipped.
    """
    from app.models.alert import Alert, AlertRule
    from app.services.notification_service import NotificationService

    retry_cutoff = datetime.utcnow() - DELIVERY_RETRY_AFTER
    pending_result = await db.execute(
        select(Alert, AlertRule)
        .join(AlertRule, Alert.rule_id == AlertRule.id)
        .where(
            Alert.resolved_at.is_(None),
            or_(
                Alert.notification_status.in_(["pending", "failed"]),
                and_(
                    Alert.notification_status == "queued",
                    Alert.last_notification_attempt_at.is_not(None),
                    Alert.last_notification_attempt_at < retry_cutoff,
                ),
            ),
        )
        .order_by(Alert.triggered_at.asc())
    )
    grouped = defaultdict(list)
    for alert, rule in pending_result.all():
        account_key = str(alert.account_id) if alert.account_id else "_global"
        grouped[(str(rule.id), account_key)].append((alert, rule))

    delivered = 0
    now = datetime.utcnow()
    service = NotificationService(sendgrid_api_key=settings.SENDGRID_API_KEY)
    for group_rows in grouped.values():
        alerts = [row[0] for row in group_rows]
        rule = group_rows[0][1]
        if not _has_delivery_target(rule):
            for alert in alerts:
                alert.notification_status = "skipped"
                alert.notification_error = "No valid delivery target configured"
                alert.last_notification_attempt_at = now
            continue

        for batch in _chunked(alerts, MAX_ALERTS_PER_BATCH):
            message, details = _build_batch_payload(rule, batch)
            try:
                results = await service.send_alert(
                    rule.alert_type,
                    message,
                    _serialize_detail(details),
                    rule.notification_channels or [],
                    rule.notification_emails,
                    rule.webhook_url,
                    from_email=settings.SENDGRID_FROM_EMAIL,
                )
                sent = any(results.values())
                failure_reason = service.last_error or "All configured channels failed"
            except Exception as exc:  # noqa: BLE001
                sent = False
                failure_reason = str(exc)

            for alert in batch:
                alert.last_notification_attempt_at = now
                if sent:
                    alert.notification_status = "sent"
                    alert.notification_sent_at = now
                    alert.notification_error = None
                else:
                    alert.notification_status = "failed"
                    alert.notification_error = failure_reason
            if sent:
                delivered += len(batch)

    return delivered


async def check_alerts_once(SessionLocal) -> dict:
    """Evaluate every enabled alert rule, then deliver pending alerts."""
    from app.models.alert import AlertRule

    async with SessionLocal() as db:
        result = await db.execute(
            select(AlertRule).where(AlertRule.is_enabled == True)  # noqa: E712
        )
        rules = result.scalars().all()

        triggered = 0
        for rule in rules:
            evaluator = EVALUATORS.get(rule.alert_type)
            if evaluator is None:
                # Readiness/trend rules are triggered by their own pipelines.
                continue
            try:
                triggered += await evaluator(db, rule)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to check alert rule %s: %s", rule.id, exc)

        await db.commit()

        delivered = await _deliver_pending_alerts(db)
        await db.commit()

    logger.info(
        "Alert check complete: %s rules, %s triggered, %s delivered",
        len(rules), triggered, delivered,
    )
    return {"checked": len(rules), "triggered": triggered, "delivered": delivered}


async def send_daily_digests_once(SessionLocal) -> dict:
    """Send yesterday's KPI digest to every opted-in active user."""
    from app.models.alert import Alert, AlertRule
    from app.models.amazon_account import AmazonAccount
    from app.models.user import Organization, OrganizationMember, User
    from app.services.analytics_service import AnalyticsService
    from app.services.notification_service import NotificationService

    async with SessionLocal() as db:
        result = await db.execute(
            select(User, Organization)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .join(Organization, Organization.id == OrganizationMember.organization_id)
            .where(User.is_active == True)  # noqa: E712
        )
        users = result.all()

        notification_service = NotificationService(sendgrid_api_key=settings.SENDGRID_API_KEY)
        analytics_service = AnalyticsService(db)

        sent_count = 0
        for user, org in users:
            prefs = (org.settings or {}).get(f"notification_prefs_{user.id}") or {}
            if not prefs.get("daily_digest", True):
                continue
            try:
                account_ids = list(
                    (
                        await db.execute(
                            select(AmazonAccount.id).where(
                                AmazonAccount.organization_id == org.id,
                                AmazonAccount.is_active == True,  # noqa: E712
                            )
                        )
                    ).scalars().all()
                )
                if not account_ids:
                    continue

                yesterday = date.today() - timedelta(days=1)
                kpis = await analytics_service.compute_dashboard_kpis(
                    account_ids=account_ids,
                    start_date=yesterday,
                    end_date=yesterday,
                )
                digest_kpis = dict(kpis.get("current") or {})
                changes = kpis.get("changes") or {}
                digest_kpis["revenue_change"] = changes.get("revenue", 0) or 0
                digest_kpis["units_change"] = changes.get("units", 0) or 0

                alerts_rows = await db.execute(
                    select(Alert)
                    .join(AlertRule, Alert.rule_id == AlertRule.id)
                    .where(
                        AlertRule.organization_id == org.id,
                        Alert.triggered_at >= datetime.utcnow() - timedelta(hours=24),
                    )
                    .order_by(Alert.triggered_at.desc())
                    .limit(5)
                )
                recent_alerts = [
                    {"message": alert.message} for alert in alerts_rows.scalars().all()
                ]

                sent = await notification_service.send_daily_digest(
                    to_email=user.email,
                    kpis=digest_kpis,
                    alerts=recent_alerts,
                    from_email=settings.SENDGRID_FROM_EMAIL,
                )
                if sent:
                    sent_count += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to send digest to %s: %s", user.email, exc)

        return {"sent": sent_count, "total_users": len(users)}


def _run_with_private_engine(job_name: str, coro_fn):
    """Run an async job on a private engine + fresh event loop."""
    from app.db.session import db_url as _db_url

    engine = create_async_engine(_db_url, echo=False, pool_size=2, max_overflow=1)
    SessionLocal = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro_fn(SessionLocal))
    except Exception:
        logger.exception("In-process %s failed", job_name)
        return None
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()


def run_alert_check():
    """In-process scheduler entrypoint mirroring Celery ``check_alerts``."""
    return _run_with_private_engine("alert check", check_alerts_once)


def run_daily_digest():
    """In-process scheduler entrypoint mirroring Celery ``send_daily_digests``."""
    if not settings.SENDGRID_API_KEY:
        # Short-circuit before any engine work: nothing can be delivered.
        logger.info("Daily digest skipped: SendGrid not configured")
        return {"skipped": True, "reason": "sendgrid_not_configured", "sent": 0}
    return _run_with_private_engine("daily digest", send_daily_digests_once)
