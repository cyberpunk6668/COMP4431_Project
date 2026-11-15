"""Closed synthetic option lessons and exact expiry-payoff arithmetic.

No model, broker, account, database or file access. Quote/IV fields are authored
teaching inputs, not a pricing-model calibration or received market quotes.
The saved shape deliberately reuses historical demo reports so existing chat
can read the same sample and the added h.lab.* local numeric evidence.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.options_history import HistoryDataset, analyze_history


VERSION = "17.0"
AS_OF = "2026-11-11T21:00:00Z"
DATES = ("2026-11-09", "2026-11-10", "2026-11-11")
EXPIRY = "2026-12-18"
STRIKES = (95, 100, 105, 110)
MULTIPLIER = 100
SCENARIO_IDS = ("put_activity", "wide_spread", "protection_cost")
STRATEGIES = ("long_call", "long_put", "call_debit_spread")
CENT = Decimal("0.01")
SOURCES = {
    "long_call": {"id":"oic.long_call", "title":"OIC: Long Call",
        "url":"https://www.optionseducation.org/strategies/all-strategies/long-call"},
    "long_put": {"id":"oic.long_put", "title":"OIC: Long Put",
        "url":"https://www.optionseducation.org/strategies/all-strategies/long-put"},
    "call_debit_spread": {"id":"oic.call_debit_spread", "title":"OIC: Bull Call Spread (Debit Call Spread)",
        "url":"https://www.optionseducation.org/strategies/all-strategies/bull-call-spread-debit-call-spread"},
}


def _t(language, zh, en):
    return en if language == "en" else zh


def _number(value):
    """Boundary serialization only; arithmetic remains Decimal throughout."""
    return None if value is None else float(value)


def _money(value):
    return None if value is None else format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def _source(language):
    return {"kind":"synthetic_demo", "synthetic":True, "verified":False,
        "label":_t(language,"合成教学数据 · 不是真实行情", "Synthetic teaching data · not market observations"),
        "as_of":AS_OF, "date_scope":_t(language,"固定虚构教学日期，不是交易所时间或当前数据", "Fixed fictional teaching date, not an exchange timestamp or current data")}


class LabEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    scenario_id: Literal["put_activity", "wide_spread", "protection_cost"] = "put_activity"
    strategy: Literal["long_call", "long_put", "call_debit_spread"] = "long_call"
    strike: Literal[95, 100, 105] = 100
    upper_strike: Literal[100, 105, 110] | None = None
    expiry_price: Decimal = Field(Decimal("105"), ge=0, le=1000, max_digits=7, decimal_places=2)
    contracts: int = Field(1, ge=1, le=10, strict=True)
    execution: Literal["natural", "midpoint"] = "natural"
    language: Literal["zh", "en"] = "zh"

    @field_validator("strike", "upper_strike", mode="before")
    @classmethod
    def integer_strike(cls, value):
        if value is not None and type(value) is not int:
            raise ValueError("Select an integer strike from the synthetic chain")
        return value

    @field_validator("expiry_price", mode="before")
    @classmethod
    def finite_price(cls, value):
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            raise ValueError("Expiry price must be a finite decimal")
        if isinstance(value, str) and len(value) > 24:
            raise ValueError("Expiry price is too long")
        return value

    @model_validator(mode="after")
    def matching_legs(self):
        if self.strategy == "call_debit_spread":
            if self.upper_strike is None or self.upper_strike <= self.strike:
                raise ValueError("Call debit spread needs a higher short-call strike")
        elif self.upper_strike is not None:
            raise ValueError("A single long option has no upper strike")
        return self


_SCENARIOS = {
    "put_activity": {
        "zh":("看跌成交更集中", "成交增加，不等于看空人数增加", "看跌成交占比变大，能确认什么？", "区分成交活动、持仓和交易意图。"),
        "en":("More put activity", "More contracts do not mean more bearish people", "What does a higher put-volume share establish?", "Separate contract activity, open interest and trade intent."),
    },
    "wide_spread": {
        "zh":("同一想法，不同成本", "报价变宽，先看买卖两侧", "中间价看起来便宜，为什么不一定买得到？", "理解买卖价差与成交价格假设的影响。"),
        "en":("Same idea, different entry cost", "Wider quotes change the cost assumption", "Why is the displayed midpoint not a guaranteed fill?", "Understand bid/ask spreads and execution assumptions."),
    },
    "protection_cost": {
        "zh":("下方保护的价格", "波动率更贵，仍不是方向预测", "看跌保护更贵，是否就代表一定会下跌？", "比较同到期、不同执行价的示例权利金与 IV。"),
        "en":("The price of downside protection", "Higher quoted volatility is not a direction forecast", "Does more expensive downside protection prove a future fall?", "Compare synthetic premiums and IV across strikes at one expiry."),
    },
}


def _scenario(scenario_id, language):
    if scenario_id not in _SCENARIOS:
        raise ValueError("Unknown option learning scenario")
    title, subtitle, question, goal = _SCENARIOS[scenario_id]["en" if language == "en" else "zh"]
    return {"id":scenario_id, "title":title, "subtitle":subtitle, "question":question, "learning_goal":goal}


def _inputs(request):
    return {"scenario_id":request.scenario_id, "strategy":request.strategy, "strike":request.strike,
        "upper_strike":request.upper_strike, "expiry_price":_number(request.expiry_price),
        "contracts":request.contracts, "execution":request.execution, "language":request.language}


def catalogue(language="zh"):
    return {"version":VERSION, "source":_source(language),
        "scenarios":[_scenario(key,language) for key in SCENARIO_IDS],
        "strategies":[{"id":key,"label":_t(language,zh,en)} for key,zh,en in (
            ("long_call","买入看涨", "Long call"), ("long_put","买入看跌", "Long put"),
            ("call_debit_spread","看涨借记价差", "Call debit spread"))],
        "defaults":_inputs(LabEvaluationRequest(language=language)),
        "constraints":{"strikes":[95,100,105],"upper_strikes":[100,105,110],"contracts":{"min":1,"max":10},
            "expiry_price":{"min":0,"max":1000,"step":0.01},"multiplier":MULTIPLIER,
            "executions":["natural","midpoint"]}}


def _quotes(scenario_id):
    protection = scenario_id == "protection_cost"
    calls = ("8", "4.5", "2", "1") if protection else ("6.5", "3.5", "1.5", ".6")
    puts = ("3", "4.5", "7", "11") if protection else ("1.5", "3.5", "6.5", "10.6")
    ivs = (".40", ".31", ".25", ".24") if protection else (".28", ".26", ".25", ".25")
    rows = []
    for i,strike in enumerate(STRIKES):
        for right,mids in (("C",calls),("P",puts)):
            mid = Decimal(mids[i])
            width = Decimal(".9") if scenario_id == "wide_spread" and i==3 and right=="C" else Decimal("1.2") if scenario_id == "wide_spread" else Decimal(".20")
            bid,ask = mid-width/2,mid+width/2
            volume = (100,120,90,70)[i] if right=="C" else (160,240,260,140)[i] if scenario_id=="put_activity" else (100,120,110,70)[i]
            rows.append({"strike":strike,"right":right,"bid":bid,"ask":ask,"mid":mid,"spread":width,
                "spread_percent":width/mid,"volume":volume,
                "open_interest":(900,1000,800,500)[i] if right=="C" else (850,1100,900,550)[i],
                "implied_volatility":Decimal(ivs[i])})
    return rows


def _public_quotes(quotes):
    return [{key:_number(value) if isinstance(value,Decimal) else value for key,value in quote.items()} for quote in quotes]


def _dataset(scenario_id, language):
    rows=[]
    for i,day in enumerate(DATES):
        for quote in _quotes(scenario_id):
            mid=quote["mid"]
            # Fixed paired contracts in every supplied date. These complete
            # artificial daily bars are not summaries of broker intraday bars.
            close=mid+Decimal(i-2)*Decimal(".05")
            volume=quote["volume"]
            if scenario_id=="put_activity" and quote["right"]=="P":
                volume=volume*(3,5,8)[i]//8
            rows.append({"trading_date":day,"strike":float(quote["strike"]),"right":quote["right"],
                "open":_number(close),"high":_number(close+Decimal(".10")),"low":_number(close-Decimal(".10")),"close":_number(close),
                "volume":float(volume),"open_interest":float(quote["open_interest"]),"oi_asof_date":day})
    return HistoryDataset(label=_t(language,"合成期权学习：", "Synthetic option lesson: ")+_scenario(scenario_id,language)["title"],
        symbol="DEMO",expiry=EXPIRY,source_label="Authored synthetic teaching inputs, not market observations",
        exported_at=AS_OF,rows=rows)


def _evidence(identifier,label,value,unit,description,language):
    return {"id":identifier,"label":label,"value":_number(value),"unit":unit,"description":description,
        "scope":"history","symbol":"DEMO","expiry":EXPIRY,"trading_date":DATES[-1],"synthetic":True}


def _metrics(quotes,language):
    volume=sum(quote["volume"] for quote in quotes)
    put_volume=sum(quote["volume"] for quote in quotes if quote["right"]=="P")
    atm=next(q for q in quotes if q["strike"]==100 and q["right"]=="C")
    put=next(q for q in quotes if q["strike"]==95 and q["right"]=="P")
    call=next(q for q in quotes if q["strike"]==105 and q["right"]=="C")
    values=(
        ("h.lab.put_volume_share",_t(language,"样本看跌成交占比", "Sample put-volume share"),Decimal(put_volume)/Decimal(volume),"fraction",
            _t(language,"最后教学日，固定合约窗口内的看跌成交量占比。", "Put volume as a share of the fixed last-day teaching sample."),
            _t(language,"计数的是合约，不是看空人数、主动买卖或新开仓方向。", "Counts contracts, not bearish people, aggressor side or opening intent.")),
        ("h.lab.atm_spread_percent",_t(language,"平值看涨价差 / 中间价", "ATM call spread / midpoint"),atm["spread_percent"],"fraction",
            _t(language,"合成买卖报价的宽度，除以该合约中间价。", "Width of the synthetic bid/ask pair divided by its midpoint."),
            _t(language,"报价是虚构输入；中间价不保证成交，也不能把历史成交条当作同步报价。", "Quotes are authored inputs. A midpoint is not a promised fill; historical bars are not synchronized quotes.")),
        ("h.lab.protection_iv_gap",_t(language,"下方看跌与上方看涨 IV 差", "Downside put / upside call IV gap"),(put["implied_volatility"]-call["implied_volatility"])*100,"percentage_points",
            _t(language,"比较 95 看跌与 105 看涨的合成 IV；假定标的为 100、同一到期日。", "Synthetic IV of the 95 put minus the 105 call; assumed underlying 100 and the same expiry."),
            _t(language,"IV 是给定教学输入，未从这些权利金校准；不是下跌概率或因果判断。", "IV is a supplied teaching input, not calibrated from these premiums, a downside probability or a causal conclusion.")),
    )
    return [{"id":key,"label":label,"value":_number(value),"unit":unit,"meaning":meaning,"limitation":limit} for key,label,value,unit,meaning,limit in values]


def _trial(request,quotes):
    qmap={(q["strike"],q["right"]):q for q in quotes}
    right="P" if request.strategy=="long_put" else "C"
    long=qmap[(request.strike,right)]
    long_basis="ask" if request.execution=="natural" else "mid"
    long_premium=long[long_basis]
    short=qmap[(request.upper_strike,"C")] if request.strategy=="call_debit_spread" else None
    short_basis="bid" if request.execution=="natural" else "mid"
    short_premium=short[short_basis] if short else Decimal(0)
    net=long_premium-short_premium
    width=Decimal(request.upper_strike-request.strike) if short else None
    # Even a closed synthetic scenario must not produce an invalid debit
    # spread, e.g. an upfront outlay exceeding its idealized terminal width.
    if net<=0 or (width is not None and net>=width):
        raise ValueError("Synthetic premiums do not form a valid positive debit spread")
    units=Decimal(request.contracts*MULTIPLIER)
    strike=Decimal(request.strike)
    def gross(price):
        return max(strike-price,Decimal(0)) if right=="P" else max(price-strike,Decimal(0))- (max(price-Decimal(request.upper_strike),Decimal(0)) if short else Decimal(0))
    cost=net*units
    payoff=gross(request.expiry_price)*units
    pnl=payoff-cost
    breakeven=strike-net if right=="P" else strike+net
    maxgain=(strike-net)*units if right=="P" else (width-net)*units if short else None
    points={Decimal(i) for i in range(0,201,5)}|{strike,breakeven,request.expiry_price}
    if short:points.add(Decimal(request.upper_strike))
    if request.expiry_price>200:points.update({request.expiry_price/2,request.expiry_price*Decimal(".75")})
    curve=[{"price":_number(price),"pnl":_number(gross(price)*units-cost)} for price in sorted(points)]
    legs=[{"right":right,"side":"long","strike":request.strike,"premium":_number(long_premium),"price_basis":"midpoint" if long_basis=="mid" else long_basis,"quantity":request.contracts}]
    if short:legs.append({"right":"C","side":"short","strike":request.upper_strike,"premium":_number(short_premium),"price_basis":"midpoint" if short_basis=="mid" else short_basis,"quantity":request.contracts})
    assumptions=[
        _t(request.language,"这是合成教学的到期日理想化现金盈亏，不能用于估算提前平仓价值。", "This is synthetic, idealized cash payoff at expiry, not a pre-expiry closing valuation."),
        _t(request.language,f"固定乘数 100，每腿等量 {request.contracts} 份，所有腿同一到期日；不包括现货持仓。", f"Fixed multiplier 100, {request.contracts} equal contracts per leg, one expiry; no underlying-stock position included."),
        _t(request.language,"不含手续费、税费、融资、股息、滑点、行权/指派、分腿执行或提前指派的额外风险；组合必须保持完整。", "Excludes fees, taxes, funding, dividends, slippage, exercise/assignment, legging and early-assignment risks; assumes the position remains intact."),
        _t(request.language,"natural 假设买入按 ask、卖出按 bid；midpoint 假设各腿按中间价成交，但不保证可实现。", "Natural assumes buying at ask and selling at bid; midpoint assumes midpoint fills for each leg, which are not guaranteed."),
        _t(request.language,"图中价格范围不是未来价格预测；最大收益取决于公式而非图的最高点。", "The chart range is not a price forecast; maximum gain comes from the formula, not the chart's highest point."),
    ]
    formula={"long_call":"[max(S_T - K, 0) - premium] × contracts × 100",
        "long_put":"[max(K - S_T, 0) - premium] × contracts × 100",
        "call_debit_spread":"[max(S_T - K_long, 0) - max(S_T - K_short, 0) - net_debit] × contracts × 100"}[request.strategy]
    amounts={"cost":cost,"break_even":breakeven,"max_loss":cost,"max_gain":maxgain,"pnl":pnl,"payoff":payoff,"net_premium":net}
    return {**_inputs(request),**{key:_number(value) for key,value in amounts.items()},"units":int(units),"multiplier":MULTIPLIER,
        "currency":"USD","amount_basis":"position_total_USD","price_basis":"underlying_USD_per_share",
        "max_gain_unlimited":maxgain is None,"outcome":"profit" if pnl>0 else "loss" if pnl<0 else "breakeven",
        "pnl_percent_of_cost":_number(pnl/cost),"curve":curve,"legs":legs,"formula":formula,
        "decimal_strings":{key:_money(value) for key,value in amounts.items()},"assumptions":assumptions,
        "sources":[deepcopy(SOURCES[request.strategy])]}


def _trial_evidence(trial,language):
    labels={"cost":("初始净支付总额", "Initial net debit"),"break_even":("到期盈亏平衡标的价", "Expiry breakeven underlying price"),
        "max_loss":("理想化到期最大损失", "Idealized maximum loss at expiry"),"max_gain":("理想化到期最大收益", "Idealized maximum gain at expiry"),
        "pnl":("输入到期价下的净盈亏", "Net P/L at the entered expiry price"),"payoff":("输入到期价下的到期现金值", "Expiry cash payoff at the entered price"),
        "expiry_price":("假设标的到期价", "Assumed underlying price at expiry"),"net_premium":("每股净权利金", "Net premium per share"),
        "contracts":("每腿合约份数", "Contracts per leg"),"strike":("买入腿执行价", "Long-leg strike"),"upper_strike":("卖出看涨腿执行价", "Short-call strike")}
    result=[]
    for key,pair in labels.items():
        value=trial.get(key)
        if value is None:continue  # Unlimited gain is a flag, not a missing numeric observation.
        description=_t(language,f"合成到期试算；固定乘数100、每腿{trial['contracts']}份。{'每股标的/报价美元' if key in {'break_even','expiry_price','net_premium','strike','upper_strike'} else '合约数量' if key=='contracts' else '整组总美元'}；不是市场价格或提前平仓估值。",
            f"Synthetic expiry calculation; multiplier 100 and {trial['contracts']} contracts per leg. {'Per-share USD' if key in {'break_even','expiry_price','net_premium','strike','upper_strike'} else 'Contract count' if key=='contracts' else 'Position-total USD'}; not market prices or a pre-expiry value.")
        result.append(_evidence("h.lab.trial."+key,_t(language,*pair),Decimal(str(value)),"contracts" if key=="contracts" else "USD",description,language))
    return result


def _insights(scenario_id, metrics, language):
    """Turn each teaching observation into a bounded reading task, not a signal."""
    put_activity = scenario_id == "put_activity"
    wide_spread = scenario_id == "wide_spread"
    protection_cost = scenario_id == "protection_cost"
    put_title = _t(language,
        "看跌合约更忙，原因还没确定" if put_activity else "成交分布不是本例的主角",
        "Busier put contracts, unresolved intent" if put_activity else "Volume is not this lesson's main clue")
    put_explanation = _t(language,
        "这份合成例子里，看跌成交占比连续三天上升，能确认的是活动向看跌合约集中，不是看空人数增加。下一步：展开专业数据，把看涨、看跌成交与未平仓量一起看；本例未平仓量不变，新增成交不等于新增持仓。" if put_activity else
        "这份合成例子里，看涨和看跌成交量接近，没有设置看跌活动持续集中的变化。不能仅因看跌略多就说情绪转空。下一步：把成交分布与本例的报价宽度分开看，先检查买卖两侧的成本。" if wide_spread else
        "这份合成例子里，看涨和看跌成交量接近，较贵的保护没有同时给出更多人看空的证据。下一步：把成交数量与保护的报价、IV 分开核对，不用其中一个数字替另一个作结论。",
        "In this synthetic example, put-volume share rises across the three teaching days. That establishes concentrated contract activity, not more bearish people. Next: expand the detailed data and compare call/put volume with open interest. OI stays unchanged here; extra trades are not extra open positions." if put_activity else
        "Call and put volume are close in this synthetic example; it does not introduce a sustained concentration of put activity. Slightly more puts do not establish bearish sentiment. Next: separate this volume mix from quote width, then inspect the entry cost on both sides of the quote." if wide_spread else
        "Call and put volume are close in this synthetic example. More expensive protection is not accompanied by evidence that more people are bearish. Next: inspect contract counts separately from protection quotes and IV; do not let one number stand in for another.")
    spread_title = _t(language,
        "买卖两侧拉开，进场代价就不同" if wide_spread else "先核对付出多少，再看盈亏",
        "Wider quotes change the entry cost" if wide_spread else "Check what you pay before reading P/L")
    spread_explanation = _t(language,
        "本例特意放宽合成 bid/ask，买入按 ask 要比显示的中间价付出更多，价差组合的卖出腿还要按 bid 计算。下一步：在试算里固定策略、行权价、到期价格与份数，只切换 natural（买卖报价）和 midpoint（中间价），比较整组成本与盈亏平衡价怎样移动。" if wide_spread else
        "本例报价较窄，也仍然存在买入价与卖出价的差别；标的到期上涨并不自动等于扣除权利金后赚钱。下一步：在试算里固定策略、行权价、到期价格与份数，只切换 natural（买卖报价）和 midpoint（中间价），比较成本、盈亏平衡价与净盈亏。",
        "This lesson deliberately widens synthetic bid/ask quotes. Buying at ask costs more than the displayed midpoint; a spread's short leg is also priced at bid. Next: hold strategy, strikes, expiry price and contract count fixed, switch only natural versus midpoint, and compare position cost and the movement in break-even price." if wide_spread else
        "The quotes are narrower here, but buying and selling still use different prices. A higher underlying price at expiry does not automatically mean a profit after premium. Next: keep strategy, strikes, expiry price and contract count fixed, switch only natural versus midpoint, and compare cost, break-even and net P/L.")
    protection_title = _t(language,
        "下方保护较贵，不是下跌概率" if protection_cost else "IV 差提供定价线索，不预测方向",
        "Pricier downside protection is not a fall probability" if protection_cost else "An IV gap is a pricing clue, not a forecast")
    protection_explanation = _t(language,
        "本例特意提高下方 95 看跌相对上方 105 看涨的给定 IV，并设置更贵的看跌保护；这是合成的保护定价线索，不能把 IV 差换算成下跌概率。下一步：展开专业数据，核对两者同到期但行权价不同；再选择买入看跌、行权价 95，查看支付成本和到期盈亏平衡价，不把 IV 差直接代入盈亏公式。" if protection_cost else
        "本例 95 看跌的给定 IV 略高于 105 看涨，只展示不同位置的保护定价差异，不能据此说接下来会跌。下一步：在专业数据里先核对这两份合约同到期、不同执行价，再切换到「下方保护的价格」情景比较；IV 差不能换算成下跌概率。",
        "This lesson deliberately raises the authored IV of the downside 95 put relative to the upside 105 call and sets pricier put protection. It is a synthetic protection-pricing clue; the IV gap cannot be converted into a probability of a fall. Next: check the detailed table for the same expiry but different strikes, then select a long 95 put and inspect its cost and expiry break-even. Do not insert the IV gap into the payoff formula." if protection_cost else
        "The authored IV of the 95 put is slightly higher than that of the 105 call. This illustrates protection pricing across strikes, not evidence of a coming fall. Next: check their same expiry and different strikes in the detailed table, then compare the Price of downside protection lesson. The IV gap cannot be converted into a probability of a fall.")
    copy = ((put_title, put_explanation), (spread_title, spread_explanation),
            (protection_title, protection_explanation))
    return [{"id":metric["id"],"title":title,"explanation":explanation,
             "limitation":metric["limitation"],"evidence_ids":[metric["id"]]}
            for metric,(title,explanation) in zip(metrics,copy)]


def build_scenario(scenario_id="put_activity", language="zh"):
    """Return a fresh, fully labelled synthetic report; does not persist it."""
    scenario=_scenario(scenario_id,language)
    quotes=_quotes(scenario_id)
    report=analyze_history(_dataset(scenario_id,language),source_kind="demo",language=language)
    metrics=_metrics(quotes,language)
    metric_evidence=[_evidence(m["id"],m["label"],Decimal(str(m["value"])),m["unit"],m["meaning"]+" "+m["limitation"],language) for m in metrics]
    insights=_insights(scenario_id,metrics,language)
    if scenario_id=="put_activity":
        # The reading task describes the whole teaching period, not only the
        # last-day share. Bind its trend/OI claims to the existing evidence.
        insights[0]["evidence_ids"].extend(
            [f"h.day.{index}.put_volume_share" for index in range(len(DATES))]
            + ["h.change.oi_total"])
    default=LabEvaluationRequest(scenario_id=scenario_id,language=language)
    trial=_trial(default,quotes)
    report["evidence"].extend(metric_evidence+_trial_evidence(trial,language))
    report["lab_context"]={"version":VERSION,"source":_source(language),"scenario":scenario,"synthetic":True,
        "dataset_as_of":AS_OF,"expiry":EXPIRY,"underlying_price":100,"currency":"USD","multiplier":MULTIPLIER,
        "metrics":metrics,"insights":insights,"quote_table":_public_quotes(quotes),"default_trial":_inputs(default),"trial":trial,
        "notices":[_t(language,"所有历史日线、报价、IV 与持仓都是人为构造的示例，不是 IBKR 或任何交易所返回。", "All bars, quotes, IV and OI are authored examples, not data returned by IBKR or an exchange."),
            _t(language,"示例 IV 是给定输入，未由权利金校准；不提供胜率、预测或买卖建议。", "Example IV is an authored input, not calibrated from premiums. No win probability, forecast or trade instruction is supplied.")]}
    return report


def evaluate(request: LabEvaluationRequest | dict):
    """Rebuild a scenario plus exact trial evidence; no side effects or calls."""
    if not isinstance(request,LabEvaluationRequest):request=LabEvaluationRequest.model_validate(request)
    report=build_scenario(request.scenario_id,request.language)
    trial=_trial(request,_quotes(request.scenario_id))
    report["lab_context"]["trial"]=trial
    report["evidence"]=[item for item in report["evidence"] if not item["id"].startswith("h.lab.trial.")]+_trial_evidence(trial,request.language)
    return report
