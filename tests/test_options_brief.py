from copy import deepcopy
from datetime import timedelta
import json

import pytest

from app.options_analytics import analyze_option_snapshot
from app.options_brief import build_batch_plain_brief, build_plain_brief
from app.options_collective import build_batch_comparison, build_collective_analysis
from test_options_collective import NOW, snapshot


def report(data=None):
    data = data if data is not None else snapshot()
    analysis = analyze_option_snapshot(data, now=NOW)
    collective = build_collective_analysis(data, analysis, now=NOW)
    return {"snapshot": data, **analysis, "collective": collective, "capture_age_seconds": 2}


def card(brief, identifier):
    return next(item for item in brief["cards"] if item["id"] == identifier)


def test_counts_are_normalized_as_contracts_and_cite_local_evidence():
    data = report()
    brief = build_plain_brief(data, now=NOW)
    activity = card(brief, "activity")
    assert activity["visual"]["first_value"] == 60
    assert activity["visual"]["second_value"] == 40
    assert "100 份样本成交合约" in activity["answer"]
    assert "人" not in activity["answer"]
    assert "按比例折算" in activity["answer"]
    known = {"g0." + item["id"] for item in data["collective"]["evidence"]}
    assert set(brief["evidence_ids"]) <= known
    assert all(set(item["evidence_ids"]) <= known for item in brief["cards"])
    assert len(brief["cards"]) == 4
    json.dumps(brief, allow_nan=False)


def test_zero_volume_and_missing_volume_have_different_meanings():
    data = snapshot()
    for row in data["quotes"]:
        row["volume"] = 0
    zero = build_plain_brief(report(data), now=NOW)
    assert "为零" in card(zero, "activity")["answer"]
    assert "visual" not in card(zero, "activity")
    assert "visual" not in card(zero, "concentration")
    for row in data["quotes"]:
        row["volume"] = None
    missing = build_plain_brief(report(data), now=NOW)
    assert "看不清" in card(missing, "activity")["answer"]
    assert "为零" not in card(missing, "activity")["answer"]
    assert "visual" not in card(missing, "activity")


def test_one_paired_strike_does_not_create_a_population_share():
    data = snapshot()
    for row in data["quotes"]:
        if row["strike"] != 100:
            row["volume"] = None
    brief = build_plain_brief(report(data), now=NOW)
    assert card(brief, "activity")["tone"] == "attention"
    assert "visual" not in card(brief, "activity")
    assert "100 份" not in card(brief, "activity")["answer"]


@pytest.mark.parametrize("mode,label", [(3, "延迟资料"), (2, "已冻结"), (4, "延迟且已冻结")])
def test_received_frozen_and_delayed_data_stays_labelled(mode, label):
    brief = build_plain_brief(report(snapshot(mode=mode)), now=NOW)
    assert label in brief["freshness"]["label"]
    assert brief["freshness"]["tone"] == "attention"
    assert brief["freshness"]["historical"] is False
    assert brief["status"] == "descriptive"
    assert "较早的市场报价" in brief["freshness"]["meaning"]


def test_stale_snapshot_is_explicitly_historical_without_erasing_its_scope():
    data = report()
    brief = build_plain_brief(data, now=NOW + timedelta(seconds=90))
    assert brief["status"] == "limited"
    assert brief["freshness"]["historical"]
    assert "较早" in brief["headline"]
    assert brief["scope"] == {"symbol": "TEST", "expiration": "2026-11-20"}
    assert brief["freshness"]["age_seconds"] == 92


def test_unknown_or_future_receipt_is_not_marked_current():
    data = report()
    data["snapshot"]["received_at"] = (NOW + timedelta(minutes=1)).isoformat()
    brief = build_plain_brief(data, now=NOW)
    assert brief["status"] == "limited"
    assert brief["freshness"]["age_seconds"] is None
    data["snapshot"].pop("received_at")
    data.pop("capture_age_seconds")
    assert build_plain_brief(data, now=NOW)["freshness"]["historical"]


def test_mixed_feed_does_not_get_a_put_call_mix_visual():
    data = report()
    data["quality"]["market_data_status"] = "mixed"
    brief = build_plain_brief(data, now=NOW)
    assert brief["status"] == "limited"
    assert "混合" in brief["freshness"]["label"]
    assert "visual" not in card(brief, "activity")
    assert card(brief, "pricing")["tone"] == "attention"


def test_concentration_retains_all_tied_peaks_without_predicting_price_levels():
    brief = build_plain_brief(report(), now=NOW)
    concentration = card(brief, "concentration")
    assert "95" in concentration["answer"] and "105" in concentration["answer"]
    assert "各占" in concentration["answer"]
    assert "40%" in concentration["answer"]
    assert "股价目标" in concentration["meaning"]
    assert "集中度高" not in concentration["answer"]


def test_agreement_uses_the_common_cohort_not_unmatched_totals():
    data = report()
    positioning = data["collective"]["positioning"]
    positioning.update(put_volume_share=.8, put_open_interest_share=.2, coverage=1, common_strikes=[95, 100, 105])
    first = card(build_plain_brief(data, now=NOW), "agreement")
    assert "成交更偏向看跌合约" in first["answer"]
    assert "尚未结清的合约却更偏向看涨合约" in first["answer"]
    assert "g0.common_volume_put_share" in first["evidence_ids"]
    positioning.update(put_volume_share=None, put_open_interest_share=None)
    missing = card(build_plain_brief(data, now=NOW), "agreement")
    assert "还缺少" in missing["answer"]


def test_relative_pricing_uses_a_comparable_iv_metric_or_explains_the_gap():
    data = report()
    pricing = card(build_plain_brief(data, now=NOW), "pricing")
    assert "看跌一侧" in pricing["answer"]
    assert "g0.skew_25_delta" in pricing["evidence_ids"]
    data["metrics"]["iv_skew_25_delta"]["value"] = None
    data["metrics"]["atm_straddle"]["value"] = None
    missing = card(build_plain_brief(data, now=NOW), "pricing")
    assert "无法可靠比较" in missing["answer"]
    assert missing["tone"] == "attention"


def test_batch_keeps_separate_groups_and_validates_reference_namespaces():
    first = report(snapshot(mode=3))
    second = deepcopy(first)
    second["snapshot"]["symbol"] = "OTHER"
    second["collective"]["context"]["symbol"] = "OTHER"
    comparison = build_batch_comparison([first, second])
    brief = build_batch_plain_brief([first, second], comparison, [], now=NOW)
    assert brief["status"] == "descriptive"
    assert len(brief["items"]) == 2
    assert any(item.startswith("g0.") for item in brief["items"][0]["evidence_ids"])
    assert all(item.startswith("g1.") for item in brief["items"][1]["evidence_ids"])
    assert "同一瞬间" in brief["freshness"]["meaning"]
    assert "样本内" in card(brief, "batch_activity")["answer"]
    assert "没有满足" in card(brief, "batch_pricing")["answer"]


def test_batch_partial_and_empty_results_remain_limited():
    first = report(snapshot(mode=3))
    second = deepcopy(first)
    second["snapshot"]["symbol"] = "OTHER"
    comparison = build_batch_comparison([first, second])
    partial = build_batch_plain_brief([first, second], comparison, [{"symbol": "MISSING"}], now=NOW)
    assert partial["status"] == "limited"
    assert partial["scope"]["groups"] == 3
    assert len(partial["items"]) == 2
    assert "1 组" in partial["next_steps"][0]
    empty = build_batch_plain_brief([], build_batch_comparison([]), [{"symbol": "MISSING"}], now=NOW)
    assert empty["status"] == "limited"
    assert not empty["items"]
    assert "没有取得" in empty["headline"]
    json.dumps(empty, allow_nan=False)


def test_batch_term_pricing_requires_a_valid_same_underlying_pair():
    first = report(snapshot(mode=3))
    far_data = snapshot(mode=3)
    far_data["expiration"] = "2026-12-18"
    for row in far_data["quotes"]:
        row["expiration"] = far_data["expiration"]
        row["implied_volatility"] += .03
    second = report(far_data)
    comparison = build_batch_comparison([first, second])
    brief = build_batch_plain_brief([first, second], comparison, [], now=NOW)
    pricing = card(brief, "batch_pricing")
    assert pricing["tone"] == "available"
    assert "高 3 个波动率百分点" in pricing["answer"]
    assert pricing["evidence_ids"] == ["comparison.report_1_atm_iv", "comparison.report_2_atm_iv"]


def test_english_brief_keeps_contract_and_snapshot_language():
    brief = build_plain_brief(report(snapshot(mode=3)), language="en", now=NOW)
    activity = card(brief, "activity")
    assert "traded contracts" in activity["answer"]
    assert "people" not in activity["answer"]
    assert "Delayed data" in brief["freshness"]["label"]
    assert brief["glossary"][0]["term"] == "Call / put options"


def test_timezone_aware_clock_is_required():
    with pytest.raises(ValueError):
        build_plain_brief(report(), now=NOW.replace(tzinfo=None))
