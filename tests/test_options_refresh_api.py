"""Refreshing preserves previous snapshots, bindings, messages and request scope."""
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app
from app.options_chat import describe_analysis
from app.options_ibkr import IBKROptionsError
from test_options_workflow import make_snapshot


class RefreshGateway:
    def __init__(self):
        self.calls = []
        self.failure = None

    async def snapshot(self, symbol, expiry, strike_count, market_data_type):
        self.calls.append((symbol, expiry, strike_count, market_data_type))
        if self.failure:
            raise IBKROptionsError(self.failure, "Controlled collection failure")
        data = make_snapshot(3)
        data.update(symbol=symbol, trading_class=symbol, multiplier=100, exchange="SMART", requested_market_data_type=3)
        stamp = (datetime.now(UTC) - timedelta(seconds=20 if len(self.calls) == 1 else 1)).isoformat()
        data["started_at"] = data["received_at"] = stamp
        data["underlying"]["received_at"] = stamp
        if expiry:
            data["expiration"] = expiry
        for row in data["quotes"]:
            row["expiration"] = data["expiration"]
            row["volume"] = (10 if row["right"] == "C" else 15) if len(self.calls) == 1 else (15 if row["right"] == "C" else 35)
            for field in ("received_at", "quote_received_at", "volume_received_at", "open_interest_received_at"):
                row[field] = stamp
        return data


@pytest.fixture
def setup(tmp_path):
    gateway = RefreshGateway()
    app = create_app(Settings(api_key="", offline=True, db_path=tmp_path / "refresh.sqlite3"), options_provider=gateway)
    client = TestClient(app)
    report = client.post("/api/options/analyze", json={"symbol": "TEST", "radius": 1, "market_data_type": 3}).json()
    sid = client.post("/api/sessions", json={"title": "Refresh acceptance"}).json()["id"]
    assert client.put(f"/api/sessions/{sid}/analysis", json={"analysis_id": report["analysis_id"]}).status_code == 200
    calls = []

    async def explain(message, history, language, engine, analysis):
        calls.append({"analysis": analysis, "engine": engine, "message": message})
        return {"answer": "新样本的数据结构发生了变化，请核对两次接收时间。", "mode": "offline", "sources": [],
                "analysis_context": {**describe_analysis(analysis, language), "evidence_ids": [], "evidence": []}}

    app.state.options_chat.answer = explain
    return client, app, gateway, report, sid, calls


def refresh(client, sid, analysis_id, **kwargs):
    return client.post(f"/api/sessions/{sid}/analysis/refresh", json={"analysis_id": analysis_id, **kwargs})


def test_refresh_captures_same_expiry_and_keeps_both_immutable_reports(setup):
    client, _, gateway, previous, sid, calls = setup
    first = client.post("/api/chat", json={"message": "解释这批数据", "session_id": sid}).json()
    result = refresh(client, sid, previous["analysis_id"], language="zh", engine="local")
    assert result.status_code == 200
    data = result.json()
    new_id = data["active_analysis"]["analysis_id"]
    assert new_id != previous["analysis_id"] and data["refreshed"] is True
    assert gateway.calls[-1] == ("TEST", previous["snapshot"]["expiration"], 3, 3)
    assert len(gateway.calls) == 2 and calls[-1]["engine"] == "local"
    current = client.get("/api/options/analyses/" + new_id).json()
    assert current["previous_analysis_id"] == previous["analysis_id"]
    assert current["refresh_comparison"]["previous_analysis_id"] == previous["analysis_id"]
    assert client.get("/api/options/analyses/" + previous["analysis_id"]).json() == previous
    saved = client.get("/api/sessions/" + sid).json()
    assert saved["active_analysis_id"] == new_id
    assert [item["analysis_id"] for item in saved["analysis_history"]] == [new_id, previous["analysis_id"]]
    assert saved["analysis_history"][0]["is_current"] and not saved["analysis_history"][1]["is_current"]
    assert saved["messages"][1]["analysis_context"] == first["analysis_context"]
    assert saved["messages"][-2]["content"] == data["user_message"]
    assert saved["messages"][-1]["analysis_context"]["analysis_id"] == new_id
    exported = client.get(f"/api/sessions/{sid}/export").json()
    assert exported["analysis_history"] == saved["analysis_history"]


def test_collection_failure_preserves_current_binding_history_and_messages(setup):
    client, _, gateway, previous, sid, calls = setup
    gateway.failure = "ibkr_expiration_unavailable"
    before = client.get("/api/sessions/" + sid).json()
    response = refresh(client, sid, previous["analysis_id"])
    assert response.status_code == 404
    after = client.get("/api/sessions/" + sid).json()
    assert after["active_analysis_id"] == before["active_analysis_id"]
    assert after["analysis_history"] == before["analysis_history"] and after["messages"] == []
    assert not calls


def test_stale_expected_id_never_triggers_collection(setup):
    client, _, gateway, previous, sid, _ = setup
    for stale_id in (str(uuid4()),):
        response = refresh(client, sid, stale_id)
        assert response.status_code == 409 and response.json()["detail"]["code"] == "analysis_refresh_conflict"
    assert len(gateway.calls) == 1
    assert client.get(f"/api/sessions/{sid}").json()["active_analysis_id"] == previous["analysis_id"]


def test_duplicate_stale_refresh_cannot_create_a_third_snapshot(setup):
    client, _, gateway, previous, sid, _ = setup
    assert refresh(client, sid, previous["analysis_id"]).status_code == 200
    assert refresh(client, sid, previous["analysis_id"]).status_code == 409
    assert len(gateway.calls) == 2
    assert len(client.get(f"/api/sessions/{sid}").json()["analysis_history"]) == 2


def test_unexpected_explanation_failure_still_exposes_saved_new_data(setup):
    client, app, _, previous, sid, _ = setup

    async def unavailable(*args):
        raise RuntimeError("Controlled model-side failure")

    app.state.options_chat.answer = unavailable
    result = refresh(client, sid, previous["analysis_id"]).json()
    assert result["refreshed"] and result["mode"] == "offline"
    assert result["warning"] == "options_answer_unavailable"
    assert result["analysis_context"]["analysis_id"] != previous["analysis_id"]
    assert result["active_analysis"]["analysis_id"] == result["analysis_context"]["analysis_id"]
    assert len(result["analysis_history"]) == 2


def test_detached_analysis_cannot_be_refreshed_and_history_remains(setup):
    client, _, gateway, previous, sid, _ = setup
    client.put(f"/api/sessions/{sid}/analysis", json={"analysis_id": None})
    assert refresh(client, sid, previous["analysis_id"]).status_code == 409
    saved = client.get(f"/api/sessions/{sid}").json()
    assert saved["active_analysis"] is None and len(saved["analysis_history"]) == 1
    assert not saved["analysis_history"][0]["is_current"] and len(gateway.calls) == 1


def test_bad_request_or_cross_origin_does_not_collect(setup):
    client, _, gateway, previous, sid, _ = setup
    path = f"/api/sessions/{sid}/analysis/refresh"
    for body in ({"analysis_id": "wrong"}, {"analysis_id": previous["analysis_id"], "radius": 6},
                 {"analysis_id": previous["analysis_id"], "engine": "unknown"}):
        assert client.post(path, json=body).status_code == 422
    assert client.post(path, json={"analysis_id": previous["analysis_id"]}, headers={"Origin": "https://external.example"}).status_code == 403
    assert len(gateway.calls) == 1


def test_history_survives_unbinding_and_process_reinitialization(setup):
    client, app, _, previous, sid, _ = setup
    data = refresh(client, sid, previous["analysis_id"]).json()
    expected_ids = [item["analysis_id"] for item in data["analysis_history"]]
    client.put(f"/api/sessions/{sid}/analysis", json={"analysis_id": None})
    another = create_app(Settings(api_key="", offline=True, db_path=app.state.store.path), options_provider=RefreshGateway())
    restored = TestClient(another).get(f"/api/sessions/{sid}").json()
    assert restored["active_analysis_id"] is None
    assert [item["analysis_id"] for item in restored["analysis_history"]] == expected_ids
    assert restored["messages"][-1]["analysis_context"]["analysis_id"] == expected_ids[0]


def test_refresh_rate_limit_uses_a_shared_route_key(setup):
    client, _, gateway, _, sid, _ = setup
    for _ in range(6):
        assert refresh(client, sid, str(uuid4())).status_code == 409
    assert refresh(client, sid, str(uuid4())).status_code == 429
    assert len(gateway.calls) == 1


def test_in_flight_duplicate_refresh_is_rejected_before_second_collection(setup):
    client, _, gateway, previous, sid, _ = setup
    entered, release = Event(), Event()
    original = gateway.snapshot

    async def held(*args):
        entered.set()
        await asyncio.to_thread(release.wait, 5)
        return await original(*args)

    gateway.snapshot = held
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(refresh, client, sid, previous["analysis_id"])
        try:
            assert entered.wait(3)
            duplicate = refresh(client, sid, previous["analysis_id"])
            assert duplicate.status_code == 409 and duplicate.json()["detail"]["code"] == "analysis_refresh_busy"
        finally:
            release.set()
        assert pending.result(timeout=10).status_code == 200
    assert len(gateway.calls) == 2


def test_all_failed_batch_refresh_keeps_previous_successful_scope(setup):
    client, _, gateway, _, sid, calls = setup
    batch = client.post("/api/options/batch", json={"items": [{"symbol": "TEST"}, {"symbol": "OTHER"}],
                                                  "radius": 1, "market_data_type": 3}).json()
    client.put(f"/api/sessions/{sid}/analysis", json={"analysis_id": batch["analysis_id"]})
    before = client.get(f"/api/sessions/{sid}").json()
    gateway.failure = "ibkr_entitlement_missing"
    result = refresh(client, sid, batch["analysis_id"])
    assert result.status_code == 424 and result.json()["detail"]["code"] == "ibkr_refresh_empty"
    after = client.get(f"/api/sessions/{sid}").json()
    assert after["active_analysis_id"] == batch["analysis_id"]
    assert after["analysis_history"] == before["analysis_history"]
    assert not after["messages"] and not calls
