"""Isolated browser-test app with a controlled provider, never external models/IB.

Only the test launcher starts this factory, on a separate loopback port and an
explicit database under tmp/. It adds test controls solely to this fixture app.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import signal
from typing import Literal

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.config import ROOT, Settings
from app.main import create_app, analyze_history_capture


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["hold_next", "release", "break_streams", "shutdown"]


def create_fixture_app():
    raw_path = os.environ.get("FINPILOT_COMPANION_TEST_DB")
    if not raw_path:
        raise RuntimeError("Explicit isolated test database is required")
    path = Path(raw_path).resolve()
    if not path.is_relative_to((ROOT / "tmp").resolve()):
        raise RuntimeError("Fixture database must remain under workspace tmp/")
    counters = {"controlled_provider_generations": 0, "external_model_requests": 0, "broker_requests": 0}
    state = {"hold_next": False, "waiting": False, "requests": [], "provider_calls": []}
    gate = asyncio.Event()

    class BrokerForbidden:
        async def status(self):
            return {"status": "disabled", "message": "Controlled fixture: no broker transport"}
        async def snapshot(self, *args, **kwargs):
            counters["broker_requests"] += 1
            raise AssertionError("Browser fixture must not collect market data")
        async def list_expirations(self, *args, **kwargs):
            counters["broker_requests"] += 1
            raise AssertionError("Browser fixture must not query a Gateway")

    app = create_app(Settings(api_key="fixture-provider-only", offline=False, db_path=path), options_provider=BrokerForbidden())
    app.state.service.local_provider.status = lambda: {"available": False, "reason": "controlled_fixture", "trained": False}

    async def controlled_complete(messages, *, json_output=False):
        counters["controlled_provider_generations"] += 1
        payload = None
        for item in reversed(messages):
            if item.get("role") != "user":
                continue
            try:
                candidate = json.loads(item["content"])
            except (TypeError, ValueError):
                continue
            if isinstance(candidate, dict) and "saved_history" in candidate:
                payload = candidate
                break
        question = payload.get("question", "") if payload else messages[-1]["content"]
        marker = next(iter(re.findall(r"\b(?:WORKSPACE|PET|GENERAL)_[A-Z]+\b", question)), "UNTAGGED")
        state["provider_calls"].append({"marker": marker, "json_output": bool(json_output),
                                         "analysis_id": payload.get("saved_history", {}).get("analysis_id") if payload else None})
        if state["hold_next"]:
            state["hold_next"] = False
            state["waiting"] = True
            gate.clear()
            try:
                await asyncio.wait_for(gate.wait(), 35)
            finally:
                state["waiting"] = False
        else:
            await asyncio.sleep(.15)
        if payload:
            local = {r["id"] for r in payload["local_evidence"]}
            experts = {r["id"] for r in payload["expert_sources"]}
            assert {"expert.put_call", "expert.history_time"} <= experts
            assert {"h.change.volume_total", "h.change.oi_total"} <= local
            return json.dumps({"response": [
                {"kind": "limitation", "text": marker + "：这份历史样本的成交变化未满足可比条件，缺失的持仓仍未提供。",
                 "evidence_ids": ["h.change.volume_total", "h.change.oi_total"]},
                {"kind": "explanation", "text": "看跌合约计数不是看空人数，历史资料不能代表当前市场情绪。",
                 "evidence_ids": ["expert.put_call", "expert.history_time"]},
            ]}, ensure_ascii=False)
        # This is intentionally hostile display text, not executable HTML.
        return marker + ' controlled fixture response. <img src=x onerror="window.__unsafeRan=true"> [unsafe](javascript:alert(1))'

    cloud = app.state.service.provider
    assert cloud is app.state.history_chat.cloud is app.state.options_chat.cloud is app.state.options.llm
    cloud.complete = controlled_complete

    capture = json.loads((ROOT / "reports/ibkr_history_probe_v13.json").read_text(encoding="utf-8"))
    first = analyze_history_capture(deepcopy(capture))
    first["label"] = "Controlled archive A; existing IBKR bars, no new collection"
    second = deepcopy(first)
    second["label"] = "Controlled archive B; same archived values, distinct immutable analysis"
    aid = app.state.store.save_analysis(first)
    bid = app.state.store.save_analysis(second)
    selected = app.state.store.create("Selected fixture conversation")["id"]
    other = app.state.store.create("Other fixture conversation")["id"]
    app.state.store.set_active_analysis(selected, aid)
    app.state.store.append_turn(other, "PRIVATE_OTHER_SENTINEL", {"answer": "Unselected fixture only", "sources": [], "mode": "offline"})
    seeded = {"selected_session": selected, "other_session": other, "analysis_a": aid, "analysis_b": bid,
              "analysis_a_fingerprint": hashlib.sha256(json.dumps(app.state.store.get_analysis(aid), sort_keys=True).encode()).hexdigest()}

    @app.middleware("http")
    async def audit(request: Request, call_next):
        route = request.url.path
        if not route.startswith("/__fixture/"):
            item = {"surface": request.headers.get("x-finpilot-test-surface", "control"), "method": request.method, "path": route}
            if request.method == "POST" and route == "/api/chat":
                body = await request.json()
                item["keys"] = sorted(body)
                item["session_id"] = body.get("session_id")
                item["analysis_id"] = body.get("analysis_id")
            state["requests"].append(item)
        if route in {"/api/options/analyze", "/api/options/batch", "/api/options/history/fetch"} or route.endswith("/analysis/refresh"):
            counters["broker_requests"] += 1
            return JSONResponse({"detail": "No new broker requests are permitted by the fixture"}, status_code=403)
        return await call_next(request)

    @app.get("/__fixture/state")
    async def fixture_state():
        return {"fixture_only": True, "provider": "Controlled in-process replacement; NOT a real DeepSeek response",
                "seed": seeded, "counters": counters, **state}

    @app.post("/__fixture/control")
    async def fixture_control(body: Control):
        if body.action == "hold_next":
            state["hold_next"] = True
        elif body.action == "release":
            gate.set()
        elif body.action == "break_streams":
            # An actual stream terminates and EventSource reconnects; a queue
            # sentinel closes just that stream without restarting the backend.
            for sub in list(app.state.companion.subscribers):
                while not sub.queue.empty():
                    sub.queue.get_nowait()
                sub.queue.put_nowait(None)
        else:
            # Test-only owned-service teardown, never mounted in production.
            asyncio.get_running_loop().call_later(.1, os.kill, os.getpid(), signal.SIGTERM)
        return {"accepted": True}

    return app
