"""A delayed fallback advisory does not prove an explicit delayed feed was denied."""
import pytest

from app.options_ibkr import IBKROptionsError, _raise_no_ticks


@pytest.mark.parametrize("mode,expected", [
    (1, "ibkr_entitlement_missing"), (2, "ibkr_entitlement_missing"),
    (3, "ibkr_underlying_unavailable"), (4, "ibkr_underlying_unavailable"),
])
def test_delayed_notice_without_usable_ticks_keeps_requested_feed_distinct(mode, expected):
    with pytest.raises(IBKROptionsError) as caught:
        _raise_no_ticks({10167}, IBKROptionsError("ibkr_underlying_unavailable", "No usable ticks"), mode)
    assert caught.value.code == expected


@pytest.mark.parametrize("mode", [3, 4])
def test_explicit_permission_denial_remains_distinct_from_delayed_notice(mode):
    with pytest.raises(IBKROptionsError) as caught:
        _raise_no_ticks({10167, 354}, IBKROptionsError("ibkr_underlying_unavailable", "No usable ticks"), mode)
    assert caught.value.code == "ibkr_entitlement_missing"
