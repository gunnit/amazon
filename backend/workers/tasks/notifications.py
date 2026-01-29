"""Notification Celery tasks."""
import asyncio
from uuid import UUID
import logging

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task
def send_email(to_emails: list, subject: str, html_content: str):
    """Send email notification."""
    from app.services.notification_service import NotificationService
    from app.config import settings

    async def _send():
        service = NotificationService(sendgrid_api_key=settings.SENDGRID_API_KEY)
        return await service.send_email(to_emails, subject, html_content)

    try:
        result = run_async(_send())
        logger.info(f"Email sent to {to_emails}: {result}")
        return {"sent": result}

    except Exception as e:
        logger.exception(f"Failed to send email to {to_emails}")
        raise


@celery_app.task
def send_alert(
    alert_type: str,
    message: str,
    details: dict,
    channels: list,
    emails: list = None,
    webhook_url: str = None,
):
    """Send alert notification."""
    from app.services.notification_service import NotificationService
    from app.config import settings

    async def _send():
        service = NotificationService(sendgrid_api_key=settings.SENDGRID_API_KEY)
        return await service.send_alert(
            alert_type, message, details, channels, emails, webhook_url
        )

    try:
        result = run_async(_send())
        logger.info(f"Alert sent: {result}")
        return result

    except Exception as e:
        logger.exception(f"Failed to send alert")
        raise


@celery_app.task
def send_daily_digests():
    """Send daily digest emails to all users."""
    from app.db.session import AsyncSessionLocal
    from app.models.user import User, OrganizationMember
    from app.services.analytics_service import AnalyticsService
    from app.services.notification_service import NotificationService
    from app.config import settings
    from datetime import date, timedelta
    from sqlalchemy import select

    async def _send_digests():
        async with AsyncSessionLocal() as db:
            # Get all active users with their organizations
            result = await db.execute(
                select(User, OrganizationMember.organization_id)
                .join(OrganizationMember)
                .where(User.is_active == True)
            )
            users = result.all()

            notification_service = NotificationService(
                sendgrid_api_key=settings.SENDGRID_API_KEY
            )
            analytics_service = AnalyticsService(db)

            sent_count = 0
            for user, org_id in users:
                try:
                    # Get KPIs for yesterday
                    yesterday = date.today() - timedelta(days=1)
                    kpis = await analytics_service.compute_dashboard_kpis(
                        account_ids=[org_id],  # Would need to get all org accounts
                        start_date=yesterday,
                        end_date=yesterday,
                    )

                    await notification_service.send_daily_digest(
                        to_email=user.email,
                        kpis=kpis["current"],
                        alerts=[],
                    )
                    sent_count += 1

                except Exception as e:
                    logger.warning(f"Failed to send digest to {user.email}: {e}")

            return {"sent": sent_count, "total_users": len(users)}

    return run_async(_send_digests())


@celery_app.task
def check_alerts():
    """Check all alert rules and trigger notifications."""
    from app.db.session import AsyncSessionLocal
    from app.models.alert import AlertRule
    from app.models.amazon_account import AmazonAccount
    from app.models.inventory import InventoryData
    from datetime import date
    from sqlalchemy import select, func

    async def _check():
        async with AsyncSessionLocal() as db:
            # Get all enabled alert rules
            result = await db.execute(
                select(AlertRule).where(AlertRule.is_enabled == True)
            )
            rules = result.scalars().all()

            triggered = 0
            for rule in rules:
                try:
                    if rule.alert_type == "low_stock":
                        # Check for low stock items
                        threshold = rule.conditions.get("threshold", 10)
                        accounts = rule.applies_to_accounts or []

                        query = select(func.count(InventoryData.id)).where(
                            InventoryData.afn_fulfillable_quantity < threshold,
                            InventoryData.snapshot_date == date.today(),
                        )
                        if accounts:
                            query = query.where(InventoryData.account_id.in_(accounts))

                        count_result = await db.execute(query)
                        low_stock_count = count_result.scalar()

                        if low_stock_count > 0:
                            send_alert.delay(
                                alert_type="low_stock",
                                message=f"{low_stock_count} products below stock threshold",
                                details={"count": low_stock_count, "threshold": threshold},
                                channels=rule.notification_channels or [],
                                emails=rule.notification_emails,
                                webhook_url=rule.webhook_url,
                            )
                            triggered += 1

                except Exception as e:
                    logger.warning(f"Failed to check alert rule {rule.id}: {e}")

            return {"checked": len(rules), "triggered": triggered}

    return run_async(_check())
