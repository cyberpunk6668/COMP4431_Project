"""Plan or run a small, source-controlled DeepSeek news comparison.

The default is a local preflight with no network requests. ``--live`` sends
six billable model requests per repeat. Both arms use the configured official
API model and adapter; this is not a test of the DeepSeek website or app.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import ROOT, Settings
from app.knowledge import KnowledgeRetriever
from app.llm import ENDPOINT, DeepSeek, ProviderError
from app.service import SYSTEM, ChatService


QUESTIONS = (
    (
        "ceo_and_dates",
        "截至2026年11月15日，黄仁勋是否已经离任英伟达（NVIDIA）CEO？"
        "请区分离任生效日期与公开公告日期，并说明目前由谁担任 CEO。"
        "对无法核实的部分请明确说明。",
    ),
    (
        "interim_roles",
        "截至2026年11月15日，英伟达（NVIDIA）的 Colette Kress 是临时 CEO "
        "还是正式继任者？她是否继续兼任 CFO，谁担任董事长？"
        "请说明信息的依据与日期。",
    ),
    (
        "evidence_limits",
        "只依据英伟达（NVIDIA）本次 CEO 变更的官方新闻稿与 SEC 8-K，"
        "能否确定英伟达下周的股价涨跌，或据此认定黄仁勋已经违法？"
        "请区分公告确认的事实、推断与尚不确定的事项。",
    ),
)

_SAFE_ERRORS = frozenset({
    "authentication_failed", "insufficient_balance", "rate_limited",
    "provider_unavailable", "incomplete_response", "empty_response",
    "network_or_timeout", "invalid_response",
})


def _safe_error(code: str) -> str:
    return code if code in _SAFE_ERRORS else "provider_error"


def baseline_messages(question: str, *, system_content: str | None = None) -> list[dict]:
    # SYSTEM's citation instruction is conditional on supplied relevant
    # references. This arm supplies none, and supplies no invented source IDs.
    return [
        {"role": "system", "content": system_content if system_content is not None else SYSTEM + "\nRequested language: zh"},
        {"role": "user", "content": question},
    ]


class TraceProvider:
    """Record message bodies and raw text, never credentials or HTTP headers."""

    def __init__(self, delegate=None):
        self.delegate = delegate
        self.calls = []

    async def complete(self, messages):
        call = {"messages": copy.deepcopy(messages), "raw_answer": None,
                "provider_error": None, "latency_ms": None}
        self.calls.append(call)
        if self.delegate is None:
            # Used only to capture ChatService's actual planned request.
            return "Local preflight only; no model request was made."
        tick = time.perf_counter()
        try:
            call["raw_answer"] = await self.delegate.complete(messages)
            return call["raw_answer"]
        except ProviderError as exc:
            call["provider_error"] = _safe_error(exc.code)
            raise ProviderError(call["provider_error"]) from None
        finally:
            call["latency_ms"] = round((time.perf_counter() - tick) * 1000, 2)


async def build_report(settings: Settings, *, live: bool = False,
                       repeats: int = 1, provider=None) -> dict:
    """Return the evidence plan, and optionally the ungraded raw A/B results."""
    if not 1 <= repeats <= 5:
        raise ValueError("repeats must be between 1 and 5")
    retriever = KnowledgeRetriever(settings.knowledge_path)
    report = {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "mode": "live" if live else "preflight",
        "status": "ready",
        "experiment": {
            "provider": "DeepSeek official API",
            "endpoint": ENDPOINT,
            "model": settings.model,
            "provider_configured": settings.online,
            "parameters": {"temperature": 0.2, "max_tokens": 1400,
                           "thinking": "disabled", "stream": False},
            "web_search_enabled": False,
            "tool_configuration": "Neither arm supplies tools or a web-search tool to the API.",
            "network_scope": "Live mode uses the internet for model inference, not web search.",
            "comparison_scope": "Same configured API model; not the DeepSeek website/app.",
            "variable": "Local reference DATA is absent in baseline and supplied by ChatService in RAG.",
            "system_policy": "Baseline copies each actual planned ChatService system message byte-for-byte through the requested-language line, including company-event rules; only the Reference DATA section is removed.",
            "history_policy": "Every arm/question/repeat starts with an empty conversation history.",
            "order_policy": "AB and BA orders alternate by question and repeat.",
            "corpus_sha256": hashlib.sha256(settings.knowledge_path.read_bytes()).hexdigest(),
            "repeats": repeats,
            "planned_provider_requests": len(QUESTIONS) * 2 * repeats,
        },
        "questions": [],
        "results": [],
        "actual_provider_requests": 0,
        "assessment": {
            "status": "manual_review_required",
            "note": "No keyword-based correctness score is calculated. A correct refusal is not a hallucination. Preserve all runs, including failures.",
        },
    }
    # The synthetic provider only captures actual application prompts locally.
    # Never instantiate DeepSeek or call a network client during preflight.
    planner = TraceProvider()
    planning_settings = replace(settings, api_key="local-preflight-placeholder", offline=False)
    planning_service = ChatService(retriever, planner, planning_settings)
    for question_id, question in QUESTIONS:
        sources = retriever.search(question, limit=3)
        before = len(planner.calls)
        await planning_service.answer(question, [], "zh")
        planned_rag = planner.calls[-1]["messages"] if len(planner.calls) > before else None
        baseline_policy = (
            planned_rag[0]["content"].split("\nReference DATA:", 1)[0]
            if planned_rag else None
        )
        report["questions"].append({
            "id": question_id, "prompt": question,
            "retrieved_sources": [
                {key: source[key] for key in ("id", "title", "url", "category", "updated_at")
                 if key in source} for source in sources
            ],
            "planned_requests": {
                "baseline": baseline_messages(question, system_content=baseline_policy),
                "rag": planned_rag,
            },
        })
    if not live:
        return report
    if not settings.online:
        report.update(status="skipped", reason="API key missing or FINPILOT_OFFLINE enabled; no live requests made.")
        return report

    trace = TraceProvider(provider if provider is not None else DeepSeek(settings))
    service = ChatService(retriever, trace, settings)
    baseline_plans = {
        question["id"]: question["planned_requests"]["baseline"]
        for question in report["questions"]
    }
    for repeat in range(1, repeats + 1):
        for question_index, (question_id, question) in enumerate(QUESTIONS):
            arms = ("baseline", "rag") if (repeat + question_index) % 2 else ("rag", "baseline")
            for arm in arms:
                before = len(trace.calls)
                tick = time.perf_counter()
                if arm == "baseline":
                    try:
                        answer = await trace.complete(copy.deepcopy(baseline_plans[question_id]))
                        result = {"answer": answer, "sources": [], "mode": "deepseek"}
                    except ProviderError as exc:
                        result = {"answer": None, "sources": [], "mode": "provider-error",
                                  "warning": _safe_error(exc.code)}
                else:
                    result = await service.answer(question, [], "zh")
                attempted = len(trace.calls) > before
                call = trace.calls[-1] if attempted else {}
                error = call.get("provider_error")
                report["results"].append({
                    "repeat": repeat, "question_id": question_id, "arm": arm,
                    "request_order": len(report["results"]) + 1,
                    "prompt": question,
                    "status": "provider_failed" if error else "generated" if result["mode"] == "deepseek" else "not_generated",
                    "provider_attempted": attempted,
                    "provider_error": error,
                    "messages": call.get("messages"),
                    "raw_answer": call.get("raw_answer"),
                    "answer": result.get("answer"),
                    "mode": result["mode"],
                    "warning": _safe_error(result["warning"]) if result.get("warning") else None,
                    "sources": result.get("sources", []),
                    "source_ids": [source["id"] for source in result.get("sources", [])],
                    "latency_ms": round((time.perf_counter() - tick) * 1000, 2),
                    "provider_latency_ms": call.get("latency_ms"),
                })
    report["actual_provider_requests"] = len(trace.calls)
    report["status"] = "completed" if all(
        result["status"] == "generated" for result in report["results"]
    ) else "completed_with_failures"
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Make six billable model requests per repeat; no web search.")
    parser.add_argument("--repeats", type=int, default=1, choices=range(1, 6))
    parser.add_argument("--output", type=Path, help="Report path; live defaults to a new timestamped file.")
    args = parser.parse_args(argv)
    report = asyncio.run(build_report(Settings(), live=args.live, repeats=args.repeats))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT / "reports" / (
        f"news_demo_live_{stamp}.json" if args.live else "news_demo_preflight.json"
    )
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(output), "mode": report["mode"],
                      "status": report["status"],
                      "actual_provider_requests": report["actual_provider_requests"]},
                     ensure_ascii=True))
    return 0 if report["status"] in {"ready", "completed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
