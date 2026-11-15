"""Replay is reachable in the actual app, without touching its broker or chats."""
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class ForbiddenGateway:
    async def snapshot(self, *args, **kwargs):
        raise AssertionError("The replay must not collect broker data")

    async def status(self):
        raise AssertionError("The replay must not even probe the broker")


def make_client(tmp_path):
    app = create_app(Settings(api_key="", offline=True, db_path=tmp_path / "demo.sqlite3"),
                     options_provider=ForbiddenGateway())

    async def forbidden(*args, **kwargs):
        raise AssertionError("Offline replay must not call a provider")

    app.state.options.llm.complete = forbidden
    return TestClient(app)


def test_actual_app_serves_replay_and_preserves_existing_sessions(tmp_path):
    with make_client(tmp_path) as client:
        session = client.post("/api/sessions", json={"title": "Keep my chat"}).json()
        before = client.get("/api/sessions").json()
        page = client.get("/options-demo")
        assert page.status_code == 200
        assert "options-demo.js" in page.text
        assert "script-src 'self'" in page.headers["content-security-policy"]
        catalogue = client.get("/api/options-demo/scenario")
        assert catalogue.status_code == 200
        assert catalogue.headers["cache-control"] == "no-store"
        for frame in (0, 1, 0):
            response = client.post("/api/options-demo/run", json={"frame": frame})
            assert response.status_code == 200
            result = response.json()
            assert result["frame"] == frame
            assert result["provenance"]["source_kind"] == "synthetic_replay"
            assert result["provenance"]["gateway_connected"] is False
            assert result["provenance"]["model_called"] is False
        assert client.get("/api/sessions").json() == before
        assert client.get(f"/api/sessions/{session['id']}").json()["messages"] == []


def test_replay_respects_app_cross_origin_security_and_input_limits(tmp_path):
    with make_client(tmp_path) as client:
        path = "/api/options-demo/run"
        assert client.post(path, json={"frame": 0}, headers={"Origin": "https://example.com"}).status_code == 403
        assert client.post(path, json={"frame": 2}).status_code == 422
        assert client.post(path, json={"engine": "untrusted"}).status_code == 422
        assert client.post(path, json={"question": "x" * 1001}).status_code == 422
        # A page reload or catalogue read must never start analysis automatically.
        for asset in ("options-demo.js", "options-demo.css"):
            assert client.get(f"/static/{asset}").status_code == 200
