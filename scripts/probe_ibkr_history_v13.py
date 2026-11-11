"""Bounded historical stock/call/put probe; no external requests without --run.

Uses the production history provider. Three sequential 1-hour RTH TRADES queries,
no streaming quotes/accounts/orders/models. Daily values are locally derived
from observed bars, not native EOD or verified full-session/settlement values.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.options_history_ibkr import (
    HISTORY_MESSAGES, HISTORY_TIMEOUT, MAX_BARS_PER_REQUEST, NY,
    IBKRHistoryProvider, aggregate_days, completed_window, error_category,
    make_callbacks, normalize_bar, number, request_history,
)
from app.options_ibkr import IBKRConfig, IBKROptionsError


async def probe(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    config = IBKRConfig.from_env()
    if args.client_id is not None:
        config = replace(config, client_id=args.client_id)
    return await IBKRHistoryProvider(config).fetch(args.symbol, args.expiry, args.strike, args.days)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Explicitly allow three bounded IBKR historical queries; no models")
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--expiry", default="2026-11-13")
    parser.add_argument("--strike", type=float, default=350)
    parser.add_argument("--days", type=int, choices=(3, 4, 5), default=5, help="Completed calendar-day lookback, not guaranteed sessions")
    parser.add_argument("--client-id", type=int)
    args = parser.parse_args(argv)
    if not args.run:
        parser.print_help()
        print("No --run: zero external requests, no Gateway or model connection.")
        return 0
    args.symbol = args.symbol.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]*(?:[ .-][A-Z0-9]+)?", args.symbol) or len(args.symbol) > 12:
        parser.error("Invalid US stock/ETF symbol")
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", args.expiry):
            raise ValueError
        date.fromisoformat(args.expiry)
    except ValueError:
        parser.error("Expiry must be an ISO calendar date")
    if number(args.strike) is None or args.strike <= 0:
        parser.error("Strike must be positive and finite")
    if args.client_id is not None and not 1 <= args.client_id <= 2**31 - 1:
        parser.error("Invalid client ID")
    try:
        report = asyncio.run(probe(args))
    except IBKROptionsError as error:
        diagnostics = error.diagnostics or {}
        report = {"checked_at": datetime.now(UTC).isoformat(), "status": "failed",
                  "stage": diagnostics.get("stage", "preflight"), "error_code": error.code,
                  "diagnostics": diagnostics, "history_requests": diagnostics.get("history_requests", 0), "model_requests": 0}
    except ValueError:
        report = {"checked_at": datetime.now(UTC).isoformat(), "status": "failed", "stage": "preflight",
                  "error_code": "ibkr_invalid_config", "history_requests": 0, "model_requests": 0}
    destination = ROOT / "reports/ibkr_history_probe_v13.json"
    if destination.exists():
        destination = destination.with_stem(destination.stem + "_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": destination.relative_to(ROOT).as_posix(),
                      "history_requests": report["history_requests"], "model_requests": 0}, ensure_ascii=False))
    return int(report["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
