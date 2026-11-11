"""Local refresh deltas require identical definitions, samples and valid time."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.options_analytics import analyze_option_snapshot
from app.options_changes import build_refresh_comparison
from app.options_collective import build_collective_analysis
from test_options_collective import NOW, snapshot


def capture(offset=0, *, mode=1, symbol="TEST", mutate=None, clock=None):
    clock = clock or NOW + timedelta(seconds=offset)
    data = snapshot(mode)
    stamp = (clock - timedelta(seconds=2)).isoformat()
    data["symbol"] = symbol
    data["received_at"] = stamp
    for row in [data["underlying"], *data["quotes"]]:
        for field in row:
            if field.endswith("received_at"):
                row[field] = stamp
    if mutate:
        mutate(data)
    baseline = analyze_option_snapshot(data, now=clock)
    return {"analysis_id": "old-analysis" if offset == 0 else "new-analysis", "snapshot": data,
            "analyzed_at": clock.isoformat(), **baseline,
            "collective": build_collective_analysis(data, baseline, now=clock)}


@pytest.fixture(autouse=True)
def future_clock(monkeypatch):
    import app.options_changes as module
    monkeypatch.setattr(module, "_clock", lambda: NOW + timedelta(days=5))


def metric(comparison, identifier, scope=0):
    return next(item for item in comparison["scopes"][scope]["metrics"] if item["id"] == identifier)


def test_valid_like_for_like_deltas_are_local_with_explicit_units_and_immutable_inputs():
    def changed(data):
        data["quotes"][1]["volume"] += 20
        for row in data["quotes"]:
            row["implied_volatility"] += .02

    old, new = capture(), capture(10, mutate=changed)
    original = deepcopy((old, new))
    result = build_refresh_comparison(old, new)
    assert result["status"] == "comparable" and result["previous_analysis_id"] == "old-analysis"
    assert metric(result, "volume_total")["delta"] == 20
    assert metric(result, "volume_total")["delta_unit"] == "contracts"
    assert metric(result, "volume_put_share")["delta"] == pytest.approx(100 * (80 / 120 - .6))
    assert metric(result, "volume_put_share")["delta_unit"] == "percentage_points"
    assert metric(result, "atm_iv")["delta"] == pytest.approx(2)
    assert metric(result, "atm_iv")["delta_unit"] == "volatility_points"
    assert "不是精确时间间隔内的新增成交" in result["notice"]
    assert (old, new) == original
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("field,value,reason", [
    ("trading_class", "OTHER", "contract_metadata_changed"),
    ("currency", "EUR", "contract_metadata_changed"),
    ("multiplier", 10, "contract_metadata_changed"),
    ("trading_class", None, "contract_metadata_missing"),
    ("requested_strikes", [95, 100], "requested_strikes_changed"),
    ("requested_strikes", None, "requested_strikes_missing"),
])
def test_changed_contract_window_blocks_all_deltas_but_keeps_values(field, value, reason):
    old, new = capture(), capture(10)
    new["snapshot"][field] = value
    result = build_refresh_comparison(old, new)
    assert result["status"] == "incomparable" and reason in result["scopes"][0]["reasons"]
    assert all(item["delta"] is None for item in result["scopes"][0]["metrics"])
    assert metric(result, "volume_total")["before"] == metric(result, "volume_total")["after"] == 100


def test_actual_feed_not_requested_feed_controls_comparison():
    old, new = capture(), capture(10, mode=3)
    new["snapshot"]["requested_market_data_type"] = 1
    result = build_refresh_comparison(old, new)
    assert result["status"] == "incomparable"
    assert result["scopes"][0]["before_feed"] == "live" and result["scopes"][0]["after_feed"] == "delayed"
    assert "feed_changed" in result["scopes"][0]["reasons"]


@pytest.mark.parametrize("mode", ["mixed", "unknown", "unavailable"])
def test_unconfirmed_feed_is_never_compared(mode):
    old, new = capture(), capture(10)
    new["quality"]["market_data_status"] = mode
    result = build_refresh_comparison(old, new)
    assert "feed_unconfirmed" in result["scopes"][0]["reasons"]
    assert metric(result, "quote_coverage")["delta"] is None


@pytest.mark.parametrize("stamp,reason", [
    ((NOW - timedelta(seconds=2)).isoformat(), "receipt_time_not_increasing"),
    ((NOW - timedelta(seconds=5)).isoformat(), "receipt_time_not_increasing"),
    ((NOW + timedelta(days=6)).isoformat(), "future_receipt_time"),
    ("2026-11-11T16:00:10", "receipt_time_missing"),
    (None, "receipt_time_missing"),
])
def test_invalid_equal_reversed_and_future_times_are_incomparable(stamp, reason):
    old, new = capture(), capture(10)
    new["snapshot"]["received_at"] = stamp
    result = build_refresh_comparison(old, new)
    assert result["status"] == "incomparable"
    assert reason in result["scopes"][0]["reasons"]


def test_daily_volume_uses_new_york_date_not_utc_date_and_oi_is_independent():
    # UTC dates match, but New York crosses midnight during the captures.
    old = capture(clock=datetime(2026, 11, 12, 4, 59, tzinfo=timezone.utc))
    new = capture(10, clock=datetime(2026, 11, 12, 5, 1, tzinfo=timezone.utc))
    result = build_refresh_comparison(old, new, "en")
    for name in ("volume_total", "volume_put_share"):
        assert metric(result, name)["reason"] == "volume_cross_ny_date"
        assert metric(result, name)["delta"] is None
    assert metric(result, "oi_total")["status"] == "comparable"
    assert "independent reporting cycle" in result["notice"] and "not fund flow" in result["notice"]
    # UTC midnight alone does not cross the New York daily boundary.
    old = capture(clock=datetime(2026, 11, 11, 23, 59, tzinfo=timezone.utc))
    new = capture(10, clock=datetime(2026, 11, 12, 0, 1, tzinfo=timezone.utc))
    assert metric(build_refresh_comparison(old, new), "volume_total")["status"] == "comparable"


@pytest.mark.parametrize("field,prefix,reason", [("volume", "volume", "volume_pair_sample_changed"), ("open_interest", "oi", "oi_pair_sample_changed")])
def test_same_pair_count_with_different_actual_strikes_is_not_comparable(field, prefix, reason):
    def remove(strike):
        def mutate(data):
            next(row for row in data["quotes"] if row["strike"] == strike and row["right"] == "C")[field] = None
        return mutate
    old, new = capture(mutate=remove(95)), capture(10, mutate=remove(105))
    result = build_refresh_comparison(old, new)
    assert metric(result, prefix + "_total")["reason"] == reason
    assert metric(result, prefix + "_put_share")["delta"] is None
    assert metric(result, "quote_coverage")["status"] == "comparable"


def test_median_spread_checks_actual_quote_contract_set_even_with_equal_valid_counts():
    def remove(strike, right):
        def mutate(data):
            next(row for row in data["quotes"] if (row["strike"], row["right"]) == (strike, right))["bid"] = None
        return mutate
    old, new = capture(mutate=remove(95, "C")), capture(10, mutate=remove(105, "P"))
    assert old["collective"]["liquidity"]["valid_contracts"] == new["collective"]["liquidity"]["valid_contracts"]
    result = build_refresh_comparison(old, new)
    assert metric(result, "median_spread")["reason"] == "quote_contract_set_changed"
    assert metric(result, "quote_coverage")["delta"] == 0


def test_quote_coverage_requires_matching_verified_request_denominator():
    old, new = capture(), capture(10)
    new["quality"]["requested_contracts"] = 99
    result = build_refresh_comparison(old, new)
    assert metric(result, "quote_coverage")["reason"] == "requested_denominator_unverified"
    assert metric(result, "volume_total")["status"] == "comparable"


@pytest.mark.parametrize("field,value", [("atm_strike", 105), ("greeks_basis", "bid")])
def test_atm_iv_requires_same_strike_and_greeks_basis(field, value):
    old, new = capture(), capture(10)
    new["collective"]["volatility"][field] = value
    result = build_refresh_comparison(old, new)
    assert metric(result, "atm_iv")["reason"] == "atm_definition_changed"
    assert metric(result, "atm_iv")["before"] is not None and metric(result, "atm_iv")["after"] is not None


def test_missing_values_are_not_zero_and_real_zero_counts_can_be_compared():
    old, new = capture(), capture(10)
    old["quality"]["quote_coverage"] = None
    result = build_refresh_comparison(old, new)
    assert metric(result, "quote_coverage")["before"] is None
    assert metric(result, "quote_coverage")["delta"] is None

    def zero(data):
        for row in data["quotes"]:
            row["volume"] = 0
    old = capture(mutate=zero)
    result = build_refresh_comparison(old, new)
    assert metric(result, "volume_total")["before"] == 0
    assert metric(result, "volume_total")["delta"] == 100
    assert metric(result, "volume_put_share")["delta"] is None


def test_non_finite_values_are_missing_and_non_finite_deltas_are_rejected():
    old, new = capture(), capture(10)
    old["quality"]["quote_coverage"] = float("nan")
    result = build_refresh_comparison(old, new)
    assert metric(result, "quote_coverage")["before"] is None
    json.dumps(result, allow_nan=False)


def test_batch_aligns_by_scope_not_position_and_reports_added_missing_failed_groups():
    a, b = capture(symbol="AAA"), capture(symbol="BBB")
    newer_a, c = capture(10, symbol="AAA"), capture(10, symbol="CCC")
    previous = {"analysis_id": "batch-old", "reports": [a, b]}
    current = {"reports": [c, newer_a], "failures": [{"symbol": "BBB", "expiry": "2026-11-20", "code": "ibkr_timeout"}]}
    result = build_refresh_comparison(previous, current)
    scopes = {scope["symbol"]: scope for scope in result["scopes"]}
    assert scopes["AAA"]["status"] == "comparable"
    assert scopes["CCC"]["status"] == "added"
    assert scopes["BBB"]["status"] == "failed"
    assert all(item["delta"] is None for name in ("BBB", "CCC") for item in scopes[name]["metrics"])
    assert result["failures"] == [{"phase": "current", "symbol": "BBB", "expiry": "2026-11-20", "code": "ibkr_timeout"}]
    assert result["status"] == "partial"


def test_duplicate_scope_is_not_arbitrarily_matched():
    old, new = {"reports": [capture(), capture()]}, capture(10)
    result = build_refresh_comparison(old, new)
    assert result["scopes"][0]["reasons"] == ["ambiguous_scope"]
    assert all(item["delta"] is None for item in result["scopes"][0]["metrics"])


def test_missing_batch_scope_preserves_old_values_and_empty_failed_batch_is_safe():
    old = {"analysis_id": "batch-old", "reports": [capture(symbol="AAA"), capture(symbol="BBB")]}
    new = {"reports": [capture(10, symbol="AAA")]}
    result = build_refresh_comparison(old, new)
    missing = result["scopes"][1]
    assert missing["status"] == "missing" and missing["metrics"][0]["before"] == 1
    assert missing["metrics"][0]["after"] is None
    empty = build_refresh_comparison({"reports": []}, {"reports": [], "failures": [{"symbol": "FAIL", "expiry": None, "code": "timeout"}]})
    assert empty["status"] == "incomparable" and empty["scopes"][0]["status"] == "failed"
