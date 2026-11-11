"""Read-only, bounded snapshots over the local IB Gateway TWS API.

Uses ib_async's Client directly to avoid the high-level account/position
synchronization. All *_received_at fields record local callback arrival in
UTC. Only last_trade_at, when supplied by IB, refers to an exchange trade time.
"""
import asyncio
import importlib.util
import math
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


_SYMBOL = re.compile(r"[A-Z][A-Z0-9]*(?:[ .-][A-Z0-9]+)?")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_US_LISTINGS = {
    "AMEX", "ARCA", "BATS", "BX", "CHX", "DRCTEDGE", "EDGEA", "IEX",
    "ISLAND", "LTSE", "MEMX", "NASDAQ", "NMS", "NYSE", "NYSEAMERICAN",
    "NYSEARCA", "NYSENAT", "PEARL", "PHLX", "PSX",
}
_PRICES = {1: "bid", 2: "ask", 4: "last", 9: "close",
           66: "bid", 67: "ask", 68: "last", 75: "close"}
_GREEKS = {10: "bid", 11: "ask", 12: "last", 13: "model",
           80: "bid", 81: "ask", 82: "last", 83: "model"}
_ENTITLEMENTS = {354, 10089, 10167, 10186}
_FATAL = {502, 504, 507, 1100, 1300}
_INFO = {2103, 2104, 2105, 2106, 2107, 2108, 2158}
_GREEK_FIELDS = ("implied_volatility", "delta", "gamma", "vega", "theta")
_UNDERLYING_WAIT_SECONDS = 8.0
_CLOSE_GRACE_SECONDS = .4
_OBSERVATION_SECONDS = 8.0
_SESSION_SECONDS = 30.0
_MARKET_MESSAGES = {"1", "2", "4", "10", "21", "46", "52", "58", "75", "76"}


class IBKROptionsError(RuntimeError):
    """Application-safe error. Broker strings may include account identifiers."""

    def __init__(self, code: str, message: str, *, available_expirations: list[str] | None = None,
                 diagnostics: dict | None = None):
        super().__init__(message)
        self.code = code
        self.available_expirations = available_expirations
        self.diagnostics = diagnostics


@dataclass(frozen=True, slots=True)
class IBKRConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 4002
    client_id: int = 67
    market_data_type: int = 1

    def __post_init__(self):
        if self.host == "localhost":
            object.__setattr__(self, "host", "127.0.0.1")
        if (self.host not in {"127.0.0.1", "::1"} or not 1 <= self.port <= 65535
                or not 1 <= self.client_id <= 2**31 - 1 or self.market_data_type not in {1, 2, 3, 4}):
            raise ValueError("Invalid local IBKR configuration")

    @classmethod
    def from_env(cls):
        return cls(
            enabled=os.getenv("IBKR_ENABLED", "false").strip().lower() in {"1", "true", "yes"},
            host=os.getenv("IBKR_HOST", "127.0.0.1").strip().lower(),
            port=int(os.getenv("IBKR_PORT", "4002")),
            client_id=int(os.getenv("IBKR_CLIENT_ID", "67")),
            market_data_type=int(os.getenv("IBKR_MARKET_DATA_TYPE", "1")),
        )


def _now():
    return datetime.now(timezone.utc)


def _iso(value):
    return value.isoformat() if value is not None else None


def _monotonic():
    return asyncio.get_running_loop().time()


def _number(value, lower=-1e10, upper=1e10):
    if isinstance(value, (int, float)) and math.isfinite(value) and lower <= value <= upper:
        return float(value)
    return None


def _iso_expiration(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{8}", value):
        raise ValueError("Invalid broker expiration date")
    return datetime.strptime(value, "%Y%m%d").date().isoformat()


def _ticker_key(symbol):
    return re.sub(r"[ .-]", "", symbol)


@dataclass
class _Ticks:
    strike: float | None = None
    right: str | None = None
    mode: int | None = None
    family: bool | None = None
    values: dict[str, float] = field(default_factory=dict)
    times: dict[str, datetime] = field(default_factory=dict)
    greeks: dict[str, tuple[dict[str, float | None], datetime]] = field(default_factory=dict)
    codes: set[int] = field(default_factory=set)
    last_trade_at: datetime | None = None
    delayed_ticks_observed: bool = False
    observed_tick_types: set[int] = field(default_factory=set)
    received_modes: set[int] = field(default_factory=set)

    def set_mode(self, mode):
        if mode not in {1, 2, 3, 4}:
            return
        self.received_modes.add(mode)
        expected_family = mode in {3, 4}
        if ((self.mode is not None and self.mode != mode)
                or (self.family is not None and self.family != expected_family)):
            self.values.clear()
            self.times.clear()
            self.greeks.clear()
            self.last_trade_at = None
            self.delayed_ticks_observed = False
        self.mode = mode
        self.family = expected_family

    def accepts(self, delayed):
        if self.family is not None and self.family != delayed:
            return False
        self.family = delayed
        self.delayed_ticks_observed |= delayed
        return True

    def record(self, name, value):
        if value is None:
            self.values.pop(name, None)
            self.times.pop(name, None)
            return
        self.values[name] = value
        self.times[name] = _now()

    def quote_time(self):
        bid, ask = self.values.get("bid"), self.values.get("ask")
        if bid is not None and ask is not None and 0 < ask and bid <= ask:
            return min(self.times["bid"], self.times["ask"])
        return None

    def underlying(self):
        bid, ask, last = (self.values.get(key) for key in ("bid", "ask", "last"))
        quote_time = self.quote_time()
        if quote_time and bid and ask:
            price, basis, received_at = (bid + ask) / 2, "midpoint", quote_time
        else:
            price, basis, received_at = last, ("last" if last else None), self.times.get("last")
            close = self.values.get("close")
            if price is None and close is not None and close > 0:
                price, basis, received_at = close, "close", self.times.get("close")
        return {
            "price": price, "price_basis": basis, "bid": bid, "ask": ask, "last": last,
            "close": self.values.get("close"), "close_received_at": _iso(self.times.get("close")),
            "received_at": _iso(received_at), "quote_received_at": _iso(quote_time),
            "last_trade_at": _iso(self.last_trade_at), "market_data_type": self.mode,
            "delayed_ticks_observed": self.delayed_ticks_observed,
        }

    def option(self, expiry):
        basis = next((kind for kind in ("model", "bid", "ask", "last")
                      if kind in self.greeks and self.greeks[kind][0]["implied_volatility"] is not None), None)
        if basis is None:
            basis = next((kind for kind in ("model", "bid", "ask", "last") if kind in self.greeks), None)
        values, greek_at = self.greeks.get(basis, (dict.fromkeys(_GREEK_FIELDS), None))
        received_at = max([*self.times.values(), *([greek_at] if greek_at else [])], default=None)
        return {
            "strike": self.strike, "right": self.right, "expiration": expiry,
            **{key: self.values.get(key) for key in ("bid", "ask", "last", "close", "volume", "open_interest")},
            "close_received_at": _iso(self.times.get("close")),
            **values, "greeks_basis": basis, "market_data_type": self.mode,
            "received_at": _iso(received_at), "quote_received_at": _iso(self.quote_time()),
            "greeks_received_at": _iso(greek_at), "volume_received_at": _iso(self.times.get("volume")),
            "open_interest_received_at": _iso(self.times.get("open_interest")),
            "last_trade_at": _iso(self.last_trade_at), "delayed_ticks_observed": self.delayed_ticks_observed,
            "broker_codes": sorted(self.codes),
        }


class _Rejected(Exception):
    def __init__(self, code):
        self.code = code


class _Callbacks:
    """Only the broker callbacks relevant to contract metadata and market data."""

    def __init__(self):
        self.pending: dict[int, tuple[asyncio.Future, list]] = {}
        self.streams: dict[int, _Ticks] = {}
        self.global_codes: set[int] = set()

    def connectAck(self):
        pass

    def setEventsDone(self):
        for future, _ in self.pending.values():
            if not future.done():
                future.set_exception(_Rejected(504))

    def connectionClosed(self):
        self.setEventsDone()

    def error(self, req_id, code, _message, _advanced=""):
        if req_id < 0:
            self.global_codes.add(code)
            if code in _FATAL:
                for future, _ in self.pending.values():
                    if not future.done():
                        future.set_exception(_Rejected(code))
        if req_id in self.streams:
            self.streams[req_id].codes.add(code)
        if req_id in self.pending and code not in _INFO:
            future, _ = self.pending[req_id]
            if not future.done():
                future.set_exception(_Rejected(code))

    async def request(self, client, method, *args):
        req_id = client.getReqId()
        future = asyncio.get_running_loop().create_future()
        self.pending[req_id] = (future, [])
        try:
            method(req_id, *args)
            return await asyncio.wait_for(future, timeout=4.0)
        finally:
            self.pending.pop(req_id, None)
            if not future.done():
                future.cancel()

    def _append(self, req_id, row):
        if req_id in self.pending:
            self.pending[req_id][1].append(row)

    def contractDetails(self, req_id, detail):
        self._append(req_id, detail)

    def contractDetailsEnd(self, req_id):
        if req_id in self.pending:
            future, rows = self.pending[req_id]
            if not future.done():
                future.set_result(rows)

    def securityDefinitionOptionParameter(self, req_id, exchange, con_id, trading_class,
                                          multiplier, expirations, strikes):
        # ib_async 2.1.0 leaves the wire-format underlying ID as text.
        try:
            underlying_id = int(con_id)
        except (TypeError, ValueError):
            return
        self._append(req_id, (exchange, underlying_id, trading_class, multiplier, expirations, strikes))

    def securityDefinitionOptionParameterEnd(self, req_id):
        self.contractDetailsEnd(req_id)

    def marketDataType(self, req_id, mode):
        if req_id in self.streams:
            self.streams[req_id].set_mode(mode)

    def priceSizeTick(self, req_id, tick_type, price, _size):
        stream = self.streams.get(req_id)
        if stream is None:
            return
        stream.observed_tick_types.add(tick_type)
        if tick_type not in _PRICES or not stream.accepts(tick_type >= 66):
            return
        key = _PRICES[tick_type]
        stream.record(key, _number(price, 0.00000001 if key == "last" else 0))

    def tickSize(self, req_id, tick_type, size):
        stream = self.streams.get(req_id)
        if stream is None:
            return
        stream.observed_tick_types.add(tick_type)
        if stream.right is None:
            return
        if tick_type in {8, 74} and stream.accepts(tick_type == 74):
            stream.record("volume", _number(size, 0))
        elif tick_type == (27 if stream.right == "C" else 28):
            stream.record("open_interest", _number(size, 0))

    def tickString(self, req_id, tick_type, value):
        stream = self.streams.get(req_id)
        if stream is None:
            return
        stream.observed_tick_types.add(tick_type)
        if tick_type not in {45, 88} or not stream.accepts(tick_type == 88):
            return
        try:
            timestamp = datetime.fromtimestamp(int(value), timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError):
            return
        if 1970 < timestamp.year <= _now().year:
            stream.last_trade_at = timestamp

    def tickOptionComputation(self, req_id, tick_type, _attrib, iv, delta, _price,
                              _dividend, gamma, vega, theta, _underlying):
        stream = self.streams.get(req_id)
        if stream is None:
            return
        stream.observed_tick_types.add(tick_type)
        if tick_type not in _GREEKS or not stream.accepts(tick_type >= 80):
            return
        values = {
            "implied_volatility": _number(iv, 0.00000001),
            "delta": _number(delta, -1, 1),
            "gamma": _number(gamma, 0),
            "vega": _number(vega, 0),
            "theta": _number(theta) if theta != -2 else None,
        }
        basis = _GREEKS[tick_type]
        if any(value is not None for value in values.values()):
            stream.greeks[basis] = (values, _now())
        else:
            stream.greeks.pop(basis, None)


def _validate(symbol, expiration, strike_count, mode):
    symbol = symbol.strip().upper() if isinstance(symbol, str) else ""
    if len(symbol) > 12 or not _SYMBOL.fullmatch(symbol) or type(strike_count) is not int or not 1 <= strike_count <= 15:
        raise IBKROptionsError("ibkr_invalid_request", "Use a US stock/ETF ticker and 1 to 15 strikes.")
    if type(mode) is not int or mode not in {1, 2, 3, 4}:
        raise IBKROptionsError("ibkr_invalid_request", "Use IBKR market-data type 1, 2, 3 or 4.")
    if expiration is not None:
        try:
            if not isinstance(expiration, str) or not _DATE.fullmatch(expiration):
                raise ValueError
            date.fromisoformat(expiration)
        except ValueError:
            raise IBKROptionsError("ibkr_invalid_request", "Expiration must be YYYY-MM-DD.") from None
    return symbol


def _select_chain(chains, symbol, con_id, expiration, today):
    eligible = [
        row for row in chains if row[:2] == ("SMART", con_id)
        and _ticker_key(row[2]) == _ticker_key(symbol) and str(row[3]) == "100"
    ]
    trading_classes = {row[2] for row in eligible}
    if symbol in trading_classes:
        trading_class = symbol
    elif len(trading_classes) == 1:
        trading_class = next(iter(trading_classes))
    else:
        raise IBKROptionsError("ibkr_chain_unavailable", "IB Gateway did not return a standard SMART 100-share option chain.")
    available: dict[str, set[float]] = {}
    for _, _, chain_class, _, expirations, strikes in eligible:
        if chain_class != trading_class:
            continue
        valid_strikes = {strike for raw in strikes if (strike := _number(raw, 0.000001)) is not None}
        for raw_expiry in expirations:
            try:
                expiry = _iso_expiration(raw_expiry)
            except (TypeError, ValueError):
                continue
            if expiry >= today and valid_strikes:
                available.setdefault(expiry, set()).update(valid_strikes)
    expirations = sorted(available)
    expiry = expiration or (expirations[0] if expirations else None)
    if expiry not in available:
        raise IBKROptionsError("ibkr_expiration_unavailable", "Requested expiration is not available in the standard SMART chain.", available_expirations=expirations)
    return expiry, sorted(available[expiry]), expirations, trading_class


def _window(strikes, price, count):
    center = min(range(len(strikes)), key=lambda index: abs(strikes[index] - price))
    start = max(0, min(center - count // 2, len(strikes) - count))
    return strikes[start:start + count]


def _raise_no_ticks(codes, otherwise, requested_mode=None):
    if 10197 in codes:
        raise IBKROptionsError("ibkr_competing_session", "IBKR reports another session using this account's market data.")
    if 101 in codes:
        raise IBKROptionsError("ibkr_line_limit", "IBKR reported that available market-data lines were exhausted.")
    # 10167 announces an available delayed-data fallback, not a denial of the
    # explicitly requested delayed feed. Absence of usable ticks in that case
    # remains a data-availability failure, not proof that delayed access failed.
    if codes & (_ENTITLEMENTS - {10167}) or (10167 in codes and requested_mode in {1, 2}):
        raise IBKROptionsError("ibkr_entitlement_missing", "IBKR did not provide the requested data entitlement. Check stock and US option subscriptions or request delayed data explicitly.")
    raise otherwise


class IBKROptionsProvider:
    """One snapshot at a time. Live and delayed request modes are explicit."""

    def __init__(self, config: IBKRConfig | None = None):
        self._invalid_config = False
        try:
            self.config = config if config is not None else IBKRConfig.from_env()
        except ValueError:
            self.config = IBKRConfig()
            self._invalid_config = True
        self._lock = asyncio.Lock()

    async def status(self):
        config = self.config
        installed = importlib.util.find_spec("ib_async") is not None
        reachable = False
        if config.enabled:
            try:
                _, writer = await asyncio.wait_for(asyncio.open_connection(config.host, config.port), timeout=.8)
                writer.close()
                reachable = True
                await asyncio.wait_for(writer.wait_closed(), timeout=.4)
            except (OSError, TimeoutError):
                pass
        state = "tcp_ready" if reachable else "gateway_unreachable"
        if not installed:
            state = "dependency_missing"
        if not config.enabled:
            state = "disabled"
        if self._invalid_config:
            state = "invalid_config"
        host = f"[{config.host}]" if ":" in config.host else config.host
        return {"provider": "ibkr", "enabled": config.enabled, "dependency_installed": installed,
                "endpoint": f"{host}:{config.port}", "tcp_reachable": reachable,
                "requested_market_data_type": config.market_data_type, "status": state}

    async def snapshot(self, symbol: str, expiration: str | None = None,
                       strike_count: int = 9, market_data_type: int | None = None):
        config = self.config
        mode = config.market_data_type if market_data_type is None else market_data_type
        symbol = _validate(symbol, expiration, strike_count, mode)
        async with self._session() as (client, callbacks, Stock, Option, subscriptions, started_at):
            result = await self._collect(client, callbacks, Stock, Option, subscriptions,
                                         symbol, expiration, strike_count, mode)
            return {"source": "ibkr", "symbol": symbol, "currency": "USD",
                    "started_at": _iso(started_at), "received_at": _iso(_now()),
                    "requested_market_data_type": mode, **result}

    async def list_expirations(self, symbol: str) -> dict:
        """Return IBKR-listed expirations for the qualified standard option class.

        This discovers contract metadata only. It does not subscribe to stock or
        option quotes and does not infer dates from a weekday or holiday rule.
        """
        symbol = _validate(symbol, None, 1, self.config.market_data_type)
        async with self._session() as (client, callbacks, Stock, _Option, _subscriptions, _started_at):
            _stock, _expiry, _strikes, expirations, trading_class = await self._discover_chain(
                client, callbacks, Stock, symbol,
            )
            return {"source": "ibkr", "symbol": symbol, "expirations": expirations,
                    "trading_class": trading_class, "currency": "USD",
                    "date_kind": "expiration", "timezone": "America/New_York",
                    "as_of": _iso(_now())}

    @asynccontextmanager
    async def _session(self):
        """Share connection, pacing, error handling and cleanup across reads."""
        config = self.config
        if self._invalid_config:
            raise IBKROptionsError("ibkr_invalid_config", "Configure a loopback IB Gateway endpoint and a positive client ID.")
        if not config.enabled:
            raise IBKROptionsError("ibkr_disabled", "Enable the server-side IBKR configuration to use the local gateway.")
        try:
            from ib_async import Option, Stock
            from ib_async.client import Client
        except ImportError:
            raise IBKROptionsError("ibkr_dependency_missing", "Install requirements-options.txt in the backend environment.") from None
        if self._lock.locked():
            raise IBKROptionsError("ibkr_busy", "An IBKR snapshot is already running.")
        async with self._lock:
            callbacks = _Callbacks()
            client = Client(callbacks)
            client.MaxRequests = 35
            # Client consumes nextValidId and managedAccounts itself for the
            # handshake. Discard unrelated, unsolicited callback payloads.
            decode = client.decoder.interpret

            def decode_market_message(fields):
                if fields and fields[0] in _MARKET_MESSAGES:
                    decode(fields)

            client.decoder.interpret = decode_market_message
            # Decoder 2.1.0 otherwise maps an empty size payload to numeric zero.
            decode_size = client.decoder.handlers[2]

            def decode_present_size(fields):
                if len(fields) >= 5 and fields[4]:
                    decode_size(fields)

            client.decoder.handlers[2] = decode_present_size
            subscriptions = []
            started_at = _now()
            try:
                async with asyncio.timeout(_SESSION_SECONDS):
                    try:
                        await client.connectAsync(config.host, config.port, config.client_id, timeout=3)
                    except (OSError, TimeoutError):
                        self._raise_connection(callbacks)
                    yield client, callbacks, Stock, Option, subscriptions, started_at
            except TimeoutError:
                raise IBKROptionsError("ibkr_timeout", "IB Gateway did not finish the market-data request in time.") from None
            except _Rejected as error:
                if error.code == 200:
                    raise IBKROptionsError("ibkr_contract_not_found", "IBKR could not identify the requested US stock/ETF.") from None
                self._raise_connection(callbacks)
            except OSError:
                self._raise_connection(callbacks)
            finally:
                try:
                    if client.isReady():
                        for req_id in subscriptions:
                            client.cancelMktData(req_id)
                finally:
                    client.disconnect()

    @staticmethod
    def _raise_connection(callbacks):
        if 326 in callbacks.global_codes:
            raise IBKROptionsError("ibkr_client_id_conflict", "The IBKR API client ID is already in use.") from None
        raise IBKROptionsError("ibkr_connection_failed", "IB Gateway did not complete or maintain the API connection.") from None

    async def _discover_chain(self, client, callbacks, Stock, symbol, expiration=None):
        try:
            details = await callbacks.request(client, client.reqContractDetails, Stock(symbol, "SMART", "USD"))
        except _Rejected as error:
            spaced = re.sub(r"[.-]", " ", symbol)
            if spaced == symbol or error.code != 200:
                raise
            details = await callbacks.request(client, client.reqContractDetails, Stock(spaced, "SMART", "USD"))
        candidates = {
            row.contract.conId: row.contract for row in details
            if row.contract.secType == "STK" and row.contract.currency == "USD"
            and row.contract.primaryExchange.split(".")[0] in _US_LISTINGS and row.contract.conId > 0
            and _ticker_key(row.contract.symbol) == _ticker_key(symbol)
        }
        if len(candidates) != 1:
            raise IBKROptionsError("ibkr_contract_not_found", "The ticker did not resolve to one US stock/ETF listing.")
        stock = next(iter(candidates.values()))
        stock.exchange = "SMART"
        chains = await callbacks.request(client, client.reqSecDefOptParams, stock.symbol, "", "STK", stock.conId)
        today = _now().astimezone(ZoneInfo("America/New_York")).date().isoformat()
        expiry, strikes, expirations, trading_class = _select_chain(chains, stock.symbol, stock.conId, expiration, today)
        return stock, expiry, strikes, expirations, trading_class

    async def _wait_reference(self, client, callbacks, underlying):
        deadline, close_seen = _monotonic() + _UNDERLYING_WAIT_SECONDS, None
        while True:
            reference = underlying.underlying()
            elapsed = _monotonic()
            if underlying.codes & ((_ENTITLEMENTS - {10167}) | {10197, 101}):
                return reference
            if reference["price"] is not None:
                if reference["price_basis"] != "close":
                    return reference
                # A close is sufficient only for selecting a strike window.
                # Allow a short, bounded chance for last/BBO from the same burst.
                if close_seen is None:
                    close_seen = elapsed
                if elapsed - close_seen >= _CLOSE_GRACE_SECONDS:
                    return reference
            if not client.isReady():
                self._raise_connection(callbacks)
            remaining = deadline - elapsed
            if remaining <= 0:
                return reference
            await asyncio.sleep(min(.1, remaining))

    @staticmethod
    def _diagnostics(stage, mode, underlying, streams, callbacks, started):
        """Allowlisted structural facts, without prices, broker strings or IDs."""
        all_streams = [underlying, *streams]
        codes = set(callbacks.global_codes).union(*(item.codes for item in all_streams))
        received_modes = set().union(*(item.received_modes for item in all_streams))
        tick_types = set().union(*(item.observed_tick_types for item in all_streams))
        observed = bool(received_modes or tick_types)
        entitlement = "unconfirmed"
        if codes & (_ENTITLEMENTS - {10167}):
            entitlement = "explicit_denial"
        elif 10167 in codes:
            entitlement = "realtime_unsubscribed_delayed_available"
        elif observed:
            entitlement = "no_denial_observed"
        reference = underlying.underlying()
        basis = reference["price_basis"]
        bbo = sum(item.quote_time() is not None and item.values.get("bid", 0) > 0
                  and item.values.get("ask", 0) > 0 for item in streams)
        if streams:
            data_status = "two_sided_quotes" if bbo else "limited_option_fields"
        else:
            data_status = {"midpoint": "two_sided_quotes", "last": "last_reference",
                           "close": "close_reference"}.get(basis, "no_reference")
        return {
            "stage": stage, "requested_market_data_type": mode,
            "received_market_data_types": sorted(received_modes),
            "entitlement_status": entitlement, "data_status": data_status,
            "broker_codes": sorted(codes), "reference_basis": basis,
            "underlying_fields": sorted(key for key in ("bid", "ask", "last", "close") if key in underlying.values),
            "option_contracts_requested": len(streams), "option_contracts_with_bid_ask": bbo,
            "option_contracts_with_last": sum("last" in item.values for item in streams),
            "option_contracts_with_close": sum("close" in item.values for item in streams),
            "option_contracts_with_open_interest": sum("open_interest" in item.values for item in streams),
            "observed_tick_types": sorted(tick_types), "wait_seconds": round(max(0, _monotonic() - started), 3),
            "timestamp_basis": "local_callback_arrival",
            "interface_status": "market_callbacks_received" if observed else "no_market_callbacks",
        }

    async def _collect(self, client, callbacks, Stock, Option, subscriptions, symbol,
                       expiration, count, mode):
        # Validate the expiry against broker metadata before requesting any
        # market data, including the underlying reference quote.
        stock, expiry, strikes, expirations, trading_class = await self._discover_chain(
            client, callbacks, Stock, symbol, expiration,
        )
        client.reqMarketDataType(mode)

        def subscribe(contract, ticks, generic=""):
            req_id = client.getReqId()
            callbacks.streams[req_id] = ticks
            subscriptions.append(req_id)
            client.reqMktData(req_id, contract, generic, False, False, [])
            return ticks

        underlying = subscribe(stock, _Ticks())
        streams, stage, started = [], "underlying", _monotonic()
        try:
            reference = await self._wait_reference(client, callbacks, underlying)
            if reference["price"] is None or underlying.codes & ((_ENTITLEMENTS - {10167}) | {10197, 101}):
                _raise_no_ticks(underlying.codes, IBKROptionsError("ibkr_underlying_unavailable", "No underlying bid/ask midpoint, last or close reference was received."), mode)
            selected = _window(strikes, reference["price"], count)
            # The chain metadata contains separate expiry and strike sets. A fully
            # specified subscription can still reject a missing combination (200).
            stage = "options"
            for strike in selected:
                for right in ("C", "P"):
                    contract = Option(stock.symbol, expiry.replace("-", ""), strike, right, "SMART",
                                      multiplier="100", currency="USD", tradingClass=trading_class)
                    streams.append(subscribe(contract, _Ticks(strike, right), "101"))
            await asyncio.sleep(_OBSERVATION_SECONDS)
            if not client.isReady() or callbacks.global_codes & _FATAL:
                self._raise_connection(callbacks)
            quotes = [ticks.option(expiry) for ticks in streams]
            broker_codes = set().union(*(ticks.codes for ticks in streams))
            if not any(quote["received_at"] for quote in quotes):
                _raise_no_ticks(broker_codes, IBKROptionsError("ibkr_option_data_unavailable", "No requested option quote or metric was returned."), mode)
            return {
                "expiration": expiry, "available_expirations": expirations[:30],
                "underlying": underlying.underlying(), "strike_selection_price": reference["price"],
                "strike_selection_basis": reference["price_basis"],
                "strike_selection_received_at": reference["received_at"],
                "requested_strikes": selected, "quotes": quotes,
                "trading_class": trading_class, "multiplier": 100, "exchange": "SMART",
                "broker_codes": sorted(broker_codes | underlying.codes),
                "market_data_types": sorted({quote["market_data_type"] for quote in quotes
                                             if quote["market_data_type"] is not None}),
                "timestamp_basis": "local_callback_arrival",
                "diagnostics": self._diagnostics("complete", mode, underlying, streams, callbacks, started),
            }
        except IBKROptionsError as error:
            error.diagnostics = self._diagnostics(stage, mode, underlying, streams, callbacks, started)
            raise
