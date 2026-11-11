"""Opt-in bounded raw market-callback diagnostic; never requests account data.

Wire records are limited to market price/size/type/timestamp messages. Broker
error text, account payloads, credentials, orders and model calls are excluded.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import Settings  # Load the same local configuration as the app.
from app.options_ibkr import IBKROptionsProvider, IBKROptionsError, _Ticks


async def run(symbol, mode, seconds):
    record = {"checked_at": datetime.now(timezone.utc).isoformat(), "symbol": symbol,
              "requested_market_data_type": mode, "observation_seconds": seconds,
              "scope": "Actual local IB Gateway, one stock-only stream, no account/order/model requests.",
              "wire": [], "callbacks": []}
    provider = IBKROptionsProvider()
    try:
        async with provider._session() as (client, callbacks, Stock, _Option, subscriptions, _started):
            decode = client.decoder.interpret

            def observed(fields):
                if fields and fields[0] in {"1", "2", "58", "46"} and len(record["wire"]) < 120:
                    record["wire"].append({"at": datetime.now(timezone.utc).isoformat(), "fields": fields})
                decode(fields)

            client.decoder.interpret = observed
            details = await callbacks.request(client, client.reqContractDetails, Stock(symbol, "SMART", "USD"))
            contracts = [item.contract for item in details if item.contract.secType == "STK" and item.contract.currency == "USD"]
            if len(contracts) != 1:
                raise RuntimeError("Underlying did not uniquely qualify")
            stock = contracts[0]
            stock.exchange = "SMART"
            req_id = client.getReqId()
            ticks = _Ticks()
            callbacks.streams[req_id] = ticks
            price_callback, mode_callback = callbacks.priceSizeTick, callbacks.marketDataType

            def price(req, kind, value, size):
                price_callback(req, kind, value, size)
                record["callbacks"].append({"kind": "price", "tick_type": kind, "price": value,
                                            "mode": ticks.mode, "retained_fields": sorted(ticks.values)})

            def feed(req, value):
                before = sorted(ticks.values)
                mode_callback(req, value)
                record["callbacks"].append({"kind": "feed", "value": value, "before_fields": before,
                                            "after_fields": sorted(ticks.values)})

            callbacks.priceSizeTick, callbacks.marketDataType = price, feed
            client.reqMarketDataType(mode)
            subscriptions.append(req_id)
            client.reqMktData(req_id, stock, "", False, False, [])
            await asyncio.sleep(seconds)
            record.update(status="completed", underlying=ticks.underlying(), retained_values=ticks.values,
                          broker_codes=sorted(ticks.codes | callbacks.global_codes))
    except IBKROptionsError as error:
        record.update(status="failed", error_code=error.code)
    target = ROOT / "reports" / f"ibkr_wire_{symbol.lower()}_{mode}_v12.json"
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: record[key] for key in ("status", "symbol", "requested_market_data_type", "underlying", "retained_values", "broker_codes", "error_code") if key in record}))
    print(str(target))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Explicitly permit the read-only broker diagnostic")
    parser.add_argument("--symbol", default="AAPL", choices=["AAPL", "SPY", "MSFT"])
    parser.add_argument("--mode", type=int, default=3, choices=[1, 2, 3, 4])
    parser.add_argument("--seconds", type=int, default=10, choices=range(1, 13))
    args = parser.parse_args()
    if args.run:
        asyncio.run(run(args.symbol, args.mode, args.seconds))
    else:
        parser.print_help()
        print("No broker or model request made.")
