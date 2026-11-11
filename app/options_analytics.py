"""Deterministic analysis of one sampled option expiry.

Timestamps below measure local receipt. Market-data mode is independent of
receipt age, so a recently delivered delayed/frozen tick is never marked live.
"""

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from math import isclose, isfinite
from sys import float_info


MODE_LABELS = {1: "live", 2: "frozen", 3: "delayed", 4: "delayed_frozen"}
PAIR_TIME_TOLERANCE_SECONDS = 10.0
DELTA_TARGET = 0.25
DELTA_TOLERANCE = 0.05
ATM_MAX_DISTANCE = 0.03
ATM_MAX_RELATIVE_SPREAD = 0.30
MIN_SIGNAL_STRIKES = 2
MIN_SIGNAL_COVERAGE = 0.50

CAVEATS = {
    "zh": [
        "指标只覆盖本次选择的到期日和行权价，样本比例按请求范围计算。",
        "接收时间来自本机。行情模式、报价的交易所时间和未平仓量的统计时点需分别理解。",
        "成交量和未平仓量反映不同的统计口径。汇总计数无法区分主动买卖、开平仓、对冲或组合交易。",
        "25 Delta 偏斜是所选合约的看跌 IV 减看涨 IV，单位为波动率百分点。它反映相对定价。",
        "平值跨式溢价使用同一行权价两腿的买卖中价。溢价占标的价格比例仅描述期权定价。",
    ],
    "en": [
        "Metrics cover the selected expiry and strikes. Coverage is measured against the requested sample.",
        "Receipt times use the local clock. Feed mode, exchange quote time and the open-interest reporting period are separate concepts.",
        "Volume and open interest measure different activity. Aggregate counts do not identify aggressor side, opening or closing activity, hedges or multi-leg trades.",
        "The 25-delta skew is put IV minus call IV for the selected pair, in volatility percentage points. It describes relative pricing.",
        "ATM straddle premium adds both leg midpoints at the same strike. Its share of spot describes option pricing.",
    ],
}


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) and abs(result) < float_info.max else None


def _positive(value: object) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _count(value: object) -> int | None:
    number = _number(value)
    if number is None or not 0 <= number <= 2**53 or not number.is_integer():
        return None
    return int(number)


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.utcoffset() is not None else None


def _mode(row: Mapping) -> int | None:
    mode = row.get("market_data_type")
    return mode if type(mode) is int and mode in MODE_LABELS else None


def _bbo(row: Mapping) -> tuple[float, float] | None:
    bid, ask = _positive(row.get("bid")), _positive(row.get("ask"))
    if bid is None or ask is None or ask < bid:
        return None
    return bid, ask


def _mid_spread(bbo: tuple[float, float]) -> tuple[float, float]:
    bid, ask = bbo
    mid = bid + (ask - bid) / 2
    return mid, (ask - bid) / mid


def _fresh(stamp: datetime | None, now: datetime, maximum_age: float) -> bool:
    return stamp is not None and 0 <= (now - stamp).total_seconds() <= maximum_age


def _synchronized(*stamps: datetime) -> bool:
    return (max(stamps) - min(stamps)).total_seconds() <= PAIR_TIME_TOLERANCE_SECONDS


def _has_observation(row: Mapping) -> bool:
    return (
        any(_positive(row.get(field)) is not None for field in ("bid", "ask", "last", "close", "implied_volatility"))
        or any(_count(row.get(field)) is not None for field in ("volume", "open_interest"))
    )


def _requested_strikes(snapshot: Mapping) -> list[float]:
    strikes = snapshot.get("requested_strikes")
    if not isinstance(strikes, (list, tuple)):
        return []
    return sorted({strike for raw in strikes if (strike := _positive(raw)) is not None})


def _sample_rows(snapshot: Mapping, strikes: list[float]) -> tuple[dict, int, int]:
    quotes = snapshot.get("quotes")
    if not isinstance(quotes, (list, tuple)):
        return {}, 0, 0
    expiry = snapshot.get("expiration")
    in_scope = set(strikes)
    grouped = {}
    outside_sample = 0
    for row in quotes:
        if not isinstance(row, Mapping):
            outside_sample += 1
            continue
        strike = _positive(row.get("strike"))
        right = row.get("right")
        if strike not in in_scope or right not in ("C", "P") or row.get("expiration", expiry) != expiry:
            outside_sample += 1
            continue
        grouped.setdefault((strike, right), []).append(row)
    # Multiple contracts at the same expiry, strike and right are ambiguous
    # unless the provider qualifies one trading class before requesting data.
    unique = {key: rows[0] for key, rows in grouped.items() if len(rows) == 1}
    return unique, outside_sample, sum(len(rows) > 1 for rows in grouped.values())


def _metric(mode: int | None, reason: str | None = None, value: float | None = None, **details) -> dict:
    return {"value": value, "reason": reason, "market_data_status": MODE_LABELS.get(mode, "unknown"), **details}


def _paired_ratio(field: str, rows: dict, strikes: list[float], mode: int | None, now: datetime, age: float) -> dict:
    if mode is None:
        return _metric(mode, "market_data_type_unconfirmed", put_total=None, call_total=None, paired_strikes=0, pair_coverage=0.0)
    call_total = put_total = 0
    paired = []
    for strike in strikes:
        call, put = (rows.get((strike, right), {}) for right in ("C", "P"))
        if _mode(call) != mode or _mode(put) != mode:
            continue
        call_value, put_value = _count(call.get(field)), _count(put.get(field))
        call_time, put_time = (_timestamp(row.get(f"{field}_received_at")) for row in (call, put))
        if (
            call_value is None or put_value is None
            or not _fresh(call_time, now, age) or not _fresh(put_time, now, age)
            or not _synchronized(call_time, put_time)
        ):
            continue
        call_total += call_value
        put_total += put_value
        paired.append(strike)
    coverage = len(paired) / len(strikes) if strikes else 0.0
    details = {
        "put_total": put_total if paired else None,
        "call_total": call_total if paired else None,
        "paired_strikes": len(paired),
        "pair_coverage": coverage,
        "included_strikes": paired,
    }
    if not paired:
        return _metric(mode, "insufficient_paired_strikes", **details)
    if not call_total:
        return _metric(mode, "zero_call_total", **details)
    return _metric(mode, value=put_total / call_total, **details)


def _atm_straddle(rows: dict, strikes: list[float], mode: int | None, spot: float | None,
                  spot_time: datetime | None, now: datetime, age: float) -> dict:
    if spot is None or mode is None or not strikes:
        return _metric(mode, "underlying_unavailable")
    if not _fresh(spot_time, now, age):
        return _metric(mode, "underlying_price_stale")
    strike = min(strikes, key=lambda value: (abs(value - spot), value))
    spot_distance = abs(strike / spot - 1)
    if not isfinite(spot_distance):
        return _metric(mode, "invalid_numeric_range")
    details = {"strike": strike, "spot": spot, "spot_distance": spot_distance}
    if spot_distance > ATM_MAX_DISTANCE:
        return _metric(mode, "atm_strike_too_far", **details)
    call, put = (rows.get((strike, right), {}) for right in ("C", "P"))
    call_bbo, put_bbo = _bbo(call), _bbo(put)
    if _mode(call) != mode or _mode(put) != mode or not call_bbo or not put_bbo:
        return _metric(mode, "atm_quote_unavailable", **details)
    call_time, put_time = (_timestamp(row.get("quote_received_at")) for row in (call, put))
    if not _fresh(call_time, now, age) or not _fresh(put_time, now, age):
        return _metric(mode, "atm_quote_stale", **details)
    if not _synchronized(spot_time, call_time, put_time):
        return _metric(mode, "unsynchronized_receipts", **details)
    call_mid, call_spread = _mid_spread(call_bbo)
    put_mid, put_spread = _mid_spread(put_bbo)
    details.update(call_mid=call_mid, put_mid=put_mid,
                   call_relative_spread=call_spread, put_relative_spread=put_spread)
    if max(call_spread, put_spread) > ATM_MAX_RELATIVE_SPREAD:
        return _metric(mode, "wide_bid_ask_spread", **details)
    premium = call_mid + put_mid
    percent_of_spot = 100 * (premium / spot)
    if not isfinite(percent_of_spot):
        return _metric(mode, "invalid_numeric_range", **details)
    return _metric(mode, value=percent_of_spot, premium=premium, **details)


def _wing_candidates(rows: dict, spot: float, mode: int, spot_time: datetime, now: datetime, age: float) -> dict:
    wings = {"P": [], "C": []}
    for (strike, right), row in rows.items():
        if _mode(row) != mode or (right == "C" and strike <= spot) or (right == "P" and strike >= spot):
            continue
        iv, delta = _positive(row.get("implied_volatility")), _number(row.get("delta"))
        if iv is None or delta is None:
            continue
        signed_delta = delta if right == "C" else -delta
        if not DELTA_TARGET - DELTA_TOLERANCE <= signed_delta <= DELTA_TARGET + DELTA_TOLERANCE:
            continue
        basis = row.get("greeks_basis")
        greeks_time = _timestamp(row.get("greeks_received_at"))
        if (
            basis not in ("model", "bid", "ask", "last")
            or not _fresh(greeks_time, now, age)
            or not _synchronized(greeks_time, spot_time)
        ):
            continue
        wings[right].append((strike, iv, delta, signed_delta, basis, greeks_time))
    return wings


def _iv_skew(rows: dict, mode: int | None, spot: float | None, spot_time: datetime | None,
             now: datetime, age: float) -> dict:
    if spot is None or mode is None:
        return _metric(mode, "underlying_unavailable")
    if not _fresh(spot_time, now, age):
        return _metric(mode, "underlying_price_stale")
    wings = _wing_candidates(rows, spot, mode, spot_time, now, age)
    pairs = []
    for put in wings["P"]:
        for call in wings["C"]:
            if put[4] != call[4] or abs(put[3] - call[3]) > DELTA_TOLERANCE or not _synchronized(put[5], call[5]):
                continue
            distance = abs(put[3] - DELTA_TARGET) + abs(call[3] - DELTA_TARGET)
            pairs.append((distance, put[0], call[0], put, call))
    if not pairs:
        return _metric(mode, "insufficient_comparable_greeks")
    _, _, _, put, call = min(pairs)
    value = 100 * (put[1] - call[1])
    if not isfinite(value):
        return _metric(mode, "invalid_numeric_range")
    return _metric(mode, value=value, put_strike=put[0], call_strike=call[0],
                   put_iv=put[1], call_iv=call[1], put_delta=put[2], call_delta=call[2],
                   greeks_basis=put[4])


def _signals(metrics: dict) -> list[dict]:
    results = []
    for field in ("volume", "open_interest"):
        name = f"put_call_{field}"
        ratio = metrics[name]
        if ratio["paired_strikes"] < MIN_SIGNAL_STRIKES or ratio["pair_coverage"] < MIN_SIGNAL_COVERAGE:
            continue
        puts, calls = ratio["put_total"], ratio["call_total"]
        if puts == calls == 0:
            continue
        if puts > calls:
            code = f"more_put_{field}"
        elif calls > puts:
            code = f"more_call_{field}"
        else:
            code = f"equal_put_call_{field}"
        results.append({"metric": name, "code": code})
    skew = metrics["iv_skew_25_delta"]["value"]
    if skew is not None:
        code = "equal_put_call_iv"
        if skew > 1e-9:
            code = "higher_put_iv"
        elif skew < -1e-9:
            code = "higher_call_iv"
        results.append({"metric": "iv_skew_25_delta", "code": code})
    return results


def analyze_option_snapshot(snapshot: Mapping, *, now: datetime | None = None,
                            freshness_seconds: float = 30.0, language: str = "zh") -> dict:
    """Analyze an IBKR sample without inferring direction or filling missing ticks."""
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None or not isfinite(freshness_seconds) or freshness_seconds <= 0:
        raise ValueError("A timezone-aware clock and positive freshness window are required")
    strikes = _requested_strikes(snapshot)
    rows, outside_sample, ambiguous = _sample_rows(snapshot, strikes)
    underlying = snapshot.get("underlying")
    if not isinstance(underlying, Mapping):
        underlying = {}
    spot = _positive(underlying.get("price"))
    spot_time = _timestamp(underlying.get("received_at"))
    underlying_mode = _mode(underlying) if spot is not None else None
    observed = {key: row for key, row in rows.items() if _has_observation(row)}
    counts = Counter(_mode(row) for row in observed.values())
    observed_modes = set(counts)
    if spot is not None:
        observed_modes.add(underlying_mode)
    status = "unavailable"
    if len(observed_modes) > 1:
        status = "mixed"
    elif observed_modes:
        status = MODE_LABELS.get(next(iter(observed_modes)), "unknown")
    mode = underlying_mode
    if mode is None and len(observed_modes) == 1:
        mode = next(iter(observed_modes))
    underlying_bbo = _bbo(underlying)
    midpoint_available = (
        spot is not None and underlying_bbo is not None
        and underlying.get("price_basis") in ("mid", "midpoint")
        and isclose(spot, _mid_spread(underlying_bbo)[0], rel_tol=1e-6)
    )
    # A recently received last price could represent an old trade. Price-based
    # metrics therefore require a matching two-sided underlying quote.
    spot_for_metrics = spot if underlying_mode == mode and midpoint_available else None
    valid_bbo = {key: row for key, row in rows.items() if _bbo(row) is not None}
    live_bbo = {
        key: row for key, row in valid_bbo.items()
        if _mode(row) == 1 and _fresh(_timestamp(row.get("quote_received_at")), now, freshness_seconds)
    }
    live_pairs = sum(
        (strike, "C") in live_bbo and (strike, "P") in live_bbo
        and _synchronized(*(_timestamp(live_bbo[(strike, right)]["quote_received_at"]) for right in ("C", "P")))
        for strike in strikes
    )
    live_pair_coverage = live_pairs / len(strikes) if strikes else 0.0
    underlying_live = bool(
        underlying_mode == 1 and midpoint_available and _fresh(spot_time, now, freshness_seconds)
    )
    age = freshness_seconds
    metrics = {
        "put_call_volume": _paired_ratio("volume", rows, strikes, mode, now, age),
        "put_call_open_interest": _paired_ratio("open_interest", rows, strikes, mode, now, age),
        "iv_skew_25_delta": _iv_skew(rows, mode, spot_for_metrics, spot_time, now, age),
        "atm_straddle": _atm_straddle(rows, strikes, mode, spot_for_metrics, spot_time, now, age),
    }
    volume = metrics["put_call_volume"]
    volume_evidence = (
        volume["value"] is not None and volume["paired_strikes"] >= MIN_SIGNAL_STRIKES
        and volume["pair_coverage"] >= MIN_SIGNAL_COVERAGE
    )
    usable_metric = volume_evidence or any(metrics[name]["value"] is not None for name in ("iv_skew_25_delta", "atm_straddle"))
    reasons = []
    if status != "live":
        reasons.append("market_data_not_consistently_live")
    if not underlying_live:
        reasons.append("underlying_live_midpoint_unavailable")
    if live_pairs < MIN_SIGNAL_STRIKES or live_pair_coverage < MIN_SIGNAL_COVERAGE:
        reasons.append("insufficient_fresh_live_pairs")
    if not usable_metric:
        reasons.append("insufficient_recent_metric_evidence")
    if ambiguous:
        reasons.append("ambiguous_contracts_excluded")
    requested_contracts = 2 * len(strikes)
    quality = {
        "market_data_status": status,
        "llm_eligible": not reasons,
        "requested_contracts": requested_contracts,
        "received_contracts": len(observed),
        "valid_quote_contracts": len(valid_bbo),
        "fresh_live_quote_contracts": len(live_bbo),
        "quote_coverage": len(valid_bbo) / requested_contracts if requested_contracts else None,
        "fresh_live_paired_strikes": live_pairs,
        "fresh_live_pair_coverage": live_pair_coverage,
        "freshness_seconds": freshness_seconds,
        "underlying_fresh_live": underlying_live,
        "observed_quote_modes": {MODE_LABELS.get(key, "unknown"): count for key, count in counts.items()},
        "excluded_out_of_scope_rows": outside_sample,
        "excluded_ambiguous_contracts": ambiguous,
        "reason_codes": reasons,
    }
    return {"quality": quality, "metrics": metrics, "signals": _signals(metrics),
            "caveats": CAVEATS["en" if language == "en" else "zh"].copy()}
