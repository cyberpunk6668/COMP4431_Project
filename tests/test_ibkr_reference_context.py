"""Closing references never become tradable quotes or model-invented times."""
from datetime import UTC, datetime

from app.options_analytics import analyze_option_snapshot
from app.options_collective import build_collective_analysis
from app.options_chat import describe_analysis, _snapshot_notice


def close_snapshot():
    stamp = datetime.now(UTC).isoformat()
    return {
        "source": "ibkr", "symbol": "TEST", "expiration": "2030-01-18", "currency": "USD",
        "received_at": stamp, "requested_strikes": [95, 100, 105],
        "underlying": {"price": 100, "price_basis": "close", "close": 100, "close_received_at": stamp,
                       "bid": None, "ask": None, "last": None, "last_trade_at": None,
                       "received_at": stamp, "market_data_type": 3},
        "quotes": [{"strike": strike, "right": right, "expiration": "2030-01-18", "close": 2.5,
                    "close_received_at": stamp, "received_at": stamp, "market_data_type": 3}
                   for strike in (95, 100, 105) for right in ("C", "P")],
    }


def test_close_only_counts_as_received_data_without_inflating_bid_ask_coverage():
    snapshot = close_snapshot()
    analysis = analyze_option_snapshot(snapshot)
    assert analysis["quality"]["market_data_status"] == "delayed"
    assert analysis["quality"]["received_contracts"] == 6
    assert analysis["quality"]["valid_quote_contracts"] == 0
    assert analysis["quality"]["quote_coverage"] == 0
    assert not analysis["quality"]["llm_eligible"]
    assert analysis["metrics"]["atm_straddle"]["value"] is None
    assert analysis["metrics"]["iv_skew_25_delta"]["value"] is None
    collective = build_collective_analysis(snapshot, analysis)
    assert collective["volatility"]["atm_iv"] is None
    assert collective["liquidity"]["median_relative_spread_pct"] is None


def test_chat_context_discloses_reference_basis_without_inventing_market_time():
    snapshot = close_snapshot()
    result = describe_analysis({"analysis_id": "reference", "snapshot": snapshot})
    scope = result["scopes"][0]
    assert scope["reference_basis"] == "close" and scope["reference_only"]
    assert scope["reference_last_trade_at"] is None
    assert scope["reference_close_received_at"] == snapshot["underlying"]["close_received_at"]
    assert "收盘参考价" in _snapshot_notice(result, "zh")
    assert "not a current executable quote" in _snapshot_notice(result, "en")
