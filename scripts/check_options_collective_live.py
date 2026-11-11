"""Exercise joint reports against IBKR or an actual cloud model with synthetic inputs."""
import argparse
import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json

from app.config import ROOT, Settings
from app.llm import DeepSeek
from app.options_ibkr import IBKROptionsProvider
from app.options_service import OptionsBatchRequest, OptionsService
from app.options_narrative import read_model_report


def synthetic_snapshot(symbol: str):
    now = datetime.now(UTC)
    stamp = now.isoformat()
    expiry = (now.date() + timedelta(days=21)).isoformat()
    quotes = []
    for index, strike in enumerate((90, 95, 100, 105, 110)):
        for right in ("C", "P"):
            volume = (5, 10, 70, 10, 5)[index] if right == "C" else (2, 5, 12, 3, 3)[index]
            delta = (0.8, 0.65, 0.5, 0.25, 0.1)[index]
            if right == "P":
                delta = (-0.1, -0.25, -0.5, -0.65, -0.8)[index]
            if symbol == "BBB":
                volume = 10 if right == "C" else 25
            quotes.append({
                "strike": strike, "right": right, "expiration": expiry, "bid": 4.8, "ask": 5.2,
                "volume": volume, "open_interest": 100 if right == "C" else 200,
                "delta": delta, "implied_volatility": 0.22 if right == "C" else 0.30,
                "greeks_basis": "model", "market_data_type": 3,
                **{key: stamp for key in ("received_at", "quote_received_at", "greeks_received_at", "volume_received_at", "open_interest_received_at")},
            })
    return {"source": "fixture", "symbol": symbol, "expiration": expiry, "currency": "USD",
            "trading_class": symbol, "multiplier": 100, "requested_strikes": [90, 95, 100, 105, 110],
            "started_at": stamp, "received_at": stamp, "quotes": quotes,
            "underlying": {"price": 100, "bid": 99.9, "ask": 100.1, "price_basis": "midpoint", "market_data_type": 3, "received_at": stamp}}


class SyntheticGateway:
    async def snapshot(self, symbol, expiry, strike_count, market_data_type):
        return deepcopy(synthetic_snapshot(symbol))


async def run(cloud_fixture: bool):
    settings = Settings()
    gateway = SyntheticGateway() if cloud_fixture else IBKROptionsProvider()
    cloud = DeepSeek(settings)
    diagnostics = []
    if cloud_fixture:
        complete = cloud.complete

        async def recorded_complete(messages, **kwargs):
            content = await complete(messages, **kwargs)
            payload = json.loads(messages[1]["content"])
            allowed = {item["id"] for cohort in payload["cohorts"] for item in cohort["evidence"]}
            allowed.update(item["id"] for item in payload["comparisons"])
            try:
                read_model_report(content, allowed)
            except ValueError as error:
                diagnostics.append({"validation_error": str(error), "response": content})
            return content

        cloud.complete = recorded_complete
    service = OptionsService(gateway, cloud, settings)
    request = OptionsBatchRequest(
        items=[{"symbol": symbol} for symbol in (("AAA", "BBB") if cloud_fixture else ("AAPL", "MSFT"))],
        radius=2 if cloud_fixture else 1, market_data_type=3, interpret_with_llm=cloud_fixture,
    )
    result = await service.run_batch(request)
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "scope": "Actual DeepSeek, synthetic anonymized aggregate inputs" if cloud_fixture else "Actual read-only IB Gateway, no cloud call",
        "successful_reports": len(result["reports"]), "failures": result["failures"],
        "comparison_status": result["comparison"]["assessment"]["status"],
        "cohorts": [{"market_data_status": item["quality"]["market_data_status"],
                     "collective_status": item["collective"]["assessment"]["status"],
                     "findings": len(item["collective"]["assessment"]["findings"]),
                     "conflicts": len(item["collective"]["assessment"]["conflicts"]),
                     "capture_age_seconds": item["capture_age_seconds"]} for item in result["reports"]],
        "interpretation": result["interpretation"],
    }
    expected = result["interpretation"]["status"] == "ok" if cloud_fixture else len(result["reports"]) == 2
    report["status"] = "passed" if expected else "incomplete"
    if diagnostics:
        (ROOT / "tmp/options_collective_model_debug_v7.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps([item["validation_error"][:350] for item in diagnostics], ensure_ascii=True))
    destination = ROOT / "reports" / ("options_collective_cloud_v7.json" if cloud_fixture else "options_collective_gateway_v7.json")
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "interpretation"}, ensure_ascii=True, indent=2))
    print(json.dumps({"model_status": report["interpretation"]["status"], "reason": report["interpretation"].get("reason")}, indent=2))
    return 0 if expected else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cloud-fixture", action="store_true", help="Call configured DeepSeek with synthetic evidence instead of reading IBKR")
    raise SystemExit(asyncio.run(run(parser.parse_args().cloud_fixture)))
