"""Saved server snapshots, session isolation and context-aware chat routing."""
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app
from app.options_chat import describe_analysis
from test_options_workflow import FixtureGateway


@pytest.fixture
def workflow(tmp_path):
    gateway = FixtureGateway(mode=3)
    app = create_app(Settings(api_key="", offline=True, db_path=tmp_path / "workflow.sqlite3"), options_provider=gateway)
    calls = []

    async def answer(message, history, language, engine, analysis):
        calls.append({"message": message, "analysis": analysis, "engine": engine, "history": history})
        return {"answer": "这份样本只能描述所选合约的活动，不能确定未来涨跌。", "sources": [],
                "mode": "offline", "analysis_context": {**describe_analysis(analysis, language), "evidence": [], "evidence_ids": []}}

    app.state.options_chat.answer = answer
    return TestClient(app), app, gateway, calls


def capture(client):
    response = client.post("/api/options/analyze", json={"symbol": "TEST", "radius": 1})
    assert response.status_code == 200
    return response.json()


def test_snapshot_registered_and_round_trips_without_quote_refresh(workflow):
    client, _, gateway, _ = workflow
    report = capture(client)
    UUID(report["analysis_id"])
    fetched = client.get("/api/options/analyses/" + report["analysis_id"])
    assert fetched.status_code == 200 and fetched.json() == report
    assert fetched.headers["cache-control"] == "no-store"
    assert len(gateway.calls) == 1
    assert client.get("/api/sessions").json() == {"sessions": []}


def test_chat_binds_server_report_and_followups_inherit_it(workflow):
    client, _, gateway, calls = workflow
    report = capture(client)
    first = client.post("/api/chat", json={"message": "用白话解释这批数据。", "analysis_id": report["analysis_id"]}).json()
    second = client.post("/api/chat", json={"message": "为什么？", "session_id": first["session_id"]}).json()
    assert first["analysis_context"]["analysis_id"] == report["analysis_id"]
    assert second["active_analysis"]["analysis_id"] == report["analysis_id"]
    assert [item["analysis"] for item in calls] == [report, report]
    assert len(gateway.calls) == 1
    saved = client.get("/api/sessions/" + first["session_id"]).json()
    assert saved["active_analysis_id"] == report["analysis_id"]
    assert saved["messages"][-1]["analysis_context"] == second["analysis_context"]
    exported = client.get("/api/sessions/" + first["session_id"] + "/export").json()
    assert exported["messages"][1]["analysis_context"] == first["analysis_context"]


def test_invalid_context_and_forged_payload_never_create_session(workflow):
    client, _, gateway, calls = workflow
    response = client.post("/api/chat", json={"message": "解释这批数据", "analysis_id": str(uuid4())})
    assert response.status_code == 404 and response.json()["detail"]["code"] == "analysis_not_found"
    assert client.post("/api/chat", json={"message": "解释这批数据", "analysis_id": "not-an-id"}).status_code == 422
    assert client.post("/api/chat", json={"message": "解释这批数据", "analysis": {"price": 999}}).status_code == 422
    assert client.get("/api/sessions").json() == {"sessions": []}
    assert not gateway.calls and not calls


def test_binding_and_detaching_persist_and_keep_historical_reply(workflow):
    client, _, _, calls = workflow
    report = capture(client)
    sid = client.post("/api/sessions", json={"title": "Options question"}).json()["id"]
    bound = client.put(f"/api/sessions/{sid}/analysis", json={"analysis_id": report["analysis_id"]})
    assert bound.status_code == 200 and bound.json()["active_analysis"]["analysis_id"] == report["analysis_id"]
    reply = client.post("/api/chat", json={"message": "解释本批依据。", "session_id": sid}).json()
    unbound = client.put(f"/api/sessions/{sid}/analysis", json={"analysis_id": None})
    assert unbound.json() == {"active_analysis_id": None, "active_analysis": None}
    saved = client.get(f"/api/sessions/{sid}").json()
    assert saved["active_analysis"] is None
    assert saved["messages"][-1]["analysis_context"] == reply["analysis_context"]
    assert len(calls) == 1


def test_ordinary_questions_and_calculators_remain_available_when_bound(workflow):
    client, app, _, calls = workflow
    report = capture(client)
    ordinary = []

    async def general(message, history, language, engine):
        ordinary.append(message)
        return {"answer": "木星。", "sources": [], "mode": "offline"}

    app.state.service.answer = general
    for prompt in ("太阳系最大的行星是哪一颗？", "Write a short birthday poem.", "loan principal=1200 annual_rate=0 years=1",
                   "What is data science?", "How do I protect my personal data online?", "What are the risks of hiking alone?",
                   "How do video calls work?", "如何规划我的房贷还款？", "Write a report on photosynthesis.",
                   "What is a sample in statistics?", "帮我写一份光合作用实验报告。"):
        data = client.post("/api/chat", json={"message": prompt, "analysis_id": report["analysis_id"]}).json()
        assert data["answer"] == "木星。" and not data.get("analysis_context")
        assert data["active_analysis"]["analysis_id"] == report["analysis_id"]
    assert len(ordinary) == 11 and not calls


def test_explicit_null_chat_context_overrides_previous_binding(workflow):
    client, _, _, calls = workflow
    report = capture(client)
    first = client.post("/api/chat", json={"message": "解释本批数据", "analysis_id": report["analysis_id"]}).json()
    second = client.post("/api/chat", json={"message": "你好", "session_id": first["session_id"], "analysis_id": None}).json()
    assert second["active_analysis"] is None and not second.get("analysis_context")
    assert client.get("/api/sessions/" + first["session_id"]).json()["active_analysis_id"] is None
    assert len(calls) == 1


def test_sessions_keep_independent_context_and_switch_preserves_old_reply(workflow):
    client, _, _, _ = workflow
    first, second = capture(client), capture(client)
    assert first["analysis_id"] != second["analysis_id"]
    a = client.post("/api/chat", json={"message": "解释本批数据", "analysis_id": first["analysis_id"]}).json()
    b = client.post("/api/chat", json={"message": "解释本批数据", "analysis_id": second["analysis_id"]}).json()
    assert a["session_id"] != b["session_id"]
    client.put(f"/api/sessions/{a['session_id']}/analysis", json={"analysis_id": second["analysis_id"]})
    saved = client.get(f"/api/sessions/{a['session_id']}").json()
    assert saved["active_analysis_id"] == second["analysis_id"]
    assert saved["messages"][-1]["analysis_context"]["analysis_id"] == first["analysis_id"]
    assert client.get(f"/api/sessions/{b['session_id']}").json()["active_analysis_id"] == second["analysis_id"]


def test_unknown_binding_does_not_replace_valid_context(workflow):
    client, _, _, _ = workflow
    report = capture(client)
    sid = client.post("/api/sessions", json={}).json()["id"]
    client.put(f"/api/sessions/{sid}/analysis", json={"analysis_id": report["analysis_id"]})
    assert client.put(f"/api/sessions/{sid}/analysis", json={"analysis_id": str(uuid4())}).status_code == 404
    assert client.get(f"/api/sessions/{sid}").json()["active_analysis_id"] == report["analysis_id"]
    assert client.put("/api/sessions/missing/analysis", json={"analysis_id": report["analysis_id"]}).status_code == 404


def test_calculator_uses_actual_deterministic_service_while_analysis_is_attached(workflow):
    client, _, _, calls = workflow
    report = capture(client)
    result = client.post("/api/chat", json={"message": "loan principal=1200 annual_rate=0 years=1",
                                           "analysis_id": report["analysis_id"]}).json()
    assert result["mode"] == "calculator"
    assert result["calculation"]["values"]["monthly_payment"] == "100.00"
    assert result["active_analysis"]["analysis_id"] == report["analysis_id"]
    assert not calls


def test_batch_context_only_describes_successful_groups_and_records_failures(workflow):
    client, _, gateway, _ = workflow
    original = gateway.snapshot

    async def partial(symbol, *args):
        if symbol == "MISS":
            from app.options_ibkr import IBKROptionsError
            raise IBKROptionsError("ibkr_entitlement_missing", "Fixture missing data")
        return await original(symbol, *args)

    gateway.snapshot = partial
    report = client.post("/api/options/batch", json={"items": [{"symbol": "TEST"}, {"symbol": "MISS"}]}).json()
    UUID(report["analysis_id"])
    result = client.post("/api/chat", json={"message": "解释这份报告", "analysis_id": report["analysis_id"]}).json()
    context = result["analysis_context"]
    assert [scope["symbol"] for scope in context["scopes"]] == ["TEST"]
    assert context["partial_failures"] == [{"symbol": "MISS", "expiry": None, "code": "ibkr_entitlement_missing"}]

    failed = client.post("/api/options/batch", json={"items": [{"symbol": "MISS"}]}).json()
    assert failed["analysis_id"] is None and not failed["reports"]


def test_short_scope_and_data_time_questions_use_attached_snapshot(workflow):
    client, _, _, calls = workflow
    report = capture(client)
    for question in ("为什么报价这么少？", "数据还新鲜吗？", "这是什么意思？", "How old is the data?", "When was this collected?",
                     "有什么变化？", "这个变化说明什么？", "What has changed?"):
        reply = client.post("/api/chat", json={"message": question, "analysis_id": report["analysis_id"]}).json()
        assert reply["analysis_context"]["analysis_id"] == report["analysis_id"]
    assert len(calls) == 8
