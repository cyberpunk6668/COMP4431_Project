"""Offline protocol and aggregation checks; never connect to an IB endpoint."""
import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from scripts import probe_ibkr_history_v13 as probe
from app import options_history_ibkr as history


def hourly(stamp, opening=1, closing=2, volume=10):
    return SimpleNamespace(date=str(int(stamp.timestamp())), open=opening, high=max(opening, closing) + 1,
                           low=min(opening, closing) / 2, close=closing, volume=volume, average=1.5, barCount=3)


def test_installed_decoder_17_delivers_bars_and_end_callback():
    decoder_type = pytest.importorskip("ib_async.decoder").Decoder
    callbacks = probe.make_callbacks()

    async def collect():
        future = asyncio.get_running_loop().create_future()
        callbacks.pending[7] = (future, [])
        decoder = decoder_type(callbacks, 178)
        decoder.interpret(["17", "7", "start", "end", "2",
                           "1794317400", "1", "3", ".5", "2", "10", "1.5", "3",
                           "1794321000", "2", "4", "1", "3", "20", "2.5", "4"])
        bars = await future
        callbacks.pending.pop(7)
        assert len(bars) == 2 and bars[0].close == 2 and bars[1].volume == 20
        assert "17" in probe.HISTORY_MESSAGES and "90" not in probe.HISTORY_MESSAGES

    asyncio.run(collect())


def test_hourly_to_day_is_derived_and_does_not_invent_oi_or_dates():
    bars = [probe.normalize_bar(hourly(datetime(2026, 11, 9, 14, 30, tzinfo=UTC))),
            probe.normalize_bar(hourly(datetime(2026, 11, 9, 15, 30, tzinfo=UTC), 2, 3, 20))]
    untouched = deepcopy(bars)
    rows, origins = probe.aggregate_days(bars, strike=350, right="C")
    assert rows == [{"trading_date": "2026-11-09", "open": 1, "high": 4, "low": .5,
                     "close": 3, "volume": 30, "strike": 350, "right": "C", "open_interest": None, "oi_asof_date": None}]
    assert origins[0]["observed_hourly_bars"] == 2 and origins[0]["derived_daily"]
    assert origins[0]["partial_bars"] and not origins[0]["full_session_verified"]
    assert bars == untouched
    assert probe.aggregate_days([], strike=350, right="P") == ([], [])


def test_unknown_volume_does_not_become_zero_and_conflicting_bars_reject():
    stamp = datetime(2026, 11, 9, 14, 30, tzinfo=UTC)
    missing = probe.normalize_bar(hourly(stamp, volume=-1))
    rows, _ = probe.aggregate_days([missing], strike=350, right="P")
    assert rows[0]["volume"] is None
    zero = probe.normalize_bar(hourly(stamp, volume=0))
    assert probe.aggregate_days([zero], strike=350, right="P")[0][0]["volume"] == 0
    with pytest.raises(ValueError, match="Conflicting"):
        probe.aggregate_days([zero, {**zero, "close": 100}])
    assert len(probe.aggregate_days([zero, deepcopy(zero)])[0]) == 1


def test_completed_calendar_window_excludes_today_and_uses_ny_timezone():
    # 02:00 UTC is still the previous New York date; DST offset is explicit.
    start, end = probe.completed_window(3, datetime(2026, 11, 11, 2, tzinfo=UTC))
    assert end == datetime(2026, 11, 10, 5, tzinfo=UTC)
    assert start == datetime(2026, 11, 7, 5, tzinfo=UTC)


@pytest.mark.parametrize("code,message,expected", [
    (162, "HMDS query returned no data", "no_historical_data"),
    (162, "No market data permissions for PRIVATE_ACCOUNT", "permission_or_subscription"),
    (162, "Historical data request pacing violation", "pacing"),
    (162, "No data of type EODChart is available", "unsupported_eod"),
    (10089, "Private subscription details", "permission_or_subscription"),
    (200, "Private contract details", "contract_unavailable"),
])
def test_hmds_error_code_is_not_automatically_assumed_to_be_permissions(code, message, expected):
    assert probe.error_category(code, message) == expected
    callbacks = probe.make_callbacks()
    callbacks.error(5, code, message)
    assert callbacks.codes[5] == {code} and callbacks.categories[5] == {expected}
    assert "PRIVATE_ACCOUNT" not in str(callbacks.__dict__)


def test_history_request_is_one_shot_and_timeout_cancels(monkeypatch):
    callbacks = probe.make_callbacks()
    calls = []
    end = datetime(2026, 11, 11, 5, tzinfo=UTC)

    class Client:
        def getReqId(self):
            return 9

        def reqHistoricalData(self, *args):
            calls.append(args)

        def isReady(self):
            return True

        def cancelHistoricalData(self, req_id):
            calls.append(("cancel", req_id))

    monkeypatch.setattr(history, "HISTORY_TIMEOUT", .001)
    with pytest.raises(TimeoutError):
        asyncio.run(probe.request_history(Client(), callbacks, "contract", end, 5))
    assert calls[0] == (9, "contract", "20261111-05:00:00", "5 D", "1 hour", "TRADES", True, 2, False, [])
    assert calls[-1] == ("cancel", 9) and callbacks.pending == {}


def test_default_cli_never_opens_gateway(monkeypatch, capsys):
    async def forbidden(*args):
        raise AssertionError("Default CLI must not enter probe")

    monkeypatch.setattr(probe, "probe", forbidden)
    assert probe.main([]) == 0
    assert "zero external requests" in capsys.readouterr().out


def test_complete_probe_uses_only_metadata_and_three_historical_requests(monkeypatch):
    transport = pytest.importorskip("ib_async.client")
    decoder_type = pytest.importorskip("ib_async.decoder").Decoder
    expiry = (datetime.now(UTC).date() + timedelta(days=30)).isoformat()
    calls = {"history": [], "connects": 0, "disconnects": 0}

    class Client:
        def __init__(self, callbacks):
            self.callbacks, self.next_id = callbacks, 0
            self.decoder = decoder_type(callbacks, 178)

        async def connectAsync(self, *args, **kwargs):
            calls["connects"] += 1

        def getReqId(self):
            self.next_id += 1
            return self.next_id

        def reqContractDetails(self, req_id, contract):
            if contract.secType == "STK":
                contract.conId, contract.primaryExchange = 1, "NASDAQ"
            else:
                contract.conId = 2 if contract.right == "C" else 3
            self.callbacks.contractDetails(req_id, SimpleNamespace(contract=contract))
            self.callbacks.contractDetailsEnd(req_id)

        def reqSecDefOptParams(self, req_id, *args):
            self.callbacks.securityDefinitionOptionParameter(req_id, "SMART", "1", "AAPL", "100", [expiry.replace("-", "")], [350])
            self.callbacks.securityDefinitionOptionParameterEnd(req_id)

        def reqHistoricalData(self, req_id, contract, end, duration, size, what, rth, fmt, updates, options):
            calls["history"].append((contract.secType, contract.right, duration, size, what, rth, fmt, updates, options))
            ending = datetime.strptime(end, "%Y%m%d-%H:%M:%S").replace(tzinfo=UTC)
            at = str(int((ending - timedelta(hours=12)).timestamp()))
            self.decoder.interpret(["17", str(req_id), "start", "end", "1", at, "1", "3", ".5", "2", "10", "1.5", "3"])

        def reqMktData(self, *args):
            raise AssertionError("History probe must not subscribe to live quotes")

        def reqMarketDataType(self, *args):
            raise AssertionError("Watchlist feed modes do not establish history entitlements")

        def isReady(self):
            return True

        def disconnect(self):
            calls["disconnects"] += 1

    async def no_wait(_seconds):
        pass

    monkeypatch.setattr(transport, "Client", Client)
    monkeypatch.setattr(probe.asyncio, "sleep", no_wait)
    monkeypatch.setenv("IBKR_ENABLED", "true")
    monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
    args = SimpleNamespace(symbol="AAPL", expiry=expiry, strike=350, days=5, client_id=99)
    report = asyncio.run(probe.probe(args))
    assert report["status"] == "passed" and report["history_requests"] == 3 and report["model_requests"] == 0
    assert calls["connects"] == calls["disconnects"] == 1
    assert [row[:2] for row in calls["history"]] == [("STK", ""), ("OPT", "C"), ("OPT", "P")]
    assert all(row[2:] == ("5 D", "1 hour", "TRADES", True, 2, False, []) for row in calls["history"])
    assert len(report["dataset"]["rows"]) == 2
    assert all(row["open_interest"] is row["oi_asof_date"] is None for row in report["dataset"]["rows"])
    assert report["aggregation"]["partial_bars"] and not report["aggregation"]["native_eod"]
    assert all(item["trading_days_received"] == 1 for item in report["instruments"])
    assert report["dataset"]["bar_basis"] == "derived_from_intraday_trades"
    assert report["actual_coverage"]["C"]["received_hourly_bars"] == 1
