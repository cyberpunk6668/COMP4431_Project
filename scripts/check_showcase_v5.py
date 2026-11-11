"""Browser verification for the video homepage and its FinPilot entry points."""

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
REPORT = ROOT / "reports" / "showcase_check_v5.json"
SCREENSHOTS = ROOT / "reports" / "screenshots" / "showcase-v5"
VIDEO = "/static/showcase/media/reference-motion.mp4"
ENTER_GROUPS = ("header", "eyebrow", "heading", "description", "actions")
INTRO_OBSERVER = """
(() => {
  const observation = { groups: {}, videoReady: null, start: null, ready: null };
  window.showcaseIntroObservation = observation;
  function sample() {
    const hero = document.querySelector('#hero');
    if (hero?.dataset.videoState === 'ready' && observation.videoReady === null) {
      observation.videoReady = performance.now();
    }
    if (hero?.dataset.introState === 'playing' && observation.start === null) {
      observation.start = performance.now();
    }
    if (observation.start !== null) {
      const elapsed = performance.now() - observation.start;
      for (const element of document.querySelectorAll('[data-hero-enter]')) {
        const name = element.dataset.heroEnter;
        const style = getComputedStyle(element);
        const opacity = Number(style.opacity);
        const y = style.transform === 'none' ? 0 : new DOMMatrixReadOnly(style.transform).m42;
        const group = observation.groups[name] ??= {};
        if (group.initial === undefined) group.initial = { opacity, y };
        if (group.firstVisible === undefined && opacity > 0.005) group.firstVisible = elapsed;
        if (group.settled === undefined && opacity === 1 && Math.abs(y) < 0.05) group.settled = elapsed;
      }
      if (hero?.dataset.introState === 'ready') {
        observation.ready = elapsed;
        return;
      }
    }
    requestAnimationFrame(sample);
  }
  requestAnimationFrame(sample);
})();
"""


def screenshot(page, name: str) -> None:
    page.screenshot(path=str(SCREENSHOTS / name), animations="disabled")


def open_home(page, base: str) -> None:
    response = page.goto(base + "/", wait_until="domcontentloaded")
    assert response and response.status == 200, "Homepage failed to load"


def settled_hero(page) -> None:
    hero = page.locator("#hero")
    page.wait_for_function("() => document.querySelector('#hero')?.dataset.introState === 'ready'", timeout=12000)
    expect(hero.locator("h1")).to_be_visible()
    assert hero.locator("h1").inner_text().strip()
    for name in ENTER_GROUPS:
        group = page.locator(f'[data-hero-enter="{name}"]')
        assert group.count() == 1, f"Missing intro group {name}"
        assert group.evaluate("element => getComputedStyle(element).opacity") == "1", name


def check_intro(page) -> dict:
    page.wait_for_function("() => window.showcaseIntroObservation.ready !== null", timeout=5000)
    observation = page.evaluate("window.showcaseIntroObservation")
    assert observation["videoReady"] <= observation["start"], observation
    first_visible = []
    for name, expected_delay in zip(ENTER_GROUPS, (200, 300, 400, 500, 600)):
        group = observation["groups"][name]
        assert group["initial"]["opacity"] < 0.02, (name, group)
        assert (group["initial"]["y"] < 0 if name == "header" else group["initial"]["y"] > 0), (name, group)
        assert abs(group["firstVisible"] - expected_delay) < 160, (name, group, expected_delay)
        assert 700 <= group["settled"] - group["firstVisible"] <= 1230, (name, group)
        first_visible.append(group["firstVisible"])
    assert first_visible == sorted(set(first_visible)), first_visible
    assert 1390 <= observation["ready"] <= 2100, observation
    return observation


def check_workspace_links(context, page, base: str) -> None:
    links = set(page.locator('a[href^="/workspace"]').evaluate_all("links => links.map(link => link.getAttribute('href'))"))
    assert "/workspace" in links
    assert "/workspace?tool=compound" in links
    assert "/workspace?engine=local" in links
    assert any(link.startswith("/workspace?prompt=") for link in links)
    assert "/workspace?view=knowledge" in links
    for link in sorted(links):
        response = context.request.get(base + link)
        assert response.status == 200 and 'id="message-input"' in response.text(), link

    workspace = context.new_page()
    prompt = next(link for link in sorted(links) if link.startswith("/workspace?prompt="))
    workspace.goto(base + prompt, wait_until="domcontentloaded")
    expect(workspace.locator("#message-input")).not_to_have_value("")
    workspace.goto(base + "/workspace?tool=compound", wait_until="domcontentloaded")
    expect(workspace.locator("#calculator-dialog")).to_be_visible()
    workspace.goto(base + "/workspace?view=knowledge", wait_until="domcontentloaded")
    expect(workspace.locator("#knowledge-dialog")).to_be_visible()
    models = context.request.get(base + "/api/models").json()["models"]
    local_ready = any(model["id"] == "local" and model["available"] for model in models)
    workspace.goto(base + "/workspace?engine=local", wait_until="domcontentloaded")
    expect(workspace.locator("#model-select")).to_have_value("local" if local_ready else "deepseek")
    workspace.close()


def check_features(context, page, base: str, checks: list[str]) -> None:
    primary = page.locator('[data-hero-enter="actions"] a[href="/workspace"]')
    expect(primary).to_be_visible()
    page.locator('[data-hero-enter="actions"] a[href="#experience"]').click()
    expect(page).to_have_url(re.compile(r"#experience$"))
    expect(page.locator("#experience h2")).to_be_visible()
    checks.append("hero_links_to_story_and_workbench")

    for index in range(4):
        step = page.get_by_test_id(f"story-step-{index}")
        step.click()
        expect(step).to_have_attribute("aria-selected", "true")
        expect(page.locator("#story-panel")).to_have_attribute("aria-labelledby", f"story-tab-{index}")
    checks.append("four_story_steps_remain_interactive")

    page.locator("#evidence").scroll_into_view_if_needed()
    links = page.locator('#evidence a[href^="https://"]')
    expect(links.first).to_be_visible()
    knowledge = context.request.get(base + "/api/knowledge").json()["documents"]
    approved = {document["url"] for document in knowledge}
    assert set(links.evaluate_all("links => links.map(link => link.href)")) <= approved
    checks.append("citations_match_local_curated_sources")

    page.locator("#planning").scroll_into_view_if_needed()
    expect(page.get_by_test_id("calc-result")).to_contain_text("94,111.23", timeout=12000)
    rate = page.locator("#calc-rate")
    rate.press("Home")
    minimum = float(rate.get_attribute("min") or 0)
    scenario = {"kind": "compound", "principal": 10000, "annual_rate": minimum, "years": 10, "monthly_contribution": 500}
    expected = context.request.post(base + "/api/calculate", data=scenario).json()["values"]["future_value"]
    expect(page.get_by_test_id("calc-result")).to_contain_text(f"{float(expected):,.2f}", timeout=12000)
    checks.append("calculator_updates_from_real_api_after_keyboard_input")
    page.locator("#intelligence").scroll_into_view_if_needed()
    mentor = page.get_by_test_id("mentor-stage")
    expect(mentor).to_be_visible()
    page.locator("#intelligence").get_by_role("button", name="2D", exact=True).click()
    expect(mentor.locator('[data-actual-mode="2d"]')).to_be_visible(timeout=10000)
    checks.append("mentor_can_switch_to_2d")
    assert page.locator("#start video").count() == 0
    expect(page.locator('#start a[href="/workspace"]').first).to_be_visible()
    check_workspace_links(context, page, base)
    checks.append("actual_workspace_deep_links_open_tools_and_prompt_without_chat")


def check_mobile(page, checks: list[str], animated: bool) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("scrollTo({top:0,behavior:'instant'})")
    menu = page.get_by_test_id("menu-toggle")
    expect(menu).to_be_visible()
    menu.press("Enter")
    expect(menu).to_have_attribute("aria-expanded", "true")
    navigation = page.locator("#mobile-navigation")
    expect(navigation).to_be_visible()
    expect(navigation.locator('a[href="/workspace"]')).to_be_visible()
    expect(navigation.locator("a").first).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(menu).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(navigation.locator("a").last).to_be_focused()
    page.keyboard.press("Tab")
    expect(menu).to_be_focused()
    if animated:
        page.wait_for_function("() => getComputedStyle(document.querySelector('#mobile-navigation')).opacity === '1'")
        screenshot(page, "mobile-menu.png")
    page.keyboard.press("Escape")
    expect(menu).to_have_attribute("aria-expanded", "false")
    expect(menu).to_be_focused()
    expect(navigation).to_have_count(0)
    menu.click()
    navigation.locator('a[href^="#"]').first.click()
    expect(menu).to_have_attribute("aria-expanded", "false")
    expect(navigation).to_have_count(0)
    checks.append("mobile_menu_keyboard_focus_and_exit_" + ("animated" if animated else "reduced_motion"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    origin = urlsplit(base).netloc
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    checks, layouts, page_errors, console_errors, outside_requests, chat_requests = [], [], [], [], [], []
    fault_console_errors = {"failed_video": [], "video_timeout": []}
    report = {
        "status": "running",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "browser": "Microsoft Edge, headless",
        "base": base,
        "checks": checks,
        "layouts": layouts,
        "page_errors": page_errors,
        "normal_console_errors": console_errors,
        "controlled_fault_console_errors": fault_console_errors,
        "external_runtime_requests": outside_requests,
        "chat_requests": chat_requests,
    }

    def page_for(context, fault: str | None = None):
        def observe(request):
            target = urlsplit(request.url)
            if target.scheme in {"http", "https"} and target.netloc != origin:
                outside_requests.append(request.url)
            if target.path == "/api/chat":
                chat_requests.append(request.url)
        context.on("request", observe)
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        log = fault_console_errors[fault] if fault else console_errors
        page.on("console", lambda message: log.append(message.text) if message.type == "error" else None)
        return page

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = page_for(context)
            page.add_init_script(INTRO_OBSERVER)
            open_home(page, base)
            settled_hero(page)
            assert page.locator("#hero").get_attribute("data-video-state") == "ready"
            video = page.get_by_test_id("hero-video")
            assert video.get_attribute("src") == VIDEO
            media = video.evaluate("element => ({muted:element.muted, loop:element.loop, inline:element.playsInline, autoplay:element.autoplay, width:element.videoWidth})")
            assert all(media.values()), media
            page.wait_for_function("() => document.querySelector('[data-testid=hero-video]').currentTime > 0.05")
            provenance = json.loads((ROOT / "frontend" / "public" / "asset-provenance.json").read_text(encoding="utf-8"))
            expected_hash = next(asset["sha256"] for asset in provenance if asset["file"] == "media/reference-motion.mp4")
            assert hashlib.sha256((ROOT / "web" / "showcase" / "media" / "reference-motion.mp4").read_bytes()).hexdigest() == expected_hash
            checks.append("same_origin_reference_video_is_decoded_and_autoplays_muted_inline")
            report["intro_observation_ms"] = check_intro(page)
            checks.append("five_ordered_intro_transitions_observed_in_browser")
            screenshot(page, "hero-desktop.png")
            check_mobile(page, checks, animated=True)
            page.evaluate("scrollTo({top:0,behavior:'instant'})")
            screenshot(page, "hero-mobile.png")
            page.set_viewport_size({"width": 1440, "height": 1000})

            motion_toggle = page.get_by_test_id("motion-toggle")
            motion_toggle.click()
            expect(motion_toggle).to_have_attribute("aria-pressed", "true")
            if video.count():
                page.wait_for_function("() => document.querySelector('[data-testid=hero-video]').paused")
                paused_time = video.evaluate("element => element.currentTime")
                page.wait_for_timeout(350)
                assert abs(video.evaluate("element => element.currentTime") - paused_time) < 0.03
            settled_hero(page)
            motion_toggle.click()
            expect(motion_toggle).to_have_attribute("aria-pressed", "false")
            page.wait_for_function("() => document.querySelector('[data-testid=hero-video]')?.paused === false")
            checks.append("global_motion_control_pauses_and_resumes_video")
            motion_toggle.click()
            check_features(context, page, base, checks)
            context.close()

            reduced = browser.new_context(reduced_motion="reduce", color_scheme="dark", viewport={"width": 1440, "height": 1000})
            page = page_for(reduced)
            open_home(page, base)
            settled_hero(page)
            expect(page.locator("#hero")).to_have_attribute("data-video-state", "static")
            assert page.evaluate("matchMedia('(prefers-color-scheme: dark)').matches")
            assert page.evaluate("getComputedStyle(document.documentElement).colorScheme.includes('light') || getComputedStyle(document.body).colorScheme.includes('light')")
            reduced_video = page.get_by_test_id("hero-video")
            assert not reduced_video.count() or reduced_video.evaluate("element => element.paused")
            checks.append("reduced_motion_uses_static_hero_and_dark_os_keeps_light_appearance")
            screenshot(page, "static-dark-os.png")

            for width, height in ((320, 568), (390, 844), (768, 1024), (1023, 900), (1024, 900), (1440, 1000), (1920, 1080)):
                page.set_viewport_size({"width": width, "height": height})
                page.evaluate("scrollTo({top:0,behavior:'instant'})")
                page.wait_for_function("() => document.fonts.status === 'loaded'")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), width
                hero_box = page.locator("#hero").bounding_box()
                assert hero_box and abs(hero_box["height"] - height) <= 1, (width, height, hero_box)
                for selector in ("#hero h1", '[data-hero-enter="actions"]'):
                    box = page.locator(selector).bounding_box()
                    assert box and box["x"] >= -1 and box["x"] + box["width"] <= width + 1, (width, selector, box)
                    assert box["y"] >= 0 and box["y"] + box["height"] <= height + 1, (width, selector, box)
                if width < 1024:
                    expect(page.get_by_test_id("menu-toggle")).to_be_visible()
                else:
                    expect(page.get_by_test_id("menu-toggle")).to_be_hidden()
                page.locator("#planning").scroll_into_view_if_needed()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), width
                layouts.append({"width": width, "height": height, "hero_height": hero_box["height"], "hero": "passed", "planning": "passed"})
            checks.append("responsive_layout_at_seven_widths_and_1024px_navigation_breakpoint")
            check_mobile(page, checks, animated=False)
            reduced.close()

            for fault in ("failed_video", "video_timeout"):
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                held = []
                if fault == "failed_video":
                    context.route("**" + VIDEO, lambda route: route.fulfill(status=404, body="Fixture: unavailable media"))
                else:
                    context.route("**" + VIDEO, lambda route: held.append(route), times=1)
                page = page_for(context, fault)
                fault_started = time.perf_counter()
                open_home(page, base)
                settled_hero(page)
                expect(page.locator("#hero")).to_have_attribute("data-video-state", "fallback")
                elapsed = time.perf_counter() - fault_started
                assert elapsed < 8, (fault, elapsed)
                if fault == "video_timeout":
                    assert held and elapsed >= 2, (fault, elapsed)
                expect(page.locator('[data-hero-enter="actions"] a[href="/workspace"]')).to_be_visible()
                report[fault + "_seconds_to_visible"] = round(elapsed, 2)
                checks.append(fault + "_reveals_functional_static_hero")
                if fault == "failed_video":
                    screenshot(page, "video-fallback.png")
                else:
                    held[0].continue_()
                    expect(page.locator("#hero")).to_have_attribute("data-video-state", "ready", timeout=12000)
                    settled_hero(page)
                    checks.append("late_media_recovers_without_restarting_intro")
                context.close()

            no_js = browser.new_context(java_script_enabled=False, viewport={"width": 1000, "height": 900})
            page = page_for(no_js)
            open_home(page, base)
            expect(page.locator("h1").first).to_be_visible()
            expect(page.locator('a[href="/workspace"]').first).to_be_visible()
            checks.append("javascript_disabled_keeps_readable_static_entry")
            no_js.close()
            browser.close()

        assert not page_errors, page_errors
        assert not console_errors, console_errors
        assert not outside_requests, outside_requests
        assert not chat_requests, chat_requests
        checks.append("no_unhandled_errors_remote_resources_or_chat_calls")
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        report["total"] = len(checks)
        report["duration_seconds"] = round(time.perf_counter() - start, 2)
        audited = [ROOT / path for path in ("frontend/src/App.tsx", "frontend/src/styles.css", "frontend/src/components/Hero.tsx", "frontend/src/components/hero.css", "web/showcase/index.html", "web/showcase/media/reference-motion.mp4")]
        report["sha256"] = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in audited if path.is_file()}
        report["screenshots"] = sorted(path.relative_to(ROOT).as_posix() for path in SCREENSHOTS.glob("*.png"))
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{report['status']}: {len(checks)} checks, {len(layouts)} layouts, {report['duration_seconds']} seconds")
        print(REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
