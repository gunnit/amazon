"""When the Anthropic provider is down (no credit, rate limit, outage) the
recommendation generation must surface a clean 502 with a non-leaking detail,
never an uncaught 500 with a stack trace.
"""
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.api.v1 import recommendations as rec_endpoint
from app.schemas.strategic_recommendation import StrategicRecommendationGenerateRequest
from app.services import strategic_recommendations_service as svc
from app.services.strategic_recommendations_service import (
    AIProviderUnavailableError,
    StrategicRecommendationsService,
    _is_anthropic_provider_error,
)


# A stand-in that looks like an anthropic SDK error: same module name + class name.
class _FakeAnthropicError(Exception):
    pass


_FakeAnthropicError.__module__ = "anthropic"
_FakeAnthropicError.__name__ = "APIStatusError"
_FakeAnthropicError.__qualname__ = "APIStatusError"


def test_is_anthropic_provider_error_detects_sdk_error():
    err = _FakeAnthropicError("Your credit balance is too low to access the API")
    assert _is_anthropic_provider_error(err) is True


def test_is_anthropic_provider_error_ignores_other_errors():
    assert _is_anthropic_provider_error(ValueError("bad json")) is False
    assert _is_anthropic_provider_error(RuntimeError("boom")) is False


@pytest.mark.asyncio
async def test_generate_translates_provider_error(monkeypatch):
    """A raised anthropic error becomes AIProviderUnavailableError, not a 500."""
    service = StrategicRecommendationsService(db=SimpleNamespace())
    org_id = uuid4()

    monkeypatch.setattr(svc.settings, "ANTHROPIC_API_KEY", "test-key", raising=False)

    async def _granularity(*args, **kwargs):
        return SimpleNamespace()

    async def _snapshot(*args, **kwargs):
        return {"accounts": [{"account_id": str(uuid4())}], "date_from": None, "date_to": None}

    monkeypatch.setattr(service, "_resolve_granularity", _granularity)
    monkeypatch.setattr(service, "_effective_lookback", lambda *a, **k: 28)
    monkeypatch.setattr(service, "_build_org_snapshot", _snapshot)

    def _raise(*args, **kwargs):
        raise _FakeAnthropicError("Your credit balance is too low to access the API")

    monkeypatch.setattr(svc._StrategicRecAnalysisService, "__init__", lambda self, key: None)
    monkeypatch.setattr(svc._StrategicRecAnalysisService, "analyze", _raise)

    with pytest.raises(AIProviderUnavailableError):
        await service.generate_for_organization(org_id, language="en")


@pytest.mark.asyncio
async def test_endpoint_maps_provider_error_to_clean_502(monkeypatch):
    """The endpoint returns 502 with a stable, non-leaking detail."""
    org = SimpleNamespace(id=uuid4())
    user = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(commit=None)

    provider_message = "Your credit balance is too low to access the API"

    class _StubService:
        def __init__(self, _db):
            pass

        async def generate_for_organization(self, *args, **kwargs):
            raise AIProviderUnavailableError(provider_message)

    monkeypatch.setattr(rec_endpoint, "StrategicRecommendationsService", _StubService)

    payload = StrategicRecommendationGenerateRequest(language="en")

    with pytest.raises(HTTPException) as exc_info:
        await rec_endpoint.generate_recommendations(
            payload=payload, db=db, org=org, current_user=user
        )

    assert exc_info.value.status_code == 502
    # Detail is a stable token, NOT the raw provider message.
    assert exc_info.value.detail == "ai_provider_unavailable"
    assert provider_message not in str(exc_info.value.detail)
