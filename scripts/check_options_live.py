"""Probe configured IB Gateway with actual read-only requests.

Run from the project root as `python -m scripts.check_options_live`.
Only connection state, coverage and diagnostic codes are saved.
"""
import argparse
import asyncio
import json
from datetime import UTC, datetime

from app.config import ROOT
from app.options_analytics import analyze_option_snapshot
from app.options_ibkr import IBKROptionsError, IBKROptionsProvider


async def probe(symbol: str, modes: list[int | None]):
    gateway = IBKROptionsProvider()
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "scope": "Actual configured local IB Gateway. No LLM request or recorded raw market data.",
        "gateway": await gateway.status(),
        "attempts": [],
    }
    for mode in modes:
        attempt = {"symbol": symbol, "requested_market_data_type": mode or report["gateway"]["requested_market_data_type"]}
        report["attempts"].append(attempt)
        try:
            snapshot = await gateway.snapshot(symbol, strike_count=3, market_data_type=mode)
            analysis = analyze_option_snapshot(snapshot)
        except IBKROptionsError as error:
            attempt.update(outcome="broker_request_failed", code=error.code, detail=str(error))
        else:
            attempt.update(
                outcome="sample_received", expiration=snapshot["expiration"], quality=analysis["quality"],
                broker_codes=snapshot.get("broker_codes", []),
                available_metrics=[key for key, metric in analysis["metrics"].items() if metric["value"] is not None],
            )
    destination = ROOT / "reports" / "options_gateway_smoke_v6.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if any(item["outcome"] == "sample_received" for item in report["attempts"]) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--modes", nargs="+", choices=(1, 2, 3, 4), type=int, default=[None])
    args = parser.parse_args()
    raise SystemExit(asyncio.run(probe(args.symbol, args.modes)))
