"""Real app/Edge replay checks in private offline state; no model or IBKR calls."""
from datetime import datetime, timezone
from copy import deepcopy
import json
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import time

import uvicorn
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import Settings
from app.main import create_app


class NoGateway:
    async def snapshot(self, *args, **kwargs):
        raise AssertionError("Browser replay contacted the broker")

    async def status(self):
        # The complete workspace reads local provider availability when its
        # dialog opens. Supply a disabled status, without any broker transport.
        return {"status": "disabled", "provider": "ibkr", "tcp_reachable": False,
                "enabled": False, "gateway_connected": False}


def check_view(browser, url, width, shots):
    context = browser.new_context(viewport={"width": width, "height": 1000}, reduced_motion="reduce")
    page = context.new_page()
    errors, external, runs, checks = [], [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url) if not request.url.startswith(url) else None)
    page.on("request", lambda request: runs.append(request.post_data_json) if request.url.endswith("/api/options-demo/run") else None)
    page.goto(url + "/options-demo")
    expect(page.locator("#demo-engine")).to_be_enabled()
    expect(page.locator("#demo-engine")).to_have_value("local")
    expect(page.locator("#demo-start")).to_be_enabled()
    assert not runs
    checks.append("page_load_reads_scenario_only_no_analysis_or_cloud")
    page.locator("#demo-start").click()
    expect(page.locator("#demo-result")).to_be_visible()
    expect(page.locator("#demo-quotes")).to_have_count(0)
    expect(page.locator('[data-metric="put_call_volume"] .metric-value')).to_contain_text("1.5")
    expect(page.locator('[data-metric="iv_skew_25_delta"]')).to_contain_text("百分点")
    expect(page.locator("#demo-messages .message-pair")).to_have_count(1)
    expect(page.locator("#demo-answer-mode")).to_contain_text("本地")
    assert runs[-1]["frame"] == 0 and runs[-1]["engine"] == "local"
    checks.append("one_click_actual_app_sample_calculation_rule_answer")
    expect(page.locator("#demo-overview")).to_be_visible()
    expect(page.locator("#demo-phenomena")).to_contain_text("波动")
    expect(page.locator('[data-phenomenon="iv_meaning"]')).to_have_count(1)
    assert len(runs) == 1
    expect(page.locator("table, canvas, svg[role=img]")).to_have_count(0)
    assert not page.locator("#demo-analysis-details").evaluate("element => element.open")
    checks.append("default_view_prioritizes_phenomena_and_chat_details_remain_collapsed")
    baseline = page.locator("#demo-messages .answer-text").first.inner_text()
    page.locator("#demo-result").scroll_into_view_if_needed()
    page.screenshot(path=str(shots / f"baseline-{width}.png"), full_page=True, animations="disabled")
    page.locator("#demo-analysis-details > summary").click()
    page.locator("#demo-next").click()
    expect(page.locator("#demo-quality-note")).to_contain_text("缺")
    expect(page.locator("#demo-changes-section")).to_be_visible()
    expect(page.locator('[data-change="put_call_volume"]')).to_contain_text("2")
    expect(page.locator('[data-metric="iv_skew_25_delta"] .metric-value')).to_contain_text("12")
    expect(page.locator("#demo-quality-note")).to_contain_text("缺")
    assert page.locator("#demo-messages .answer-text").first.inner_text() == baseline
    expect(page.locator("#demo-messages .message-pair")).to_have_count(2)
    old_answer = page.locator('.message-pair[data-frame="0"]').first
    old_answer.locator(".answer-details > summary").click()
    old_answer.locator(".answer-evidence button").filter(has_text="约 25Δ 看跌减看涨 IV").click()
    expect(old_answer.locator(".saved-answer-evidence")).to_contain_text("8 个百分点")
    checks.append("matched_frame_changes_missing_not_zero_old_answer_and_evidence_immutable")
    before = len(runs)
    page.locator("#demo-followup > summary").click()
    page.locator("#demo-presets button").filter(has_text="隐含波动率").click()
    assert len(runs) == before
    page.locator("#demo-ask-local").click()
    expect(page.locator("#demo-messages .message-pair")).to_have_count(3)
    assert runs[-1]["frame"] == 1
    expect(page.locator("#demo-messages .answer-text").last).to_contain_text("波动")
    checks.append("preset_fills_only_explicit_send_reads_current_frame")
    page.locator("#demo-question").fill('<img src=x onerror="alert(1)">')
    page.locator("#demo-ask-local").click()
    expect(page.locator("#demo-messages .message-pair")).to_have_count(4)
    assert page.locator("#demo-messages img").count() == 0
    checks.append("user_text_is_escaped")
    page.route("**/api/options-demo/run", lambda route: route.fulfill(status=500, content_type="application/json", body='{"detail":"Controlled failure"}'), times=1)
    page.locator("#demo-start").click()
    expect(page.locator("#demo-error")).to_contain_text("Controlled failure")
    expect(page.locator("#demo-messages .message-pair")).to_have_count(4)
    expect(page.locator('[data-metric="iv_skew_25_delta"] .metric-value')).to_contain_text("12")
    expect(page.locator("#demo-start")).to_be_enabled()
    checks.append("failed_request_preserves_prior_frame_and_messages_allows_retry")
    page.locator("#demo-reset").click()
    expect(page.locator("#demo-result")).to_be_hidden()
    expect(page.locator("#demo-error")).to_be_hidden()
    before = len(runs)
    page.locator("#demo-start").focus()
    page.keyboard.press("Enter")
    expect(page.locator("#demo-result")).to_be_visible()
    assert len(runs) == before + 1
    checks.append("reset_then_keyboard_one_click_replays_cleanly")
    # Only a table may scroll horizontally; the page must fit its viewport.
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    assert not errors and not external, (errors, external)
    page.locator("#demo-result").scroll_into_view_if_needed()
    page.screenshot(path=str(shots / f"replay-{width}.png"), full_page=True, animations="disabled")
    checks.append("viewport_fits_no_external_assets_or_javascript_errors")
    context.close()
    return {"width": width, "status": "passed", "checks": checks, "model_requests": 0,
            "gateway_requests": 0, "page_errors": errors}


def check_model_controls(browser, url):
    """Controlled responses verify UI states; genuine inference has its own report."""
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    metadata = context.request.get(url + "/api/options-demo/scenario").json()
    metadata.update(cloud_configured=True, configured_model="controlled-ui-provider")
    result = context.request.post(url + "/api/options-demo/run", data={"frame": 0, "engine": "local"}).json()
    page = context.new_page()
    page.route("**/api/options-demo/scenario", lambda route: route.fulfill(json=metadata))
    requests = []

    def model_response(route):
        requests.append(route.request.post_data_json)
        assert requests[-1]["engine"] == "deepseek"
        for selector in ("#demo-start", "#demo-next", "#demo-engine", "#demo-reset", "#demo-question"):
            expect(page.locator(selector)).to_be_disabled()
        record = deepcopy(result)
        record["provenance"]["model_called"] = True
        if len(requests) == 1:
            record["answer"].update(mode="deepseek", text="合成样本的模型显示测试，未调用真实模型。", notice="受控 UI 响应")
        else:
            record["answer"].update(mode="local_fallback", fallback_reason="model_validation_failed", notice="模型输出未通过检查，显示本地规则。")
        route.fulfill(json=record)

    page.route("**/api/options-demo/run", model_response)
    page.goto(url + "/options-demo")
    expect(page.locator("#demo-engine")).to_have_value("deepseek")
    assert not requests
    expect(page.locator("#demo-engine-notice")).to_contain_text("请求真实模型")
    page.locator("#demo-start").click()
    expect(page.locator("#demo-answer-mode")).to_contain_text("DeepSeek")
    assert len(requests) == 1
    page.locator("#demo-followup > summary").click()
    page.locator("#demo-question").fill("解释当前样本")
    page.locator("#demo-ask-local").click()
    expect(page.locator("#demo-messages .message-pair")).to_have_count(2)
    expect(page.locator("#demo-messages .message-pair").last).to_contain_text("格式或引用检查")
    expect(page.locator("#demo-answer-mode")).to_contain_text("本地")
    context.close()
    return {"status": "passed", "provider": "controlled UI fixtures, not real model inference",
            "checks": ["configured_engine_default_without_auto_call", "explicit_click_uses_selected_engine",
                       "inflight_controls_locked", "model_success_and_validation_fallback_distinguished"],
            "actual_model_requests": 0}


def check_entry_routes(browser, url, shots):
    """Click the built homepage and workspace entries, not just direct URLs."""
    results = []
    for width, language in ((1440, "zh"), (1440, "en"), (390, "zh"), (390, "en")):
        context = browser.new_context(viewport={"width": width, "height": 1000}, reduced_motion="reduce")
        context.add_init_script(f"localStorage.setItem('finpilot-language', '{language}')")
        page = context.new_page()
        posts = []
        server_errors = []
        page.on("response", lambda response: server_errors.append(response.url) if response.status >= 500 else None)
        page.on("request", lambda request: posts.append(request.url) if request.method == "POST" and
                any(request.url.endswith(path) for path in ("/api/chat", "/api/options-demo/run", "/api/options/analyze", "/api/options/batch", "/api/options/history/fetch")) else None)

        def assert_analysis():
            expect(page).to_have_url(url + "/options-demo")
            expect(page.locator("#demo-start")).to_be_enabled()
            expect(page.locator("#lab-scenarios")).to_have_count(0)

        page.goto(url + "/")
        primary = page.get_by_test_id("hero-options-analysis")
        expect(primary).to_have_attribute("href", "/options-demo")
        primary.click()
        assert_analysis()
        page.screenshot(path=str(shots / f"entry-{width}-{language}.png"), full_page=True, animations="disabled")
        page.goto(url + "/")
        if width < 1024:
            page.get_by_test_id("menu-toggle").click()
        page.locator('.site-header a[href="/options-demo"]').filter(visible=True).click()
        assert_analysis()
        page.goto(url + "/")
        page.locator('.site-footer a[href="/learn"]').click()
        expect(page).to_have_url(url + "/learn")
        expect(page.locator("#lab-scenarios button")).to_have_count(3)
        expect(page.locator("#demo-start")).to_have_count(0)
        page.goto(url + "/workspace")
        page.locator("#starter-options-analysis").click()
        assert_analysis()
        page.goto(url + "/workspace")
        if width < 1024:
            page.locator("#mobile-menu").click()
        page.locator("#nav-options-insights").click()
        assert_analysis()
        page.goto(url + "/workspace?view=options")
        expect(page.locator("#options-dialog")).to_be_visible()
        page.locator("#options-analysis-entry").click()
        assert_analysis()
        assert not posts, posts
        assert not server_errors, server_errors
        results.append({"width": width, "language": language, "status": "passed",
                        "checks": ["home_primary_analysis", "home_navigation_analysis", "learning_is_separate",
                                   "workspace_primary_analysis", "workspace_sidebar_analysis", "options_dialog_analysis"],
                        "model_requests": 0, "gateway_requests": 0})
        context.close()
    return results


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shots = ROOT / "reports" / "screenshots" / "options-data-demo" / stamp
    shots.mkdir(parents=True, exist_ok=True)
    report = {"status": "failed", "checked_at": stamp,
              "scope": "Actual create_app + private offline settings + real Edge viewports; no real model or gateway", "viewports": []}
    target = ROOT / "reports" / f"options_demo_browser_{stamp}.json"
    with TemporaryDirectory(prefix="finpilot-options-demo-") as private:
        app = create_app(Settings(api_key="", offline=True, db_path=Path(private) / "state.sqlite3"), options_provider=NoGateway())

        async def forbidden(*args, **kwargs):
            raise AssertionError("Offline browser requested model")

        app.state.options.llm.complete = forbidden
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{sock.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.05)
            if not server.started:
                raise RuntimeError("Private browser server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
                try:
                    for width in (1440, 390, 320):
                        report["viewports"].append(check_view(browser, url, width, shots))
                    report["model_controls"] = check_model_controls(browser, url)
                    report["entry_navigation"] = check_entry_routes(browser, url, shots)
                finally:
                    browser.close()
            report["status"] = "passed"
        except Exception as error:
            report["error"] = str(error)
            raise
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            sock.close()
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"status": report["status"], "report": str(target)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
