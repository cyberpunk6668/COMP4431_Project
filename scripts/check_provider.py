"""Explicit live integration check. Makes one small, billable DeepSeek request.

Does not print/store credentials, request headers or provider error bodies.
"""
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import ROOT, Settings
from app.llm import DeepSeek, ProviderError


async def main():
    settings = Settings()
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "model": settings.model,
              "endpoint": "https://api.deepseek.com/chat/completions", "test": "live_provider_connectivity"}
    tick = time.perf_counter()
    if not settings.online:
        report.update(status="skipped", reason="No key or offline mode enabled")
    else:
        try:
            answer = await DeepSeek(settings).complete([
                {"role": "system", "content": "This is an integration test. Reply with the exact phrase requested, without other content."},
                {"role": "user", "content": "Reply exactly: FinPilot connection verified"},
            ])
            report.update(status="passed" if "FinPilot connection verified" in answer else "unexpected_output", response=answer[:200])
        except ProviderError as exc:
            report.update(status="failed", reason=exc.code)
    report["latency_ms"] = round((time.perf_counter() - tick) * 1000, 2)
    output = ROOT / "reports" / "provider_check.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
