"""Reviewed news imports preserve raw provenance and validate every source first."""
import hashlib
import json
import sqlite3
from datetime import datetime

import httpx
import pytest

from scripts import import_news_demo


@pytest.fixture
def news_import(tmp_path, monkeypatch):
    legacy = {"id": "legacy-topic", "title": "Existing reviewed knowledge", "text": "Keep this text."}
    documents = []
    downloads = {}
    calls = []
    for suffix in ("release", "8k"):
        url = "https://example.test/" + suffix
        documents.append({
            "id": "news-" + suffix, "title": "Reviewed " + suffix, "url": url,
            "publisher": "Example official publisher", "category": "company_news",
            "published_at": "2026-11-12", "event_date": "2026-11-11", "updated_at": "2026-11-15",
            "keywords": ["example leadership"], "text_zh": "已审阅的中文摘要。",
            "text_en": "A reviewed English summary.", "review_checks": ["confirmed " + suffix, "interim CEO"],
        })
        body = ("<html><head><style>HIDDEN STYLE</style></head><body>"
                "<script>HIDDEN SCRIPT</script><p>Confirmed " + suffix + "</p>"
                "<p>An interim CEO was appointed.</p><p>中文资料。</p></body></html>").encode("utf-8")
        downloads[url] = {"status": 200, "content_type": "text/html; charset=utf-8", "body": body}

    manifest = {"reviewed_at": "2026-11-15", "documents": documents}
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    knowledge_path = tmp_path / "knowledge.json"
    knowledge_path.write_text(json.dumps({
        "schema_version": 1, "reviewed_at": "2026-11-10", "documents": [legacy],
    }), encoding="utf-8")
    paths = {"manifest_path": manifest_path, "knowledge_path": knowledge_path,
             "db_path": tmp_path / "db" / "news.sqlite3", "archive_path": tmp_path / "archive",
             "report_path": tmp_path / "reports" / "import.json"}
    real_client = httpx.Client

    def handle(request):
        url = str(request.url)
        calls.append(url)
        download = downloads[url]
        return httpx.Response(download["status"], headers={"content-type": download["content_type"]},
                              content=download["body"], request=request)

    def mocked_client(**kwargs):
        return real_client(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(import_news_demo.httpx, "Client", mocked_client)
    return {"paths": paths, "documents": documents, "legacy": legacy, "downloads": downloads, "calls": calls}


def run_import(fixture):
    return import_news_demo.import_sources(**fixture["paths"])


def read_rows(path):
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute("SELECT * FROM news_source_snapshots ORDER BY id, raw_sha256")]


def test_two_sources_retain_matching_sqlite_html_hash_and_reviewed_export(news_import):
    result = run_import(news_import)
    paths = news_import["paths"]
    rows = read_rows(paths["db_path"])
    knowledge = json.loads(paths["knowledge_path"].read_text(encoding="utf-8"))
    exports = {doc["id"]: doc for doc in knowledge["documents"]}
    assert len(rows) == 2 and result["document_count"] == 3
    assert news_import["calls"] == [doc["url"] for doc in news_import["documents"]]
    assert knowledge["documents"][0] == news_import["legacy"]
    assert knowledge["reviewed_at"] == "2026-11-10" and knowledge["company_news_reviewed_at"] == "2026-11-15"
    for row in rows:
        raw = news_import["downloads"][row["url"]]["body"]
        digest = hashlib.sha256(raw).hexdigest()
        assert row["raw_html"] == raw and row["raw_sha256"] == digest
        name = row["id"] + "-" + digest[:12]
        assert (paths["archive_path"] / (name + ".html")).read_bytes() == raw
        assert (paths["archive_path"] / (name + ".txt")).read_text(encoding="utf-8") == row["extracted_text"]
        assert "HIDDEN" not in row["extracted_text"] and "中文资料" in row["extracted_text"]
        assert row["event_date"] == "2026-11-11" and row["published_at"] == "2026-11-12"
        assert row["reviewed_at"] == "2026-11-15"
        assert datetime.fromisoformat(row["fetched_at"]).utcoffset().total_seconds() == 0
        exported = exports[row["id"]]
        assert json.loads(row["reviewed_document"]) == exported
        assert exported["raw_sha256"] == digest and "review_checks" not in exported
        assert exported["text"] == exported["text_zh"] + "\n" + exported["text_en"]
        assert next(source for source in result["sources"] if source["id"] == row["id"])["raw_sha256"] == digest
    assert json.loads(paths["report_path"].read_text(encoding="utf-8")) == result


def test_reimport_does_not_duplicate_sources_or_replace_other_knowledge(news_import):
    run_import(news_import)
    paths = news_import["paths"]
    first_rows = read_rows(paths["db_path"])
    knowledge = json.loads(paths["knowledge_path"].read_text(encoding="utf-8"))
    additional = {"id": "another-topic", "text": "Unrelated knowledge added after initial import."}
    knowledge["documents"].append(additional)
    paths["knowledge_path"].write_text(json.dumps(knowledge, ensure_ascii=False), encoding="utf-8")
    result = run_import(news_import)
    final = json.loads(paths["knowledge_path"].read_text(encoding="utf-8"))
    assert read_rows(paths["db_path"]) == first_rows
    assert result["document_count"] == 4
    assert [doc["id"] for doc in final["documents"]] == ["legacy-topic", "news-release", "news-8k", "another-topic"]
    assert final["documents"][0] == news_import["legacy"] and final["documents"][-1] == additional
    assert len(list(paths["archive_path"].glob("*.html"))) == 2
    assert len(list(paths["archive_path"].glob("*.txt"))) == 2


@pytest.mark.parametrize("existing_import", [False, True])
def test_incomplete_second_source_fails_before_database_or_knowledge_mutation(news_import, existing_import):
    paths = news_import["paths"]
    if existing_import:
        run_import(news_import)
    prior_knowledge = paths["knowledge_path"].read_bytes()
    prior_rows = read_rows(paths["db_path"]) if existing_import else None
    prior_report = paths["report_path"].read_bytes() if existing_import else None
    prior_archives = {path.name: path.read_bytes() for path in paths["archive_path"].glob("*")} if existing_import else {}
    second_url = news_import["documents"][1]["url"]
    news_import["downloads"][second_url]["body"] = b"<html><body>Incomplete page without reviewed anchors.</body></html>"
    with pytest.raises(ValueError, match="Source changed or incomplete for news-8k"):
        run_import(news_import)
    assert paths["knowledge_path"].read_bytes() == prior_knowledge
    if existing_import:
        assert read_rows(paths["db_path"]) == prior_rows
        assert paths["report_path"].read_bytes() == prior_report
        assert {path.name: path.read_bytes() for path in paths["archive_path"].glob("*")} == prior_archives
    else:
        assert not paths["db_path"].exists() and not paths["archive_path"].exists()
        assert not paths["report_path"].exists()


@pytest.mark.parametrize("status,content_type,error", [
    (503, "text/html", httpx.HTTPStatusError), (200, "application/json", ValueError),
])
def test_unavailable_or_non_html_second_source_does_not_partially_import(news_import, status, content_type, error):
    paths = news_import["paths"]
    before = paths["knowledge_path"].read_bytes()
    download = news_import["downloads"][news_import["documents"][1]["url"]]
    download.update(status=status, content_type=content_type)
    with pytest.raises(error):
        run_import(news_import)
    assert paths["knowledge_path"].read_bytes() == before
    assert not paths["db_path"].exists() and not paths["archive_path"].exists()


def test_anchors_in_scripts_do_not_validate_missing_source_content(news_import):
    paths = news_import["paths"]
    second_url = news_import["documents"][1]["url"]
    news_import["downloads"][second_url]["body"] = (
        b"<html><body>Missing article<script>confirmed 8k; interim CEO</script></body></html>"
    )
    with pytest.raises(ValueError, match="Source changed or incomplete"):
        run_import(news_import)
    assert not paths["db_path"].exists()
