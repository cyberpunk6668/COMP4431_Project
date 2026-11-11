"""The reviewed lexical retriever exposes its ranking and abstains off topic."""
from copy import deepcopy
import json

import pytest

from app.expert_knowledge import DEFAULT_PATH, ExpertKnowledge


@pytest.fixture
def expert():
    return ExpertKnowledge()


def test_corpus_reviewed_provenance_and_unique_ids(expert):
    assert 10 <= len(expert.documents) <= 15
    assert len({doc["id"] for doc in expert.documents}) == len(expert.documents)
    for doc in expert.documents:
        assert doc["id"].startswith("expert.") and doc["reviewed_at"] == "2026-11-11"
        assert doc["publisher"] and doc["topics"] and doc["text"] and doc["text_en"]
        assert doc["url"].startswith(("https://www.optionseducation.org/", "https://www.cboe.com/", "https://www.interactivebrokers.com/"))


@pytest.mark.parametrize("query,expected", [
    ("为什么成交量和未平仓量矛盾", "expert.volume_oi"),
    ("看跌成交增加说明多数人看空吗", "expert.put_call"),
    ("what is implied volatility", "expert.volatility"),
    ("历史分钟BID_ASK能算价差吗", "expert.history_bars"),
    ("IBKR历史订阅权限是什么", "expert.history_permissions"),
    ("未平仓持仓日期和隔夜报告", "expert.oi_cycle"),
    ("样本变化共同合约配对为何重要", "expert.contract_identity"),
])
def test_topic_specific_retrieval(query, expected, expert):
    assert expected in [doc["id"] for doc in expert.search(query)]


@pytest.mark.parametrize("query", ["", "   ", "今天天气怎么样", "write a short sick leave email", "banana recipes", None])
def test_no_irrelevant_padding(query, expert):
    assert expert.search(query) == []


def test_rank_fusion_is_explainable_not_confidence(expert):
    result = expert.search("成交量和未平仓量变化")
    for doc in result:
        trace = doc["retrieval"]
        ranks = [trace[key] for key in ("bm25_rank", "char_rank") if trace[key] is not None]
        assert trace["rrf_score"] == pytest.approx(sum(1/(60+r) for r in ranks), abs=1e-8)
        assert trace["method"] == "bm25_char_ngram_rrf" and trace["embedding"] is False
        assert trace["matched_terms"] or trace["matched_ngrams"]
    assert result[0]["retrieval"]["bm25_rank"] and result[0]["retrieval"]["char_rank"]


def test_query_limits_normalization_determinism_and_no_corpus_mutation(expert):
    original = deepcopy(expert.documents)
    assert expert.search("ＢＩＤ＿ＡＳＫ") == expert.search("bid_ask")
    first = expert.search("期权历史数据比较", limit=30)
    assert len(first) <= 6 and expert.search("成交量", limit=0) == []
    first[0]["topics"].append("mutated")
    assert expert.documents == original
    assert expert.search("成交量") == expert.search("成交量")


@pytest.mark.parametrize("mutation", ["duplicate", "bad_url", "missing_publisher", "empty_topics"])
def test_invalid_corpus_rejected(tmp_path, mutation):
    raw = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    if mutation == "duplicate":
        raw["documents"].append(deepcopy(raw["documents"][0]))
    elif mutation == "bad_url":
        raw["documents"][0]["url"] = "javascript:alert(1)"
    elif mutation == "missing_publisher":
        del raw["documents"][0]["publisher"]
    else:
        raw["documents"][0]["topics"] = []
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        ExpertKnowledge(path)
