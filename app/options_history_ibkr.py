"""Bounded, read-only historical stock/option bars over the local IB Gateway.

No model, account synchronization, streaming quote or order requests. Observed
intraday trades are aggregated by New York date with explicit coverage limits.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
import math
import re
from zoneinfo import ZoneInfo

from app.options_ibkr import IBKRConfig, IBKROptionsError, _SYMBOL

NY = ZoneInfo("America/New_York")
MAX_HISTORY_REQUESTS = 3
MAX_BARS_PER_REQUEST = 256
HISTORY_TIMEOUT = 20
TOTAL_TIMEOUT = 90
HISTORY_MESSAGES = {"4", "10", "17", "52", "75", "76"}
SOURCES = [
    "https://www.interactivebrokers.com/docs/tws-api/doc/md/historical-bars",
    "https://www.interactivebrokers.com/docs/tws-api/doc/md/market-data-limitations",
]


def number(value, *, nonnegative=True):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) >= 1e100:
        return None
    return value if not nonnegative or value >= 0 else None


def error_category(code, message):
    """Retain an enum only: broker error strings can contain private identifiers."""
    text = str(message).lower()
    if code in {354, 10089, 10186, 10187} or "permission" in text or "not subscribed" in text:
        return "permission_or_subscription"
    if "pacing" in text:
        return "pacing"
    if "eodchart" in text:
        return "unsupported_eod"
    if "no data" in text:
        return "no_historical_data"
    if code == 200:
        return "contract_unavailable"
    return "request_error"


def completed_window(days, now=None):
    now = now or datetime.now(UTC)
    end = datetime.combine(now.astimezone(NY).date(), time(), NY)
    start = end - timedelta(days=days)
    return start.astimezone(UTC), end.astimezone(UTC)


def normalize_bar(bar):
    raw = bar.date
    if isinstance(raw, datetime):
        if raw.utcoffset() is None:
            raise ValueError("Naive historical timestamp")
        stamp = raw.astimezone(UTC)
    elif isinstance(raw, str) and re.fullmatch(r"[0-9]{9,12}", raw):
        stamp = datetime.fromtimestamp(int(raw), UTC)
    else:
        raise ValueError("Hourly formatDate=2 requires an epoch timestamp")
    prices = {field: number(getattr(bar, field, None)) for field in ("open", "high", "low", "close")}
    if any(value is None for value in prices.values()):
        raise ValueError("Invalid historical OHLC")
    if not prices["low"] <= min(prices["open"], prices["close"]) <= max(prices["open"], prices["close"]) <= prices["high"]:
        raise ValueError("Inconsistent historical OHLC")
    return {"at": stamp.isoformat(), "trading_date": stamp.astimezone(NY).date().isoformat(),
            **prices, "volume": number(getattr(bar, "volume", None)),
            "wap": number(getattr(bar, "average", None)), "bar_count": number(getattr(bar, "barCount", None))}


def aggregate_days(bars, *, strike=None, right=None):
    """Aggregate observed bars only; do not fill missing dates/bars or infer OI."""
    groups = defaultdict(list)
    seen = {}
    for bar in bars:
        if bar["at"] in seen:
            if seen[bar["at"]] != bar:
                raise ValueError("Conflicting historical bars at one timestamp")
            continue
        seen[bar["at"]] = bar
        groups[bar["trading_date"]].append(bar)
    rows, provenance = [], []
    for day, entries in sorted(groups.items()):
        entries.sort(key=lambda item: item["at"])
        volumes = [entry["volume"] for entry in entries]
        row = {"trading_date": day, "open": entries[0]["open"], "high": max(item["high"] for item in entries),
               "low": min(item["low"] for item in entries), "close": entries[-1]["close"],
               "volume": sum(volumes) if all(value is not None for value in volumes) else None}
        if right is not None:
            row.update(strike=strike, right=right, open_interest=None, oi_asof_date=None)
        rows.append(row)
        provenance.append({"trading_date": day, "right": right, "observed_hourly_bars": len(entries),
                           "first_bar_at": entries[0]["at"], "last_bar_at": entries[-1]["at"],
                           "derived_daily": True, "partial_bars": True, "full_session_verified": False})
    return rows, provenance


def make_callbacks():
    from app.options_ibkr import _Callbacks, _INFO

    class HistoryCallbacks(_Callbacks):
        def __init__(self):
            super().__init__()
            self.codes = defaultdict(set)
            self.categories = defaultdict(set)
            self.last_history_request_id = None

        def error(self, req_id, code, message, advanced=""):
            self.codes[req_id].add(code)
            if code not in _INFO | {2119}:
                self.categories[req_id].add(error_category(code, message))
            super().error(req_id, code, message, advanced)

        def historicalData(self, req_id, bar):
            if req_id in self.pending:
                future, rows = self.pending[req_id]
                if len(rows) >= MAX_BARS_PER_REQUEST:
                    if not future.done():
                        future.set_exception(ValueError("historical_bar_limit"))
                else:
                    rows.append(bar)

        def historicalDataEnd(self, req_id, _start, _end):
            self.contractDetailsEnd(req_id)

    return HistoryCallbacks()


async def request_history(client, callbacks, contract, end, days):
    req_id = client.getReqId()
    callbacks.last_history_request_id = req_id
    future = asyncio.get_running_loop().create_future()
    callbacks.pending[req_id] = (future, [])
    completed = False
    try:
        client.reqHistoricalData(req_id, contract, end.strftime("%Y%m%d-%H:%M:%S"), f"{days} D",
                                 "1 hour", "TRADES", True, 2, False, [])
        result = await asyncio.wait_for(future, HISTORY_TIMEOUT)
        completed = True
        return result, req_id
    finally:
        callbacks.pending.pop(req_id, None)
        if not completed and client.isReady():
            client.cancelHistoricalData(req_id)
        if not future.done():
            future.cancel()


async def _fetch_report(config, symbol, expiry, strike, days):
    from ib_async import Option, Stock
    from ib_async.client import Client
    from app.options_ibkr import _Rejected, _select_chain, _ticker_key, _US_LISTINGS

    client_id = config.client_id
    start, end = completed_window(days)
    today = datetime.now(UTC).astimezone(NY).date()
    if date.fromisoformat(expiry) < today:
        raise IBKROptionsError("ibkr_historical_expired_option", "Expired options are not supported by this probe")
    report = {
        "checked_at": datetime.now(UTC).isoformat(), "status": "running", "stage": "connect",
        "scope": "Actual IBKR metadata plus at most three sequential historical TRADES requests; no streaming quotes, account/order requests or models.",
        "request": {"symbol": symbol, "expiry": expiry, "strike": strike, "calendar_days": days,
                    "end_exclusive_utc": end.isoformat(), "start_inclusive_utc": start.isoformat(),
                    "bar_size": "1 hour", "what_to_show": "TRADES", "use_rth": True, "keep_up_to_date": False},
        "aggregation": {"kind": "derived_daily", "native_eod": False, "partial_bars": True,
                        "full_session_verified": False, "timezone": "America/New_York"},
        "unavailable_fields": ["historical_open_interest", "historical_option_greeks", "per_contract_historical_iv", "trade_aggressor_side"],
        "limits": ["Options EOD and expired-option history are not supported by IBKR's published limitations.",
                   "Calendar-day lookback may return fewer trading dates; no gaps are filled and no zero activity is invented.",
                   "Locally aggregated observed hourly bars are not official daily settlement or proof of complete RTH coverage.",
                   "Historical availability/permissions must be tested separately; delayed watchlist access does not prove historical access.",
                   "Historical volume can differ from streaming volume because IBKR filters historical trades."],
        "sources": SOURCES, "history_requests": 0, "model_requests": 0, "instruments": [],
        "capability_only": True,
    }
    callbacks = make_callbacks()
    client = Client(callbacks)
    client.MaxRequests = 20
    decode = client.decoder.interpret
    client.decoder.interpret = lambda fields: decode(fields) if fields and fields[0] in HISTORY_MESSAGES else None
    try:
        async with asyncio.timeout(TOTAL_TIMEOUT):
            await client.connectAsync(config.host, config.port, client_id, timeout=3)
            report["stage"] = "qualify_contracts"
            details = await callbacks.request(client, client.reqContractDetails, Stock(symbol, "SMART", "USD"))
            stocks = {item.contract.conId: item.contract for item in details
                      if item.contract.secType == "STK" and item.contract.currency == "USD"
                      and item.contract.primaryExchange.split(".")[0] in _US_LISTINGS
                      and _ticker_key(item.contract.symbol) == _ticker_key(symbol) and item.contract.conId > 0}
            if len(stocks) != 1:
                raise IBKROptionsError("ibkr_contract_not_found", "The US stock could not be qualified uniquely")
            stock = next(iter(stocks.values()))
            stock.exchange = "SMART"
            chains = await callbacks.request(client, client.reqSecDefOptParams, stock.symbol, "", "STK", stock.conId)
            expiry, strikes, _expiries, trading_class = _select_chain(chains, stock.symbol, stock.conId, expiry, today.isoformat())
            if strike not in strikes:
                raise IBKROptionsError("ibkr_invalid_request", "The fixed strike is not in the standard chain metadata")
            contracts = [("stock", stock)]
            for right in ("C", "P"):
                query = Option(stock.symbol, expiry.replace("-", ""), strike, right, "SMART",
                               multiplier="100", currency="USD", tradingClass=trading_class)
                candidates = await callbacks.request(client, client.reqContractDetails, query)
                matches = {item.contract.conId: item.contract for item in candidates
                           if item.contract.secType == "OPT" and item.contract.currency == "USD" and str(item.contract.multiplier) == "100"
                           and _ticker_key(item.contract.symbol) == _ticker_key(stock.symbol)
                           and item.contract.right == right and item.contract.strike == strike
                           and item.contract.lastTradeDateOrContractMonth[:8] == expiry.replace("-", "")
                           and item.contract.tradingClass == trading_class and item.contract.conId > 0}
                if len(matches) != 1:
                    raise IBKROptionsError("ibkr_contract_not_found", "A fixed option contract could not be qualified uniquely")
                contract = next(iter(matches.values()))
                contract.exchange = "SMART"
                contracts.append((right, contract))
            report["stage"] = "historical_bars"
            option_rows, provenance = [], []
            for role, contract in contracts:
                assert report["history_requests"] < MAX_HISTORY_REQUESTS
                report["history_requests"] += 1
                item = {"role": role, "symbol": symbol, "expiry": expiry if role != "stock" else None,
                        "strike": strike if role != "stock" else None, "right": role if role != "stock" else None}
                report["instruments"].append(item)
                try:
                    raw, req_id = await request_history(client, callbacks, contract, end, days)
                    bars, rejected = [], 0
                    for bar in raw:
                        try:
                            normalized = normalize_bar(bar)
                            if start <= datetime.fromisoformat(normalized["at"]) < end:
                                bars.append(normalized)
                        except (ValueError, OverflowError, OSError):
                            rejected += 1
                    rows, origins = aggregate_days(bars, strike=strike, right=role if role != "stock" else None)
                    item.update(status="received" if bars else "empty", bars=bars, derived_daily=rows,
                                trading_days_received=len(rows), observed_trading_dates=[row["trading_date"] for row in rows],
                                rejected_bars=rejected, broker_codes=sorted(callbacks.codes[req_id]))
                    if role != "stock":
                        option_rows.extend(rows)
                        provenance.extend(origins)
                except _Rejected as error:
                    item.update(status="request_failed", broker_codes=[error.code],
                                safe_categories=sorted(callbacks.categories[callbacks.last_history_request_id]))
                except TimeoutError:
                    item.update(status="timeout", broker_codes=[])
                await asyncio.sleep(.35)
            if option_rows:
                report["dataset"] = {"label": f"{symbol} {expiry} {strike:g} C/P historical sample",
                    "symbol": symbol, "expiry": expiry, "currency": "USD",
                    "bar_basis": "derived_from_intraday_trades",
                    "source_label": "IBKR historical TRADES 1-hour RTH bars; locally derived daily summaries with partial/unverified session coverage",
                    "exported_at": datetime.now(UTC).isoformat(),
                    "rows": sorted(option_rows, key=lambda row: (row["trading_date"], row["strike"], row["right"]))}
                report["row_provenance"] = provenance
            report["actual_coverage"] = {item["role"]: {
                "received_hourly_bars": len(item.get("bars", [])),
                "observed_trading_dates": item.get("observed_trading_dates", []),
                "trading_days_received": item.get("trading_days_received", 0),
                "rejected_bars": item.get("rejected_bars", 0), "full_session_verified": False,
            } for item in report["instruments"]}
            success = sum(item.get("status") == "received" for item in report["instruments"])
            report.update(stage="complete", status="passed" if success == 3 else "partial" if success else "failed",
                          historical_instruments_received=success)
    except (IBKROptionsError, _Rejected, TimeoutError, OSError, ValueError) as error:
        report.update(status="failed", error_type=type(error).__name__)
        if isinstance(error, IBKROptionsError):
            report["error_code"] = error.code
        elif isinstance(error, _Rejected):
            report["broker_codes"] = [error.code]
        elif isinstance(error, TimeoutError):
            report["error_code"] = ("ibkr_client_id_conflict" if 326 in callbacks.global_codes else "ibkr_connection_failed") if report["stage"] == "connect" else "ibkr_historical_timeout"
        elif isinstance(error, OSError):
            report["error_code"] = "ibkr_connection_failed"
    finally:
        client.disconnect()
        report["global_broker_codes"] = sorted(callbacks.global_codes)
    return report


def failure_diagnostics(report):
    """Expose structural facts and categorical errors, never broker text or IDs."""
    codes = set(report.get("broker_codes", [])) | set(report.get("global_broker_codes", []))
    instruments = []
    for item in report.get("instruments", []):
        codes.update(item.get("broker_codes", []))
        instruments.append({"role": item["role"], "status": item.get("status", "incomplete"),
                            "received_hourly_bars": len(item.get("bars", [])),
                            "trading_days_received": item.get("trading_days_received", 0),
                            "broker_codes": item.get("broker_codes", []),
                            "safe_categories": item.get("safe_categories", [])})
    return {"stage": report.get("stage", "historical_bars"), "source": "ibkr_historical",
            "history_requests": report.get("history_requests", 0), "model_requests": 0,
            "bar_basis": "derived_from_intraday_trades", "full_session_verified": False,
            "broker_codes": sorted(codes), "instruments": instruments}


class IBKRHistoryProvider:
    """One bounded historical fetch at a time, optionally sharing the live lock."""

    def __init__(self, config: IBKRConfig | None = None, lock: asyncio.Lock | None = None):
        self._invalid_config = False
        try:
            self.config = config if config is not None else IBKRConfig.from_env()
        except ValueError:
            self.config = IBKRConfig()
            self._invalid_config = True
        self._lock = lock if lock is not None else asyncio.Lock()

    async def fetch(self, symbol: str, expiry: str, strike: float, days: int = 5) -> dict:
        symbol = symbol.strip().upper() if isinstance(symbol, str) else ""
        if not _SYMBOL.fullmatch(symbol) or len(symbol) > 12 or number(strike) is None or not 0 < strike <= 1_000_000:
            raise IBKROptionsError("ibkr_invalid_request", "Use a US stock symbol and an explicit positive finite strike")
        try:
            if not isinstance(expiry, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", expiry):
                raise ValueError
            expiration = date.fromisoformat(expiry)
        except ValueError:
            raise IBKROptionsError("ibkr_invalid_request", "Use an explicit ISO expiration date") from None
        if type(days) is not int or days not in {3, 4, 5}:
            raise IBKROptionsError("ibkr_invalid_request", "Use a bounded 3 to 5 calendar-day historical lookback")
        if expiration < datetime.now(UTC).astimezone(NY).date():
            raise IBKROptionsError("ibkr_historical_expired_option", "IBKR expired-option historical data is unavailable")
        if self._invalid_config:
            raise IBKROptionsError("ibkr_invalid_config", "Configure a valid local IBKR endpoint")
        if not self.config.enabled:
            raise IBKROptionsError("ibkr_disabled", "Enable the server-side IBKR provider to collect history")
        if self._lock.locked():
            raise IBKROptionsError("ibkr_busy", "An IBKR metadata, quote or historical request is already running")
        async with self._lock:
            try:
                report = await _fetch_report(self.config, symbol, expiry, float(strike), days)
            except ImportError:
                raise IBKROptionsError("ibkr_dependency_missing", "Install the optional IBKR transport dependency") from None
            if report["status"] != "passed":
                raise IBKROptionsError(report.get("error_code", "ibkr_historical_unavailable"),
                                       "Required historical bars were not returned; no missing observations were invented",
                                       diagnostics=failure_diagnostics(report))
            return report

