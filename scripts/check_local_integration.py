"""Exercise the trained local model through the actual HTTP API.

Run only AFTER train/eval GPU processes have exited. No cloud request is made.
Protocol/citation checks are not a financial correctness benchmark.
"""
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"


def main():
    results = []
    with httpx.Client(base_url=BASE, timeout=70) as client:
        model = next(x for x in client.get("/api/models").json()["models"] if x["id"] == "local")
        if not model["available"]:
            raise RuntimeError("Trained adapter and local runtime are not ready")
        cases = [
            ("zh_local_generation", "请解释复利，并说明固定利率假设的限制。", "zh", "local-lora"),
            ("en_local_generation", "Explain FDIC deposit insurance and its limits in the United States.", "en", "local-lora"),
            ("local_calculator_route", "loan principal=1200 annual_rate=0 years=1", "en", "calculator"),
        ]
        for name, question, language, expected in cases:
            tick = time.perf_counter()
            response = client.post("/api/chat", json={"message": question, "language": language, "engine": "local"})
            response.raise_for_status()
            data = response.json()
            citations = re.findall(r"\[([a-zA-Z0-9_-]+)\]", data["answer"])
            source_ids = {x["id"] for x in data["sources"]}
            passed = data["mode"] == expected and (expected == "calculator" or bool(source_ids & set(citations)))
            results.append({"case": name, "passed": passed, "expected_mode": expected, "latency_ms": round((time.perf_counter()-tick)*1000, 2), **data})
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "total": len(results), "passed": sum(x["passed"] for x in results),
              "results": results, "limits": "Actual cached local-model HTTP integration. Checks response mode, completion and supplied citation IDs; raw answers require source-faithfulness review. No DeepSeek comparison or general accuracy claim."}
    (ROOT / "reports" / "local_integration.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("total", "passed", "results")}, ensure_ascii=True, indent=2))
    return int(report["passed"] != report["total"])


if __name__ == "__main__":
    raise SystemExit(main())
