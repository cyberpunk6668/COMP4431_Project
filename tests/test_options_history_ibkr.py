"""Production history-provider guards/locks, with no socket or model requests."""
import asyncio
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from app import options_history_ibkr as history
from app.options_history import HistoryDataset
from app.options_ibkr import IBKRConfig, IBKROptionsError, IBKROptionsProvider


def future_expiry():
    return (datetime.now(UTC).date() + timedelta(days=14)).isoformat()


@pytest.mark.parametrize("updates", [
    {"symbol": "?"}, {"strike": 0}, {"strike": True}, {"strike": float("inf")},
    {"strike": 1_000_001}, {"days": True}, {"days": 6}, {"expiry": "2030-02-30"},
])
def test_invalid_parameters_fail_before_any_transport(monkeypatch, updates):
    async def forbidden(*args):
        raise AssertionError("Invalid history request must not reach transport")

    monkeypatch.setattr(history, "_fetch_report", forbidden)
    request = {"symbol": "AAPL", "expiry": future_expiry(), "strike": 350, "days": 5, **updates}
    with pytest.raises(IBKROptionsError) as raised:
        asyncio.run(history.IBKRHistoryProvider(IBKRConfig(enabled=True)).fetch(**request))
    assert raised.value.code == "ibkr_invalid_request"


def test_expired_disabled_and_invalid_config_do_not_open_transport(monkeypatch):
    async def forbidden(*args):
        raise AssertionError("Preflight must not reach transport")

    monkeypatch.setattr(history, "_fetch_report", forbidden)
    with pytest.raises(IBKROptionsError) as raised:
        asyncio.run(history.IBKRHistoryProvider(IBKRConfig(enabled=True)).fetch("AAPL", "2000-01-21", 350))
    assert raised.value.code == "ibkr_historical_expired_option"
    with pytest.raises(IBKROptionsError) as raised:
        asyncio.run(history.IBKRHistoryProvider(IBKRConfig()).fetch("AAPL", future_expiry(), 350))
    assert raised.value.code == "ibkr_disabled"
    monkeypatch.setenv("IBKR_HOST", "192.0.2.1")
    with pytest.raises(IBKROptionsError) as raised:
        asyncio.run(history.IBKRHistoryProvider().fetch("AAPL", future_expiry(), 350))
    assert raised.value.code == "ibkr_invalid_config"


def test_history_and_live_provider_share_one_lock(monkeypatch):
    async def exercise():
        shared = asyncio.Lock()
        started, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def collect(config, symbol, expiry, strike, days):
            calls.append((symbol, expiry, strike, days))
            started.set()
            await release.wait()
            return {"status": "passed", "dataset": {"bar_basis": "derived_from_intraday_trades"}}

        monkeypatch.setattr(history, "_fetch_report", collect)
        provider = history.IBKRHistoryProvider(IBKRConfig(enabled=True), lock=shared)
        live = IBKROptionsProvider(IBKRConfig(enabled=True))
        live._lock = shared
        work = asyncio.create_task(provider.fetch(" aapl ", future_expiry(), 350, 3))
        await started.wait()
        with pytest.raises(IBKROptionsError) as raised:
            await provider.fetch("AAPL", future_expiry(), 350)
        assert raised.value.code == "ibkr_busy"
        # The existing provider refuses at the shared lock, before constructing
        # any client or subscribing to a quote.
        with pytest.raises(IBKROptionsError) as raised:
            await live.snapshot("AAPL", market_data_type=3)
        assert raised.value.code == "ibkr_busy"
        release.set()
        result = await work
        assert result["dataset"]["bar_basis"] == "derived_from_intraday_trades"
        assert calls == [("AAPL", future_expiry(), 350.0, 3)] and not shared.locked()

    asyncio.run(exercise())


def test_partial_history_is_typed_failure_with_safe_diagnostics_and_releases_lock(monkeypatch):
    partial = {"status": "partial", "stage": "complete", "history_requests": 3,
               "global_broker_codes": [2106], "instruments": [
                   {"role": "stock", "status": "received", "bars": [{"close": 99}], "trading_days_received": 1},
                   {"role": "C", "status": "request_failed", "broker_codes": [162],
                    "safe_categories": ["permission_or_subscription"], "broker_message": "PRIVATE_ACCOUNT_DETAIL"},
                   {"role": "P", "status": "empty", "bars": []},
               ]}

    async def collect(*args):
        return partial

    monkeypatch.setattr(history, "_fetch_report", collect)
    provider = history.IBKRHistoryProvider(IBKRConfig(enabled=True))
    with pytest.raises(IBKROptionsError) as raised:
        asyncio.run(provider.fetch("AAPL", future_expiry(), 350))
    assert raised.value.code == "ibkr_historical_unavailable"
    diagnostics = raised.value.diagnostics
    assert diagnostics["history_requests"] == 3 and diagnostics["model_requests"] == 0
    assert diagnostics["broker_codes"] == [162, 2106]
    assert diagnostics["instruments"][1]["safe_categories"] == ["permission_or_subscription"]
    assert "PRIVATE_ACCOUNT" not in json.dumps(diagnostics) and "broker_message" not in json.dumps(diagnostics)
    assert not provider._lock.locked()


def test_dependency_failure_is_safe_and_unlocks(monkeypatch):
    async def unavailable(*args):
        raise ImportError("PRIVATE_MODULE_DETAIL")

    monkeypatch.setattr(history, "_fetch_report", unavailable)
    provider = history.IBKRHistoryProvider(IBKRConfig(enabled=True))
    with pytest.raises(IBKROptionsError) as raised:
        asyncio.run(provider.fetch("AAPL", future_expiry(), 350))
    assert raised.value.code == "ibkr_dependency_missing" and "PRIVATE" not in str(raised.value)
    assert not provider._lock.locked()


def test_recorded_actual_bars_replay_without_altering_receipt():
    receipt = Path(__file__).resolve().parents[1] / "reports/ibkr_history_probe_v13.json"
    if not receipt.is_file():
        pytest.skip("Recorded ordinary-market receipt is not packaged in this checkout")
    original_bytes = receipt.read_bytes()
    recorded = json.loads(original_bytes)
    if recorded.get("status") != "passed" or "dataset" not in recorded:
        pytest.skip("No successful recorded receipt")
    rows = []
    for item in recorded["instruments"]:
        if item["role"] in {"C", "P"}:
            derived, origins = history.aggregate_days(item["bars"], strike=item["strike"], right=item["role"])
            rows.extend(derived)
            assert all(origin["partial_bars"] and not origin["full_session_verified"] for origin in origins)
    rows.sort(key=lambda row: (row["trading_date"], row["strike"], row["right"]))
    assert rows == recorded["dataset"]["rows"]
    assert all(row["open_interest"] is row["oi_asof_date"] is None for row in rows)
    dataset = HistoryDataset.model_validate({**recorded["dataset"], "bar_basis": "derived_from_intraday_trades"})
    assert dataset.bar_basis == "derived_from_intraday_trades"
    assert receipt.read_bytes() == original_bytes
