"""Verify collective options reports in Edge with local synthetic responses.

This script intercepts every options API request. It never reads brokerage
data or submits a model request.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.options_analytics import analyze_option_snapshot
from app.options_collective import build_batch_comparison, build_collective_analysis
from app.options_narrative import build_model_evidence


REPORT = ROOT / "reports/options_collective_browser_v7.json"
SHOTS = ROOT / "reports/screenshots/options-v7"


def sample(symbol, expiry, *, language="zh", iv_shift=0):
    stamp = datetime.now(timezone.utc).isoformat()
    quotes = []
    for strike in (90, 95, 100, 105, 110):
        for side in ("C", "P"):
            iv = 0.20 + abs(strike - 100) / 200 + iv_shift
            if side == "P" and strike < 100:
                iv += 0.02
            quotes.append({
                "strike": strike, "right": side, "expiration": expiry,
                "bid": 1.9, "ask": 2.1, "last": 2,
                "volume": 300 if side == "P" and strike == 95 else 30,
                "open_interest": 800 if side == "C" and strike == 105 else 100,
                "implied_volatility": iv, "greeks_basis": "model",
                "delta": (0.5 if strike == 100 else 0.25 if strike > 100 else 0.75) if side == "C" else (-0.5 if strike == 100 else -0.25 if strike < 100 else -0.75),
                "market_data_type": 3, "received_at": stamp, "quote_received_at": stamp,
                "volume_received_at": stamp, "open_interest_received_at": stamp,
                "greeks_received_at": stamp,
            })
    snapshot = {
        "source": "fixture", "symbol": symbol, "expiration": expiry, "currency": "USD",
        "trading_class": symbol, "multiplier": 100, "started_at": stamp, "received_at": stamp,
        "requested_strikes": [90, 95, 100, 105, 110], "quotes": quotes,
        "underlying": {"price": 100, "bid": 99.9, "ask": 100.1, "price_basis": "midpoint", "market_data_type": 3, "received_at": stamp},
    }
    analysis = analyze_option_snapshot(snapshot, language=language)
    collective = build_collective_analysis(snapshot, analysis, language=language)
    return {"snapshot": snapshot, **analysis, "collective": collective, "capture_age_seconds": 2.3,
            "snapshot_id": "synthetic-collective-check", "interpretation": {"status": "skipped"}}


def narrative(evidence, language="zh", *, hostile=False):
    available = {record["id"] for record in evidence if record["value"] is not None}
    preferred = ["g0.volume_put_share", "g1.volume_put_share", "comparison.report_1_atm_iv"]
    ids = [identifier for identifier in preferred if identifier in available]
    if not ids:
        ids = list(available)[:2]
    zh = language == "zh"
    summary = "成交与存量分布出现分歧，需结合流动性与期限差异阅读。" if zh else "Activity and positioning differ and need liquidity and expiration context."
    if hostile:
        summary += " <img src=x onerror=alert(1)>"
    return {
        "status": "ok", "model": "fixture-model", "basis": "descriptive_snapshot",
        "report": {
            "summary": {"text": summary, "evidence_ids": ids},
            "observations": [{"text": "成交在少数行权价集中，需联合流动性解释。" if zh else "Activity clusters at a few strikes and needs liquidity context.", "evidence_ids": ids}],
            "conflicts": [{"text": "成交活跃方向与未平仓存量分布不同。" if zh else "Activity and outstanding contracts differ.", "evidence_ids": ids}],
            "scenarios": [{"condition": "后续样本中的成交集中继续" if zh else "Concentration persists in later samples", "implication": "继续核查价差和覆盖范围" if zh else "Recheck spreads and coverage", "evidence_ids": ids}],
            "limitations": ["仅为合成测试样本。" if zh else "Synthetic test sample."],
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def model_records(reports, comparison=None):
    payload = build_model_evidence(reports, comparison)
    return [record for cohort in payload["cohorts"] for record in cohort["evidence"]] + payload["comparisons"]


def check(browser, base, width, height):
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
    page = context.new_page()
    errors, bodies = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    expiry = (datetime.now(timezone.utc).date() + timedelta(days=14)).isoformat()
    later = (datetime.now(timezone.utc).date() + timedelta(days=42)).isoformat()

    def options(route):
        path = urlsplit(route.request.url).path
        if path.endswith("/status"):
            route.fulfill(json={"status": "tcp_ready", "enabled": True, "endpoint": "127.0.0.1:4002"})
            return
        body = route.request.post_data_json
        bodies.append({"path": path, "body": body})
        language = body["language"]
        if path.endswith("/batch"):
            reports, failures = [], []
            for index, item in enumerate(body["items"]):
                if item["symbol"] == "MISS":
                    failures.append({**item, "code": "ibkr_entitlement_missing"})
                else:
                    reports.append(sample(item["symbol"], item["expiry"] or expiry, language=language, iv_shift=index * .03))
            comparison = build_batch_comparison(reports, language=language)
            result = {"reports": reports, "failures": failures, "comparison": comparison,
                      "completed_at": datetime.now(timezone.utc).isoformat(),
                      "interpretation": narrative(model_records(reports, comparison), language) if body["interpret_with_llm"] else {"status": "skipped"}}
        else:
            result = sample(body["symbol"], body.get("expiry") or expiry, language=language)
            if body["interpret_with_llm"]:
                result["interpretation"] = narrative(model_records([result]), language, hostile=True)
        route.fulfill(json=result)

    context.route("**/api/options/**", options)
    try:
        page.goto(base + "/workspace?view=options", wait_until="domcontentloaded")
        dialog = page.locator("#options-dialog")
        result = page.locator("#options-results")
        expect(dialog).to_be_visible()
        assert not bodies
        page.locator("#options-symbol").fill("SPY")
        page.locator("#options-feed-mode").select_option("3")
        page.locator("#options-interpret").check()
        page.locator("#options-submit").click()
        expect(result.locator(".options-assessment")).to_contain_text("整批期权综合分析")
        expect(result.locator(".options-model-report")).to_contain_text("API 模型综合报告")
        expect(result.locator(".options-model-report")).to_contain_text("条件情景")
        expect(result.locator(".options-model-report")).to_contain_text("<img")
        assert result.locator("img").count() == 0
        expect(result.locator(".options-distribution")).to_have_count(2)
        assert result.locator("meter").count() > 0
        expect(result).to_contain_text("成交与持仓是否一致")
        expect(result).to_contain_text("采集距报告完成 2.3 秒")
        assert result.locator(".options-raw-details").get_attribute("open") is None

        single_reference = result.locator(".options-model-report .options-evidence-links button").filter(has_text="[g0.volume_put_share]").first
        expect(single_reference).to_be_visible()
        single_reference.click()
        expect(result.locator(".options-evidence-catalogue")).to_have_attribute("open", "")
        assert page.evaluate("() => document.activeElement.tagName") == "TR"
        assert page.evaluate("() => document.activeElement.textContent.includes('SPY')")
        result.locator(".options-raw-details > summary").click()
        expect(result.locator("tbody tr").last).to_be_visible()
        assert result.locator(".options-chain-table tbody tr").count() == 10

        page.locator("#options-analysis-mode").select_option("batch")
        expect(page.locator("#options-symbol")).to_be_hidden()
        page.locator("#options-batch-items").fill("AAPL\nAAPL")
        page.locator("#options-submit").click()
        expect(page.locator("#options-error")).to_be_visible()
        assert len(bodies) == 1
        page.locator("#options-batch-items").fill(f"AAPL {expiry}\nAAPL {later}\nMISS")
        page.locator("#options-submit").click()
        expect(result.locator(".options-assessment").first).to_contain_text("跨期权链联合分析")
        expect(result).to_contain_text("同标的到期结构")
        expect(result).to_contain_text("MISS")
        expect(result.locator(".options-chain-report")).to_have_count(2)
        assert bodies[-1]["path"] == "/api/options/batch"
        assert len(bodies[-1]["body"]["items"]) == 3
        assert bodies[-1]["body"]["market_data_type"] == 3
        for identifier, expected_expiry in [("g0.volume_put_share", expiry), ("g1.volume_put_share", later), ("comparison.report_1_atm_iv", expiry)]:
            reference = result.locator(".options-model-report .options-evidence-links button").filter(has_text=f"[{identifier}]").first
            expect(reference).to_be_visible()
            reference.click()
            assert page.evaluate("() => document.activeElement.tagName") == "TR"
            assert page.evaluate("date => document.activeElement.textContent.includes(date)", expected_expiry)
            assert page.evaluate("() => document.activeElement.textContent.includes('AAPL')")
        result.locator(".options-evidence-catalogue").first.locator("summary").click()
        result.locator(".options-chain-report > summary").first.click()
        expect(result.locator(".options-chain-report .options-collective").first).to_be_visible()

        scroll, client = dialog.evaluate("el => [el.scrollWidth, el.clientWidth]")
        assert scroll <= client + 1, (width, scroll, client)
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
        dialog.evaluate("el => { const top=document.getElementById('options-results').getBoundingClientRect().top; el.scrollTop += top-el.getBoundingClientRect().top-22; }")
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"collective-{width}.png"), full_page=False, animations="disabled")
        page.keyboard.press("Escape")
        page.locator("#language-toggle").click()
        if width <= 760:
            page.locator("#mobile-menu").click()
        page.locator("#nav-options").click()
        expect(dialog).to_contain_text("Cross-chain comparison")
        expect(page.locator("#options-batch-hint")).to_contain_text("Up to four lines")
        assert not errors, errors
        return {"width": width, "height": height, "single_requests": 1, "batch_requests": 1, "page_errors": errors}
    finally:
        context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "running", "scope": "Synthetic option API responses only. No broker or cloud model requests.", "checks": [], "viewports": []}
    try:
        with sync_playwright() as runner:
            browser = runner.chromium.launch(channel="msedge", headless=True)
            for width, height in [(320, 740), (390, 844), (1440, 1000)]:
                report["viewports"].append(check(browser, args.base.rstrip("/"), width, height))
            browser.close()
        report["checks"] = ["no_auto_analysis", "collective_report_before_raw_data", "liquidity_and_distributions", "positioning_and_volatility", "structured_model_summary_conflicts_and_scenarios", "model_text_is_safe", "single_prefixed_evidence_reference_resolves", "batch_g0_g1_and_comparison_references_resolve_to_correct_cohort", "raw_contract_details_expand", "batch_input_validation", "batch_request_contract", "partial_failure_visible", "term_structure_and_comparison_rows", "nested_chain_reports", "mobile_dialog_containment", "english_reopen"]
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        report["source_sha256"] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            "web/index.html", "web/options.js", "web/options.css", "app/options_collective.py")}
        report["screenshots"] = [path.relative_to(ROOT).as_posix() for path in sorted(SHOTS.glob("*.png"))]
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(report["status"], len(report["checks"]), len(report["viewports"]))


if __name__ == "__main__":
    main()
