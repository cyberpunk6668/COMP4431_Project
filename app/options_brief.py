"""Plain-language, evidence-linked descriptions of options report snapshots.

This layer explains existing cohort calculations. It does not estimate a price
direction, investor count, trading intention or probability from option counts.
"""
from collections.abc import Mapping
from datetime import datetime, timezone
from math import isfinite


KNOWN_MODES = {"live", "delayed", "frozen", "delayed_frozen"}


def _text(language, chinese, english):
    return english if language == "en" else chinese


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return float(value) if isfinite(value) else None
    except OverflowError:
        return None


def _fraction(value):
    value = _number(value)
    return value if value is not None and 0 <= value <= 1 else None


def _display(value, decimals=1):
    return f"{value:.{decimals}f}".rstrip("0").rstrip(".") if decimals else f"{value:.0f}"


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.utcoffset() is not None else None


def _refs(report, identifiers, prefix="g0."):
    available = {item.get("id") for item in report.get("collective", {}).get("evidence", []) if isinstance(item, Mapping)}
    return [prefix + identifier for identifier in identifiers if identifier in available]


def _card(identifier, question, answer, meaning, evidence_ids, tone="neutral", details="", visual=None):
    result = {"id": identifier, "question": question, "answer": answer, "meaning": meaning,
              "evidence_ids": evidence_ids, "tone": tone, "details": details}
    if visual is not None:
        result["visual"] = visual
    return result


def _freshness(report, language, now):
    mode = report.get("quality", {}).get("market_data_status", "unknown")
    snapshot = report.get("snapshot", {})
    stamp = _timestamp(snapshot.get("received_at"))
    age = (now - stamp).total_seconds() if stamp is not None else _number(report.get("capture_age_seconds"))
    if age is not None and age < 0:
        age = None
    maximum_age = _number(report.get("quality", {}).get("freshness_seconds")) or 30
    historical = age is None or age > maximum_age
    labels = {
        "live": ("实时来源", "Live source"),
        "delayed": ("延迟资料", "Delayed data"),
        "frozen": ("已冻结的报价", "Frozen quotes"),
        "delayed_frozen": ("延迟且已冻结的报价", "Delayed frozen quotes"),
        "mixed": ("混合行情来源", "Mixed feed types"),
        "unknown": ("行情来源未确认", "Unconfirmed feed type"),
        "unavailable": ("还没有可用行情", "No usable market data"),
    }
    label = _text(language, *labels.get(mode, labels["unknown"]))
    if mode not in KNOWN_MODES:
        meaning = _text(language, "需要先确认资料类型，再解释交易与价格。", "Confirm the data type before interpreting activity and prices.")
    elif age is None:
        meaning = _text(language, "缺少可靠的本地接收时间，暂时无法确认这份快照有多新。", "A reliable local receipt time is missing, so the age of this snapshot is unclear.")
    elif historical:
        label += _text(language, " · 较早采集", " · Earlier capture")
        meaning = _text(language, "这份快照已超出本地接收时效阈值，适合回看采集时的结构；查看此刻状况前请重新获取。", "This snapshot exceeds the local receipt freshness window. It describes the structure at capture; collect again before assessing the present.")
    elif mode == "live":
        meaning = _text(language, "IBKR 将来源标为实时，本机近期收到了这批数据。接收时间仍不能测量交易所到本机的完整延迟。", "IBKR labels the source live, and this computer received the batch recently. Receipt time does not measure the full exchange-to-computer delay.")
    else:
        meaning = _text(language, "本机刚收到资料，也可能是较早的市场报价。请按这份带时间标记的样本阅读。", "Recently received data can still contain earlier market quotes. Read this as a time-labelled sample.")
    return {"mode": mode, "label": label, "meaning": meaning,
            "tone": "available" if mode == "live" and not historical else "attention",
            "received_at": snapshot.get("received_at"), "age_seconds": age,
            "historical": historical}


def _supported_distribution(distribution):
    total = _number(distribution.get("total"))
    coverage = _fraction(distribution.get("coverage"))
    paired = _number(distribution.get("paired_strikes"))
    return total is not None and total >= 0 and coverage is not None and coverage >= .5 and paired is not None and paired >= 2


def _activity(report, language, mode):
    distribution = report.get("collective", {}).get("distributions", {}).get("volume", {})
    refs = _refs(report, ["volume_coverage", "volume_total", "volume_put_share"])
    question = _text(language, "哪一类合约交易更多？", "Which type of option traded more?")
    if mode not in KNOWN_MODES or not _supported_distribution(distribution):
        return _card("activity", question,
                     _text(language, "这次还看不清两类合约的成交构成。", "The mix of put and call trading is not clear in this batch."),
                     _text(language, "需要同一范围内足够多的看涨、看跌合约都有成交量，才能公平比较。", "Enough calls and puts need volume data in the same sample window for a fair comparison."), refs, "attention")
    total = distribution["total"]
    coverage = distribution["coverage"]
    detail = _text(language, f"使用了 {_display(distribution['paired_strikes'], 0)} 档成对合约，覆盖本次请求范围的 {_display(coverage * 100)}%。", f"Uses {_display(distribution['paired_strikes'], 0)} paired strikes, covering {_display(coverage * 100)}% of the requested window.")
    if total == 0:
        return _card("activity", question,
                     _text(language, "已返回的成交计数为零。", "The returned trade counts are zero."),
                     _text(language, "零成交计数无法形成两侧成交占比，也不代表投资者没有兴趣。", "Zero trade counts do not provide a put/call mix and do not establish a lack of investor interest."), refs, "attention", detail)
    put_total = _number(distribution.get("put_total"))
    if put_total is None or not 0 <= put_total <= total:
        return _card("activity", question, _text(language, "两侧成交计数不完整。", "The two trade counts are incomplete."),
                     _text(language, "补齐同一范围的成交量后再作比较。", "Complete volume data in the same window before comparing."), refs, "attention")
    put_percent = round(100 * put_total / total, 1)
    call_percent = round(100 - put_percent, 1)
    answer = _text(language,
        f"按比例折算，本次每 100 份样本成交合约中，约 {_display(put_percent)} 份是看跌期权，{_display(call_percent)} 份是看涨期权。",
        f"Rescaled to 100 traded contracts in this sample, about {_display(put_percent)} are puts and {_display(call_percent)} are calls.")
    meaning = _text(language, "这告诉你哪类合约更活跃。每笔交易都有买方和卖方，这些计数不能说明买卖双方分别想做什么。", "This describes which contract type was more active. Every trade has a buyer and seller; these counts do not show what each buyer or seller intends.")
    visual = {"type": "parts", "first_label": _text(language, "看跌合约", "Put contracts"), "first_value": put_percent,
              "second_label": _text(language, "看涨合约", "Call contracts"), "second_value": call_percent,
              "unit": _text(language, "每 100 份样本成交合约，按比例折算", "Per 100 sampled traded contracts, rescaled")}
    return _card("activity", question, answer, meaning, refs, "available", detail, visual)


def _concentration(report, language, mode):
    distribution = report.get("collective", {}).get("distributions", {}).get("volume", {})
    refs = _refs(report, ["volume_coverage", "volume_total", "volume_top_share"])
    question = _text(language, "交易集中在哪里？", "Where is trading concentrated?")
    if mode not in KNOWN_MODES or not _supported_distribution(distribution):
        return _card("concentration", question, _text(language, "还缺少足够的成对成交资料。", "There is not enough paired volume data yet."),
                     _text(language, "覆盖太少时，看到的热点可能只是遗漏合约造成的。", "With too little coverage, an apparent hotspot may reflect missing contracts."), refs, "attention")
    if distribution["total"] == 0:
        return _card("concentration", question, _text(language, "本次没有可比较的成交热点。", "This batch has no trade-count hotspot to compare."),
                     _text(language, "已返回的成交总数为零，无法算出哪个价位占比更多。", "The returned total is zero, so a larger share cannot be assigned to any strike."), refs, "neutral")
    share = _fraction(distribution.get("top_strike_share"))
    peaks = [strike for strike in distribution.get("peak_strikes", []) if _number(strike) is not None]
    if share is None or not peaks:
        return _card("concentration", question, _text(language, "暂时无法定位成交最多的约定价格。", "The busiest strike cannot be identified yet."),
                     _text(language, "请先查看成交明细的覆盖范围。", "Check the coverage of the trade counts first."), refs, "attention")
    locations = "、".join(_display(strike, 2) for strike in peaks[:3])
    if len(peaks) > 3:
        locations += _text(language, "等", " and others")
    answer = _text(language,
        f"成交最多的合约约定价格是 {locations}；每个并列价位各占样本成交的 {_display(share * 100)}%。" if len(peaks) > 1 else f"成交最多的合约约定价格是 {locations}，占样本成交的 {_display(share * 100)}%。",
        f"The busiest strike price is {locations}; each tied strike accounts for {_display(share * 100)}% of sampled volume." if len(peaks) > 1 else f"The busiest strike price is {locations}, accounting for {_display(share * 100)}% of sampled volume.")
    meaning = _text(language, "合约约定价格也叫行权价。这里标出交易较多的合约位置，不能直接当作股价目标或支撑、阻力位。", "The agreed contract price is called the strike. This locates active contracts; it does not establish a stock-price target or support/resistance level.")
    return _card("concentration", question, answer, meaning, refs, "available")


def _pricing(report, language, mode):
    question = _text(language, "期权价格透露了什么？", "What do the option prices show?")
    metric = report.get("metrics", {}).get("iv_skew_25_delta", {})
    skew = _number(metric.get("value"))
    refs = _refs(report, ["skew_25_delta"])
    if mode in KNOWN_MODES and metric.get("market_data_status") == mode and skew is not None:
        if skew > 0:
            answer = _text(language, "按同一口径比较，这对合约中看跌一侧的相对定价更高。", "On a like-for-like basis, the put in this pair has a higher relative pricing measure.")
        elif skew < 0:
            answer = _text(language, "按同一口径比较，这对合约中看涨一侧的相对定价更高。", "On a like-for-like basis, the call in this pair has a higher relative pricing measure.")
        else:
            answer = _text(language, "按同一口径比较，这对合约的相对定价指标相同。", "The two comparable options have the same relative pricing measure.")
        meaning = _text(language, "为便于比较，系统把这对合约的报价换算成同一指标：隐含波动率（IV）。它反映报价中包含的波动程度，保护需求、供需和报价条件都可能影响它。", "The system converts the two quotes into a common measure, implied volatility (IV), for comparison. It describes the degree of movement priced into the quotes; protection demand, supply and quote conditions can all affect it.")
        return _card("pricing", question, answer, meaning, refs, "available")
    straddle = report.get("metrics", {}).get("atm_straddle", {})
    premium_share = _number(straddle.get("value"))
    if mode in KNOWN_MODES and straddle.get("market_data_status") == mode and premium_share is not None and premium_share >= 0:
        return _card("pricing", question,
            _text(language, f"在同一约定价格上，一份看涨加一份看跌的合计报价中间价，约为标的参考价的 {_display(premium_share)}%。", f"At the same strike, the combined midpoint of one call and one put is about {_display(premium_share)}% of the underlying reference price."),
            _text(language, "这反映两份期权的合计权利金尺度。它不能直接当作上涨概率或到期价格范围。", "This describes the combined premium scale. It is not an upside probability or a forecast price range."),
            _refs(report, ["atm_straddle_pct"]), "available")
    return _card("pricing", question,
        _text(language, "这次还无法可靠比较两侧期权的相对定价。", "Relative pricing of the two sides cannot be compared reliably in this batch."),
        _text(language, "缺少合格的买卖报价或可比波动率时，交易计数仍可阅读，价格方面的结论需要等待补齐数据。", "Trade counts can still be read when qualifying quotes or comparable volatility are missing. Pricing conclusions need those fields first."), refs, "attention")


def _agreement(report, language, mode):
    positioning = report.get("collective", {}).get("positioning", {})
    question = _text(language, "这些线索是一致的吗？", "Do these observations agree?")
    refs = _refs(report, ["positioning_coverage", "common_volume_put_share", "common_oi_put_share", "positioning_gap"])
    pv, po = (_fraction(positioning.get(key)) for key in ("put_volume_share", "put_open_interest_share"))
    coverage = _fraction(positioning.get("coverage"))
    common = positioning.get("common_strikes", [])
    if mode not in KNOWN_MODES or pv is None or po is None or coverage is None or coverage < .5 or len(common) < 2:
        return _card("agreement", question,
            _text(language, "还缺少同一范围的交易和未结清合约资料。", "Matching activity and outstanding-contract data are still incomplete."),
            _text(language, "成交量反映一段时间里的交易，未平仓量反映尚未结清的合约。先用同一范围比较，才能解释它们的差别。", "Volume describes trades during a period; open interest describes outstanding contracts. Compare the same contract window before explaining differences."), refs, "attention")
    split = (pv > .5 > po) or (po > .5 > pv)
    if split:
        volume_side = _text(language, "看跌", "puts") if pv > .5 else _text(language, "看涨", "calls")
        interest_side = _text(language, "看跌", "puts") if po > .5 else _text(language, "看涨", "calls")
        answer = _text(language, f"这次成交更偏向{volume_side}合约，尚未结清的合约却更偏向{interest_side}合约。", f"Trading is weighted toward {volume_side}, while outstanding contracts are weighted toward {interest_side}.")
        meaning = _text(language, "两者统计时点和用途不同，可以同时存在。先保留这种分歧，别把其中一项当成所有参与者的共同方向。", "The measures have different reporting periods and uses and can coexist. Retain the difference rather than treating either as a shared intention of all participants.")
    elif (pv > .5 and po > .5) or (pv < .5 and po < .5):
        side = _text(language, "看跌", "puts") if pv > .5 else _text(language, "看涨", "calls")
        answer = _text(language, f"这次成交与尚未结清的合约，在构成上都更偏向{side}合约。", f"Activity and outstanding contracts are both weighted toward {side} in this sample.")
        meaning = _text(language, "这是合约构成上的呼应。每笔交易仍有买卖双方，因此同侧占比不能直接告诉你参与者想让价格往哪走。", "This is agreement in contract mix. Every trade still has two sides, so shared contract weights do not reveal participants' intended price direction.")
    else:
        answer = _text(language, "至少一类统计中的两侧占比相同，暂时没有一致的侧别偏重。", "At least one measure has equal put and call shares, so there is no common side emphasis.")
        meaning = _text(language, "把它理解为本批结构较均衡或信息尚未形成同侧呼应，再查看报价和覆盖范围。", "Read this as a balanced mix or a lack of shared side emphasis, then check quotes and coverage.")
    return _card("agreement", question, answer, meaning, refs, "attention" if split else "available")


def _glossary(language):
    definitions = [
        ("看涨期权 / 看跌期权", "Call / put options", "分别赋予按约定价格买入或卖出标的的权利；一份成交合约同时有买方和卖方。", "They give the holder the right to buy or sell the underlying at an agreed price. Every traded contract has a buyer and seller."),
        ("成交量", "Trading volume", "一段时间内交易的合约数量；每笔成交都有买方和卖方，计数不会直接告诉你谁主动买入。", "The number of contracts traded during a period. Every trade has a buyer and seller; the count does not identify who initiated it."),
        ("到期日", "Expiration", "合约权利终止的日期。每组报告只分析选定到期日的期权。", "The date on which the contract rights expire. Each report group covers options at its selected expiration."),
        ("行权价", "Strike price", "合约事先约定的买入或卖出价格。它与股票当前价格不同。", "The buying or selling price agreed in the contract, separate from the current stock price."),
        ("未平仓量", "Open interest", "尚未结清的合约总数，按独立的统计周期更新。", "The number of outstanding contracts, updated on its own reporting cycle."),
        ("隐含波动率（IV）", "Implied volatility (IV)", "从期权价格折算出的波动定价指标，通常按年表示；它本身不指明上涨或下跌方向。", "A volatility pricing measure inferred from option prices, usually annualized. It does not specify an up or down direction."),
        ("买卖价差", "Bid/ask spread", "当前卖方要价与买方出价的距离。差距越大，屏幕上的价格越难代表一个确定可成交的价格。", "The gap between the asking and bidding prices. A wider gap makes a displayed quote less representative of a definite executable price."),
    ]
    return [{"term": _text(language, zh, en), "meaning": _text(language, zh_meaning, en_meaning)}
            for zh, en, zh_meaning, en_meaning in definitions]


def build_plain_brief(report, language="zh", *, now=None):
    """Explain one selected-expiry report using its existing validated cohorts."""
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("A timezone-aware clock is required")
    freshness = _freshness(report, language, now)
    mode = freshness["mode"]
    cards = [_activity(report, language, mode), _concentration(report, language, mode),
             _pricing(report, language, mode), _agreement(report, language, mode)]
    descriptive = report.get("collective", {}).get("assessment", {}).get("status") == "descriptive"
    supported = descriptive and mode in KNOWN_MODES
    readable_card = next((cards[index] for index in (3, 0, 2, 1) if cards[index]["tone"] == "available"), None)
    headline = readable_card["answer"] if readable_card else _text(language, "这次能先看报价完整程度，其余线索仍需补齐。", "This batch can first show quote completeness; the other observations need more data.")
    if supported and cards[3]["tone"] == "attention" and cards[3]["evidence_ids"]:
        positioning = report.get("collective", {}).get("positioning", {})
        pv, po = (_fraction(positioning.get(key)) for key in ("put_volume_share", "put_open_interest_share"))
        if pv is not None and po is not None and ((pv > .5 > po) or (po > .5 > pv)):
            headline = cards[3]["answer"]
    if not supported:
        headline = _text(language, "这次资料还不足以拼出可比较的样本结构。", "There is not enough comparable evidence to describe this sample yet.")
    elif freshness["historical"]:
        headline = _text(language, "这是一份较早的快照。以下描述对应采集时的样本。", "This is an earlier snapshot. The descriptions below refer to the sample at capture.")
    next_steps = []
    if mode != "live" or freshness["historical"]:
        next_steps.append(_text(language, "先确认资料时间；若要看此刻状况，重新获取并核对实时行情权限。", "Check the data time first. For present conditions, collect again and verify live-data permissions."))
    liquidity = report.get("collective", {}).get("liquidity", {})
    if (_fraction(liquidity.get("coverage")) or 0) < .5:
        next_steps.append(_text(language, "先补齐有效买价与卖价，再阅读价格和波动结构。", "Obtain valid bids and asks before interpreting pricing and volatility."))
    next_steps.append(_text(language, "点开结论旁的依据，确认它覆盖的是哪些合约。", "Open the evidence beside each conclusion to check which contracts it covers."))
    snapshot = report.get("snapshot", {})
    return {
        "title": _text(language, "先看懂这批期权", "Understand this options sample"),
        "headline": headline, "scope": {"symbol": snapshot.get("symbol"), "expiration": snapshot.get("expiration")},
        "status": "descriptive" if supported and not freshness["historical"] else "limited",
        "freshness": freshness, "cards": cards, "next_steps": next_steps,
        "glossary": _glossary(language),
        "evidence_ids": list(dict.fromkeys(identifier for card in cards for identifier in card["evidence_ids"])),
    }


def build_batch_plain_brief(reports, comparison, failures, language="zh", *, now=None):
    """Explain comparisons without pooling different underlying contract counts."""
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("A timezone-aware clock is required")
    briefs = [build_plain_brief(report, language, now=now) for report in reports]
    items = []
    for index, brief in enumerate(briefs):
        refs = [identifier.replace("g0.", f"g{index}.", 1) for identifier in brief["evidence_ids"]]
        items.append({**brief["scope"], "status": brief["status"], "headline": brief["headline"],
                      "activity": brief["cards"][0]["answer"], "pricing": brief["cards"][2]["answer"],
                      "freshness": brief["freshness"], "evidence_ids": refs})
    supported = sum(brief["status"] == "descriptive" for brief in briefs)
    total = len(reports) + len(failures)
    headline = _text(language, f"本次收到 {len(reports)} 组资料，{supported} 组可作带时点的样本解读。", f"Received {len(reports)} groups; {supported} support a time-labelled sample description.")
    if not reports:
        headline = _text(language, "这次还没有取得可比较的资料。", "No comparable data was collected in this batch.")
    modes = {brief["freshness"]["mode"] for brief in briefs}
    all_recent = bool(briefs) and all(not brief["freshness"]["historical"] for brief in briefs)
    freshness = {
        "mode": next(iter(modes)) if len(modes) == 1 else "mixed" if modes else "unavailable",
        "label": briefs[0]["freshness"]["label"] if len(modes) == 1 else _text(language, "各组行情类型不同", "The groups use different feed types") if modes else _text(language, "还没有可用行情", "No usable market data"),
        "meaning": _text(language, "各组按顺序采集，不能把它们当作同一瞬间的全市场画面。", "Groups are captured sequentially and do not form a simultaneous picture of the whole market."),
        "tone": "available" if modes == {"live"} and all_recent else "attention",
        "historical": not all_recent,
    }
    coverage = [_fraction(report.get("collective", {}).get("liquidity", {}).get("coverage")) for report in reports]
    enough_quotes = sum(value is not None and value >= .5 for value in coverage)
    all_refs = list(dict.fromkeys(identifier for item in items for identifier in item["evidence_ids"]))
    coverage_refs = [f"comparison.report_{index + 1}_quote_coverage" for index in range(len(reports))
                     if any(item.get("id") == f"report_{index + 1}_quote_coverage" for item in comparison.get("evidence", []))]
    cards = [_card("batch_coverage", _text(language, "这次比较的信息够完整吗？", "Is there enough data for this comparison?"),
                   _text(language, f"收到的 {len(reports)} 组中，{enough_quotes} 组至少一半合约有近期有效买卖报价。", f"Of {len(reports)} received groups, {enough_quotes} have recent valid bids and asks for at least half their contracts."),
                   _text(language, "报价齐全程度只说明数据覆盖，不能当成预测正确率。成交和持仓资料可以有不同的覆盖范围。", "Quote completeness describes coverage, not predictive accuracy. Volume and inventory can have different coverage."),
                   coverage_refs, "available" if reports and enough_quotes == len(reports) else "attention")]
    eligible = []
    for index, report in enumerate(reports):
        distribution = report.get("collective", {}).get("distributions", {}).get("volume", {})
        mode = report.get("quality", {}).get("market_data_status")
        if mode in KNOWN_MODES and _supported_distribution(distribution) and distribution["total"] > 0:
            put_total = _number(distribution.get("put_total"))
            if put_total is not None and 0 <= put_total <= distribution["total"]:
                eligible.append((put_total / distribution["total"], index, report))
    if len(eligible) >= 2:
        low, high = min(eligible, key=lambda item: item[0]), max(eligible, key=lambda item: item[0])
        def label(item):
            snapshot = item[2].get("snapshot", {})
            return f"{snapshot.get('symbol', '')} / {snapshot.get('expiration', '')}"
        answer = _text(language,
            f"在各自样本内，{label(low)} 的看跌合约占成交 {_display(low[0] * 100)}%，{label(high)} 为 {_display(high[0] * 100)}%。",
            f"Within each sample, puts account for {_display(low[0] * 100)}% of volume in {label(low)}, and {_display(high[0] * 100)}% in {label(high)}.")
        if low[0] == high[0]:
            answer = _text(language, f"在各自时点的样本内，可比较组别的看跌合约成交占比均约为 {_display(low[0] * 100)}%。", f"Within their own time-labelled samples, the eligible groups have the same put share of volume, about {_display(low[0] * 100)}%.")
        refs = [f"g{index}.volume_put_share" for _, index, report in eligible
                if _refs(report, ["volume_put_share"])]
        cards.append(_card("batch_activity", _text(language, "各组的交易构成有何不同？", "How does the trade mix differ?"), answer,
            _text(language, "这是各自时点的比例对照。每组约定价格范围、标的和行情类型可能不同，不能据此把原始数量合并或判断哪个标的更看空。", "This compares shares at each group's own capture time. Strikes, underlyings and feed types may differ; raw counts cannot be pooled into a directional ranking."), refs, "available"))
    else:
        cards.append(_card("batch_activity", _text(language, "各组的交易构成有何不同？", "How does the trade mix differ?"),
            _text(language, "至少还需要两组有足够成对成交资料，才能对照交易构成。", "At least two groups need enough paired volume data to compare their trade mix."),
            _text(language, "先分别阅读下方各组结果，缺失数据不会自动按零计算。", "Read the groups separately below. Missing counts are not treated as zero."), [], "attention"))
    comparable_terms = [item for item in comparison.get("term_structure", []) if item.get("status") == "comparable" and _number(item.get("far_minus_near_iv_pp")) is not None]
    question = _text(language, "不同到期日的价格该怎样比较？", "How can pricing be compared across expirations?")
    if comparable_terms:
        term = comparable_terms[0]
        near_index, far_index = term["near_report_index"], term["far_report_index"]
        gap = term["far_minus_near_iv_pp"]
        if gap == 0:
            answer = _text(language, "一对符合比较条件的到期日，平值参考 IV 相同。", "A comparable pair of expirations has the same near-ATM reference IV.")
        else:
            direction = _text(language, "高", "higher") if gap > 0 else _text(language, "低", "lower")
            answer = _text(language, f"在一对符合条件的同标的到期日中，较远到期日的平值 IV 比较近到期日{direction} {_display(abs(gap), 2)} 个波动率百分点。", f"For a qualifying pair on the same underlying, the later expiry's near-ATM IV is {_display(abs(gap), 2)} volatility percentage points {direction} than the earlier expiry's.")
        refs = [f"comparison.report_{index + 1}_atm_iv" for index in (near_index, far_index)]
        cards.append(_card("batch_pricing", question, answer,
            _text(language, "IV 是期权价格折算出的波动定价。同标的、口径和时间满足条件，才显示这种期限差异。", "IV is a volatility measure inferred from option prices. This expiration difference is shown only when underlying, definitions and receipt times qualify."), refs, "available"))
    else:
        cards.append(_card("batch_pricing", question,
            _text(language, "这次没有满足比较条件的同标的到期日配对。", "No same-underlying expiration pair meets the comparison requirements."),
            _text(language, "不同公司、报价缺失或口径不一致时，不能把数字直接放在一起解释为期限变化。", "Different companies, missing quotes or inconsistent definitions prevent interpreting the figures as an expiration effect."), [], "attention"))
    next_steps = []
    if failures:
        next_steps.append(_text(language, f"有 {len(failures)} 组未取得资料，先查看对应的失败原因。", f"Data was unavailable for {len(failures)} groups; review those diagnostics first."))
    next_steps.extend([_text(language, "逐组确认到期日、行情类型和采集时间，再比较比例。", "Check each expiry, feed type and capture time before comparing shares."),
                       _text(language, "点开结论旁的依据，核对它属于哪个标的和到期日。", "Open the evidence beside a conclusion to confirm its underlying and expiry.")])
    return {"title": _text(language, "把几组期权放在一起看", "Understand the options groups together"),
            "headline": headline, "scope": {"groups": total}, "status": "descriptive" if supported >= 2 and not failures else "limited",
            "freshness": freshness, "cards": cards, "items": items, "next_steps": next_steps,
            "glossary": _glossary(language), "evidence_ids": all_refs + coverage_refs}
