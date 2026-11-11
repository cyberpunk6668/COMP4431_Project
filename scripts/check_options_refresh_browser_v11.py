"""Verify explicit options refresh, immutable history and changes with fixture APIs.

All /api/ routes are intercepted. No IBKR data or external model is requested.
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
REPORT = ROOT / "reports/options_refresh_browser_v11.json"
SHOTS = ROOT / "reports/screenshots/options-v11"
IDS = [str(UUID(int=value)) for value in (301, 302, 303)]
SESSION_ID = "refresh-conversation"


def check(browser, base, width, height):
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
    context.add_init_script(f"localStorage.setItem('finpilot-session', {json.dumps(SESSION_ID)});")
    page = context.new_page()
    page.set_default_timeout(10000)
    calls, refresh_calls, chat_calls, errors, held = [], [], [], [], []
    next_mode = ["hold_success"]
    saved, metadata = {}, {}
    stamps = [(datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat(),
              (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat(), (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()]
    for index, identifier in enumerate(IDS):
        reports = []
        scopes = []
        for symbol in ("AAPL", "MSFT"):
            report = helpers["fixture"](symbol, "2030-01-18", "zh")
            report["snapshot"].update(source="ibkr", received_at=stamps[index])
            reports.append(report)
            scopes.append({"id": "g" + str(len(scopes)), "symbol": symbol, "expiry": "2030-01-18", "received_at": stamps[index],
                           "market_data_status": "delayed", "quote_coverage": 1.0, "time_status": "known", "stale": index == 0})
        comparison = helpers["build_batch_comparison"](reports, "zh")
        saved[identifier] = {"analysis_id": identifier, "reports": reports, "comparison": comparison, "failures": [],
                             "completed_at": stamps[index], "interpretation": {"status": "skipped"},
                             "plain_brief": helpers["build_batch_plain_brief"](reports, comparison, [], "zh")}
        metadata[identifier] = {"analysis_id": identifier, "source": "ibkr", "captured_at": stamps[index], "completed_at": stamps[index],
                                "snapshot_age_seconds": 120 if index == 0 else 0, "stale": index == 0, "scopes": scopes,
                                "freshness_threshold_seconds": 30, "realtime_guaranteed": False, "partial_failures": []}

    def comparison(index, language):
        zh = language == "zh"
        missing = "上一次没有取得这一指标，不能把缺失值当作零。" if zh else "The previous indicator was unavailable; a missing value is not zero."
        changed = "两次行情类型不同，不能直接比较这项变化。" if zh else "The feed types differ; this change cannot be compared directly."
        return {"previous_analysis_id": IDS[index - 1], "previous_captured_at": stamps[index - 1], "current_captured_at": stamps[index],
                "status": "partial", "summary": "仅比较口径相同的样本指标。" if zh else "Only indicators with matching sample definitions are compared.",
                "scopes": [{"id": "s0", "symbol": "AAPL", "expiry": "2030-01-18", "previous_received_at": stamps[index - 1], "received_at": stamps[index],
                            "before_feed": "delayed", "after_feed": "delayed", "status": "partial", "reasons": [], "reason_messages": [],
                            "metrics": [
                                {"id": "volume_put_share", "label": "看跌成交量占比" if zh else "Put share of sampled volume", "before": .6, "after": .7,
                                 "unit": "fraction", "delta": 10, "delta_unit": "percentage_points", "status": "comparable", "reason": None},
                                {"id": "volume_total", "label": "样本成交总数" if zh else "Sample volume total", "before": 1000, "after": 1200,
                                 "unit": "contracts", "delta": 200, "delta_unit": "contracts", "status": "comparable", "reason": None},
                                {"id": "atm_iv", "label": "平值参考波动率" if zh else "ATM reference volatility", "before": None, "after": .3,
                                 "unit": "fraction", "delta": None, "delta_unit": "volatility_points", "status": "incomparable", "reason": "missing_before", "reason_text": missing},
                            ]},
                           {"id": "s1", "symbol": "MSFT", "expiry": "2030-01-18", "previous_received_at": stamps[index - 1], "received_at": stamps[index],
                            "before_feed": "delayed", "after_feed": "frozen", "status": "incomparable", "reasons": ["feed_changed"], "reason_messages": [changed],
                            "metrics": [{"id": "volume_put_share", "label": "看跌成交量占比" if zh else "Put share of sampled volume", "before": .5, "after": .4,
                                         "unit": "fraction", "delta": None, "delta_unit": "percentage_points", "status": "incomparable", "reason": "feed_changed", "reason_text": changed}]}],
                "failures": [], "notice": "Synthetic local comparison."}

    old_context = {**deepcopy(metadata[IDS[0]]), "evidence": [{"id": "g0.volume_put_share", "label": "样本看跌成交量占比", "value": .6, "unit": "fraction", "scope": "g0", "symbol": "AAPL", "expiry": "2030-01-18"}]}
    session = {"id": SESSION_ID, "title": "AAPL / MSFT · 分析追问", "active_analysis_id": IDS[0], "history": [IDS[0]],
               "messages": [{"role": "user", "content": "这些样本说明什么？"}, {"role": "assistant", "content": "这是上一次固定快照的说明 [g0.volume_put_share]。", "mode": "deepseek", "sources": [], "analysis_context": old_context}]}

    def history():
        return [{**deepcopy(metadata[identifier]), "is_current": identifier == session["active_analysis_id"]} for identifier in session["history"]]

    def session_payload():
        return {key: deepcopy(value) for key, value in session.items() if key != "history"} | {"active_analysis": deepcopy(metadata.get(session["active_analysis_id"])), "analysis_history": history()}

    def complete_refresh(route, body, index, fallback=False):
        local_comparison = comparison(index, body["language"])
        identifier = IDS[index]
        metadata[identifier]["refresh_comparison"] = local_comparison
        metadata[identifier]["scopes"][1]["market_data_status"] = "frozen"
        saved[identifier]["refresh_comparison"] = local_comparison
        analysis_context = deepcopy(metadata[identifier])
        metric = local_comparison["scopes"][0]["metrics"][0]
        analysis_context["evidence"] = [{**metric, "id": "change.s0.volume_put_share", "value": metric["after"], "scope": "s0", "symbol": "AAPL", "expiry": "2030-01-18",
                                            "previous_received_at": stamps[index - 1], "received_at": stamps[index], "before_feed": "delayed", "after_feed": "delayed"}]
        analysis_context["evidence_ids"] = ["change.s0.volume_put_share"]
        zh = body["language"] == "zh"
        intent = "重新采集同一范围并解释与上次的变化（服务器记录的意图）。" if zh else "Collect the same scope and explain changes (server-recorded intent)."
        answer = ("这是本地回退说明：" if fallback else "这是变化解释：") + "样本占比由 60% 变为 70% [change.s0.volume_put_share]。这不是涨跌预测。"
        message = {"role": "assistant", "content": answer, "mode": "offline" if fallback else "deepseek", "sources": [],
                   "warning": "options_answer_unavailable" if fallback else None, "analysis_context": analysis_context}
        session["active_analysis_id"] = identifier
        session["history"].insert(0, identifier)
        session["messages"].extend([{"role": "user", "content": intent}, message])
        route.fulfill(json={"session_id": SESSION_ID, "user_message": intent, "answer": answer, "sources": [], "mode": message["mode"],
                            "warning": message["warning"], "analysis_context": analysis_context,
                            "active_analysis": deepcopy(metadata[identifier]), "analysis_history": history()})

    def respond(route):
        request = route.request
        path = urlsplit(request.url).path
        body = request.post_data_json if request.method in ("POST", "PUT") else None
        calls.append({"method": request.method, "path": path, "body": body})
        if path == "/api/health":
            route.fulfill(json={"status": "ok", "mode": "deepseek", "model": "fixture", "knowledge_documents": 0})
        elif path == "/api/models":
            route.fulfill(json={"default": "deepseek", "models": [{"id": "deepseek", "label": "DeepSeek", "available": True}, {"id": "local", "label": "Local LoRA", "available": True}]})
        elif path == "/api/sessions":
            route.fulfill(json={"sessions": [{"id": SESSION_ID, "title": session["title"]}]})
        elif path == f"/api/sessions/{SESSION_ID}/analysis/refresh":
            refresh_calls.append(body)
            assert body["analysis_id"] == session["active_analysis_id"]
            if next_mode[0] == "hold_success":
                held.append((route, body))
            elif next_mode[0] == "all_failed":
                route.fulfill(status=424, json={"detail": {"code": "ibkr_option_data_unavailable", "message": "本次未取得任何期权数据；已保留上一次分析。"}})
            else:
                complete_refresh(route, body, 2, fallback=True)
        elif path == f"/api/sessions/{SESSION_ID}":
            route.fulfill(json=session_payload())
        elif path == f"/api/sessions/{SESSION_ID}/analysis":
            session["active_analysis_id"] = body["analysis_id"]
            route.fulfill(json={"active_analysis_id": body["analysis_id"], "active_analysis": deepcopy(metadata.get(body["analysis_id"]))})
        elif path.startswith("/api/options/analyses/"):
            route.fulfill(json=saved[path.rsplit("/", 1)[1]])
        elif path == "/api/options/status":
            route.fulfill(json={"status": "tcp_ready", "enabled": True, "endpoint": "synthetic:4002"})
        elif path == "/api/options/expirations":
            route.fulfill(json={"source": "ibkr", "symbol": "AAPL", "expirations": ["2030-01-16", "2030-01-18"], "date_kind": "expiration", "timezone": "America/New_York"})
        elif path == "/api/chat":
            chat_calls.append(body)
            answer = "普通问题的本地合成回答。"
            message = {"role": "assistant", "content": answer, "sources": [], "mode": "deepseek", "analysis_context": None}
            session["messages"].extend([{"role": "user", "content": body["message"]}, message])
            route.fulfill(json={"session_id": SESSION_ID, "answer": answer, "sources": [], "mode": "deepseek", "analysis_context": None,
                                "active_analysis": deepcopy(metadata.get(session["active_analysis_id"])), "analysis_history": history()})
        else:
            raise AssertionError(f"Unexpected request: {request.method} {path}")

    context.route("**/api/**", respond)
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(base + "/workspace", wait_until="domcontentloaded")
        card = page.locator("#analysis-context-card")
        expect(card).to_have_attribute("data-analysis-id", IDS[0])
        expect(page.locator("#send-button")).to_be_enabled()
        expect(card.locator(".analysis-refresh-button")).to_have_text("刷新并解释变化")
        expect(card.locator(".analysis-refresh-disclosure")).to_contain_text("草稿不会发送")
        assert not refresh_calls and not chat_calls
        page.locator("#message-input").fill("这是一份尚未发送的草稿。")
        page.locator("#model-select").select_option("local")
        expect(card.locator(".analysis-refresh-disclosure")).to_contain_text("Local LoRA")
        card.locator(".analysis-refresh-button").click()
        expect(card.locator(".analysis-refresh-button")).to_be_disabled()
        expect(page.locator("#analysis-context-status")).to_contain_text("正在重新采集并解释变化")
        expect(page.locator("#message-input")).to_have_value("这是一份尚未发送的草稿。")
        for selector in ("#send-button", "#model-select", "#language-toggle", "#top-new", ".session-open", ".analysis-remove"):
            expect(page.locator(selector)).to_be_disabled()
        card.locator(".analysis-refresh-button").dispatch_event("click")
        page.evaluate("() => refreshAnalysis()")
        assert len(refresh_calls) == 1 and len(held) == 1
        assert refresh_calls[0] == {"analysis_id": IDS[0], "language": "zh", "engine": "local"}
        expect(page.locator(".message.assistant")).to_have_count(1)
        route, body = held.pop()
        complete_refresh(route, body, 1)
        expect(card).to_have_attribute("data-analysis-id", IDS[1])
        expect(page.locator("#send-button")).to_be_enabled()
        expect(page.locator(".message.assistant")).to_have_count(2)
        expect(page.locator(".message.user").last).to_contain_text("服务器记录的意图")
        expect(page.locator("#message-input")).to_have_value("这是一份尚未发送的草稿。")
        assert not chat_calls
        old_reply = page.locator(".message-analysis-context").first
        expect(old_reply).to_have_attribute("data-analysis-id", IDS[0])
        assert old_reply.locator(".analysis-refresh-comparison").count() == 0
        comparison_ui = page.locator(".message-analysis-context").last.locator(".analysis-refresh-comparison")
        expect(comparison_ui).to_be_visible()
        expect(comparison_ui).to_contain_text("本地接收时间")
        share = comparison_ui.locator('[data-change-id="s0.volume_put_share"]')
        expect(share).to_contain_text("60%")
        expect(share).to_contain_text("70%")
        expect(share).to_contain_text("+10 百分点")
        counts = comparison_ui.locator('[data-change-id="s0.volume_total"]')
        expect(counts).to_contain_text("1,000 份合约")
        expect(counts).to_contain_text("+200 份合约")
        absent = comparison_ui.locator('[data-change-id="s0.atm_iv"]')
        expect(absent).to_contain_text("未提供")
        expect(absent).to_contain_text("30%")
        expect(absent).to_contain_text("暂不能直接比较")
        assert absent.locator("dd").first.inner_text() == "未提供"
        incompatible = comparison_ui.locator('[data-change-id="s1.volume_put_share"]')
        expect(incompatible).to_contain_text("两次行情类型不同")
        expect(incompatible).to_contain_text("暂不能直接比较")
        page.locator('.analysis-inline-citation[data-evidence-id="change.s0.volume_put_share"]').click()
        expect(page.locator('.analysis-evidence-card[data-evidence-id="change.s0.volume_put_share"]')).to_be_visible()
        expect(page.locator('.analysis-evidence-card[data-evidence-id="change.s0.volume_put_share"]')).to_contain_text("+10 百分点")

        # History is immutable and reviewing an entry does not change the active binding.
        card.locator(".analysis-history > summary").click()
        entries = card.locator(".analysis-history-entry")
        expect(entries).to_have_count(2)
        expect(entries.first).to_have_attribute("data-analysis-id", IDS[1])
        expect(entries.first).to_have_attribute("data-current", "true")
        before = len(calls)
        entries.last.locator(".analysis-history-view").click()
        expect(page.locator("#options-dialog")).to_be_visible()
        expect(page.locator("#options-gateway")).to_contain_text("固定快照")
        assert calls[before:] == [{"method": "GET", "path": "/api/options/analyses/" + IDS[0], "body": None}]
        assert session["active_analysis_id"] == IDS[1]
        page.keyboard.press("Escape")
        expect(card).to_have_attribute("data-analysis-id", IDS[1])

        # Complete collection failure preserves cards, history, messages and the draft.
        next_mode[0] = "all_failed"
        before_messages = page.locator("#chat-messages").inner_text()
        card.locator(".analysis-refresh-button").click()
        expect(page.locator("#error-banner")).to_contain_text("本次未取得任何期权数据")
        expect(card).to_have_attribute("data-analysis-id", IDS[1])
        assert page.locator("#chat-messages").inner_text() == before_messages
        expect(page.locator("#message-input")).to_have_value("这是一份尚未发送的草稿。")
        expect(card.locator(".analysis-history-entry")).to_have_count(2)

        # A model failure still keeps the newly collected immutable snapshot and local explanation.
        page.locator("#model-select").select_option("deepseek")
        next_mode[0] = "fallback"
        card.locator(".analysis-refresh-button").click()
        expect(card).to_have_attribute("data-analysis-id", IDS[2])
        expect(page.locator(".message.assistant")).to_have_count(3)
        expect(page.locator(".message.assistant").last).to_contain_text("新采集的快照已保留")
        expect(page.locator(".message.assistant").last).to_contain_text("本地回退说明")
        expect(card.locator(".analysis-history-entry")).to_have_count(3)
        assert refresh_calls[-1]["analysis_id"] == IDS[1] and refresh_calls[-1]["engine"] == "deepseek"
        expect(page.locator("#message-input")).to_have_value("这是一份尚未发送的草稿。")
        assert not chat_calls
        expect(old_reply).to_have_attribute("data-analysis-id", IDS[0])

        # Reload restores history and active data. The normal composer remains a separate action.
        page.reload(wait_until="domcontentloaded")
        expect(card).to_have_attribute("data-analysis-id", IDS[2])
        expect(card.locator(".analysis-history-entry")).to_have_count(3)
        page.locator("#message-input").fill("这是一个普通问题。")
        page.locator("#send-button").click()
        expect(page.locator(".message.assistant")).to_have_count(4)
        assert len(chat_calls) == 1 and chat_calls[0]["message"] == "这是一个普通问题。"
        assert chat_calls[0]["analysis_id"] == IDS[2]
        assert page.locator(".message.assistant").last.locator(".message-analysis-context").count() == 0
        page.locator("#language-toggle").click()
        expect(card.locator(".analysis-refresh-button")).to_have_text("Refresh and explain changes")
        expect(card.locator(".analysis-refresh-disclosure")).to_contain_text("your input draft is not sent")
        expect(card.locator(".analysis-history > summary")).to_contain_text("Analysis history (3)")
        expect(page.locator(".analysis-refresh-comparison").first).to_contain_text("Previous")
        expect(page.locator(".analysis-refresh-comparison").first).to_contain_text("Not directly comparable")

        # The new history controls do not reintroduce an arbitrary expiry calendar.
        if width <= 760:
            page.locator("#mobile-menu").click()
        page.locator("#nav-options").click()
        page.locator("#options-symbol").fill("AAPL")
        page.locator("#options-advanced > summary").click()
        expect(page.locator("#options-expiry-status")).to_have_attribute("data-state", "ready")
        assert page.locator("#options-expiry").evaluate("el => el.tagName") == "SELECT"
        assert page.locator('#options-dialog input[type="date"]').count() == 0
        assert page.locator("#options-expiry option").evaluate_all("items => items.map(el => el.value)") == ["", "2030-01-16", "2030-01-18"]
        page.keyboard.press("Escape")
        if page.locator("#toast").is_visible():
            page.locator("#toast").wait_for(state="hidden", timeout=6000)
        card.locator(".analysis-history > summary").click()
        card.scroll_into_view_if_needed()
        SHOTS.mkdir(parents=True, exist_ok=True)
        card.screenshot(path=str(SHOTS / f"refresh-card-{width}.png"), animations="disabled")
        page.locator(".analysis-refresh-comparison").last.screenshot(path=str(SHOTS / f"changes-{width}.png"), animations="disabled")
        page.screenshot(path=str(SHOTS / f"workspace-{width}.png"), animations="disabled")
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
        assert card.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        assert page.locator(".analysis-refresh-comparison").last.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        assert not errors, errors
        return {"width": width, "height": height, "page_errors": errors, "synthetic_refresh_posts": len(refresh_calls), "synthetic_chat_posts": len(chat_calls), "saved_snapshots": len(session["history"])}
    except Exception:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"failed-{width}.png"))
        raise
    finally:
        for route, _body in held:
            route.abort()
        context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "running", "viewports": [],
              "scope": "All API traffic intercepted with synthetic responses; no broker or external model calls. UI integration checks, not market-data freshness or model-quality validation."}
    try:
        with sync_playwright() as runner:
            browser = runner.chromium.launch(channel="msedge", headless=True)
            for width, height in ((320, 740), (390, 844), (1440, 1000)):
                report["viewports"].append(check(browser, args.base.rstrip("/"), width, height))
            browser.close()
        report["checks"] = ["explicit_refresh_disclosure_and_no_automatic_request", "single_post_uses_expected_snapshot_current_model_and_language",
                            "busy_status_and_global_lock", "duplicate_refresh_is_suppressed", "draft_is_not_submitted_or_cleared",
                            "server_recorded_user_intent_is_appended", "old_reply_keeps_original_snapshot", "before_after_local_receipt_and_feed",
                            "percent_contract_and_percentage_point_changes", "missing_values_do_not_become_zero", "incomparable_metrics_keep_values_without_delta",
                            "change_evidence_can_be_opened_and_located", "newest_first_history_and_current_marker", "history_review_is_get_only_and_does_not_rebind",
                            "all_capture_failure_retains_old_context_messages_history_and_draft", "model_failure_keeps_new_snapshot_with_local_fallback",
                            "reload_restores_active_snapshot_and_history", "ordinary_chat_remains_separate", "chinese_english_labels", "actual_expiry_selector_regression", "mobile_containment"]
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "report": str(REPORT), "viewports": len(report["viewports"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
