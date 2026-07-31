"""Advertising history backfill: window chunking and failure surfacing."""
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AmazonAPIError
from app.services.data_extraction import (
    ADS_LOOKBACK_DAYS,
    ADS_REPORT_MAX_WINDOW_DAYS,
    DataExtractionService,
)


class FakeDb:
    def __init__(self):
        self.commits = 0
        self.flushes = 0

    async def commit(self):
        self.commits += 1

    async def flush(self):
        self.flushes += 1


def _account(**overrides):
    base = dict(
        id=uuid4(),
        account_name="Dialcos",
        advertising_refresh_token_encrypted="enc-token",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _prepare(service, monkeypatch, client=None):
    """Stub the client factory, campaign upsert, and campaign-id map."""
    if client is None:
        client = SimpleNamespace(list_campaigns=lambda _p: [], close=lambda: None)
    monkeypatch.setattr(
        service, "_create_advertising_api_client", lambda *_a, **_k: (client, "profile-1")
    )

    async def fake_sync_campaigns(_account, _campaigns):
        return 0

    async def fake_map(_account):
        return {}

    monkeypatch.setattr(service, "_sync_advertising_campaigns", fake_sync_campaigns)
    monkeypatch.setattr(service, "_campaign_ids_by_external_id", fake_map)
    return client


@pytest.mark.asyncio
async def test_backfill_windows_respect_cap_and_lookback(monkeypatch):
    db = FakeDb()
    service = DataExtractionService(db)
    _prepare(service, monkeypatch)
    calls = []

    async def fake_run_reports(_client, _profile, _account, _map, start, end, report_types):
        calls.append((start, end, tuple(report_types)))
        return 1, []

    monkeypatch.setattr(service, "_run_advertising_reports", fake_run_reports)

    total = await service.backfill_advertising_history(_account())

    today = date.today()
    yesterday = today - timedelta(days=1)
    by_types = {}
    for start, end, report_types in calls:
        assert start <= end
        assert (end - start).days + 1 <= ADS_REPORT_MAX_WINDOW_DAYS
        by_types.setdefault(report_types, []).append((start, end))

    expected = {
        ("sp_campaigns", "sp_advertised_product"): "sp",
        ("sb_campaigns",): "sb",
        ("sd_campaigns",): "sd",
    }
    assert set(by_types) == set(expected)
    for report_types, product in expected.items():
        windows = sorted(by_types[report_types])
        assert windows[0][0] == today - timedelta(days=ADS_LOOKBACK_DAYS[product] - 1)
        assert windows[-1][1] == yesterday
        for (_s1, e1), (s2, _e2) in zip(windows, windows[1:]):
            assert s2 == e1 + timedelta(days=1)  # contiguous: no gaps, no overlaps

    assert total == len(calls)
    assert db.commits == len(calls)


@pytest.mark.asyncio
async def test_backfill_skips_account_without_ads_token(monkeypatch):
    service = DataExtractionService(FakeDb())

    def explode(*_a, **_k):
        raise AssertionError("must not create an ads client without a token")

    monkeypatch.setattr(service, "_create_advertising_api_client", explode)

    count = await service.backfill_advertising_history(
        _account(advertising_refresh_token_encrypted=None)
    )
    assert count == 0


@pytest.mark.asyncio
async def test_sync_advertising_raises_when_all_reports_fail(monkeypatch):
    service = DataExtractionService(FakeDb())

    def failing_request(**_kwargs):
        raise AmazonAPIError("report request rejected", error_code="400")

    client = SimpleNamespace(
        list_campaigns=lambda _p: [],
        request_report=failing_request,
        close=lambda: None,
    )
    _prepare(service, monkeypatch, client=client)

    with pytest.raises(AmazonAPIError) as excinfo:
        await service.sync_advertising(_account())

    assert "All advertising reports failed" in str(excinfo.value)
    assert excinfo.value.error_code == "ADS_ALL_REPORTS_FAILED"


@pytest.mark.asyncio
async def test_sync_advertising_tolerates_partial_failures_and_defaults_window(monkeypatch):
    db = FakeDb()
    service = DataExtractionService(db)
    requested = []

    def request_report(profile_id, report_type, date_range):
        requested.append((report_type, date_range))
        if report_type != "sp_campaigns":
            raise AmazonAPIError("report unavailable", error_code="404")
        return "report-1"

    client = SimpleNamespace(
        list_campaigns=lambda _p: [],
        request_report=request_report,
        close=lambda: None,
    )
    _prepare(service, monkeypatch, client=client)

    async def fake_process_campaign(_client, _profile, _rt, _rid, _account, _map):
        return 3

    monkeypatch.setattr(service, "_process_campaign_report", fake_process_campaign)

    count = await service.sync_advertising(_account())

    assert count == 3
    today = date.today()
    assert requested[0][1] == (today - timedelta(days=6), today)
