"""Notification service for email and alerts."""
import base64
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending notifications."""

    def __init__(self, sendgrid_api_key: Optional[str] = None):
        self.sendgrid_api_key = sendgrid_api_key

    async def send_email(
        self,
        to_emails: List[str],
        subject: str,
        html_content: str,
        from_email: str = "noreply@niuexa.ai",
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Send email using SendGrid."""
        if not self.sendgrid_api_key:
            logger.warning("SendGrid API key not configured")
            return False

        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Attachment, Disposition, FileContent, FileName, FileType, Mail

            message = Mail(
                from_email=from_email,
                to_emails=to_emails,
                subject=subject,
                html_content=html_content,
            )

            for attachment in attachments or []:
                encoded = base64.b64encode(attachment["content"]).decode("ascii")
                message.attachment = Attachment(
                    file_content=FileContent(encoded),
                    file_name=FileName(attachment["filename"]),
                    file_type=FileType(attachment.get("content_type") or "application/octet-stream"),
                    disposition=Disposition("attachment"),
                )

            sg = SendGridAPIClient(self.sendgrid_api_key)
            response = sg.send(message)

            return response.status_code in [200, 201, 202]

        except Exception as e:
            logger.exception(f"Failed to send email: {e}")
            return False

    async def send_alert(
        self,
        alert_type: str,
        message: str,
        details: Dict[str, Any],
        channels: List[str],
        emails: Optional[List[str]] = None,
        webhook_url: Optional[str] = None,
    ) -> Dict[str, bool]:
        """Send alert through specified channels."""
        results = {}

        if "email" in channels and emails:
            subject = f"Inthezon Alert: {alert_type}"
            html_content = self._format_alert_email(alert_type, message, details)
            results["email"] = await self.send_email(emails, subject, html_content)

        if "webhook" in channels and webhook_url:
            results["webhook"] = await self._send_webhook(webhook_url, {
                "alert_type": alert_type,
                "message": message,
                "details": details,
            })

        return results

    def _format_alert_email(
        self,
        alert_type: str,
        message: str,
        details: Dict[str, Any],
    ) -> str:
        """Format alert as HTML email."""
        details_html = "".join(
            f"<li><strong>{k}:</strong> {v}</li>"
            for k, v in details.items()
        )

        return f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #4472C4;">Inthezon Alert: {alert_type}</h2>
            <p>{message}</p>
            <h3>Details:</h3>
            <ul>{details_html}</ul>
            <hr>
            <p style="color: #666; font-size: 12px;">
                This is an automated alert from Inthezon.
                Log in to your dashboard for more details.
            </p>
        </body>
        </html>
        """

    async def _send_webhook(
        self,
        url: str,
        payload: Dict[str, Any],
    ) -> bool:
        """Send webhook notification."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    timeout=30.0,
                )
                return response.status_code in [200, 201, 202, 204]

        except Exception as e:
            logger.exception(f"Failed to send webhook: {e}")
            return False

    async def send_daily_digest(
        self,
        to_email: str,
        kpis: Dict[str, Any],
        alerts: List[Dict[str, Any]],
    ) -> bool:
        """Send daily digest email."""
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h1 style="color: #4472C4;">Daily Performance Digest</h1>

            <h2>Key Metrics</h2>
            <table style="border-collapse: collapse; width: 100%;">
                <tr style="background-color: #4472C4; color: white;">
                    <th style="padding: 10px; text-align: left;">Metric</th>
                    <th style="padding: 10px; text-align: right;">Value</th>
                    <th style="padding: 10px; text-align: right;">Change</th>
                </tr>
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #ddd;">Revenue</td>
                    <td style="padding: 10px; text-align: right;">${kpis.get('revenue', 0):,.2f}</td>
                    <td style="padding: 10px; text-align: right;">{kpis.get('revenue_change', 0):+.1f}%</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #ddd;">Units Sold</td>
                    <td style="padding: 10px; text-align: right;">{kpis.get('units', 0):,}</td>
                    <td style="padding: 10px; text-align: right;">{kpis.get('units_change', 0):+.1f}%</td>
                </tr>
            </table>

            <h2>Alerts ({len(alerts)})</h2>
            {''.join(f'<p>- {a.get("message", "")}</p>' for a in alerts[:5])}

            <hr>
            <p style="color: #666; font-size: 12px;">
                View full details in your <a href="https://inthezon.niuexa.ai">Inthezon Dashboard</a>
            </p>
        </body>
        </html>
        """

        return await self.send_email(
            to_emails=[to_email],
            subject="Inthezon Daily Digest",
            html_content=html_content,
        )
