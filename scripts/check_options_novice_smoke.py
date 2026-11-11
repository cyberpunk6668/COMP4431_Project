"""Verify plain-language reports with synthetic data or read-only IBKR data."""
import argparse
import asyncio
from datetime import UTC, datetime
import json

from app.config import ROOT, Settings
from app.llm import DeepSeek
from app.options_ibkr import IBKROptionsProvider
from app.options_service import OptionsBatchRequest, OptionsService
from scripts.check_options_collective_live import SyntheticGateway


async def run(gateway_enabled: bool, cloud_enabled: bool):
    settings = Settings()
    gateway = IBKROptionsProvider() if gateway_enabled else SyntheticGateway()
    service = OptionsService(gateway, DeepSeek(settings), settings)
    symbols = ("AAPL", "MSFT") if gateway_enabled else ("AAA", "BBB")
    result = await service.run_batch(OptionsBatchRequest(
        items=[{"symbol": symbol} for symbol in symbols], radius=1 if gateway_enabled else 2,
        market_data_type=3, interpret_with_llm=cloud_enabled,
    ))
    brief = result["plain_brief"]
    passed = bool(brief["headline"] and brief["cards"] and brief["next_steps"])
    if cloud_enabled:
        passed = passed and result["interpretation"]["status"] == "ok"
    report = {
        "checked_at": datetime.now(UTC).isoformat(), "status": "passed" if passed else "incomplete",
        "scope": "Actual IB Gateway, no cloud" if gateway_enabled else "Synthetic inputs with actual DeepSeek" if cloud_enabled else "Synthetic inputs, no external requests",
        "successful_reports": len(result["reports"]), "failures": result["failures"],
        "plain_brief": brief,
        "interpretation": result["interpretation"] if cloud_enabled else {"status": result["interpretation"]["status"]},
    }
    if gateway_enabled:
        report["plain_brief"] = {
            "status": brief["status"], "freshness_mode": brief["freshness"].get("mode"),
            "card_ids": [item["id"] for item in brief["cards"]],
            "item_statuses": [item["status"] for item in brief.get("items", [])],
        }
    destination = ROOT / "reports" / ("options_novice_gateway_v8.json" if gateway_enabled else "options_novice_cloud_v8.json" if cloud_enabled else "options_novice_smoke_v8.json")
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "scope": report["scope"], "reports": len(result["reports"]),
                      "brief_status": brief["status"], "cards": len(brief["cards"]), "model_status": result["interpretation"]["status"]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--gateway", action="store_true", help="Read actual IBKR delayed batches without calling the model")
    mode.add_argument("--cloud-fixture", action="store_true", help="Call DeepSeek with synthetic aggregate inputs")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.gateway, args.cloud_fixture)))
