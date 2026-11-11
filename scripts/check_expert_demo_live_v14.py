"""Opt-in actual Edge demo: archived history → references → two model answers.

Without --live: zero HTTP/browser/broker/model calls and no report changes.
With --live: one actual /history/sample archive replay (NOT a new IB capture),
one UI expert search, and two UI chat turns. No financial response is mocked.
No existing sessions are read. Only the session created by the first chat is
queried/exported/deleted. One schema repair per answer is server-bounded; the
script never retries. A failed run remains failed and requires a separate,
explicit authorization for any further live diagnosis.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
from time import perf_counter
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_history_live_v13 import QUESTIONS, audit_answer, audit_history, fingerprint, read_response, safe_text


REPORT = ROOT / "reports/expert_demo_cloud_v14.json"
SHOTS = ROOT / "reports/screenshots/expert-demo-v14-live"


def answer_parts(answer):
    """Inspect the rendered paragraph/citation bindings, excluding local notice."""
    body = answer.split("\n\n", 1)[-1]
    return [{"kind": "explanation", "text": re.sub(r"\s*\[[A-Za-z][A-Za-z0-9_.-]*\]", "", paragraph).strip(),
             "evidence_ids": list(dict.fromkeys(re.findall(r"\[([A-Za-z][A-Za-z0-9_.-]*)\]", paragraph)))}
            for paragraph in re.split(r"\n\s*\n", body) if paragraph.strip()]


def audit_grounding(reply, record, question, catalogue):
    from app.expert_grounding import validate_expert_grounding

    context = reply["analysis_context"]
    retrieval = context["retrieval"]
    assert retrieval["knowledge_version"] == catalogue["version"]
    assert retrieval["corpus_sha256"] == catalogue["corpus_sha256"]
    documents = {item["id"]: item for item in catalogue["documents"]}
    hits = {item["id"]: item for item in retrieval["hits"]}
    assert set(hits) <= documents.keys(), "Retrieval returned an unknown expert ID"
    for hit in hits.values():
        if hit.get("method") == "curated_support_facet":
            assert hit.get("bm25_rank") is None and hit.get("char_rank") is None and hit.get("rrf_score") is None
            assert hit.get("selection_reason") in {"context_facet", "query_facet", "required_facet"}
    for source in reply["sources"]:
        assert source["id"] in hits
        assert source["supports"] == documents[source["id"]]["supports"]
    audit = validate_expert_grounding(answer_parts(reply["answer"]),
        [documents[key] for key in hits], question, "historical_ibkr",
        local_ids={item["id"] for item in record["evidence"]})
    assert audit["method"] == "reviewed_support_facets"
    return audit


def _screenshot(page, path, owned_sid):
    masks = []
    if owned_sid:
        # The current page does not display IDs, but mask any future occurrence.
        candidate = page.get_by_text(owned_sid, exact=False)
        if candidate.count():
            masks.append(candidate)
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), animations="disabled", mask=masks)


def run(base):
    from playwright.sync_api import expect, sync_playwright
    from app.expert_knowledge import ExpertKnowledge

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    report_path = REPORT if not REPORT.exists() else REPORT.with_stem(REPORT.stem + "-" + run_id)
    shot_dir = SHOTS / run_id
    report = {
        "checked_at": datetime.now(UTC).isoformat(), "status": "running", "phase": "initializing",
        "transport": "Actual Edge 1440x1000 → /demo → loopback HTTP → saved historical archive and DeepSeek",
        "provenance": "This run replays the server's existing IBKR archive. It does NOT reconnect to IBKR or collect fresh market data.",
        "privacy": "Fresh browser context. Existing session list/details are never read. Only this page's newly created session is audited and removed. No request headers, credentials, account data or session IDs are stored.",
        "no_response_mocking": True, "new_broker_requests": 0, "automatic_script_retries": 0, "automatic_network_retries": 0,
        "diagnostics_trace_enabled_by_test": False,
        "model_budget": {"answer_turns": 2, "maximum_generations": 4, "maximum_schema_repairs_per_answer": 1},
        "count_visibility": "HTTP/UI actions are observed. Provider-internal generation counts are reported by the server, not directly observed by this browser test.",
        "counters": {"archive_replay_http_requests": 0, "expert_search_http_requests": 0, "chat_http_requests": 0, "confirmed_deepseek_replies": 0},
        "turns": [], "screenshots": [], "checks": [],
    }
    started = perf_counter()
    owned_sid, analysis_id, context, page = None, None, None, None
    errors, blocked, unexpected_external = [], [], []
    credential_checks = 0
    try:
        with sync_playwright() as runner:
            browser = runner.chromium.launch(channel="msedge", headless=True)
            report["browser"] = {"channel": "msedge", "version": browser.version, "headless": True, "viewport": {"width": 1440, "height": 1000}}
            context = browser.new_context(base_url=base, viewport={"width": 1440, "height": 1000},
                                          reduced_motion="no-preference", timezone_id="Asia/Shanghai")
            request = context.request
            try:
                report["phase"] = "health_and_catalogue"
                health = read_response(request.get(base + "/api/health", timeout=10000, max_retries=0), report)
                assert health.get("version") == "14.0.0", "Restarted v14 service is required"
                assert health.get("mode") in {"deepseek", "online"}, "Cloud chat is not configured"
                report["app_version"] = health["version"]
                catalogue = read_response(request.get(base + "/api/experts", timeout=10000, max_retries=0), report)
                local_knowledge = ExpertKnowledge()
                assert catalogue["version"] == local_knowledge.version and catalogue["corpus_sha256"] == local_knowledge.corpus_sha256
                assert catalogue["document_count"] == len(catalogue["documents"]) == len(local_knowledge.documents)
                assert catalogue["embedding"] is False
                report["catalogue"] = {key: catalogue[key] for key in ("version", "corpus_sha256", "document_count", "embedding")}

                def guard(route):
                    nonlocal credential_checks
                    incoming = route.request
                    parsed = urlsplit(incoming.url)
                    if parsed.scheme not in {"http", "https"} or parsed.netloc != urlsplit(base).netloc:
                        unexpected_external.append({"scheme": parsed.scheme, "host": parsed.hostname})
                        route.abort()
                        return
                    path = parsed.path
                    if not path.startswith("/api/"):
                        route.continue_()
                        return
                    headers = incoming.all_headers()
                    assert not any(key.lower() in {"authorization", "proxy-authorization", "x-api-key"} for key in headers), "Unexpected credential header on demo request"
                    credential_checks += 1
                    if incoming.method == "GET" and path == "/api/models":
                        route.continue_()
                        return
                    if incoming.method == "POST" and path == "/api/options/history/sample" and report["counters"]["archive_replay_http_requests"] == 0:
                        assert parse_qs(parsed.query).get("language") == ["zh"]
                        report["counters"]["archive_replay_http_requests"] += 1
                        route.continue_()
                        return
                    if incoming.method == "GET" and path == "/api/experts/search" and report["counters"]["expert_search_http_requests"] == 0:
                        assert parse_qs(parsed.query).get("q") == [QUESTIONS[0]]
                        report["counters"]["expert_search_http_requests"] += 1
                        route.continue_()
                        return
                    if incoming.method == "POST" and path == "/api/chat":
                        body = incoming.post_data_json
                        index = report["counters"]["chat_http_requests"]
                        if (index < 2 and body.get("session_id") == owned_sid and body.get("analysis_id") == analysis_id
                                and body.get("message") == QUESTIONS[index] and body.get("language") == "zh" and body.get("engine") == "deepseek"):
                            report["counters"]["chat_http_requests"] += 1
                            route.continue_()
                            return
                    # Includes /sessions, other people's session details, broker
                    # fetch/analyze/refresh routes and accidental repeated sends.
                    blocked.append({"method": incoming.method, "path": safe_text(path)})
                    route.abort()

                context.route("**/*", guard)
                context.add_init_script("""window.__v14AvatarStatuses=[];
                  document.addEventListener('finpilot-avatar-status',event=>{
                    const value=event.detail;if(!value)return;
                    const safe={};for(const key of ['requestedMode','actualMode','renderer','state','reducedMotion','fallbackReason','frames','threeRevision'])safe[key]=value[key];
                    window.__v14AvatarStatuses.push(safe);
                  },true);""")
                page = context.new_page()
                page.set_default_timeout(15000)
                page.on("pageerror", lambda error: errors.append(safe_text(error)))
                report["phase"] = "demo_initial_ui_and_real_avatar"
                with page.expect_response(lambda response: urlsplit(response.url).path == "/api/models") as models_response:
                    page.goto(base + "/demo", wait_until="domcontentloaded")
                models = read_response(models_response.value, report)
                expect(page.locator("#demo-load")).to_be_enabled()
                expect(page.locator("#demo-search-fields")).to_have_attribute("disabled", "")
                expect(page.locator("#demo-question")).to_be_disabled()
                expect(page.locator("#demo-chat-fields")).to_have_attribute("disabled", "")
                expect(page.locator("#demo-chat-input")).to_be_disabled()
                assert report["counters"] == {"archive_replay_http_requests": 0, "expert_search_http_requests": 0, "chat_http_requests": 0, "confirmed_deepseek_replies": 0}
                avatar = page.locator("#demo-avatar-stage .fp-avatar")
                expect(avatar).to_have_attribute("data-actual-mode", "3d")
                expect(page.locator("#demo-avatar-renderer")).to_contain_text(re.compile("WEBGL", re.I))
                canvas = avatar.locator("canvas")
                expect(canvas).to_be_visible()
                assert canvas.evaluate("node => {const gl=node.getContext('webgl2');return !!gl&&!gl.isContextLost()&&node.width>0&&node.height>0;}")
                page.wait_for_timeout(400)
                page.locator("#demo-avatar-2d").click()
                expect(avatar).to_have_attribute("data-actual-mode", "2d")
                expect(avatar.locator("svg.fp-avatar__flat")).to_be_visible()
                expect(page.locator("#demo-avatar-renderer")).to_contain_text(re.compile("SVG", re.I))
                shot = shot_dir / "demo-2d.png"
                _screenshot(page, shot, owned_sid)
                report["screenshots"].append(shot.relative_to(ROOT).as_posix())
                page.locator("#demo-avatar-3d").click()
                expect(avatar).to_have_attribute("data-actual-mode", "3d")
                expect(canvas).to_be_visible()
                statuses = page.evaluate("window.__v14AvatarStatuses")
                assert any(item["renderer"] == "webgl2" and item["frames"] > 0 and item["threeRevision"] for item in statuses)
                assert any(item["renderer"] == "svg" and item["actualMode"] == "2d" for item in statuses)
                report["avatar"] = {"actual_webgl2_draw_observed": True, "native_svg_2d_observed": True,
                                    "rendered_frames_at_mode_change": max(item.get("frames", 0) for item in statuses),
                                    "three_revision": next(item["threeRevision"] for item in statuses if item.get("threeRevision"))}
                shot = shot_dir / "demo-3d.png"
                _screenshot(page, shot, owned_sid)
                report["screenshots"].append(shot.relative_to(ROOT).as_posix())
                select = page.locator("#demo-model")
                expect(select).to_be_enabled()
                assert any(item["id"] == "deepseek" and item["available"] for item in models["models"])
                alternative = next((item for item in models["models"] if item["id"] != "deepseek" and item["available"]), None)
                if alternative:
                    select.select_option(alternative["id"])
                    expect(select).to_have_value(alternative["id"])
                    report["model_switch"] = {"status": "verified_without_generation", "alternative_engine": alternative["id"]}
                else:
                    for item in models["models"]:
                        if not item["available"]:
                            expect(select.locator(f'option[value="{item["id"]}"]')).to_be_disabled()
                    report["model_switch"] = {"status": "only_deepseek_available", "limitation": "Unavailable alternatives are correctly disabled; no alternate generation was requested"}
                select.select_option("deepseek")
                expect(select).to_have_value("deepseek")
                assert report["counters"]["chat_http_requests"] == 0

                report["phase"] = "archive_replay_click"
                with page.expect_response(lambda response: response.request.method == "POST" and urlsplit(response.url).path == "/api/options/history/sample") as response:
                    page.locator("#demo-load").click()
                record = read_response(response.value, report)
                analysis_id = record["analysis_id"]
                report["analysis_id"] = analysis_id
                captured = audit_history(record, {"symbol": "AAPL", "expiry": "2026-11-13", "strike": 350.})
                captured["archived_original_capture_history_requests"] = captured.pop("server_reported_history_requests")
                captured["this_run_new_broker_requests"] = 0
                report["archive"] = captured
                assert re.fullmatch(r"[0-9a-f]{64}", record["source"].get("archive_sha256", ""))
                report["archive_sha256"] = record["source"]["archive_sha256"]
                original_hash = fingerprint(record)
                report["analysis_fingerprint"] = original_hash
                archive = page.locator("#demo-archive-result")
                expect(archive).to_be_visible()
                expect(archive).to_have_attribute("data-analysis-id", analysis_id)
                expect(archive.locator(".source-badge")).to_have_attribute("data-demo", "false")
                expect(archive.locator(".source-badge")).to_contain_text("IBKR")
                expect(archive).to_contain_text(record["period"]["start"])
                expect(archive).to_contain_text(record["period"]["end"])
                expect(archive.locator(".archive-fact").nth(1).locator("dd")).to_contain_text(re.compile(r"未.*(?:核验|验证)|unverified", re.I))
                expect(page.locator("#demo-archive")).to_have_attribute("data-state", "done")
                expect(page.locator("#demo-load-status")).to_be_visible()
                expect(page.locator("#demo-load-error")).not_to_be_visible()
                assert archive.locator(".contract-card").count() == len(record["contract_changes"])
                expect(page.locator("#demo-search-fields")).not_to_have_attribute("disabled", "")
                expect(page.locator("#demo-question")).to_be_enabled()
                expect(page.locator("#demo-chat-fields")).to_have_attribute("disabled", "")
                expect(page.locator("#demo-chat-input")).to_be_disabled()
                assert report["counters"]["chat_http_requests"] == 0

                report["phase"] = "expert_search_click"
                page.locator("#demo-question").fill(QUESTIONS[0])
                with page.expect_response(lambda response: urlsplit(response.url).path == "/api/experts/search") as response:
                    page.locator("#demo-search").click()
                hits = read_response(response.value, report)
                assert hits and isinstance(hits, list)
                catalogue_docs = {doc["id"]: doc for doc in catalogue["documents"]}
                for hit in hits:
                    assert hit["id"] in catalogue_docs
                    for key in ("url", "publisher", "reviewed_at", "supports"):
                        assert hit[key] == catalogue_docs[hit["id"]][key]
                    assert hit["retrieval"]["knowledge_version"] == catalogue["version"] and hit["retrieval"]["corpus_sha256"] == catalogue["corpus_sha256"]
                expect(page.locator("#demo-expert-results .expert-card")).to_have_count(len(hits))
                expect(page.locator("#demo-experts")).to_have_attribute("data-state", "done")
                expect(page.locator("#demo-search-status")).to_be_visible()
                expect(page.locator("#demo-search-error")).not_to_be_visible()
                expect(page.locator("#demo-chat-fields")).not_to_have_attribute("disabled", "")
                expect(page.locator("#demo-chat-input")).to_be_enabled()
                report["candidate_source_ids"] = [hit["id"] for hit in hits]
                assert report["counters"]["chat_http_requests"] == 0
                page.locator("#demo-expert-results .retrieval-details").first.locator("summary").click()
                shot = shot_dir / "demo-expert-search.png"
                page.locator("#demo-expert-results").scroll_into_view_if_needed()
                _screenshot(page, shot, owned_sid)
                report["screenshots"].append(shot.relative_to(ROOT).as_posix())

                assert not errors and not blocked and not unexpected_external, "Demo preflight failed before any model generation"
                replies = []
                for index, question in enumerate(QUESTIONS):
                    report["phase"] = f"turn_{index+1}_ui_chat"
                    editor = page.locator("#demo-chat-input")
                    editor.fill(question)
                    with page.expect_response(lambda response: response.request.method == "POST" and urlsplit(response.url).path == "/api/chat", timeout=95000) as response:
                        page.locator("#demo-explain").click()
                    reply = read_response(response.value, report)
                    if owned_sid is None:
                        owned_sid = reply.get("session_id")
                        assert isinstance(owned_sid, str) and owned_sid
                    else:
                        assert reply.get("session_id") == owned_sid
                    summary = {"mode": reply.get("mode"), "warning": reply.get("warning"), "answer_excerpt": safe_text(reply.get("answer", ""))[:7500],
                               "server_reported_generation_attempts": reply.get("generation_attempts"), "server_reported_schema_repair_attempts": reply.get("schema_repair_attempts")}
                    report["turns"].append(summary)
                    report["phase"] = f"turn_{index+1}_local_values_and_claim_source_support"
                    summary.update(audit_answer(reply, record, require_data=index == 0))
                    summary["paragraph_grounding_audit"] = audit_grounding(reply, record, question, catalogue)
                    replies.append(reply)
                    report["counters"]["confirmed_deepseek_replies"] += 1
                    report["phase"] = f"turn_{index+1}_ui_render"
                    expect(editor).to_be_enabled()
                    expect(editor).to_have_value("")
                    expect(page.locator("#demo-ai-error")).not_to_be_visible()
                    expect(page.locator("#demo-messages .demo-message.assistant")).to_have_count(index+1)
                    latest = page.locator("#demo-messages .demo-message.assistant").last
                    expect(latest.locator(".message-mode")).to_have_text("DeepSeek")
                    expect(latest.locator(".reply-warning")).to_have_count(0)
                    expect(latest.locator(".reply-scope")).to_contain_text(record["period"]["start"])
                    expect(latest.locator(".reply-scope")).to_contain_text(record["period"]["end"])
                    expect(latest.locator(".reply-source")).to_have_count(len(reply["sources"]))
                    for source in reply["sources"]:
                        expect(latest.locator(f'.demo-expert-reference[data-source-id="{source["id"]}"]').first).to_have_attribute("href", source["url"])
                    for identifier in reply["analysis_context"]["evidence_ids"]:
                        expect(latest.locator(f'.demo-inline-reference[data-evidence-id="{identifier}"]').first).to_be_visible()
                        expect(latest.locator(f'.demo-evidence-card[data-evidence-id="{identifier}"]')).to_have_count(1)
                    if reply["analysis_context"]["evidence_ids"]:
                        latest.locator(".demo-inline-reference[data-evidence-id]").first.click()
                        expect(latest.locator(".demo-evidence-card").first).to_be_visible()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "Desktop horizontal overflow"
                    latest.scroll_into_view_if_needed()
                    shot = shot_dir / f"demo-answer-{index+1}.png"
                    _screenshot(page, shot, owned_sid)
                    report["screenshots"].append(shot.relative_to(ROOT).as_posix())

                report["phase"] = "owned_session_persistence_export_and_fixed_history"
                for endpoint in (f"/api/sessions/{owned_sid}", f"/api/sessions/{owned_sid}/export"):
                    session = read_response(request.get(base + endpoint, timeout=15000, max_retries=0), report)
                    assert session["active_analysis_id"] == analysis_id and len(session["messages"]) == 4
                    assert [item["analysis_id"] for item in session["analysis_history"]] == [analysis_id]
                    for index, reply in enumerate(replies):
                        assert session["messages"][index*2]["content"] == QUESTIONS[index]
                        saved = session["messages"][index*2+1]
                        assert saved["content"] == reply["answer"] and saved["analysis_context"] == reply["analysis_context"] and saved["sources"] == reply["sources"]
                unchanged = read_response(request.get(base + f"/api/options/analyses/{analysis_id}", timeout=15000, max_retries=0), report)
                assert fingerprint(unchanged) == original_hash
                assert unchanged["source"]["archive_sha256"] == report["archive_sha256"]
                assert report["counters"] == {"archive_replay_http_requests": 1, "expert_search_http_requests": 1, "chat_http_requests": 2, "confirmed_deepseek_replies": 2}
                assert sum(item["server_reported_generation_attempts"] for item in report["turns"]) <= 4
                statuses = page.evaluate("window.__v14AvatarStatuses")
                assert any(item["state"] == "thinking" for item in statuses) and statuses[-1]["state"] == "idle"
                report["avatar"]["thinking_and_idle_states_observed"] = True
                assert not errors and not blocked and not unexpected_external
                report.update(status="passed_limited", workflow_status="passed", phase="complete", original_analysis_unchanged=True,
                              owned_session_persisted_and_exported=True, current_market_prediction=False,
                              limits=["Archive replay only; no new IBKR collection or present-market verification.", "Observed intraday bars do not prove complete-session coverage; volume changes remain incomparable and OI remains absent.",
                                      "Grounding checks recognized claim facets and retrieved support bindings; they are not general semantic entailment or an accuracy score."])
                report["checks"] = ["actual_demo_step_clicks", "no_existing_session_reads", "no_broker_routes_or_response_mocking", "real_webgl2_and_svg_renderers",
                                    "model_selection_without_generation", "separate_candidate_search_and_actual_answer_sources", "catalogue_version_hash_match",
                                    "per_paragraph_recognized_claim_support", "local_values_and_time_source_unchanged", "two_validated_deepseek_turns", "same_owned_session_persistence_and_export", "no_pageerror_or_horizontal_overflow"]
            except Exception as error:
                report.update(status="failed", workflow_status="failed", error_type=type(error).__name__)
                if isinstance(error, (AssertionError, ValueError)):
                    report["error_code"] = safe_text(error)[:700]
                if page is not None:
                    try:
                        shot = shot_dir / "demo-failed.png"
                        _screenshot(page, shot, owned_sid)
                        report["screenshots"].append(shot.relative_to(ROOT).as_posix())
                    except Exception:
                        pass
            finally:
                if owned_sid:
                    try:
                        deleted = request.delete(f"{base}/api/sessions/{owned_sid}", timeout=15000, max_retries=0)
                        report["owned_session_removed"] = deleted.status == 200 and deleted.json().get("deleted") is True
                    except Exception:
                        report["owned_session_removed"] = False
                    if not report["owned_session_removed"]:
                        report.update(status="failed", workflow_status="failed", cleanup_error="owned_session_cleanup_failed")
                report["immutable_archived_analyses_retained"] = int(analysis_id is not None)
                context.close()
                browser.close()
    except Exception as error:
        report.update(status="failed", workflow_status="failed", error_type=type(error).__name__)
    finally:
        report["page_errors"], report["blocked_api_requests"], report["blocked_external_requests"] = errors, blocked, unexpected_external
        report["api_requests_checked_for_absent_credentials"] = credential_checks
        report["elapsed_seconds"] = round(perf_counter()-started, 3)
        attempts = [turn.get("server_reported_generation_attempts") for turn in report["turns"]]
        repairs = [turn.get("server_reported_schema_repair_attempts") for turn in report["turns"]]
        report["server_reported_total_generation_attempts"] = sum(attempts) if attempts and all(type(value) is int for value in attempts) else None
        report["server_reported_repair_attempts"] = sum(repairs) if repairs and all(type(value) is int for value in repairs) else None
        payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
        if owned_sid:
            payload = payload.replace(owned_sid, "[owned-session-redacted]")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(payload+"\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "phase": report["phase"], "report": report_path.relative_to(ROOT).as_posix(),
                          "counters": report["counters"], "new_broker_requests": 0,
                          "server_reported_total_generation_attempts": report["server_reported_total_generation_attempts"]}, ensure_ascii=False))
    return 0 if report["status"] == "passed_limited" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Allow one saved-archive replay, one expert search and two real UI model turns, at most four generations; no IB connection")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    if not args.live:
        parser.print_help()
        print("No --live: zero external requests. Browser, HTTP, broker and models were not started; reports unchanged.")
        return 0
    base = args.base.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path or parsed.query or parsed.fragment or parsed.username:
        parser.error("--base must be a loopback HTTP origin")
    return run(base)


if __name__ == "__main__":
    raise SystemExit(main())
