"""Conservative local comparisons between immutable options captures.

No market request or model arithmetic occurs here. Existing aggregates are read
only after the contract window, feed, timestamps and metric sample are checked.
Raw quote fields are inspected solely to verify the already-calculated median
spread's actual contract membership, using the original aggregation conditions.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from math import isfinite
from zoneinfo import ZoneInfo

from app.options_analytics import (
    MODE_LABELS, _bbo, _count, _fresh, _mode, _requested_strikes, _sample_rows,
)


METRICS = {
    "quote_coverage": ("有效报价覆盖", "Valid quote coverage", "fraction", "percentage_points"),
    "volume_put_share": ("看跌成交占比", "Put share of trading volume", "fraction", "percentage_points"),
    "oi_put_share": ("看跌未平仓占比", "Put share of open interest", "fraction", "percentage_points"),
    "volume_total": ("配对样本成交总数", "Paired-sample trading volume", "contracts", "contracts"),
    "oi_total": ("配对样本未平仓总数", "Paired-sample open interest", "contracts", "contracts"),
    "median_spread": ("相对买卖价差中位数", "Median relative bid/ask spread", "percent", "percentage_points"),
    "atm_iv": ("近平值隐含波动率", "Near-ATM implied volatility", "fraction", "volatility_points"),
}
REASONS = {
    "scope_added": ("上次没有这个标的与到期日范围。", "This underlying and expiration were not captured previously."),
    "scope_missing": ("新快照没有返回这个原有范围。", "The new capture did not return this previous scope."),
    "capture_failed": ("这个范围的采集请求失败，不能把未返回当成零。", "Collection failed for this scope; absent data is not zero."),
    "ambiguous_scope": ("同一标的与到期日存在重复范围，无法唯一配对。", "Duplicate underlying/expiration scopes cannot be paired uniquely."),
    "contract_metadata_missing": ("合约类别、币种或乘数缺失，不能确认相同合约口径。", "Contract class, currency or multiplier is missing, so identical contract definitions cannot be confirmed."),
    "contract_metadata_changed": ("合约类别、币种或乘数发生变化。", "Contract class, currency or multiplier changed."),
    "requested_strikes_missing": ("缺少可核验的请求行权价范围。", "The requested strike window cannot be verified."),
    "requested_strikes_changed": ("请求的行权价范围改变，汇总变化可能来自取样。", "The requested strike window changed; aggregate differences may reflect sampling."),
    "feed_unconfirmed": ("实际行情类型未获一致确认。", "The actual feed type is unconfirmed or inconsistent."),
    "feed_changed": ("实际收到的行情类型改变，不能直接比较。", "The actual feed type changed and cannot be compared directly."),
    "receipt_time_missing": ("缺少带时区的本地接收时间。", "A timezone-aware local receipt time is missing."),
    "receipt_time_not_increasing": ("新快照接收时间没有晚于旧快照。", "The new receipt time is not later than the previous one."),
    "future_receipt_time": ("接收时间位于本地时钟未来，时序无法核验。", "A receipt time is in the local clock's future, so ordering cannot be verified."),
    "requested_denominator_unverified": ("报价覆盖的请求合约分母无法核验。", "The requested-contract denominator of quote coverage cannot be verified."),
    "volume_pair_sample_changed": ("成交计数实际配对的行权价集合改变。", "The actual paired strike set for trading volume changed."),
    "oi_pair_sample_changed": ("未平仓计数实际配对的行权价集合改变。", "The actual paired strike set for open interest changed."),
    "paired_sample_unverified": ("缺少可核验的实际配对计数范围。", "The actual paired count sample cannot be verified."),
    "volume_cross_ny_date": ("接收时间跨越纽约日期，日累计成交不能相减。", "Receipt times cross New York dates; daily cumulative volume cannot be subtracted."),
    "quote_contract_set_unverified": ("无法核验价差指标实际使用的合约集合。", "The actual contract set used by the spread metric cannot be verified."),
    "quote_contract_set_changed": ("价差指标实际使用的有效报价合约集合改变。", "The valid-quote contract set used by the spread metric changed."),
    "atm_definition_missing": ("缺少近平值行权价或波动率计算口径。", "The near-ATM strike or volatility basis is missing."),
    "atm_definition_changed": ("近平值行权价或波动率计算口径改变。", "The near-ATM strike or volatility basis changed."),
    "missing_before": ("旧样本的这个指标缺失。", "This metric is missing in the previous sample."),
    "missing_after": ("新样本的这个指标缺失。", "This metric is missing in the new sample."),
    "missing_both": ("前后样本的这个指标都缺失。", "This metric is missing in both samples."),
    "non_finite_delta": ("差值超出安全数值范围，未生成变化量。", "The difference is outside the finite numeric range; no delta was produced."),
}


def _text(language, pair):
    return pair[1] if language == "en" else pair[0]


def _clock():
    return datetime.now(timezone.utc)


def _number(value):
    if type(value) not in (int, float):
        return None
    try:
        return value if isfinite(value) else None
    except OverflowError:
        return None


def _stamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.utcoffset() is not None else None
    except (ValueError, OverflowError):
        return None


def _reports(analysis):
    if isinstance(analysis.get("reports"), list):
        return [report for report in analysis["reports"] if isinstance(report, dict)]
    return [analysis] if isinstance(analysis.get("snapshot"), dict) else []


def _key(report):
    snapshot = report.get("snapshot", {})
    return snapshot.get("symbol"), snapshot.get("expiration")


def _feed(report):
    quality = report.get("quality", {}).get("market_data_status")
    context = report.get("collective", {}).get("context", {}).get("market_data_status")
    return quality if quality in MODE_LABELS.values() and context in (None, quality) else "unknown"


def _strikes(report):
    raw = report.get("snapshot", {}).get("requested_strikes")
    if not isinstance(raw, (list, tuple)) or not raw:
        return None
    if any(_number(value) is None or value <= 0 for value in raw) or len(set(raw)) != len(raw):
        return None
    return tuple(sorted(raw))


def _paired(report, field):
    distribution = report.get("collective", {}).get("distributions", {}).get(field, {})
    rows = distribution.get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    strikes = []
    requested = _strikes(report)
    for row in rows:
        if not isinstance(row, dict) or _number(row.get("strike")) is None:
            return None
        if not requested or row["strike"] not in requested or any(_count(row.get(side)) is None for side in ("call", "put")):
            return None
        strikes.append(row["strike"])
    if len(set(strikes)) != len(strikes) or distribution.get("paired_strikes") != len(strikes):
        return None
    return tuple(sorted(strikes))


def _spread_contracts(report):
    """Mirror membership checks of collective._liquidity, without recomputing a metric."""
    analyzed = _stamp(report.get("analyzed_at"))
    strikes = _strikes(report)
    if analyzed is None or not strikes:
        return None
    feed = _feed(report)
    mode = next((code for code, label in MODE_LABELS.items() if label == feed), None)
    if mode is None:
        return None
    age = _number(report.get("quality", {}).get("freshness_seconds")) or 30
    if age <= 0:
        return None
    snapshot = report.get("snapshot", {})
    rows, _, _ = _sample_rows(snapshot, _requested_strikes(snapshot))
    contracts = frozenset(key for key, row in rows.items()
                          if _mode(row) == mode and _bbo(row) and _fresh(_stamp(row.get("quote_received_at")), analyzed, age))
    expected = report.get("collective", {}).get("liquidity", {}).get("valid_contracts")
    return contracts if contracts and expected == len(contracts) else None


def _value(report, metric):
    collective = report.get("collective", {})
    if metric == "quote_coverage":
        value = report.get("quality", {}).get("quote_coverage")
    elif metric == "median_spread":
        value = collective.get("liquidity", {}).get("median_relative_spread_pct")
    elif metric == "atm_iv":
        value = collective.get("volatility", {}).get("atm_iv")
    else:
        prefix, kind = metric.split("_", 1)
        distribution = collective.get("distributions", {}).get("volume" if prefix == "volume" else "open_interest", {})
        if kind == "total":
            value = distribution.get("total")
        else:
            # Use the already calculated evidence share, never divide totals here.
            candidates = [item.get("value") for item in collective.get("evidence", [])
                          if isinstance(item, dict) and item.get("id") == metric]
            value = candidates[0] if len(candidates) == 1 else None
    value = _number(value)
    if value is not None and (value < 0 or metric in {"quote_coverage", "volume_put_share", "oi_put_share"} and value > 1):
        return None
    return value


def _base_reasons(before, after, now):
    reasons = []
    previous, current = before.get("snapshot", {}), after.get("snapshot", {})
    fields = ("trading_class", "currency", "multiplier")
    if any(previous.get(key) in (None, "") or current.get(key) in (None, "") for key in fields):
        reasons.append("contract_metadata_missing")
    elif any(previous[key] != current[key] for key in fields):
        reasons.append("contract_metadata_changed")
    left, right = _strikes(before), _strikes(after)
    if left is None or right is None:
        reasons.append("requested_strikes_missing")
    elif left != right:
        reasons.append("requested_strikes_changed")
    feeds = _feed(before), _feed(after)
    if "unknown" in feeds:
        reasons.append("feed_unconfirmed")
    elif feeds[0] != feeds[1]:
        reasons.append("feed_changed")
    times = _stamp(previous.get("received_at")), _stamp(current.get("received_at"))
    if None in times:
        reasons.append("receipt_time_missing")
    else:
        if times[1] <= times[0]:
            reasons.append("receipt_time_not_increasing")
        if any(stamp > now for stamp in times):
            reasons.append("future_receipt_time")
    return reasons


def _metric_reason(before, after, metric):
    if metric == "quote_coverage":
        denominators = [report.get("quality", {}).get("requested_contracts") for report in (before, after)]
        expected = len(_strikes(before) or ()) * 2
        if not expected or any(type(value) is not int or value != expected for value in denominators):
            return "requested_denominator_unverified"
    elif metric.startswith(("volume_", "oi_")):
        field = "volume" if metric.startswith("volume_") else "open_interest"
        samples = _paired(before, field), _paired(after, field)
        if None in samples:
            return "paired_sample_unverified"
        if samples[0] != samples[1]:
            return "volume_pair_sample_changed" if field == "volume" else "oi_pair_sample_changed"
        if field == "volume":
            times = [_stamp(report["snapshot"].get("received_at")) for report in (before, after)]
            if any(stamp is None for stamp in times) or times[0].astimezone(ZoneInfo("America/New_York")).date() != times[1].astimezone(ZoneInfo("America/New_York")).date():
                return "volume_cross_ny_date"
    elif metric == "median_spread":
        samples = _spread_contracts(before), _spread_contracts(after)
        if None in samples:
            return "quote_contract_set_unverified"
        if samples[0] != samples[1]:
            return "quote_contract_set_changed"
    elif metric == "atm_iv":
        definitions = []
        for report in (before, after):
            volatility = report.get("collective", {}).get("volatility", {})
            strike, basis = _number(volatility.get("atm_strike")), volatility.get("greeks_basis")
            if strike is None or strike <= 0 or basis not in {"model", "bid", "ask", "last"}:
                return "atm_definition_missing"
            definitions.append((strike, basis))
        if definitions[0] != definitions[1]:
            return "atm_definition_changed"
    return None


def _captured(analysis):
    stamps = [_stamp(report.get("snapshot", {}).get("received_at")) for report in _reports(analysis)]
    earliest = min((stamp for stamp in stamps if stamp), default=None)
    return earliest.isoformat() if earliest else None


def build_refresh_comparison(previous, current, language="zh") -> dict:
    """Compare like-for-like saved scopes; preserve unavailable before/after values."""
    grouped = []
    for analysis in (previous, current):
        mapping = defaultdict(list)
        for report in _reports(analysis):
            mapping[_key(report)].append(report)
        grouped.append(mapping)
    old, new = grouped
    failures = [{"phase": phase, **{key: item.get(key) for key in ("symbol", "expiry", "code")}}
                for phase, analysis in (("previous", previous), ("current", current))
                for item in analysis.get("failures", []) if isinstance(item, dict)]
    keys = list(dict.fromkeys([*old, *new, *((item["symbol"], item["expiry"]) for item in failures)]))
    scopes, now = [], _clock()
    for index, key in enumerate(keys):
        before_items, after_items = old.get(key, []), new.get(key, [])
        before, after = (before_items[0] if len(before_items) == 1 else {}), (after_items[0] if len(after_items) == 1 else {})
        failed = any((item["symbol"], item["expiry"]) == key and item["phase"] == "current" for item in failures)
        if len(before_items) > 1 or len(after_items) > 1:
            reasons, status = ["ambiguous_scope"], "incomparable"
        elif not before and not after:
            reasons, status = ["capture_failed"], "failed"
        elif not before:
            reasons, status = ["scope_added"], "added"
        elif not after:
            reasons, status = ["capture_failed" if failed else "scope_missing"], "failed" if failed else "missing"
        else:
            reasons, status = _base_reasons(before, after, now), None
        metrics = []
        for metric, (zh, en, unit, delta_unit) in METRICS.items():
            left, right = _value(before, metric), _value(after, metric)
            reason = reasons[0] if reasons else _metric_reason(before, after, metric)
            if reason is None and (left is None or right is None):
                reason = "missing_both" if left is None and right is None else "missing_before" if left is None else "missing_after"
            delta = None
            if reason is None:
                scale = 100 if unit == "fraction" else 1
                calculated = (Decimal(str(right)) - Decimal(str(left))) * scale
                delta = _number(float(calculated))
                if delta is None:
                    reason = "non_finite_delta"
                elif unit == "contracts" and delta.is_integer():
                    delta = int(delta)
            metrics.append({"id": metric, "label": _text(language, (zh, en)), "before": left, "after": right,
                            "unit": unit, "delta": delta, "delta_unit": delta_unit,
                            "direction": "unavailable" if delta is None else "increased" if delta > 0 else "decreased" if delta < 0 else "unchanged",
                            "status": "incomparable" if reason else "comparable", "reason": reason,
                            "reason_text": _text(language, REASONS[reason]) if reason else None})
        comparable = sum(item["status"] == "comparable" for item in metrics)
        if status is None:
            status = "comparable" if comparable == len(metrics) else "partial" if comparable else "incomparable"
        all_reasons = list(dict.fromkeys([*reasons, *(item["reason"] for item in metrics if item["reason"])]))
        scope_info = lambda report: {field: report.get("snapshot", {}).get(field) for field in ("trading_class", "currency", "multiplier", "requested_strikes")}
        scopes.append({"id": f"s{index}", "symbol": key[0], "expiry": key[1],
                       "previous_received_at": before.get("snapshot", {}).get("received_at"),
                       "received_at": after.get("snapshot", {}).get("received_at"),
                       "before_feed": _feed(before), "after_feed": _feed(after),
                       "before_scope": scope_info(before), "after_scope": scope_info(after),
                       "status": status, "reasons": all_reasons,
                       "reason_messages": [_text(language, REASONS[reason]) for reason in all_reasons], "metrics": metrics})
    any_comparable = any(metric["status"] == "comparable" for scope in scopes for metric in scope["metrics"])
    status = "comparable" if scopes and not failures and all(scope["status"] == "comparable" for scope in scopes) else "partial" if any_comparable else "incomparable"
    summary = {
        "comparable": ("前后样本口径一致，可逐项查看已计算的变化。", "The sample definitions match; the locally calculated changes can be reviewed metric by metric."),
        "partial": ("只有部分指标可前后比较；其余变化量未生成。", "Only some metrics are comparable; no deltas were produced for the others."),
        "incomparable": ("前后样本尚不能形成可核验的同口径变化。", "The captures do not establish verifiable like-for-like changes."),
    }
    return {"previous_analysis_id": previous.get("analysis_id"), "previous_captured_at": _captured(previous),
            "current_captured_at": _captured(current), "status": status, "summary": _text(language, summary[status]),
            "scopes": scopes, "failures": failures,
            "notice": _text(language, (
                "这是显式重新采集后的前后快照对照。覆盖、行情类型或取样改变不能当成市场涨跌。成交总数差值只是两次收到的累计计数差，不是精确时间间隔内的新增成交，更不代表资金流入。日成交按纽约接收日期核对；本地接收日期不能证明交易所统计周期。未平仓量有独立报告周期，差值不代表资金流入或方向性新持仓。",
                "This comparison follows an explicit new capture. Coverage, feed or sample changes are not market price direction. A volume-total delta is only the difference between received cumulative counts, not exact trades during the receipt interval or fund flow. Daily volume uses New York receipt dates; local receipt dates do not establish the exchange reporting period. Open interest has an independent reporting cycle; its difference is not fund flow or new directional positioning."))}
