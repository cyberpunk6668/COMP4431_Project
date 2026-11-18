"""Malformed browser headers must be rejected without crashing mutations."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.mark.parametrize("origin", ["http://[invalid", "http://[127.0.0.1]", "null", "https://testserver"])
def test_invalid_origin_rejected_without_mutation(tmp_path, origin):
    app = create_app(Settings(api_key="", offline=True, db_path=tmp_path / "security.sqlite3"))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/sessions", json={"title": "Must not be saved"}, headers={"Origin": origin})
        assert response.status_code == 403
        assert client.get("/api/sessions").json() == {"sessions": []}


def test_matching_browser_origin_can_create_session(tmp_path):
    app = create_app(Settings(api_key="", offline=True, db_path=tmp_path / "security.sqlite3"))
    with TestClient(app) as client:
        response = client.post("/api/sessions", json={"title": "Allowed"}, headers={"Origin": "http://testserver"})
        assert response.status_code == 201
