"""Independent expiry arithmetic and closed-data tests; no broker/model needed."""
from copy import deepcopy
from decimal import Decimal
import json
import math

import pytest
from pydantic import ValidationError

from app.options_lab import (
    AS_OF, DATES, EXPIRY, SCENARIO_IDS, LabEvaluationRequest,
    build_scenario, catalogue, evaluate,
)


def trial(**kwargs):
    return evaluate(LabEvaluationRequest(**kwargs))["lab_context"]["trial"]


@pytest.mark.parametrize("language", ["zh", "en"])
def test_catalogue_identifies_synthetic_dates_choices_and_no_current_claim(language):
    data=catalogue(language)
    assert data["version"]=="17.0"
    assert data["source"]["synthetic"] and not data["source"]["verified"]
    assert data["source"]["kind"]=="synthetic_demo" and data["source"]["as_of"]==AS_OF
    assert {s["id"] for s in data["scenarios"]}==set(SCENARIO_IDS)
    assert {s["id"] for s in data["strategies"]}=={"long_call","long_put","call_debit_spread"}
    for scenario in data["scenarios"]:
        assert scenario["title"] and scenario["question"] and scenario["learning_goal"]
    request=LabEvaluationRequest.model_validate(data["defaults"])
    assert request.upper_strike is None and request.contracts==1 and request.expiry_price==105


@pytest.mark.parametrize("scenario", SCENARIO_IDS)
def test_report_fixed_paired_sample_and_quote_metrics_are_auditable(scenario):
    r=build_scenario(scenario)
    assert r["analysis_kind"]=="historical_options" and r["source"]["kind"]=="demo"
    assert not r["source"]["verified"] and r["symbol"]=="DEMO" and r["expiry"]==EXPIRY
    assert r["period"]=={"start":DATES[0],"end":DATES[-1]}
    assert len(r["rows"])==24 and len(r["daily"])==3
    assert all(d["common_contracts"]==8 for d in r["daily"])
    assert all(d["oi_total"]==6600 for d in r["daily"])
    ctx=r["lab_context"]
    assert ctx["source"]["synthetic"] and ctx["synthetic"]
    quotes=ctx["quote_table"]
    assert len(quotes)==8
    for q in quotes:
        assert 0<=q["bid"]<q["mid"]<q["ask"]
        assert q["spread"]==pytest.approx(q["ask"]-q["bid"])
        assert q["spread_percent"]==pytest.approx(q["spread"]/q["mid"])
        assert 0<q["implied_volatility"]<1
        assert type(q["volume"]) is int and type(q["open_interest"]) is int
    # The sample's paired midpoints obey elementary zero-carry parity. The
    # authored IV values are still illustrative inputs, not a calibrated model.
    by={(q["strike"],q["right"]):q for q in quotes}
    for strike in (95,100,105,110):
        assert by[(strike,"C")]["mid"]-by[(strike,"P")]["mid"]==pytest.approx(100-strike)
    metrics={m["id"]:m for m in ctx["metrics"]}
    assert metrics["h.lab.put_volume_share"]["value"]==pytest.approx(r["daily"][-1]["put_volume_share"])
    atm=by[(100,"C")]
    assert metrics["h.lab.atm_spread_percent"]["value"]==pytest.approx((atm["ask"]-atm["bid"])/atm["mid"])
    assert metrics["h.lab.protection_iv_gap"]["value"]==pytest.approx((by[(95,"P")]["implied_volatility"]-by[(105,"C")]["implied_volatility"])*100)
    ids=[item["id"] for item in r["evidence"]]
    assert len(ids)==len(set(ids))
    assert {m["id"] for m in ctx["metrics"]}<=set(ids)
    json.dumps(r,allow_nan=False)


def test_put_activity_increases_contract_counts_without_oi_change():
    r=build_scenario("put_activity")
    shares=[d["put_volume_share"] for d in r["daily"]]
    assert shares[0]<shares[1]<shares[2]
    assert len({d["oi_total"] for d in r["daily"]})==1
    assert "人数" in r["lab_context"]["metrics"][0]["limitation"]


def test_spread_and_downside_cost_examples_differ_for_the_intended_reason():
    base=build_scenario("put_activity")["lab_context"]
    wide=build_scenario("wide_spread")["lab_context"]
    protection=build_scenario("protection_cost")["lab_context"]
    assert wide["metrics"][1]["value"]>base["metrics"][1]["value"]
    assert protection["metrics"][2]["value"]>base["metrics"][2]["value"]
    p=next(q for q in protection["quote_table"] if q["strike"]==95 and q["right"]=="P")
    c=next(q for q in protection["quote_table"] if q["strike"]==105 and q["right"]=="C")
    assert p["mid"]>c["mid"]


@pytest.mark.parametrize("language",["zh","en"])
@pytest.mark.parametrize("scenario",SCENARIO_IDS)
def test_insights_add_bounded_next_steps_instead_of_repeating_metric_definitions(scenario,language):
    report=build_scenario(scenario,language)
    context=report["lab_context"]
    metrics={metric["id"]:metric for metric in context["metrics"]}
    evidence_ids={item["id"] for item in report["evidence"]}
    insights=context["insights"]
    assert len(insights)==3 and len({item["explanation"] for item in insights})==3
    assert {item["id"] for item in insights}==set(metrics)
    for item in insights:
        metric=metrics[item["id"]]
        assert set(item)=={"id","title","explanation","limitation","evidence_ids"}
        expected=[metric["id"]]
        if scenario=="put_activity" and item["id"]=="h.lab.put_volume_share":
            expected.extend(["h.day.0.put_volume_share","h.day.1.put_volume_share","h.day.2.put_volume_share","h.change.oi_total"])
        assert item["evidence_ids"]==expected
        assert set(item["evidence_ids"])<=evidence_ids
        assert item["title"]!=metric["label"] and item["explanation"]!=metric["meaning"]
        assert item["limitation"]==metric["limitation"]
        assert ("下一步：" if language=="zh" else "Next:") in item["explanation"]
    assert "natural" in insights[1]["explanation"] and "midpoint" in insights[1]["explanation"]
    assert ("不能" if language=="zh" else "cannot") in insights[2]["explanation"]
    assert ("下跌概率" if language=="zh" else "probability of a fall") in insights[2]["explanation"]


@pytest.mark.parametrize("language",["zh","en"])
def test_put_activity_period_claims_reference_existing_comparable_evidence(language):
    report=build_scenario("put_activity",language)
    insight=report["lab_context"]["insights"][0]
    evidence={item["id"]:item for item in report["evidence"]}
    daily_ids=["h.day.0.put_volume_share","h.day.1.put_volume_share","h.day.2.put_volume_share"]
    assert set(daily_ids+["h.change.oi_total"])<=set(insight["evidence_ids"])
    points=[evidence[identifier] for identifier in daily_ids]
    assert [item["trading_date"] for item in points]==list(DATES)
    assert points[0]["value"]<points[1]["value"]<points[2]["value"]
    oi=evidence["h.change.oi_total"]
    assert oi["status"]=="comparable" and oi["delta"]==0
    assert oi["direction"]=="unchanged" and oi["before"]==oi["after"]==6600
    assert all(item["oi_total"]==6600 for item in report["daily"])


@pytest.mark.parametrize("language",["zh","en"])
def test_scenario_reading_tasks_match_the_data_instead_of_implying_real_sentiment(language):
    contexts={name:build_scenario(name,language)["lab_context"] for name in SCENARIO_IDS}
    busy=contexts["put_activity"]["insights"][0]["explanation"]
    for phrase in (("合成", "不是看空人数增加", "未平仓量不变", "新增成交不等于新增持仓") if language=="zh" else
                   ("synthetic", "not more bearish people", "OI stays unchanged", "extra trades are not extra open positions")):
        assert phrase in busy
    for name in ("wide_spread","protection_cost"):
        context=contexts[name]
        volume_guide=context["insights"][0]["explanation"]
        assert ("接近" if language=="zh" else "close") in volume_guide
        assert abs(context["metrics"][0]["value"]-.5)<.03
        assert ("连续三天上升" if language=="zh" else "rises across") not in volume_guide
    wide=contexts["wide_spread"]["insights"][1]["explanation"]
    for phrase in (("特意放宽", "固定策略", "到期价格与份数", "成本与盈亏平衡价") if language=="zh" else
                   ("deliberately widens", "hold strategy", "expiry price and contract count fixed", "cost", "break-even")):
        assert phrase in wide
    protection=contexts["protection_cost"]["insights"][2]["explanation"]
    for phrase in (("合成", "同到期但行权价不同", "行权价 95", "不把 IV 差直接代入盈亏公式") if language=="zh" else
                   ("synthetic", "same expiry but different strikes", "long 95 put", "Do not insert the IV gap into the payoff formula")):
        assert phrase in protection


@pytest.mark.parametrize("strategy,upper,price,cost,payoff,pnl,breakeven,maxgain",[
    ("long_call",None,"105",360,500,140,"103.60",None),
    ("long_call",None,"100",360,0,-360,"103.60",None),
    ("long_call",None,"101",360,100,-260,"103.60",None),
    ("long_put",None,"90",360,1000,640,"96.40",9640),
    ("long_put",None,"0",360,10000,9640,"96.40",9640),
    ("long_put",None,"110",360,0,-360,"96.40",9640),
    ("call_debit_spread",105,"100",220,0,-220,"102.20",280),
    ("call_debit_spread",105,"103",220,300,80,"102.20",280),
    ("call_debit_spread",105,"105",220,500,280,"102.20",280),
    ("call_debit_spread",105,"150",220,500,280,"102.20",280),
])
def test_independent_hand_calculated_expiry_examples(strategy,upper,price,cost,payoff,pnl,breakeven,maxgain):
    t=trial(strategy=strategy,upper_strike=upper,expiry_price=price)
    assert t["cost"]==cost and t["max_loss"]==cost
    assert t["payoff"]==payoff and t["pnl"]==pnl
    assert t["decimal_strings"]["break_even"]==breakeven
    assert t["max_gain"]==maxgain and t["max_gain_unlimited"]==(maxgain is None)
    assert t["units"]==100 and t["amount_basis"]=="position_total_USD"


@pytest.mark.parametrize("scenario",SCENARIO_IDS)
@pytest.mark.parametrize("strategy,upper",[("long_call",None),("long_put",None),("call_debit_spread",105)])
@pytest.mark.parametrize("execution",["natural","midpoint"])
def test_break_even_is_zero_and_quantity_scales_exact_money(scenario,strategy,upper,execution):
    first=trial(scenario_id=scenario,strategy=strategy,upper_strike=upper,execution=execution,expiry_price="103.17")
    at_break=trial(scenario_id=scenario,strategy=strategy,upper_strike=upper,execution=execution,expiry_price=first["decimal_strings"]["break_even"])
    three=trial(scenario_id=scenario,strategy=strategy,upper_strike=upper,execution=execution,contracts=3,expiry_price="103.17")
    assert at_break["pnl"]==0 and at_break["outcome"]=="breakeven"
    for key in ("cost","pnl","max_loss","payoff"):
        assert Decimal(three["decimal_strings"][key])==3*Decimal(first["decimal_strings"][key])
    assert three["units"]==300 and three["break_even"]==first["break_even"]
    if first["max_gain"] is not None:
        assert Decimal(three["decimal_strings"]["max_gain"])==3*Decimal(first["decimal_strings"]["max_gain"])
    for point in first["curve"]:
        assert math.isfinite(point["price"]) and math.isfinite(point["pnl"])


@pytest.mark.parametrize("scenario",SCENARIO_IDS)
@pytest.mark.parametrize("strategy,upper",[("long_call",None),("long_put",None),("call_debit_spread",105)])
def test_monotonic_expiry_payoff_and_formula_bounds(scenario,strategy,upper):
    values=[trial(scenario_id=scenario,strategy=strategy,upper_strike=upper,expiry_price=price) for price in (0,90,95,100,103,105,110,200,1000)]
    pnl=[Decimal(t["decimal_strings"]["pnl"]) for t in values]
    assert pnl==sorted(pnl,reverse=strategy=="long_put")
    for t in values:
        assert t["pnl"]>=-t["max_loss"]
        if t["max_gain"] is not None:assert t["pnl"]<=t["max_gain"]
    if strategy=="long_call":
        assert values[-1]["max_gain"] is None and values[-1]["max_gain_unlimited"]
        assert max(p["pnl"] for p in values[-1]["curve"])<float("inf")
    elif strategy=="long_put":
        assert values[0]["pnl"]==values[0]["max_gain"]
    else:
        assert values[-1]["pnl"]==values[-2]["pnl"]==values[-1]["max_gain"]


@pytest.mark.parametrize("strategy,upper",[("long_call",None),("long_put",None),("call_debit_spread",105)])
def test_wide_spread_natural_cost_is_worse_than_midpoint_assumption(strategy,upper):
    natural=trial(scenario_id="wide_spread",strategy=strategy,upper_strike=upper)
    mid=trial(scenario_id="wide_spread",strategy=strategy,upper_strike=upper,execution="midpoint")
    assert natural["cost"]>mid["cost"] and natural["pnl"]<mid["pnl"]
    assert natural["legs"][0]["price_basis"]=="ask"
    if upper:assert natural["legs"][1]["price_basis"]=="bid"
    assert all(leg["price_basis"]=="midpoint" for leg in mid["legs"])


@pytest.mark.parametrize("payload",[
    {"scenario_id":"unknown"},{"strategy":"short_call"},{"strike":90},{"strike":"100"},{"strike":100.0},
    {"expiry_price":True},{"expiry_price":False},{"expiry_price":"NaN"},{"expiry_price":"Infinity"},
    {"expiry_price":float("nan")},{"expiry_price":float("inf")},{"expiry_price":"-0.01"},
    {"expiry_price":"1000.01"},{"expiry_price":"100.001"},{"expiry_price":{}},{"expiry_price":"1"*25},
    {"contracts":0},{"contracts":11},{"contracts":True},{"contracts":1.0},{"contracts":"1"},
    {"strategy":"call_debit_spread"},{"strategy":"call_debit_spread","upper_strike":100},
    {"strategy":"call_debit_spread","strike":105,"upper_strike":100},
    {"upper_strike":105},{"execution":"last"},{"premium":0.01},{"multiplier":1},{"language":"fr"},
])
def test_untrusted_trial_inputs_are_rejected(payload):
    with pytest.raises(ValidationError):LabEvaluationRequest.model_validate(payload)


def test_report_trial_replaces_prior_evidence_without_mutating_other_reports():
    base=build_scenario()
    before=deepcopy(base)
    changed=evaluate({"strategy":"call_debit_spread","upper_strike":105,"expiry_price":"102.20","contracts":2})
    assert base==before
    assert changed["lab_context"]["trial"]["pnl"]==0
    base_ids={x["id"] for x in base["evidence"]}
    changed_ids=[x["id"] for x in changed["evidence"]]
    assert len(changed_ids)==len(set(changed_ids))
    assert "h.lab.trial.upper_strike" in changed_ids and "h.lab.trial.max_gain" in changed_ids
    assert "h.lab.trial.max_gain" not in base_ids
    assert {x for x in base_ids if not x.startswith("h.lab.trial.")}<={x for x in changed_ids}
    evidence={x["id"]:x for x in changed["evidence"]}
    assert evidence["h.lab.trial.cost"]["value"]==440
    assert evidence["h.lab.trial.contracts"]["value"]==2 and evidence["h.lab.trial.contracts"]["unit"]=="contracts"
    assert all("合成" in x["description"] for x in changed["evidence"] if x["id"].startswith("h.lab.trial."))
    assert changed["rows"]==base["rows"] and changed["daily"]==base["daily"]
    json.dumps(changed,allow_nan=False)


def test_labels_limits_sources_and_non_trade_execution_are_explicit():
    t=trial(strategy="call_debit_spread",upper_strike=105,language="en")
    all_limits=" ".join(t["assumptions"])
    for word in ("expiry","pre-expiry","assignment","fees","midpoint","not guaranteed","intact"):
        assert word in all_limits
    assert t["sources"][0]["url"]=="https://www.optionseducation.org/strategies/all-strategies/bull-call-spread-debit-call-spread"
    assert t["decimal_strings"]["cost"]=="220.00"
    assert "max" in t["formula"] and "100" in t["formula"]
    with pytest.raises(ValueError,match="Unknown"):
        build_scenario("../../.env")
