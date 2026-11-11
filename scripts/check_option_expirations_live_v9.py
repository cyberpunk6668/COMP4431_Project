"""Check real IBKR expiration metadata through HTTP and Edge's date selector.

Exactly one real metadata GET is initiated by each viewport. No option routes
are mocked, and no analyze/batch/quote/LLM endpoint is permitted. The desktop
response is also the API baseline, avoiding an unnecessary third broker read.
"""
import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/options_expirations_live_v9.json"
SHOTS = ROOT / "reports/screenshots/options-v9-live"
METADATA_FIELDS = {
    "source", "symbol", "expirations", "trading_class", "currency",
    "date_kind", "timezone", "as_of",
}


def validate_metadata(data):
    assert isinstance(data, dict) and set(data) == METADATA_FIELDS, "Unexpected metadata fields"
    assert data["source"] == "ibkr" and data["symbol"] == "AAPL"
    assert data["date_kind"] == "expiration" and data["timezone"] == "America/New_York"
    assert data["currency"] == "USD" and data["trading_class"] == "AAPL"
    dates = data["expirations"]
    assert isinstance(dates, list) and dates, "No live AAPL expirations returned"
    assert dates == sorted(set(dates)), "Metadata dates must be sorted and unique"
    for value in dates:
        assert isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
        assert date.fromisoformat(value).isoformat() == value
    assert datetime.fromisoformat(data["as_of"]).tzinfo is not None
    return dates


def check_viewport(browser, base, width, height, reference):
    context = browser.new_context(
        viewport={"width": width, "height": height}, reduced_motion="reduce",
        timezone_id="Asia/Shanghai", is_mobile=width < 600, has_touch=width < 600,
    )
    page = context.new_page()
    page_errors, blocked, metadata_requests = [], [], []
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    def guard(route):
        request = route.request
        parsed = urlsplit(request.url)
        path = parsed.path
        if request.method != "GET":
            blocked.append({"method": request.method, "path": path})
            route.abort()
        elif path == "/api/options/expirations":
            assert parse_qs(parsed.query) == {"symbol": ["AAPL"]}
            metadata_requests.append({"method": "GET", "path": path, "symbol": "AAPL"})
            route.continue_()
        elif path in {"/api/health", "/api/models", "/api/options/status"}:
            route.continue_()
        elif path == "/api/sessions":
            # Conversation history is irrelevant to this check; prevent even
            # reading private titles. Screenshot masking is applied as well.
            route.fulfill(json={"sessions": []})
        else:
            blocked.append({"method": request.method, "path": path})
            route.abort()

    context.route("**/api/**", guard)
    result = {"width": width, "height": height, "status": "running"}
    try:
        page.goto(base + "/workspace?view=options", wait_until="domcontentloaded")
        dialog = page.locator("#options-dialog")
        expiry = page.locator("#options-expiry")
        advanced = page.locator("#options-advanced")
        status = page.locator("#options-expiry-status")
        expect(dialog).to_be_visible()
        assert advanced.get_attribute("open") is None
        assert expiry.evaluate("el => el.tagName") == "SELECT"
        assert page.locator('input[type="date"]').count() == 0
        assert not metadata_requests, "Opening the tool must not fetch dates automatically"
        page.locator("#options-symbol").fill("AAPL")
        started = time.monotonic()
        with page.expect_response(
            lambda response: urlsplit(response.url).path == "/api/options/expirations",
            timeout=30000,
        ) as received:
            advanced.locator("summary").click()
        response = received.value
        assert response.request.method == "GET" and response.status == 200, "Real metadata HTTP request failed"
        metadata = response.json()
        dates = validate_metadata(metadata)
        expect(status).to_have_attribute("data-state", "ready", timeout=30000)
        expect(expiry).to_be_enabled()
        values = expiry.locator("option").evaluate_all("items => items.map(el => el.value)")
        labels = expiry.locator("option").all_text_contents()
        assert values == [""] + dates, "DOM choices differ from the real HTTP metadata"
        assert labels[1:] == dates, "Date labels changed the broker's literal dates"
        assert labels[0].strip() and ("自动" in labels[0] or "automatic" in labels[0])
        if reference is not None:
            assert dates == reference, "The two real viewport metadata reads returned different expirations"

        # Exercise a real listed selection and cache-preserving reopen without
        # submitting the analysis form or requesting market quotes.
        expiry.select_option(dates[-1])
        expect(expiry).to_have_value(dates[-1])
        advanced.locator("summary").click()
        advanced.locator("summary").click()
        expect(expiry).to_have_value(dates[-1])
        expiry.select_option("")
        expect(expiry).to_have_value("")
        expiry.select_option(dates[0])
        expect(expiry).to_have_value(dates[0])
        expiry.scroll_into_view_if_needed()
        assert len(metadata_requests) == 1, "Reopening must reuse the successful metadata result"
        assert not blocked, "An unexpected API request was attempted"
        assert not page_errors, "Browser page errors occurred"
        bounds = expiry.bounding_box()
        assert bounds and bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width + 1
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        SHOTS.mkdir(parents=True, exist_ok=True)
        shot = SHOTS / f"expirations-live-{width}.png"
        page.screenshot(path=str(shot), animations="disabled", mask=[page.locator("#session-list")])
        result.update(
            status="passed", metadata=metadata, http_status=response.status,
            real_metadata_gets=len(metadata_requests), metadata_delivery="real HTTP, no options interception",
            metadata_to_ready_seconds=round(time.monotonic() - started, 3),
            option_values=values, automatic_option_label=labels[0],
            listed_selection_and_automatic_default=True, selection_survives_reopen=True,
            native_date_inputs=0, horizontal_overflow=False, page_errors=page_errors,
            attempted_forbidden_requests=blocked, screenshot=str(shot.relative_to(ROOT)),
            screenshot_masks=["#session-list"],
        )
        return result, dates
    finally:
        context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    assert urlsplit(base).hostname in {"127.0.0.1", "localhost", "::1"}, "Local service only"
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(), "status": "running",
        "scope": "Live AAPL broker metadata through local HTTP and Edge DOM on desktop/mobile. Two real metadata GETs, one per viewport. No analyze, batch, quote or LLM requests. This verifies metadata-to-selector integration, not option analysis or live market quotes.",
        "privacy": "Only the expiration metadata allowlist is saved. Session-list GET is replaced with an empty list for privacy, and the screenshot masks the session list. No options endpoint is mocked. No account fields are recorded.",
        "viewports": [], "checks": [],
    }
    try:
        with sync_playwright() as runner:
            request = runner.request.new_context(base_url=base)
            health = request.get("/api/health")
            assert health.status == 200
            report["service_version"] = health.json()["version"]
            assert report["service_version"] == "9.0.0"
            request.dispose()
            browser = runner.chromium.launch(channel="msedge", headless=True)
            report["browser"] = {"channel": "msedge", "version": browser.version, "headless": True}
            reference = None
            try:
                for width, height in ((1440, 1000), (390, 844)):
                    result, reference = check_viewport(browser, base, width, height, reference)
                    report["viewports"].append(result)
            finally:
                browser.close()
        report["real_metadata_gets"] = sum(item["real_metadata_gets"] for item in report["viewports"])
        assert report["real_metadata_gets"] == 2
        report["checks"] = [
            "real_http_aapl_expiration_metadata", "real_http_dates_equal_desktop_and_mobile_dom",
            "only_automatic_and_actual_iso_expirations", "no_arbitrary_date_calendar",
            "literal_dates_without_timezone_shift", "listed_and_automatic_selection",
            "selection_survives_reopen_without_extra_broker_read", "no_horizontal_overflow",
            "no_page_errors", "no_quote_analysis_batch_or_llm_requests", "session_privacy_mask",
        ]
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "report": str(REPORT), "viewports": len(report["viewports"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
