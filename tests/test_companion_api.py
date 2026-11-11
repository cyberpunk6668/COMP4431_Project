"""Local shared conversation APIs invalidate only after persistence commits."""
import asyncio
from contextlib import contextmanager
import json
from threading import Event, Thread
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.storage import Store
from test_companion import drain
from test_options_refresh_api import setup as refresh_setup


@pytest.fixture
def setup(tmp_path):
    app = create_app(Settings(api_key="", offline=True, db_path=tmp_path / "companion.sqlite3"))
    return app, TestClient(app)


def test_connection_is_explicit_and_metadata_only_with_no_generation(setup, monkeypatch):
    app, client = setup
    async def forbidden(*args, **kwargs):
        raise AssertionError("Connecting must not invoke a model or broker")
    monkeypatch.setattr(app.state.service.provider, "complete", forbidden)
    monkeypatch.setattr(app.state.options.gateway, "snapshot", forbidden)
    sid = client.post("/api/sessions", json={}).json()["id"]
    assert client.get("/api/companion/connection").json()["session_id"] is None
    result = client.put("/api/companion/connection", json={"session_id": sid, "language": "en", "engine": "local"}).json()
    assert result["session_id"] == sid and result["generation"] == 1
    assert result["language"] == "en" and result["engine"] == "local"
    assert result["activities"] == [] and "messages" not in result
    assert client.get(f"/api/sessions/{sid}").json()["messages"] == []
    assert client.put("/api/companion/connection", json={"session_id": str(uuid4())}).status_code == 404
    assert client.get("/api/companion/connection").json()["session_id"] == sid
    assert client.put("/api/companion/connection", json={"session_id": None, "expected_generation": 0}).status_code == 409
    assert client.put("/api/companion/connection", json={"session_id": None}).json()["session_id"] is None


def test_origins_hosts_and_state_schema_are_not_loosened(setup):
    _, client = setup
    assert client.put("/api/companion/connection", json={"session_id": None}, headers={"Origin": "https://example.org"}).status_code == 403
    assert client.get("/api/companion/connection", headers={"Host": "example.org"}).status_code == 400
    assert client.get("/api/companion/events?surface=unknown").status_code == 422
    assert client.put("/api/companion/connection", json={"session_id": None, "secret": "not a supported field"}).status_code == 422
    assert client.get("/api/health").json()["application"] == "FinPilot"
    assert "connect-src 'self'" in client.get("/api/companion/connection").headers["Content-Security-Policy"]


def test_committed_turn_notifies_only_selected_session_and_never_transmits_text(setup, monkeypatch):
    app, client = setup
    sid, other = [client.post("/api/sessions", json={}).json()["id"] for _ in range(2)]
    client.put("/api/companion/connection", json={"session_id": sid})
    bus = app.state.companion
    subscriber = bus.subscribe("workspace")
    original_publish = bus._publish
    observed = []
    def inspect(kind, *args, **kwargs):
        if kind == "session.changed":
            saved = app.state.store.get(sid)
            assert len(saved["messages"]) == 2
            observed.append(saved["messages"][-1]["id"])
        return original_publish(kind, *args, **kwargs)
    monkeypatch.setattr(bus, "_publish", inspect)
    text = "解释复利 PRIVATE_QUESTION_MARKER"
    reply = client.post("/api/chat", json={"session_id": sid, "message": text}).json()
    assert reply["mode"] == "offline" and observed
    events = drain(subscriber)
    assert [e["type"] for e in events] == ["activity", "session.changed", "activity"]
    assert events[0]["payload"]["status"] == "started"
    assert events[-1]["payload"]["activities"] == []
    assert "PRIVATE_QUESTION_MARKER" not in json.dumps(events)
    client.post("/api/chat", json={"session_id": other, "message": "什么是复利？"})
    assert not drain(subscriber)


def test_activity_scope_and_real_speech_phase(setup):
    app, client = setup
    sid = client.post("/api/sessions", json={}).json()["id"]
    connection = client.put("/api/companion/connection", json={"session_id": sid}).json()
    body = {"operation_id": "read-latest", "kind": "speech", "phase": "speaking", "status": "started", "session_id": sid, "generation": connection["generation"]}
    assert client.post("/api/companion/activity", json=body).json()["activities"][0]["phase"] == "speaking"
    assert client.post("/api/companion/activity", json={**body, "generation": 0}).status_code == 409
    assert client.post("/api/companion/activity", json={**body, "session_id": str(uuid4())}).status_code == 409
    assert client.post("/api/companion/activity", json={**body, "kind": "chat"}).status_code == 422
    assert client.post("/api/companion/activity", json={**body, "status": "completed"}).json()["activities"] == []


def test_delete_linked_session_clears_binding_after_committed_delete(setup):
    app, client = setup
    sid = client.post("/api/sessions", json={}).json()["id"]
    client.put("/api/companion/connection", json={"session_id": sid})
    subscriber = app.state.companion.subscribe("workspace")
    assert client.delete(f"/api/sessions/{sid}").status_code == 200
    assert app.state.store.get(sid) is None
    assert client.get("/api/companion/connection").json()["session_id"] is None
    assert [e["type"] for e in drain(subscriber)] == ["session.deleted", "connection.changed"]


def test_refresh_announces_committed_analysis_before_model_and_turn_after_model(refresh_setup, monkeypatch):
    client, app, _, old, sid, _ = refresh_setup
    bus = app.state.companion
    bus.connect(sid)
    subscriber = bus.subscribe("workspace")
    original = app.state.options_chat.answer
    seen = []
    async def explain(*args):
        current = app.state.store.get(sid)["active_analysis_id"]
        assert current != old["analysis_id"]
        queued = list(subscriber.queue._queue)
        assert any(e["type"] == "analysis.changed" and e["payload"]["analysis_id"] == current for e in queued)
        assert app.state.store.get(sid)["messages"] == []
        seen.append(current)
        return await original(*args)
    monkeypatch.setattr(app.state.options_chat, "answer", explain)
    result = client.post(f"/api/sessions/{sid}/analysis/refresh", json={"analysis_id": old["analysis_id"]})
    assert result.status_code == 200 and seen
    events = drain(subscriber)
    assert [e["type"] for e in events] == ["activity", "analysis.changed", "session.changed", "activity"]
    assert events[-1]["payload"]["activities"] == []
    assert len(app.state.store.get(sid)["messages"]) == 2
    assert app.state.store.get_analysis(old["analysis_id"]) is not None


def test_shared_followup_inherits_new_binding_instead_of_stale_page_analysis(refresh_setup):
    client, app, _, old, sid, calls = refresh_setup
    client.put("/api/companion/connection", json={"session_id": sid})
    updated = client.post(f"/api/sessions/{sid}/analysis/refresh", json={"analysis_id": old["analysis_id"]}).json()
    new_id = updated["active_analysis"]["analysis_id"]
    response = client.post("/api/chat", json={"session_id": sid, "message": "解释当前报告"}).json()
    assert response["active_analysis"]["analysis_id"] == new_id
    assert calls[-1]["analysis"]["analysis_id"] == new_id
    assert app.state.store.get(sid)["messages"][1]["analysis_context"]["analysis_id"] == new_id


def test_connection_switch_during_pending_model_does_not_leak_completion(tmp_path):
    async def scenario():
        app = create_app(Settings(api_key="", offline=True, db_path=tmp_path / "pending.sqlite3"))
        first, second = app.state.store.create()["id"], app.state.store.create()["id"]
        bus = app.state.companion
        bus.connect(first)
        began, release = asyncio.Event(), asyncio.Event()
        async def answer(*args):
            began.set()
            await release.wait()
            return {"answer": "Saved private answer", "mode": "offline", "sources": []}
        app.state.service.answer = answer
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            running = asyncio.create_task(client.post("/api/chat", json={"session_id": first, "message": "Explain compounding"}))
            await asyncio.wait_for(began.wait(), 1)
            changed = await asyncio.wait_for(client.put("/api/companion/connection", json={"session_id": second}), 1)
            assert changed.status_code == 200
            observer = bus.subscribe("workspace")
            release.set()
            assert (await running).status_code == 200
            assert not drain(observer)
            assert len(app.state.store.get(first)["messages"]) == 2
            assert app.state.store.get(second)["messages"] == []
    asyncio.run(scenario())


def test_sse_reset_framing_and_disconnect_releases_presence(setup):
    app, _ = setup
    endpoint = next(r.endpoint for r in app.routes if getattr(r, "path", None) == "/api/companion/events")
    class Request:
        disconnected = False
        async def is_disconnected(self):
            return self.disconnected
    async def scenario():
        request = Request()
        response = await endpoint(request, surface="desktop")
        assert response.media_type == "text/event-stream"
        assert response.headers["X-Accel-Buffering"] == "no"
        chunk = await anext(response.body_iterator)
        payload = json.loads(chunk.split("data: ", 1)[1])
        assert payload["type"] == "reset" and payload["payload"]["connection"]["desktop_connected"]
        request.disconnected = True
        with pytest.raises(StopAsyncIteration):
            await anext(response.body_iterator)
        assert not app.state.companion.connection()["desktop_connected"]
    asyncio.run(scenario())


def test_store_get_header_and_messages_share_a_read_snapshot(tmp_path, monkeypatch):
    store = Store(tmp_path / "coherent.sqlite3")
    sid = store.create()["id"]
    reply = {"answer": "Old answer", "mode": "offline", "sources": []}
    store.append_turn(sid, "Old question", reply)
    with store.connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
    original = store.connect
    reading_messages, committed = Event(), Event()
    def trace(statement):
        if statement.startswith("SELECT * FROM messages WHERE") and not reading_messages.is_set():
            reading_messages.set()
            assert committed.wait(3)
    @contextmanager
    def traced():
        with original() as db:
            db.set_trace_callback(trace)
            yield db
    monkeypatch.setattr(store, "connect", traced)
    def writer():
        assert reading_messages.wait(3)
        store.append_turn(sid, "New question", {**reply, "answer": "New answer"})
        committed.set()
    thread = Thread(target=writer)
    thread.start()
    before = store.get(sid)
    thread.join(3)
    assert not thread.is_alive() and committed.is_set()
    assert len(before["messages"]) == 2
    after = store.get(sid)
    assert len(after["messages"]) == 4
