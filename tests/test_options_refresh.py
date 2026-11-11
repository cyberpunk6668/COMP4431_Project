import asyncio
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from app.config import Settings
from app.options_ibkr import IBKROptionsError
from app.options_refresh import attach_refresh_request, build_refresh_request, capture_refresh
from app.options_service import OptionsBatchRequest, OptionsRequest, OptionsService


def report(symbol="AAA", expiry="2030-01-18", count=5, mode=3):
    return {"snapshot": {"symbol": symbol, "expiration": expiry,
                         "requested_strikes": list(range(90, 90 + count)),
                         "requested_market_data_type": mode}}


def test_new_request_pins_resolved_expiry_and_preserves_exact_radius_and_feed():
    original = report(expiry="2000-01-21", count=3)
    untouched = deepcopy(original)
    request = OptionsRequest(symbol="AAA", radius=6, interpret_with_llm=True, market_data_type=None)
    attached = attach_refresh_request(original, request)
    assert original == untouched and "refresh_request" not in original
    restored = build_refresh_request(attached, "en")
    assert isinstance(restored, OptionsRequest)
    assert restored.expiry == "2000-01-21"  # Never roll an expired successful date.
    assert restored.radius == 6  # A short returned chain must not shrink a known request.
    assert restored.market_data_type == 3
    assert not restored.interpret_with_llm and restored.language == "en"
    assert request.expiry is None and request.interpret_with_llm


def test_batch_preserves_request_order_and_retries_failed_original_expiry():
    original = {
        "reports": [report("AAA"), report("BBB", "2030-02-15")],
        "failures": [{"symbol": "FAIL", "expiry": None, "code": "ibkr_entitlement_missing"}],
    }
    request = OptionsBatchRequest(items=[{"symbol": "FAIL"}, {"symbol": "AAA"},
                                         {"symbol": "BBB", "expiry": "2030-02-15"}], radius=5, market_data_type=1)
    attached = attach_refresh_request(original, request)
    restored = build_refresh_request(attached, "zh")
    assert isinstance(restored, OptionsBatchRequest)
    assert [item.model_dump() for item in restored.items] == [
        {"symbol": "FAIL", "expiry": None}, {"symbol": "AAA", "expiry": "2030-01-18"},
        {"symbol": "BBB", "expiry": "2030-02-15"},
    ]
    assert restored.radius == 5 and restored.market_data_type == 1
    assert not restored.interpret_with_llm


def test_duplicate_resolved_scope_is_refreshed_once():
    original = {"reports": [report()], "failures": [
        {"symbol": "AAA", "expiry": "2030-01-18", "code": "duplicate_resolved_contract_scope"}]}
    request = OptionsBatchRequest(items=[{"symbol": "AAA"}, {"symbol": "AAA", "expiry": "2030-01-18"}])
    attached = attach_refresh_request(original, request)
    restored = build_refresh_request(attached, "zh")
    assert [item.model_dump() for item in restored.items] == [{"symbol": "AAA", "expiry": "2030-01-18"}]


@pytest.mark.parametrize("count,radius", [(1, 1), (2, 1), (3, 1), (7, 3), (13, 6), (15, 6)])
def test_v10_legacy_radius_is_inferred_with_api_bounds(count, radius):
    restored = build_refresh_request(report(count=count))
    assert restored.radius == radius and restored.market_data_type == 3
    assert restored.symbol == "AAA" and restored.expiry == "2030-01-18"
    assert not restored.interpret_with_llm


def test_v10_partial_batch_recovers_fixed_successes_and_original_failures():
    original = {"reports": [report("AAA", count=3), report("BBB", count=9)],
                "failures": [{"symbol": "MISS", "expiry": "2030-03-15", "code": "ibkr_underlying_unavailable"}]}
    restored = build_refresh_request(original, "en")
    assert restored.radius == 4 and restored.market_data_type == 3
    assert [item.model_dump() for item in restored.items] == [
        {"symbol": "AAA", "expiry": "2030-01-18"}, {"symbol": "BBB", "expiry": "2030-01-18"},
        {"symbol": "MISS", "expiry": "2030-03-15"},
    ]


@pytest.mark.parametrize("invalid", [
    {}, {"snapshot": {"symbol": "AAA", "expiration": "2030-01-18", "requested_strikes": []}},
    {**report(), "refresh_request": {"kind": "unsupported", "request": {}}},
    {**report(), "refresh_request": {"kind": "single", "request": {"symbol": "AAA", "expiry": None}}},
    {**report(), "refresh_request": {"kind": "single", "request": {"symbol": "BBB", "expiry": "2030-01-18"}}},
    {"reports": [report(f"SYM{index}") for index in range(5)]},
    {"reports": [report("AAA", mode=1), report("BBB", mode=3)]},
])
def test_invalid_saved_scope_fails_before_any_collection(invalid):
    with pytest.raises(IBKROptionsError) as raised:
        build_refresh_request(invalid)
    assert raised.value.code == "ibkr_refresh_invalid"


def test_mismatched_server_result_is_not_silently_attached_to_another_request():
    with pytest.raises(IBKROptionsError) as raised:
        attach_refresh_request(report("AAA"), OptionsRequest(symbol="BBB"))
    assert raised.value.code == "ibkr_refresh_invalid"


def snapshot(symbol, expiry):
    stamp = datetime.now(UTC).isoformat()
    return {"source": "fixture", "symbol": symbol, "expiration": expiry, "currency": "USD",
            "trading_class": symbol, "multiplier": 100, "requested_market_data_type": 3,
            "requested_strikes": [95, 100, 105], "started_at": stamp, "received_at": stamp,
            "underlying": {"price": 100, "bid": 99.9, "ask": 100.1, "price_basis": "midpoint", "market_data_type": 3, "received_at": stamp},
            "quotes": [{"strike": strike, "right": right, "expiration": expiry, "bid": 2, "ask": 2.2,
                        "volume": 10 if right == "C" else 20, "open_interest": 100,
                        "market_data_type": 3, "received_at": stamp, "quote_received_at": stamp,
                        "volume_received_at": stamp, "open_interest_received_at": stamp}
                       for strike in [95, 100, 105] for right in ("C", "P")]}


class Gateway:
    def __init__(self, fail_all=False):
        self.fail_all, self.calls = fail_all, []

    async def snapshot(self, symbol, expiry, strike_count, market_data_type):
        self.calls.append((symbol, expiry, strike_count, market_data_type))
        if self.fail_all or symbol == "FAIL":
            raise IBKROptionsError("ibkr_entitlement_missing", "Synthetic missing permission")
        return snapshot(symbol, expiry or "2030-02-15")


class NoLLM:
    async def complete(self, *args, **kwargs):
        raise AssertionError("Refresh must never request model interpretation")


def test_capture_refresh_uses_real_local_analysis_and_preserves_partial_retry(tmp_path):
    gateway = Gateway()
    service = OptionsService(gateway, NoLLM(), Settings(api_key="test-only", offline=False, db_path=tmp_path / "unused.sqlite"))
    original = {"reports": [report("AAA", count=3)],
                "failures": [{"symbol": "FAIL", "expiry": None, "code": "ibkr_entitlement_missing"}]}
    untouched = deepcopy(original)
    refreshed = asyncio.run(capture_refresh(service, original, "en"))
    assert gateway.calls == [("AAA", "2030-01-18", 3, 3), ("FAIL", None, 3, 3)]
    assert refreshed["reports"][0]["collective"]["assessment"]["status"] == "descriptive"
    assert refreshed["reports"][0]["quality"]["market_data_status"] == "delayed"
    assert refreshed["interpretation"]["status"] == "skipped"
    assert build_refresh_request(refreshed).items[1].model_dump() == {"symbol": "FAIL", "expiry": None}
    assert original == untouched


def test_empty_refresh_batch_reports_failure_and_does_not_mutate_old_analysis(tmp_path):
    gateway = Gateway(fail_all=True)
    service = OptionsService(gateway, NoLLM(), Settings(offline=True, db_path=tmp_path / "unused.sqlite"))
    original = {"reports": [report()], "failures": []}
    untouched = deepcopy(original)
    with pytest.raises(IBKROptionsError) as raised:
        asyncio.run(capture_refresh(service, original))
    assert raised.value.code == "ibkr_refresh_empty"
    assert original == untouched and len(gateway.calls) == 1


def test_single_refresh_uses_saved_request_without_model_and_keeps_expiry(tmp_path):
    gateway = Gateway()
    service = OptionsService(gateway, NoLLM(), Settings(offline=True, db_path=tmp_path / "unused.sqlite"))
    original = attach_refresh_request(report(count=3), OptionsRequest(symbol="AAA", radius=6, market_data_type=3, interpret_with_llm=True))
    refreshed = asyncio.run(capture_refresh(service, original))
    assert gateway.calls == [("AAA", "2030-01-18", 13, 3)]
    assert refreshed["interpretation"]["status"] == "skipped"
    assert build_refresh_request(refreshed).radius == 6
