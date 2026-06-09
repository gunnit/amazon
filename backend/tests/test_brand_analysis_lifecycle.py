"""Unit tests for brand analysis job lifecycle (cancel + delete hardening).

These exercise the state-machine logic in ``BrandAnalysisService`` without a
live database by stubbing ``get_job`` and using a no-op fake session, so the
status transitions and guard rails are covered in CI without Postgres.
"""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.services.brand_analysis_service as svc  # noqa: E402
from app.services.brand_analysis_service import (  # noqa: E402
    RUNNING_STATUSES,
    TERMINAL_STATUSES,
    STATUS_PROGRESS,
    BrandAnalysisJobRunningError,
    BrandAnalysisService,
)


def _run(coro):
    return asyncio.run(coro)


class _FakeDB:
    def __init__(self):
        self.deleted = []

    async def flush(self):
        return None

    async def delete(self, obj):
        self.deleted.append(obj)


class _StubService(BrandAnalysisService):
    def __init__(self, job):
        super().__init__(_FakeDB())
        self._job = job

    async def get_job(self, job_id, org_id):
        return self._job


def _job(**overrides):
    base = dict(
        id=uuid4(),
        organization_id=uuid4(),
        account_id=None,
        brand_name="Acme",
        status="pending",
        progress_step="Queued",
        progress_pct=0,
        error_message=None,
        completed_at=None,
        cancel_requested=False,
        celery_task_id=None,
        updated_at=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_status_sets_are_consistent():
    assert "cancelling" in RUNNING_STATUSES
    assert "cancelled" in TERMINAL_STATUSES
    assert "cancelled" not in RUNNING_STATUSES
    assert STATUS_PROGRESS["cancelled"] == 100
    assert STATUS_PROGRESS["cancelling"] == 95
    # Terminal and running sets must not overlap.
    assert RUNNING_STATUSES.isdisjoint(TERMINAL_STATUSES)


def test_cancel_pending_job_goes_straight_to_cancelled():
    job = _job(status="pending")
    service = _StubService(job)
    result = _run(service.request_cancel(job.id, job.organization_id))
    assert result.status == "cancelled"
    assert result.cancel_requested is True
    assert result.progress_pct == 100
    assert result.completed_at is not None


def test_cancel_running_job_enters_cancelling_and_revokes(monkeypatch):
    revoked = {}
    monkeypatch.setattr(svc, "_revoke_celery_task", lambda tid: revoked.setdefault("id", tid))
    job = _job(status="generating_metrics", celery_task_id="task-123")
    service = _StubService(job)
    result = _run(service.request_cancel(job.id, job.organization_id))
    assert result.status == "cancelling"
    assert result.cancel_requested is True
    assert revoked["id"] == "task-123"
    # Still non-terminal: the worker finalizes to cancelled cooperatively.
    assert result.status not in TERMINAL_STATUSES


def test_cancel_terminal_job_is_left_untouched():
    job = _job(status="completed")
    service = _StubService(job)
    result = _run(service.request_cancel(job.id, job.organization_id))
    assert result.status == "completed"
    assert result.cancel_requested is False


def test_delete_running_job_is_rejected():
    job = _job(status="generating_pptx")
    service = _StubService(job)
    with pytest.raises(BrandAnalysisJobRunningError):
        _run(service.delete_job(job.id, job.organization_id))


def test_delete_terminal_job_is_allowed():
    job = _job(status="completed")
    service = _StubService(job)
    deleted = _run(service.delete_job(job.id, job.organization_id))
    assert deleted is True
    assert job in service.db.deleted


def test_notification_alert_types_map_to_contract():
    assert svc.BRAND_ANALYSIS_READY_ALERT_TYPE == "brand_analysis_ready"
    assert svc.BRAND_ANALYSIS_FAILED_ALERT_TYPE == "brand_analysis_failed"
