"""Real browser acceptance. Requires running local server and installed Edge/Chrome.

One real RAG answer is requested; screenshots contain only synthetic demo content.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"


def main():
    screenshots = ROOT / "reports" / "screenshots" / "v2"
    screenshots.mkdir(parents=True, exist_ok=True)
    checks, errors, console_errors = [], [], []
    started = time.perf_counter()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        page = context.new_page()
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" and "favicon" not in msg.text else None)
        page.goto(BASE + "/workspace", wait_until="networkidle")
        expect(page.locator("#engine-label")).to_contain_text("已配置")
        expect(page.locator("#message-input")).to_be_visible()
        page.wait_for_function("state.avatar && state.avatar.getStatus().actualMode === '3d'", timeout=20000)
        avatar_status = page.evaluate("state.avatar.getStatus()")
        assert avatar_status["renderer"] == "webgl2" and avatar_status["threeRevision"] == "187"
        page.screenshot(path=str(screenshots / "home-desktop.png"), full_page=True)
        checks.append("desktop_initial_load_and_configuration_label")
        checks.append("actual_webgl2_avatar_under_application_csp")
        page.locator("#theme-toggle").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.screenshot(path=str(screenshots / "home-dark.png"), full_page=True)
        page.reload(wait_until="networkidle")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.locator("#theme-toggle").click()
        checks.append("dark_theme_toggle_and_persistence")
        page.locator("#avatar-2d").click()
        page.wait_for_function("state.avatar.getStatus().actualMode === '2d'")
        page.locator("#avatar-3d").click()
        page.wait_for_function("state.avatar.getStatus().actualMode === '3d'")
        page.locator("#reduce-motion").check()
        assert page.evaluate("state.avatar.getStatus().reducedMotion")
        page.locator("#reduce-motion").uncheck()
        checks.append("avatar_mode_and_reduced_motion_controls")

        page.locator("#message-input").fill("什么是分散投资？它能消除所有风险吗？")
        page.locator("#send-button").click()
        page.wait_for_function("state.avatarState === 'thinking'", timeout=10000)
        expect(page.locator(".message.assistant")).to_have_count(1, timeout=65000)
        expect(page.locator(".message-mode")).to_contain_text("DeepSeek")
        assert page.locator(".source-card").count() >= 1
        assert page.locator(".source-card").first.get_attribute("href").startswith("https://")
        assert page.locator(".source-number").first.text_content() in page.locator(".message.assistant .message-body").text_content()
        expect(page.locator("#send-button")).to_be_enabled()
        page.wait_for_function("state.avatarState === 'idle'")
        checks.append("avatar_thinking_state_tracks_real_cloud_request")
        page.screenshot(path=str(screenshots / "chat-sources.png"), full_page=True)
        sid = page.evaluate("localStorage.getItem('finpilot-session')")
        checks.append("real_deepseek_chat_and_source_links")

        with page.expect_download() as download:
            page.locator("#export-button").click()
        exported = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
        assert exported["id"] == sid and len(exported["messages"]) == 2
        checks.append("json_export_matches_conversation")

        page.reload(wait_until="networkidle")
        expect(page.locator(".message.assistant")).to_have_count(1)
        checks.append("session_restored_after_reload")
        page.locator("#top-new").click()
        expect(page.locator(".message")).to_have_count(0)
        page.locator(".session-open").first.click()
        expect(page.locator(".message.assistant")).to_have_count(1)
        checks.append("new_chat_and_session_switch")

        page.locator("#nav-calculator").click()
        page.locator("#calc-principal").fill("10000")
        page.locator("#calc-annual_rate").fill("5")
        page.locator("#calc-years").fill("10")
        page.locator("#calc-monthly_contribution").fill("500")
        page.locator("#calculate-button").click()
        expect(page.locator("#calculation-output")).to_contain_text("94,111.23")
        page.screenshot(path=str(screenshots / "calculator-compound.png"), full_page=True)
        page.locator("#tab-loan").click()
        page.locator("#calc-principal").fill("100000")
        page.locator("#calc-annual_rate").fill("6")
        page.locator("#calc-years").fill("30")
        page.locator("#calculate-button").click()
        expect(page.locator("#calculation-output")).to_contain_text("599.55")
        page.locator("#tab-budget").click()
        page.locator("#calc-income").fill("5000")
        page.locator("#calc-expenses").fill("6000")
        page.locator("#calculate-button").click()
        expect(page.locator("#calculation-output")).to_contain_text("-20%")
        page.locator("#calculator-dialog .close-dialog").click()
        checks.append("compound_loan_budget_forms_and_verified_results")

        page.locator("#nav-knowledge").click()
        expect(page.locator(".knowledge-card")).to_have_count(18)
        page.locator("#knowledge-dialog .close-dialog").click()
        page.locator("#language-toggle").click()
        expect(page.locator("html")).to_have_attribute("lang", "en")
        expect(page.locator("#engine-label")).to_contain_text("configured")
        checks.append("knowledge_catalogue_and_english_interface")

        # Forced outage tests draft preservation and user-facing error handling.
        page.route("**/api/chat", lambda route: route.fulfill(status=503, content_type="application/json", body='{"detail":"Synthetic browser outage"}'))
        page.locator("#message-input").fill("Keep this draft on failure")
        page.locator("#send-button").click()
        expect(page.locator("#error-banner")).to_contain_text("Synthetic browser outage")
        expect(page.locator("#message-input")).to_have_value("Keep this draft on failure")
        page.unroute("**/api/chat")
        checks.append("failed_request_keeps_draft_and_shows_error")

        page.locator("#top-new").click()
        payload = '<img src=x onerror="window.xssExecuted=true">'
        page.locator("#message-input").fill(payload)
        page.locator("#send-button").click()
        expect(page.locator(".message.assistant")).to_have_count(1)
        assert page.locator(".message.user img").count() == 0
        assert not page.evaluate("Boolean(window.xssExecuted)")
        expect(page.locator(".message.user .message-body")).to_have_text(payload)
        xss_sid = page.evaluate("localStorage.getItem('finpilot-session')")
        checks.append("untrusted_chat_text_not_executed_as_html")

        page.on("dialog", lambda dialog: dialog.accept())
        page.locator(".session-row.active .session-delete").click(force=True)
        expect(page.locator(".message")).to_have_count(0)
        checks.append("session_delete_updates_ui")

        mobile = context.new_page()
        mobile.set_viewport_size({"width": 390, "height": 844})
        mobile.goto(BASE + "/workspace", wait_until="networkidle")
        mobile.evaluate("localStorage.removeItem('finpilot-session')")
        mobile.reload(wait_until="networkidle")
        assert mobile.evaluate("document.documentElement.scrollWidth <= innerWidth")
        mobile.locator("#mobile-menu").click()
        expect(mobile.locator("#sidebar")).to_have_class("sidebar open")
        mobile.locator("#nav-calculator").click()
        expect(mobile.locator("#calculator-dialog")).to_be_visible()
        mobile.locator("#calculator-dialog .close-dialog").click()
        mobile.wait_for_timeout(300)  # Wait for the 200ms sidebar close transition before visual evidence.
        mobile.screenshot(path=str(screenshots / "home-mobile.png"), full_page=True)
        checks.append("mobile_layout_menu_and_calculator")

        for width in (320, 768, 1024):
            mobile.set_viewport_size({"width": width, "height": 900})
            assert mobile.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Horizontal overflow at {width}px"
        checks.append("responsive_no_horizontal_overflow_320_768_1024")

        reference = context.new_page()
        reference.goto(BASE + "/docs", wait_until="networkidle")
        assert reference.locator("#endpoints details").count() >= 8
        reference.locator("#run").click()
        expect(reference.locator("#response")).to_contain_text('"status": "ok"')
        checks.append("local_api_reference_and_request_tester")

        # Preserve one useful synthetic demo session; remove malicious test payload.
        context.request.delete(BASE + f"/api/sessions/{xss_sid}")
        browser.close()
    assert not errors, errors
    # HTTP503 is expected from the synthetic outage; other browser errors are reviewed.
    unexpected = [x for x in console_errors if "503" not in x]
    assert not unexpected, unexpected
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "passed", "checks": checks,
              "total": len(checks), "browser": "Microsoft Edge (headless Chromium)", "duration_seconds": round(time.perf_counter()-started, 2),
              "page_errors": errors, "console_errors": console_errors,
              "screenshots": [p.relative_to(ROOT).as_posix() for p in screenshots.glob("*.png")],
              "voice_validation": "Capability detection/UI only. Actual microphone and audible synthesis require manual testing on the presentation machine."}
    (ROOT / "reports" / "browser_check_v2.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
