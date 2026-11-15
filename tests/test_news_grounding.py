"""Dated company evidence stays auditable across narrow leadership follow-ups."""
import asyncio
import json

import pytest

from app.config import Settings
from app.knowledge import KnowledgeRetriever
from app.llm import ProviderError
from app.service import ChatService


class RecordingProvider:
    def __init__(self, answer="已确认临时任命。[example-8k]", error=None):
        self.answer, self.error, self.calls = answer, error, []

    async def complete(self, messages):
        self.calls.append(messages)
        if self.error:
            raise ProviderError(self.error)
        return self.answer


@pytest.fixture
def service_factory(tmp_path):
    documents = []
    for source_id, category, keywords in (
        ("example-8k", "company_news", ["示例公司", "example corp"]),
        ("example-release", "company_news", ["示例公司", "example corp"]),
        ("example-etf", "education", ["ETF"]),
    ):
        zh = "事件生效日期 2026-11-11，公告日期 2026-11-12，本地复核日期 2026-11-15。仅确认临时任命。"
        en = "Effective 2026-11-11; published 2026-11-12; locally reviewed 2026-11-15. An interim appointment only."
        documents.append({
            "id": source_id, "category": category, "keywords": keywords,
            "title": source_id, "url": "https://www.sec.gov/" + source_id,
            "updated_at": "2026-11-15", "text_zh": zh, "text_en": en,
            "text": zh + " " + en,
        })
    path = tmp_path / "knowledge.json"
    path.write_text(json.dumps({"documents": documents}), encoding="utf-8")

    def create(*, online=True, answer="已确认临时任命。[example-8k]", error=None):
        settings = Settings(api_key="test-only" if online else "", offline=not online, knowledge_path=path)
        provider = RecordingProvider(answer, error)
        return ChatService(KnowledgeRetriever(path), provider, settings), provider

    return create


def ask(service, question, history=None, language="zh"):
    return asyncio.run(service.answer(question, history or [], language))


def test_offline_news_exposes_snapshot_metadata_and_is_not_model_success(service_factory):
    service, provider = service_factory(online=False)
    result = ask(service, "示例公司的 CEO 交接情况？")
    assert result["mode"] == "offline" and result["warning"] == "offline_requested"
    assert "未由大模型生成" in result["answer"] and "2026-11-11" in result["answer"]
    assert not provider.calls
    assert {item["id"] for item in result["sources"]} == {"example-8k", "example-release"}
    assert all(item["category"] == "company_news" and item["updated_at"] == "2026-11-15"
               for item in result["sources"])


def test_news_generation_receives_dated_snapshot_and_role_distinction_rules(service_factory):
    service, provider = service_factory()
    ask(service, "示例公司的 CEO 交接情况？")
    prompt = provider.calls[-1][0]["content"]
    assert "dated local snapshots, not live search" in prompt
    assert "event/effective date, publication date" in prompt
    assert "interim appointments from permanent appointments" in prompt
    assert "legal conclusion is not established" in prompt
    assert "Do not infer a future stock price" in prompt
    assert "does not prove that leadership remained unchanged" in prompt
    assert "Distinguish project-authored interpretations" in prompt
    assert "2026-11-11" in prompt and "2026-11-12" in prompt and "2026-11-15" in prompt
    ask(service, "Explain ETF.", language="en")
    assert "dated local snapshots" not in provider.calls[-1][0]["content"]


def test_only_cited_valid_news_sources_are_published(service_factory):
    service, _ = service_factory(answer="临时任命。[example-8k] [fabricated-source]")
    result = ask(service, "示例公司 CEO")
    assert [item["id"] for item in result["sources"]] == ["example-8k"]
    assert result["sources"][0]["updated_at"] == "2026-11-15"
    assert "[unverified citation]" in result["answer"]
    assert "fabricated-source" not in result["answer"]


@pytest.mark.parametrize("question", [
    "那她还兼任 CFO 吗？", "正式继任者是谁？", "那这次交接何时生效？",
    "公告日期是什么时候？", "Does she still serve as CFO?", "Who is the permanent successor?",
])
def test_short_leadership_questions_recover_news_from_user_context(service_factory, question):
    service, provider = service_factory()
    history = [{"role": "user", "content": "示例公司的 CEO 是否离任？"},
               {"role": "assistant", "content": "Unsupported claim about a different company."}]
    result = ask(service, question, history)
    assert result["sources"][0]["id"] == "example-8k"
    assert "[example-8k]" in provider.calls[-1][0]["content"]


def test_followup_chain_recovers_original_news_without_using_assistant_claims(service_factory):
    service, provider = service_factory()
    history = [{"role": "user", "content": "示例公司 CEO 有什么变动？"},
               {"role": "assistant", "content": "Wrongly says the appointment is permanent."},
               {"role": "user", "content": "那她还兼任 CFO 吗？"},
               {"role": "assistant", "content": "Fabricated legal accusation."}]
    result = ask(service, "正式继任者是谁？", history)
    assert result["sources"][0]["category"] == "company_news"
    evidence = provider.calls[-1][0]["content"]
    assert "Fabricated legal accusation" not in evidence
    assert "Wrongly says" not in evidence


@pytest.mark.parametrize("question", [
    "微软的 CEO 是谁？", "Who is Microsoft's CEO?", "帮我写 Python 代码。", "解释一下光合作用。",
])
def test_new_topics_do_not_borrow_previous_company_news(service_factory, question):
    service, provider = service_factory()
    history = [{"role": "user", "content": "示例公司 CEO 是否离任？"}]
    result = ask(service, question, history)
    assert not result["sources"]
    assert "Reference DATA" not in provider.calls[-1][0]["content"]


def test_context_switch_stops_news_lookup_even_when_later_question_mentions_a_role(service_factory):
    service, provider = service_factory()
    history = [{"role": "user", "content": "示例公司 CEO 是否离任？"},
               {"role": "user", "content": "我们换个话题，讨论其他公司。"}]
    result = ask(service, "正式继任者是谁？", history)
    assert not result["sources"]
    assert "Reference DATA" not in provider.calls[-1][0]["content"]


def test_assistant_alone_cannot_create_company_evidence_context(service_factory):
    service, provider = service_factory()
    history = [{"role": "user", "content": "你好"},
               {"role": "assistant", "content": "示例公司换了 CEO。"}]
    result = ask(service, "那她还兼任 CFO 吗？", history)
    assert not result["sources"]
    assert "Reference DATA" not in provider.calls[-1][0]["content"]


def test_recovered_evidence_is_limited_to_company_news(service_factory):
    service, _ = service_factory(online=False)
    history = [{"role": "user", "content": "示例公司的 CEO 与 ETF"}]
    result = ask(service, "那她还兼任 CFO 吗？", history)
    assert result["sources"]
    assert all(item["category"] == "company_news" for item in result["sources"])


def test_provider_failure_returns_explicit_offline_news_extracts(service_factory):
    service, provider = service_factory(error="network_or_timeout")
    result = ask(service, "示例公司 CEO")
    assert len(provider.calls) == 1
    assert result["mode"] == "offline" and result["warning"] == "network_or_timeout"
    assert "未由大模型生成" in result["answer"] and result["sources"]
