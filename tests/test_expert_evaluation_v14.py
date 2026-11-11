"""Offline checks for source scope metadata and retrieval metric denominators."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from scripts import evaluate_expert_v14 as evaluator


def test_multi_gold_recall_is_not_first_hit_rate():
    metrics = evaluator.rank_metrics(["irrelevant", "gold_a", "gold_b"], {"gold_a", "gold_b"}, 2)
    assert metrics == {"recall": 0.5, "reciprocal_rank": 0.5, "all_gold_hit": False}
    assert evaluator.rank_metrics(["irrelevant", "gold_a", "gold_b"], {"gold_a", "gold_b"}, 3)["all_gold_hit"] is True
    with pytest.raises(ValueError, match="Duplicate"):
        evaluator.rank_metrics(["gold_a", "gold_a"], {"gold_a"}, 2)
    with pytest.raises(ValueError, match="at least one"):
        evaluator.rank_metrics([], set(), 2)


def test_no_hit_cases_do_not_dilute_relevant_recall(tmp_path, monkeypatch):
    docs = [{"id": "expert.a", "supports": ["facet_a"]},
            {"id": "expert.b", "supports": ["facet_b"]},
            {"id": "expert.c", "supports": ["facet_c"]}]
    answers = {"first": [docs[2], docs[0]], "second": [docs[0]],
               "clean": [], "false_positive": [docs[2]]}

    class FixedRetriever:
        def __init__(self, path):
            self.documents = docs

        def search(self, query, limit):
            return [{**d, "retrieval": {"method": "fixed_test"}} for d in answers[query]][:limit]

    monkeypatch.setattr(evaluator, "ExpertKnowledge", FixedRetriever)
    cases = {"construction": {}, "metric_definitions": {}, "cases": [
        {"id": "1", "language": "en", "kind": "single", "query": "first",
         "relevant_ids": ["expert.a"], "required_facets": ["facet_a"]},
        {"id": "2", "language": "en", "kind": "multi", "query": "second",
         "relevant_ids": ["expert.a", "expert.b"], "required_facets": ["facet_a", "facet_b"]},
        {"id": "3", "language": "en", "kind": "none", "query": "clean",
         "relevant_ids": [], "required_facets": []},
        {"id": "4", "language": "en", "kind": "none", "query": "false_positive",
         "relevant_ids": [], "required_facets": []},
    ]}
    cases_path = tmp_path / "cases.json"
    corpus_path = tmp_path / "corpus.json"
    cases_path.write_text(json.dumps(cases), encoding="utf-8")
    corpus_path.write_text("{}", encoding="utf-8")
    report = evaluator.evaluate(cases_path, corpus_path, (2, 4))
    summary = report["summary"]
    assert summary["relevant_queries"] == 2 and summary["no_hit_queries"] == 2
    assert summary["relevant_query_metrics"]["2"] == {
        "recall_at_k": 0.75, "mrr_at_k": 0.75,
        "all_gold_hit_rate_at_k": 0.5, "facet_recall_at_k": 0.75}
    assert summary["no_hit_abstention_rate"] == 0.5
    assert summary["no_hit_false_positive_rate"] == 0.5
    assert report["external_calls"] == {"http": 0, "ibkr": 0, "llm": 0}


def test_official_source_scope_and_gold_labels_are_auditable():
    corpus = json.loads(evaluator.DEFAULT_PATH.read_text(encoding="utf-8"))
    suite = json.loads(evaluator.CASES_PATH.read_text(encoding="utf-8"))
    docs = {doc["id"]: doc for doc in corpus["documents"]}
    allowed_hosts = {"www.interactivebrokers.com", "www.optionseducation.org", "www.cboe.com"}
    for doc in docs.values():
        assert doc["supports"] and set(doc["supports"]) <= set(corpus["support_facets"])
        assert urlparse(doc["url"]).hostname in allowed_hosts
        assert all(doc["source_review"][key] for key in ("direct_support", "analytical_inference", "boundaries", "section"))
    assert docs["expert.history_limits"]["supports"] == ["expired_eod_limits"]
    assert docs["expert.history_bars"]["supports"] == ["historical_bar_semantics"]
    assert docs["expert.put_call"]["supports"] == ["put_call_limits"]
    assert docs["expert.history_oi"]["supports"] == ["historical_oi_availability"]
    assert "reqHistoricalData" in docs["expert.history_oi"]["text"]
    assert suite["construction"]["held_out_from_ranker_tuning"] is False
    assert suite["construction"]["split_role"] == "discovery_dev"
    assert suite["construction"]["blind_external_benchmark"] is False
    assert {c["language"] for c in suite["cases"]} == {"en", "zh"}
    assert any(len(c["relevant_ids"]) > 1 for c in suite["cases"])
    assert any(not c["relevant_ids"] for c in suite["cases"])
    for case in suite["cases"]:
        assert case["query"] not in {doc["title"] for doc in docs.values()}
        assert set(case["relevant_ids"]) <= docs.keys()


def test_evaluation_rejects_out_of_range_limit():
    with pytest.raises(ValueError, match="top-k"):
        evaluator.evaluate(k_values=(7,))


def test_new_holdout_split_is_separate_and_blind():
    dev = json.loads(evaluator.CASES_PATH.read_text(encoding="utf-8"))
    blind = json.loads((evaluator.ROOT / "evaluation" / "expert_holdout_v14.json").read_text(encoding="utf-8"))
    assert blind["construction"]["held_out_from_ranker_tuning"] is True
    assert blind["construction"]["blind_to_ranker_author_until_algorithm_freeze"] is True
    assert blind["construction"]["independent_third_party_adjudication"] is False
    assert len(blind["cases"]) == 24
    assert sum(bool(c["relevant_ids"]) for c in blind["cases"]) == 18
    assert sum(c["kind"] == "cross_topic" for c in blind["cases"]) == 4
    assert sum(c["language"] == "zh" for c in blind["cases"]) == 12
    assert {c["id"] for c in dev["cases"]}.isdisjoint(c["id"] for c in blind["cases"])
    assert {c["query"] for c in dev["cases"]}.isdisjoint(c["query"] for c in blind["cases"])
