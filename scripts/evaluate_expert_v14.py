"""Offline retrieval evaluation; zero broker, account, HTTP or LLM calls.

Run directly: python scripts/evaluate_expert_v14.py
This evaluates the existing search method without changing its lexicon or ranker.
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

from app.expert_knowledge import DEFAULT_PATH, METHOD, ExpertKnowledge

CASES_PATH = ROOT / "evaluation" / "expert_cases_v14.json"
REPORT_PATH = ROOT / "reports" / "expert_retrieval_v14.json"
K_VALUES = (1, 3, 4, 6)


def rank_metrics(actual: list[str], expected: set[str], k: int) -> dict:
    """Compute IR metrics against a *set* of relevant IDs, including multi-gold.

    MRR deliberately measures the first relevant result; complete multi-facet
    retrieval is measured separately so a good MRR cannot hide a missed source.
    """
    if k <= 0 or not expected:
        raise ValueError("Metrics require positive k and at least one gold ID")
    if len(actual) != len(set(actual)):
        raise ValueError("Duplicate retrieved IDs must not inflate recall")
    top = actual[:k]
    matches = expected.intersection(top)
    first = next((index for index, item in enumerate(top, 1) if item in expected), None)
    return {"recall": len(matches) / len(expected),
            "reciprocal_rank": 1 / first if first else 0.0,
            "all_gold_hit": matches == expected}


def _mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 6) if values else None


def _summarize(rows: list[dict], k_values: tuple[int, ...]) -> dict:
    relevant = [row for row in rows if row["relevant_ids"]]
    unrelated = [row for row in rows if not row["relevant_ids"]]
    return {
        "queries": len(rows), "relevant_queries": len(relevant),
        "no_hit_queries": len(unrelated),
        "relevant_query_metrics": {
            str(k): {"recall_at_k": _mean([r["metrics"][str(k)]["recall"] for r in relevant]),
                     "mrr_at_k": _mean([r["metrics"][str(k)]["reciprocal_rank"] for r in relevant]),
                     "all_gold_hit_rate_at_k": _mean([float(r["metrics"][str(k)]["all_gold_hit"]) for r in relevant]),
                     "facet_recall_at_k": _mean([r["metrics"][str(k)]["facet_recall"] for r in relevant])}
            for k in k_values},
        "no_hit_abstention_rate": _mean([float(not r["retrieved_ids"]) for r in unrelated]),
        "no_hit_false_positive_rate": _mean([float(bool(r["retrieved_ids"])) for r in unrelated]),
    }


def evaluate(cases_path: Path = CASES_PATH, knowledge_path: Path = DEFAULT_PATH,
             k_values: tuple[int, ...] = K_VALUES) -> dict:
    if not k_values or any(not isinstance(k, int) or k < 1 or k > 6 for k in k_values):
        raise ValueError("The existing retriever supports top-k from 1 through 6")
    suite = json.loads(cases_path.read_text(encoding="utf-8"))
    retriever = ExpertKnowledge(knowledge_path)
    docs = {doc["id"]: doc for doc in retriever.documents}
    facets = {facet for doc in docs.values() for facet in doc.get("supports", [])}
    case_ids = set()
    rows = []
    for case in suite["cases"]:
        if not case.get("id") or case["id"] in case_ids:
            raise ValueError("Each evaluation case requires a unique ID")
        case_ids.add(case["id"])
        expected = set(case["relevant_ids"])
        required = set(case["required_facets"])
        if len(case["relevant_ids"]) != len(expected) or expected - docs.keys():
            raise ValueError(f"Unknown or duplicated gold IDs: {case['id']}")
        if required - facets or bool(expected) != bool(required):
            raise ValueError(f"Invalid gold claim facets: {case['id']}")
        if expected and not required <= {f for i in expected for f in docs[i].get("supports", [])}:
            raise ValueError(f"Gold documents do not support required facets: {case['id']}")
        if not isinstance(case.get("query"), str) or not case["query"].strip():
            raise ValueError(f"Empty query: {case['id']}")
        started = time.perf_counter()
        found = retriever.search(case["query"], limit=max(k_values))
        elapsed = (time.perf_counter() - started) * 1000
        actual = [doc["id"] for doc in found]
        metrics = {}
        for k in k_values:
            if expected:
                metrics[str(k)] = rank_metrics(actual, expected, k)
                covered = {f for doc in found[:k] for f in doc.get("supports", [])}
                metrics[str(k)]["facet_recall"] = len(required & covered) / len(required)
        rows.append({**case, "retrieved_ids": actual, "metrics": metrics,
                     "missed_ids_at_4": sorted(expected - set(actual[:4])),
                     "retrieval_ms": round(elapsed, 3),
                     "ranking": [{"id": doc["id"], "supports": doc.get("supports", []),
                                  "retrieval": doc["retrieval"]} for doc in found]})
    summary = _summarize(rows, k_values)
    return {
        "version": suite.get("version", "14.0.0"), "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "evaluated_with_limitations", "method": METHOD,
        "scope": "Unmodified raw ExpertKnowledge.search only; excludes chat query expansion, claim-source validation and model generation.",
        "external_calls": {"http": 0, "ibkr": 0, "llm": 0},
        "corpus_documents": len(docs), "support_facets": len(facets),
        "inputs": {"cases": cases_path.name, "corpus": knowledge_path.name,
                   "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
                   "corpus_sha256": hashlib.sha256(knowledge_path.read_bytes()).hexdigest(),
                   "retriever_sha256": hashlib.sha256((ROOT / "app" / "expert_knowledge.py").read_bytes()).hexdigest()},
        "construction": suite["construction"], "metric_definitions": suite["metric_definitions"],
        "summary": summary,
        "by_language": {language: _summarize([r for r in rows if r["language"] == language], k_values)
                        for language in sorted({r["language"] for r in rows})},
        "by_kind": {kind: _summarize([r for r in rows if r["kind"] == kind], k_values)
                    for kind in sorted({r["kind"] for r in rows})},
        "limitations": [
            "Gold relevance is manually authored by a project maintainer, not independently adjudicated.",
            "Split role and prior exposure are recorded in construction; this is not a blind external benchmark.",
            "No answer accuracy, source entailment, numeric correctness or prediction performance is measured.",
            "Facet coverage is a reviewed metadata mapping, not an automatic proof that an answer is entailed.",
            "Known misses and incidental lexical matches are retained; no ranker changes were made from this evaluation."
        ],
        "cases": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=CASES_PATH)
    parser.add_argument("--knowledge", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--out", type=Path, default=REPORT_PATH)
    args = parser.parse_args()
    report = evaluate(args.cases, args.knowledge)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.out), "summary": report["summary"],
                      "external_calls": report["external_calls"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
