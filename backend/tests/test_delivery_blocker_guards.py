"""Guards that stand between a single mistake and unrecoverable damage.

Each one closes a blocker found in the 2026-08-28 delivery-readiness audit:
* the retention tasks delete client history the handover docs tell you to start;
* the rate limiter keyed off a caller-supplied header (CWE-348);
* deleting the last admin locks the organization out with no way back in.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

# NOTE: run this module on its own (`pytest tests/test_delivery_blocker_guards.py`).
# Several other test modules replace `app.*` entries in sys.modules with stubs
# and never restore them, so a single-process full-suite run resolves the import
# below to a stub. That harness defect predates this file and is tracked as the
# conftest.py/sys.modules isolation item; it is not a defect in these guards.
from app.api.deps import RateLimiter, client_ip, TRUSTED_PROXY_HOPS
from workers.tasks import maintenance


def _request(headers: dict, peer: str = "10.0.0.9"):
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=peer))


def test_destructive_tasks_refuse_without_opt_in(monkeypatch):
    monkeypatch.delenv("ALLOW_DESTRUCTIVE_RETENTION", raising=False)
    for task in ("manage_data_retention", "manage_partitions"):
        with pytest.raises(RuntimeError, match="disabled by default"):
            maintenance._require_destructive_opt_in(task)


def test_destructive_tasks_run_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_RETENTION", "true")
    maintenance._require_destructive_opt_in("manage_data_retention")


def test_forged_forwarded_for_cannot_change_the_bucket():
    """A caller prepending addresses must not get a fresh rate-limit bucket."""
    assert TRUSTED_PROXY_HOPS == 1
    honest = _request({"x-forwarded-for": "203.0.113.7"})
    forged = _request({"x-forwarded-for": "1.2.3.4, 5.6.7.8, 203.0.113.7"})
    assert client_ip(honest) == client_ip(forged) == "203.0.113.7"


def test_client_ip_falls_back_to_the_peer_without_the_header():
    assert client_ip(_request({}, peer="198.51.100.4")) == "198.51.100.4"


@pytest.mark.asyncio
async def test_account_limit_survives_ip_rotation():
    """The per-account counter is what an attacker cannot rotate away."""
    limiter = RateLimiter(max_requests=3, window_seconds=900, scope="login-account")
    for _ in range(3):
        await limiter.hit("victim@example.com")
    with pytest.raises(HTTPException) as exc:
        await limiter.hit("victim@example.com")
    assert exc.value.status_code == 429
    # A different account is unaffected.
    await limiter.hit("someone-else@example.com")
