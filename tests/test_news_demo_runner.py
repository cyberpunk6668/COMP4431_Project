"""The comparison must preserve raw evidence and never call a model by default."""
import asyncio
import json

from app.config import Settings
from app.llm import ProviderError
from app.service import COMPANY_NEWS_SYSTEM
from scripts import run_news_demo as runner


def settings_for(tmp_path, *, online=True):
    documents = []
    for doc_id in ("nvda-news", "nvda-filing"):
        documents.append({
            "id": doc_id, "title": "NVIDIA corporate event",
            "url": "https://www.sec.gov/example", "category": "company_news",
            "updated_at": "2026-11-15", "keywords": ["NVIDIA", "英伟达"],
            "text": "An original local summary with dates, roles, and boundaries.",
            "text_zh": "有日期和职位说明的本地摘要。", "text_en": "A dated local summary.",
        })
    path = tmp_path / "knowledge.json"
    path.write_text(json.dumps({"documents": documents}), encoding="utf-8")
    return Settings(api_key="private-fixture-key" if online else "", offline=not online,
                    knowledge_path=path, db_path=tmp_path / "must-not-be-created.sqlite3")


class FakeProvider:
    def __init__(self, *, error=None):
        self.error = error
        self.calls = []

    async def complete(self, messages):
        self.calls.append(messages)
        if self.error:
            raise ProviderError(self.error)
        return "Recorded answer. [nvda-news] [invented-source]"


def test_default_preflight_captures_actual_rag_prompt_without_network_or_database(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Preflight must not instantiate the API provider")

    monkeypatch.setattr(runner, "DeepSeek", forbidden)
    settings = settings_for(tmp_path)
    report = asyncio.run(runner.build_report(settings))
    assert report["mode"] == "preflight" and report["status"] == "ready"
    assert report["actual_provider_requests"] == 0 and report["results"] == []
    assert len(report["questions"]) == 3
    assert report["experiment"]["planned_provider_requests"] == 6
    for question in report["questions"]:
        baseline = question["planned_requests"]["baseline"]
        rag = question["planned_requests"]["rag"]
        assert len(baseline) == len(rag) == 2
        assert baseline[-1] == rag[-1] == {"role": "user", "content": question["prompt"]}
        assert "Reference DATA:" not in baseline[0]["content"]
        assert "Reference DATA:" in rag[0]["content"]
        assert baseline[0]["content"].startswith(runner.SYSTEM)
        assert rag[0]["content"].startswith(runner.SYSTEM)
        assert COMPANY_NEWS_SYSTEM in baseline[0]["content"]
        assert COMPANY_NEWS_SYSTEM in rag[0]["content"]
        assert baseline[0]["content"] == rag[0]["content"].split("\nReference DATA:", 1)[0]
        assert {s["id"] for s in question["retrieved_sources"]} == {"nvda-news", "nvda-filing"}
    assert "private-fixture-key" not in json.dumps(report)
    assert not settings.db_path.exists()


def test_live_preserves_raw_output_and_postprocessed_app_answer_separately(tmp_path):
    provider = FakeProvider()
    settings = settings_for(tmp_path)
    report = asyncio.run(runner.build_report(settings, live=True, repeats=2, provider=provider))
    assert report["status"] == "completed"
    assert report["actual_provider_requests"] == len(provider.calls) == 12
    assert {row["repeat"] for row in report["results"]} == {1, 2}
    assert all(len(messages) == 2 for messages in provider.calls)
    assert {row["arm"] for row in report["results"]} == {"baseline", "rag"}
    assert report["assessment"]["status"] == "manual_review_required"
    for repeat in (1, 2):
        for question_id, _ in runner.QUESTIONS:
            pair = {row["arm"]: row for row in report["results"]
                    if row["repeat"] == repeat and row["question_id"] == question_id}
            assert pair["baseline"]["messages"][0]["content"] == pair["rag"]["messages"][0]["content"].split("\nReference DATA:", 1)[0]
    for result in report["results"]:
        assert result["status"] == "generated"
        assert result["raw_answer"] == "Recorded answer. [nvda-news] [invented-source]"
        assert result["messages"][-1]["content"] == result["prompt"]
        assert result["latency_ms"] >= 0 and result["provider_latency_ms"] >= 0
        if result["arm"] == "rag":
            assert result["source_ids"] == ["nvda-news"]
            assert "[unverified citation]" in result["answer"]
        else:
            assert result["source_ids"] == []
            assert result["answer"] == result["raw_answer"]
    assert not settings.db_path.exists()


def test_provider_failure_is_explicit_and_cannot_expose_untrusted_exception_text(tmp_path):
    provider = FakeProvider(error="unexpected-private-fixture-key")
    report = asyncio.run(runner.build_report(settings_for(tmp_path), live=True, provider=provider))
    assert report["status"] == "completed_with_failures"
    assert report["actual_provider_requests"] == 6
    assert all(row["status"] == "provider_failed" for row in report["results"])
    assert all(row["provider_error"] == "provider_error" for row in report["results"])
    assert all(row["raw_answer"] is None for row in report["results"])
    assert "unexpected-private-fixture-key" not in json.dumps(report)
    assert all(row["mode"] == "offline" for row in report["results"] if row["arm"] == "rag")


def test_live_request_with_offline_configuration_is_skipped_without_calling_provider(tmp_path):
    provider = FakeProvider()
    report = asyncio.run(runner.build_report(settings_for(tmp_path, online=False), live=True, provider=provider))
    assert report["status"] == "skipped"
    assert report["actual_provider_requests"] == 0 and provider.calls == []
    assert report["results"] == []


def test_cli_writes_requested_report_without_serializing_settings(tmp_path, monkeypatch, capsys):
    settings = settings_for(tmp_path)
    monkeypatch.setattr(runner, "Settings", lambda: settings)
    output = tmp_path / "output" / "preflight.json"
    assert runner.main(["--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert report["mode"] == "preflight" and printed["report"] == str(output.resolve())
    assert "private-fixture-key" not in output.read_text(encoding="utf-8")
