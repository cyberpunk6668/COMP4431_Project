"""Exercise options-page languages in a private app and real Edge viewports.

No real model or broker is used. Cloud UI states use controlled responses;
the offline application supplies the actual local and unconfigured fallbacks.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import socket
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import time
from urllib.parse import parse_qs, urlsplit

import uvicorn
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import Settings
from app.main import create_app

CJK = re.compile(r"[\u3400-\u9fff]")
TEACHING_COPY = re.compile(r"教学|科普|教程|演示|\b(?:teaching|educational|tutorial|demonstration|demo)\b", re.I)
ENGLISH_AUDIT = r"""({keepOriginalAnswers = false} = {}) => {
    const cjk = /[\u3400-\u9fff]/;
    const issues = [];
    const ignored = element => element.closest('#demo-language') ||
        (keepOriginalAnswers && element.closest('.answer-text[lang="zh-CN"],.user-message[lang="zh-CN"]'));
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
        const parent = node.parentElement;
        if (!parent || ignored(parent) || parent.closest('script,style,noscript')) continue;
        if (!parent.checkVisibility()) continue;
        const text = node.textContent.trim();
        if (cjk.test(text)) issues.push({kind: 'text', text});
    }
    for (const element of document.querySelectorAll('[aria-label],[title],[placeholder]')) {
        if (ignored(element) || !element.checkVisibility()) continue;
        for (const attribute of ['aria-label', 'title', 'placeholder']) {
            const text = element.getAttribute(attribute) || '';
            if (cjk.test(text)) issues.push({kind: attribute, text, tag: element.tagName});
        }
    }
    return issues;
}"""


class NoGateway:
    async def snapshot(self, *args, **kwargs):
        raise AssertionError("Language checks must not collect broker data")

    async def status(self):
        return {"status": "disabled", "provider": "ibkr", "enabled": False,
                "tcp_reachable": False, "gateway_connected": False}


def new_context(browser, width):
    context = browser.new_context(viewport={"width": width, "height": 1000}, reduced_motion="reduce")
    # Set a preference only for a new origin, so reloads actually test persistence.
    context.add_init_script("if (!localStorage.getItem('finpilot-language')) localStorage.setItem('finpilot-language', 'en')")
    return context


def english(page, *, keep_original_answers=False):
    expect(page.locator("html")).to_have_attribute("lang", "en")
    assert not CJK.search(page.title()), page.title()
    meta = page.locator('meta[name="description"]').get_attribute("content")
    assert meta and not CJK.search(meta), meta
    issues = page.evaluate(ENGLISH_AUDIT, {"keepOriginalAnswers": keep_original_answers})
    assert not issues, json.dumps(issues, ensure_ascii=False)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), page.viewport_size


def assert_simulated_record(record, *, model_called=False):
    """A result-style page must keep the underlying source and engine honest."""
    assert record["provenance"]["source_kind"] == "synthetic_replay"
    assert record["provenance"]["gateway_connected"] is False
    assert record["provenance"]["model_called"] is model_called
    assert record["snapshot"]["source_kind"] == "synthetic_replay"
    assert record["quality"]["source_kind"] == "synthetic_replay"


def assert_product_presentation(page, language, *, has_result=False):
    en = language == "en"
    expect(page.locator("#demo-source-badge")).to_be_visible()
    expect(page.locator("#demo-source-badge")).to_have_text(
        "Simulated data · Not live market data" if en else "模拟数据 · 非实时行情")
    expect(page.locator("#demo-stage-data strong")).to_have_text("Read options data" if en else "读取期权数据")
    if has_result:
        expect(page.locator("#overview-title")).to_have_text("Analysis overview" if en else "期权分析概览")
        expect(page.locator("#demo-scope")).to_have_text("AAPL · Volatility & risk analysis" if en else "AAPL · 波动与风险分析")
        expect(page.locator("#demo-frame-label")).to_have_text("First analysis" if en else "首次分析")
        expect(page.locator("#demo-answer-mode")).to_have_text("Local rule analysis" if en else "本地规则分析")
        expect(page.locator("#demo-status")).to_contain_text("No model request" if en else "未请求模型")
        # The source badge identifies simulation. The default result and its
        # answer should read as an analysis, without a teaching/demo preamble.
        text = page.locator("#demo-result").inner_text()
        assert not TEACHING_COPY.search(text), text


def switch(page, language):
    page.locator("#demo-language").click()
    expect(page.locator("html")).to_have_attribute("lang", "en" if language == "en" else "zh-CN")
    expect(page.locator("#demo-language")).to_be_enabled()
    assert page.evaluate("localStorage.getItem('finpilot-language')") == language


def open_details(page, selector):
    detail = page.locator(selector)
    if not detail.evaluate("element => element.open"):
        detail.locator(":scope > summary").click()


def expand_english_content(page):
    for selector in ("#demo-settings", "#demo-analysis-details", "#demo-evidence-details",
                     ".limitations-details", "#demo-followup", ".cloud-action", "#demo-source-details"):
        open_details(page, selector)
    for proof in page.locator(".answer-details").all():
        if not proof.evaluate("element => element.open"):
            proof.locator(":scope > summary").click()


def check_view(browser, base, width, shots):
    context = new_context(browser, width)
    page = context.new_page()
    errors, external, requests, catalogue_languages, checks = [], [], [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def request_seen(request):
        if not request.url.startswith(base):
            external.append(request.url)
        if urlsplit(request.url).path == "/api/options-demo/run":
            requests.append(request.post_data_json)
        if urlsplit(request.url).path == "/api/options-demo/scenario":
            catalogue_languages.append(parse_qs(urlsplit(request.url).query).get("language", [None])[0])

    page.on("request", request_seen)
    try:
        page.goto(base + "/options-demo")
        expect(page.locator("#demo-start")).to_be_enabled()
        expect(page.locator("#demo-language")).to_be_enabled()
        english(page)
        assert_product_presentation(page, "en")
        assert catalogue_languages[-1] == "en", catalogue_languages
        assert not requests
        checks.append("inherits_shared_english_preference_localized_metadata_and_accessibility_without_auto_analysis")
        page.screenshot(path=str(shots / f"entry-en-{width}.png"), full_page=True, animations="disabled")

        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/options-demo/run" and response.request.method == "POST") as first_response:
            page.locator("#demo-start").click()
        expect(page.locator("#demo-messages .message-pair")).to_have_count(1)
        expect(page.locator("#demo-language")).to_be_enabled()
        assert len(requests) == 1 and requests[-1]["language"] == "en", requests
        assert requests[-1]["engine"] == "local"
        expect(page.locator("#demo-messages .answer-text")).to_have_attribute("lang", "en")
        assert not CJK.search(page.locator("#demo-messages .answer-text").inner_text())
        expect(page.locator("#demo-phenomena .phenomenon-card")).to_have_count(3)
        expect(page.locator("table,canvas")).to_have_count(0)
        assert_simulated_record(first_response.value.json())
        assert_product_presentation(page, "en", has_result=True)
        english(page)
        page.screenshot(path=str(shots / f"answer-en-{width}.png"), full_page=True, animations="disabled")
        checks.append("single_click_sends_english_once_and_returns_real_local_english_answer_with_no_contract_visuals")
        checks.append("english_result_labels_preserve_visible_simulated_source_and_local_engine_truth")

        original_en = page.locator(".answer-text").first.inner_text()
        expand_english_content(page)
        page.locator(".answer-evidence button").first.click()
        expect(page.locator(".saved-answer-evidence")).to_be_visible()
        english(page)
        checks.append("expanded_settings_metrics_references_units_sources_limits_and_forms_are_english")

        before = len(requests)
        page.locator("#demo-presets button").first.click()
        assert len(requests) == before
        assert not CJK.search(page.locator("#demo-question").input_value())
        page.locator("#demo-ask-local").click()
        expect(page.locator("#demo-messages .message-pair")).to_have_count(2)
        assert len(requests) == before + 1 and requests[-1]["language"] == "en"
        english(page)
        checks.append("english_preset_prefills_only_then_explicit_send_uses_selected_language")

        before = len(requests)
        switch(page, "zh")
        expect(page.locator("#demo-start")).to_contain_text("重新分析")
        assert page.locator(".answer-text").first.inner_text() == original_en
        expect(page.locator(".answer-language").first).to_contain_text("英文")
        assert len(requests) == before
        page.locator("#demo-reset").click()
        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/options-demo/run" and response.request.method == "POST") as chinese_response:
            page.locator("#demo-start").click()
        expect(page.locator("#demo-messages .message-pair")).to_have_count(1)
        assert requests[-1]["language"] == "zh"
        original_zh = page.locator(".answer-text").inner_text()
        assert CJK.search(original_zh)
        assert_simulated_record(chinese_response.value.json())
        assert_product_presentation(page, "zh", has_result=True)
        checks.append("chinese_result_labels_preserve_visible_simulated_source_and_local_engine_truth")
        before = len(requests)
        switch(page, "en")
        assert page.locator(".answer-text").inner_text() == original_zh
        expect(page.locator(".answer-language")).to_contain_text("Chinese")
        expect(page.locator(".answer-text")).to_have_attribute("lang", "zh-CN")
        assert len(requests) == before
        expand_english_content(page)
        page.locator(".answer-evidence button").first.click()
        english(page, keep_original_answers=True)
        checks.append("switch_preserves_generated_text_and_labels_original_answer_language_without_extra_model_call")

        # Explicitly verify both stored-language reload directions.
        switch(page, "zh")
        before = len(requests)
        page.reload()
        expect(page.locator("#demo-start")).to_be_enabled()
        expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
        assert len(requests) == before
        switch(page, "en")
        page.reload()
        expect(page.locator("#demo-start")).to_be_enabled()
        english(page)
        assert len(requests) == before
        checks.append("chinese_and_english_preferences_survive_reload_without_automatic_analysis")

        other = context.new_page()
        other.goto(base + "/options-demo")
        expect(other.locator("#demo-language")).to_be_enabled()
        switch(other, "zh")
        expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
        expect(page.locator("#demo-language")).to_be_enabled()
        switch(other, "en")
        expect(page.locator("html")).to_have_attribute("lang", "en")
        expect(page.locator("#demo-language")).to_be_enabled()
        other.close()
        english(page)
        assert len(requests) == before
        checks.append("cross_tab_preference_sync_without_unrequested_analysis")

        # Navigation may restore the options document from the back/forward
        # cache. A language changed by another tool must be read on return.
        page.goto(base + "/learn")
        expect(page.locator("#lab-language")).to_be_enabled()
        expect(page.locator("html")).to_have_attribute("lang", "en")
        page.locator("#lab-language").click()
        expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
        assert page.evaluate("localStorage.getItem('finpilot-language')") == "zh"
        page.go_back(wait_until="domcontentloaded")
        expect(page).to_have_url(base + "/options-demo")
        expect(page.locator("#demo-start")).to_be_enabled()
        expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
        expect(page.locator("#demo-language")).to_be_enabled()
        assert len(requests) == before
        switch(page, "en")
        english(page)
        assert len(requests) == before
        assert not errors and not external, (errors, external)
        checks.append("learning_page_language_change_applies_on_browser_back_no_auto_analysis_or_page_errors")
        return {"width": width, "status": "passed", "checks": checks,
                "actual_model_requests": 0, "broker_requests": 0,
                "analysis_requests": len(requests), "page_errors": errors}
    finally:
        context.close()


def check_pending_and_cloud_states(browser, base):
    """The cloud response is a fixture, not evidence of real cloud inference."""
    context = new_context(browser, 1440)
    page = context.new_page()
    errors, requests, pending = [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def metadata(route):
        data = context.request.get(route.request.url).json()
        data.update(cloud_configured=True, configured_model="controlled-language-provider")
        route.fulfill(json=data)

    def run(route):
        body = route.request.post_data_json
        requests.append(body)
        assert body["language"] == "en" and body["engine"] == "deepseek", body
        if len(requests) == 1:
            pending.append(route)
        elif len(requests) == 2:
            # The actual offline server returns a correctly localized no-key fallback.
            data = context.request.post(base + "/api/options-demo/run", data=body).json()
            assert data["answer"]["mode"] == "local_fallback", data["answer"]
            assert_simulated_record(data)
            route.fulfill(json=data)
        else:
            route.fulfill(status=500, json={"detail": "Controlled server failure"})

    page.route("**/api/options-demo/scenario**", metadata)
    page.route("**/api/options-demo/run", run)
    try:
        page.goto(base + "/options-demo")
        expect(page.locator("#demo-start")).to_be_enabled()
        expect(page.locator("#demo-engine")).to_have_value("deepseek")
        assert not requests
        page.locator("#demo-start").click()
        expect(page.locator("#demo-language")).to_be_disabled()
        expect(page.locator("#demo-start")).to_be_disabled()
        assert len(pending) == 1
        other = context.new_page()
        other.goto(base + "/options-demo")
        expect(other.locator("#demo-language")).to_be_enabled()
        switch(other, "zh")
        # A response requested in English must not be reinterpreted as a Chinese one.
        expect(page.locator("html")).to_have_attribute("lang", "en")
        template = context.request.post(base + "/api/options-demo/run", data={"frame": 0, "engine": "local", "language": "en"}).json()
        fixture = deepcopy(template)
        fixture["provenance"]["model_called"] = True
        fixture["answer"].update(mode="deepseek", language="en",
                                  text="This controlled English response explains the synthetic sample's volatility pricing and limits.",
                                  notice="Controlled UI response; no real provider was called.")
        pending.pop().fulfill(json=fixture)
        expect(page.locator("#demo-messages .message-pair")).to_have_count(1)
        expect(page.locator("#demo-language")).to_be_enabled()
        expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
        expect(page.locator(".answer-text")).to_have_attribute("lang", "en")
        expect(page.locator(".answer-language")).to_contain_text("英文")
        expect(page.locator("#demo-answer-mode")).to_have_text("DeepSeek 实际生成")
        # Applying the queued language change replaces the transient status;
        # the saved answer keeps the durable model-attempt provenance.
        expect(page.locator(".answer-source-note")).to_contain_text("本次已发起模型请求")
        assert len(requests) == 1
        other.close()
        switch(page, "en")
        english(page)
        expect(page.locator("#demo-answer-mode")).to_have_text("Generated by DeepSeek")
        expect(page.locator(".answer-source-note")).to_contain_text("A model request was made")
        expect(page.locator("#demo-source-badge")).to_have_text("Simulated data · Not live market data")

        open_details(page, "#demo-followup")
        page.locator("#demo-question").fill("What does implied volatility describe?")
        page.locator("#demo-ask-local").click()
        expect(page.locator("#demo-messages .message-pair")).to_have_count(2)
        expect(page.locator("#demo-answer-mode")).to_have_text("Local rule fallback")
        expect(page.locator("#demo-status")).to_contain_text("No model request")
        expect(page.locator(".message-pair").last.locator(".answer-source-note")).to_contain_text("No model request was made")
        assert len(requests) == 2
        english(page)
        saved = page.locator(".answer-text").all_text_contents()
        page.locator("#demo-question").fill("Explain the current sample again.")
        page.locator("#demo-ask-local").click()
        expect(page.locator("#demo-error")).to_be_visible()
        expect(page.locator("#demo-language")).to_be_enabled()
        assert page.locator(".answer-text").all_text_contents() == saved
        english(page)
        assert len(requests) == 3 and not errors, (requests, errors)
        return {"status": "passed", "scope": "controlled cloud UI responses, actual offline fallback",
                "checks": ["language_locked_while_request_in_flight", "cross_tab_change_queued_until_response_completes",
                           "response_retains_requested_language_after_queued_switch", "explicit_english_payload_and_cloud_mode",
                           "unconfigured_fallback_english", "server_failure_english_preserves_answers",
                           "result_labels_keep_model_attempts_and_unconfigured_local_fallback_distinct"],
                "actual_model_requests": 0, "broker_requests": 0}
    finally:
        for route in pending:
            route.abort()
        context.close()


def check_stale_backend_guards(browser, base, shots):
    """A new static client must not send language fields to an old server.

    The legacy catalogue deliberately ignores the language query, reproducing
    the older service contract that caused the user's HTTP 422. No real model
    or broker is used; validation inputs are controlled and must not be echoed.
    """
    cases = []
    for language in ("en", "zh"):
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        context.add_init_script(f"localStorage.setItem('finpilot-language', '{language}')")
        page = context.new_page()
        errors, run_requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: run_requests.append(request.post_data_json)
                if urlsplit(request.url).path == "/api/options-demo/run" else None)

        def legacy_metadata(route):
            data = context.request.get(base + "/api/options-demo/scenario?language=zh").json()
            for key in ("language", "display_catalogue", "api_contract", "supported_languages"):
                data.pop(key, None)
            route.fulfill(json=data)

        page.route("**/api/options-demo/scenario**", legacy_metadata)
        try:
            page.goto(base + "/options-demo")
            expect(page.locator("#demo-error")).to_be_visible()
            expect(page.locator("#demo-start")).to_be_disabled()
            expect(page.locator("#demo-language")).to_be_enabled()
            expect(page.locator("html")).to_have_attribute("lang", "en" if language == "en" else "zh-CN")
            if language == "en":
                expect(page.locator("#demo-error")).to_contain_text(re.compile("restart|update", re.I))
                english(page)
            else:
                expect(page.locator("#demo-error")).to_contain_text("重启")
            # Error UI must remain bilingual even when the old backend cannot
            # return any translated catalogue at all.
            other = "zh" if language == "en" else "en"
            switch(page, other)
            expect(page.locator("#demo-start")).to_be_disabled()
            if other == "en":
                expect(page.locator("#demo-error")).to_contain_text(re.compile("restart|update", re.I))
                english(page)
            else:
                expect(page.locator("#demo-error")).to_contain_text("重启")
            switch(page, language)
            assert not run_requests and not errors, (run_requests, errors)
            page.screenshot(path=str(shots / f"legacy-backend-{language}.png"), full_page=True, animations="disabled")
            cases.append({"language": language, "case": "legacy_catalogue_without_language_contract",
                          "status": "passed", "checks": ["old_service_detected_before_analysis",
                            "analysis_disabled_without_any_post", "localized_restart_guidance_language_control_remains_usable"],
                          "actual_model_requests": 0, "broker_requests": 0})
        finally:
            context.close()

        context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        context.add_init_script(f"localStorage.setItem('finpilot-language', '{language}')")
        page = context.new_page()
        errors, requests = [], []
        secret_marker = "do-not-render-validation-input"
        page.on("pageerror", lambda error: errors.append(str(error)))

        def reject_language(route):
            body = route.request.post_data_json
            requests.append(body)
            assert body["language"] == language and body["engine"] == "local", body
            if len(requests) == 1:
                # A real local explanation establishes immutable prior state.
                data = context.request.post(base + "/api/options-demo/run", data=body).json()
                route.fulfill(json=data)
                return
            route.fulfill(status=422, json={"detail": [{
                "type": "extra_forbidden", "loc": ["body", "language"],
                "msg": "Extra inputs are not permitted", "input": secret_marker,
            }]})

        page.route("**/api/options-demo/run", reject_language)
        try:
            page.goto(base + "/options-demo")
            expect(page.locator("#demo-start")).to_be_enabled()
            page.locator("#demo-start").click()
            expect(page.locator("#demo-messages .message-pair")).to_have_count(1)
            saved = page.locator(".answer-text").inner_text()
            # Re-analysis reproduces the failing initial-analysis transport,
            # while checking that a useful prior answer is not discarded.
            page.locator("#demo-start").click()
            expect(page.locator("#demo-error")).to_be_visible()
            expect(page.locator("#demo-language")).to_be_enabled()
            expect(page.locator("#demo-start")).to_be_disabled()
            if language == "en":
                expect(page.locator("#demo-error")).to_contain_text(re.compile("restart|update", re.I))
                english(page)
            else:
                expect(page.locator("#demo-error")).to_contain_text("重启")
            assert secret_marker not in page.locator("body").inner_text()
            assert page.locator(".answer-text").inner_text() == saved
            assert len(requests) == 2 and not errors, (requests, errors)
            page.screenshot(path=str(shots / f"language-schema-422-{language}.png"), full_page=True, animations="disabled")
            cases.append({"language": language, "case": "language_field_rejected_by_old_post_schema",
                          "status": "passed", "checks": ["language_422_has_actionable_restart_guidance",
                            "validation_input_is_not_echoed", "prior_answer_preserved_without_hidden_retry"],
                          "actual_model_requests": 0, "broker_requests": 0})
        finally:
            context.close()
    return {"status": "passed", "scope": "controlled old-service catalogue and FastAPI 422 responses", "cases": cases,
            "actual_model_requests": 0, "broker_requests": 0}


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    shots = ROOT / "reports" / "screenshots" / "options-data-language" / stamp
    shots.mkdir(parents=True, exist_ok=True)
    target = ROOT / "reports" / f"options_demo_language_{stamp}.json"
    report = {"status": "failed", "checked_at": stamp,
              "scope": "Actual app, private database, offline providers, real Edge viewports; controlled cloud and old-backend errors",
              "viewports": []}
    with TemporaryDirectory(prefix="finpilot-options-language-") as private:
        app = create_app(Settings(api_key="", offline=True, db_path=Path(private) / "state.sqlite3"), options_provider=NoGateway())

        async def forbidden(*args, **kwargs):
            raise AssertionError("The language browser check requested a real model")

        app.state.options.llm.complete = forbidden
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        base = f"http://127.0.0.1:{sock.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.05)
            if not server.started:
                raise RuntimeError("Private language test server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
                try:
                    for width in (1440, 390, 320):
                        report["viewports"].append(check_view(browser, base, width, shots))
                    report["controlled_cloud_and_pending"] = check_pending_and_cloud_states(browser, base)
                    report["stale_backend_guards"] = check_stale_backend_guards(browser, base, shots)
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
