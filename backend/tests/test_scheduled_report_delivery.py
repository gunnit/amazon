"""Delivery + email-readiness tests for scheduled reports.

These exercise the real delivery/digest control flow without sending email or
touching a database: the per-run engine/session is replaced with an in-memory
fake that hands back prepared run/schedule objects.

Run in isolation:
    venv/bin/python -m pytest tests/test_scheduled_report_delivery.py -p no:cacheprovider -q
"""
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import scheduled_report_service as srs
from app.services import notification_service as ns
from workers.tasks import notifications as notif_tasks


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """Yields run then schedule on successive execute() calls; records commits."""

    def __init__(self, run, schedule):
        self._returns = [run, schedule]
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, _query):
        value = self._returns.pop(0) if self._returns else None
        return _FakeResult(value)

    async def commit(self):
        self.commits += 1


def _make_run_and_schedule():
    run = SimpleNamespace(
        id=uuid4(),
        scheduled_report_id=uuid4(),
        artifact_data_compressed=b"gzipped-bytes",
        artifact_data=b"raw-bytes",
        artifact_filename="report.xlsx",
        artifact_content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        recipients_snapshot=["alice@example.com"],
        report_name="Weekly perf",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 7),
        status="generated",
        delivery_status="pending",
        progress_step="Report generated",
        error_message=None,
        completed_at=None,
    )
    schedule = SimpleNamespace(
        id=run.scheduled_report_id,
        last_run_status="generated",
        last_run_at=None,
    )
    return run, schedule


def _patch_delivery_session(monkeypatch, run, schedule):
    session = _FakeSession(run, schedule)

    class _Maker:
        def __call__(self):
            return session

    monkeypatch.setattr(srs, "async_sessionmaker", lambda *a, **k: _Maker())

    # The engine is disposed in the finally block; provide an async no-op.
    async def _dispose():
        return None

    monkeypatch.setattr(
        srs,
        "create_async_engine",
        lambda *a, **k: SimpleNamespace(dispose=_dispose),
    )
    return session


def test_delivery_not_configured_when_sendgrid_missing(monkeypatch):
    run, schedule = _make_run_and_schedule()
    _patch_delivery_session(monkeypatch, run, schedule)
    monkeypatch.setattr(srs.settings, "SENDGRID_API_KEY", None)

    srs.deliver_scheduled_report_run_job(str(run.id))

    assert run.delivery_status == "not_configured"
    assert run.status == "generated"
    assert schedule.last_run_status == "generated"
    # Artifact remains downloadable.
    assert run.artifact_data_compressed


def test_delivery_failed_keeps_run_generated(monkeypatch):
    run, schedule = _make_run_and_schedule()
    _patch_delivery_session(monkeypatch, run, schedule)
    monkeypatch.setattr(srs.settings, "SENDGRID_API_KEY", "SG.key")

    async def _fake_send(self, *args, **kwargs):
        self.last_error = "Mittente non verificato su SendGrid"
        return False

    monkeypatch.setattr(ns.NotificationService, "send_email", _fake_send)

    srs.deliver_scheduled_report_run_job(str(run.id))

    assert run.delivery_status == "failed"
    assert run.status == "generated"
    assert run.error_message == "Mittente non verificato su SendGrid"
    assert schedule.last_run_status == "generated"


def test_delivery_sent_marks_run_delivered(monkeypatch):
    run, schedule = _make_run_and_schedule()
    _patch_delivery_session(monkeypatch, run, schedule)
    monkeypatch.setattr(srs.settings, "SENDGRID_API_KEY", "SG.key")

    captured = {}

    async def _fake_send(self, *args, **kwargs):
        captured["from_email"] = kwargs.get("from_email")
        return True

    monkeypatch.setattr(ns.NotificationService, "send_email", _fake_send)

    srs.deliver_scheduled_report_run_job(str(run.id))

    assert run.delivery_status == "sent"
    assert run.status == "delivered"
    assert schedule.last_run_status == "delivered"
    # Verified sender is passed through from config.
    assert captured["from_email"] == srs.settings.SENDGRID_FROM_EMAIL


def test_daily_digests_short_circuit_without_sendgrid(monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "SENDGRID_API_KEY", None)

    iterated = {"sessions": 0}

    def _boom(*_a, **_k):
        iterated["sessions"] += 1
        raise AssertionError("send_daily_digests must not open a session when SendGrid is absent")

    # If the short-circuit fails, run_async would be invoked and open a session.
    monkeypatch.setattr(notif_tasks, "run_async", _boom)

    result = notif_tasks.send_daily_digests()

    assert result == {"skipped": True, "reason": "sendgrid_not_configured", "sent": 0}
    assert iterated["sessions"] == 0


@pytest.mark.asyncio
async def test_send_email_uses_config_from_email_when_not_passed(monkeypatch):
    captured = {}

    class _FakeMail:
        def __init__(self, *, from_email, to_emails, subject, html_content):
            captured["from_email"] = from_email

    class _FakeResponse:
        status_code = 202

    class _FakeClient:
        def __init__(self, _key):
            pass

        def send(self, _message):
            return _FakeResponse()

    import sendgrid
    import sendgrid.helpers.mail as mail_helpers

    monkeypatch.setattr(sendgrid, "SendGridAPIClient", _FakeClient)
    monkeypatch.setattr(mail_helpers, "Mail", _FakeMail)

    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "SENDGRID_FROM_EMAIL", "verified@inthezon.test")

    service = ns.NotificationService(sendgrid_api_key="SG.key")
    ok = await service.send_email(
        to_emails=["alice@example.com"],
        subject="Hi",
        html_content="<p>hi</p>",
    )

    assert ok is True
    assert captured["from_email"] == "verified@inthezon.test"
