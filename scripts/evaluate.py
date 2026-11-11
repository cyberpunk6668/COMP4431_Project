"""Reproducible, API-free retrieval acceptance evaluation.

Run: python scripts/evaluate.py
Metrics deliberately do not make claims about generated answer correctness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.knowledge import KnowledgeRetriever


def evaluate(cases_path: Path, knowledge_path: Path) -> dict:
    suite = json.loads(cases_path.read_text(encoding="utf-8"))
    retriever = KnowledgeRetriever(knowledge_path)
    known_ids = {d["id"] for d in retriever.documents}
    results = []
    durations = []
    positive_recalls = []
    reciprocal_ranks = []
    positive_hits = []
    rejections = []
    for case in suite["cases"]:
        expected = set(case["expected_source_ids"])
        if expected - known_ids:
            raise ValueError(f"Unknown expected source IDs in {case['id']}")
        started = time.perf_counter()
        actual = [d["id"] for d in retriever.search(case["query"], limit=3)]
        elapsed_ms = (time.perf_counter() - started) * 1000
        durations.append(elapsed_ms)
        relevant_ranks = [i+1 for i, source in enumerate(actual) if source in expected]
        recall = len(expected.intersection(actual))/len(expected) if expected else None
        mrr = 1/min(relevant_ranks) if relevant_ranks else 0
        if expected:
            positive_recalls.append(recall)
            reciprocal_ranks.append(mrr)
            positive_hits.append(bool(relevant_ranks))
        else:
            rejections.append(not actual)
        results.append({**case, "retrieved_source_ids": actual, "recall_at_3": recall,
                        "reciprocal_rank_at_3": mrr if expected else None,
                        "passed": expected.issubset(actual) if expected else not actual,
                        "latency_ms": round(elapsed_ms, 3)})
    latencies = sorted(durations)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation_type": "local bilingual lexical retrieval acceptance (no LLM call)",
        "limitations": suite["limitations"],
        "knowledge_sha256": hashlib.sha256(knowledge_path.read_bytes()).hexdigest(),
        "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        "document_count": len(retriever.documents),
        "case_count": len(results),
        "positive_case_count": len(positive_recalls),
        "negative_case_count": len(rejections),
        "metrics": {
            "mean_recall_at_3": round(statistics.mean(positive_recalls), 4),
            "hit_rate_at_3": round(statistics.mean(positive_hits), 4),
            "mrr_at_3": round(statistics.mean(reciprocal_ranks), 4),
            "out_of_domain_rejection_accuracy": round(statistics.mean(rejections), 4),
            "all_expected_sources_or_correct_rejection_rate": round(sum(r["passed"] for r in results)/len(results), 4),
            "median_latency_ms": round(statistics.median(durations), 3),
            "p95_latency_ms": round(latencies[max(0, math_ceil(0.95*len(latencies))-1)], 3)
        },
        "metric_definitions": {
            "mean_recall_at_3": "Mean fraction of expected relevant IDs found among up to three results, positive cases only.",
            "hit_rate_at_3": "Fraction of positive queries retrieving at least one expected ID.",
            "mrr_at_3": "Mean reciprocal rank of first expected ID, zero if not found; positive queries only.",
            "out_of_domain_rejection_accuracy": "Fraction of negative queries returning no source.",
            "all_expected_sources_or_correct_rejection_rate": "Positive cases require all expected IDs; negatives require no result."
        },
        "results": results
    }


def math_ceil(value: float) -> int:
    return int(value) if value == int(value) else int(value)+1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=ROOT/"evaluation"/"cases.json")
    parser.add_argument("--output", type=Path, default=ROOT/"reports"/"evaluation.json")
    args = parser.parse_args()
    report = evaluate(args.cases, ROOT/"data"/"knowledge.json")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("results", "metric_definitions")}, ensure_ascii=False, indent=2))
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
