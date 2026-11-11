"""Live RAG integration checks: two billable generated answers plus local routes."""
import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import ROOT, Settings
from app.knowledge import KnowledgeRetriever
from app.llm import DeepSeek
from app.service import ChatService


async def main():
    settings = Settings()
    service = ChatService(KnowledgeRetriever(settings.knowledge_path), DeepSeek(settings), settings)
    cases = [
        ("zh_rag", "什么是分散投资？它能消除所有投资风险吗？", "zh", "deepseek"),
        ("en_rag", "Explain the difference between nominal annual interest compounded monthly and APY.", "en", "deepseek"),
        ("deterministic_tool", "compound principal=10000 annual_rate=5 years=10 monthly_contribution=500", "en", "calculator"),
        ("live_data_boundary", "今天苹果的股价是多少？", "zh", "offline"),
        ("out_of_domain", "How do I bake sourdough bread?", "en", "offline"),
    ]
    rows = []
    for name, question, lang, expected in cases:
        tick = time.perf_counter()
        result = await service.answer(question, [], lang)
        source_ids = [s["id"] for s in result["sources"]]
        cited = re.findall(r"\[([^\]]+)\]", result["answer"])
        good_citations = bool(set(source_ids) & set(cited)) if expected == "deepseek" else True
        rows.append({"case": name, "question": question, "expected_mode": expected,
                     "passed": result["mode"] == expected and good_citations,
                     "latency_ms": round((time.perf_counter() - tick) * 1000, 2), **result})
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "model": settings.model,
              "passed": sum(r["passed"] for r in rows), "total": len(rows), "results": rows,
              "limits": "Small integration sample, not a guarantee of financial accuracy, adversarial robustness or production readiness."}
    (ROOT / "reports" / "live_integration.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "total": report["total"], "cases": [{k:r[k] for k in ("case", "passed", "mode", "latency_ms")} for r in rows]}, ensure_ascii=True, indent=2))
    return int(report["passed"] != report["total"])


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
