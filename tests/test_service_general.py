"""General questions reach the chosen model without weakening finance evidence."""
import asyncio

import pytest

from app.config import Settings
from app.knowledge import KnowledgeRetriever
from app.llm import ProviderError
from app.service import ChatService


class RecordingProvider:
    def __init__(self, answer="A helpful answer.", error=None):
        self.answer = answer
        self.error = error
        self.calls = []

    async def complete(self, messages):
        self.calls.append(messages)
        if self.error:
            raise ProviderError(self.error)
        return self.answer


class LocalProvider(RecordingProvider):
    def __init__(self, *args, available=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.available = available

    def status(self):
        return {"available": self.available}


def setup_service(*, online=True, answer="A helpful answer.", error=None, local=None):
    settings = Settings(api_key="test-only" if online else "", offline=not online)
    provider = RecordingProvider(answer, error)
    return ChatService(KnowledgeRetriever(settings.knowledge_path), provider, settings, local), provider


def answer(service, message, history=None, language="en", engine="deepseek"):
    return asyncio.run(service.answer(message, history or [], language, engine))


@pytest.mark.parametrize("question", [
    "Explain why the sky is blue.", "Help me write a friendly birthday message.",
    "What is the difference between a Python list and a tuple?", "解释一下光合作用。",
])
def test_general_questions_call_model_without_financial_sources(question):
    service, provider = setup_service()
    result = answer(service, question)
    assert result["mode"] == "deepseek"
    assert result["sources"] == [] and "warning" not in result
    assert len(provider.calls) == 1
    instructions = provider.calls[0][0]["content"]
    assert "Do not refuse a question because it is outside finance" in instructions
    assert "Reference DATA" not in instructions


@pytest.mark.parametrize("question", [
    "Should I buy a laptop for programming?", "Should I sell my old phone?",
    "Explain what insider trading is.", "洗钱是什么，为什么违法？",
    "Explain the current rate of change in calculus.",
    "为什么现在利率上升会让债券价格下降？",
])
def test_benign_advice_definitions_and_conceptual_rates_are_not_preemptively_blocked(question):
    service, provider = setup_service()
    result = answer(service, question)
    assert result["mode"] == "deepseek"
    assert len(provider.calls) == 1
    assert "warning" not in result


def test_standalone_general_question_after_finance_does_not_borrow_old_context():
    service, provider = setup_service()
    history = [{"role": "user", "content": "Explain compound interest."},
               {"role": "assistant", "content": "Compounding earns interest on interest."}]
    for question in ("Write a poem about the moon.", "Tell me more about photosynthesis.", "详细介绍太阳系。"):
        result = answer(service, question, history)
        assert result["sources"] == []
        assert "Reference DATA" not in provider.calls[-1][0]["content"]
        assert provider.calls[-1][-1] == {"role": "user", "content": question}


def test_actual_short_followup_keeps_relevant_finance_context():
    service, provider = setup_service(answer="Interest can earn interest. [compound-interest]")
    result = answer(service, "Can you explain that?", [{"role": "user", "content": "Explain compound interest."}])
    assert result["sources"][0]["id"] == "compound-interest"
    assert "Reference DATA" in provider.calls[-1][0]["content"]


def test_financial_answers_keep_primary_references_and_unknown_ids_are_not_links():
    service, provider = setup_service(answer="Diversification reduces concentration risk. [diversification] [made-up]")
    result = answer(service, "Explain diversification.")
    assert result["mode"] == "deepseek"
    assert [item["id"] for item in result["sources"]] == ["diversification"]
    assert "[unverified citation]" in result["answer"]
    assert "Reference DATA" in provider.calls[0][0]["content"]


def test_ordinary_programming_answer_keeps_array_index_not_a_citation():
    service, _ = setup_service(answer="Use `values[i]` to access the item at index i.")
    result = answer(service, "How do I access an item in a Python list?")
    assert result["answer"] == "Use `values[i]` to access the item at index i."
    assert result["sources"] == []


@pytest.mark.parametrize("question,warning", [
    ("今天苹果的股价是多少？", "no_live_data"),
    ("What is the current stock price?", "no_live_data"),
    ("Which stock should I buy?", "education_boundary"),
    ("Should I buy this ETF?", "education_boundary"),
])
def test_specific_live_quotes_and_personal_trade_requests_remain_explicit(question, warning):
    service, provider = setup_service()
    result = answer(service, question)
    assert result["warning"] == warning and result["sources"] == []
    assert not provider.calls


def test_offline_general_and_provider_failure_are_transparent():
    for service, provider, expected in (
        (*setup_service(online=False), "offline_requested"),
        (*setup_service(error="network_or_timeout"), "network_or_timeout"),
    ):
        result = answer(service, "Explain photosynthesis.")
        assert result["mode"] == "offline" and result["warning"] == expected
        assert result["sources"] == []
        assert "unavailable" in result["answer"]
    greeting = answer(setup_service(online=False)[0], "你好！", language="zh")
    assert greeting["answer"].startswith("你好") and greeting["mode"] == "offline"


def test_general_question_honors_selected_local_model_and_language():
    local = LocalProvider(answer="水在常压下受热会蒸发。")
    service, cloud = setup_service(local=local)
    result = answer(service, "解释一下蒸发。", language="zh", engine="local")
    assert result["mode"] == "local-lora" and result["sources"] == []
    assert "Requested language: zh" in local.calls[0][0]["content"]
    assert not cloud.calls


def test_unavailable_local_does_not_silently_switch_to_cloud():
    service, cloud = setup_service(local=LocalProvider(available=False))
    result = answer(service, "Explain photosynthesis.", engine="local")
    assert result["warning"] == "local_model_unavailable"
    assert result["mode"] == "offline" and not cloud.calls


def test_sensitive_key_is_neither_forwarded_nor_generated():
    service, provider = setup_service()
    result = answer(service, "Please use sk-" + "x" * 32)
    assert result["warning"] == "sensitive_input" and not provider.calls
