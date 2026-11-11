"""Verify broker-derived expiration choices in Edge, using synthetic API replies only.

All options routes are intercepted. Wednesday dates below are fixtures: they
prove membership in broker metadata is used instead of a weekday heuristic.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import runpy
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
helpers = runpy.run_path(str(ROOT / "scripts/check_options_novice_browser.py"))
fixture = helpers["fixture"]
build_batch_comparison = helpers["build_batch_comparison"]
build_batch_plain_brief = helpers["build_batch_plain_brief"]
REPORT = ROOT / "reports/options_expirations_browser_v9.json"
SHOTS = ROOT / "reports/screenshots/options-v9"
DATES = {
    "AAPL": ["2030-01-16", "2030-01-18", "2030-02-15"],
    "MSFT": ["2030-01-25", "2030-02-15"],
    "SPY": ["2030-01-16", "2030-01-25"],
    "RACEA": ["2030-03-15"],
    "RACEB": ["2030-04-19"],
    "LONG": [(date(2030, 3, 1) + timedelta(days=index)).isoformat() for index in range(40)],
}


def metadata(symbol):
    return {"source": "ibkr", "symbol": symbol, "expirations": DATES.get(symbol, []),
            "trading_class": symbol, "currency": "USD", "date_kind": "expiration",
            "timezone": "America/New_York", "as_of": datetime.now(timezone.utc).isoformat()}


def check(browser, base, width, height):
    context = browser.new_context(viewport={"width": width, "height": height},
                                  reduced_motion="reduce", timezone_id="America/Los_Angeles")
    page = context.new_page()
    errors, events, posts, held = [], [], [], []
    fail_metadata = {"FAIL"}
    page.on("pageerror", lambda error: errors.append(str(error)))

    def respond(route):
        parsed = urlsplit(route.request.url)
        path = parsed.path
        if path.endswith("/status"):
            route.fulfill(json={"status": "tcp_ready", "enabled": True, "endpoint": "fixture:4002"})
            return
        if path.endswith("/expirations"):
            symbol = parse_qs(parsed.query)["symbol"][0]
            events.append({"kind": "metadata", "symbol": symbol})
            if symbol == "RACEA":
                held.append(route)
            elif symbol in fail_metadata:
                route.fulfill(status=424, json={"detail": {"code": "ibkr_connection_failed", "message": "Synthetic disconnected gateway"}})
            else:
                route.fulfill(json=metadata(symbol))
            return
        assert route.request.method == "POST", path
        body = route.request.post_data_json
        posts.append({"path": path, "body": body})
        events.append({"kind": "analysis", "path": path})
        language = body["language"]
        if path.endswith("/batch"):
            reports = [fixture(item["symbol"], item.get("expiry") or DATES.get(item["symbol"], DATES["AAPL"])[0], language)
                       for item in body["items"]]
            comparison = build_batch_comparison(reports, language)
            data = {"reports": reports, "failures": [], "comparison": comparison,
                    "interpretation": {"status": "skipped"}, "completed_at": datetime.now(timezone.utc).isoformat()}
            data["plain_brief"] = build_batch_plain_brief(reports, comparison, [], language)
        elif path.endswith("/analyze"):
            data = fixture(body["symbol"], body.get("expiry") or DATES.get(body["symbol"], DATES["AAPL"])[0], language)
        else:
            raise AssertionError(f"Unexpected options endpoint: {path}")
        route.fulfill(json=data)

    context.route("**/api/options/**", respond)
    try:
        page.goto(base + "/workspace?view=options", wait_until="domcontentloaded")
        dialog = page.locator("#options-dialog")
        expiry = page.locator("#options-expiry")
        status = page.locator("#options-expiry-status")
        advanced = page.locator("#options-advanced")
        symbol = page.locator("#options-symbol")
        results = page.locator("#options-results")
        expect(dialog).to_be_visible()
        assert expiry.evaluate("el => el.tagName") == "SELECT"
        assert dialog.locator('input[type="date"]').count() == 0
        assert advanced.get_attribute("open") is None
        assert not events and not posts, (events, posts)

        symbol.fill("AAPL")
        advanced.locator("summary").click()
        expect(status).to_have_attribute("data-state", "ready")
        expect(expiry).to_be_enabled()
        assert expiry.locator("option").evaluate_all("items => items.map(el => el.value)") == [""] + DATES["AAPL"]
        assert expiry.locator("option").all_text_contents()[1:] == DATES["AAPL"]
        assert expiry.locator('option[value="2030-01-17"]').count() == 0
        assert not posts  # opening a date list must not collect quotes or send an LLM request
        expiry.select_option("2030-01-16")
        advanced.locator("summary").click()
        advanced.locator("summary").click()
        expect(status).to_have_attribute("data-state", "ready")
        expect(expiry).to_have_value("2030-01-16")
        assert sum(event.get("symbol") == "AAPL" for event in events) == 1
        page.locator("#options-submit").click()
        expect(results.locator(".options-plain-report")).to_be_visible()
        assert posts[-1]["body"]["expiry"] == "2030-01-16"
        assert not posts[-1]["body"]["interpret_with_llm"]
        page.locator("#options-view-professional").click()
        expect(results.locator(".options-professional-report")).to_be_visible()
        expect(results.locator(".options-plain-report")).to_be_hidden()
        raw = results.locator(".options-professional-report .options-raw-details")
        raw.locator("summary").first.click()
        expect(raw.locator(".options-chain-table")).to_be_visible()
        page.locator("#options-view-simple").click()
        expect(results.locator(".options-plain-report")).to_be_visible()

        # Closing, language switching and reopening preserve the verified choice.
        page.keyboard.press("Escape")
        page.locator("#language-toggle").click()
        if width <= 760:
            page.locator("#mobile-menu").click()
        page.locator("#nav-options").click()
        expect(status).to_have_attribute("data-state", "ready")
        expect(expiry).to_have_value("2030-01-16")
        expect(expiry.locator("option").first).to_have_text("Nearest available expiration (automatic)")

        # A new symbol immediately removes the old chain's selectable dates.
        symbol.fill("MSFT")
        expect(expiry).to_be_disabled()
        expect(expiry.locator("option")).to_have_count(1)
        symbol.press("Tab")
        expect(status).to_have_attribute("data-state", "ready")
        assert expiry.locator("option").evaluate_all("items => items.map(el => el.value)") == [""] + DATES["MSFT"]
        expect(expiry).to_have_value("")
        expiry.select_option("2030-01-25")
        expiry.scroll_into_view_if_needed()
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"expirations-{width}.png"), animations="disabled")

        # Metadata failure stays explicit and never exposes an unverified manual date.
        symbol.fill("FAIL")
        symbol.press("Tab")
        expect(status).to_have_attribute("data-state", "failed")
        expect(status).to_contain_text("IB Gateway API connection failed")
        expect(expiry).to_be_disabled()
        expect(expiry.locator("option")).to_have_count(1)
        count = len(posts)
        page.locator("#options-submit").click()
        expect(results.locator(".options-plain-report")).to_be_visible()
        assert len(posts) == count + 1 and posts[-1]["body"]["expiry"] is None
        page.locator("#options-refresh-expirations").click()
        expect(status).to_have_attribute("data-state", "failed")
        assert sum(event.get("symbol") == "FAIL" for event in events) == 2  # errors are not cached

        # An empty actual chain also has no manual-date fallback.
        symbol.fill("EMPTY")
        symbol.press("Tab")
        expect(status).to_have_attribute("data-state", "unavailable")
        expect(expiry.locator("option")).to_have_count(1)
        expect(expiry).to_be_disabled()

        # The picker uses the full metadata response, including dates past index 30.
        symbol.fill("LONG")
        symbol.press("Tab")
        expect(status).to_have_attribute("data-state", "ready")
        expect(expiry.locator("option")).to_have_count(41)
        expiry.select_option(DATES["LONG"][-1])
        page.locator("#options-submit").click()
        expect(results.locator(".options-plain-report")).to_be_visible()
        assert posts[-1]["body"]["expiry"] == DATES["LONG"][-1]

        # Explicit batch dates must be checked before any quote/model POST.
        page.locator("#options-analysis-mode").select_option("batch")
        expect(page.locator(".options-expiry-field")).to_be_hidden()
        batch = page.locator("#options-batch-items")
        batch.fill("AAPL 2030-01-17\nMSFT 2030-01-25")
        count = len(posts)
        page.locator("#options-submit").click()
        expect(page.locator("#options-error")).to_be_visible()
        expect(page.locator("#options-error")).to_contain_text("2030-01-17")
        expect(page.locator("#options-error")).to_contain_text("2030-01-16")
        assert len(posts) == count
        batch.fill("FAIL 2030-01-16")
        page.locator("#options-submit").click()
        expect(page.locator("#options-error")).to_be_visible()
        expect(page.locator("#options-error")).to_contain_text("IB Gateway API connection failed")
        assert len(posts) == count
        batch.fill("AAPL 2030-01-16\nAAPL 2030-02-15\nMSFT 2030-01-25")
        page.locator("#options-submit").click()
        expect(results.locator(".options-plain-report")).to_be_visible()
        assert len(posts) == count + 1
        assert posts[-1]["body"]["items"] == [
            {"symbol": "AAPL", "expiry": "2030-01-16"},
            {"symbol": "AAPL", "expiry": "2030-02-15"},
            {"symbol": "MSFT", "expiry": "2030-01-25"}]
        assert sum(event.get("symbol") == "AAPL" for event in events) == 1
        assert sum(event.get("symbol") == "MSFT" for event in events) == 1

        before = len(events)
        batch.fill("AAPL\nMSFT")
        page.locator("#options-submit").click()
        expect(results.locator(".options-plain-report")).to_be_visible()
        assert all(item["expiry"] is None for item in posts[-1]["body"]["items"])
        assert not any(event["kind"] == "metadata" for event in events[before:])
        assert dialog.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")

        # Race test: metadata is serialized; an old symbol cannot overwrite a newer one.
        if width == 1440:
            page.locator("#options-analysis-mode").select_option("single")
            symbol.fill("RACEA")
            symbol.press("Tab")
            page.wait_for_function("() => document.getElementById('options-expiry-status').dataset.state === 'loading'")
            page.wait_for_timeout(100)
            assert len(held) == 1
            symbol.fill("RACEB")
            symbol.press("Tab")
            page.wait_for_timeout(100)
            assert not any(event.get("symbol") == "RACEB" for event in events)
            held.pop().fulfill(json=metadata("RACEA"))
            expect(status).to_have_attribute("data-state", "ready")
            assert expiry.locator("option").evaluate_all("items => items.map(el => el.value)") == [""] + DATES["RACEB"]
            assert expiry.locator('option[value="2030-03-15"]').count() == 0
            assert not any(post["body"].get("symbol") in ("RACEA", "RACEB") for post in posts)

            # Uncached batch metadata requests finish in order before the POST.
            page.locator("#options-analysis-mode").select_option("batch")
            before = len(events)
            batch.fill("SPY 2030-01-16\nRACEB 2030-04-19")
            page.locator("#options-submit").click()
            expect(results.locator(".options-plain-report")).to_be_visible()
            assert [event["kind"] for event in events[before:]] == ["metadata", "analysis"]

            # A success older than 60 seconds must be read again, not silently reused.
            page.evaluate("() => { const now = Date.now.bind(Date); Date.now = () => now() + 61000; }")
            before = len(events)
            batch.fill("AAPL 2030-01-16\nMSFT 2030-01-25")
            page.locator("#options-submit").click()
            expect(results.locator(".options-plain-report")).to_be_visible()
            assert [event["kind"] for event in events[before:]] == ["metadata", "metadata", "analysis"]
            assert [event.get("symbol") for event in events[before:before + 2]] == ["AAPL", "MSFT"]

        assert not errors, errors
        return {"width": width, "height": height, "page_errors": errors,
                "metadata_requests": sum(event["kind"] == "metadata" for event in events),
                "fixture_analysis_posts": len(posts), "events": events}
    finally:
        for route in held:
            route.abort()
        context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "running",
              "scope": "Synthetic API interception only; real deterministic report builders. No IBKR or LLM calls. Not a live-market validation.",
              "viewports": [], "checks": []}
    try:
        with sync_playwright() as runner:
            browser = runner.chromium.launch(channel="msedge", headless=True)
            for width, height in ((320, 740), (390, 844), (1440, 1000)):
                report["viewports"].append(check(browser, args.base.rstrip("/"), width, height))
            browser.close()
        report["checks"] = ["no_arbitrary_date_calendar", "no_automatic_quote_or_llm_request",
                            "actual_chain_membership_including_non_friday_fixture", "literal_dates_without_timezone_shift",
                            "verified_selection_survives_reopen_and_language_change", "symbol_change_clears_old_dates",
                            "success_cache_and_uncached_failure_retry", "truthful_metadata_failure_nearest_default",
                            "empty_chain_has_no_manual_dates", "invalid_batch_date_blocks_post_and_lists_actual_dates",
                            "unavailable_batch_metadata_blocks_post", "success_cache_expires_after_60_seconds",
                            "valid_batch_dates_preserved_and_metadata_deduplicated", "undated_batch_uses_backend_nearest",
                            "stale_response_guard_and_sequential_metadata", "metadata_precedes_analysis_post",
                            "full_metadata_list_beyond_30_dates", "novice_and_professional_report_toggle",
                            "novice_report_and_mobile_containment"]
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "report": str(REPORT), "viewports": len(report["viewports"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
