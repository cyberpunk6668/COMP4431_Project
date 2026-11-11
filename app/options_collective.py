"""Joint, auditable descriptions of a sampled option chain.

Counts remain paired by strike. Quotes measure displayed tightness rather than
execution capacity. Local receipt times cannot establish exchange latency.
"""
from collections.abc import Mapping
from datetime import datetime, timezone
from math import isclose, isfinite
from statistics import median

from app.options_analytics import (
    MODE_LABELS, PAIR_TIME_TOLERANCE_SECONDS, _bbo, _count, _fresh,
    _mid_spread, _mode, _number, _positive, _requested_strikes,
    _sample_rows, _synchronized, _timestamp,
)


def _text(language, chinese, english):
    return english if language == "en" else chinese


def _paired_counts(rows, strikes, field, mode, now, age):
    pairs = {}
    if mode is None:
        return pairs
    candidates = []
    for strike in strikes:
        call, put = (rows.get((strike, right), {}) for right in ("C", "P"))
        if _mode(call) != mode or _mode(put) != mode:
            continue
        values = [_count(row.get(field)) for row in (call, put)]
        stamps = [_timestamp(row.get(f"{field}_received_at")) for row in (call, put)]
        if any(value is None for value in values):
            continue
        if not all(_fresh(stamp, now, age) for stamp in stamps) or not _synchronized(*stamps):
            continue
        candidates.append((strike, values, stamps))
    if not candidates:
        return pairs
    latest = max(stamp for _, _, stamps in candidates for stamp in stamps)
    for strike, values, stamps in candidates:
        if (latest - min(stamps)).total_seconds() <= PAIR_TIME_TOLERANCE_SECONDS:
            pairs[strike] = {"call": values[0], "put": values[1]}
    return pairs


def _distribution(pairs, strikes, status):
    total = sum(pair["call"] + pair["put"] for pair in pairs.values())
    ordered = []
    for strike, pair in sorted(pairs.items()):
        subtotal = pair["call"] + pair["put"]
        ordered.append({"strike": strike, **pair, "total": subtotal,
                        "share": subtotal / total if total else None})
    ranked = sorted((row["total"] for row in ordered), reverse=True)
    largest = ranked[0] if ranked else None
    return {
        "rows": ordered,
        "total": total if ordered else None,
        "call_total": sum(pair["call"] for pair in pairs.values()) if ordered else None,
        "put_total": sum(pair["put"] for pair in pairs.values()) if ordered else None,
        "paired_strikes": len(pairs),
        "coverage": len(pairs) / len(strikes) if strikes else 0.0,
        "peak_strikes": [row["strike"] for row in ordered if total and row["total"] == largest],
        "top_strike_share": largest / total if total else None,
        "top_two_strike_share": sum(ranked[:2]) / total if total else None,
        "hhi": sum(row["share"] ** 2 for row in ordered) if total else None,
        "market_data_status": status,
    }


def _positioning(volume, interest, strikes):
    common = sorted(set(volume) & set(interest))
    volume_puts = sum(volume[strike]["put"] for strike in common)
    volume_total = sum(sum(volume[strike].values()) for strike in common)
    oi_puts = sum(interest[strike]["put"] for strike in common)
    oi_total = sum(sum(interest[strike].values()) for strike in common)
    volume_share = volume_puts / volume_total if volume_total else None
    oi_share = oi_puts / oi_total if oi_total else None
    gap = 100 * (volume_share - oi_share) if volume_share is not None and oi_share is not None else None
    relation = "unavailable"
    if gap is not None:
        relation = "equal_put_weight"
        if gap > 1e-9:
            relation = "activity_more_put_weighted"
        elif gap < -1e-9:
            relation = "activity_more_call_weighted"
    return {
        "put_volume_share": volume_share,
        "put_open_interest_share": oi_share,
        "put_share_gap_pp": gap,
        "common_strikes": common,
        "coverage": len(common) / len(strikes) if strikes else 0.0,
        "relation": relation,
    }


def _liquidity(rows, strikes, mode, status, now, age):
    spreads = []
    for row in rows.values():
        bbo = _bbo(row)
        if _mode(row) == mode and mode is not None and bbo and _fresh(_timestamp(row.get("quote_received_at")), now, age):
            spreads.append(100 * _mid_spread(bbo)[1])
    requested = len(strikes) * 2
    return {
        "requested_contracts": requested,
        "valid_contracts": len(spreads),
        "coverage": len(spreads) / requested if requested else 0.0,
        "median_relative_spread_pct": median(spreads) if spreads else None,
        "wide_spread_contracts": sum(value > 30 for value in spreads),
        "wide_spread_threshold_pct": 30,
        "market_data_status": status,
    }


def _spot(underlying, mode, now, age):
    bbo = _bbo(underlying)
    price = _positive(underlying.get("price"))
    stamp = _timestamp(underlying.get("received_at"))
    if mode is None or _mode(underlying) != mode or bbo is None or price is None:
        return None, stamp
    if underlying.get("price_basis") not in ("mid", "midpoint") or not _fresh(stamp, now, age):
        return None, stamp
    return (price if isclose(price, _mid_spread(bbo)[0], rel_tol=1e-6) else None), stamp


def _volatility(rows, strikes, underlying, mode, status, now, age):
    spot, spot_time = _spot(underlying, mode, now, age)
    result = {"atm_iv": None, "atm_strike": None, "atm_moneyness_pct": None,
              "greeks_basis": None, "atm_received_at": None, "points": [],
              "market_data_status": status, "reason": "comparable_atm_iv_unavailable"}
    if spot is None or not strikes:
        return result
    candidates = {}
    for (strike, right), row in rows.items():
        iv, delta = _positive(row.get("implied_volatility")), _number(row.get("delta"))
        stamp, quote_stamp = _timestamp(row.get("greeks_received_at")), _timestamp(row.get("quote_received_at"))
        basis = row.get("greeks_basis")
        bbo = _bbo(row)
        if mode is None or _mode(row) != mode or iv is None or delta is None or basis not in ("model", "bid", "ask", "last"):
            continue
        if (right == "C" and not 0 <= delta <= 1) or (right == "P" and not -1 <= delta <= 0):
            continue
        if not bbo or _mid_spread(bbo)[1] > .30:
            continue
        if not _fresh(stamp, now, age) or not _fresh(quote_stamp, now, age):
            continue
        if not _synchronized(stamp, quote_stamp, spot_time):
            continue
        moneyness = 100 * (strike / spot - 1)
        if not isfinite(moneyness):
            continue
        candidates[strike, right] = {"strike": strike, "right": right, "iv": iv,
                                     "delta": delta, "greeks_basis": basis,
                                     "received_at": stamp.isoformat(),
                                     "moneyness_pct": moneyness}
    strike = min(strikes, key=lambda value: (abs(value - spot), value))
    call, put = candidates.get((strike, "C")), candidates.get((strike, "P"))
    if (not call or not put or abs(strike / spot - 1) > .01
            or not .35 <= call["delta"] <= .65 or not -.65 <= put["delta"] <= -.35
            or call["greeks_basis"] != put["greeks_basis"]
            or not _synchronized(_timestamp(call["received_at"]), _timestamp(put["received_at"]))):
        return result
    atm_iv = call["iv"] + (put["iv"] - call["iv"]) / 2
    result.update(atm_iv=atm_iv, atm_strike=strike, atm_moneyness_pct=call["moneyness_pct"],
                  greeks_basis=call["greeks_basis"], reason=None,
                  atm_received_at=min(call["received_at"], put["received_at"]))
    for point in sorted(candidates.values(), key=lambda row: (row["strike"], row["right"])):
        if point["greeks_basis"] == result["greeks_basis"]:
            difference = 100 * (point["iv"] - atm_iv)
            if isfinite(difference):
                result["points"].append({**point, "iv_minus_atm_pp": difference})
    return result


def build_collective_analysis(snapshot, analysis, language="zh", now=None):
    """Describe distribution, quote conditions and cross-signal agreement."""
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("A timezone-aware clock is required")
    quality = analysis.get("quality", {})
    status = quality.get("market_data_status", "unknown")
    mode = next((number for number, label in MODE_LABELS.items() if label == status), None)
    age = _positive(quality.get("freshness_seconds")) or 30.0
    strikes = _requested_strikes(snapshot)
    rows, excluded, ambiguous = _sample_rows(snapshot, strikes)
    scope = {"symbol": snapshot.get("symbol"), "expiration": snapshot.get("expiration"),
             "market_data_status": status, "requested_strikes": len(strikes)}
    underlying = snapshot.get("underlying")
    if not isinstance(underlying, Mapping):
        underlying = {}
    volume = _paired_counts(rows, strikes, "volume", mode, now, age)
    interest = _paired_counts(rows, strikes, "open_interest", mode, now, age)
    distributions = {"volume": _distribution(volume, strikes, status),
                     "open_interest": _distribution(interest, strikes, status)}
    positioning = _positioning(volume, interest, strikes)
    liquidity = _liquidity(rows, strikes, mode, status, now, age)
    volatility = _volatility(rows, strikes, underlying, mode, status, now, age)
    evidence, findings, conflicts = [], [], []

    def add_evidence(identifier, value, unit, chinese, english, description):
        evidence.append({"id": identifier, "label": _text(language, chinese, english),
                         "value": value, "unit": unit, "scope": scope.copy(),
                         "description": description})

    def finding(identifier, chinese_title, english_title, chinese, english, ids, conflict=False):
        item = {"id": identifier, "title": _text(language, chinese_title, english_title),
                "text": _text(language, chinese, english), "evidence_ids": ids}
        (conflicts if conflict else findings).append(item)

    add_evidence("liquidity_coverage", liquidity["coverage"], "fraction", "双边报价覆盖", "Two-sided quote coverage",
                 _text(language, "同模式且近期收到的有效正买卖价覆盖。", "Coverage of recent positive, uncrossed bid/ask quotes in one feed mode."))
    add_evidence("median_spread", liquidity["median_relative_spread_pct"], "percent", "买卖价差中位数", "Median relative spread",
                 _text(language, "价差除以中间价，不包含可成交数量或订单簿深度。", "Spread divided by midpoint; displayed size and execution depth are not measured."))
    finding("quote_conditions", "先看报价可用性", "Quote conditions first",
            f"{liquidity['valid_contracts']} / {liquidity['requested_contracts']} 份合约有同模式、近期双边报价。后续定价结论仅使用满足对应配对条件的数据。",
            f"{liquidity['valid_contracts']} of {liquidity['requested_contracts']} contracts have recent two-sided quotes in the same feed mode. Pricing findings use the qualifying paired data.",
            ["liquidity_coverage", "median_spread"])
    for field, prefix, zh, en in (("volume", "volume", "成交", "volume"), ("open_interest", "oi", "持仓", "open interest")):
        distribution = distributions[field]
        pairs, total = distribution["paired_strikes"], distribution["total"]
        add_evidence(f"{prefix}_coverage", distribution["coverage"], "fraction", f"{zh}配对覆盖", f"Paired {en} coverage",
                     _text(language, "两侧都有计数，按本地接收时间配对。", "Both sides have counts, paired by local receipt time."))
        add_evidence(f"{prefix}_total", total, "contracts", f"样本{zh}总数", f"Sample {en} total",
                     _text(language, "限本批成对行权价。", "Limited to paired strikes in this batch."))
        put_share = distribution["put_total"] / total if total else None
        add_evidence(f"{prefix}_put_share", put_share, "fraction", f"样本看跌{zh}占比", f"Put share of sampled {en}",
                     _text(language, "分母仅含本字段有效的两侧配对计数。", "The denominator contains only valid paired side counts for this field."))
        add_evidence(f"{prefix}_top_share", distribution["top_strike_share"], "fraction", f"最大{zh}集中档占比", f"Largest-strike {en} share",
                     _text(language, "并列峰值全部保留。", "All tied peak strikes are retained."))
        add_evidence(f"{prefix}_top_two_share", distribution["top_two_strike_share"], "fraction", f"前两档{zh}占比", f"Top-two-strike {en} share",
                     _text(language, "在有配对计数的行权价中计算。", "Computed among strikes with paired counts."))
        add_evidence(f"{prefix}_hhi", distribution["hhi"], "index", f"{zh}行权价集中度", f"Strike concentration of {en}",
                     _text(language, "各行权价份额平方和，越大代表样本越集中。", "Sum of squared strike shares; larger values indicate greater concentration within this sample."))
        if pairs and total:
            peaks = ", ".join(f"{strike:g}" for strike in distribution["peak_strikes"])
            share = distribution["top_strike_share"] * 100
            finding(f"{prefix}_concentration", f"{zh}集中在什么位置", f"Where {en} is concentrated",
                    f"在 {pairs} 档两侧可比的行权价中，最高{zh}合计位于 {peaks}，单档占本样本 {share:.1f}%。这标出观察区域，需结合两侧数量和报价查看。",
                    f"Across {pairs} comparable paired strikes, peak combined {en} is at {peaks}. Each peak represents {share:.1f}% of this sample; inspect the side counts and quotes at those locations.",
                    [f"{prefix}_coverage", f"{prefix}_total", f"{prefix}_top_share"])
        elif total == 0:
            finding(f"{prefix}_zero", f"本批{zh}计数为零", f"Zero observed {en} counts",
                    f"{pairs} 档配对行权价返回的{zh}总数为零，因此没有可识别的集中峰值。",
                    f"The {pairs} paired strikes returned zero total {en}, so no concentration peak can be identified.",
                    [f"{prefix}_coverage", f"{prefix}_total"])
    add_evidence("positioning_coverage", positioning["coverage"], "fraction", "成交与持仓共同覆盖", "Common volume/OI coverage",
                 _text(language, "两个字段使用完全相同的行权价和两侧合约。", "Both fields use exactly the same strikes and sides."))
    for identifier, key, chinese, english in (
        ("common_volume_put_share", "put_volume_share", "共同样本看跌成交占比", "Put share of common-sample volume"),
        ("common_oi_put_share", "put_open_interest_share", "共同样本看跌持仓占比", "Put share of common-sample OI"),
        ("positioning_gap", "put_share_gap_pp", "看跌成交占比减持仓占比", "Put volume share minus OI share"),
    ):
        add_evidence(identifier, positioning[key], "percentage_points" if key.endswith("pp") else "fraction", chinese, english,
                     _text(language, "成交量是期间累计，未平仓量有独立统计周期；此比较描述结构差异。", "Volume accumulates during a period; OI has a separate reporting cycle. The comparison describes structural differences."))
    comparable_positioning = len(positioning["common_strikes"]) >= 2 and positioning["coverage"] >= .5
    pv, po, gap = (positioning[key] for key in ("put_volume_share", "put_open_interest_share", "put_share_gap_pp"))
    if comparable_positioning and gap is not None:
        divergence = (pv > .5 > po) or (po > .5 > pv)
        finding("activity_positioning", "成交活跃度与存量结构一起看", "Compare activity with outstanding positions",
                f"共同样本中，看跌成交占比 {pv * 100:.1f}%，看跌未平仓量占比 {po * 100:.1f}%，相差 {gap:+.1f} 个百分点。两种统计口径共同呈现了本批的结构。",
                f"In the common sample, puts account for {pv * 100:.1f}% of volume and {po * 100:.1f}% of OI, a {gap:+.1f} percentage-point gap. These two measures jointly describe the sample structure.",
                ["positioning_coverage", "common_volume_put_share", "common_oi_put_share", "positioning_gap"], conflict=divergence)
    skew = analysis.get("metrics", {}).get("iv_skew_25_delta", {}).get("value")
    skew = _number(skew)
    add_evidence("skew_25_delta", skew, "percentage_points", "近 25Δ 看跌 IV 减看涨 IV", "Near-25-delta put IV minus call IV",
                 _text(language, "沿用严格同模式、同 Greek 口径配对的偏斜。", "Uses the strictly paired same-mode, same-Greek-basis skew."))
    add_evidence("atm_iv", volatility["atm_iv"], "fraction", "近平值两侧平均 IV", "Mean near-ATM IV",
                 _text(language, "要求两侧接近半 Delta、行权价距标的在百分之一内。", "Both sides must be near half delta and the strike within one percent of spot."))
    straddle = _number(analysis.get("metrics", {}).get("atm_straddle", {}).get("value"))
    add_evidence("atm_straddle_pct", straddle, "percent", "平值跨式权利金占比", "ATM straddle premium share",
                 _text(language, "沿用同价、同步且价差受限的两腿报价中价。", "Uses synchronized same-strike leg midpoints with bounded spreads."))
    volume_distribution = distributions["volume"]
    vtotal = volume_distribution["total"]
    vshare = volume_distribution["put_total"] / vtotal if vtotal else None
    if volume_distribution["paired_strikes"] >= 2 and volume_distribution["coverage"] >= .5 and vshare is not None and skew is not None:
        if abs(vshare - .5) > 1e-9 and abs(skew) > 1e-9:
            align = (vshare > .5) == (skew > 0)
            finding("activity_pricing", "成交和相对定价是否呼应", "Activity and relative pricing",
                    f"配对成交中看跌占 {vshare * 100:.1f}%，近 25Δ 看跌 IV 减看涨 IV 为 {skew:+.2f} 个波动率点。两条线索{'偏向同一侧' if align else '偏向不同侧'}，需要结合对冲需求和计数口径解释。",
                    f"Puts represent {vshare * 100:.1f}% of paired volume; near-25-delta put IV minus call IV is {skew:+.2f} vol points. The two observations emphasize {'the same side' if align else 'different sides'}; hedging demand and counting conventions remain relevant.",
                    ["volume_coverage", "volume_put_share", "skew_25_delta"], conflict=not align)
    usable = any(distribution["paired_strikes"] >= 2 and distribution["coverage"] >= .5
                 and distribution["total"] is not None for distribution in distributions.values())
    usable = usable or liquidity["valid_contracts"] >= 2 or volatility["atm_iv"] is not None
    headline = _text(language, "本批数据可联合描述活动、存量分布与报价条件。", "This batch supports a joint description of activity, outstanding positions and quote conditions.")
    if conflicts:
        headline = _text(language, "本批活动、存量或相对定价存在分歧，应逐项核对依据。", "Activity, outstanding positions or relative pricing diverge in this batch; review each evidence set.")
    if not usable:
        headline = _text(language, "当前批次的可比证据不足，需补齐报价或配对计数。", "Comparable evidence is insufficient; obtain additional quotes or paired counts.")
    limitations = [
        _text(language, "结论覆盖本次到期日和抽样行权价；未覆盖的合约可能改变分布。", "Findings cover this expiry and sampled strikes; omitted contracts may change the distributions."),
        _text(language, "报价价差只描述显示报价的紧密度，成交容量需要报价数量和深度。", "Spreads describe displayed quote tightness; execution capacity requires size and depth."),
        _text(language, "持仓集中位置是样本观察区域，价格支撑阻力需要独立验证。", "OI concentrations identify sample observation areas; price support/resistance requires separate validation."),
        _text(language, "成交与持仓不能识别主动买卖、开平仓或组合交易，新闻情绪需要独立来源。", "Volume and OI do not identify aggressor side, opening/closing or multi-leg trades; news sentiment needs separate sources."),
    ]
    if status != "live":
        limitations.insert(0, _text(language, f"本批行情类型为 {status}，按该类快照描述。", f"This batch uses {status} data and is described as that snapshot type."))
    if excluded or ambiguous:
        limitations.append(_text(language, f"已排除 {excluded} 条范围外记录和 {ambiguous} 个重复合约键。", f"Excluded {excluded} out-of-scope rows and {ambiguous} duplicate contract keys."))
    return {
        "assessment": {"status": "descriptive" if usable else "insufficient", "headline": headline,
                       "findings": findings, "conflicts": conflicts, "limitations": limitations},
        "evidence": evidence, "liquidity": liquidity, "distributions": distributions,
        "positioning": positioning, "volatility": volatility,
        "context": {**scope, "received_at": snapshot.get("received_at")},
    }


def build_batch_comparison(reports, language="zh"):
    """Compare supported per-batch statistics; retain capture and sample scope."""
    rows, evidence, term_structure = [], [], []
    findings, conflicts = [], []
    for index, report in enumerate(reports):
        snapshot = report.get("snapshot", {})
        collective = report.get("collective", {})
        liquidity = collective.get("liquidity", {})
        volatility = collective.get("volatility", {})
        distribution = collective.get("distributions", {}).get("volume", {})
        total = distribution.get("total")
        row = {
            "report_index": index, "symbol": snapshot.get("symbol"), "expiration": snapshot.get("expiration"),
            "market_data_status": collective.get("context", {}).get("market_data_status", "unknown"),
            "received_at": snapshot.get("received_at"), "quote_coverage": liquidity.get("coverage"),
            "median_relative_spread_pct": liquidity.get("median_relative_spread_pct"),
            "put_volume_share": distribution.get("put_total") / total if total else None,
            "volume_pair_coverage": distribution.get("coverage"),
            "atm_iv": volatility.get("atm_iv"), "atm_moneyness_pct": volatility.get("atm_moneyness_pct"),
            "greeks_basis": volatility.get("greeks_basis"), "atm_received_at": volatility.get("atm_received_at"),
            "trading_class": snapshot.get("trading_class"), "currency": snapshot.get("currency"),
            "multiplier": snapshot.get("multiplier"),
            "descriptive": collective.get("assessment", {}).get("status") == "descriptive",
        }
        rows.append(row)
        for field, unit in (("quote_coverage", "fraction"), ("median_relative_spread_pct", "percent"),
                            ("put_volume_share", "fraction"), ("atm_iv", "fraction")):
            evidence.append({"id": f"report_{index + 1}_{field}", "label": field,
                             "value": row[field], "unit": unit,
                             "scope": {"report_index": index, "symbol": row["symbol"], "expiration": row["expiration"],
                                       "market_data_status": row["market_data_status"]},
                             "description": _text(language, "按各自抽样范围读取。", "Read within each report's own sample scope.")})
    for first in rows:
        for second in rows[first["report_index"] + 1:]:
            if first["symbol"] != second["symbol"] or first["expiration"] == second["expiration"]:
                continue
            near, far = sorted((first, second), key=lambda row: row["expiration"] or "")
            comparable = all(near[field] is not None and near[field] == far[field]
                             for field in ("currency", "trading_class", "multiplier", "greeks_basis", "market_data_status"))
            stamps = [_timestamp(row["atm_received_at"]) for row in (near, far)]
            comparable = comparable and near["market_data_status"] in MODE_LABELS.values()
            comparable = comparable and all(_positive(row["atm_iv"]) is not None for row in (near, far))
            comparable = comparable and all(stamp is not None for stamp in stamps) and _synchronized(*stamps)
            comparable = comparable and all(_number(row["atm_moneyness_pct"]) is not None for row in (near, far))
            if comparable:
                comparable = abs(near["atm_moneyness_pct"] - far["atm_moneyness_pct"]) <= 1
            gap = 100 * (far["atm_iv"] - near["atm_iv"]) if comparable else None
            if gap is not None and not isfinite(gap):
                gap, comparable = None, False
            term_structure.append({"near_report_index": near["report_index"], "far_report_index": far["report_index"],
                                   "far_minus_near_iv_pp": gap,
                                   "status": "comparable" if comparable else "insufficient",
                                   "reason": None if comparable else "expiry_iv_comparability_not_met"})
            if comparable:
                near_id, far_id = f"report_{near['report_index'] + 1}_atm_iv", f"report_{far['report_index'] + 1}_atm_iv"
                findings.append({"id": f"term_{near['report_index']}_{far['report_index']}",
                                 "title": _text(language, "同标的到期结构", "Same-underlying term structure"),
                                 "text": _text(language,
                                    f"{near['symbol']} 的 {far['expiration']} 近平值 IV 比 {near['expiration']} 高 {gap:+.2f} 个波动率点，口径与接收时间满足比较条件。",
                                    f"For {near['symbol']}, near-ATM IV at {far['expiration']} differs from {near['expiration']} by {gap:+.2f} vol points. Basis and receipt times meet comparison conditions."),
                                 "evidence_ids": [near_id, far_id]})
    if len(rows) >= 2:
        labels = [f"{row['symbol']} / {row['expiration']}" for row in rows]
        findings.insert(0, {
            "id": "sample_comparison", "title": _text(language, "联合样本范围", "Joint sample scope"),
            "text": _text(language,
                f"已联合整理 {'、'.join(labels)}。各组按自己的抽样范围保留报价覆盖和相对价差，跨组结论需先核对行情模式和接收时间。",
                f"Jointly reviewed {', '.join(labels)}. Each group retains its own quote coverage and relative spread; cross-group findings require matching feed modes and receipt times."),
            "evidence_ids": [f"report_{row['report_index'] + 1}_quote_coverage" for row in rows],
        })
    supported = sum(row["descriptive"] for row in rows)
    return {
        "assessment": {"status": "descriptive" if supported >= 2 else "insufficient",
                       "headline": _text(language, "按各样本覆盖范围联合查看，并仅比较符合口径的到期结构。", "Review the samples jointly within their coverage, comparing term IV only when definitions match."),
                       "findings": findings, "conflicts": conflicts,
                       "limitations": [
                           _text(language, "不同标的合约量级和抽样区间不同，原始数量需在各自样本内解释。", "Contract scale and sampled ranges differ across underlyings; interpret raw counts within each sample."),
                           _text(language, "批次按顺序采集，比较同时保留各批接收时间。", "Batches are collected sequentially; comparisons retain each batch's receipt time."),
                       ]},
        "rows": rows, "term_structure": term_structure, "evidence": evidence,
    }
