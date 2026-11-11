"""Check novice-first option reading in Edge using synthetic responses only."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import runpy
import sys
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.options_analytics import analyze_option_snapshot
from app.options_collective import build_collective_analysis, build_batch_comparison
from app.options_brief import build_plain_brief, build_batch_plain_brief

legacy = runpy.run_path(str(ROOT / "scripts/check_options_collective_browser.py"))
sample = legacy["sample"]
narrative = legacy["narrative"]
model_records = legacy["model_records"]
REPORT = ROOT / "reports/options_novice_browser_v8.json"
SHOTS = ROOT / "reports/screenshots/options-v8"


def fixture(symbol, expiry, language):
    report = sample(symbol, expiry, language=language)
    snapshot = report["snapshot"]
    if symbol in ("ZERO", "EMPTY", "UNKNOWN"):
        if symbol == "EMPTY":
            snapshot["quotes"] = []
        for row in snapshot["quotes"]:
            if symbol == "ZERO":
                row["volume"] = row["open_interest"] = 0
            if symbol == "UNKNOWN":
                row["market_data_type"] = None
        if symbol == "UNKNOWN":
            snapshot["underlying"]["market_data_type"] = None
        analysis = analyze_option_snapshot(snapshot, language=language)
        report.update(analysis)
        report["collective"] = build_collective_analysis(snapshot, analysis, language=language)
    report["plain_brief"] = build_plain_brief(report, language)
    return report


def check(browser, base, width, height):
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
    page = context.new_page()
    errors, requests = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    expiry = (datetime.now(timezone.utc).date() + timedelta(days=14)).isoformat()

    def respond(route):
        path = urlsplit(route.request.url).path
        if path.endswith("/status"):
            route.fulfill(json={"status": "tcp_ready", "endpoint": "127.0.0.1:4002", "enabled": True})
            return
        body = route.request.post_data_json
        requests.append(body)
        if body.get("market_data_type") == 1:
            route.fulfill(status=424, json={"detail": {"code": "ibkr_entitlement_missing", "message": "Fixture permission error"}})
            return
        lang = body["language"]
        if path.endswith("/batch"):
            reports, failures = [], []
            for item in body["items"]:
                if item["symbol"] == "MISS":
                    failures.append({**item, "code": "ibkr_entitlement_missing"})
                else:
                    reports.append(fixture(item["symbol"], item.get("expiry") or expiry, lang))
            comparison = build_batch_comparison(reports, lang)
            result = {"reports": reports, "failures": failures, "comparison": comparison,
                      "completed_at": datetime.now(timezone.utc).isoformat(),
                      "interpretation": narrative(model_records(reports, comparison), lang) if body["interpret_with_llm"] else {"status": "skipped"}}
            result["plain_brief"] = build_batch_plain_brief(reports, comparison, failures, lang)
        else:
            result = fixture(body["symbol"], body.get("expiry") or expiry, lang)
            if body["interpret_with_llm"]:
                result["interpretation"] = narrative(model_records([result]), lang, hostile=True)
        route.fulfill(json=result)

    context.route("**/api/options/**", respond)
    try:
        page.goto(base + "/workspace?view=options", wait_until="domcontentloaded")
        dialog = page.locator("#options-dialog")
        result = page.locator("#options-results")
        expect(dialog).to_be_visible()
        expect(page.locator("#options-view-simple")).to_have_attribute("aria-pressed", "true")
        assert page.locator("#options-advanced").get_attribute("open") is None
        assert not requests
        expect(page.locator("#options-feed-mode")).to_be_hidden()
        page.locator("#options-symbol").fill("SPY")
        page.locator("#options-submit").click()
        brief = result.locator(".options-plain-report")
        expect(brief).to_be_visible()
        expect(brief.locator(".options-freshness")).to_contain_text("延迟")
        expect(brief.locator(".options-plain-card")).to_have_count(4)
        expect(brief.locator(".options-parts figcaption")).to_contain_text("100")
        expect(result.locator(".options-professional-report")).to_be_hidden()
        assert brief.locator(".options-citation-group > summary").first.inner_text().startswith("查看依据（")
        assert brief.locator(".options-plain-card").first.locator(".options-citation-group").count() == 1
        expect(brief.locator(".options-evidence-links button").first).to_be_hidden()
        dialog.evaluate("el => { el.scrollTop += document.getElementById('options-results').getBoundingClientRect().top-el.getBoundingClientRect().top-65; }")
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"easy-{width}.png"), full_page=False, animations="disabled")

        evidence_disclosure = brief.locator(".options-citation-group").first
        evidence_disclosure.locator("summary").focus()
        page.keyboard.press("Enter")
        expect(evidence_disclosure).to_have_attribute("open", "")
        reference = evidence_disclosure.locator("button").first
        assert not reference.inner_text().startswith("[")
        reference.click()
        assert page.evaluate("() => document.activeElement.tagName") == "TR"
        assert page.evaluate("() => document.activeElement.textContent.includes('SPY')")
        brief.locator(".options-glossary > summary").click()
        expect(brief.locator(".options-glossary dt")).to_have_count(7)

        page.locator("#options-view-professional").click()
        expect(result.locator(".options-professional-report")).to_be_visible()
        expect(brief).to_be_hidden()
        raw = result.locator(".options-professional-report .options-raw-details")
        raw.locator("summary").first.click()
        expect(raw.locator(".options-chain-table")).to_be_visible()
        assert result.locator(".options-professional-report .options-evidence-links button").first.inner_text().startswith("[")
        page.reload(wait_until="domcontentloaded")
        expect(page.locator("#options-view-professional")).to_have_attribute("aria-pressed", "true")
        assert len(requests) == 1
        page.locator("#options-view-simple").click()

        page.locator("#options-advanced > summary").click()
        page.locator("#options-feed-mode").select_option("1")
        page.locator("#options-symbol").fill("SPY")
        page.locator("#options-submit").click()
        expect(page.locator("#options-error")).to_be_visible()
        expect(page.locator(".options-retry-delayed")).to_be_visible()
        assert len(requests) == 2
        page.locator(".options-retry-delayed").click()
        expect(result.locator(".options-plain-report")).to_be_visible()
        assert len(requests) == 3 and requests[-1]["market_data_type"] == 3
        assert not requests[-1]["interpret_with_llm"]

        for symbol in ("EMPTY", "ZERO", "UNKNOWN"):
            page.locator("#options-symbol").fill(symbol)
            page.locator("#options-submit").click()
            expect(result.locator(".options-plain-report")).to_be_visible()
            if symbol == "EMPTY":
                expect(result.locator(".options-plain-report .options-parts")).to_have_count(0)
            elif symbol == "ZERO":
                expect(result.locator(".options-plain-report .options-parts")).to_have_count(0)
                assert "0" in result.locator(".options-plain-report").inner_text() or "零" in result.locator(".options-plain-report").inner_text()
            else:
                expect(result.locator(".options-freshness")).to_contain_text("未确认")

        page.locator("#options-analysis-mode").select_option("batch")
        page.locator("#options-batch-items").fill("AAPL\nMSFT\nMISS")
        page.locator("#options-interpret").check()
        page.locator("#options-submit").click()
        expect(result.locator(".options-plain-items > article")).to_have_count(2)
        expect(result.locator(".options-plain-report")).to_contain_text("MISS")
        ai = result.locator(".options-plain-report .options-ai-more")
        assert ai.get_attribute("open") is None
        ai.locator("summary").first.click()
        expect(ai.locator(".options-model-report")).to_contain_text("条件情景")
        assert ai.locator("img").count() == 0
        assert requests[-1]["interpret_with_llm"]
        assert len(requests[-1]["items"]) == 3
        scroll, client = dialog.evaluate("el => [el.scrollWidth,el.clientWidth]")
        assert scroll <= client + 1, (width, scroll, client)
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")

        page.keyboard.press("Escape")
        page.locator("#language-toggle").click()
        if width <= 760:
            page.locator("#mobile-menu").click()
        page.locator("#nav-options").click()
        expect(page.locator("#options-view-simple")).to_have_text("Easy reading")
        expect(result.locator(".options-plain-report")).to_be_visible()
        expect(result.locator(".options-professional-report")).to_be_hidden()
        assert not errors, errors
        return {"width": width, "height": height, "fixture_requests": len(requests), "page_errors": errors}
    finally:
        context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "running",
              "scope": "Synthetic responses, real deterministic brief builders. No broker or model requests. Interface task checks, not a study with novice participants.",
              "checks": [], "viewports": []}
    try:
        with sync_playwright() as runner:
            browser = runner.chromium.launch(channel="msedge", headless=True)
            for width, height in ((320,740),(390,844),(1440,1000)):
                report["viewports"].append(check(browser,args.base.rstrip("/"),width,height))
            browser.close()
        report["checks"] = ["novice_default_and_no_auto_request", "advanced_settings_collapsed", "freshness_before_conclusions",
                            "four_plain_questions", "per_hundred_contract_visual", "technical_report_hidden",
                            "plain_evidence_labels_and_real_target", "glossary_keyboard_details", "professional_toggle_and_raw_data",
                            "reading_preference_persists", "permission_error_explicit_delayed_retry", "consent_preserved",
                            "missing_and_zero_have_no_fake_share_chart", "unknown_feed_label", "batch_items_and_partial_failure",
                            "optional_safe_model_explanation", "mobile_containment", "english_reopen"]
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed",error=str(error))
        raise
    finally:
        report["source_sha256"] = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
            "web/index.html","web/options.js","web/options.css","app/options_brief.py")}
        report["screenshots"] = [path.relative_to(ROOT).as_posix() for path in sorted(SHOTS.glob("*.png"))]
        REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(report["status"],len(report["checks"]),len(report["viewports"]))


if __name__ == "__main__":
    main()

