"""Opt-in Edge acceptance of real UI refresh and continuous IBKR analysis chat.

Without --live: zero external requests, including health checks. With --live:
one actual AAPL delayed initial collection, one refresh clicked in the real UI,
and one follow-up sent in the real UI. Options/chat responses are never mocked.
Only the sidebar session-list GET is privacy-filtered to this script's session.
The model may perform its server-side bounded format repair; report the attempt
counts returned by the server instead of claiming to observe provider calls.
Only the owned session is deleted. Immutable analyses remain on the server.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
from time import perf_counter
from urllib.parse import urlsplit
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_options_chat_live_v10 import fingerprint, safe_text
from scripts.check_options_refresh_live_v11 import validate_answer, validate_comparison
from scripts.check_ibkr_refresh_live_v12 import audit_capture


REPORT = ROOT / "reports/ibkr_browser_live_v12.json"
SHOTS = ROOT / "reports/screenshots/options-v12-live"
FOLLOWUP = "这个变化能说明市场转向吗？请结合前后数据与局限解释。"
DRAFT = "这是刷新验收保留的临时草稿，不发送。"


def read_response(response, report, expected=200):
    if response.status != expected:
        code = None
        try:
            detail = response.json().get("detail")
            if isinstance(detail, dict):
                candidate = detail.get("code")
                if isinstance(candidate, str) and re.fullmatch(r"[a-z0-9_]{1,80}", candidate):
                    code = candidate
                if isinstance(detail.get("diagnostics"), dict):
                    report.setdefault("provider_diagnostics", []).append(detail["diagnostics"])
        except (ValueError, AttributeError):
            pass
        raise AssertionError(f"HTTP {response.status} for owned acceptance request; code={code}")
    return response.json()


def reply_summary(reply, previous, current, changes, *, refresh):
    summary = validate_answer(reply, previous, current, changes, require_change=refresh)
    attempts, repairs = reply.get("generation_attempts"), reply.get("schema_repair_attempts")
    if attempts is not None:
        assert type(attempts) is int and 1 <= attempts <= 2
    if repairs is not None:
        assert type(repairs) is int and 0 <= repairs <= 1
        if attempts is not None:
            assert repairs == attempts - 1
    summary.update(server_reported_generation_attempts=attempts,
                   server_reported_schema_repair_attempts=repairs)
    return summary


def run(base):
    from playwright.sync_api import expect, sync_playwright

    report = {
        "checked_at": datetime.now(UTC).isoformat(), "status": "running", "workflow_status": "running",
        "scope": "Real Edge desktop UI against the local server; actual IBKR AAPL collection/refresh requested as delayed and two model chat turns. No options/chat response mocking. Full quotes require complete timestamped BBO in both captures; partial fields remain limited.",
        "privacy": "Fresh browser context. Only the session-list GET is replaced with owned-session metadata; all financial responses are real. Screenshots mask the session list. No credentials, account fields, session IDs, prompts or protocol payloads are recorded.",
        "transport": "Actual loopback HTTP, desktop Edge 1440x1000",
        "base": base, "automatic_script_retries": 0,
        "provider_call_count_note": "This browser test observes two requested model turns. Provider-internal calls are not directly visible; returned generation/repair attempts are reported separately.",
        "captures": [], "turns": [], "checks": [], "screenshots": [],
    }
    counters = {"initial_analysis_http_requests": 0, "refresh_ui_http_requests": 0,
                "followup_ui_http_requests": 0, "confirmed_deepseek_replies": 0}
    report["counters"] = counters
    started = perf_counter()
    owned_sid, old_id, new_id, context, page = None, None, None, None, None
    errors, blocked = [], []
    try:
        with sync_playwright() as runner:
            browser = runner.chromium.launch(channel="msedge", headless=True)
            report["browser"] = {"channel": "msedge", "version": browser.version, "headless": True,
                                 "viewport": {"width": 1440, "height": 1000}}
            context = browser.new_context(base_url=base, viewport={"width": 1440, "height": 1000},
                                          reduced_motion="reduce", timezone_id="Asia/Shanghai")
            request = context.request
            try:
                report["phase"] = "health"
                health = read_response(request.get(base + "/api/health", timeout=10000), report)
                assert health.get("version") == "12.0.0", "Restarted v12 server is required"
                assert health.get("mode") in {"deepseek", "online"}, "Server is not configured for cloud chat"
                report.update(app_version=health["version"], model=health.get("model"))
                report["phase"] = "initial_actual_capture"
                counters["initial_analysis_http_requests"] += 1
                previous = read_response(request.post(base + "/api/options/analyze", data={
                    "symbol": "AAPL", "market_data_type": 3, "radius": 1, "interpret_with_llm": False, "language": "zh",
                }, timeout=300000), report)
                old_id = previous["analysis_id"]
                assert UUID(old_id).version == 4
                old_hash = fingerprint(previous)
                report["old_analysis_id"], report["old_fingerprint"] = old_id, old_hash
                report["captures"].append(audit_capture(previous))
                own = read_response(request.post(base + "/api/sessions", data={"title": "IBKR v12 owned browser acceptance"}, timeout=10000), report, 201)
                owned_sid = own["id"]
                read_response(request.put(f"{base}/api/sessions/{owned_sid}/analysis", data={"analysis_id": old_id}, timeout=10000), report)
                refresh_path = f"/api/sessions/{owned_sid}/analysis/refresh"
                own_row = {key: own[key] for key in ("id", "title", "created_at", "updated_at")}

                def guard(route):
                    incoming = route.request
                    path = urlsplit(incoming.url).path
                    if incoming.method == "GET" and path == "/api/sessions":
                        route.fulfill(json={"sessions": [own_row]})
                        return
                    if incoming.method == "POST" and path == refresh_path:
                        body = incoming.post_data_json
                        allowed = (counters["refresh_ui_http_requests"] == 0 and body == {
                            "analysis_id": old_id, "language": "zh", "engine": "deepseek"})
                        if allowed:
                            counters["refresh_ui_http_requests"] += 1
                            route.continue_()
                            return
                    elif incoming.method == "POST" and path == "/api/chat":
                        body = incoming.post_data_json
                        allowed = (counters["followup_ui_http_requests"] == 0 and new_id is not None
                                   and body.get("session_id") == owned_sid and body.get("analysis_id") == new_id
                                   and body.get("engine") == "deepseek" and body.get("language") == "zh"
                                   and body.get("message") == FOLLOWUP)
                        if allowed:
                            counters["followup_ui_http_requests"] += 1
                            route.continue_()
                            return
                    elif incoming.method == "GET" and (path in {"/api/health", "/api/models", "/api/options/status"}
                          or path == f"/api/sessions/{owned_sid}" or path == f"/api/sessions/{owned_sid}/export"
                          or path.startswith("/api/options/analyses/")):
                        route.continue_()
                        return
                    blocked.append({"method": incoming.method,
                                    "path": re.sub(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", "[owned-id]", path, flags=re.I)})
                    route.abort()

                context.route("**/api/**", guard)
                context.add_init_script("""localStorage.setItem('finpilot-session', %s);
                    localStorage.setItem('finpilot-language','zh');
                    localStorage.setItem('finpilot-engine','deepseek');""" % json.dumps(owned_sid))
                page = context.new_page()
                page.set_default_timeout(15000)
                page.on("pageerror", lambda error: errors.append(safe_text(error)))
                page.goto(base + "/workspace", wait_until="domcontentloaded")
                card = page.locator("#analysis-context-card")
                editor = page.locator("#message-input")
                expect(card).to_be_visible()
                expect(card).to_have_attribute("data-analysis-id", old_id)
                expect(card).to_contain_text("AAPL")
                expect(page.locator("#model-select")).to_have_value("deepseek")
                editor.fill(DRAFT)
                report["phase"] = "ui_refresh"
                with page.expect_response(lambda value: value.request.method == "POST" and urlsplit(value.url).path == refresh_path,
                                          timeout=300000) as response:
                    card.locator(".analysis-refresh-button").click()
                refreshed = read_response(response.value, report)
                assert refreshed.get("refreshed") is True and refreshed.get("user_message")
                report["phase"] = "refresh_capture_audit"
                new_id = refreshed["analysis_context"]["analysis_id"]
                assert new_id != old_id and UUID(new_id).version == 4
                report["new_analysis_id"] = new_id
                current = read_response(request.get(base + "/api/options/analyses/" + new_id, timeout=15000), report)
                report["captures"].append(audit_capture(current))
                changes = validate_comparison(previous, current)
                report["comparison_status"] = current["refresh_comparison"]["status"]
                report["local_changes"] = [{"id": key, **{field: item[field] for field in (
                    "before", "after", "delta", "unit", "delta_unit", "status", "reason", "direction")}} for key, item in changes.items()]
                summary = {"mode": refreshed.get("mode"), "warning": refreshed.get("warning"),
                           "answer_excerpt": safe_text(refreshed.get("answer", ""))[:3500],
                           "server_reported_generation_attempts": refreshed.get("generation_attempts"),
                           "server_reported_schema_repair_attempts": refreshed.get("schema_repair_attempts")}
                report["turns"].append(summary)
                report["phase"] = "refresh_reply_validation"
                summary.update(reply_summary(refreshed, previous, current, changes, refresh=True))
                counters["confirmed_deepseek_replies"] += 1
                report["phase"] = "refresh_ui_render_validation"
                expect(card).to_have_attribute("data-analysis-id", new_id)
                expect(editor).to_be_enabled()
                expect(editor).to_have_value(DRAFT)
                report["draft_preserved_during_refresh"] = True
                expect(page.locator("#chat-messages .message.assistant")).to_have_count(1)
                expect(page.locator("#chat-messages .message.assistant .message-mode")).to_have_text("DeepSeek")
                comparison = page.locator("#chat-messages .analysis-refresh-comparison").first
                expect(comparison).to_be_visible()
                expect(comparison).to_have_attribute("data-status", current["refresh_comparison"]["status"])
                assert comparison.locator(".analysis-change-metric").count() == len(changes)
                for identifier, metric in changes.items():
                    article = comparison.locator(f'[data-change-id="{identifier.removeprefix("change.")}"]')
                    expect(article).to_have_attribute("data-status", metric["status"])
                history = card.locator(".analysis-history")
                history.locator("summary").click()
                expect(history.locator(".analysis-history-entry")).to_have_count(2)
                expect(history.locator(".analysis-history-entry[data-current='true']")).to_have_attribute("data-analysis-id", new_id)
                expect(history.locator(".analysis-history-entry[data-current='false']")).to_have_attribute("data-analysis-id", old_id)
                report["ui_history_count_after_refresh"] = 2
                report["comparison_dom_status_matches_local"] = True
                SHOTS.mkdir(parents=True, exist_ok=True)
                comparison.scroll_into_view_if_needed()
                shot = SHOTS / "ibkr-refresh-desktop.png"
                page.screenshot(path=str(shot), animations="disabled", mask=[page.locator("#session-list")])
                report["screenshots"].append(shot.relative_to(ROOT).as_posix())
                assert read_response(request.get(base + "/api/options/analyses/" + old_id, timeout=15000), report) == previous
                report["old_snapshot_unchanged_after_refresh"] = True
                report["phase"] = "ui_followup"
                editor.fill(FOLLOWUP)
                with page.expect_response(lambda value: value.request.method == "POST" and urlsplit(value.url).path == "/api/chat",
                                          timeout=300000) as response:
                    page.locator("#send-button").click()
                followup = read_response(response.value, report)
                summary = {"mode": followup.get("mode"), "warning": followup.get("warning"),
                           "answer_excerpt": safe_text(followup.get("answer", ""))[:3500],
                           "server_reported_generation_attempts": followup.get("generation_attempts"),
                           "server_reported_schema_repair_attempts": followup.get("schema_repair_attempts")}
                report["turns"].append(summary)
                report["phase"] = "followup_reply_validation"
                summary.update(reply_summary(followup, previous, current, changes, refresh=False))
                counters["confirmed_deepseek_replies"] += 1
                report["phase"] = "followup_ui_and_persistence_validation"
                expect(editor).to_be_enabled()
                expect(editor).to_have_value("")
                expect(card).to_have_attribute("data-analysis-id", new_id)
                expect(page.locator("#chat-messages .message.assistant")).to_have_count(2)
                assert page.locator("#chat-messages .message.assistant .message-mode").all_text_contents() == ["DeepSeek", "DeepSeek"]
                expect(page.locator("#chat-messages .message-analysis-context")).to_have_count(2)
                assert page.locator("#chat-messages .message-analysis-context").evaluate_all("items => items.every(item => item.dataset.analysisId === %s)" % json.dumps(new_id))
                expect(page.locator("#chat-messages .analysis-refresh-comparison")).to_have_count(2)
                for container in (read_response(request.get(f"{base}/api/sessions/{owned_sid}", timeout=15000), report),
                                  read_response(request.get(f"{base}/api/sessions/{owned_sid}/export", timeout=15000), report)):
                    assert container["active_analysis_id"] == new_id
                    assert [item["analysis_id"] for item in container["analysis_history"]] == [new_id, old_id]
                    assert [item["is_current"] for item in container["analysis_history"]] == [True, False]
                    assert len(container["messages"]) == 4
                    assert container["messages"][0]["content"] == refreshed["user_message"]
                    assert container["messages"][2]["content"] == FOLLOWUP
                    for index, reply in enumerate((refreshed, followup)):
                        assert container["messages"][2 * index + 1]["analysis_context"] == reply["analysis_context"]
                assert fingerprint(read_response(request.get(base + "/api/options/analyses/" + old_id, timeout=15000), report)) == old_hash
                assert read_response(request.get(base + "/api/options/analyses/" + new_id, timeout=15000), report) == current
                assert counters == {"initial_analysis_http_requests": 1, "refresh_ui_http_requests": 1,
                                    "followup_ui_http_requests": 1, "confirmed_deepseek_replies": 2}
                assert not errors and not blocked, "Page errors or unexpected API requests occurred"
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                page.locator("#chat-messages .message.assistant").last.scroll_into_view_if_needed()
                shot = SHOTS / "ibkr-followup-desktop.png"
                page.screenshot(path=str(shot), animations="disabled", mask=[page.locator("#session-list")])
                report["screenshots"].append(shot.relative_to(ROOT).as_posix())
                full = all(item["complete_bbo_evidence"] for item in report["captures"])
                attempts = [item["server_reported_generation_attempts"] for item in report["turns"]]
                report.update(status="passed" if full else "passed_limited", workflow_status="passed", phase="complete",
                              market_data_level="full_quotes" if full else "limited", full_quote_validation=full,
                              old_snapshot_unchanged=True, history_count=2, persisted_chat_turns=2,
                              server_reported_total_generation_attempts=sum(attempts) if all(type(value) is int for value in attempts) else None)
                report["checks"] = ["real_options_and_chat_responses", "ui_refresh_button_then_ui_followup",
                                    "draft_preserved", "new_context_and_two_version_history", "old_and_new_json_unchanged",
                                    "local_comparison_values_and_all_citations_verified", "two_deepseek_mode_replies",
                                    "actual_data_level_distinguished_from_full_quotes", "session_export_preserves_context",
                                    "no_pageerror_or_horizontal_overflow", "privacy_filtered_sidebar_and_masked_screenshots"]
            except Exception as error:
                report.update(status="failed", workflow_status="failed", error_type=type(error).__name__)
                if isinstance(error, AssertionError):
                    report["error_code"] = re.sub(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", "[owned-id]", safe_text(error), flags=re.I)[:400]
                if page is not None:
                    try:
                        SHOTS.mkdir(parents=True, exist_ok=True)
                        shot = SHOTS / "ibkr-browser-failed.png"
                        page.screenshot(path=str(shot), animations="disabled", mask=[page.locator("#session-list")])
                        report["screenshots"].append(shot.relative_to(ROOT).as_posix())
                    except Exception:
                        pass
            finally:
                if owned_sid:
                    try:
                        response = request.delete(f"{base}/api/sessions/{owned_sid}", timeout=15000)
                        report["owned_session_removed"] = response.status == 200 and response.json().get("deleted") is True
                    except Exception:
                        report["owned_session_removed"] = False
                    if not report["owned_session_removed"]:
                        report.update(status="failed", workflow_status="failed", cleanup_error="owned_session_cleanup_failed")
                report["owned_immutable_analyses_retained"] = int(old_id is not None) + int(new_id is not None)
                context.close()
                browser.close()
    except Exception as error:
        report.update(status="failed", workflow_status="failed", error_type=type(error).__name__)
    finally:
        attempts = [item.get("server_reported_generation_attempts") for item in report["turns"]]
        report["server_reported_total_generation_attempts"] = sum(attempts) if attempts and all(type(value) is int for value in attempts) else None
        report["page_errors"] = errors
        report["blocked_requests"] = blocked
        report["elapsed_seconds"] = round(perf_counter() - started, 3)
        report["limits"] = list(dict.fromkeys(note for item in report["captures"] for note in item["limitations"]))
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "workflow_status": report["workflow_status"],
                          "market_data_level": report.get("market_data_level"), "report": REPORT.relative_to(ROOT).as_posix(),
                          "counters": counters}, ensure_ascii=False))
    return int(report["status"] not in {"passed", "passed_limited"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Allow two real IBKR captures and two UI model turns, including the server's bounded repair if needed")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    if not args.live:
        parser.print_help()
        print("No --live: zero external requests; the browser and HTTP client were not started.")
        return 0
    base = args.base.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path or parsed.query:
        parser.error("--base must be a loopback HTTP origin")
    return run(base)


if __name__ == "__main__":
    raise SystemExit(main())
