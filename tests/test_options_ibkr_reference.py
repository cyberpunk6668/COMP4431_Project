"""Replay the installed IB decoder offline, including late close-only streams."""
import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app import options_ibkr as module
from app.options_analytics import analyze_option_snapshot
from app.options_collective import build_collective_analysis
from app.options_ibkr import IBKRConfig, IBKROptionsError, IBKROptionsProvider


def test_close_ticks_are_independent_and_reference_priority_is_explicit():
    decoder_type = pytest.importorskip("ib_async.decoder").Decoder
    callbacks = module._Callbacks()
    underlying = callbacks.streams[1] = module._Ticks()
    option = callbacks.streams[2] = module._Ticks(100, "C")
    decoder = decoder_type(callbacks, 178)
    decoder.interpret(["58", "1", "1", "3"])
    decoder.interpret(["1", "6", "1", "75", "100", "0", "0"])
    quote = underlying.underlying()
    assert quote["price"] == quote["close"] == 100 and quote["price_basis"] == "close"
    assert quote["close_received_at"] == quote["received_at"]
    assert quote["bid"] is quote["ask"] is quote["last"] is quote["quote_received_at"] is quote["last_trade_at"] is None
    decoder.interpret(["1", "6", "1", "68", "101", "0", "0"])
    assert underlying.underlying()["price_basis"] == "last"
    decoder.interpret(["1", "6", "1", "66", "100", "1", "0"])
    decoder.interpret(["1", "6", "1", "67", "104", "1", "0"])
    assert underlying.underlying()["price"] == 102 and underlying.underlying()["price_basis"] == "midpoint"
    assert underlying.underlying()["close"] == 100
    # The non-delayed close tick has the same independent semantics. An explicit
    # zero close is recorded, while it cannot select a stock strike window.
    decoder.interpret(["58", "1", "2", "1"])
    decoder.interpret(["1", "6", "2", "9", "0", "0", "0"])
    row = option.option("2030-01-18")
    assert row["close"] == 0 and row["close_received_at"] is not None
    assert row["bid"] is row["ask"] is row["last"] is row["last_trade_at"] is None
    assert option.underlying()["price"] is None


def virtual_clock(monkeypatch):
    clock, events = [0.0], []
    base = datetime(2026, 11, 11, 5, 42, tzinfo=UTC)

    async def sleep(seconds):
        clock[0] += seconds
        for event in list(events):
            when, callback = event
            if when <= clock[0]:
                events.remove(event)
                callback()

    monkeypatch.setattr(module, "_monotonic", lambda: clock[0])
    monkeypatch.setattr(module, "_now", lambda: base + timedelta(seconds=clock[0]))
    monkeypatch.setattr(module.asyncio, "sleep", sleep)
    return clock, events


def install_wire_gateway(monkeypatch, events, clock, *, absent=False, denied=False, improve_later=False):
    transport = pytest.importorskip("ib_async.client")
    decoder_type = pytest.importorskip("ib_async.decoder").Decoder
    calls = {"modes": [], "subscriptions": [], "cancellations": [], "disconnects": 0}

    class WireClient:
        def __init__(self, callbacks):
            self.callbacks, self.req_id = callbacks, 0
            self.decoder = decoder_type(callbacks, 178)

        async def connectAsync(self, *args, **kwargs):
            pass

        def getReqId(self):
            self.req_id += 1
            return self.req_id

        def reqContractDetails(self, req_id, stock):
            stock.conId, stock.primaryExchange = 123, "NASDAQ"
            self.callbacks.contractDetails(req_id, SimpleNamespace(contract=stock))
            self.callbacks.contractDetailsEnd(req_id)

        def reqSecDefOptParams(self, req_id, *args):
            self.callbacks.securityDefinitionOptionParameter(req_id, "SMART", "123", "AAPL", "100", ["20300118"], [95, 100, 105])
            self.callbacks.securityDefinitionOptionParameterEnd(req_id)

        def reqMarketDataType(self, mode):
            calls["modes"].append(mode)

        def reqMktData(self, req_id, contract, generic, snapshot, regulatory, options):
            assert not snapshot and not regulatory and not options
            calls["subscriptions"].append(req_id)
            # Requested delayed-frozen may legitimately be confirmed as delayed.
            self.decoder.interpret(["58", "1", str(req_id), "3"])
            if contract.secType == "STK":
                self.callbacks.error(req_id, 354 if denied else 10167, "PRIVATE_BROKER_ACCOUNT_STRING")

                def stock_ticks():
                    self.decoder.interpret(["2", "6", str(req_id), "74", "0"])
                    if not absent:
                        self.decoder.interpret(["1", "6", str(req_id), "75", "100", "0", "0"])
                    for tick in (66, 67, 68):
                        self.decoder.interpret(["1", "6", str(req_id), str(tick), "-1", "0", "0"])

                if denied:
                    stock_ticks()
                else:
                    events.append((clock[0] + 5.2, stock_ticks))
                    if improve_later:
                        def last_tick():
                            self.decoder.interpret(["1", "6", str(req_id), "68", "101", "1", "0"])
                        events.append((clock[0] + 6.0, last_tick))
            else:
                assert generic == "101" and contract.multiplier == "100"

                def option_ticks():
                    self.decoder.interpret(["1", "6", str(req_id), "75", "1.5", "0", "0"])
                    self.decoder.interpret(["2", "6", str(req_id), "27" if contract.right == "C" else "28", "100" if contract.right == "C" else "200"])
                    self.decoder.interpret(["21", str(req_id), "83", "0", ".25", ".5" if contract.right == "C" else "-.5", "1.5", "0", ".02", ".1", "-.01", "100"])

                events.append((clock[0] + 7.1, option_ticks))

        def isReady(self):
            return True

        def cancelMktData(self, req_id):
            calls["cancellations"].append(req_id)

        def disconnect(self):
            calls["disconnects"] += 1

    monkeypatch.setattr(transport, "Client", WireClient)
    return calls


def test_late_close_allows_option_collection_but_never_price_sensitive_metrics(monkeypatch):
    clock, events = virtual_clock(monkeypatch)
    calls = install_wire_gateway(monkeypatch, events, clock)
    provider = IBKROptionsProvider(IBKRConfig(enabled=True, market_data_type=4))
    result = asyncio.run(provider.snapshot("AAPL", strike_count=3))
    assert calls["modes"] == [4]  # No implicit fallback request.
    assert result["requested_market_data_type"] == 4 and result["market_data_types"] == [3]
    assert result["underlying"]["price_basis"] == result["strike_selection_basis"] == "close"
    assert result["underlying"]["last_trade_at"] is None
    assert all(row["close"] == 1.5 and row["close_received_at"] is not None for row in result["quotes"])
    assert all(row["bid"] is row["ask"] is row["last"] is None for row in result["quotes"])
    diagnostics = result["diagnostics"]
    assert diagnostics["stage"] == "complete" and diagnostics["reference_basis"] == "close"
    assert diagnostics["data_status"] == "limited_option_fields"
    assert diagnostics["received_market_data_types"] == [3]
    assert diagnostics["entitlement_status"] == "realtime_unsubscribed_delayed_available"
    assert diagnostics["option_contracts_requested"] == diagnostics["option_contracts_with_close"] == diagnostics["option_contracts_with_open_interest"] == 6
    assert diagnostics["option_contracts_with_bid_ask"] == diagnostics["option_contracts_with_last"] == 0
    assert {27, 28, 66, 67, 68, 74, 75, 83} <= set(diagnostics["observed_tick_types"])
    assert 13 <= diagnostics["wait_seconds"] < 15 and diagnostics["interface_status"] == "market_callbacks_received"
    assert diagnostics["underlying_fields"] == ["close"]
    assert "PRIVATE_BROKER" not in str(result) and "account" not in str(diagnostics).lower()
    analysis = analyze_option_snapshot(result, now=module._now())
    assert analysis["quality"]["market_data_status"] == "delayed"
    assert analysis["quality"]["valid_quote_contracts"] == 0 and not analysis["quality"]["llm_eligible"]
    assert analysis["metrics"]["put_call_open_interest"]["value"] == 2
    assert analysis["metrics"]["iv_skew_25_delta"]["value"] is None
    assert analysis["metrics"]["atm_straddle"]["value"] is None
    collective = build_collective_analysis(result, analysis, now=module._now())
    assert collective["volatility"]["atm_iv"] is None and collective["volatility"]["atm_strike"] is None
    assert calls["subscriptions"] == calls["cancellations"] and calls["disconnects"] == 1


def test_strike_reference_basis_is_not_overwritten_by_a_later_last_price(monkeypatch):
    clock, events = virtual_clock(monkeypatch)
    install_wire_gateway(monkeypatch, events, clock, improve_later=True)
    result = asyncio.run(IBKROptionsProvider(IBKRConfig(enabled=True)).snapshot("AAPL", strike_count=3, market_data_type=3))
    assert result["strike_selection_basis"] == "close" and result["strike_selection_price"] == 100
    assert result["underlying"]["price_basis"] == "last" and result["underlying"]["price"] == 101
    assert result["strike_selection_received_at"] < result["underlying"]["received_at"]


@pytest.mark.parametrize("denied,expected", [(False, "ibkr_underlying_unavailable"), (True, "ibkr_entitlement_missing")])
def test_absent_reference_and_hard_denial_have_safe_distinct_diagnostics(monkeypatch, denied, expected):
    clock, events = virtual_clock(monkeypatch)
    calls = install_wire_gateway(monkeypatch, events, clock, absent=not denied, denied=denied)
    with pytest.raises(IBKROptionsError) as raised:
        asyncio.run(IBKROptionsProvider(IBKRConfig(enabled=True)).snapshot("AAPL", market_data_type=3))
    error = raised.value
    assert error.code == expected
    assert error.diagnostics["stage"] == "underlying" and error.diagnostics["option_contracts_requested"] == 0
    assert error.diagnostics["entitlement_status"] == ("explicit_denial" if denied else "realtime_unsubscribed_delayed_available")
    if not denied:
        assert error.diagnostics["wait_seconds"] == 8 and error.diagnostics["data_status"] == "no_reference"
    assert "PRIVATE_BROKER" not in str(error) + str(error.diagnostics)
    assert len(calls["subscriptions"]) == 1 and calls["subscriptions"] == calls["cancellations"]
    assert calls["disconnects"] == 1


def test_close_grace_can_upgrade_to_a_two_sided_reference(monkeypatch):
    clock, events = virtual_clock(monkeypatch)
    callbacks = module._Callbacks()
    stream = callbacks.streams[1] = module._Ticks()
    callbacks.marketDataType(1, 3)
    callbacks.priceSizeTick(1, 75, 100, 0)

    def bbo():
        callbacks.priceSizeTick(1, 66, 100, 1)
        callbacks.priceSizeTick(1, 67, 102, 1)

    events.append((.2, bbo))
    client = SimpleNamespace(isReady=lambda: True)
    reference = asyncio.run(IBKROptionsProvider()._wait_reference(client, callbacks, stream))
    assert reference["price_basis"] == "midpoint" and reference["price"] == 101
    assert clock[0] == .2


def test_diagnostics_do_not_count_zero_bid_as_usable_two_sided_quote(monkeypatch):
    monkeypatch.setattr(module, "_monotonic", lambda: 0)
    callbacks = module._Callbacks()
    underlying = callbacks.streams[1] = module._Ticks()
    option = callbacks.streams[2] = module._Ticks(100, "C")
    callbacks.marketDataType(1, 3)
    callbacks.marketDataType(2, 3)
    callbacks.priceSizeTick(1, 75, 100, 0)
    callbacks.priceSizeTick(2, 66, 0, 1)
    callbacks.priceSizeTick(2, 67, 1, 1)
    assert option.quote_time() is not None  # Diagnostic requirements are stricter.
    diagnostics = IBKROptionsProvider._diagnostics("complete", 3, underlying, [option], callbacks, 0)
    assert diagnostics["option_contracts_with_bid_ask"] == 0
    assert diagnostics["data_status"] == "limited_option_fields"
