"""Notification Celery tasks."""
import asyncio
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

from sqlalchemy import and_, func, or_, select

from app.core.sync_health import build_sync_incident, normalize_sync_failure_conditions
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)
QUEUE_RETRY_AFTER = timedelta(minutes=15)
MAX_ALERTS_PER_BATCH = 25


def _build_dedup_key(event_kind: str, account_id=None, asin: Optional[str] = None) -> str:
    return f"{event_kind}:{account_id or '-'}:{asin or '-'}"


def _serialize_detail(value: Any) -> Any:
    if isinstance(value, datetime):
        return _isoformat(value)
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
        f"{len(alerts)} alerts triggered for rule '{rule.name}'",
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


def run_async(coro_factory):
    """Run async function in sync context.

    Accepts either a zero-arg callable returning a coroutine (preferred —
    invoked after a fresh engine is installed) or, for backwards compat,
    a coroutine object. Installs a fresh engine/session factory so
    asyncpg futures bind to this loop, and disposes the engine afterwards.
    """
    from app.db.session import reset_engine_for_worker

    reset_engine_for_worker()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        coro = coro_factory() if callable(coro_factory) else coro_factory
        return loop.run_until_complete(coro)
    finally:
        try:
            from app.db.session import engine
            loop.run_until_complete(engine.dispose())
        except Exception:
            pass
        loop.close()


@celery_app.task
def send_email(to_emails: list, subject: str, html_content: str):
    """Send email notification."""
    from app.config import settings
    from app.services.notification_service import NotificationService

    async def _send():
        service = NotificationService(sendgrid_api_key=settings.SENDGRID_API_KEY)
        return await service.send_email(to_emails, subject, html_content)

    try:
        result = run_async(_send)
        logger.info(f"Email sent to {to_emails}: {result}")
        return {"sent": result}
    except Exception:
        logger.exception(f"Failed to send email to {to_emails}")
        raise


@celery_app.task
def send_alert(alert_ids: list[str]):
    """Send a batch of alerts and persist delivery status."""
    from app.config import settings
    from app.models.alert import Alert, AlertRule
    from app.services.notification_service import NotificationService

    async def _send():
        from app.db import session as db_session
        async with db_session.AsyncSessionLocal() as db:
            parsed_ids = [UUID(alert_id) for alert_id in alert_ids]
            result = await db.execute(
                select(Alert)
                .where(Alert.id.in_(parsed_ids))
                .order_by(Alert.triggered_at.asc())
                .with_for_update()
            )
            alerts = result.scalars().all()
            if not alerts:
                return {"status": "missing", "count": 0}

            rule = await db.get(AlertRule, alerts[0].rule_id)
            if rule is None:
                return {"status": "missing_rule", "count": len(alerts)}

            sendable_alerts = [
                alert for alert in alerts
                if alert.resolved_at is None and alert.notification_status not in {"sent", "skipped"}
            ]
            now = datetime.utcnow()

            if not sendable_alerts or not _has_delivery_target(rule):
                for alert in alerts:
                    if alert.notification_status != "sent":
                        alert.notification_status = "skipped"
                        alert.last_notification_attempt_at = now
                        if not _has_delivery_target(rule):
                            alert.notification_error = "No valid delivery target configured"
                await db.commit()
                return {"status": "skipped", "count": len(alerts)}

            message, details = _build_batch_payload(rule, sendable_alerts)
            service = NotificationService(sendgrid_api_key=settings.SENDGRID_API_KEY)
            results = await service.send_alert(
                rule.alert_type,
                message,
                _serialize_detail(details),
                rule.notification_channels or [],
                rule.notification_emails,
                rule.webhook_url,
            )

            delivered = any(results.values())
            for alert in sendable_alerts:
                alert.last_notification_attempt_at = now
                if delivered:
                    alert.notification_status = "sent"
                    alert.notification_sent_at = now
                    alert.notification_error = None
                else:
                    alert.notification_status = "failed"
                    alert.notification_error = "All configured channels failed"

            await db.commit()
            return {
                "status": "sent" if delivered else "failed",
                "count": len(sendable_alerts),
                "channels": results,
            }

    try:
        result = run_async(_send)
        logger.info(f"Alert batch processed: {result}")
        return result
    except Exception:
        logger.exception("Failed to send alert batch")
        raise


@celery_app.task
def send_daily_digests():
    """Send daily digest emails to all users."""
    from app.config import settings
    from app.models.user import OrganizationMember, User
    from app.services.analytics_service import AnalyticsService
    from app.services.notification_service import NotificationService

    async def _send_digests():
        from app.db import session as db_session
        async with db_session.AsyncSessionLocal() as db:
            result = await db.execute(
                select(User, OrganizationMember.organization_id)
                .join(OrganizationMember)
                .where(User.is_active == True)
            )
            users = result.all()

            notification_service = NotificationService(sendgrid_api_key=settings.SENDGRID_API_KEY)
            analytics_service = AnalyticsService(db)

            sent_count = 0
            for user, org_id in users:
                try:
                    yesterday = date.today() - timedelta(days=1)
                    kpis = await analytics_service.compute_dashboard_kpis(
                        account_ids=[org_id],
                        start_date=yesterday,
                        end_date=yesterday,
                    )

                    await notification_service.send_daily_digest(
                        to_email=user.email,
                        kpis=kpis["current"],
                        alerts=[],
                    )
                    sent_count += 1
                except Exception as exc:
                    logger.warning(f"Failed to send digest to {user.email}: {exc}")

            return {"sent": sent_count, "total_users": len(users)}

    return run_async(_send_digests)


@celery_app.task
def check_alerts():
    """Check all alert rules and trigger notifications."""
    from app.models.alert import Alert, AlertRule
    from app.models.amazon_account import AmazonAccount
    from app.models.inventory import InventoryData
    from app.models.product import BSRHistory, Product

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
        """Evaluate low_stock alert rule."""
        threshold = int(rule.conditions.get("threshold", 10))
        recovery_buffer = max(int(rule.conditions.get("recovery_buffer", 2)), 0)

        latest_date_q = select(func.max(InventoryData.snapshot_date))
        if rule.applies_to_accounts:
            latest_date_q = latest_date_q.where(
                InventoryData.account_id.in_(rule.applies_to_accounts)
            )
        result = await db.execute(latest_date_q)
        latest_date = result.scalar_one_or_none()
        if not latest_date:
            return 0

        query = select(InventoryData, AmazonAccount.account_name).join(
            AmazonAccount, AmazonAccount.id == InventoryData.account_id
        ).where(
            InventoryData.snapshot_date == latest_date,
        )
        if rule.applies_to_accounts:
            query = query.where(InventoryData.account_id.in_(rule.applies_to_accounts))
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
                    f"Low stock: {item.asin} has {quantity} units in {account_name} "
                    f"(threshold: {threshold})"
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
                    "recommended_action": "Replenish or verify inbound inventory before the item goes out of stock.",
                },
            )
            if was_created:
                created_count += 1

        await _resolve_missing_alerts(db, rule, ["low_stock"], hold_keys)
        return created_count

    async def _evaluate_sync_failure(db, rule):
        """Evaluate sync_failure alerts with delayed, stuck, and failure incidents."""
        conditions = normalize_sync_failure_conditions(rule.conditions)

        query = select(AmazonAccount).where(AmazonAccount.is_active == True)
        if rule.applies_to_accounts:
            query = query.where(AmazonAccount.id.in_(rule.applies_to_accounts))

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
        """Evaluate price_change alert rule."""
        min_price = rule.conditions.get("min_price")
        max_price = rule.conditions.get("max_price")
        if min_price is None and max_price is None:
            return 0

        query = select(Product, AmazonAccount.account_name).join(
            AmazonAccount, AmazonAccount.id == Product.account_id
        ).where(
            Product.is_active == True,
            Product.current_price.isnot(None),
        )
        if rule.applies_to_accounts:
            query = query.where(Product.account_id.in_(rule.applies_to_accounts))
        if rule.applies_to_asins:
            query = query.where(Product.asin.in_(rule.applies_to_asins))

        filters = []
        if min_price is not None:
            filters.append(Product.current_price < min_price)
        if max_price is not None:
            filters.append(Product.current_price > max_price)

        if len(filters) == 2:
            from sqlalchemy import or_
            query = query.where(or_(*filters))
        else:
            query = query.where(filters[0])

        result = await db.execute(query)
        products = result.all()

        count = 0
        hold_keys = set()
        for product, account_name in products:
            current_price = float(product.current_price)
            event_kind = None
            if min_price is not None and current_price < float(min_price):
                event_kind = "price_below_min"
                message = (
                    f"Price below minimum: {product.asin} is now {current_price:.2f} "
                    f"in {account_name} (min: {float(min_price):.2f})"
                )
            elif max_price is not None and current_price > float(max_price):
                event_kind = "price_above_max"
                message = (
                    f"Price above maximum: {product.asin} is now {current_price:.2f} "
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
                    "recommended_action": "Review repricing rules or recent listing edits.",
                },
            )
            if was_created:
                count += 1
        await _resolve_missing_alerts(db, rule, ["price_below_min", "price_above_max"], hold_keys)
        return count

    async def _evaluate_bsr_drop(db, rule):
        """Evaluate bsr_drop alert rule."""
        drop_percent = float(rule.conditions.get("drop_percent", 20))
        lookback_days = max(int(rule.conditions.get("lookback_days", 7)), 3)
        min_history_points = max(int(rule.conditions.get("min_history_points", 4)), 3)

        query = select(Product, AmazonAccount.account_name).join(
            AmazonAccount, AmazonAccount.id == Product.account_id
        ).where(
            Product.is_active == True,
            Product.current_bsr.isnot(None),
        )
        if rule.applies_to_accounts:
            query = query.where(Product.account_id.in_(rule.applies_to_accounts))
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
                        f"BSR worsened for {product.asin} in {account_name}: "
                        f"#{latest_bsr} vs baseline #{baseline_bsr:.0f} ({change_pct:.0f}% worse)"
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
                        "recommended_action": "Review ranking, pricing, and ad activity to confirm whether the drop is sustained.",
                    },
                )
                if was_created:
                    count += 1
        await _resolve_missing_alerts(db, rule, ["bsr_drop"], hold_keys)
        return count

    async def _check():
        from app.db import session as db_session
        async with db_session.AsyncSessionLocal() as db:
            result = await db.execute(
                select(AlertRule).where(AlertRule.is_enabled == True)
            )
            rules = result.scalars().all()

            evaluators = {
                "low_stock": _evaluate_low_stock,
                "sync_failure": _evaluate_sync_failure,
                "price_change": _evaluate_price_change,
                "bsr_drop": _evaluate_bsr_drop,
            }

            triggered = 0
            for rule in rules:
                try:
                    evaluator = evaluators.get(rule.alert_type)
                    if evaluator is None:
                        logger.warning(f"Unknown alert type: {rule.alert_type}")
                        continue
                    triggered += await evaluator(db, rule)
                except Exception as exc:
                    logger.warning(f"Failed to check alert rule {rule.id}: {exc}")

            await db.commit()
            retry_cutoff = datetime.utcnow() - QUEUE_RETRY_AFTER
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

            queued = 0
            now = datetime.utcnow()
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
                    try:
                        send_alert.delay(alert_ids=[str(alert.id) for alert in batch])
                        for alert in batch:
                            alert.notification_status = "queued"
                            alert.notification_error = None
                            alert.last_notification_attempt_at = now
                        queued += len(batch)
                    except Exception as exc:
                        for alert in batch:
                            alert.notification_status = "failed"
                            alert.notification_error = str(exc)
                            alert.last_notification_attempt_at = now

            await db.commit()
            logger.info(
                "Alert check complete: %s rules checked, %s alerts triggered, %s alerts queued",
                len(rules),
                triggered,
                queued,
            )
            return {"checked": len(rules), "triggered": triggered, "queued": queued}

    return run_async(_check)
