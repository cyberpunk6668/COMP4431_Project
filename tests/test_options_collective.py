from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.options_analytics import analyze_option_snapshot
from app.options_collective import build_batch_comparison, build_collective_analysis


NOW = datetime(2026, 11, 11, 16, tzinfo=timezone.utc)


def snapshot(mode=1):
    stamp = (NOW - timedelta(seconds=2)).isoformat()
    rows = []
    volumes = {95: (10, 30), 100: (10, 10), 105: (20, 20)}
    interest = {95: (300, 50), 100: (100, 100), 105: (100, 50)}
    iv = {95: (.28, .30), 100: (.22, .24), 105: (.20, .26)}
    deltas = {95: (.75, -.25), 100: (.5, -.5), 105: (.25, -.75)}
    for strike in (95, 100, 105):
        for side_index, right in enumerate(("C", "P")):
            rows.append({
                "strike": strike, "right": right, "expiration": "2026-11-20",
                "bid": 2, "ask": 2.2, "volume": volumes[strike][side_index],
                "open_interest": interest[strike][side_index],
                "implied_volatility": iv[strike][side_index], "delta": deltas[strike][side_index],
                "greeks_basis": "model", "market_data_type": mode,
                "received_at": stamp, "quote_received_at": stamp, "volume_received_at": stamp,
                "open_interest_received_at": stamp, "greeks_received_at": stamp,
            })
    return {"symbol": "TEST", "expiration": "2026-11-20", "currency": "USD", "trading_class": "TEST",
            "multiplier": 100, "requested_strikes": [95, 100, 105], "received_at": stamp,
            "underlying": {"price": 100, "bid": 99.9, "ask": 100.1, "price_basis": "midpoint",
                           "received_at": stamp, "market_data_type": mode}, "quotes": rows}


def collective(data, language="zh"):
    baseline = analyze_option_snapshot(data, now=NOW, language=language)
    return build_collective_analysis(data, baseline, now=NOW, language=language)


def row(data, strike, right):
    return next(item for item in data["quotes"] if (item["strike"], item["right"]) == (strike, right))


def test_joint_concentration_conflicts_and_quote_tightness():
    result = collective(snapshot())
    assert result["assessment"]["status"] == "descriptive"
    assert result["liquidity"]["median_relative_spread_pct"] == pytest.approx(100 * .2 / 2.1)
    volume = result["distributions"]["volume"]
    assert volume["total"] == 100
    assert volume["peak_strikes"] == [95, 105]
    assert volume["top_strike_share"] == .4
    assert volume["top_two_strike_share"] == .8
    assert volume["hhi"] == pytest.approx(.36)
    assert result["distributions"]["open_interest"]["peak_strikes"] == [95]
    assert result["positioning"]["put_share_gap_pp"] == pytest.approx(100 * (.6 - 2 / 7))
    assert "activity_positioning" in [finding["id"] for finding in result["assessment"]["conflicts"]]
    assert "activity_pricing" in [finding["id"] for finding in result["assessment"]["findings"]]
    ids = {item["id"] for item in result["evidence"]}
    assert len(ids) == len(result["evidence"])
    for finding in result["assessment"]["findings"] + result["assessment"]["conflicts"]:
        assert set(finding["evidence_ids"]) <= ids
    json.dumps(result, allow_nan=False)


def test_activity_oi_uses_exact_common_cohort():
    data = snapshot()
    row(data, 95, "P")["open_interest"] = None
    result = collective(data)
    assert result["distributions"]["volume"]["total"] == 100
    assert result["distributions"]["open_interest"]["paired_strikes"] == 2
    assert result["positioning"]["common_strikes"] == [100, 105]
    assert result["positioning"]["put_volume_share"] == .5
    assert result["positioning"]["put_open_interest_share"] == pytest.approx(150 / 350)
    evidence = {item["id"]: item["value"] for item in result["evidence"]}
    assert evidence["volume_put_share"] == .6
    assert evidence["common_volume_put_share"] == .5


def test_smile_uses_valid_matching_atm_basis():
    data = snapshot()
    result = collective(data)
    assert result["volatility"]["atm_iv"] == pytest.approx(.23)
    assert len(result["volatility"]["points"]) == 6
    assert next(point for point in result["volatility"]["points"] if point["strike"] == 95 and point["right"] == "P")["iv_minus_atm_pp"] == pytest.approx(7)
    row(data, 100, "P")["greeks_basis"] = "bid"
    assert collective(data)["volatility"]["atm_iv"] is None


def test_stale_and_mixed_fields_do_not_manufacture_distribution():
    stale = snapshot()
    for item in [stale["underlying"], *stale["quotes"]]:
        for field in list(item):
            if field.endswith("received_at"):
                item[field] = (NOW - timedelta(seconds=60)).isoformat()
    result = collective(stale)
    assert result["assessment"]["status"] == "insufficient"
    assert result["distributions"]["volume"]["total"] is None
    mixed = snapshot()
    row(mixed, 100, "P")["market_data_type"] = 3
    result = collective(mixed)
    assert result["context"]["market_data_status"] == "mixed"
    assert result["assessment"]["status"] == "insufficient"
    assert result["distributions"]["volume"]["paired_strikes"] == 0


def test_recent_delayed_snapshot_supports_labeled_description():
    result = collective(snapshot(mode=3), language="en")
    assert result["assessment"]["status"] == "descriptive"
    assert result["context"]["market_data_status"] == "delayed"
    assert result["distributions"]["volume"]["total"] == 100
    assert any("delayed" in item for item in result["assessment"]["limitations"])


def test_observed_zero_has_no_fake_concentration():
    data = snapshot()
    for item in data["quotes"]:
        item["volume"] = 0
    volume = collective(data)["distributions"]["volume"]
    assert volume["total"] == 0
    assert volume["peak_strikes"] == []
    assert volume["top_strike_share"] is None and volume["hhi"] is None


def test_unsynchronized_count_pairs_reduce_coverage():
    data = snapshot()
    row(data, 100, "C")["volume_received_at"] = (NOW - timedelta(seconds=25)).isoformat()
    assert collective(data)["distributions"]["volume"]["paired_strikes"] == 2


def test_ambiguous_duplicates_excluded_with_visible_limit():
    data = snapshot()
    data["quotes"].append(deepcopy(row(data, 95, "C")))
    result = collective(data)
    assert result["distributions"]["volume"]["paired_strikes"] == 2
    assert any("重复" in item for item in result["assessment"]["limitations"])


def report(data):
    return {"snapshot": data, "collective": collective(data)}


def test_term_iv_requires_matching_basis_and_receipts():
    near, far = snapshot(), snapshot()
    far["expiration"] = "2026-12-18"
    for item in far["quotes"]:
        item["expiration"] = far["expiration"]
        item["implied_volatility"] += .02
    result = build_batch_comparison([report(near), report(far)])
    assert result["term_structure"][0]["status"] == "comparable"
    assert result["term_structure"][0]["far_minus_near_iv_pp"] == pytest.approx(2)
    for item in far["quotes"]:
        item["greeks_basis"] = "bid"
    result = build_batch_comparison([report(near), report(far)])
    assert result["term_structure"][0]["status"] == "insufficient"


def test_term_iv_does_not_compare_other_symbol_or_missing_class():
    near, far = snapshot(), snapshot()
    far["symbol"] = "OTHER"
    far["expiration"] = "2026-12-18"
    assert build_batch_comparison([report(near), report(far)])["term_structure"] == []
    far["symbol"] = "TEST"
    far["trading_class"] = None
    for item in far["quotes"]:
        item["expiration"] = far["expiration"]
    assert build_batch_comparison([report(near), report(far)])["term_structure"][0]["status"] == "insufficient"


def test_two_empty_batches_remain_insufficient():
    data = snapshot()
    data["quotes"] = []
    result = build_batch_comparison([report(data), report(data)])
    assert result["assessment"]["status"] == "insufficient"


def test_extreme_iv_remains_json_serializable():
    data = snapshot()
    row(data, 100, "C")["implied_volatility"] = 1e308
    row(data, 100, "P")["implied_volatility"] = 1e308
    result = collective(data)
    assert result["volatility"]["atm_iv"] == 1e308
    json.dumps(result, allow_nan=False)
