"""Exercise saved-options follow-up in Edge with synthetic API replies only.

Every /api/ request is intercepted; no broker or external model is contacted.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import runpy
from urllib.parse import urlsplit
from uuid import UUID

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
helpers = runpy.run_path(str(ROOT / "scripts/check_options_novice_browser.py"))
fixture = helpers["fixture"]
REPORT = ROOT / "reports/options_chat_browser_v10.json"
SHOTS = ROOT / "reports/screenshots/options-v10"
IDS = {"AAPL": str(UUID(int=101)), "MSFT": str(UUID(int=102))}
BATCH_ID = str(UUID(int=103))


def check(browser, base, width, height):
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(10000)
    errors, calls, chat_calls = [], [], []
    sessions, reports, metadata = {}, {}, {}
    fail_detach = [False]
    captured = (datetime.now(timezone.utc) - timedelta(seconds=95)).isoformat()
    for symbol, identifier in IDS.items():
        report = fixture(symbol, "2030-01-18", "zh")
        report["analysis_id"] = identifier
        report["snapshot"]["received_at"] = captured
        report["snapshot"]["source"] = "ibkr"
        reports[identifier] = report
        metadata[identifier] = {
            "analysis_id": identifier, "source": "ibkr", "captured_at": captured, "completed_at": captured,
            "snapshot_age_seconds": 95, "stale": True, "freshness_threshold_seconds": 30,
            "realtime_guaranteed": False,
            "scopes": [{"id": "g0", "symbol": symbol, "expiry": "2030-01-18", "received_at": captured,
                        "market_data_status": "delayed", "snapshot_age_seconds": 95, "stale": True,
                        "quote_coverage": 1.0, "assessment_status": "descriptive_snapshot", "reason_codes": []}],
            "partial_failures": [], "notice": "Synthetic fixed snapshot.",
        }
    comparison = helpers["build_batch_comparison"]([reports[IDS["AAPL"]], reports[IDS["MSFT"]]], "zh")
    failures = [{"symbol": "MISS", "expiry": None, "code": "ibkr_entitlement_missing"}]
    reports[BATCH_ID] = {"analysis_id": BATCH_ID, "reports": [reports[IDS["AAPL"]], reports[IDS["MSFT"]]],
                         "failures": failures, "comparison": comparison, "completed_at": captured,
                         "interpretation": {"status": "skipped"}}
    reports[BATCH_ID]["plain_brief"] = helpers["build_batch_plain_brief"](reports[BATCH_ID]["reports"], comparison, failures, "zh")
    metadata[BATCH_ID] = deepcopy(metadata[IDS["AAPL"]])
    metadata[BATCH_ID].update(analysis_id=BATCH_ID, partial_failures=failures)
    metadata[BATCH_ID]["scopes"].append({**metadata[IDS["MSFT"]]["scopes"][0], "id": "g1"})
    metadata[IDS["MSFT"]]["captured_at"] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    metadata[IDS["MSFT"]]["scopes"][0]["time_status"] = "future"
    metadata[BATCH_ID]["captured_at"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    metadata[BATCH_ID]["scopes"][0].update(received_at=metadata[BATCH_ID]["captured_at"], time_status="known", stale=False)
    metadata[BATCH_ID]["scopes"][1].update(received_at=None, time_status="missing", stale=True)

    def session_payload(session):
        return {**session, "active_analysis": deepcopy(metadata.get(session["active_analysis_id"]))}

    def respond(route):
        request = route.request
        path = urlsplit(request.url).path
        body = request.post_data_json if request.method in ("POST", "PUT") else None
        calls.append({"method": request.method, "path": path, "body": body})
        if path == "/api/health":
            route.fulfill(json={"status": "ok", "mode": "deepseek", "model": "fixture", "knowledge_documents": 0})
        elif path == "/api/models":
            route.fulfill(json={"default": "deepseek", "models": [{"id": "deepseek", "label": "DeepSeek", "available": True}, {"id": "local", "label": "Local LoRA", "available": True}]})
        elif path == "/api/sessions" and request.method == "GET":
            route.fulfill(json={"sessions": [{"id": item["id"], "title": item["title"]} for item in sessions.values()]})
        elif path == "/api/sessions" and request.method == "POST":
            identifier = "session-" + str(len(sessions) + 1)
            session = {"id": identifier, "title": body.get("title", "Fixture conversation"), "messages": [], "active_analysis_id": None}
            sessions[identifier] = session
            route.fulfill(status=201, json=session_payload(session))
        elif path.startswith("/api/sessions/"):
            parts = path.split("/")
            session = sessions[parts[3]]
            if path.endswith("/analysis"):
                if fail_detach[0] and body["analysis_id"] is None:
                    route.fulfill(status=503, json={"detail": "Synthetic persistence failure"})
                    return
                session["active_analysis_id"] = body["analysis_id"]
                route.fulfill(json={"active_analysis_id": body["analysis_id"], "active_analysis": deepcopy(metadata.get(body["analysis_id"]))})
            else:
                route.fulfill(json=session_payload(session))
        elif path == "/api/options/status":
            route.fulfill(json={"status": "tcp_ready", "enabled": True, "endpoint": "synthetic:4002"})
        elif path == "/api/options/analyze":
            route.fulfill(json=reports[IDS[body["symbol"]]])
        elif path == "/api/options/batch":
            route.fulfill(json=reports[BATCH_ID])
        elif path.startswith("/api/options/analyses/"):
            route.fulfill(json=reports[path.rsplit("/", 1)[1]])
        elif path == "/api/chat":
            chat_calls.append(body)
            identifier = body.get("session_id")
            if not identifier:
                identifier = "session-" + str(len(sessions) + 1)
                sessions[identifier] = {"id": identifier, "title": body["message"], "messages": [], "active_analysis_id": None}
            session = sessions[identifier]
            session["active_analysis_id"] = body["analysis_id"]
            analysis_context = deepcopy(metadata.get(body["analysis_id"]))
            if analysis_context and body["message"] != "普通问题":
                scope = analysis_context["scopes"][0]
                analysis_context["evidence_ids"] = ["g0.volume_put_share"]
                analysis_context["evidence"] = [{"id": "g0.volume_put_share", "label": "看跌成交量占比", "value": 0.6,
                    "unit": "fraction", "scope": "g0", "symbol": scope["symbol"], "expiry": scope["expiry"],
                    "received_at": captured, "market_data_status": "delayed", "description": "Synthetic paired sample. <img src=x onerror=alert(1)>"}]
                for evidence_identifier, label, value, unit in [("g0.positioning_gap", "占比差", 12.5, "percentage_points"),
                        ("g0.volume_total", "合约总数", 1200, "contracts"), ("g0.median_spread", "价差", 3.4, "percent"),
                        ("g0.atm_iv", "缺失数据", None, "fraction")]:
                    analysis_context["evidence"].append({"id": evidence_identifier, "label": label, "value": value, "unit": unit,
                        "scope": "g0", "symbol": scope["symbol"], "expiry": scope["expiry"]})
                answer = "样本中的看跌成交量较多 [g0.volume_put_share]，这不足以预测涨跌。 <img src=x onerror=alert(1)>"
                if body["analysis_id"] == BATCH_ID:
                    analysis_context["evidence"].append({"id": "comparison.volume_gap", "label": "跨项目占比差", "value": 8,
                        "unit": "percentage_points", "scope": "comparison", "scope_ids": ["g0", "g1"]})
                    answer += " 跨项目比较 [comparison.volume_gap]。"
            else:
                analysis_context = None
                answer = "这是一个普通问题的合成回答。"
            message = {"role": "assistant", "content": answer, "sources": [], "mode": "deepseek", "analysis_context": analysis_context}
            session["messages"].extend([{"role": "user", "content": body["message"]}, deepcopy(message)])
            route.fulfill(json={"session_id": identifier, "answer": answer, "sources": [], "mode": "deepseek",
                                "analysis_context": analysis_context, "active_analysis": deepcopy(metadata.get(body["analysis_id"]))})
        else:
            raise AssertionError(f"Unexpected API request: {request.method} {path}")

    context.route("**/api/**", respond)
    page.on("pageerror", lambda error: errors.append(str(error)))

    def open_options():
        if width <= 760:
            page.locator("#mobile-menu").click()
        page.locator("#nav-options").click()
        expect(page.locator("#options-dialog")).to_be_visible()

    def select_session(identifier):
        if width <= 760:
            page.locator("#mobile-menu").click()
        title = sessions[identifier]["title"]
        page.locator(".session-open").filter(has_text=title).click()
        expect(page.locator("#send-button")).to_be_enabled()

    try:
        page.goto(base + "/workspace?view=options", wait_until="domcontentloaded")
        expect(page.locator("#options-dialog")).to_be_visible()
        page.locator("#options-symbol").fill("AAPL")
        page.locator("#options-submit").click()
        expect(page.locator(".options-followup-main")).to_be_visible()
        expect(page.locator(".options-followup-suggestions button")).to_have_count(4)
        page.locator(".options-followup-suggestions button").first.click()
        card = page.locator("#analysis-context-card")
        expect(page.locator("#options-dialog")).not_to_be_visible()
        expect(card).to_have_attribute("data-analysis-id", IDS["AAPL"])
        expect(card).to_contain_text("AAPL")
        expect(card).to_contain_text("2030-01-18")
        expect(card).to_contain_text("延迟行情")
        expect(card).to_contain_text("本地接收时间")
        expect(card).to_contain_text("固定快照")
        expect(card).to_contain_text("30 秒")
        expect(card).to_contain_text("DeepSeek")
        expect(page.locator("#message-input")).to_have_value("这些数据说明什么？")
        assert not chat_calls
        assert len(sessions) == 1
        first_session = "session-1"
        page.locator("#model-select").select_option("local")
        expect(card).to_contain_text("Local LoRA")
        page.locator("#send-button").click()
        expect(page.locator(".message-analysis-context")).to_have_count(1)
        assert chat_calls[-1]["analysis_id"] == IDS["AAPL"] and chat_calls[-1]["engine"] == "local"
        expect(page.locator(".message-analysis-context")).to_contain_text("AAPL")
        expect(page.locator(".message-analysis-context")).to_contain_text("延迟行情")
        expect(page.locator(".message-analysis-context")).to_contain_text("本地接收时间")
        page.locator(".analysis-inline-citation").click()
        evidence = page.locator('.analysis-evidence-card[data-evidence-id="g0.volume_put_share"]')
        expect(evidence).to_be_visible()
        assert evidence.evaluate("el => document.activeElement === el")
        expect(evidence).to_contain_text("60%")
        expect(evidence).to_contain_text("AAPL")
        expect(page.locator('.analysis-evidence-card[data-evidence-id="g0.positioning_gap"]')).to_contain_text("12.5 百分点")
        expect(page.locator('.analysis-evidence-card[data-evidence-id="g0.volume_total"]')).to_contain_text("1,200 份合约")
        expect(page.locator('.analysis-evidence-card[data-evidence-id="g0.median_spread"]')).to_contain_text("3.4%")
        expect(page.locator('.analysis-evidence-card[data-evidence-id="g0.atm_iv"]')).to_contain_text("未提供")
        expect(page.locator(".analysis-inline-citation")).to_have_text("依据 1")
        assert page.locator(".message img").count() == 0
        assert "<img" in page.locator(".message.assistant").inner_text()

        # Reviewing a saved report reads storage only; there is no new market collection.
        before = len(calls)
        card.locator(".analysis-text-button").first.click()
        expect(page.locator("#options-dialog")).to_be_visible()
        expect(page.locator("#options-gateway")).to_contain_text("固定快照")
        expect(page.locator(".options-freshness")).to_contain_text("已保存的行情快照")
        expect(page.locator(".options-freshness")).not_to_contain_text("本机近期")
        assert calls[before:] == [{"method": "GET", "path": "/api/options/analyses/" + IDS["AAPL"], "body": None}]
        page.keyboard.press("Escape")

        # Changing the current report never changes the evidence attached to an old answer.
        open_options()
        page.locator("#options-symbol").fill("MSFT")
        page.locator("#options-submit").click()
        expect(page.locator(".options-followup-main")).to_be_visible()
        page.locator(".options-followup-main").click()
        expect(card).to_have_attribute("data-analysis-id", IDS["MSFT"])
        expect(card).to_contain_text("无法确认这份快照的新鲜度")
        expect(card).not_to_contain_text("快照已超过 30 秒")
        expect(page.locator("#chat-messages .message")).to_have_count(0)
        assert len(chat_calls) == 1 and len(sessions) == 2
        second_session = "session-2"
        page.locator("#send-button").click()
        expect(page.locator(".message-analysis-context")).to_contain_text("MSFT")
        assert chat_calls[-1]["analysis_id"] == IDS["MSFT"]

        # Each conversation restores its own analysis and unsent draft.
        page.locator("#message-input").fill("MSFT draft")
        select_session(first_session)
        expect(card).to_have_attribute("data-analysis-id", IDS["AAPL"])
        expect(page.locator(".message-analysis-context")).to_contain_text("AAPL")
        expect(page.locator(".message-analysis-context")).not_to_contain_text("MSFT")
        page.locator("#message-input").fill("AAPL draft")
        select_session(second_session)
        expect(card).to_have_attribute("data-analysis-id", IDS["MSFT"])
        expect(page.locator("#message-input")).to_have_value("MSFT draft")

        # A persistence error must not falsely claim that context has been removed.
        fail_detach[0] = True
        card.locator(".analysis-remove").click()
        expect(page.locator("#error-banner")).to_be_visible()
        expect(card).to_be_visible()
        assert sessions[second_session]["active_analysis_id"] == IDS["MSFT"]
        fail_detach[0] = False
        card.locator(".analysis-remove").click()
        expect(card).to_be_hidden()
        assert sessions[second_session]["active_analysis_id"] is None
        expect(page.locator(".message-analysis-context")).to_contain_text("MSFT")
        page.reload(wait_until="domcontentloaded")
        expect(page.locator("#send-button")).to_be_enabled()
        expect(card).to_be_hidden()
        expect(page.locator(".message-analysis-context")).to_contain_text("MSFT")
        # The URL intentionally reopens the options dialog on reload.
        if page.locator("#options-dialog").is_visible():
            page.keyboard.press("Escape")
        page.locator("#message-input").fill("普通问题")
        page.locator("#send-button").click()
        expect(page.locator(".message.assistant")).to_have_count(2)
        assert chat_calls[-1]["analysis_id"] is None
        assert page.locator(".message.assistant").last.locator(".message-analysis-context").count() == 0

        # New conversations start without context; switching back restores it.
        if width <= 760:
            page.locator("#mobile-menu").click()
            page.locator("#sidebar-new").click()
        else:
            page.locator("#top-new").click()
        expect(card).to_be_hidden()
        expect(page.locator(".message")).to_have_count(0)
        select_session(first_session)
        expect(card).to_have_attribute("data-analysis-id", IDS["AAPL"])
        expect(page.locator("#message-input")).to_have_value("")  # drafts are kept in memory, not persisted to disk
        page.locator("#language-toggle").click()
        expect(card).to_contain_text("Fixed snapshot")
        expect(card).to_contain_text("Local receipt (UTC)")
        expect(page.locator(".message-analysis-context")).to_contain_text("Options snapshot used for this answer")
        expect(page.locator(".analysis-inline-citation")).to_have_text("Evidence 1")
        if width == 1440:
            open_options()
            page.locator("#options-analysis-mode").select_option("batch")
            page.locator("#options-batch-items").fill("AAPL\nMSFT\nMISS")
            page.locator("#options-submit").click()
            expect(page.locator(".options-followup-main")).to_be_visible()
            before = len(chat_calls)
            page.locator(".options-followup-main").click()
            expect(card).to_have_attribute("data-analysis-id", BATCH_ID)
            expect(card).to_contain_text("AAPL")
            expect(card).to_contain_text("MSFT")
            expect(card).to_contain_text("Some items were unavailable")
            expect(card).to_contain_text("Snapshot freshness could not be confirmed")
            expect(card).not_to_contain_text("Snapshot is over 30 seconds old")
            assert len(chat_calls) == before
            page.locator("#send-button").click()
            expect(page.locator(".message-analysis-context")).to_have_count(1)
            page.locator('.analysis-inline-citation[data-evidence-id="comparison.volume_gap"]').click()
            comparison_card = page.locator('.analysis-evidence-card[data-evidence-id="comparison.volume_gap"]')
            expect(comparison_card).to_be_visible()
            expect(comparison_card).to_contain_text("Cross-item comparison")
            expect(comparison_card).to_contain_text("8 percentage points")
            assert comparison_card.evaluate("el => document.activeElement === el")
        card.scroll_into_view_if_needed()
        if page.locator("#toast").is_visible():
            page.locator("#toast").wait_for(state="hidden", timeout=6000)
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"chat-context-{width}.png"), animations="disabled")
        card.screenshot(path=str(SHOTS / f"context-card-{width}.png"), animations="disabled")
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
        assert card.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        assert not errors, errors
        return {"width": width, "height": height, "page_errors": errors, "synthetic_chat_posts": len(chat_calls),
                "sessions_created": len(sessions), "api_requests": len(calls)}
    except Exception:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"failed-{width}.png"))
        print("DEBUG_SESSIONS", page.locator("#session-list").inner_text(), page.locator("#sidebar").get_attribute("class"), flush=True)
        raise
    finally:
        context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "running", "viewports": [],
              "scope": "All API routes synthetic and intercepted; no brokerage or external model calls. Browser integration checks, not live-market or model-quality validation."}
    try:
        with sync_playwright() as runner:
            browser = runner.chromium.launch(channel="msedge", headless=True)
            for width, height in ((320, 740), (390, 844), (1440, 1000)):
                report["viewports"].append(check(browser, args.base.rstrip("/"), width, height))
            browser.close()
        report["checks"] = ["prominent_followup_and_four_plain_suggestions", "prefill_without_automatic_llm_call",
                            "dedicated_analysis_conversation", "next_send_uses_current_model_and_explicit_analysis_id",
                            "scope_local_receipt_actual_feed_fixed_snapshot_and_staleness", "clickable_local_evidence_and_html_safety",
                            "saved_report_get_without_quote_refresh", "per_reply_context_does_not_follow_current_report",
                            "per_session_binding_and_unsent_drafts", "failed_detach_retains_context", "successful_detach_survives_reload",
                            "ordinary_chat_explicit_null", "new_conversation_context_is_empty", "chinese_and_english", "mobile_containment"]
        report["checks"].extend(["local_evidence_percentage_points_contracts_missing_values", "saved_report_freshness_is_capture_time_only",
                                 "batch_scope_partial_failure_and_comparison_evidence", "missing_or_future_scope_time_is_not_reported_as_30_seconds_old"])
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "report": str(REPORT), "viewports": len(report["viewports"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
