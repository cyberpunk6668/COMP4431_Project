"""Exercise homepage language switching and cross-page preferences in a real browser.

Run against the built application, for example:
    .venv\\Scripts\\python.exe scripts/check_showcase_language.py
The checks do not send chat messages or invoke a language model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "showcase_language_check.json"
SCREENSHOTS = ROOT / "reports" / "screenshots" / "showcase-language"
CJK = re.compile(r"[\u3400-\u9fff]")
INPUTS = ("#calc-principal", "#calc-monthly", "#calc-rate", "#calc-years")

# Inspect text even below the viewport, while excluding collapsed/hidden content.
# The explicit target-language label is intentionally Chinese in the English UI.
ENGLISH_AUDIT = r"""() => {
    const cjk = /[\u3400-\u9fff]/;
    const issues = [];
    const ignored = node => node.closest('[data-testid="language-toggle"]');
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
        const parent = node.parentElement;
        if (!parent || ignored(parent) || parent.closest('script,style,noscript')) continue;
        if (!parent.checkVisibility()) continue;
        const text = node.textContent.trim();
        if (cjk.test(text)) issues.push({kind: 'text', text, parent: parent.className?.baseVal ?? parent.className});
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


def at_top(page) -> None:
    page.evaluate("scrollTo({top: 0, behavior: 'instant'})")


def home(page, base: str, language: str | None = None) -> None:
    response = page.goto(base + "/", wait_until="domcontentloaded")
    assert response and response.status == 200, "Homepage did not load"
    expect(page.get_by_test_id("language-toggle")).to_be_visible()
    if language:
        expect(page.locator("html")).to_have_attribute("lang", "en" if language == "en" else "zh-CN")
    expect(page.get_by_test_id("calc-result")).to_contain_text("94,111.23", timeout=15000)


def switch(page, language: str) -> None:
    at_top(page)
    page.get_by_test_id("language-toggle").click()
    expect(page.locator("html")).to_have_attribute("lang", "en" if language == "en" else "zh-CN")
    assert page.evaluate("localStorage.getItem('finpilot-language')") == language


def english(page) -> None:
    expect(page.locator("html")).to_have_attribute("lang", "en")
    assert not CJK.search(page.title()), page.title()
    description = page.locator('meta[name="description"]').get_attribute("content")
    assert description and not CJK.search(description), description
    issues = page.evaluate(ENGLISH_AUDIT)
    assert not issues, json.dumps(issues, ensure_ascii=False)


def screenshot(page, name: str) -> None:
    page.screenshot(path=str(SCREENSHOTS / name), animations="disabled")


def layout(page, language: str, width: int, height: int) -> dict:
    page.set_viewport_size({"width": width, "height": height})
    at_top(page)
    page.wait_for_function("() => document.fonts.status === 'loaded'")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (language, width)
    for selector in (".site-header .brand", '[data-testid="language-toggle"]', "#hero h1", ".hero-actions"):
        locator = page.locator(selector)
        expect(locator).to_be_visible()
        box = locator.bounding_box()
        assert box and box["x"] >= -1 and box["x"] + box["width"] <= width + 1, (language, width, selector, box)
        assert box["y"] >= -1 and box["y"] + box["height"] <= height + 1, (language, width, selector, box)
    menu = page.get_by_test_id("menu-toggle")
    if menu.is_visible():
        menu.click()
        expect(menu).to_have_attribute("aria-expanded", "true")
        navigation = page.locator("#mobile-navigation")
        expect(navigation).to_be_visible()
        if language == "en":
            assert not CJK.search(navigation.inner_text()), navigation.inner_text()
        page.keyboard.press("Escape")
        expect(menu).to_have_attribute("aria-expanded", "false")
    for index in range(4):
        page.get_by_test_id(f"story-step-{index}").click()
        expect(page.locator(".story-visual")).to_have_attribute("data-stage", str(index))
        bounds = page.locator(".story-visual").evaluate("""element => {
            const header = element.querySelector('.story-visual-top').getBoundingClientRect();
            const footer = element.querySelector('.story-visual-bottom').getBoundingClientRect();
            const scene = element.querySelector('.story-frame > div').getBoundingClientRect();
            return {headerBottom: header.bottom, footerTop: footer.top, sceneTop: scene.top, sceneBottom: scene.bottom};
        }""")
        assert bounds["sceneTop"] >= bounds["headerBottom"] + 3, (language, width, index, "story_header_overlap", bounds)
        assert bounds["sceneBottom"] <= bounds["footerTop"] - 3, (language, width, index, "story_footer_overlap", bounds)
    tabs = page.locator(".evidence-demo").evaluate("""element => {
        const card = element.getBoundingClientRect();
        return Array.from(element.querySelectorAll('.evidence-topics > button')).map(button => {
            const box = button.getBoundingClientRect();
            return {text: button.textContent, left: box.left - card.left, right: box.right - card.left, cardWidth: card.width};
        });
    }""")
    assert all(tab["left"] >= 0 and tab["right"] <= tab["cardWidth"] + 1 for tab in tabs), (language, width, "clipped_evidence_tabs", tabs)
    page.locator("#planning").scroll_into_view_if_needed()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (language, width, "planning")
    at_top(page)
    return {"language": language, "width": width, "height": height, "status": "passed"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    origin = urlsplit(base).netloc
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    checks, layouts, page_errors, chat_requests, external_requests = [], [], [], [], []
    report = {
        "status": "running", "checked_at": datetime.now(timezone.utc).isoformat(),
        "base": base, "browser": "Microsoft Edge, headless", "checks": checks,
        "layouts": layouts, "page_errors": page_errors, "chat_requests": chat_requests,
        "external_requests": external_requests,
    }

    def observe_context(context):
        def request(request):
            target = urlsplit(request.url)
            if target.path == "/api/chat":
                chat_requests.append(request.url)
            if target.scheme in {"http", "https"} and target.netloc != origin:
                external_requests.append(request.url)
        context.on("request", request)
        context.on("page", lambda page: page.on("pageerror", lambda error: page_errors.append(str(error))))

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
            observe_context(context)
            context.add_init_script("""if ('speechSynthesis' in window) {
                window.speechSynthesis.speak = utterance => {
                    window.showcaseSpeech = {language: utterance.lang, text: utterance.text};
                    utterance.onstart?.();
                };
            }""")
            page = context.new_page()
            home(page, base, "zh")
            assert "金融" in page.locator("#hero h1").inner_text()
            switch(page, "en")
            english(page)
            for section in ("#experience", "#evidence", "#planning", "#intelligence", "#start"):
                assert page.locator(section + " h2").inner_text().strip(), section
            checks.append("entire_homepage_navigation_metadata_and_accessible_labels_are_english")

            for index in range(4):
                step = page.get_by_test_id(f"story-step-{index}")
                step.click()
                expect(step).to_have_attribute("aria-selected", "true")
                expect(page.locator(".story-visual")).to_have_attribute("data-stage", str(index))
                english(page)
            checks.append("all_four_learning_steps_and_illustration_labels_are_english")

            for index in range(3):
                topic = page.get_by_test_id(f"evidence-topic-{index}")
                topic.click()
                expect(topic).to_have_attribute("aria-selected", "true")
                expect(page.locator("#evidence-answer")).to_have_attribute("aria-labelledby", f"evidence-tab-{index}")
                details = page.locator(".source-excerpt")
                details.locator("summary").click()
                expect(details).to_have_attribute("open", "")
                english(page)
                prompt = urlsplit(page.locator(".evidence-demo-cta").get_attribute("href"))
                assert not CJK.search(parse_qs(prompt.query)["prompt"][0])
            checks.append("all_three_knowledge_examples_source_summaries_and_deep_link_prompts_are_english")

            page.locator("#calc-principal").fill("12000")
            page.locator("#calc-rate").press("Home")
            expected = context.request.post(base + "/api/calculate", data={
                "kind": "compound", "principal": 12000, "monthly_contribution": 500,
                "annual_rate": 0, "years": 10,
            }).json()["values"]["future_value"]
            expect(page.get_by_test_id("calc-result")).to_contain_text(f"{float(expected):,.2f}")
            inputs = {selector: page.locator(selector).input_value() for selector in INPUTS}
            rendered_result = page.get_by_test_id("calc-result").inner_text()
            switch(page, "zh")
            assert "金融" in page.locator("#hero h1").inner_text()
            assert "计算" in page.locator("#calc-status").inner_text()
            expect(page.get_by_test_id("evidence-topic-2")).to_have_attribute("aria-selected", "true")
            expect(page.locator(".source-excerpt")).to_have_attribute("open", "")
            assert {selector: page.locator(selector).input_value() for selector in INPUTS} == inputs
            assert page.get_by_test_id("calc-result").inner_text() == rendered_result
            switch(page, "en")
            english(page)
            checks.append("switching_both_directions_preserves_inputs_results_selected_topic_and_expanded_summary")

            page.locator("#intelligence").scroll_into_view_if_needed()
            mentor = page.get_by_test_id("mentor-stage")
            page.locator("#intelligence").get_by_role("button", name="2D", exact=True).click()
            expect(mentor.locator('[data-actual-mode="2d"]')).to_be_visible(timeout=15000)
            english(page)
            checks.append("lazy_loaded_avatar_and_model_section_use_selected_language")
            page.locator(".mentor-listen").click()
            expect(page.locator(".mentor-listen")).to_have_attribute("aria-pressed", "true")
            spoken = page.evaluate("window.showcaseSpeech")
            assert spoken and spoken["language"] == "en-US" and not CJK.search(spoken["text"]), spoken
            switch(page, "zh")
            expect(page.locator(".mentor-listen")).to_have_attribute("aria-pressed", "false")
            page.locator(".mentor-listen").click()
            spoken = page.evaluate("window.showcaseSpeech")
            assert spoken and spoken["language"] == "zh-CN" and CJK.search(spoken["text"]), spoken
            switch(page, "en")
            expect(page.locator(".mentor-listen")).to_have_attribute("aria-pressed", "false")
            checks.append("speech_uses_selected_language_and_switching_stops_previous_language_without_playing_audio")
            at_top(page)
            screenshot(page, "home-en-desktop.png")
            page.reload(wait_until="domcontentloaded")
            expect(page.locator("html")).to_have_attribute("lang", "en")
            english(page)
            checks.append("selected_english_language_survives_reload")

            second = context.new_page()
            home(second, base, "en")
            switch(second, "zh")
            expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
            switch(second, "en")
            expect(page.locator("html")).to_have_attribute("lang", "en")
            second.close()
            checks.append("homepage_updates_when_another_tab_changes_language")

            at_top(page)
            page.locator('.hero-actions a[href="/learn"]').click()
            expect(page.locator("html")).to_have_attribute("lang", "en")
            expect(page.locator("#lab-language")).to_be_enabled(timeout=20000)
            page.locator("#lab-language").click()
            expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
            page.go_back(wait_until="domcontentloaded")
            expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
            switch(page, "en")
            checks.append("learning_lab_inherits_language_and_browser_back_restores_changed_preference")

            page.locator('.hero-actions a[href="/workspace"]').click()
            expect(page.locator("html")).to_have_attribute("lang", "en")
            page.locator("#language-toggle").click()
            expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
            home(page, base, "zh")
            checks.append("workspace_inherits_language_and_returning_home_uses_updated_preference")

            for language in ("zh", "en"):
                if language == "en":
                    switch(page, "en")
                for width, height in ((320, 568), (390, 844), (768, 1024), (1024, 900), (1440, 1000), (1920, 1080)):
                    layouts.append(layout(page, language, width, height))
                    if width == 390:
                        screenshot(page, f"home-{language}-mobile.png")
                if language == "zh":
                    screenshot(page, "home-zh-desktop.png")
            checks.append("both_languages_keep_navigation_hero_and_calculator_inside_six_viewport_widths")
            context.close()

            failed = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
            observe_context(failed)
            failed.route("**/api/calculate", lambda route: route.fulfill(status=503, content_type="application/json", body='{"detail":"unavailable"}'))
            failure_page = failed.new_page()
            failure_page.goto(base + "/", wait_until="domcontentloaded")
            expect(failure_page.locator("#calc-status button")).to_be_attached(timeout=15000)
            switch(failure_page, "en")
            english(failure_page)
            expect(failure_page.locator("#calc-status button")).to_be_enabled()
            checks.append("calculation_failure_message_and_retry_control_follow_selected_language")
            failed.close()
            browser.close()
        assert not page_errors, page_errors
        assert not chat_requests, chat_requests
        assert not external_requests, external_requests
        checks.append("no_unhandled_browser_errors_remote_resources_or_paid_model_requests")
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        report["total"] = len(checks)
        report["duration_seconds"] = round(time.perf_counter() - start, 2)
        audited = ("frontend/src/App.tsx", "frontend/src/i18n.tsx", "frontend/src/components/Hero.tsx", "frontend/src/components/hero.css", "web/showcase/index.html")
        report["sha256"] = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in audited if (ROOT / path).is_file()}
        report["screenshots"] = sorted(path.relative_to(ROOT).as_posix() for path in SCREENSHOTS.glob("*.png"))
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{report['status']}: {len(checks)} checks, {len(layouts)} layouts, {report['duration_seconds']} seconds")
        print(REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
