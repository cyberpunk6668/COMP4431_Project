"""Local preflight by default; --live makes exactly two explicit model requests."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.llm import DeepSeek
from app.options_demo import DemoRequest, QUESTIONS, run_demo


class Trace:
    def __init__(self, delegate):
        self.delegate = delegate
        self.calls = []

    async def complete(self, messages, *, json_output):
        record = {"messages": messages, "raw_answer": None}
        self.calls.append(record)
        record["raw_answer"] = await self.delegate.complete(messages, json_output=json_output)
        return record["raw_answer"]


async def main(live):
    config = Settings()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {"checked_at": stamp, "mode": "live" if live else "preflight",
              "gateway_requests": 0, "results": [], "status": "passed"}
    if live and not config.online:
        report.update(status="skipped", reason="Model is not configured or offline mode is enabled")
    else:
        trace = Trace(DeepSeek(config))
        for frame, question in ((0, QUESTIONS[0]), (1, QUESTIONS[2])):
            result = await run_demo(DemoRequest(frame=frame, engine="deepseek" if live else "local",
                                               question=question), config, trace)
            report["results"].append(result)
            if live and result["answer"]["mode"] != "deepseek":
                report["status"] = "failed"
        report["provider_calls"] = trace.calls
        report["actual_model_requests"] = len(trace.calls)
    target = ROOT / "reports" / f"options_demo_{report['mode']}_{stamp}.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(target),
                      "actual_model_requests": report.get("actual_model_requests", 0)}, ensure_ascii=False))
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Send two billable requests to the configured model")
    arguments = parser.parse_args()
    raise SystemExit(asyncio.run(main(arguments.live)))
