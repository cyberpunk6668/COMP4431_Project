"""Opt-in, bounded real Edge/DeepSeek project-manual acceptance.

Default: print the dry-run policy without HTTP, browsers, reports or database
changes. --live requires a separately started isolated backend on :8016.
Only the sidebar session-list GET is a privacy fixture. Two real UI chat
turns may request one topic-selection generation each, with no script retry.
The model does not freely generate the manual steps. No broker fetch, desktop
connection change, existing-session read or deletion is performed.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import UUID


BASE = "http://127.0.0.1:8016"
QUESTIONS = ("期权分析怎么用？", "下一步")
SOURCE_FILES = (
    "app/main.py", "app/project_help.py", "app/project_help_chat.py",
    "app/service.py", "app/storage.py", "data/project_help.json",
    "web/app.js", "web/companion/messages.js", "web/help.html", "web/help.js",
    "scripts/check_project_help_live_v16.py",
)


def safe_text(value):
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{6,}|\bBearer\s+[^\s\"']+",
                  "[credential-redacted]", str(value), flags=re.I)
    return re.sub(r"\b(?:DU|U|F|I)[0-9]{5,12}\b", "[account-redacted]", text)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False).encode("utf-8")).hexdigest()


def sha_files(root):
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in SOURCE_FILES}


def utc_stamp(value):
    assert isinstance(value, str), "Saved message time missing"
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0
    return value


def audit_reply(reply, entries, manual_sha, turn_index):
    """Compare every displayed instruction to the separately read HTTP manual."""
    assert reply.get("mode") == "project-help", "Reply did not use project-help"
    context = reply.get("project_help")
    assert isinstance(context, dict) and context.get("intent") == "project_help"
    assert context.get("current_version") == 16 and context.get("manual_version") == "16.0"
    assert context.get("known") is True
    assert context.get("followup_used") is (turn_index == 1)
    ids = context.get("topic_ids")
    assert isinstance(ids, list) and 1 <= len(ids) <= 4 and len(set(ids)) == len(ids)
    assert set(ids) <= entries.keys() and "help.options" in ids
    topics = [entries[key] for key in ids]
    assert context.get("topics") == topics, "Selected manual entries changed"
    steps = [step for topic in topics for step in topic["steps"]]
    restrictions = [item for topic in topics for item in topic["restrictions"]]
    links, seen = [], set()
    for topic in topics:
        for link in topic["links"]:
            if link["url"] not in seen:
                seen.add(link["url"])
                links.append(link)
    assert context.get("steps") == steps and context.get("restrictions") == restrictions
    assert context.get("links") == links
    sections = []
    for topic in topics:
        lines = ["## " + topic["title"], topic["summary"] + " [" + topic["id"] + "]"]
        lines.extend(f"{i}. {step}" for i, step in enumerate(topic["steps"], 1))
        lines.append("使用边界：")
        lines.extend("- " + item for item in topic["restrictions"])
        sections.append("\n\n".join(lines))
    expected_answer = "\n\n".join(sections)
    assert reply.get("answer") == expected_answer, "Answer is not the exact reviewed manual text"
    selector = context.get("selector", {})
    assert selector.get("engine") == "deepseek" and selector.get("status") == "validated"
    assert selector.get("requested_engine") == "deepseek"
    assert selector.get("generation_attempts") == 1
    assert reply.get("generation_attempts") == 1 and reply.get("schema_repair_attempts") == 0
    assert not reply.get("warning"), "Accepted live selector unexpectedly warned"
    assert not reply.get("analysis_context"), "Tutorial was contaminated by financial analysis context"
    grounding = context.get("grounding", {})
    assert grounding.get("manual_sha256") == manual_sha
    assert grounding.get("uses_model_for_selection") is True
    assert grounding.get("model_selection_validated") is True
    assert grounding.get("model_generated_steps") is False
    assert grounding.get("reads_source_contents_for_answers") is False
    sources = reply.get("sources")
    assert isinstance(sources, list) and [source.get("id") for source in sources] == ids
    for source, topic in zip(sources, topics):
        assert source.get("id") in entries and source.get("url") == "/help#" + topic["id"]
        assert source.get("title") == topic["title"] and source.get("snippet") == topic["summary"]
        assert source.get("category") == "project_help" and source.get("manual_version") == "16.0"
    return {
        "topic_ids": ids, "mode": reply["mode"], "selector": selector,
        "manual_version": context["manual_version"], "manual_sha256": manual_sha,
        "answer_sha256": digest(expected_answer), "steps_exactly_equal_http_manual": True,
        "full_answer_exactly_equal_http_manual": True, "followup_used": context["followup_used"],
        "financial_analysis_context_absent": True, "source_urls": [source["url"] for source in sources],
        "source_drift": grounding.get("source_drift", []),
    }


def run(base):
    assert base == BASE, "Only the explicitly isolated :8016 backend is allowed"
    root = Path(__file__).resolve().parents[1]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = root / "reports/project_help_live_v16.json"
    if target.exists():
        target = target.with_stem(target.stem + "-" + stamp)
    shots = root / "reports/screenshots/project-help-live-v16" / stamp
    report = {
        "checked_at": datetime.now(UTC).isoformat(), "status": "running", "phase": "preflight",
        "scope": "Actual Edge headless workspace; real DeepSeek selects reviewed topic IDs. Local manual supplies all steps.",
        "base": base, "questions": list(QUESTIONS), "financial_and_chat_responses_mocked": False,
        "privacy_fixture": "Only browser GET /api/sessions is fulfilled with an empty list; no existing session details are read.",
        "model_budget": {"ui_turns": 2, "maximum_generations": 2, "maximum_schema_repairs": 0},
        "automatic_retries": 0, "new_broker_requests": 0,
        "zero_broker_basis": "Only saved-archive replay and project-help requests; browser guard rejects collection actions. No independent socket/billing instrumentation in this script.",
        "call_count_scope": "Server-reported generation attempts on two script-owned real UI turns; no independent provider billing trace.",
        "counters": {"ui_chat_http_requests": 0, "confirmed_deepseek_selectors": 0, "generations": 0, "schema_repairs": 0},
        "turns": [], "received_reply_metadata": [], "checks": [], "screenshots": [],
        "cleanup_policy": "Close only owned browser. Retain owned session and immutable archive in isolated DB. Never modify companion connection or stop backend.",
    }
    browser = None
    sid = None
    try:
        # Optional dependencies are intentionally imported only after --live;
        # dependency failures are retained like any other opted-in failure.
        import httpx
        from playwright.sync_api import expect, sync_playwright

        report["source_sha256"] = sha_files(root)
        manual_sha = report["source_sha256"]["data/project_help.json"]
        with httpx.Client(base_url=base, timeout=30, follow_redirects=False, trust_env=False) as api, sync_playwright() as pw:
            def request(method, path, **kwargs):
                # No unbounded session-list GET or existing-record scan is permitted.
                assert not (method == "GET" and path.split("?")[0] == "/api/sessions")
                if path.startswith("/api/sessions/"):
                    assert sid is not None and path.split("?")[0] in {f"/api/sessions/{sid}", f"/api/sessions/{sid}/analysis"}
                response = api.request(method, path, **kwargs)
                assert response.is_success, f"Owned acceptance API HTTP {response.status_code}"
                return response.json()

            health = request("GET", "/api/health")
            assert health.get("application") == "FinPilot" and health.get("version") == "16.0.0"
            assert health.get("mode") == "deepseek", "Server is not configured for live DeepSeek"
            catalogue = request("GET", "/api/project-help?language=zh")
            assert catalogue.get("manual_version") == "16.0" and catalogue.get("current_version") == 16
            entries = {}
            for listed in catalogue["topics"]:
                key = listed["id"]
                assert re.fullmatch(r"help\.[a-z_]+", key) and key not in entries
                entries[key] = request("GET", "/api/project-help/topics/" + key + "?language=zh")
                assert entries[key] == listed
            assert "help.options" in entries and "help.boundaries" in entries
            unknown = entries["help.boundaries"]
            assert unknown.get("known") is False
            report["unknown_entry_read"] = {
                "topic_id": "help.boundaries", "known": False, "model_requests": 0,
                "scope": "Read-only HTTP entry check only; not a negative unknown-question chat-routing test.",
            }
            report["phase"] = "archive_replay_no_gateway"
            record = request("POST", "/api/options/history/sample?language=zh")
            assert record.get("analysis_kind") == "historical_options"
            assert record.get("source", {}).get("kind") == "ibkr_historical"
            assert record["source"].get("verified") is True
            assert re.fullmatch(r"[0-9a-f]{64}", record["source"].get("archive_sha256", ""))
            analysis_id = record["analysis_id"]
            assert UUID(analysis_id).version == 4
            archive_fingerprint = digest(record)
            report["archive"] = {
                "analysis_id": analysis_id, "symbol": record.get("symbol"), "expiry": record.get("expiry"),
                "period": record.get("period"), "archive_sha256": record["source"]["archive_sha256"],
                "this_run_new_broker_requests": 0, "scope": "Replay of the existing saved IBKR archive, not a new capture.",
            }
            sid = request("POST", "/api/sessions", json={"title": "v16 owned project-help real selector acceptance"})["id"]
            assert UUID(sid).version == 4
            report["owned_session_id"] = sid
            request("PUT", f"/api/sessions/{sid}/analysis", json={"analysis_id": analysis_id})
            assert request("GET", f"/api/sessions/{sid}")["messages"] == []
            browser = pw.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="zh-CN", reduced_motion="reduce")
            guard_failures, page_errors, requests_seen = [], [], []

            def intercept(route):
                req = route.request
                parsed = urlsplit(req.url)
                if f"{parsed.scheme}://{parsed.netloc}" != base:
                    # Avoid external font/media requests and screenshots of non-owned pages.
                    return route.abort()
                path = parsed.path
                requests_seen.append({"method": req.method, "path": path})
                if path == "/api/sessions" and req.method == "GET":
                    return route.fulfill(json={"sessions": []})
                reason = None
                if path.startswith("/api/sessions/") and path != f"/api/sessions/{sid}":
                    reason = "Browser tried a non-owned or mutating session endpoint"
                elif path.startswith("/api/options/") and path != f"/api/options/analyses/{analysis_id}":
                    reason = "Browser tried a broker/options action during a tutorial"
                elif req.method not in {"GET", "HEAD"}:
                    if path != "/api/chat" or req.method != "POST":
                        reason = "Browser tried an unexpected state-changing endpoint"
                    else:
                        body = req.post_data_json
                        index = report["counters"]["ui_chat_http_requests"]
                        if index >= 2 or not isinstance(body, dict) or body.get("session_id") != sid or body.get("message") != QUESTIONS[index] or body.get("engine") != "deepseek" or body.get("language") != "zh" or ("analysis_id" in body and body["analysis_id"] != analysis_id):
                            reason = "Browser chat exceeded the exact owned two-turn budget"
                        else:
                            report["counters"]["ui_chat_http_requests"] += 1
                if reason:
                    guard_failures.append(reason)
                    return route.abort()
                return route.continue_()

            context.route("**/*", intercept)
            page = context.new_page()
            page.on("pageerror", lambda error: page_errors.append(safe_text(error)))
            page.goto(base + "/workspace?session=" + sid, wait_until="domcontentloaded")
            expect(page.locator("#message-input")).to_be_enabled()
            assert page.locator(".session-open").count() == 0
            assert report["counters"]["ui_chat_http_requests"] == 0
            report["checks"].append("startup_manual_reads_archive_replay_do_not_generate")
            shots.mkdir(parents=True)
            for index, question in enumerate(QUESTIONS):
                report["phase"] = f"ui_turn_{index + 1}"
                expect(page.locator("#message-input")).to_be_enabled()
                page.locator("#message-input").fill(question)
                with page.expect_response(lambda r: urlsplit(r.url).path == "/api/chat" and r.request.method == "POST", timeout=150000) as pending:
                    page.locator("#send-button").click()
                response = pending.value
                assert response.status == 200, f"Real UI chat HTTP {response.status}; no retry attempted"
                reply = response.json()
                report["received_reply_metadata"].append({
                    "mode": reply.get("mode"), "warning": reply.get("warning"),
                    "generation_attempts": reply.get("generation_attempts"),
                    "schema_repair_attempts": reply.get("schema_repair_attempts"),
                    "selector": reply.get("project_help", {}).get("selector"),
                })
                report["counters"]["generations"] += int(reply.get("generation_attempts") or 0)
                report["counters"]["schema_repairs"] += int(reply.get("schema_repair_attempts") or 0)
                assert report["counters"]["generations"] <= 2 and report["counters"]["schema_repairs"] == 0
                turn = audit_reply(reply, entries, manual_sha, index)
                report["turns"].append(turn)
                report["counters"]["confirmed_deepseek_selectors"] += 1
                assert reply.get("session_id") == sid and reply.get("active_analysis", {}).get("analysis_id") == analysis_id
                card = page.locator("#chat-messages > .message.assistant").last.locator(".project-help-card")
                expect(card).to_be_visible()
                expect(card).to_have_attribute("data-manual-version", "16.0")
                assert card.locator(".project-help-steps > li").all_text_contents() == reply["project_help"]["steps"]
                expect(card.locator(".project-help-method")).to_contain_text("DeepSeek")
                expect(card.locator(".project-help-method")).to_contain_text("操作步骤不由模型自由生成")
                expect(card.locator(".project-help-provenance")).to_contain_text("16.0")
                expect(card.locator(".project-help-provenance")).to_contain_text("主题匹配生成尝试: 1")
                assert page.locator(".session-open").count() == 0
                assert not guard_failures, guard_failures
                # Local non-shared UI initially appends unsaved view models. Reload
                # the same owned URL to verify authoritative persisted message IDs.
                page.reload(wait_until="domcontentloaded")
                expect(page.locator("#message-input")).to_be_enabled()
                expected_count = (index + 1) * 2
                expect(page.locator("#chat-messages > .message[data-message-id]")).to_have_count(expected_count)
                saved = request("GET", f"/api/sessions/{sid}")
                assert saved.get("active_analysis_id") == analysis_id
                messages = saved["messages"]
                ids = [message["id"] for message in messages]
                assert len(ids) == expected_count and len(set(ids)) == expected_count
                assert [message["role"] for message in messages] == ["user", "assistant"] * (index + 1)
                for pos in range(index + 1):
                    user, assistant = messages[pos * 2:pos * 2 + 2]
                    assert user["content"] == QUESTIONS[pos]
                    audit_reply({**assistant, "answer": assistant["content"],
                                 "generation_attempts": assistant.get("project_help", {}).get("selector", {}).get("generation_attempts"),
                                 "schema_repair_attempts": 0}, entries, manual_sha, pos)
                    utc_stamp(user["created_at"])
                    utc_stamp(assistant["created_at"])
                assert messages[-1]["project_help"] == reply["project_help"]
                assert messages[-1]["sources"] == reply["sources"]
                turn["persisted_message_ids"] = ids
                turn["saved_at_utc"] = messages[-1]["created_at"]
                turn["time_scope"] = "Message saved time and manual version, not a market data timestamp."
                restored = page.locator("#chat-messages > .message.assistant").last
                assert restored.locator(".project-help-card .project-help-steps > li").all_text_contents() == reply["project_help"]["steps"]
                assert restored.locator(".message-analysis-context").count() == 0
                source = restored.locator(".project-help-sources a").first
                expected_url = "/help#" + reply["project_help"]["topic_ids"][0]
                expect(source).to_have_attribute("href", expected_url)
                with page.expect_popup() as opened:
                    source.click()
                manual_page = opened.value
                manual_page.wait_for_url(base + expected_url)
                topic_card = manual_page.locator('[id="' + reply["project_help"]["topic_ids"][0] + '"]')
                expect(topic_card).to_be_visible()
                assert topic_card.locator(".project-help-steps > li").all_text_contents() == entries[reply["project_help"]["topic_ids"][0]]["steps"]
                manual_page.close()
                restored.scroll_into_view_if_needed()
                shot = shots / f"turn-{index + 1}-real-selector-local-manual.png"
                page.screenshot(path=str(shot), animations="disabled", full_page=False)
                report["screenshots"].append(shot.relative_to(root).as_posix())
                report["checks"].append(f"turn_{index + 1}_exact_manual_safe_sources_binding_persistence_real_card_link")
                assert not guard_failures and not page_errors
            assert report["counters"] == {"ui_chat_http_requests": 2, "confirmed_deepseek_selectors": 2, "generations": 2, "schema_repairs": 0}
            assert digest(request("GET", "/api/options/analyses/" + analysis_id)) == archive_fingerprint
            report["checks"].extend(["immutable_archive_unchanged", "two_turns_four_unique_messages", "no_companion_connection_mutation", "no_financial_context_in_tutorials"])
            report["browser_api_request_counts"] = {
                f"{method} {path}": sum(1 for item in requests_seen if item == {"method": method, "path": path})
                for method, path in sorted({(item["method"], item["path"]) for item in requests_seen if item["path"].startswith("/api/")})
            }
            report["page_errors"] = page_errors
            report["guard_failures"] = guard_failures
            browser.close()
            browser = None
            report["status"], report["phase"] = "passed", "complete"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = safe_text(error)
    finally:
        if browser is not None and browser.is_connected():
            try:
                browser.close()
            except Exception as error:
                report["browser_cleanup_error"] = safe_text(error)
        report["owned_records_retained"] = sid is not None
        report["backend_lifecycle_managed_by_script"] = False
        report["companion_connection_modified_by_script"] = False
        try:
            after = sha_files(root)
            report["source_sha256_at_end"] = after
            report["source_unchanged_during_run"] = after == report.get("source_sha256")
        except Exception as error:
            report["source_hash_error"] = safe_text(error)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "phase": report["phase"],
                      "report": str(target), "counters": report["counters"],
                      "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--base", choices=[BASE], default=BASE)
    args = parser.parse_args()
    if not args.live:
        print("Dry run: zero HTTP, browser, model, broker, report or database actions. --live permits two real topic-selection generations on isolated :8016.")
    else:
        raise SystemExit(run(args.base))
