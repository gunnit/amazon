"""Notification service for email and alerts."""
import base64
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Actionable error states surfaced to operators and the UI (Italian copy).
EMAIL_ERROR_NOT_CONFIGURED = "Invio email non configurato: chiave SendGrid mancante sul server."


def _sender_unverified_message(from_email: str) -> str:
    return (
        f"Mittente {from_email} non verificato su SendGrid: "
        "verifica la Sender Identity sull'account SendGrid per abilitare l'invio."
    )


class NotificationService:
    """Service for sending notifications."""

    def __init__(self, sendgrid_api_key: Optional[str] = None):
        self.sendgrid_api_key = sendgrid_api_key
        # Holds the actionable reason for the most recent failed send, or None.
        self.last_error: Optional[str] = None

    async def send_email(
        self,
        to_emails: List[str],
        subject: str,
        html_content: str,
        from_email: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Send email using SendGrid.

        On failure, ``self.last_error`` carries an actionable Italian message
        (e.g. an unverified sender) so callers can show it instead of a
        generic "failed".
        """
        self.last_error = None

        if from_email is None:
            from app.config import settings
            from_email = settings.SENDGRID_FROM_EMAIL

        if not self.sendgrid_api_key:
            logger.warning("SendGrid API key not configured")
            self.last_error = EMAIL_ERROR_NOT_CONFIGURED
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

            if response.status_code in [200, 201, 202]:
                return True

            self.last_error = f"SendGrid ha risposto con stato {response.status_code}."
            logger.warning("SendGrid send returned status %s", response.status_code)
            return False

        except Exception as e:
            self.last_error = self._classify_send_error(e, from_email)
            logger.error("Failed to send email via SendGrid: %s", self.last_error)
            return False

    def check_sender_verified(self, from_email: Optional[str] = None) -> Optional[bool]:
        """Best-effort check that ``from_email`` is a verified SendGrid sender.

        Uses SendGrid's read-only verified-senders API (a cheap GET) so it does
        NOT send a live email. Returns ``True``/``False`` when the answer is
        known, or ``None`` when it can't be determined (no key, network/library
        failure, unexpected payload). Never raises.
        """
        if not self.sendgrid_api_key:
            return None

        if from_email is None:
            from app.config import settings
            from_email = settings.SENDGRID_FROM_EMAIL

        try:
            from sendgrid import SendGridAPIClient

            sg = SendGridAPIClient(self.sendgrid_api_key)
            response = sg.client.verified_senders.get()
            if response.status_code not in (200, 201):
                return None

            body = response.body
            if isinstance(body, (bytes, bytearray)):
                body = body.decode("utf-8", errors="replace")
            import json

            payload = json.loads(body) if isinstance(body, str) else body
            results = (payload or {}).get("results", [])
            target = (from_email or "").strip().lower()
            for entry in results:
                from_addr = (entry.get("from_email") or "").strip().lower()
                if from_addr == target:
                    return bool(entry.get("verified"))
            return False
        except Exception as exc:  # noqa: BLE001 - status check must never raise
            logger.warning("SendGrid sender verification check failed: %s", exc)
            return None

    @staticmethod
    def _classify_send_error(error: Exception, from_email: str) -> str:
        """Turn a raw SendGrid exception into an actionable Italian message."""
        status_code = getattr(error, "status_code", None)
        body = getattr(error, "body", None)
        if isinstance(body, (bytes, bytearray)):
            body = body.decode("utf-8", errors="replace")
        body_text = (body or "").lower()

        if status_code == 403 or "sender identity" in body_text or "verified sender" in body_text:
            return _sender_unverified_message(from_email)
        if status_code == 401 or "authorization grant" in body_text:
            return "Chiave SendGrid non valida o revocata: aggiorna le credenziali sul server."
        if status_code:
            return f"Invio email fallito (SendGrid {status_code})."
        return "Invio email fallito per un errore SendGrid imprevisto."

    async def send_alert(
        self,
        alert_type: str,
        message: str,
        details: Dict[str, Any],
        channels: List[str],
        emails: Optional[List[str]] = None,
        webhook_url: Optional[str] = None,
        from_email: Optional[str] = None,
    ) -> Dict[str, bool]:
        """Send alert through specified channels."""
        results = {}
        alert_label = details.get("incident_label") or details.get("incident_type") or alert_type

        if "email" in channels and emails:
            subject = f"Inthezon Alert: {alert_label}"
            html_content = self._format_alert_email(alert_label, message, details)
            results["email"] = await self.send_email(emails, subject, html_content, from_email=from_email)

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
        details_html = self._format_detail_items(details)

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

    def _format_detail_items(self, value: Any) -> str:
        """Render nested detail data into a small HTML list."""
        if isinstance(value, dict):
            return "".join(
                f"<li><strong>{k.replace('_', ' ').title()}:</strong> {self._format_detail_value(v)}</li>"
                for k, v in value.items()
                if v not in (None, "", [])
            )
        return self._format_detail_value(value)

    def _format_detail_value(self, value: Any) -> str:
        if isinstance(value, dict):
            return f"<ul>{self._format_detail_items(value)}</ul>"
        if isinstance(value, list):
            items = "".join(f"<li>{self._format_detail_value(item)}</li>" for item in value)
            return f"<ul>{items}</ul>"
        return str(value)

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
        from_email: Optional[str] = None,
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
            from_email=from_email,
        )
