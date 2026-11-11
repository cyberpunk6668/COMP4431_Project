import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import options_ibkr as module
from app.options_ibkr import IBKRConfig, IBKROptionsError, IBKROptionsProvider


def test_bid_ask_time_and_market_type_switch(monkeypatch):
    first = datetime(2026, 11, 11, 14, 30, tzinfo=timezone.utc)
    second = first.replace(second=2)
    times = iter([first, second, second])
    monkeypatch.setattr(module, "_now", lambda: next(times))
    callbacks = module._Callbacks()
    stream = callbacks.streams[1] = module._Ticks()
    callbacks.priceSizeTick(1, 1, 99.0, 3)
    callbacks.priceSizeTick(1, 2, 101.0, 4)
    assert stream.underlying()["market_data_type"] is None
    callbacks.marketDataType(1, 1)
    assert stream.underlying()["price"] == 100
    assert stream.underlying()["received_at"] == first.isoformat()
    callbacks.marketDataType(1, 4)
    assert stream.underlying()["price"] is None
    assert stream.underlying()["delayed_ticks_observed"] is False
    callbacks.priceSizeTick(1, 4, 100, 1)
    assert stream.underlying()["price"] is None
    callbacks.priceSizeTick(1, 68, 98, 1)
    assert stream.underlying()["price"] == 98
    assert stream.underlying()["market_data_type"] == 4
    assert stream.underlying()["delayed_ticks_observed"] is True


def test_unavailable_values_do_not_become_zero_or_valid_greeks():
    callbacks = module._Callbacks()
    stream = callbacks.streams[1] = module._Ticks(100, "P")
    callbacks.marketDataType(1, 1)
    callbacks.tickSize(1, 27, 600)  # Call open interest cannot populate a put.
    callbacks.tickSize(1, 8, 0)  # Explicitly observed zero differs from absent.
    callbacks.tickOptionComputation(1, 13, 0, -1, -2, -1, -1, -2, -2, -2, -1)
    row = stream.option("2026-11-20")
    assert row["volume"] == 0
    assert row["open_interest"] is None
    assert row["implied_volatility"] is None
    assert row["greeks_received_at"] is None
    assert row["quote_received_at"] is None


def test_local_configuration_rejects_remote_hosts(monkeypatch):
    monkeypatch.setenv("IBKR_HOST", "192.0.2.1")
    monkeypatch.setenv("IBKR_ENABLED", "true")
    provider = IBKROptionsProvider()
    assert asyncio.run(provider.status())["status"] == "invalid_config"
    with pytest.raises(IBKROptionsError) as raised:
        asyncio.run(provider.snapshot("AAPL"))
    assert raised.value.code == "ibkr_invalid_config"


def test_disabled_provider_does_not_contact_gateway():
    provider = IBKROptionsProvider(IBKRConfig())
    assert asyncio.run(provider.status())["status"] == "disabled"
    with pytest.raises(IBKROptionsError) as raised:
        asyncio.run(provider.snapshot("BRK B"))
    assert raised.value.code == "ibkr_disabled"


@pytest.mark.parametrize("denied", [False, True])
def test_bounded_snapshot_with_wire_format_chain_id_and_cleanup(monkeypatch, denied):
    transport = pytest.importorskip("ib_async.client")
    calls = {"subscriptions": [], "cancellations": [], "disconnects": 0, "decoded": []}

    class MockClient:
        def __init__(self, callbacks):
            self.callbacks = callbacks
            self.decoder = SimpleNamespace(handlers={2: lambda _fields: None}, interpret=calls["decoded"].append)
            self.req_id = 0

        async def connectAsync(self, host, port, client_id, timeout):
            assert (host, port, client_id, timeout) == ("127.0.0.1", 4002, 67, 3)
            self.decoder.interpret(["61", "unsolicited position callback"])
            self.decoder.interpret(["58", "market data type callback"])

        def getReqId(self):
            self.req_id += 1
            return self.req_id

        def reqContractDetails(self, req_id, stock):
            stock.conId, stock.primaryExchange = 12345, "NASDAQ"
            self.callbacks.contractDetails(req_id, SimpleNamespace(contract=stock))
            self.callbacks.contractDetailsEnd(req_id)

        def reqSecDefOptParams(self, req_id, symbol, exchange, sec_type, con_id):
            assert (symbol, exchange, sec_type, con_id) == ("AAPL", "", "STK", 12345)
            self.callbacks.securityDefinitionOptionParameter(
                req_id, "SMART", "12345", "AAPL", "100", ["20300118"], [float(i) for i in range(90, 120)]
            )
            self.callbacks.securityDefinitionOptionParameterEnd(req_id)

        def reqMarketDataType(self, mode):
            assert mode == 3

        def reqMktData(self, req_id, contract, ticks, snapshot, regulatory, options):
            assert not snapshot and not regulatory and not options
            calls["subscriptions"].append(req_id)
            self.callbacks.marketDataType(req_id, 4)
            if contract.secType == "STK":
                self.callbacks.priceSizeTick(req_id, 66, 100, 1)
                self.callbacks.priceSizeTick(req_id, 67, 102, 1)
            else:
                assert ticks == "101" and contract.multiplier == "100"
                if denied:
                    self.callbacks.error(req_id, 10197, "account-specific broker detail")
                else:
                    self.callbacks.priceSizeTick(req_id, 66, 1, 1)
                    self.callbacks.priceSizeTick(req_id, 67, 1.2, 1)

        def isReady(self):
            return True

        def cancelMktData(self, req_id):
            calls["cancellations"].append(req_id)

        def disconnect(self):
            calls["disconnects"] += 1

    monkeypatch.setattr(transport, "Client", MockClient)
    monkeypatch.setattr(module, "_OBSERVATION_SECONDS", 0)
    provider = IBKROptionsProvider(IBKRConfig(enabled=True, market_data_type=3))
    if denied:
        with pytest.raises(IBKROptionsError) as raised:
            asyncio.run(provider.snapshot("aapl", strike_count=15))
        assert raised.value.code == "ibkr_competing_session"
        assert "account-specific" not in str(raised.value)
    else:
        snapshot = asyncio.run(provider.snapshot("aapl", strike_count=15))
        assert snapshot["source"] == "ibkr"
        assert snapshot["currency"] == "USD"
        assert snapshot["expiration"] == "2030-01-18"
        assert snapshot["underlying"]["price"] == 101
        assert snapshot["requested_market_data_type"] == 3
        assert snapshot["market_data_types"] == [4]
        assert len(snapshot["quotes"]) == 30
        assert snapshot["quotes"][0]["open_interest"] is None
    assert calls["decoded"] == [["58", "market data type callback"]]
    assert len(calls["subscriptions"]) == 31
    assert calls["subscriptions"] == calls["cancellations"]
    assert calls["disconnects"] == 1


def metadata_client(monkeypatch, *, pause=None):
    """Install a broker fixture that permits metadata reads and rejects quotes."""
    transport = pytest.importorskip("ib_async.client")
    calls = {"connects": 0, "disconnects": 0, "chain_requests": 0, "quotes": 0}

    class MetadataClient:
        def __init__(self, callbacks):
            self.callbacks = callbacks
            self.decoder = SimpleNamespace(handlers={2: lambda _fields: None}, interpret=lambda _fields: None)
            self.req_id = 0

        async def connectAsync(self, host, port, client_id, timeout):
            calls["connects"] += 1

        def getReqId(self):
            self.req_id += 1
            return self.req_id

        def reqContractDetails(self, req_id, stock):
            stock.conId, stock.primaryExchange = 12345, "NASDAQ"
            self.callbacks.contractDetails(req_id, SimpleNamespace(contract=stock))
            self.callbacks.contractDetailsEnd(req_id)

        def reqSecDefOptParams(self, req_id, symbol, exchange, sec_type, con_id):
            calls["chain_requests"] += 1

            def complete():
                # Only these dates belong to the standard SMART class. Include
                # non-Friday dates to catch invented weekday-calendar logic.
                self.callbacks.securityDefinitionOptionParameter(
                    req_id, "SMART", str(con_id), symbol, "100",
                    ["20261113", "20261110", "20261111", "20261114", "20261109", "20261113", "2026111", "20261131"],
                    [90.0, 100.0, 110.0],
                )
                for venue, underlying_id, option_class, multiplier in (
                    ("CBOE", str(con_id), symbol, "100"),
                    ("SMART", "99999", symbol, "100"),
                    ("SMART", str(con_id), symbol + "1", "100"),
                    ("SMART", str(con_id), symbol, "10"),
                ):
                    self.callbacks.securityDefinitionOptionParameter(
                        req_id, venue, underlying_id, option_class, multiplier, ["20261112"], [100.0],
                    )
                self.callbacks.securityDefinitionOptionParameterEnd(req_id)

            if pause:
                entered, release = pause
                entered.set()

                async def finish_later():
                    await release.wait()
                    complete()

                asyncio.create_task(finish_later())
            else:
                complete()

        def reqMarketDataType(self, mode):
            raise AssertionError("Metadata discovery must not request a market-data type")

        def reqMktData(self, *args):
            calls["quotes"] += 1
            raise AssertionError("Metadata discovery must not request quotes")

        def isReady(self):
            return True

        def disconnect(self):
            calls["disconnects"] += 1

    monkeypatch.setattr(transport, "Client", MetadataClient)
    monkeypatch.setattr(module, "_now", lambda: datetime(2026, 11, 11, 2, tzinfo=timezone.utc))
    return calls


def test_list_expirations_uses_actual_metadata_and_new_york_calendar(monkeypatch):
    calls = metadata_client(monkeypatch)
    provider = IBKROptionsProvider(IBKRConfig(enabled=True))
    result = asyncio.run(provider.list_expirations(" aapl "))
    assert result == {
        "source": "ibkr", "symbol": "AAPL", "currency": "USD", "trading_class": "AAPL",
        "expirations": ["2026-11-10", "2026-11-11", "2026-11-13", "2026-11-14"],
        "date_kind": "expiration", "timezone": "America/New_York", "as_of": "2026-11-11T02:00:00+00:00",
    }
    assert calls == {"connects": 1, "disconnects": 1, "chain_requests": 1, "quotes": 0}


def test_unsupported_expiry_is_rejected_before_any_market_data(monkeypatch):
    calls = metadata_client(monkeypatch)
    provider = IBKROptionsProvider(IBKRConfig(enabled=True))
    with pytest.raises(IBKROptionsError) as raised:
        asyncio.run(provider.snapshot("AAPL", "2026-11-12"))
    assert raised.value.code == "ibkr_expiration_unavailable"
    assert calls == {"connects": 1, "disconnects": 1, "chain_requests": 1, "quotes": 0}


def test_disabled_expiry_provider_does_not_connect():
    with pytest.raises(IBKROptionsError) as raised:
        asyncio.run(IBKROptionsProvider(IBKRConfig()).list_expirations("AAPL"))
    assert raised.value.code == "ibkr_disabled"


def test_metadata_and_snapshot_share_one_concurrency_limit(monkeypatch):
    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = metadata_client(monkeypatch, pause=(entered, release))
        provider = IBKROptionsProvider(IBKRConfig(enabled=True))
        discovery = asyncio.create_task(provider.list_expirations("AAPL"))
        await entered.wait()
        with pytest.raises(IBKROptionsError) as raised:
            await provider.snapshot("AAPL")
        assert raised.value.code == "ibkr_busy"
        release.set()
        await discovery
        assert calls["connects"] == calls["disconnects"] == 1
        assert calls["quotes"] == 0

    asyncio.run(exercise())
