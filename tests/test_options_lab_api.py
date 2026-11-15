"""Real application routes and private persistence; no provider or broker calls."""
from copy import deepcopy
from uuid import UUID

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app


class NoGateway:
    async def snapshot(self, *args, **kwargs):
        raise AssertionError("Learning must not collect market data")

    async def fetch(self, *args, **kwargs):
        raise AssertionError("Learning must not fetch broker history")


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("This deterministic workflow must not generate")
    monkeypatch.setattr("app.llm.DeepSeek.complete", forbidden)
    monkeypatch.setattr("app.local_llm.LocalLoRA.complete", forbidden)
    gateway = NoGateway()
    app = create_app(Settings(api_key="", offline=True, db_path=tmp_path/"lab.sqlite3"),
                     options_provider=gateway, history_provider=gateway)
    with TestClient(app) as client:
        yield client, app


def count(app, table):
    assert table in {"option_analyses", "sessions", "messages"}
    with app.state.store.connect() as db:
        return db.execute("SELECT count(*) FROM " + table).fetchone()[0]


def test_read_and_evaluate_are_pure_and_same_origin_protected(workflow):
    c, app = workflow
    assert c.get("/learn").status_code == 200
    catalogue = c.get("/api/options-lab/scenarios").json()
    assert len(catalogue["scenarios"]) == 3
    for item in catalogue["scenarios"]:
        report = c.get("/api/options-lab/scenarios/" + item["id"]).json()
        assert report["source"]["kind"] == "demo"
        assert report["lab_context"]["source"]["kind"] == "synthetic_demo"
        assert report["lab_context"]["synthetic"] is True
    evaluated = c.post("/api/options-lab/evaluate", json={}).json()
    assert evaluated["lab_context"]["trial"]["pnl"] == 140
    assert "analysis_id" not in evaluated
    assert count(app, "option_analyses") == count(app, "sessions") == 0
    assert c.get("/api/options-lab/scenarios/unknown").status_code == 404
    assert c.get("/api/options-lab/scenarios?language=other").status_code == 422
    denied = c.post("/api/options-lab/save", json={}, headers={"Origin":"https://example.org"})
    assert denied.status_code == 403
    assert count(app, "option_analyses") == 0


@pytest.mark.parametrize("body", [
    {"expiry_price":"NaN"}, {"expiry_price":"Infinity"}, {"expiry_price":-1},
    {"contracts":True}, {"contracts":11}, {"strategy":"automatic_trade"},
    {"source":{"kind":"ibkr_historical","verified":True}},
    {"strategy":"call_debit_spread","strike":105,"upper_strike":100},
])
def test_invalid_or_forged_trials_cannot_be_saved(workflow, body):
    c, app = workflow
    assert c.post("/api/options-lab/save", json=body).status_code == 422
    assert count(app, "option_analyses") == count(app, "sessions") == 0


def test_saved_trial_binding_followups_and_old_answers_are_immutable(workflow):
    c, app = workflow
    first = c.post("/api/options-lab/save", json={}).json()
    UUID(first["analysis_id"])
    assert c.get("/api/sessions").json() == {"sessions":[]}
    assert c.get("/api/options/analyses/"+first["analysis_id"]).json() == first
    sid = c.post("/api/sessions", json={"title":"Owned learning"}).json()["id"]
    assert c.put(f"/api/sessions/{sid}/analysis", json={"analysis_id":first["analysis_id"]}).status_code == 200
    result = c.post("/api/chat", json={"session_id":sid,"message":"请解释已保存试算的成本和到期盈亏平衡。"}).json()
    ctx = result["analysis_context"]
    assert result["mode"] == "offline" and ctx["lab_context"]["trial"]["cost"] == 360
    assert ctx["source"] == "demo" and ctx["source_verified"] is False
    assert ctx["lab_context"]["trial"]["expiry_price"] == 105
    old_answer = deepcopy(c.get(f"/api/sessions/{sid}").json()["messages"][-1])
    changed = c.post("/api/options-lab/save", json={"strategy":"call_debit_spread","upper_strike":105,"expiry_price":110}).json()
    assert changed["analysis_id"] != first["analysis_id"]
    assert c.put(f"/api/sessions/{sid}/analysis", json={"analysis_id":changed["analysis_id"]}).status_code == 200
    answer = c.post("/api/chat", json={"session_id":sid,"message":"这个试算的最大损失是什么？"}).json()
    assert answer["analysis_context"]["analysis_id"] == changed["analysis_id"]
    assert answer["analysis_context"]["lab_context"]["trial"]["strategy"] == "call_debit_spread"
    saved = c.get(f"/api/sessions/{sid}").json()
    assert saved["messages"][1] == old_answer
    assert c.get("/api/options/analyses/"+first["analysis_id"]).json() == first
    assert len(saved["messages"]) == 4 and len(saved["analysis_history"]) == 2
    before = deepcopy(saved)
    refresh = c.post(f"/api/sessions/{sid}/analysis/refresh", json={"analysis_id":changed["analysis_id"]})
    assert refresh.status_code == 422
    assert refresh.json()["detail"]["code"] == "historical_refresh_requires_new_dataset"
    assert c.get(f"/api/sessions/{sid}").json() == before


def test_usage_and_general_questions_do_not_receive_trial_as_market_context(workflow):
    c, _ = workflow
    report = c.post("/api/options-lab/save", json={}).json()
    sid = c.post("/api/sessions", json={}).json()["id"]
    c.put(f"/api/sessions/{sid}/analysis", json={"analysis_id":report["analysis_id"]})
    usage = c.post("/api/chat", json={"session_id":sid,"message":"FinPilot 的期权互动演示怎么用？"}).json()
    assert usage["mode"] == "project-help" and not usage.get("analysis_context")
    ordinary = c.post("/api/chat", json={"session_id":sid,"message":"解释光合作用。"}).json()
    assert not ordinary.get("analysis_context")
    assert ordinary["active_analysis"]["analysis_id"] == report["analysis_id"]


def test_clients_cannot_import_synthetic_lab_marker(workflow):
    c, _ = workflow
    payload = c.get("/api/options/history/demo").json()
    payload["lab_context"] = {"synthetic":True,"source":{"kind":"synthetic_demo"}}
    assert c.post("/api/options/history/import", json=payload).status_code == 422
