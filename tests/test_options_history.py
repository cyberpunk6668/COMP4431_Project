from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.options_history import HistoryDataset, analyze_history, demo_dataset


NOW = datetime(2026, 11, 11, 12, tzinfo=UTC)


def dataset():
    return demo_dataset(NOW)


def report(data=None):
    return analyze_history(HistoryDataset.model_validate(data or dataset()), now=NOW)


def test_fixed_sample_has_deterministic_changes_and_explicit_unverified_source():
    result = report()
    assert result["source"]["kind"] == "import" and result["source"]["verified"] is False
    assert result["quality"]["common_contracts"] == 4
    assert len(result["daily"]) == 3
    changes = {item["id"]: item for item in result["changes"]}
    assert changes["h.change.volume_total"]["before"] == 360
    assert changes["h.change.volume_total"]["after"] == 600
    assert changes["h.change.volume_total"]["delta"] == 240
    expected = (320 / 600 - 160 / 360) * 100
    assert changes["h.change.put_volume_share"]["delta"] == pytest.approx(expected)
    assert changes["h.change.put_volume_share"]["delta_unit"] == "percentage_points"
    assert result["rows"] and "bid" not in result["rows"][0]


def test_missing_leg_is_excluded_on_all_dates_instead_of_changing_denominator():
    data = dataset()
    data["rows"] = [row for row in data["rows"] if not (row["strike"] == 105 and row["right"] == "C" and row["trading_date"] == "2026-11-06")]
    result = report(data)
    assert result["quality"]["provided_contracts"] == 4
    assert result["quality"]["common_contracts"] == 2
    assert {item["common_contracts"] for item in result["daily"]} == {2}
    assert result["changes"][0]["before"] == 180
    assert result["changes"][0]["after"] == 300


def test_zero_volume_is_observed_zero_but_put_share_is_undefined():
    data = dataset()
    for row in data["rows"]:
        row["volume"] = 0
    result = report(data)
    assert all(item["volume_total"] == 0 for item in result["daily"])
    assert all(item["put_volume_share"] is None for item in result["daily"])
    assert result["changes"][0]["delta"] == 0
    assert result["changes"][1]["status"] == "incomparable"


def test_missing_volume_does_not_become_zero_or_partial_total():
    data = dataset()
    data["rows"][-1]["volume"] = None
    result = report(data)
    assert result["daily"][-1]["volume_total"] is None
    assert result["changes"][0]["delta"] is None


def test_unknown_oi_date_preserves_raw_field_but_does_not_claim_daily_positioning():
    data = dataset()
    data["rows"][-1]["oi_asof_date"] = None
    result = report(data)
    assert result["rows"][-1]["open_interest"] is not None
    assert result["daily"][-1]["oi_total"] is None
    assert result["changes"][2]["status"] == "incomparable"


def test_repeated_oi_asof_does_not_establish_new_reporting_period():
    data = dataset()
    for row in data["rows"]:
        row["oi_asof_date"] = "2026-11-05"
    result = report(data)
    assert result["changes"][2]["reason"] == "oi_asof_not_advanced"
    assert result["changes"][2]["delta"] is None


@pytest.mark.parametrize("change", [
    lambda d: d["rows"].append(deepcopy(d["rows"][0])),
    lambda d: d["rows"][0].update(high=1, low=9),
    lambda d: d["rows"][0].update(high=1, low=2, open=None, close=None),
    lambda d: d["rows"][0].update(high=1, low=None, open=2, close=None),
    lambda d: d["rows"][0].update(volume=-1),
    lambda d: d["rows"][0].update(volume=1.5),
    lambda d: d["rows"][0].update(close=float("nan")),
    lambda d: d["rows"][0].update(strike=True),
    lambda d: d["rows"][0].update(oi_asof_date="2026-11-10"),
    lambda d: d.update(source={"kind": "ibkr_historical", "verified": True}),
    lambda d: d.update(multiplier=10),
    lambda d: d.update(expiry="2026-11-01"),
])
def test_rejects_ambiguous_or_invented_observations(change):
    data = dataset()
    change(data)
    with pytest.raises(ValidationError):
        HistoryDataset.model_validate(data)


def test_unfinished_session_and_future_observations_are_not_historical():
    data = dataset()
    for row in data["rows"]:
        if row["trading_date"] == "2026-11-10":
            row["trading_date"] = "2026-11-11"
    with pytest.raises(ValueError, match="unfinished sessions"):
        report(data)


def test_one_day_cannot_be_called_a_multi_day_comparison():
    data = dataset()
    data["rows"] = [row for row in data["rows"] if row["trading_date"] == "2026-11-10"]
    result = report(data)
    assert result["quality"]["status"] == "limited"
    assert all(item["delta"] is None for item in result["changes"])


def test_demo_is_always_explicit_and_cannot_be_verified_market_data():
    result = analyze_history(HistoryDataset.model_validate(dataset()), source_kind="demo", now=NOW)
    assert result["source"]["kind"] == "demo" and result["source"]["verified"] is False
    assert "合成" in result["source"]["label"]
    assert result["symbol"] == "DEMO"
    assert "合成" in result["limitations"][0]


def test_trade_prices_remain_per_contract_and_zero_base_does_not_divide():
    data = dataset()
    first = data["rows"][0]
    first.update(open=0, high=0, low=0, close=0)
    result = report(data)
    change = next(item for item in result["contract_changes"] if item["strike"] == first["strike"] and item["right"] == first["right"])
    assert change["change_pct"] is None
    assert "aggregate_price" not in result


def test_intraday_derived_summary_never_claims_official_eod_or_full_session():
    data = dataset()
    data["bar_basis"] = "derived_from_intraday_trades"
    result = report(data)
    assert any("EOD" in text and "不保证" in text for text in result["limitations"])
    assert all(item["delta"] is None and item["reason"] == "historical_bar_coverage_unverified" for item in result["changes"] if "volume" in item["id"])
    assert any(item["id"].startswith("h.contract.") and item["status"] == "comparable" for item in result["evidence"])


def test_extremely_small_price_base_does_not_create_nonfinite_json():
    import json
    data = dataset()
    data["rows"][0].update(open=1e-320, high=1e-320, low=1e-320, close=1e-320)
    result = report(data)
    assert result["contract_changes"][0]["change_pct"] is None
    json.dumps(result, allow_nan=False)
