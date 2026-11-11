from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.llm import ProviderError
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(api_key="", offline=True, db_path=tmp_path / "test.sqlite3")))


def test_chat_persistence_export_delete(client):
    result = client.post("/api/chat", json={"message": "什么是复利？"}).json()
    assert result["mode"] == "offline"
    assert result["sources"]
    sid = result["session_id"]
    messages = client.get(f"/api/sessions/{sid}").json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["warning"] == "offline_requested"
    assert client.get(f"/api/sessions/{sid}/export").json()["messages"] == messages
    assert client.delete(f"/api/sessions/{sid}").status_code == 200
    assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_input_and_session_validation(client):
    for message in ["", "  ", "x" * 3001]:
        assert client.post("/api/chat", json={"message": message}).status_code == 422
    assert client.post("/api/chat", json={"message": "ETF", "language": "fr"}).status_code == 422
    assert client.post("/api/chat", json={"message": "ETF", "session_id": "missing"}).status_code == 404
    assert client.post("/api/calculate", json={"kind": "loan"}).status_code == 422


def test_credentials_not_persisted(client):
    assert client.post("/api/chat", json={"message": "sk-" + "x" * 32}).status_code == 422
    assert client.get("/api/sessions").json() == {"sessions": []}


def test_cross_origin_and_host_rejected(client):
    assert client.post("/api/chat", json={"message": "ETF"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400


def test_live_data_and_advice_boundary(client):
    for question, warning in [("今天苹果的股价是多少", "no_live_data"), ("which stock should I buy", "education_boundary")]:
        result = client.post("/api/chat", json={"message": question}).json()
        assert result["warning"] == warning and result["sources"] == []


def test_calculator_chat_bypasses_llm(client):
    data = client.post("/api/chat", json={"message": "loan principal=1200 annual_rate=0 years=1"}).json()
    assert data["mode"] == "calculator"
    assert data["calculation"]["values"]["monthly_payment"] == "100.00"


def test_health_has_no_secret_and_reports_config_only(client):
    response = client.get("/api/health")
    assert response.json()["provider_verified"] is False
    assert "api_key" not in response.text
    assert response.headers["Cache-Control"] == "no-store"


def test_requested_offline_language_overrides_query_script(client):
    data = client.post("/api/chat", json={"message": "复利是什么", "language": "en"}).json()
    assert data["mode"] == "offline"
    assert "Compound interest" in data["answer"] or "compound interest" in data["answer"]


def test_tiny_decimal_http_validation(client):
    assert client.post("/api/calculate", json={"kind": "loan", "principal": 1200, "annual_rate": "1e-100", "years": 1}).status_code == 422


def test_local_api_reference_and_schema(client):
    assert client.get("/docs").status_code == 200
    assert "cdn" not in client.get("/docs").text
    assert "/api/chat" in client.get("/openapi.json").json()["paths"]


def test_provider_failure_is_transparent(tmp_path):
    app = create_app(Settings(api_key="test-only", offline=False, db_path=tmp_path / "db.sqlite3"))
    async def fail(messages):
        raise ProviderError("authentication_failed")
    app.state.service.provider.complete = fail
    result = TestClient(app).post("/api/chat", json={"message": "Explain diversification", "language": "en"}).json()
    assert result["mode"] == "offline" and result["warning"] == "authentication_failed"
    assert "Offline reference extracts" in result["answer"]


def test_provider_success_includes_history_and_evidence(tmp_path):
    app = create_app(Settings(api_key="test-only", offline=False, db_path=tmp_path / "db.sqlite3"))
    calls = []
    async def answer(messages):
        calls.append(messages)
        return "Diversification spreads risk."
    app.state.service.provider.complete = answer
    client = TestClient(app)
    first = client.post("/api/chat", json={"message": "Explain diversification", "language": "en"}).json()
    second = client.post("/api/chat", json={"message": "Tell me more about diversification", "session_id": first["session_id"], "language": "en"}).json()
    assert second["mode"] == "deepseek"
    assert len(calls[1]) == 4
    assert "Reference DATA" in calls[1][0]["content"]


def test_rate_limit(client):
    for _ in range(20):
        assert client.post("/api/chat", json={"message": "hello"}).status_code == 200
    assert client.post("/api/chat", json={"message": "hello"}).status_code == 429
