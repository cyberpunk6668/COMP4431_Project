"""Workspace acceptance in real Edge on a running local FinPilot.

Actual backend tests cover calculators and sessions. The historical dark
profile can also send two billable DeepSeek questions. Use --theme light for
the Coinwise workspace; that profile always skips live chat and writes v5
artifacts. A separate mocked backend/speech context tests
failure, concurrent UI states and speech-event wiring. No local LLM is loaded.
Only sessions created by this run are deleted. This is not an accessibility
certification, financial accuracy benchmark, or microphone/audio hardware test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SOURCE = {"id": "compound-interest", "title": "复利 / Compound interest",
          "url": "https://www.investor.gov/financial-tools-calculators/calculators/compound-interest-calculator",
          "snippet": "Compound interest earns interest on the principal and accumulated interest. It does not guarantee market returns."}
MOCK_ANSWER = """## 有依据的回答

**复利**表示利息也参与计息。[compound-interest]

- 明确利率与期限。
- 核查费用和风险。

`FV = P(1+r)^n`

<img src=x onerror="window.xssExecuted=true"> [unknown-source]"""


def avatar_status(page):
    return page.evaluate("window.finPilotAvatarInstance?.getStatus() || null")


def ready(page):
    page.wait_for_function("typeof state !== 'undefined' && state.health && state.models.length > 0")
    expect(page.locator("#message-input")).to_be_visible()


def settle_visual(page):
    page.evaluate("document.activeElement?.blur(); window.scrollTo({top:0, behavior:'instant'})")
    if page.locator("#toast").count():
        expect(page.locator("#toast")).to_be_hidden(timeout=5000)
    page.wait_for_timeout(450)


def open_calculator(page):
    page.locator("#quick-calculate").click()
    expect(page.locator("#calculator-dialog")).to_be_visible()


def calculate(page, kind, fields):
    page.locator(f"#tab-{kind}").click()
    for name, value in fields.items():
        page.locator(f"#calc-{name}").fill(str(value))
    page.locator("#calculate-button").click()
    expect(page.locator("#calculation-output")).to_be_visible()
    expect(page.locator("#calculate-button")).to_be_enabled()


def mock_context(browser, base, checks, details, page_errors, screenshots):
    pending_chat, pending_calculations = [], []
    context = browser.new_context(viewport={"width": 1440, "height": 1050})
    context.add_init_script("""
      class FixtureRecognition {
        constructor(){ window.fixtureRecognition=this; }
        start(){ this.onstart?.(new Event('start')); }
        stop(){ this.onend?.(new Event('end')); }
        abort(){ this.onend?.(new Event('end')); }
      }
      Object.defineProperty(window,'SpeechRecognition',{configurable:true,value:FixtureRecognition});
    """)
    models = {"default": "deepseek", "models": [
        {"id": "deepseek", "label": "DeepSeek", "available": True, "configured": True},
        {"id": "local", "label": "Local LoRA", "available": False, "reason": "ml_runtime_missing"},
    ]}

    def respond(route):
        path = urlsplit(route.request.url).path
        if path == "/api/chat":
            pending_chat.append(route)
            return
        if path == "/api/calculate":
            pending_calculations.append(route)
            return
        value = {"/api/health": {"status": "ok", "mode": "deepseek", "model": "deepseek-flash", "knowledge_documents": 18},
                 "/api/models": models, "/api/sessions": {"sessions": []},
                 "/api/knowledge": {"documents": [{**SOURCE, "category": "education", "updated_at": "2026-11-10"}]}}.get(path, {})
        route.fulfill(status=200, content_type="application/json", body=json.dumps(value, ensure_ascii=False))

    context.route("**/api/**", respond)
    page = context.new_page()
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.goto(base + "/workspace", wait_until="networkidle")
    ready(page)
    page.wait_for_function("window.finPilotAvatarInstance?.getStatus().actualMode === '3d'", timeout=20000)
    assert page.locator('#model-select option[value="local"]').evaluate("el=>el.disabled")
    expect(page.locator('#model-select option[value="local"]')).to_contain_text("未就绪")
    expect(page.locator("#model-description")).not_to_contain_text("implementation")
    checks.append("unavailable_local_model_is_disabled_and_explained")

    page.locator("#message-input").fill("   ")
    page.locator("#send-button").click()
    assert not pending_chat and page.locator(".message.user").count() == 0
    page.locator('.prompt-card[data-prompt="risk"]').click()
    assert len(page.locator("#message-input").input_value()) > 5
    assert not pending_chat and page.locator(".message.user").count() == 0
    checks.append("empty_input_is_ignored_and_sample_only_fills_an_editable_draft")

    page.locator("#message-input").fill('<img src=x onerror="window.xssExecuted=true">')
    page.locator("#send-button").click()
    expect(page.locator("body")).to_have_attribute("data-assistant-state", "thinking")
    expect(page.locator("#model-select")).to_be_disabled()
    expect(page.locator("#mic-button")).to_be_disabled()
    expect(page.locator("#send-button")).to_be_disabled()
    expect(page.locator("#chat-status")).to_be_visible()
    expect(page.locator("#chat-form")).to_have_attribute("aria-busy", "true")
    assert pending_chat and pending_chat[0].request.post_data_json["engine"] == "deepseek"
    # New-session navigation must either disable the control or preserve the
    # pending conversation with a clear busy guard.
    if not page.locator("#top-new").is_disabled():
        page.locator("#top-new").click()
        assert page.locator(".message.user").count() == 1
    pending_chat.pop(0).fulfill(status=200, content_type="application/json", body=json.dumps({"session_id": "fixture-v4", "answer": MOCK_ANSWER, "sources": [SOURCE], "mode": "deepseek"}, ensure_ascii=False))
    expect(page.locator(".message.assistant")).to_have_count(1)
    expect(page.locator("body")).to_have_attribute("data-assistant-state", "idle")
    expect(page.locator("#model-select")).to_be_enabled()
    assert page.locator(".message.assistant strong").first.text_content() == "复利"
    assert page.locator(".message.assistant li").count() == 2
    assert page.locator(".message-body img").count() == 0
    assert not page.evaluate("Boolean(window.xssExecuted)")
    sizes = page.evaluate("Object.fromEntries(['.message.assistant .message-body','#model-description','.copilot-intro'].map(s=>[s,parseFloat(getComputedStyle(document.querySelector(s)).fontSize)]))")
    assert sizes[".message.assistant .message-body"] >= 14
    assert sizes["#model-description"] >= 12 and sizes[".copilot-intro"] >= 12
    details["reading_sizes_px"] = sizes
    expect(page.locator(".inline-citation")).to_have_attribute("href", SOURCE["url"])
    page.locator(".source-preview summary").click()
    expect(page.locator(".source-preview p")).to_be_visible()
    checks.extend(["pending_chat_locks_engine_and_preserves_navigation_context", "chat_completion_returns_avatar_and_controls_to_idle", "safe_rich_text_and_expandable_matching_sources", "primary_body_and_model_descriptions_have_readable_sizes"])
    settle_visual(page)
    page.screenshot(path=str(screenshots / "chat-desktop.png"), full_page=True, animations="disabled")

    page.locator("#mic-button").click()
    expect(page.locator("body")).to_have_attribute("data-assistant-state", "listening")
    assert avatar_status(page)["state"] == "listening"
    page.locator("#mic-button").click()
    expect(page.locator("body")).to_have_attribute("data-assistant-state", "idle")
    page.evaluate("Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{speak(u){window.fixtureUtterance=u;u.onstart(new Event('start'));},cancel(){}}})")
    page.locator("#avatar-read-last").click()
    expect(page.locator("body")).to_have_attribute("data-assistant-state", "speaking")
    assert avatar_status(page)["state"] == "speaking"
    page.evaluate("window.fixtureUtterance.onend(new Event('end'))")
    expect(page.locator("body")).to_have_attribute("data-assistant-state", "idle")
    checks.append("mock_speech_events_drive_listening_speaking_and_idle")

    page.locator("#message-input").fill("Keep this draft after a synthetic outage")
    page.locator("#send-button").click()
    expect(page.locator("#avatar-read-last")).to_be_disabled()
    for action in page.locator('.message-action[data-action="speak"]').all():
        expect(action).to_be_disabled()
    page.evaluate("window.fixtureUtterance=null;readAloud('Synthetic busy-state attempt')")
    expect(page.locator("body")).to_have_attribute("data-assistant-state", "thinking")
    assert page.evaluate("window.fixtureUtterance") is None
    pending_chat.pop(0).fulfill(status=503, content_type="application/json", body='{"detail":"Synthetic QA outage"}')
    expect(page.locator("body")).to_have_attribute("data-assistant-state", "error")
    expect(page.locator("#message-input")).to_have_value("Keep this draft after a synthetic outage")
    expect(page.locator("#error-banner")).to_contain_text("Synthetic QA outage")
    expect(page.locator("#send-button")).to_be_enabled()
    checks.extend(["pending_answer_blocks_previous_answer_speech_including_programmatic_attempt", "failed_chat_displays_error_and_keeps_draft"])

    # Reload a synthetic catalogue with a ready local model. No local inference
    # worker is started in this test; the request body and returned mode matter.
    models["models"][1]["available"] = True
    page.reload(wait_until="networkidle")
    ready(page)
    page.locator("#model-select").select_option("local")
    expect(page.locator("#model-description")).to_contain_text("实验")
    if page.locator("#model-switch-status").count():
        expect(page.locator("#model-switch-status")).to_contain_text(re.compile("本地|LoRA"))
    assert page.evaluate("state.engine") == "local"
    page.locator("#message-input").fill("What is compound interest?")
    page.locator("#send-button").click()
    expect(page.locator("body")).to_have_attribute("data-assistant-state", "thinking")
    assert pending_chat[0].request.post_data_json["engine"] == "local"
    pending_chat.pop(0).fulfill(status=200, content_type="application/json", body=json.dumps({"session_id": "fixture-local-v4", "answer": MOCK_ANSWER, "sources": [SOURCE], "mode": "local-lora"}, ensure_ascii=False))
    expect(page.locator(".message-mode")).to_contain_text("LoRA")
    checks.append("model_switch_confirmation_request_contract_and_actual_mode_badge")
    page.locator("#model-select").select_option("deepseek")
    assert page.evaluate("state.engine") == "deepseek"
    expect(page.locator("#model-name")).to_contain_text("DeepSeek")
    expect(page.locator("#model-switch-status")).to_contain_text("DeepSeek")
    page.locator("#model-select").select_option("local")

    open_calculator(page)
    page.locator("#calculate-button").click()
    expect(page.locator("#calculate-button")).to_be_disabled()
    assert pending_calculations
    if page.locator("#tab-loan").is_disabled():
        # Locking the calculation tabs is a valid way of preventing stale output.
        details["calculator_pending_strategy"] = "tabs_disabled"
    else:
        page.locator("#tab-loan").click()
        details["calculator_pending_strategy"] = "request_generation_guard"
    pending_calculations.pop(0).fulfill(status=200, content_type="application/json", body=json.dumps({"kind": "compound", "summary": "OLD COMPOUND REQUEST", "values": {"future_value": "999999.00"}, "series": [], "formula": "old", "assumptions": []}))
    if details["calculator_pending_strategy"] == "request_generation_guard":
        page.wait_for_timeout(350)
        assert "OLD COMPOUND REQUEST" not in page.locator("#calculation-output").inner_text()
    expect(page.locator("#calculate-button")).to_be_enabled()
    page.locator("#calculator-dialog .close-dialog").click()
    checks.append("calculator_delayed_response_cannot_replace_another_tool")

    open_calculator(page)
    page.locator("#tab-compound").click()
    page.locator("#calculate-button").click()
    expect(page.locator("#calculate-button")).to_be_disabled()
    assert pending_calculations
    page.locator("#calc-annual_rate").fill("7")
    expect(page.locator("#calculate-button")).to_be_enabled()
    pending_calculations.pop(0).fulfill(status=200, content_type="application/json", body=json.dumps({"kind": "compound", "summary": "OLD PARAMETER REQUEST", "values": {"future_value": "999999.00"}, "series": [], "formula": "old", "assumptions": []}))
    page.wait_for_timeout(300)
    expect(page.locator("#calculation-output")).to_be_hidden()
    page.locator("#calculate-button").click()
    expect(page.locator("#calculate-button")).to_be_disabled()
    pending_calculations.pop(0).fulfill(status=200, content_type="application/json", body=json.dumps({"kind": "compound", "summary": "CURRENT PARAMETER REQUEST", "values": {"future_value": "94111.23"}, "series": [], "formula": "test", "assumptions": []}))
    expect(page.locator("#calculation-output")).to_be_visible()
    page.locator("#calc-annual_rate").fill("8")
    expect(page.locator("#calculation-output")).to_be_hidden()
    checks.append("editing_parameters_discards_inflight_and_previously_displayed_calculations")
    page.locator("#calc-principal").fill("-1")
    page.locator("#calculate-button").click()
    assert not pending_calculations
    assert not page.locator("#calc-principal").evaluate("el=>el.checkValidity()")
    page.locator("#calculator-dialog .close-dialog").click()
    checks.append("calculator_rejects_invalid_principal_before_network_request")

    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(250)
    if page.locator("#copilot-content").is_visible():
        page.locator("#avatar-collapse").click()
    settle_visual(page)
    page.screenshot(path=str(screenshots / "chat-mobile.png"), full_page=True, animations="disabled")
    page.locator("#avatar-collapse").click()
    expect(page.locator("#avatar-stage")).to_be_visible()
    settle_visual(page)
    page.screenshot(path=str(screenshots / "avatar-mobile.png"), full_page=True, animations="disabled")
    checks.append("mobile_chat_and_expandable_companion_remain_accessible")
    models["models"][0]["available"] = False
    models["default"] = "local"
    page.reload(wait_until="networkidle")
    ready(page)
    assert page.locator('#model-select option[value="deepseek"]').evaluate("el=>el.disabled")
    expect(page.locator("#model-select")).to_have_value("local")
    checks.append("both_models_switch_bidirectionally_and_unavailable_cloud_is_disabled")
    context.close()


def real_context(browser, base, checks, layouts, details, page_errors, console_errors, skip_live, theme, version, screenshots):
    context = browser.new_context(viewport={"width": 1440, "height": 1050}, accept_downloads=True)
    alternate_theme = "dark" if theme == "light" else "light"
    old_skin = "gold-v4" if theme == "light" else ""
    skin = "coinwise-v5" if theme == "light" else "gold-v4"
    # Seed the previous workspace skin and theme in the isolated browser profile.
    context.add_init_script(f"""if (!sessionStorage.getItem('qa-seeded')) {{
        localStorage.setItem('finpilot-theme', {json.dumps(alternate_theme)});
        localStorage.setItem('finpilot-workspace-skin', {json.dumps(old_skin)});
        sessionStorage.setItem('qa-seeded', '1');
    }}""")
    unexpected_chats = []
    if skip_live:
        def block_chat(route):
            unexpected_chats.append(route.request.method)
            route.abort()

        context.route("**/api/chat", block_chat)
    page = context.new_page()
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.goto(base + "/workspace", wait_until="networkidle")
    ready(page)
    expect(page.locator("html")).to_have_attribute("data-theme", theme)
    assert page.evaluate("localStorage.getItem('finpilot-workspace-skin')") == skin
    page.wait_for_function("window.finPilotAvatarInstance?.getStatus().actualMode === '3d'", timeout=20000)
    details["initial_avatar"] = avatar_status(page)
    assert details["initial_avatar"]["renderer"] == "webgl2"
    palette = page.evaluate("({background:getComputedStyle(document.body).backgroundColor,accent:getComputedStyle(document.documentElement).getPropertyValue('--gold').trim(),font:getComputedStyle(document.body).fontFamily})")
    details["palette"] = palette
    assert "inter" in palette["font"].lower(), palette
    # Palette token name is documented so the test does not mistake a green
    # legacy theme with a merely gold button for a complete visual migration.
    if theme == "light":
        assert palette["accent"].lower() in {"#d4af37", "rgb(212, 175, 55)"}, palette
        assert palette["background"] == "rgb(250, 250, 250)", palette
        checks.append("prior_gold_v4_theme_migrates_to_coinwise_v5_light_palette")
    else:
        assert palette["accent"].lower() in {"#dba85a", "#d4af37", "rgb(219, 168, 90)"}, palette
        assert all(int(channel) < 35 for channel in re.findall(r"\d+", palette["background"])[:3]), palette
        checks.append("existing_light_preference_migrates_to_unified_dark_gold")
    checks.append("actual_webgl2_avatar_and_local_brand_font")
    external_assets = page.evaluate("performance.getEntriesByType('resource').map(e=>e.name).filter(u=>!u.startsWith(location.origin)&&!u.startsWith('data:'))")
    assert not external_assets, external_assets
    details["workspace_external_assets"] = external_assets
    checks.append("workspace_fonts_and_graphics_load_locally_without_cdn_assets")
    settle_visual(page)
    page.screenshot(path=str(screenshots / "workspace-desktop.png"), full_page=True, animations="disabled")
    if theme == "dark":
        homepage = context.new_page()
        homepage.goto(base + "/", wait_until="networkidle")
        home_palette = homepage.evaluate("({accent:getComputedStyle(document.documentElement).getPropertyValue('--gold').trim(),font:getComputedStyle(document.body).fontFamily})")
        assert home_palette["accent"].lower() == palette["accent"].lower(), home_palette
        assert "inter" in home_palette["font"].lower(), home_palette
        details["homepage_palette"] = home_palette
        homepage.close()
        checks.append("homepage_and_workspace_share_gold_token_and_inter_typeface")
    page.locator("#theme-toggle").click()
    expect(page.locator("html")).to_have_attribute("data-theme", alternate_theme)
    page.reload(wait_until="networkidle")
    ready(page)
    expect(page.locator("html")).to_have_attribute("data-theme", alternate_theme)
    page.locator("#theme-toggle").click()
    expect(page.locator("html")).to_have_attribute("data-theme", theme)
    page.wait_for_function("window.finPilotAvatarInstance?.getStatus().actualMode === '3d'")
    checks.append("post_migration_explicit_theme_choice_survives_reload")

    page.locator("#avatar-2d").click()
    page.wait_for_function("window.finPilotAvatarInstance.getStatus().actualMode === '2d'")
    page.locator("#avatar-3d").click()
    page.wait_for_function("window.finPilotAvatarInstance.getStatus().actualMode === '3d'")
    pause = page.locator("#workspace-motion-toggle")
    pause.click()
    expect(pause).to_have_attribute("aria-pressed", "true")
    expect(page.locator("html")).to_have_attribute("data-motion", "reduced")
    page.wait_for_timeout(200)
    before = avatar_status(page)["frames"]
    page.wait_for_timeout(450)
    assert avatar_status(page)["frames"] == before
    infinite_running = page.evaluate("document.getAnimations().filter(a=>a.playState==='running'&&a.effect?.getTiming().iterations===Infinity).length")
    assert infinite_running == 0, infinite_running
    pause.click()
    expect(pause).to_have_attribute("aria-pressed", "false")
    page.wait_for_timeout(200)
    before = avatar_status(page)["frames"]
    page.wait_for_timeout(450)
    assert avatar_status(page)["frames"] > before
    checks.extend(["two_and_three_dimensional_avatar_modes", "workspace_pause_stops_and_resumes_nonessential_motion"])

    for language in ("zh", "en"):
        if page.locator("html").get_attribute("lang") != ("zh-CN" if language == "zh" else "en"):
            page.locator("#language-toggle").click()
        for width in (320, 390, 768, 1024, 1440, 1920):
            page.set_viewport_size({"width": width, "height": 1050 if width >= 768 else 844})
            page.wait_for_timeout(200)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Overflow at {language}/{width}"
            expect(page.locator("#message-input")).to_be_visible()
            open_calculator(page)
            box = page.locator("#calculator-dialog").bounding_box()
            assert box and box["x"] >= 0 and box["x"] + box["width"] <= width + 1, box
            page.locator("#calculator-dialog .close-dialog").click()
            layouts.append({"language": language, "width": width, "workspace": "passed", "calculator_dialog": "passed"})
    page.locator("#language-toggle").click()
    checks.append("six_responsive_widths_in_both_languages_keep_chat_and_calculator_in_view")

    page.set_viewport_size({"width": 390, "height": 844})
    settle_visual(page)
    page.screenshot(path=str(screenshots / "workspace-mobile.png"), full_page=True, animations="disabled")
    page.locator("#mobile-menu").click()
    expect(page.locator("#mobile-menu")).to_have_attribute("aria-expanded", "true")
    page.keyboard.press("Escape")
    expect(page.locator("#mobile-menu")).to_have_attribute("aria-expanded", "false")
    assert page.evaluate("document.activeElement?.id") == "mobile-menu"
    page.locator("#mobile-menu").click()
    sidebar_ids = page.evaluate("Array.from(document.querySelectorAll('#sidebar a,#sidebar button')).filter(e=>!e.disabled&&e.getClientRects().length).map(e=>e.id||e.className)")
    for _ in range(len(sidebar_ids) + 3):
        page.keyboard.press("Tab")
        assert page.evaluate("Boolean(document.activeElement?.closest('#sidebar')) || document.activeElement?.id==='mobile-menu'")
    page.locator("#sidebar-shade").click(position={"x": 375, "y": 300}, force=True)
    expect(page.locator("#mobile-menu")).to_have_attribute("aria-expanded", "false")
    page.locator("#mobile-menu").click()
    page.locator("#nav-knowledge").click()
    expect(page.locator("#knowledge-dialog")).to_be_visible()
    expect(page.locator(".knowledge-card")).to_have_count(18)
    page.locator("#knowledge-dialog .close-dialog").click()
    checks.append("mobile_navigation_escape_focus_cycle_backdrop_and_knowledge")

    page.set_viewport_size({"width": 1440, "height": 1050})
    open_calculator(page)
    page.locator("#tab-compound").focus()
    page.keyboard.press("ArrowRight")
    expect(page.locator("#tab-loan")).to_have_attribute("aria-selected", "true")
    checks.append("calculator_tabs_support_arrow_keyboard_navigation")
    calculate(page, "compound", {"principal": 10000, "annual_rate": 5, "years": 10, "monthly_contribution": 500})
    expect(page.locator("#calculation-output")).to_contain_text("94,111.23")
    page.screenshot(path=str(screenshots / "calculator-desktop.png"), full_page=True, animations="disabled")
    calculate(page, "compound", {"principal": 10000, "annual_rate": 0, "years": 10, "monthly_contribution": 500})
    expect(page.locator("#calculation-output")).to_contain_text("70,000.00")
    calculate(page, "loan", {"principal": 100000, "annual_rate": 6, "years": 30})
    expect(page.locator("#calculation-output")).to_contain_text("599.55")
    calculate(page, "budget", {"income": 5000, "expenses": 6000})
    expect(page.locator("#calculation-output")).to_contain_text("-20%")
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(screenshots / "calculator-mobile.png"), full_page=True, animations="disabled")
    page.locator("#calculator-dialog .close-dialog").click()
    checks.append("actual_compound_zero_rate_loan_and_negative_budget_results")

    # Actual CRUD is independent of cloud connectivity. Keep a precise allowlist
    # of this run's sessions; older/user-created sessions are never deleted.
    owned = []
    try:
        stamp = str(time.time_ns())[-10:]
        session_a = context.request.post(base + "/api/sessions", data={"title": f"QA-{version}-A-{stamp}"}).json()
        owned.append(session_a["id"])
        session_b = context.request.post(base + "/api/sessions", data={"title": f"QA-{version}-B-{stamp}"}).json()
        owned.append(session_b["id"])
        page.set_viewport_size({"width": 1440, "height": 1050})
        page.reload(wait_until="networkidle")
        ready(page)
        page.locator(".session-open").filter(has_text=session_a["title"]).click()
        page.wait_for_function("id=>state.sessionId===id", arg=session_a["id"])
        expect(page.locator(".message")).to_have_count(0)
        checks.append("actual_sessions_are_created_and_selected_without_touching_user_data")
        if not skip_live:
            page.locator("#model-select").select_option("deepseek")
            questions = [
                ("zh", f"QA v4 {stamp}：什么是复利？请说明限制并引用来源。", "compound-interest"),
                ("en", "Explain diversification and why it cannot remove every investment risk. Cite your references.", "diversification"),
            ]
            live = []
            for index, (language, question, expected_id) in enumerate(questions):
                width = 1440 if index == 0 else 390
                page.set_viewport_size({"width": width, "height": 1050 if index == 0 else 844})
                if page.locator("html").get_attribute("lang") != ("zh-CN" if language == "zh" else "en"):
                    page.locator("#language-toggle").click()
                page.locator("#message-input").fill(question)
                start = time.perf_counter()
                page.locator("#send-button").click()
                expect(page.locator(".message.assistant")).to_have_count(index + 1, timeout=70000)
                expect(page.locator(".message-mode").last).to_contain_text("DeepSeek")
                expect(page.locator("#send-button")).to_be_enabled()
                expect(page.locator("body")).to_have_attribute("data-assistant-state", "idle")
                citations = page.locator(".message.assistant").last.locator(".inline-citation")
                assert citations.count() >= 1
                assert expected_id in page.locator(".message.assistant").last.inner_text()
                live.append({"language": language, "mode": "deepseek", "expected_source": expected_id,
                             "viewport_width": width,
                             "latency_ms": round((time.perf_counter() - start) * 1000, 2)})
                settle_visual(page)
                page.screenshot(path=str(screenshots / ("live-chat-desktop.png" if index == 0 else "live-chat-mobile.png")), full_page=True, animations="disabled")
            details["live_chat"] = live
            checks.append("two_actual_deepseek_bilingual_answers_have_visible_sources_and_idle_recovery")
            with page.expect_download() as download:
                page.locator("#export-button").click()
            exported = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
            assert exported["id"] == session_a["id"] and len(exported["messages"]) == 4
            assert not re.search(r"sk-[A-Za-z0-9_-]{20,}", json.dumps(exported))
            page.reload(wait_until="networkidle")
            expect(page.locator(".message.assistant")).to_have_count(2)
            checks.extend(["downloaded_json_matches_actual_conversation_without_credentials", "actual_conversation_restores_after_reload"])
        else:
            details["live_chat"] = "Skipped; the chat endpoint is blocked in the real-backend browser context."
            with page.expect_download() as download:
                page.locator("#export-button").click()
            exported = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
            assert exported["id"] == session_a["id"] and exported["messages"] == []
            checks.append("actual_empty_test_session_exports_as_json_without_model_inference")

        page.set_viewport_size({"width": 1440, "height": 1050})
        page.locator("#top-new").click()
        expect(page.locator(".message")).to_have_count(0)
        assert page.evaluate("state.sessionId") is None
        page.locator(".session-open").filter(has_text=session_b["title"]).click()
        page.wait_for_function("id=>state.sessionId===id", arg=session_b["id"])
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator(".session-row.active .session-delete").click(force=True)
        expect(page.locator(".message")).to_have_count(0)
        assert context.request.get(base + f"/api/sessions/{session_b['id']}").status == 404
        owned.remove(session_b["id"])
        checks.append("new_conversation_and_actual_delete_update_workspace")
    finally:
        for sid in owned:
            context.request.delete(base + "/api/sessions/" + sid)
    if skip_live:
        assert not unexpected_chats, unexpected_chats
        details["unmocked_chat_attempts"] = len(unexpected_chats)
        checks.append("no_unmocked_model_requests")
    context.close()


def touch_context(browser, base, checks, theme, screenshots, page_errors, console_errors):
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.goto(base + "/workspace", wait_until="networkidle")
    ready(page)
    expect(page.locator("html")).to_have_attribute("data-theme", theme)
    assert page.evaluate("matchMedia('(pointer: coarse)').matches")
    page.locator("#mobile-menu").tap()
    expect(page.locator("#mobile-menu")).to_have_attribute("aria-expanded", "true")
    page.locator("#sidebar-shade").tap(position={"x": 375, "y": 300}, force=True)
    expect(page.locator("#mobile-menu")).to_have_attribute("aria-expanded", "false")
    page.locator("#quick-calculate").tap()
    expect(page.locator("#calculator-dialog")).to_be_visible()
    page.locator("#calculator-dialog .close-dialog").tap()
    if not page.locator("#copilot-content").is_visible():
        page.locator("#avatar-collapse").tap()
    expect(page.locator("#avatar-stage")).to_be_visible()
    settle_visual(page)
    page.screenshot(path=str(screenshots / "touch-mobile.png"), full_page=True, animations="disabled")
    checks.append("touch_emulation_supports_navigation_backdrop_calculator_and_companion")
    context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--theme", choices=("dark", "light"), default="dark",
                        help="Use light for Coinwise v5, with no live model requests.")
    parser.add_argument("--skip-live-chat", action="store_true")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    if urlsplit(base).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Use the local application server.")
    version = "v5" if args.theme == "light" else "v4"
    skip_live = args.skip_live_chat or args.theme == "light"
    screenshots = ROOT / "reports" / "screenshots" / f"workspace-{version}"
    screenshots.mkdir(parents=True, exist_ok=True)
    report_path = ROOT / "reports" / f"workspace_check_{version}.json"
    checks, layouts, details, errors, console_errors = [], [], {}, [], []
    start = time.perf_counter()
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "running",
              "version": f"{version}-workspace", "theme": args.theme,
              "scope": {"actual_backend": "calculator and isolated synthetic-session CRUD", "cloud_generation": "skipped" if skip_live else "two real DeepSeek calls", "fixture_context": "mocked chat, calculator delay, model availability and browser speech events", "local_llm": "not loaded", "speech_hardware": "not tested"}}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            report["environment"] = {"browser_channel": "msedge", "browser_version": browser.version,
                                     "headless": True, "platform": "Windows", "base": base}
            # Mock phase precedes cloud calls so functional failures do not cause
            # unnecessary billable questions on repeated development runs.
            mock_context(browser, base, checks, details, errors, screenshots)
            real_context(browser, base, checks, layouts, details, errors, console_errors,
                         skip_live, args.theme, version, screenshots)
            touch_context(browser, base, checks, args.theme, screenshots, errors, console_errors)
            reduced_context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
            reduced = reduced_context.new_page()
            reduced.on("pageerror", lambda error: errors.append(str(error)))
            reduced.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
            reduced.goto(base + "/workspace", wait_until="networkidle")
            ready(reduced)
            reduced.wait_for_function("window.finPilotAvatarInstance?.getStatus().actualMode === '3d'")
            assert avatar_status(reduced)["reducedMotion"]
            expect(reduced.locator("html")).to_have_attribute("data-motion", "reduced")
            before = avatar_status(reduced)["frames"]
            reduced.wait_for_timeout(450)
            assert avatar_status(reduced)["frames"] == before
            checks.append("system_reduced_motion_preserves_reading_and_static_avatar")
            reduced_context.close()
            browser.close()
        assert not errors, errors
        assert not console_errors, console_errors
        report.update(status="passed", checks=checks, total=len(checks), layouts=layouts, layout_count=len(layouts), details=details,
                      page_errors=errors, normal_console_errors=console_errors)
    except Exception as error:
        report.update(status="failed", error=str(error) or type(error).__name__, error_type=type(error).__name__, checks=checks, total=len(checks), layouts=layouts, details=details, page_errors=errors, normal_console_errors=console_errors)
        raise
    finally:
        report["duration_seconds"] = round(time.perf_counter() - start, 2)
        paths = ["web/index.html", "web/styles.css", "web/app.js", "web/avatar.js", "web/avatar.css"]
        if version == "v4":
            paths.append("frontend/src/styles.css")
        report["source_sha256"] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}
        report["screenshots"] = [path.relative_to(ROOT).as_posix() for path in sorted(screenshots.glob("*.png"))]
        report["screenshot_provenance"] = {"chat-desktop.png": "mock chat response", "chat-mobile.png": "mock local response", "avatar-mobile.png": "real 3D with mock chat response", "workspace-desktop.png": "actual local APIs", "workspace-mobile.png": "actual local APIs", "calculator-desktop.png": "actual formula endpoint", "calculator-mobile.png": "actual formula endpoint", "touch-mobile.png": "actual local APIs and emulated touch"}
        if not skip_live:
            report["screenshot_provenance"]["live-chat-desktop.png"] = "actual DeepSeek Chinese response"
            report["screenshot_provenance"]["live-chat-mobile.png"] = "actual DeepSeek English response"
        if (screenshots / "local-lora-chat.png").exists():
            report["screenshot_provenance"]["local-lora-chat.png"] = "independent actual local LoRA run; see reports/browser_local_check_v4.json"
        earlier_reports = ["reports/avatar_gold_check_v4.json", "reports/browser_local_check_v4.json"]
        if version == "v5":
            report["historical_evidence"] = ["reports/workspace_check_v4.json", *earlier_reports]
        else:
            report["related_reports"] = earlier_reports
        report["verification_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        report["limits"] = ["One Windows/Edge environment; no general device-performance guarantee or full accessibility certification.", "Mock speech events verify state wiring, not microphone recognition or audible speech.", "Model response modes and source presence do not prove general financial factual accuracy."]
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "total", "layout_count", "page_errors", "duration_seconds")}, indent=2))


if __name__ == "__main__":
    main()
