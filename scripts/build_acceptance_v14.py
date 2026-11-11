"""Build the release evidence index locally; no HTTP, broker or model calls."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def read(name):
    return json.loads((REPORTS / name).read_text(encoding="utf-8"))


def main():
    snapshot = read("snapshot_expert_cloud_v14.json")
    demo = read("expert_demo_cloud_v14.json")
    browser = read("guided_demo_browser_v14.json")
    holdout = read("expert_retrieval_holdout_v14.json")
    assert snapshot["status"] == demo["status"] == "passed_limited"
    assert snapshot["manual_review"]["status"] == demo["manual_review"]["conclusion"] == "accepted_limited"
    assert browser["status"] == "passed"
    xml = ET.parse(REPORTS / "tests_v14.xml").getroot()
    counts = {name: sum(int(s.attrib.get(name, 0)) for s in xml.iter("testsuite"))
              for name in ("tests", "failures", "errors", "skipped")}
    assert counts["tests"] and counts["failures"] == counts["errors"] == 0
    runs = []
    for prefix, kind in (("snapshot_expert_cloud_v14", "snapshot"), ("expert_demo_cloud_v14", "guided_demo")):
        for path in sorted(REPORTS.glob(prefix + "*.json")):
            item = read(path.name)
            generations = item.get("generation_attempts", item.get("server_reported_total_generation_attempts"))
            repairs = item.get("schema_repair_attempts", item.get("server_reported_repair_attempts"))
            if item.get("counters", {}).get("chat_http_requests") == 0:
                generations = repairs = 0
            runs.append({"report": path.relative_to(ROOT).as_posix(), "kind": kind,
                         "checked_at": item["checked_at"], "status": item["status"], "phase": item.get("phase"),
                         "reported_generation_attempts": generations, "reported_schema_repairs": repairs,
                         "new_broker_requests": item.get("broker_requests", item.get("new_broker_requests"))})
    assert len({r["checked_at"] for r in runs}) == len(runs)
    assert all(r["new_broker_requests"] == 0 and r["reported_generation_attempts"] is not None for r in runs)
    frozen = hashlib.sha256((ROOT / "app/expert_knowledge.py").read_bytes()).hexdigest()
    assert frozen == holdout["inputs"]["retriever_sha256"]
    files = ["app/expert_grounding.py", "app/expert_knowledge.py", "app/options_claims.py", "app/options_chat.py",
             "app/history_chat.py", "app/main.py", "web/demo.html", "web/demo.js", "web/demo.css",
             "data/expert_knowledge.json", "reports/tests_v14.xml", "reports/guided_demo_browser_v14.json",
             "reports/expert_demo_cloud_v14.json", "reports/snapshot_expert_cloud_v14.json"]
    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(), "version": "14.0.0", "status": "passed_limited",
        "objective": "Expert RAG integrated with historical/current options chat and an independent interactive demo.",
        "server_tests": counts,
        "browser": {"report": "reports/guided_demo_browser_v14.json", "status": "passed", "checks_per_viewport": 27,
                    "viewport_widths": [320, 390, 1440], "api_mode": "Controlled fixtures; actual local Avatar renderers",
                    "actual_phone_hardware_tested": False},
        "real_model_validation": {
            "snapshot_report": "reports/snapshot_expert_cloud_v14.json", "demo_report": "reports/expert_demo_cloud_v14.json",
            "final_validated_answers": 3, "final_generation_attempts": 6, "final_schema_repairs": 3,
            "first_pass_all_correct": False,
            "all_recorded_generation_attempts_including_failed_runs": sum(r["reported_generation_attempts"] for r in runs),
            "count_basis": "Recorded server-reported generation attempts, not billed tokens/cost or whole-project lifetime.",
            "new_ibkr_market_data_requests": 0, "runs": runs},
        "retrieval": {"blind_report": "reports/expert_retrieval_holdout_v14.json", "recall_at_4": .87037,
                      "mrr_at_4": .796296, "all_gold_hit": [15, 18], "irrelevant_abstention": [4, 6],
                      "retriever_hash_still_matches_freeze": True, "not_answer_accuracy": True},
        "data_scope": {"source": "Previously recorded actual IBKR historical archive", "symbol": "AAPL", "strike": 350,
                       "expiry": "2026-11-13", "contract_sides": ["C", "P"],
                       "dates": ["2026-11-06", "2026-11-09", "2026-11-10"],
                       "full_session_coverage_verified": False, "historical_oi_available": False,
                       "synchronized_bbo_available": False, "volume_changes_comparable": False,
                       "archive_file_sha256": hashlib.sha256((REPORTS / "ibkr_history_probe_v13.json").read_bytes()).hexdigest(),
                       "present_market_sentiment_verified": False},
        "limitations": ["Finite reviewed-facet checks are not general semantic entailment or financial accuracy guarantees.",
                        "All final model answers required one bounded repair; failed runs remain archived.",
                        "Actual cloud testing covers one saved snapshot and one historical dataset.",
                        "Mobile checks use desktop Edge responsive/touch emulation.",
                        "Minor underlying/contract wording ambiguity is recorded in demo manual_review."],
        "documents": ["docs/innovation_rag_v14.md", "docs/demo_v14.md"],
        "sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}}
    (REPORTS / "innovation_acceptance_v14.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "tests": counts,
                      "recorded_model_generations": result["real_model_validation"]["all_recorded_generation_attempts_including_failed_runs"]}))


if __name__ == "__main__":
    main()
