"""Exercise the options dialog in Edge using intercepted options API responses."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/options_browser_v6.json"


def analysis_fixture(live: bool, interpret: bool) -> dict:
    timestamp = "2026-11-11T13:00:00Z"
    mode = 1 if live else 3
    status = "live" if live else "delayed"
    strikes = [595, 600, 605] if live else [600]
    quotes = []
    for strike in strikes:
        quotes.extend([
            {"strike": strike, "right": "C", "bid": 4.8, "ask": 5.2, "volume": 10,
             "open_interest": 0, "implied_volatility": 0.20, "delta": 0.24,
             "market_data_type": mode, "received_at": timestamp},
            {"strike": strike, "right": "P", "bid": 4.5 if live else 0, "ask": 4.9, "volume": 20,
             "open_interest": None, "implied_volatility": 0.24, "delta": -0.26,
             "market_data_type": mode, "received_at": timestamp},
        ])
    requested = 6 if live else 14
    return {
        "snapshot_id": "abc123def456" * 5,
        "snapshot": {
            "source": "ibkr", "symbol": "SPY", "expiration": "2026-11-20", "currency": "USD",
            "started_at": timestamp, "received_at": timestamp, "quotes": quotes,
            "underlying": {"price": 601.1, "received_at": timestamp,
                           "market_data_type": mode, "price_basis": "midpoint"},
        },
        "quality": {
            "market_data_status": status, "requested_contracts": requested, "received_contracts": len(quotes),
            "valid_quote_contracts": len(quotes), "fresh_live_quote_contracts": len(quotes) if live else 0,
            "quote_coverage": len(quotes) / requested, "fresh_live_pair_coverage": 1 if live else 0,
            "freshness_seconds": 30, "llm_eligible": live,
            "reason_codes": [] if live else ["market_data_not_consistently_live"],
        },
        "metrics": {
            "put_call_volume": {"value": 2, "market_data_status": status, "paired_strikes": len(strikes),
                                "pair_coverage": len(quotes) / requested,
                                "put_total": 20 * len(strikes), "call_total": 10 * len(strikes)},
            "put_call_open_interest": {"value": None, "reason": "insufficient_paired_strikes"},
            "iv_skew_25_delta": {"value": 4, "market_data_status": status, "put_iv": 0.24, "call_iv": 0.20},
            "atm_straddle": {"value": None, "reason": "wide_bid_ask_spread"},
        },
        "signals": [{"metric": "put_call_volume", "code": "more_put_volume"}],
        "caveats": ["测试使用受控的行情样本。"],
        "interpretation": (
            {"status": "ok", "model": "test-model", "evidence": ["put_call_volume"], "text": "<img src=x onerror=alert(1)> Evidence."}
            if live and interpret else {"status": "unavailable" if interpret else "skipped"}
        ),
    }


def check_viewport(browser, base: str, width: int, height: int, direct: bool) -> dict:
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
    page = context.new_page()
    errors, bodies = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def mock_options(route):
        path = urlsplit(route.request.url).path
        if path.endswith("/status"):
            route.fulfill(json={"status": "tcp_ready", "enabled": True, "endpoint": "127.0.0.1:4002"})
            return
        assert path.endswith("/analyze"), path
        body = route.request.post_data_json
        bodies.append(body)
        if len(bodies) == 4:
            route.fulfill(status=503, json={"detail": {"code": "ibkr_entitlement_missing", "message": "Unavailable"}})
            return
        route.fulfill(json=analysis_fixture(body.get("market_data_type") == 1, body["interpret_with_llm"]))

    context.route("**/api/options/**", mock_options)
    try:
        page.goto(f"{base}/workspace" + ("?view=options" if direct else ""), wait_until="domcontentloaded")

        def open_dialog():
            if width <= 760:
                page.locator("#mobile-menu").click()
            page.locator("#nav-options").click()

        if not direct:
            open_dialog()
        dialog = page.locator("#options-dialog")
        result = page.locator("#options-results")
        submit = page.locator("#options-submit")
        expect(page.get_by_role("dialog", name="期权链分析")).to_be_visible()
        expect(page.locator("#options-gateway")).to_contain_text("网关端口可访问")
        assert not bodies, "Opening the dialog must not request analysis"
        page.locator("#options-symbol").fill("spy")
        submit.click()
        expect(result.locator(".options-feed-pill")).to_have_text("延迟行情")
        expect(result).to_contain_text("14.3%")
        expect(result).to_contain_text("本次未发送指标")
        expect(result.locator("tbody tr")).to_have_count(2)
        assert bodies[0] == {"symbol": "SPY", "expiry": None, "radius": 3,
                             "interpret_with_llm": False, "language": "zh"}, bodies

        result.locator(".options-chain-filter select").select_option("P")
        expect(result.locator("tbody tr")).to_have_count(1)
        expect(result.locator("tbody tr td").nth(2)).to_have_text("0")
        expect(result.locator("tbody tr td").nth(6)).to_have_text("—")
        scroll_width, client_width = dialog.evaluate("element => [element.scrollWidth, element.clientWidth]")
        assert scroll_width <= client_width + 1, (width, scroll_width, client_width)
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth"), width

        page.locator("#options-expiry").fill("2026-11-20")
        page.locator("#options-radius").select_option("6")
        page.locator("#options-interpret").check()
        page.locator("#options-feed-mode").select_option("3")
        submit.click()
        expect(result).to_contain_text("本次无法提供模型解读")
        assert bodies[1] == {"symbol": "SPY", "expiry": "2026-11-20", "radius": 6,
                             "interpret_with_llm": True, "language": "zh", "market_data_type": 3}, bodies

        page.locator("#options-feed-mode").select_option("1")
        submit.click()
        expect(result.locator(".options-llm-text")).to_contain_text("<img")
        expect(result).to_contain_text("快照编号 abc123def456")
        expect(result).to_contain_text("模型选中的指标 · 看跌 / 看涨成交量")
        assert result.locator("img").count() == 0, "Model output must render as text"
        assert bodies[2]["market_data_type"] == 1, bodies

        submit.click()
        expect(page.locator("#options-error")).to_contain_text("未获得请求的行情")
        expect(result).to_be_hidden()
        page.keyboard.press("Escape")
        expect(dialog).to_be_hidden()
        page.locator("#language-toggle").click()
        open_dialog()
        expect(page.get_by_role("dialog", name="Option chain analysis")).to_be_visible()
        assert not errors, errors
        return {"width": width, "height": height, "deep_link": direct, "fixture_analysis_requests": len(bodies)}
    finally:
        context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(), "status": "running", "browser": "Microsoft Edge",
        "scope": "All options calls intercepted with fixtures. No IB Gateway or LLM calls from this browser test.",
        "checks": [], "viewports": [],
    }
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            for width, height, direct in [(320, 740, False), (390, 844, True), (1440, 1000, False)]:
                report["viewports"].append(check_viewport(browser, args.base.rstrip("/"), width, height, direct))
            browser.close()
        report["checks"] = [
            "navigation_and_deep_link", "no_automatic_analysis", "gateway_tcp_status", "default_feed_mode_omitted",
            "explicit_delayed_and_live_requests", "model_opt_in_and_unavailable_result", "live_delayed_labels_and_coverage",
            "missing_values_distinct_from_zero", "call_put_filter", "scroll_containment",
            "model_response_uses_text_only", "provider_error_clears_previous_result", "escape_and_english_reopen",
        ]
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        REPORT.parent.mkdir(exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{report['status']}: {len(report['checks'])} checks, {len(report['viewports'])} viewports")


if __name__ == "__main__":
    main()
