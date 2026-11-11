"""Check market-data diagnostics and reference-price labels with fixture APIs only.

No real brokerage connection or model request is made; every /api/ request is
intercepted. Close and last remain distinct from bid and ask in these fixtures.
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
REPORT = ROOT / "reports/options_diagnostics_browser_v12.json"
SHOTS = ROOT / "reports/screenshots/options-v12"
OLD_ID = str(UUID(int=401))
SESSION = "diagnostic-conversation"


def check(browser, base, width, height):
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(10000)
    calls, errors, model_calls = [], [], []
    current_case = ["close"]
    local_time = datetime.now(timezone.utc).isoformat()
    trade_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    diagnostic = {
        "stage": "options", "requested_market_data_type": 3, "received_market_data_types": [3],
        "entitlement_status": "realtime_unsubscribed_delayed_available", "data_status": "close_reference",
        "broker_codes": [10167, 10090], "reference_basis": "close", "underlying_fields": ["close"],
        "option_contracts_requested": 10, "option_contracts_with_bid_ask": 0, "option_contracts_with_last": 0,
        "option_contracts_with_close": 10, "option_contracts_with_open_interest": 0,
        "observed_tick_types": [75], "wait_seconds": 8, "timestamp_basis": "local_callback_arrival",
        "interface_status": "market_callbacks_received",
    }
    report = helpers["fixture"]("AAPL", "2030-01-18", "zh")
    report["analysis_id"] = OLD_ID
    report["snapshot"]["source"] = "ibkr"
    underlying = report["snapshot"]["underlying"]
    underlying.update(price=99.25, price_basis="close", close=99.25, close_received_at=local_time,
                      received_at=local_time, last_trade_at=None, bid=None, ask=None, market_data_type=3)
    for quote in report["snapshot"]["quotes"]:
        quote.update(bid=None, ask=None, last=None, close=2.25, close_received_at=local_time)
    report["snapshot"]["diagnostics"] = deepcopy(diagnostic)
    report["snapshot"]["diagnostics"].update(stage="complete", option_contracts_with_open_interest=10)
    # Rebuild local quality and plain wording so the fixture does not invent BBO.
    analysis = helpers["analyze_option_snapshot"](report["snapshot"], language="zh")
    report.update(analysis)
    report["collective"] = helpers["build_collective_analysis"](report["snapshot"], analysis, language="zh")
    report["plain_brief"] = helpers["build_plain_brief"](report, "zh")
    active = {"analysis_id": OLD_ID, "source": "ibkr", "captured_at": local_time, "stale": False,
              "scopes": [{"id": "g0", "symbol": "AAPL", "expiry": "2030-01-18", "received_at": local_time,
                          "market_data_status": "delayed", "time_status": "known"}], "partial_failures": []}
    session = {"id": SESSION, "title": "期权追问 · AAPL", "messages": [], "active_analysis_id": OLD_ID}

    def failure_payload(case):
        data = deepcopy(diagnostic)
        if case == "denied":
            data.update(entitlement_status="explicit_denial", received_market_data_types=[3], broker_codes=[10089], data_status="limited_option_fields")
        elif case == "no_callbacks":
            data.update(entitlement_status="unconfirmed", received_market_data_types=[], broker_codes=[], data_status="no_reference",
                        underlying_fields=[], observed_tick_types=[], interface_status="no_market_callbacks", option_contracts_with_close=0)
        return {"code": "ibkr_option_data_unavailable", "message": "Synthetic quote collection did not produce usable quotes.", "diagnostics": data}

    def respond(route):
        request = route.request
        path = urlsplit(request.url).path
        body = request.post_data_json if request.method in ("POST", "PUT") else None
        calls.append({"method": request.method, "path": path, "body": body})
        if path == "/api/health":
            route.fulfill(json={"status": "ok", "mode": "deepseek", "model": "fixture", "knowledge_documents": 0})
        elif path == "/api/models":
            route.fulfill(json={"default": "deepseek", "models": [{"id": "deepseek", "label": "DeepSeek", "available": True}]})
        elif path == "/api/sessions":
            route.fulfill(status=201 if request.method == "POST" else 200, json=session if request.method == "POST" else {"sessions": [session] if session["messages"] else []})
        elif path == f"/api/sessions/{SESSION}/analysis/refresh":
            route.fulfill(status=424, json={"detail": failure_payload("delayed")})
        elif path == f"/api/sessions/{SESSION}/analysis":
            route.fulfill(json={"active_analysis_id": OLD_ID, "active_analysis": active})
        elif path == f"/api/sessions/{SESSION}":
            route.fulfill(json={**session, "active_analysis": active, "analysis_history": [active]})
        elif path == "/api/options/status":
            route.fulfill(json={"status": "tcp_ready", "enabled": True, "endpoint": "fixture:4002"})
        elif path == "/api/options/analyze":
            case = current_case[0]
            if case in ("delayed", "denied", "no_callbacks"):
                route.fulfill(status=424, json={"detail": failure_payload(case)})
            else:
                data = deepcopy(report)
                if case in ("last", "last_unknown"):
                    data["snapshot"]["underlying"].update(price_basis="last", last_trade_at=trade_time if case == "last" else None)
                    data["snapshot"]["diagnostics"]["data_status"] = "last_reference"
                if case == "legacy":
                    data["snapshot"].pop("diagnostics", None)
                    data["snapshot"]["underlying"]["price_basis"] = "midpoint"
                route.fulfill(json=data)
        elif path == "/api/options/batch":
            comparison = helpers["build_batch_comparison"]([report], "zh")
            failures = [{"symbol": "MSFT", "expiry": None, **failure_payload("denied")}]
            route.fulfill(json={"reports": [report], "comparison": comparison, "failures": failures,
                                "plain_brief": helpers["build_batch_plain_brief"]([report], comparison, failures, "zh"),
                                "interpretation": {"status": "skipped"}, "completed_at": local_time})
        elif path.startswith("/api/options/analyses/"):
            route.fulfill(json=report)
        elif path == "/api/chat":
            model_calls.append(body)
            raise AssertionError("This diagnostic check must not send a chat/model request")
        else:
            raise AssertionError(f"Unexpected request: {request.method} {path}")

    context.route("**/api/**", respond)
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(base + "/workspace?view=options", wait_until="domcontentloaded")
        page.locator("#options-symbol").fill("AAPL")
        page.locator("#options-submit").click()
        results = page.locator("#options-results")
        plain = results.locator(".options-plain-report")
        reference = plain.locator(".options-reference-notice")
        expect(reference).to_be_visible()
        expect(reference).to_have_attribute("data-price-basis", "close")
        expect(reference).to_contain_text("不是当前可成交报价")
        expect(reference).to_contain_text("收盘价所属日期：接口未提供")
        expect(reference).to_contain_text("交易时间未知")
        expect(reference).to_contain_text("本地接收时间")
        expect(plain.locator(".market-diagnostics")).to_contain_text("收盘参考")
        expect(plain.locator(".market-diagnostics")).to_contain_text("部分请求字段存在订阅限制；已收到字段仍可读取，不能据此声称全部数据被拒绝")
        assert plain.locator(".market-diagnostics details").get_attribute("open") is None
        SHOTS.mkdir(parents=True, exist_ok=True)
        reference.screenshot(path=str(SHOTS / f"reference-{width}.png"), animations="disabled")
        page.locator("#options-view-professional").click()
        professional = results.locator(".options-professional-report")
        expect(professional.locator(".options-reference-notice")).to_contain_text("不是当前可成交报价")
        professional.locator(".options-raw-details > summary").click()
        table = professional.locator(".options-chain-table")
        expect(table.locator("thead")).to_contain_text("收盘参考价")
        cells = table.locator("tbody tr").first.locator("td").all_text_contents()
        assert cells[2:6] == ["—", "—", "—", "2.25"], cells
        page.locator("#options-view-simple").click()

        # Failed collection preserves the old report and shows the actual diagnostic facts.
        current_case[0] = "delayed"
        page.locator("#options-submit").click()
        error = page.locator("#options-error")
        expect(error.locator(".market-diagnostics")).to_be_visible()
        expect(error).to_contain_text("可用延迟行情")
        expect(error).to_contain_text("已收到延迟类型回调")
        expect(error).to_contain_text("部分请求字段存在订阅限制")
        expect(results.locator(".options-retained-notice")).to_contain_text("上一次成功")
        expect(results.locator(".options-plain-report")).to_be_visible()
        expect(page.locator("#options-request-status")).to_be_hidden()
        expect(results.locator(".options-freshness")).to_contain_text("已保存的行情快照")
        error.locator("details > summary").click()
        expect(error).to_contain_text("10167")
        expect(error).to_contain_text("10090")
        expect(error).to_contain_text("75")
        expect(error).to_contain_text("不是交易所成交时间")

        current_case[0] = "denied"
        page.locator("#options-submit").click()
        expect(error).to_contain_text("明确的订阅拒绝提示")
        expect(error).to_contain_text("不等于所有行情都被拒绝")
        current_case[0] = "no_callbacks"
        page.locator("#options-submit").click()
        expect(error).to_contain_text("权限尚未确认")
        error.locator("details > summary").click()
        expect(error).to_contain_text("未观察到行情字段回调")
        expect(error).to_contain_text("无法断言权限或接口故障")

        # Last-trade time and local receipt are shown separately, without fabricating an unknown timestamp.
        current_case[0] = "last"
        page.locator("#options-submit").click()
        expect(reference).to_have_attribute("data-price-basis", "last")
        expect(reference).to_contain_text("最近成交时间（UTC）")
        expect(reference).to_contain_text("不是双边报价")
        expect(results.locator(".options-retained-notice")).to_have_count(0)
        current_case[0] = "last_unknown"
        page.locator("#options-submit").click()
        expect(reference).to_contain_text("交易时间未知")

        # Per-item failure diagnosis remains attached to its symbol.
        page.locator("#options-analysis-mode").select_option("batch")
        page.locator("#options-batch-items").fill("AAPL\nMSFT")
        page.locator("#options-submit").click()
        expect(plain.locator(".market-diagnostics").last).to_contain_text("MSFT")
        expect(plain.locator(".market-diagnostics").last).to_contain_text("明确的订阅拒绝提示")

        # Legacy reports still display without requiring the new diagnostics shape.
        page.locator("#options-analysis-mode").select_option("single")
        current_case[0] = "legacy"
        page.locator("#options-submit").click()
        expect(plain).to_be_visible()
        expect(plain.locator(".market-diagnostics")).to_have_count(0)
        expect(reference).to_have_count(0)

        # Refresh failure exposes the same diagnostics and keeps the active snapshot and draft.
        page.locator(".options-followup-main").click()
        card = page.locator("#analysis-context-card")
        expect(card).to_have_attribute("data-analysis-id", OLD_ID)
        page.locator("#message-input").fill("我的未发送草稿")
        before_messages = page.locator("#chat-messages").inner_text()
        card.locator(".analysis-refresh-button").click()
        banner = page.locator("#error-banner")
        expect(banner.locator(".market-diagnostics")).to_be_visible()
        expect(banner).to_contain_text("已收到延迟类型回调")
        expect(card).to_have_attribute("data-analysis-id", OLD_ID)
        expect(page.locator("#message-input")).to_have_value("我的未发送草稿")
        assert page.locator("#chat-messages").inner_text() == before_messages
        banner.locator("details > summary").click()
        expect(banner).to_contain_text("收到收盘参考价")
        SHOTS.mkdir(parents=True, exist_ok=True)
        banner.screenshot(path=str(SHOTS / f"diagnostics-{width}.png"), animations="disabled")
        page.locator("#language-toggle").click()
        # A subsequent English request rerenders structured diagnosis in the active UI language.
        card.locator(".analysis-refresh-button").click()
        expect(banner).to_contain_text("Delayed-type callbacks arrived")
        expect(banner).to_contain_text("does not mean delayed quotes arrived")
        expect(banner).to_contain_text("Some requested fields have subscription restrictions")
        expect(banner).to_contain_text("Received fields remain readable; this does not establish that all data was denied")
        assert not model_calls
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
        assert banner.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        assert not errors, errors
        return {"width": width, "height": height, "page_errors": errors, "intercepted_api_calls": len(calls), "real_broker_calls": 0, "model_requests": 0}
    except Exception:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"failed-{width}.png"))
        raise
    finally:
        context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "running", "viewports": [],
              "scope": "All API traffic intercepted with synthetic responses. This checks presentation of provider facts, not actual entitlement or exchange-data availability."}
    try:
        with sync_playwright() as runner:
            browser = runner.chromium.launch(channel="msedge", headless=True)
            for width, height in ((320, 740), (390, 844), (1440, 1000)):
                report["viewports"].append(check(browser, args.base.rstrip("/"), width, height))
            browser.close()
        report["checks"] = ["close_reference_is_not_current_executable_quote", "closing_date_and_unknown_trade_time_are_not_inferred",
                            "last_trade_time_is_separate_from_local_receipt", "close_is_not_copied_into_bid_ask_or_last", "successful_snapshot_has_optional_diagnostic_records",
                            "delayed_type_without_quotes_is_explicit", "explicit_denial_does_not_claim_all_data_denied", "no_callbacks_does_not_invent_entitlement_or_adapter_fault",
                            "broker_codes_tick_types_counts_and_time_basis_are_visible", "partial_subscription_10090_preserves_received_fields_and_does_not_claim_total_denial", "failed_analysis_retains_previous_snapshot_with_explicit_old_label",
                            "batch_failure_diagnostics_identify_symbol", "legacy_reports_work_without_diagnostics", "refresh_failure_retains_active_snapshot_messages_and_draft",
                            "chinese_english_diagnostics", "no_automatic_model_request", "mobile_containment"]
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "report": str(REPORT), "viewports": len(report["viewports"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
