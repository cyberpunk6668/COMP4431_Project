"""Reproducible UI-only acceptance with mocked backend/speech events.

Start FinPilot first. This test does not call DeepSeek, run a local model, use a
microphone, or play audio. It verifies integration and safe rendering in a real
browser; it is not evidence that either LLM is available or accurate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "ui_v2_check.json"
SCREENSHOTS = ROOT / "reports" / "screenshots" / "ui-v2-mocked"
SOURCE = {
    "id": "compound-interest", "title": "复利 / Compound interest",
    "url": "https://www.investor.gov/financial-tools-calculators/calculators/compound-interest-calculator",
    "snippet": "Compound interest means earning interest on principal and accumulated interest.",
}
ANSWER = """## Financial clarity

**Compound interest** can grow over time. [compound-interest]

- Check the assumptions.
- Verify the source.

`FV = P(1+r)^n`

<img src=x onerror="window.xssExecuted=true"> [unknown-source]"""


def run(base_url: str, browser_channel: str) -> dict:
    checks, errors, layouts = [], [], []
    pending = []
    responses = {
        "/api/health": {"status": "ok", "mode": "deepseek", "model": "deepseek-flash", "knowledge_documents": 18, "version": "ui-fixture"},
        "/api/models": {"models": [
            {"id": "deepseek", "label": "DeepSeek", "available": True, "description": "Do not display implementation terms to users."},
            {"id": "local", "label": "Local LoRA", "available": False, "description": "Do not display implementation terms to users."},
        ], "default": "deepseek"},
        "/api/sessions": {"sessions": []},
    }

    def route_api(route):
        path = urlsplit(route.request.url).path
        if path == "/api/chat":
            pending.append(route)
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(responses.get(path, {})))

    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=browser_channel, headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script("""
            class FixtureRecognition {
                constructor() { window.fixtureRecognition = this; }
                start() { this.onstart?.(new Event('start')); }
                stop() { this.onend?.(new Event('end')); }
                abort() { this.onend?.(new Event('end')); }
            }
            Object.defineProperty(window, 'SpeechRecognition', { configurable:true, value:FixtureRecognition });
        """)
        page.route("**/api/**", route_api)
        page.goto(base_url, wait_until="networkidle")
        page.wait_for_function("window.finPilotAvatarInstance && window.finPilotAvatarInstance.getStatus().actualMode === '3d'")
        assert page.locator("#model-select option[value=local]").get_attribute("disabled") is not None
        expect(page.locator("#model-select option[value=local]")).to_contain_text("未就绪")
        expect(page.locator("#model-description")).not_to_contain_text("implementation")
        checks.append("localized_model_choices_and_unavailable_state")

        for theme in ("light", "dark"):
            if page.locator("html").get_attribute("data-theme") != theme:
                page.locator("#theme-toggle").click()
            for language in ("zh", "en"):
                expected_lang = "zh-CN" if language == "zh" else "en"
                if page.locator("html").get_attribute("lang") != expected_lang:
                    page.locator("#language-toggle").click()
                for width in (320, 390, 721, 768, 940, 1024, 1280, 1440):
                    page.set_viewport_size({"width": width, "height": 1050})
                    page.wait_for_timeout(80)  # Allow ResizeObserver and responsive companion collapse.
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (theme, language, width)
                    page.locator("#quick-calculate").click()
                    expect(page.locator("#calculator-dialog")).to_be_visible()
                    box = page.locator("#calculator-dialog").bounding_box()
                    assert box and box["x"] >= 0 and box["x"] + box["width"] <= width + 1
                    page.locator("#calculator-dialog .close-dialog").click()
                    layouts.append({"theme": theme, "language": language, "width": width, "home": "passed", "calculator": "passed"})
            page.set_viewport_size({"width": 1440, "height": 1050})
            if page.locator("html").get_attribute("lang") != "zh-CN":
                page.locator("#language-toggle").click()
            page.evaluate("scrollTo({top:0,behavior:'instant'})")
            page.screenshot(path=str(SCREENSHOTS / f"home-{theme}.png"), full_page=True, animations="disabled")
        checks.append("32_responsive_theme_language_cases_and_32_calculator_layouts")

        # Primary reading sizes are measured, not inferred from the stylesheet.
        page.locator("#message-input").fill('<img src=x onerror="window.xssExecuted=true">')
        page.locator("#send-button").click()
        expect(page.locator("body")).to_have_attribute("data-assistant-state", "thinking")
        assert pending
        assert pending[0].request.post_data_json["engine"] == "deepseek"
        pending.pop(0).fulfill(status=200, content_type="application/json", body=json.dumps({"session_id": "ui-fixture", "answer": ANSWER, "sources": [SOURCE], "mode": "deepseek"}))
        expect(page.locator(".message.assistant")).to_have_count(1)
        expect(page.locator("body")).to_have_attribute("data-assistant-state", "idle")
        assert page.locator(".message.assistant strong").first.text_content() == "Compound interest"
        assert page.locator(".message.assistant li").count() == 2
        assert page.locator(".message-body img").count() == 0
        assert not page.evaluate("Boolean(window.xssExecuted)")
        assert page.locator(".inline-citation").count() == 1
        expect(page.locator(".inline-citation")).to_have_attribute("href", SOURCE["url"])
        page.locator(".source-preview summary").click()
        expect(page.locator(".source-preview p")).to_be_visible()
        sizes = page.evaluate("Object.fromEntries(['.message.assistant .message-body','#model-description','.copilot-intro'].map(s=>[s,parseFloat(getComputedStyle(document.querySelector(s)).fontSize)]))")
        assert sizes[".message.assistant .message-body"] >= 14
        assert sizes["#model-description"] >= 12 and sizes[".copilot-intro"] >= 12
        checks.extend(["actual_request_thinking_idle_transitions", "safe_markdown_and_verified_source_links", "readable_primary_text_sizes"])

        page.locator("#quick-calculate").click()
        page.locator("#tab-compound").focus()
        page.keyboard.press("ArrowRight")
        expect(page.locator("#tab-loan")).to_have_attribute("aria-selected", "true")
        expect(page.locator("#calc-principal")).to_be_visible()
        page.locator("#calculator-dialog .close-dialog").click()
        checks.append("keyboard_calculator_tabs")

        page.locator("#avatar-2d").click()
        assert page.evaluate("window.finPilotAvatarInstance.getStatus().actualMode") == "2d"
        page.locator("#avatar-3d").click()
        page.wait_for_function("window.finPilotAvatarInstance.getStatus().actualMode === '3d'")
        page.locator("#reduce-motion").check()
        assert page.evaluate("window.finPilotAvatarInstance.getStatus().reducedMotion")
        checks.append("genuine_webgl_svg_switch_and_reduced_motion")

        page.locator("#mic-button").click()
        expect(page.locator("body")).to_have_attribute("data-assistant-state", "listening")
        page.locator("#mic-button").click()
        expect(page.locator("body")).to_have_attribute("data-assistant-state", "idle")
        page.evaluate("Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{speak(u){window.fixtureUtterance=u;u.onstart(new Event('start'));},cancel(){}}})")
        page.locator("#avatar-read-last").click()
        expect(page.locator("body")).to_have_attribute("data-assistant-state", "speaking")
        assert page.evaluate("window.finPilotAvatarInstance.getStatus().state") == "speaking"
        page.evaluate("window.fixtureUtterance.onend(new Event('end'))")
        expect(page.locator("body")).to_have_attribute("data-assistant-state", "idle")
        checks.append("mock_speech_recognition_and_synthesis_event_integration")

        page.locator("#message-input").fill("Keep this draft")
        page.locator("#send-button").click()
        expect(page.locator("body")).to_have_attribute("data-assistant-state", "thinking")
        pending.pop(0).fulfill(status=503, content_type="application/json", body='{"detail":"Synthetic outage"}')
        expect(page.locator("body")).to_have_attribute("data-assistant-state", "error")
        expect(page.locator("#message-input")).to_have_value("Keep this draft")
        checks.append("outage_error_state_preserves_draft")

        responses["/api/models"]["models"][1]["available"] = True
        page.reload(wait_until="networkidle")
        page.locator("#model-select").select_option("local")
        expect(page.locator("#model-description")).to_contain_text("质量仍有限")
        page.locator("#message-input").fill("What is compound interest?")
        page.locator("#send-button").click()
        expect(page.locator("body")).to_have_attribute("data-assistant-state", "thinking")
        assert pending[0].request.post_data_json["engine"] == "local"
        pending.pop(0).fulfill(status=200, content_type="application/json", body=json.dumps({"session_id": "ui-fixture", "answer": ANSWER, "sources": [SOURCE], "mode": "local-lora"}))
        expect(page.locator(".message-mode")).to_contain_text("本地 LoRA")
        checks.append("available_local_engine_selection_and_request_contract")

        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.locator("#copilot-content")).not_to_be_visible()
        page.locator("#avatar-collapse").click()
        expect(page.locator("#avatar-stage")).to_be_visible()
        page.evaluate("scrollTo({top:0,behavior:'instant'})")
        page.screenshot(path=str(SCREENSHOTS / "mobile-expanded.png"), full_page=True, animations="disabled")
        checks.append("mobile_companion_defaults_collapsed_and_expands")
        assert not errors, errors
        status = page.evaluate("window.finPilotAvatarInstance.getStatus()")
        browser.close()
    return {"status": "passed", "checks": checks, "check_count": len(checks), "layout_cases": layouts,
            "layout_case_count": len(layouts), "calculator_layout_count": len(layouts), "reading_sizes_px": sizes,
            "page_errors": errors, "renderer": status,
            "screenshots": [path.relative_to(ROOT).as_posix() for path in SCREENSHOTS.glob("*.png")]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--browser", default="msedge", choices=("msedge", "chrome"))
    args = parser.parse_args()
    if urlsplit(args.base_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Use a running local FinPilot server.")
    started = time.perf_counter()
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "browser": args.browser,
              "mocked_backend": True, "mocked_speech_events": True,
              "scope": "Real browser UI integration; no DeepSeek billing or local-model inference. Speech hardware and answer accuracy are not tested.",
              "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in (ROOT / "web" / "index.html", ROOT / "web" / "styles.css", ROOT / "web" / "app.js")}}
    try:
        report.update(run(args.base_url.rstrip("/"), args.browser))
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        report["duration_seconds"] = round(time.perf_counter() - started, 2)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "check_count", "layout_case_count", "calculator_layout_count", "page_errors", "duration_seconds")}, indent=2))


if __name__ == "__main__":
    main()
