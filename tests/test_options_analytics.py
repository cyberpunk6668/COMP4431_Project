from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.options_analytics import analyze_option_snapshot


NOW = datetime(2026, 11, 11, 17, tzinfo=timezone.utc)
EXPIRY = "2026-11-20"


def ago(seconds: int) -> str:
    return (NOW - timedelta(seconds=seconds)).isoformat()


@pytest.fixture
def snapshot() -> dict:
    rows = []
    for strike in (95, 100, 105):
        for right in ("C", "P"):
            rows.append({
                "expiration": EXPIRY,
                "strike": strike,
                "right": right,
                "bid": 2,
                "ask": 2.2,
                "last": 2.1,
                "volume": 20 if right == "P" else 10,
                "open_interest": 100 if right == "P" else 200,
                "implied_volatility": 0.28 if right == "P" else 0.20,
                "delta": -0.25 if right == "P" else 0.25,
                "greeks_basis": "model",
                "market_data_type": 1,
                "received_at": ago(2),
                "quote_received_at": ago(3),
                "volume_received_at": ago(2),
                "open_interest_received_at": ago(2),
                "greeks_received_at": ago(2),
            })
    return {
        "symbol": "SPY",
        "expiration": EXPIRY,
        "requested_strikes": [95, 100, 105],
        "received_at": ago(1),
        "underlying": {
            "price": 100,
            "bid": 99.99,
            "ask": 100.01,
            "price_basis": "midpoint",
            "received_at": ago(4),
            "market_data_type": 1,
        },
        "quotes": rows,
    }


def quote(snapshot: dict, strike: float, right: str) -> dict:
    return next(row for row in snapshot["quotes"] if (row["strike"], row["right"]) == (strike, right))


def analyze(snapshot: dict, **kwargs) -> dict:
    return analyze_option_snapshot(snapshot, now=NOW, **kwargs)


def test_clean_live_snapshot_keeps_distinct_measures(snapshot):
    result = analyze(snapshot)
    quality, metrics = result["quality"], result["metrics"]
    assert quality["market_data_status"] == "live"
    assert quality["llm_eligible"]
    assert quality["fresh_live_paired_strikes"] == 3
    assert metrics["put_call_volume"]["value"] == 2
    assert metrics["put_call_open_interest"]["value"] == 0.5
    assert metrics["iv_skew_25_delta"]["value"] == pytest.approx(8)
    assert metrics["iv_skew_25_delta"]["put_strike"] == 95
    assert metrics["iv_skew_25_delta"]["call_strike"] == 105
    assert metrics["atm_straddle"]["value"] == pytest.approx(4.2)
    assert metrics["atm_straddle"]["strike"] == 100
    assert [item["code"] for item in result["signals"]] == [
        "more_put_volume", "more_call_open_interest", "higher_put_iv",
    ]
    json.dumps(result, allow_nan=False)


def test_missing_call_excludes_both_legs_and_keeps_observed_zero(snapshot):
    quote(snapshot, 95, "C")["volume"] = None
    quote(snapshot, 100, "P")["volume"] = 0
    metrics = analyze(snapshot)["metrics"]
    volume = metrics["put_call_volume"]
    assert volume["included_strikes"] == [100, 105]
    assert volume["paired_strikes"] == 2
    assert volume["value"] == 1
    assert volume["put_total"] == 20
    assert metrics["put_call_open_interest"]["paired_strikes"] == 3


def test_zero_calls_does_not_manufacture_infinite_ratio(snapshot):
    for row in snapshot["quotes"]:
        row["volume"] = 0
    result = analyze(snapshot)
    volume = result["metrics"]["put_call_volume"]
    assert volume["reason"] == "zero_call_total"
    assert volume["call_total"] == volume["put_total"] == 0
    assert volume["value"] is None
    assert not any(item["metric"] == "put_call_volume" for item in result["signals"])


@pytest.mark.parametrize(("mode", "label"), [(2, "frozen"), (3, "delayed"), (4, "delayed_frozen")])
def test_recent_receipt_does_not_turn_non_live_mode_into_live(snapshot, mode, label):
    for row in [snapshot["underlying"], *snapshot["quotes"]]:
        row["market_data_type"] = mode
    result = analyze(snapshot)
    assert result["quality"]["market_data_status"] == label
    assert result["quality"]["fresh_live_quote_contracts"] == 0
    assert not result["quality"]["llm_eligible"]
    assert result["metrics"]["put_call_volume"]["market_data_status"] == label
    assert result["metrics"]["put_call_volume"]["value"] == 2


def test_mixed_snapshot_uses_only_matching_known_cohort(snapshot):
    quote(snapshot, 95, "P")["market_data_type"] = 3
    quote(snapshot, 105, "C")["market_data_type"] = None
    result = analyze(snapshot)
    assert result["quality"]["market_data_status"] == "mixed"
    assert not result["quality"]["llm_eligible"]
    assert result["metrics"]["put_call_volume"]["included_strikes"] == [100]
    assert result["metrics"]["iv_skew_25_delta"]["value"] is None


def test_aggregate_receipt_does_not_refresh_stale_field(snapshot):
    for row in snapshot["quotes"]:
        row.update(
            received_at=ago(1),
            quote_received_at=ago(31),
            volume_received_at=ago(31),
            greeks_received_at=ago(31),
        )
    result = analyze(snapshot)
    assert result["quality"]["valid_quote_contracts"] == 6
    assert result["quality"]["fresh_live_quote_contracts"] == 0
    assert not result["quality"]["llm_eligible"]
    assert result["metrics"]["put_call_open_interest"]["value"] == 0.5
    assert result["metrics"]["put_call_volume"]["value"] is None
    assert result["metrics"]["atm_straddle"]["reason"] == "atm_quote_stale"


@pytest.mark.parametrize(("bid", "ask", "reason"), [
    (0, 2.2, "atm_quote_unavailable"),
    (3, 2.2, "atm_quote_unavailable"),
    (1, 2.2, "wide_bid_ask_spread"),
])
def test_bad_market_does_not_produce_atm_value(snapshot, bid, ask, reason):
    quote(snapshot, 100, "C").update(bid=bid, ask=ask)
    assert analyze(snapshot)["metrics"]["atm_straddle"]["reason"] == reason


def test_current_but_unsynchronized_quotes_cannot_be_paired(snapshot):
    quote(snapshot, 100, "P").update(quote_received_at=ago(20), volume_received_at=ago(20))
    result = analyze(snapshot)
    assert result["metrics"]["atm_straddle"]["reason"] == "unsynchronized_receipts"
    assert result["metrics"]["put_call_volume"]["included_strikes"] == [95, 105]
    assert result["quality"]["fresh_live_paired_strikes"] == 2


def test_last_price_receipt_does_not_act_as_current_underlying_quote(snapshot):
    snapshot["underlying"]["price_basis"] = "last"
    result = analyze(snapshot)
    assert not result["quality"]["underlying_fresh_live"]
    assert not result["quality"]["llm_eligible"]
    assert result["metrics"]["atm_straddle"]["reason"] == "underlying_unavailable"
    assert result["metrics"]["iv_skew_25_delta"]["reason"] == "underlying_unavailable"


@pytest.mark.parametrize("change", [
    {"greeks_basis": "ask"},
    {"delta": -0.14},
    {"delta": 0.25},
    {"greeks_received_at": ago(32)},
])
def test_skew_requires_comparable_timely_wings(snapshot, change):
    quote(snapshot, 95, "P").update(change)
    result = analyze(snapshot)
    assert result["metrics"]["iv_skew_25_delta"]["reason"] == "insufficient_comparable_greeks"


def test_expiry_scope_ambiguous_contracts_and_sorting(snapshot):
    conflicting_expiry = deepcopy(quote(snapshot, 100, "P"))
    conflicting_expiry["expiration"] = "2026-11-27"
    snapshot["quotes"].append(conflicting_expiry)
    snapshot["quotes"].append(deepcopy(quote(snapshot, 95, "P")))
    result = analyze(snapshot)
    assert result["quality"]["excluded_out_of_scope_rows"] == 1
    assert result["quality"]["excluded_ambiguous_contracts"] == 1
    assert result["metrics"]["put_call_volume"]["included_strikes"] == [100, 105]
    assert not result["quality"]["llm_eligible"]
    snapshot["quotes"].reverse()
    snapshot["requested_strikes"].reverse()
    assert analyze(snapshot) == result


def test_empty_snapshot_is_unavailable_and_json_safe():
    result = analyze({}, language="en")
    assert not result["quality"]["llm_eligible"]
    assert result["quality"]["market_data_status"] == "unavailable"
    assert result["quality"]["quote_coverage"] is None
    assert result["signals"] == []
    assert all(metric["value"] is None for metric in result["metrics"].values())
    assert result["caveats"][0].startswith("Metrics cover")
    json.dumps(result, allow_nan=False)
