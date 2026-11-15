import re

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.knowledge import KnowledgeRetriever


def test_workbench_and_showcase_are_separate(tmp_path):
    c = TestClient(create_app(Settings(api_key="", offline=True, db_path=tmp_path / "db")))
    assert c.get("/").status_code == 200
    workspace = c.get("/workspace")
    assert workspace.status_code == 200 and 'id="chat-form"' in workspace.text
    assert c.get("/app").status_code == 200


def test_showcase_metadata_uses_sources_without_credentials(tmp_path):
    c = TestClient(create_app(Settings(api_key="", offline=True, db_path=tmp_path / "db", adapter_path=tmp_path / "missing")))
    r = c.get("/api/showcase")
    data = r.json()
    expected = len(KnowledgeRetriever(Settings().knowledge_path).documents)
    assert len(data["knowledge_sources"]) == data["document_count"] == expected
    assert all(s["url"].startswith("https://") and s["snippet"] for s in data["knowledge_sources"])
    assert not data["training"]["completed"] and data["training"]["steps"] == 0
    assert "api_key" not in r.text and not re.search(r"sk-[A-Za-z0-9_-]{20,}", r.text)
    assert c.get("/api/sessions").json()["sessions"] == []
