"""Actual two-profile Edge/SSE workflow over an isolated controlled-provider app.

This is NOT a real DeepSeek/broker acceptance. The script never touches the
normal :8000 server or user database. A new :8015 fixture and tmp DB are owned
and stopped by this process. No financial response is intercepted in the browser.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/companion_sync_browser_v15.json"


def run(port=8015):
    base = f"http://127.0.0.1:{port}"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    scratch = ROOT / "tmp/companion-sync-v15" / run_id
    scratch.mkdir(parents=True, exist_ok=False)
    assert scratch.resolve().is_relative_to((ROOT / "tmp").resolve())
    shots = ROOT / "reports/screenshots/companion-sync-v15" / run_id
    report_path = REPORT if not REPORT.exists() else REPORT.with_stem(REPORT.stem + "-" + run_id)
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "running", "phase": "starting_fixture",
              "scope": "Actual Edge in independent browser profiles, real SSE/session APIs and persistence; controlled in-process provider, NOT real DeepSeek.",
              "browser_financial_data_or_chat_response_mocking": False,
              "browser_response_handling": "Chat/session/analysis/source responses come from the fixture backend. One real connection PUT reply is delayed, preserving its original response bytes, for a cursor race test.",
              "fault_injection": ["Fixture control closes actual SSE streams to require a new open/reset.",
                                  "One connection PUT response is delayed without fabricating its contents.",
                                  "Old generation and epoch reset messages are injected only into explicit browser test clients."],
              "external_model_requests": 0, "new_broker_requests": 0,
              "normal_user_server_or_database_touched": False, "fixture_port": port, "checks": [], "screenshots": [],
              "limitations": ["This verifies two browser profiles, not the native Windows window/tray; native acceptance is separate.",
                              "The fixture uses previously recorded real IBKR bars; neither report A nor B recollects data.",
                              "Provider output is deterministic test data; no real DeepSeek answer accuracy is measured."]}
    process, output, browser = None, None, None
    contexts = []
    errors = []
    started = time.perf_counter()
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError("Fixture port is occupied; no existing process was stopped")
    try:
        output = (scratch / "fixture.log").open("w", encoding="utf-8")
        env = {**os.environ, "FINPILOT_COMPANION_TEST_DB": str(scratch / "fixture.sqlite3"),
               "DEEPSEEK_API_KEY": "fixture-provider-only", "IBKR_ENABLED": "false", "FINPILOT_OPTIONS_MODEL_DIAGNOSTICS": "0",
               "PYTHONIOENCODING": "utf-8"}
        command = [sys.executable, "-m", "uvicorn", "scripts.companion_fixture_v15:create_fixture_app", "--factory", "--host", "127.0.0.1", "--port", str(port)]
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        with httpx.Client(base_url=base, timeout=15) as control:
            for _ in range(60):
                try:
                    ready = control.get("/__fixture/state")
                    if ready.status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                if process.poll() is not None:
                    raise RuntimeError("Owned fixture failed to start; inspect its tmp log")
                time.sleep(.15)
            else:
                raise RuntimeError("Owned fixture startup timed out")
            initial = ready.json()
            assert initial["fixture_only"] and initial["counters"]["controlled_provider_generations"] == 0
            seed = initial["seed"]
            sid, other, aid, bid = [seed[key] for key in ("selected_session", "other_session", "analysis_a", "analysis_b")]

            def get_state():
                return control.get("/__fixture/state").json()

            def api(method, path, body=None):
                response = control.request(method, path, json=body) if body is not None else control.request(method, path)
                assert response.status_code == 200, f"Fixture control HTTP {response.status_code} for {path}"
                return response.json()

            def wait_until(predicate, message, page, seconds=15):
                deadline = time.perf_counter() + seconds
                while time.perf_counter() < deadline:
                    if predicate():
                        return
                    page.wait_for_timeout(80)
                raise AssertionError(message)

            def shot(page, label):
                shots.mkdir(parents=True, exist_ok=True)
                path = shots / (label + ".png")
                page.screenshot(path=str(path), animations="disabled")
                report["screenshots"].append(path.relative_to(ROOT).as_posix())

            def saved_messages():
                return api("GET", f"/api/sessions/{sid}")["messages"]

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
                web_context = browser.new_context(viewport={"width": 1440, "height": 1000}, extra_http_headers={"X-FinPilot-Test-Surface": "workspace"})
                pet_context = browser.new_context(viewport={"width": 1200, "height": 900}, extra_http_headers={"X-FinPilot-Test-Surface": "pet"})
                contexts.extend([web_context, pet_context])
                # Capture actual EventSource objects only for the explicit late-
                # message fault injection. Normal delivery is the real server.
                pet_context.add_init_script("""window.__syncSources=[];window.__sseOpens=0;window.__sseErrors=0;window.__sseResets=0;const Original=window.EventSource;window.EventSource=class extends Original {constructor(...args){super(...args);window.__syncSources.push(this);this.addEventListener('open',()=>window.__sseOpens++);this.addEventListener('error',()=>window.__sseErrors++);this.addEventListener('reset',()=>window.__sseResets++);}};""")
                web, pet = web_context.new_page(), pet_context.new_page()
                for page in (web, pet):
                    page.set_default_timeout(15000)
                    page.on("pageerror", lambda error: errors.append(str(error)))
                report["phase"] = "unconnected_pet_and_default_shape"
                pet.goto(base + "/pet", wait_until="domcontentloaded")
                pet.wait_for_function("()=>window.finPilotPet?.getStatus().avatar?.renderer==='canvas2d'")
                pet.locator("#pet-character").dblclick()
                expect(pet.locator("#pet-panel")).to_be_visible()
                assert pet.evaluate("window.finPilotPet.getStatus().sessionId") is None
                initial_reads = [r for r in get_state()["requests"] if r["surface"] == "pet" and r["path"].startswith("/api/sessions")]
                assert initial_reads == [], "Unconnected pet must not read existing conversations"
                assert get_state()["counters"]["controlled_provider_generations"] == 0
                assert pet.locator("#pet-messages").get_by_text("PRIVATE_OTHER_SENTINEL").count() == 0
                report["checks"].append("unconnected_pet_reads_no_old_chat_and_starts_no_model")

                report["phase"] = "explicit_workspace_connection"
                web.goto(base + "/workspace?session=" + sid, wait_until="domcontentloaded")
                web.wait_for_function("()=>window.finPilotCompanionClient && window.finPilotAvatarInstance?.getStatus().renderer==='canvas2d'")
                expect(web.locator("#companion-connect")).to_be_enabled()
                web.locator("#companion-connect").click()
                pet.wait_for_function("sid=>window.finPilotPet.getStatus().sessionId===sid", arg=sid)
                expect(pet.locator("#pet-analysis [data-analysis-id]")).to_have_attribute("data-analysis-id", aid)
                assert get_state()["counters"]["controlled_provider_generations"] == 0
                report["checks"].append("explicit_connection_real_sse_separate_profiles_zero_generation")

                def assert_messages(count):
                    expect(web.locator("#chat-messages .message")).to_have_count(count)
                    expect(pet.locator("#pet-messages .message")).to_have_count(count)
                    ids = [str(m["id"]) for m in saved_messages()]
                    for page, selector in ((web, "#chat-messages .message"), (pet, "#pet-messages .message")):
                        actual = page.locator(selector).evaluate_all("items=>items.map(x=>x.dataset.messageId)")
                        assert actual == ids and len(actual) == len(set(actual)), "POST + SSE duplicated or reordered persisted messages"

                report["phase"] = "workspace_to_pet_actual_state_and_sources"
                api("POST", "/__fixture/control", {"action": "hold_next"})
                web.locator("#message-input").fill("WORKSPACE_A 请用白话解释当前报告。")
                web.locator("#send-button").click()
                wait_until(lambda: get_state()["waiting"], "Controlled provider was not reached", web)
                pet.wait_for_function("()=>window.finPilotPet.getStatus().avatar.state==='thinking'")
                frames = pet.evaluate("window.finPilotPet.getStatus().avatar.spriteChanges")
                pet.wait_for_function("n=>window.finPilotPet.getStatus().avatar.spriteChanges>n", arg=frames)
                api("POST", "/__fixture/control", {"action": "release"})
                assert_messages(2)
                expect(web.locator("#message-input")).to_have_value("")
                expect(pet.locator(".message.assistant .message-mode")).to_have_text("DeepSeek")
                assert saved_messages()[-1]["analysis_context"]["analysis_id"] == aid
                expect(pet.locator(".message.assistant .message-sources a[data-source-id='expert.put_call']")).to_have_count(1)
                expect(pet.locator(".message.assistant .analysis-history-period")).to_contain_text("2026-11-06")
                report["checks"].append("workspace_to_pet_thinking_animation_same_saved_sources_times_and_message_ids")
                shot(web, "workspace-first-turn");shot(pet, "pet-first-turn")

                report["phase"] = "pet_to_workspace_no_duplicates"
                pet.locator("#pet-input").fill("PET_A 这些历史数据能说明现在市场看空吗？")
                pet.locator("#pet-send").click()
                assert_messages(4)
                expect(pet.locator("#pet-input")).to_have_value("")
                assert saved_messages()[-1]["analysis_context"]["analysis_id"] == aid
                report["checks"].append("pet_to_workspace_same_sid_canonical_reload_without_duplicate_append")

                report["phase"] = "new_binding_inherited_old_reply_immutable"
                first_context = saved_messages()[1]["analysis_context"]
                api("PUT", f"/api/sessions/{sid}/analysis", {"analysis_id": bid})
                expect(pet.locator("#pet-analysis [data-analysis-id]")).to_have_attribute("data-analysis-id", bid)
                pet.locator("#pet-input").fill("PET_B 请解释当前报告。")
                pet.locator("#pet-send").click()
                assert_messages(6)
                messages = saved_messages()
                assert messages[-1]["analysis_context"]["analysis_id"] == bid
                assert messages[1]["analysis_context"] == first_context
                calls = [r for r in get_state()["requests"] if r["method"] == "POST" and r["path"] == "/api/chat"]
                assert all("analysis_id" not in r["keys"] for r in calls), "Shared client must not rebind a stale analysis"
                assert api("GET", f"/api/sessions/{sid}")["active_analysis_id"] == bid
                report["checks"].append("shared_post_omits_analysis_id_inherits_B_and_preserves_old_A_answers")

                report["phase"] = "real_sse_disconnect_reconnect_no_auto_question"
                before = get_state()["counters"]["controlled_provider_generations"]
                opens = pet.evaluate("window.__sseOpens")
                resets = pet.evaluate("window.__sseResets")
                api("POST", "/__fixture/control", {"action": "break_streams"})
                pet.wait_for_function("counts=>window.__sseOpens>counts.opens&&window.__sseResets>counts.resets&&window.__syncSources[0].readyState===EventSource.OPEN", arg={"opens": opens, "resets": resets}, timeout=15000)
                assert_messages(6)
                assert get_state()["counters"]["controlled_provider_generations"] == before
                report["sse_reconnect"] = {"before_open_events": opens, "after_open_events": pet.evaluate("window.__sseOpens"),
                                           "before_reset_events": resets, "after_reset_events": pet.evaluate("window.__sseResets"),
                                           "error_events": pet.evaluate("window.__sseErrors"), "actual_service_restart_tested": False}
                report["checks"].append("actual_sse_stream_closure_reconnect_full_sync_zero_extra_generation")

                report["phase"] = "client_cursor_and_operation_origin_races"
                pet.evaluate("""async()=>{window.__raceActivities=[];window.__raceClient=FinPilotCompanionClient.create({surface:'workspace',shouldSync:()=>false,onActivity:a=>window.__raceActivities=a});await window.__raceClient.ready;}""")
                pet.wait_for_function("()=>window.__syncSources.length===2&&window.__syncSources[1].readyState===EventSource.OPEN")
                current = api("GET", "/api/companion/connection")
                busy_body = {"session_id": sid, "generation": current["generation"], "operation_id": "late-http-snapshot", "kind": "calculate", "status": "started"}
                api("POST", "/api/companion/activity", busy_body)
                pet.wait_for_function("()=>window.__raceClient.getConnection()?.activities?.some(a=>a.operation_id==='late-http-snapshot')")
                held = []
                def delay_preference_snapshot(route):
                    if route.request.method == "PUT":
                        actual = route.fetch()
                        held.append((route, actual))
                    else:
                        route.continue_()
                pet.route("**/api/companion/connection", delay_preference_snapshot)
                pet.evaluate("""()=>{window.__raceSettled=false;window.__raceClient.setPreferences({language:'en'}).then(()=>window.__raceSettled=true);} """)
                wait_until(lambda: bool(held), "Preference response was not held", pet)
                completed = api("POST", "/api/companion/activity", {**busy_body, "status": "completed"})
                pet.wait_for_function("()=>window.__raceClient.getConnection()?.activities?.length===0")
                held[0][0].fulfill(response=held[0][1])
                pet.wait_for_function("()=>window.__raceSettled")
                assert pet.evaluate("window.__raceClient.getConnection().activities.length") == 0
                assert pet.evaluate("window.__raceClient.getConnection().seq") >= completed["seq"]
                pet.unroute("**/api/companion/connection", delay_preference_snapshot)
                report["checks"].append("delayed_real_http_snapshot_cannot_resurrect_activity_after_newer_sse")

                pet.evaluate("""async sid=>{await window.__raceClient.publishActivity({operationId:'old-heartbeat',kind:'calculate',status:'started',sessionId:sid});}""", sid)
                api("PUT", "/api/companion/connection", {"session_id": None})
                renewed = api("PUT", "/api/companion/connection", {"session_id": sid, "language": "zh"})
                pet.wait_for_function("value=>window.__raceClient.getConnection()?.generation===value", arg=renewed["generation"])
                activity_requests = sum(r["path"] == "/api/companion/activity" for r in get_state()["requests"])
                pet.evaluate("""async sid=>{await window.__raceClient.publishActivity({operationId:'old-heartbeat',kind:'calculate',status:'started',sessionId:sid});await window.__raceClient.publishActivity({operationId:'old-heartbeat',kind:'calculate',status:'completed',sessionId:sid});}""", sid)
                assert sum(r["path"] == "/api/companion/activity" for r in get_state()["requests"]) == activity_requests
                assert api("GET", "/api/companion/connection")["activities"] == []
                report["checks"].append("old_operation_heartbeat_and_finish_cannot_adopt_a_new_connection_generation")

                retired = pet.evaluate("window.__raceClient.getConnection()")
                fake_reset = {**retired, "epoch": str(uuid4()), "seq": 0, "generation": 0, "session_id": None, "activities": []}
                pet.evaluate("value=>window.__syncSources[1].dispatchEvent(new MessageEvent('reset',{data:JSON.stringify({epoch:value.epoch,seq:value.seq,generation:value.generation,type:'reset',session_id:value.session_id,payload:{connection:value}})}))", fake_reset)
                pet.evaluate("value=>window.__syncSources[1].dispatchEvent(new MessageEvent('reset',{data:JSON.stringify({epoch:value.epoch,seq:value.seq+9999,generation:value.generation,type:'reset',session_id:value.session_id,payload:{connection:value}})}))", retired)
                assert pet.evaluate("window.__raceClient.getConnection().epoch") == fake_reset["epoch"]
                pet.evaluate("window.__raceClient.destroy()")
                report["checks"].append("client_only_epoch_fault_injection_rejects_a_retired_epoch_reset")

                report["phase"] = "explicit_disconnect_and_pending_operation_switch"
                old_connection = api("GET", "/api/companion/connection")
                pet.locator("#pet-disconnect").click()
                pet.wait_for_function("()=>window.finPilotPet.getStatus().sessionId===null")
                expect(pet.locator("#pet-messages .message")).to_have_count(0)
                web.locator("#companion-connect").click()
                pet.wait_for_function("sid=>window.finPilotPet.getStatus().sessionId===sid", arg=sid)
                assert_messages(6)
                api("POST", "/__fixture/control", {"action": "hold_next"})
                pet.locator("#pet-input").fill("PET_OLD 请解释当前报告。")
                pet.locator("#pet-send").click()
                wait_until(lambda: get_state()["waiting"], "Pending provider was not held", pet)
                pending_connection = api("GET", "/api/companion/connection")
                switched = api("PUT", "/api/companion/connection", {"session_id": other})
                pet.wait_for_function("sid=>window.finPilotPet.getStatus().sessionId===sid", arg=other)
                expect(pet.locator("#pet-messages .message")).to_have_count(2)
                # The old operation's completion must remain in its original
                # conversation and cannot replace the newly selected pet view.
                api("POST", "/__fixture/control", {"action": "release"})
                expect(pet.locator("#pet-send")).to_be_enabled()
                assert pet.evaluate("window.finPilotPet.getStatus().sessionId") == other
                assert "PET_OLD" not in pet.locator("#pet-messages").inner_text()
                assert len(saved_messages()) == 8
                stale = control.post("/api/companion/activity", json={"session_id": sid, "generation": pending_connection["generation"],
                    "operation_id": "stale-activity", "kind": "calculate", "status": "started"})
                assert stale.status_code == 409 and api("GET", "/api/companion/connection")["activities"] == []
                report["checks"].append("disconnect_clears_view_switch_during_pending_does_not_leak_answer_or_late_state")

                report["phase"] = "late_reset_ignored_and_delete_unlinks"
                # Explicit client-only fault injection, separately labelled.
                pet.evaluate("value=>window.__syncSources[0].dispatchEvent(new MessageEvent('connection.changed',{data:JSON.stringify({epoch:value.epoch,seq:value.seq,generation:value.generation,type:'connection.changed',session_id:value.session_id,payload:{connection:value}})}))", old_connection)
                assert pet.evaluate("window.finPilotPet.getStatus().sessionId") == other
                api("DELETE", f"/api/sessions/{other}")
                pet.wait_for_function("()=>window.finPilotPet.getStatus().sessionId===null")
                expect(pet.locator("#pet-messages .message")).to_have_count(0)
                report["checks"].append("client_injected_old_generation_reset_ignored_and_committed_delete_clears_link")

                report["phase"] = "general_safety_and_demo_isolation"
                api("PUT", "/api/companion/connection", {"session_id": sid})
                pet.wait_for_function("sid=>window.finPilotPet.getStatus().sessionId===sid", arg=sid)
                pet.locator("#pet-input").fill("GENERAL_SAFE 解释一下光合作用。")
                pet.locator("#pet-send").click()
                expect(pet.locator("#pet-messages .message")).to_have_count(10)
                assert pet.evaluate("window.__unsafeRan===undefined")
                assert pet.locator("#pet-messages .message-body img").count() == 0
                assert pet.locator("#pet-messages a[href^='javascript:']").count() == 0
                demo_context = browser.new_context(extra_http_headers={"X-FinPilot-Test-Surface": "demo"})
                contexts.append(demo_context)
                demo = demo_context.new_page();demo.on("pageerror", lambda error: errors.append(str(error)))
                demo.goto(base + "/demo", wait_until="domcontentloaded")
                demo.wait_for_function("()=>window.FinPilotCompanion !== undefined")
                demo_requests = [r for r in get_state()["requests"] if r["surface"] == "demo"]
                assert not any(r["path"].startswith("/api/sessions") or r["path"].startswith("/api/companion/") for r in demo_requests)
                report["checks"].append("safe_shared_html_url_rendering_and_demo_does_not_join_or_read_sessions")
                shot(pet, "pet-final-safety")

                final = get_state()
                assert final["counters"]["external_model_requests"] == final["counters"]["broker_requests"] == 0
                assert all(not m.get("warning") for m in saved_messages() if m["role"] == "assistant"), "Controlled history output must pass normal application validation"
                original = api("GET", f"/api/options/analyses/{aid}")
                assert hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest() == seed["analysis_a_fingerprint"]
                assert not errors
                report.update(status="passed", phase="complete", browser={"channel": "msedge", "version": browser.version,
                    "separate_profiles": True, "viewports": [{"width": 1440, "height": 1000}, {"width": 1200, "height": 900}]},
                    controlled_provider_generations=final["counters"]["controlled_provider_generations"],
                    provider_calls=final["provider_calls"], shared_chat_http_requests=[r for r in final["requests"] if r["path"] == "/api/chat"],
                    old_analysis_unchanged=True, screenshots_review_needed=True)
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__, error=str(error)[:1200])
        if "pet" in locals():
            try:
                shot(pet, "failed-pet")
            except Exception:
                pass
        if "control" in locals() and not control.is_closed:
            try:
                final = get_state()
                report.update(controlled_provider_generations=final["counters"]["controlled_provider_generations"],
                              provider_calls=final["provider_calls"])
            except Exception:
                pass
    finally:
        for context in contexts:
            try:
                context.close()
            except Exception:
                pass
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=5)
            report["owned_fixture_stopped"] = process.poll() is not None
        if output:
            output.close()
        report["page_errors"] = errors
        report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"status": report["status"], "phase": report["phase"], "checks": len(report["checks"]), "report": report_path.relative_to(ROOT).as_posix()}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8015)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or args.port == 8000:
        parser.error("Use a dedicated fixture port, never the user's :8000 server")
    raise SystemExit(run(args.port))
