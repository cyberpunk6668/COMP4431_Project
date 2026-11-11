"""Actual browser acceptance for the animated FinPilot showcase.

Run the built FastAPI app first. Uses Edge; does not submit chat or load the
local model. These checks are not an award, accessibility certification or a
representative performance benchmark.
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
SCREENSHOTS = ROOT / "reports" / "screenshots" / "showcase"


def main() -> int:
    global SCREENSHOTS
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--report-name", default="showcase_check.json")
    parser.add_argument("--screenshots-name", default="showcase")
    args = parser.parse_args()
    if Path(args.report_name).name != args.report_name or Path(args.screenshots_name).name != args.screenshots_name:
        parser.error('Report and screenshot names must be plain filenames.')
    SCREENSHOTS = ROOT / 'reports' / 'screenshots' / args.screenshots_name
    base = args.base.rstrip("/")
    origin = urlsplit(base).netloc
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    checks, layouts, errors, console_errors, remote_requests, forbidden_chat = [], [], [], [], [], []
    expected_fault_console_errors, expected_fault_requests = [], []
    details = {}
    started = time.perf_counter()
    report = {"status": "running", "checked_at": datetime.now(timezone.utc).isoformat(),
              "scope": "Actual Edge browser and local APIs. No chat requests, cloud billing, local LLM inference or simulated financial market data.",
              "base": base, "browser": "Microsoft Edge / Chromium (headless)"}
    page = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)

            def check_request(request):
                parsed = urlsplit(request.url)
                if parsed.scheme in {"http", "https"} and parsed.netloc != origin:
                    remote_requests.append(request.url)
                if parsed.path == "/api/chat":
                    forbidden_chat.append(request.url)
            context.on("request", check_request)
            response = page.goto(base + "/", wait_until="networkidle")
            assert response and response.status == 200
            assert "unsafe-eval" not in response.headers.get("content-security-policy", "")
            expect(page.locator("#hero h1")).to_be_visible()
            page.wait_for_function("document.querySelector('[data-testid=signal-scene]')?.dataset.renderer === 'webgl2'", timeout=20000)
            page.wait_for_timeout(1800)
            heading = page.locator("#hero h1").inner_text()
            assert heading.strip(), "Hero heading is empty"
            assert page.locator("#hero").evaluate("element => getComputedStyle(element).opacity") == "1"
            assert float(page.locator("#hero h1").evaluate("element => getComputedStyle(element).opacity")) > 0.95
            checks.append("built_homepage_and_readable_hero_under_real_csp")
            checks.append("genuine_webgl2_hero_renderer")
            scene = page.get_by_test_id("signal-scene")
            frames = lambda: int(scene.get_attribute("data-frames") or 0)
            before = frames()
            page.wait_for_timeout(650)
            after = frames()
            assert after > before, "Visible hero scene did not animate"
            details["observed_hero_draws_in_650ms"] = after - before
            checks.append("hero_animation_draws_frames")
            page.screenshot(path=str(SCREENSHOTS / "hero-desktop.png"), animations="disabled")

            motion_toggle = page.get_by_test_id("motion-toggle")
            motion_toggle.click()
            expect(motion_toggle).to_have_attribute("aria-pressed", "true")
            page.wait_for_timeout(200)
            before = frames()
            page.wait_for_timeout(500)
            assert frames() == before, "Pause did not stop hero rendering"
            infinite = page.evaluate("""() => document.getAnimations().filter(a =>
                a.playState === 'running' && a.effect?.getTiming().iterations === Infinity).length""")
            assert infinite == 0, "An infinite CSS animation still runs while motion is paused"
            checks.append("global_pause_stops_nonessential_motion")
            motion_toggle.click()
            expect(motion_toggle).to_have_attribute("aria-pressed", "false")
            page.wait_for_timeout(250)
            before = frames()
            page.wait_for_timeout(400)
            assert frames() > before, "Resume did not restart visible hero rendering"
            checks.append("motion_resume_works")

            for progress, expected_stage in ((0.1, 0), (0.62, 2), (0.9, 3)):
                page.evaluate("""progress => { const section=document.querySelector('#experience');
                    const top=scrollY+section.getBoundingClientRect().top-96;
                    scrollTo({top:top+(section.offsetHeight-innerHeight+96)*progress,behavior:'instant'});
                }""", progress)
                page.wait_for_timeout(250)
                expect(page.get_by_test_id(f"story-step-{expected_stage}")).to_have_attribute("aria-selected", "true")
            checks.append("native_scroll_drives_four_stage_feature_story")
            page.wait_for_timeout(500)
            page.screenshot(path=str(SCREENSHOTS / "story-desktop.png"), animations="disabled")

            page.locator("#evidence").scroll_into_view_if_needed()
            expect(page.locator("#evidence")).to_be_visible()
            links = page.locator('#evidence a[href^="https://"]')
            assert links.count() > 0, "No traceable evidence link is rendered"
            knowledge = context.request.get(base + "/api/knowledge").json()["documents"]
            approved = {document["url"] for document in knowledge}
            for href in links.evaluate_all("elements => elements.map(e => e.href)"):
                assert href in approved, f"Unverified evidence link: {href}"
            checks.append("evidence_links_match_curated_knowledge_metadata")
            page.wait_for_timeout(1100)
            page.screenshot(path=str(SCREENSHOTS / "evidence-desktop.png"), animations="disabled")

            page.locator("#planning").scroll_into_view_if_needed()
            page.wait_for_timeout(350)
            before = frames()
            page.wait_for_timeout(500)
            assert frames() == before, "Offscreen hero keeps rendering"
            checks.append("offscreen_hero_rendering_stops")
            expect(page.get_by_test_id("calc-result")).to_contain_text("94,111.23", timeout=15000)
            backend = context.request.post(base + "/api/calculate", data={"kind": "compound", "principal": 10000,
                "annual_rate": 5, "years": 10, "monthly_contribution": 500}).json()
            assert backend["values"]["future_value"] == "94111.23"
            checks.append("showcase_calculator_uses_verified_backend_result")
            rate = page.locator("#calc-rate")
            minimum = float(rate.get_attribute("min") or 0)
            rate.focus()
            rate.press("Home")
            expected = context.request.post(base + "/api/calculate", data={"kind": "compound", "principal": 10000,
                "annual_rate": minimum, "years": 10, "monthly_contribution": 500}).json()["values"]["future_value"]
            expect(page.get_by_test_id("calc-result")).to_contain_text(f"{float(expected):,.2f}", timeout=15000)
            checks.append("calculator_keyboard_input_reaches_live_api")
            page.wait_for_timeout(1100)
            page.screenshot(path=str(SCREENSHOTS / "calculator-desktop.png"), animations="disabled")
            page.locator("#calc-principal").fill("0")
            page.locator("#calc-monthly").focus()
            page.locator("#calc-monthly").press("Home")
            expect(page.get_by_test_id("calc-result")).to_have_text(re.compile(r"^\s*¥?\s*0\.00\s*$"), timeout=15000)
            endpoint = page.locator("#planning .balance-chart circle")
            assert endpoint.count() == 0 or float(endpoint.first.get_attribute("cy")) == 218, "Zero result chart endpoint is inconsistent with its flat line"
            checks.append("zero_balance_scenario_has_consistent_chart_endpoint")

            for destination in ("#experience", "#intelligence", "#start"):
                page.locator(destination).scroll_into_view_if_needed()
                expect(page.locator(destination)).to_be_visible()
            checks.append("all_feature_chapters_remain_reachable")
            video = page.locator("#start video")
            if video.count():
                assert video.evaluate("element => element.muted && element.playsInline")
                # Keep the closing visual in view while dispatching the same
                # global control action, regardless of header scroll position.
                motion_toggle.evaluate("button => button.click()")
                expect(motion_toggle).to_have_attribute("aria-pressed", "true")
                assert video.evaluate("element => element.paused")
                motion_toggle.evaluate("button => button.click()")
                expect(motion_toggle).to_have_attribute("aria-pressed", "false")
                checks.append("decorative_video_is_muted_inline_and_obeys_global_pause")

            workspace_links = page.locator('a[href^="/workspace"]')
            assert workspace_links.count() >= 3
            for href in workspace_links.evaluate_all("elements => elements.map(e => e.getAttribute('href'))"):
                result = context.request.get(base + href)
                assert result.status == 200 and "message-input" in result.text()
            checks.append("all_workspace_ctas_resolve_to_the_actual_app")
            bridge = context.new_page()
            bridge.goto(base + "/workspace?prompt=Explain%20compound%20interest", wait_until="networkidle")
            expect(bridge.locator("#message-input")).to_have_value("Explain compound interest")
            bridge.goto(base + "/workspace?tool=compound", wait_until="networkidle")
            expect(bridge.locator("#calculator-dialog")).to_be_visible()
            bridge.goto(base + "/workspace?view=knowledge", wait_until="networkidle")
            expect(bridge.locator("#knowledge-dialog")).to_be_visible()
            catalogue = context.request.get(base + "/api/models").json()["models"]
            local_ready = any(model["id"] == "local" and model["available"] for model in catalogue)
            bridge.goto(base + "/workspace?engine=local", wait_until="networkidle")
            expect(bridge.locator("#model-select")).to_have_value("local" if local_ready else "deepseek")
            bridge.close()
            checks.append("workspace_prompt_and_calculator_deep_links")
            checks.append("workspace_knowledge_and_model_deep_links_without_generation")

            reduced = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
            reduced_page = reduced.new_page()
            reduced_page.goto(base, wait_until="networkidle")
            expect(reduced_page.locator("#hero h1")).to_be_visible()
            reduced_page.wait_for_function("document.querySelector('[data-testid=signal-scene]')?.dataset.renderer === 'webgl2'", timeout=20000)
            reduced_scene = reduced_page.get_by_test_id("signal-scene")
            reduced_page.wait_for_timeout(250)
            before = reduced_scene.get_attribute("data-frames")
            reduced_page.wait_for_timeout(500)
            assert reduced_scene.get_attribute("data-frames") == before
            assert reduced_scene.get_attribute("data-reduced-motion") == "true"
            checks.append("reduced_motion_renders_static_scene_and_readable_content")
            reduced_page.locator("#experience").scroll_into_view_if_needed()
            for index in range(4):
                step = reduced_page.get_by_test_id(f"story-step-{index}")
                step.click()
                reduced_page.wait_for_timeout(150)
                expect(step).to_have_attribute("aria-selected", "true")
                expect(reduced_page.locator("#story-panel")).to_have_attribute("aria-labelledby", f"story-tab-{index}")
            checks.append("all_four_story_chapters_are_selectable_with_reduced_motion")

            for width in (320, 390, 768, 1024, 1440, 1920):
                reduced_page.set_viewport_size({"width": width, "height": 1000 if width >= 768 else 844})
                reduced_page.evaluate("scrollTo({top:0,behavior:'instant'})")
                reduced_page.wait_for_timeout(300)
                assert reduced_page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"Horizontal overflow at {width}px"
                hero_rect = reduced_page.locator("#hero h1").bounding_box()
                assert hero_rect and hero_rect["x"] >= -1 and hero_rect["x"] + hero_rect["width"] <= width + 1
                reduced_page.locator("#planning").scroll_into_view_if_needed()
                assert reduced_page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"Planning overflow at {width}px"
                layouts.append({"width": width, "hero": "passed", "calculator": "passed"})
            checks.append("six_responsive_sizes_without_horizontal_overflow")
            reduced_page.set_viewport_size({"width": 390, "height": 844})
            reduced_page.evaluate("scrollTo({top:0,behavior:'instant'})")
            menu = reduced_page.get_by_test_id("menu-toggle")
            expect(menu).to_be_visible()
            menu.click()
            expect(menu).to_have_attribute("aria-expanded", "true")
            nav = reduced_page.locator("#mobile-navigation")
            expect(nav).to_be_visible()
            reduced_page.keyboard.press("Escape")
            expect(menu).to_have_attribute("aria-expanded", "false")
            expect(menu).to_be_focused()
            menu.click()
            nav.locator('a[href^="#"]').first.click()
            expect(menu).to_have_attribute("aria-expanded", "false")
            checks.append("mobile_navigation_escape_focus_and_link_close")
            reduced_page.evaluate("scrollTo({top:0,behavior:'instant'})")
            reduced_page.screenshot(path=str(SCREENSHOTS / "hero-mobile.png"), full_page=False, animations="disabled")
            reduced.close()

            fallback = browser.new_context(viewport={"width": 1000, "height": 900}, reduced_motion="reduce")
            fallback.add_init_script("""const originalGetContext=HTMLCanvasElement.prototype.getContext;
                HTMLCanvasElement.prototype.getContext=function(type,...rest){
                  if(['webgl2','webgl','experimental-webgl'].includes(type))return null;
                  return originalGetContext.call(this,type,...rest);
                };""")
            fallback_page = fallback.new_page()
            fallback_page.goto(base, wait_until="networkidle")
            fallback_page.wait_for_function("document.querySelector('[data-testid=signal-scene]')?.dataset.renderer === 'svg'", timeout=20000)
            expect(fallback_page.locator("#hero h1")).to_be_visible()
            expect(fallback_page.get_by_test_id("signal-scene").locator("svg").first).to_be_visible()
            checks.append("forced_webgl_failure_preserves_svg_hero_and_content")
            fallback.close()

            blocked = browser.new_context(viewport={"width": 1000, "height": 900}, reduced_motion="reduce")
            def abort_engine(route):
                expected_fault_requests.append(route.request.url)
                route.abort()
            blocked.route(re.compile(r"/assets/(?:three-engine|RoomEnvironment)-[^/]+\.js(?:\?.*)?$"), abort_engine)
            blocked_page = blocked.new_page()
            blocked_errors = []
            blocked_page.on("pageerror", lambda error: blocked_errors.append(str(error)))
            blocked_page.on("console", lambda message: expected_fault_console_errors.append(message.text) if message.type == "error" else None)
            blocked_page.goto(base, wait_until="networkidle")
            blocked_page.wait_for_function("document.querySelector('[data-testid=signal-scene]')?.dataset.fallback === 'engine_unavailable'", timeout=20000)
            expect(blocked_page.locator("#hero h1")).to_be_visible()
            expect(blocked_page.get_by_test_id("signal-scene").locator("svg").first).to_be_visible()
            assert not blocked_errors, blocked_errors
            checks.append("rendering_engine_chunk_failure_does_not_break_react_content")
            blocked.close()

            no_js = browser.new_context(java_script_enabled=False, viewport={"width": 1000, "height": 900})
            no_js_page = no_js.new_page()
            no_js_page.goto(base, wait_until="load")
            expect(no_js_page.locator("h1").first).to_be_visible()
            assert no_js_page.locator('a[href="/workspace"]').count() > 0
            checks.append("javascript_disabled_still_has_heading_and_workspace_link")
            no_js.close()

            details["navigation_observation"] = page.evaluate("performance.getEntriesByType('navigation')[0]?.toJSON()")
            details["local_resource_bytes_observation"] = page.evaluate("performance.getEntriesByType('resource').reduce((sum,r)=>sum+(r.transferSize||0),0)")
            assert not errors, errors
            assert not forbidden_chat, forbidden_chat
            assert not remote_requests, remote_requests
            unexpected_console = [text for text in console_errors if "favicon" not in text]
            assert not unexpected_console, unexpected_console
            checks.append("no_page_errors_csp_errors_remote_runtime_requests_or_chat_calls")
            browser.close()
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error=str(error))
        if page is not None:
            try:
                page.screenshot(path=str(SCREENSHOTS / "failure.png"), full_page=True, animations="disabled")
            except Exception:
                pass
    report.update(total=len(checks), checks=checks, layout_cases=layouts, observations=details,
                  page_errors=errors, console_errors=console_errors, remote_runtime_requests=remote_requests,
                  expected_fault_console_errors=expected_fault_console_errors, expected_fault_requests=expected_fault_requests,
                  forbidden_chat_requests=forbidden_chat, duration_seconds=round(time.perf_counter()-started, 2),
                  screenshots=[str(path.relative_to(ROOT)).replace("\\", "/") for path in SCREENSHOTS.glob("*.png")],
                  limitations=["One local Windows/Edge environment; timings are observations, not Core Web Vitals certification.",
                               "Keyboard and reduced-motion checks are not a full accessibility audit.",
                               "Financial calculations use synthetic inputs; no LLM or investment performance is evaluated."])
    source_files = [ROOT / "frontend" / filename for filename in ("package.json", "package-lock.json", "index.html", "vite.config.ts")]
    source_files.extend((ROOT / "frontend" / "src").rglob("*.tsx"))
    source_files.extend((ROOT / "frontend" / "src").rglob("*.ts"))
    source_files.extend((ROOT / "frontend" / "src").rglob("*.css"))
    report["source_sha256"] = {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files if path.is_file()}
    report["built_assets_sha256"] = {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest() for path in (ROOT / "web" / "showcase").rglob("*") if path.is_file()}
    output = ROOT / "reports" / args.report_name
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "total", "checks", "duration_seconds", "error") if key in report}, ensure_ascii=True, indent=2))
    return int(report["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
