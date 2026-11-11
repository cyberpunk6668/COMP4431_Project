"""Check historical import, honest sample labels and expert chat with fixture APIs.

All /api/ requests are intercepted. The real deterministic history analyzer is
used on synthetic records; no broker or external LLM is contacted by this test.
"""
import argparse
from copy import deepcopy
import csv
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.options_history import HistoryDataset, analyze_history, demo_dataset
from app.history_chat import describe_history

REPORT = ROOT / "reports/options_history_browser_v13.json"
SHOTS = ROOT / "reports/screenshots/options-history-v13"


def check(browser, base, width, height):
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(10000)
    calls, posts, chats, errors = [], [], [], []
    records, sessions = {}, {}
    fail_sample = [False]
    dataset = demo_dataset()
    days = sorted({row["trading_date"] for row in dataset["rows"]})
    custom = {"label": '<img src=x onerror=alert(1)> 我的历史资料', "symbol": "AAPL", "expiry": dataset["expiry"],
              "source_label": "My export; not independently verified", "rows": []}
    for index, day in enumerate(days):
        for side in ("C", "P"):
            custom["rows"].append({"trading_date": day, "strike": 100, "right": side, "close": 2 + index,
                                    "volume": 0 if index == 0 else None if index == 1 and side == "C" else 100,
                                    "open_interest": 200})
    for side in ("C", "P"):
        custom["rows"].append({"trading_date": days[0], "strike": 105, "right": side, "close": 1, "volume": 40})

    def save(data, kind, language):
        report = analyze_history(HistoryDataset.model_validate(data), source_kind=kind, language=language)
        report["analysis_id"] = str(UUID(int=500 + len(records)))
        if kind == "ibkr_historical":
            for change in report["changes"]:
                if "volume" in change["id"]:
                    change.update(status="incomparable", delta=None, reason="historical_bar_coverage_unverified", direction="unavailable")
        records[report["analysis_id"]] = report
        return report

    def respond(route):
        request = route.request
        parsed = urlsplit(request.url)
        path = parsed.path
        language = parse_qs(parsed.query).get("language", ["zh"])[0]
        body = request.post_data_json if request.method in ("POST", "PUT") and request.post_data else None
        calls.append({"method": request.method, "path": path, "body": body})
        if path == "/api/health":
            route.fulfill(json={"status": "ok", "mode": "deepseek", "knowledge_documents": 0})
        elif path == "/api/models":
            route.fulfill(json={"default": "deepseek", "models": [{"id": "deepseek", "label": "DeepSeek", "available": True}]})
        elif path == "/api/sessions" and request.method == "GET":
            route.fulfill(json={"sessions": [{"id": item["id"], "title": item["title"]} for item in sessions.values()]})
        elif path == "/api/sessions" and request.method == "POST":
            identifier = "history-session-" + str(len(sessions) + 1)
            sessions[identifier] = {"id": identifier, "title": body["title"], "active_analysis_id": None, "messages": []}
            route.fulfill(status=201, json=sessions[identifier])
        elif path.startswith("/api/sessions/"):
            session = sessions[path.split("/")[3]]
            if path.endswith("/analysis"):
                session["active_analysis_id"] = body["analysis_id"]
                route.fulfill(json={"active_analysis_id": body["analysis_id"], "active_analysis": describe_history(records[body["analysis_id"]])})
            else:
                active = describe_history(records[session["active_analysis_id"]]) if session["active_analysis_id"] else None
                route.fulfill(json={**session, "active_analysis": active, "analysis_history": [active] if active else []})
        elif path == "/api/options/status":
            route.fulfill(json={"status": "disabled", "enabled": False})
        elif path.startswith("/api/options/analyses/"):
            route.fulfill(json=records[path.rsplit("/", 1)[1]])
        elif path == "/api/options/history/demo":
            posts.append({"path": path, "body": body})
            route.fulfill(json=save(demo_dataset(), "demo", language))
        elif path == "/api/options/history/sample":
            posts.append({"path": path, "body": body})
            if fail_sample[0]:
                route.fulfill(status=404, json={"detail": "Saved historical archive is not available in this synthetic check"})
            else:
                data = {**deepcopy(custom), "label": "Controlled saved-archive fixture", "bar_basis": "derived_from_intraday_trades"}
                route.fulfill(json=save(data, "ibkr_historical", language))
        elif path == "/api/options/history/import":
            posts.append({"path": path, "body": body})
            route.fulfill(json=save(body, "import", language))
        elif path == "/api/chat":
            chats.append(body)
            record = records[body["analysis_id"]]
            meta = describe_history(record)
            meta["evidence"] = [record["changes"][0]]
            meta["retrieval"] = {"method": "bm25_char_ngram_rrf", "embedding": False,
                                 "hits": [{"id": "expert.volume", "bm25_rank": 1, "char_rank": 1, "rrf_score": .03}]}
            source = {"id": "expert.volume", "title": "Option activity and open-interest definitions", "url": "https://www.optionseducation.org/",
                      "snippet": "Volume counts reported contracts; it does not establish trader direction."}
            answer = "这份历史样本的计数来自本地记录 [h.change.volume_total]。专家资料解释了计数的意义和限制 [expert.volume]。"
            session = sessions[body["session_id"]]
            message = {"role": "assistant", "content": answer, "mode": "deepseek", "sources": [source], "analysis_context": meta}
            session["messages"].extend([{"role": "user", "content": body["message"]}, message])
            route.fulfill(json={"session_id": session["id"], "answer": answer, "mode": "deepseek", "sources": [source],
                                "analysis_context": meta, "active_analysis": describe_history(record), "analysis_history": [describe_history(record)]})
        else:
            raise AssertionError(f"Unexpected API route: {request.method} {path}")

    context.route("**/api/**", respond)
    page.on("pageerror", lambda error: errors.append(str(error)))

    def open_options():
        if width <= 760:
            page.locator("#mobile-menu").click()
        page.locator("#nav-options").click()
        expect(page.locator("#options-dialog")).to_be_visible()

    try:
        page.goto(base + "/workspace?view=history", wait_until="domcontentloaded")
        expect(page.locator("#options-dialog")).to_be_visible()
        panel = page.locator("#history-panel")
        result = page.locator("#history-result")
        expect(panel).to_have_attribute("open", "")
        assert not posts and not chats
        with page.expect_download() as download:
            page.locator("#history-template-csv").click()
        template = Path(download.value.path()).read_text(encoding="utf-8")
        assert template.strip().startswith("trading_date,strike,right") and len(template.splitlines()) == 1
        assert not posts
        with page.expect_download() as download:
            page.locator("#history-template-json").click()
        assert json.loads(Path(download.value.path()).read_text())["rows"] == []

        # Server-owned demo provenance remains visible and never becomes a market claim.
        page.locator("#history-demo").click()
        expect(result).to_have_attribute("data-source-kind", "demo")
        expect(result.locator(".history-source-badge")).to_contain_text("教学合成数据")
        expect(result.locator(".history-question-card")).to_have_count(4)
        expect(result.locator(".history-chart figcaption")).to_contain_text("教学合成数据")
        assert len(posts) == 1 and posts[0]["path"].endswith("/demo") and not chats

        # Import a JSON that attempts to claim a verified source: only permitted fields are sent.
        untrusted = {**deepcopy(custom), "source": {"kind": "ibkr_historical", "verified": True}, "is_demo": True}
        untrusted["rows"][2]["volume"] = "   "
        page.locator("#history-file").set_input_files({"name": "history.json", "mimeType": "application/json", "buffer": json.dumps(untrusted).encode()})
        expect(page.locator("#history-submit")).to_be_enabled()
        expect(page.locator("#history-preview")).to_be_visible()
        before = len(posts)
        page.locator("#history-submit").click()
        expect(result).to_have_attribute("data-source-kind", "import")
        assert len(posts) == before + 1
        payload = posts[-1]["body"]
        assert "source" not in payload and "is_demo" not in payload and "volume" not in payload["rows"][2]
        assert payload["rows"][0]["volume"] == 0
        expect(result.locator(".history-source-badge")).to_contain_text("来源未独立核验")
        assert result.locator("img").count() == 0
        assert "<img" in result.locator("h3").inner_text()
        expect(result.locator(".history-chart circle[data-value='0']")).to_have_count(1)
        expect(result.locator(".history-chart circle")).to_have_count(2)
        expect(result.locator(".history-chart polyline")).to_have_count(0)  # missing middle date breaks the line
        result.locator('[data-metric="oi_total"]').click()
        expect(result.locator(".history-chart")).to_contain_text("不能用零代替")
        expect(result.locator(".history-chart circle")).to_have_count(0)
        result.locator('[data-metric="volume_total"]').click()
        expect(result.locator(".history-change[data-change-id='h.change.volume_total']")).to_contain_text("+200 份合约")
        expect(result.locator(".history-change[data-change-id='h.change.oi_total']")).to_contain_text("暂不能比较")

        missing_volume = deepcopy(custom)
        missing_volume["rows"][4].pop("volume")
        page.locator("#history-file").set_input_files({"name": "missing-volume.json", "mimeType": "application/json", "buffer": json.dumps(missing_volume).encode()})
        expect(page.locator("#history-submit")).to_be_enabled()
        page.locator("#history-submit").click()
        unavailable_volume = result.locator(".history-change[data-change-id='h.change.volume_total']")
        expect(unavailable_volume).to_contain_text("缺失记录")
        expect(unavailable_volume).not_to_contain_text("未平仓量或独立统计日期")

        # A quoted CSV follows the same explicit preview/import flow.
        stream = StringIO()
        writer = csv.DictWriter(stream, fieldnames=["trading_date","strike","right","close","volume","open_interest","oi_asof_date"])
        writer.writeheader()
        writer.writerows({**row, **({"oi_asof_date": days[0]} if row.get("open_interest") is not None else {})} for row in custom["rows"])
        page.locator("#history-file").set_input_files({"name": "history.csv", "mimeType": "text/csv", "buffer": stream.getvalue().encode()})
        expect(page.locator("#history-submit")).to_be_enabled()
        page.locator("#history-label").fill("CSV 样本")
        page.locator("#history-submit").click()
        expect(result.locator("h3")).to_have_text("CSV 样本")
        assert posts[-1]["path"].endswith("/import")
        assert posts[-1]["body"]["rows"][0]["volume"] == 0
        expect(result.locator(".history-change[data-change-id='h.change.oi_total']")).to_contain_text("未平仓统计日期未推进")

        # Reject oversized and malformed files locally, preserving the successful result.
        before = len(posts)
        page.locator("#history-file").set_input_files({"name": "large.json", "mimeType": "application/json", "buffer": b" " * 32001})
        expect(page.locator("#history-error")).to_contain_text("超过 32 KB")
        expect(page.locator("#history-submit")).to_be_disabled()
        page.locator("#history-file").set_input_files({"name": "bad.csv", "mimeType": "text/csv", "buffer": b'trading_date,strike,right\n"unclosed,100,C'})
        expect(page.locator("#history-error")).to_contain_text("CSV 格式有误")
        page.locator("#history-file").set_input_files({"name": "wrong-units.json", "mimeType": "application/json", "buffer": json.dumps({**custom, "currency": "EUR", "multiplier": 10}).encode()})
        expect(page.locator("#history-error")).to_contain_text("不会把其他币种或合约乘数改写")
        expect(page.locator("#history-submit")).to_be_disabled()
        page.locator("#history-file").set_input_files({"name": "wrong-basis.json", "mimeType": "application/json", "buffer": json.dumps({**custom, "bar_basis": "quote_midpoints"}).encode()})
        expect(page.locator("#history-error")).to_contain_text("请核对文件的价格口径")
        assert len(posts) == before
        expect(result.locator("h3")).to_have_text("CSV 样本")

        # Saved broker-history replay is a local archive read, with partial-session boundaries.
        page.locator("#history-sample").click()
        expect(result).to_have_attribute("data-source-kind", "ibkr_historical")
        expect(result.locator(".history-derived-boundary")).to_contain_text("不保证覆盖完整交易时段")
        expect(result.locator(".history-chart figcaption")).to_contain_text("不能据此判断全日成交量")
        expect(result.locator(".history-chart polyline")).to_have_count(0)
        prices = result.locator("details").filter(has=page.locator('summary')).filter(has_text="逐合约所收 bar 末值变化").first
        prices.locator("summary").click()
        expect(prices).to_contain_text("首日所收 bar 末值")
        expect(result.locator(".history-change").first).to_contain_text("暂不能比较")
        expect(result.locator(".history-change").first).to_contain_text("完整交易时段覆盖未核验")
        saved_id = result.get_attribute("data-analysis-id")
        fail_sample[0] = True
        page.locator("#history-sample").click()
        expect(page.locator("#history-error")).to_contain_text("此前的复盘")
        expect(result).to_have_attribute("data-analysis-id", saved_id)
        fail_sample[0] = False
        assert not chats

        # Explicit attachment only prefills; the model is called only by a separate Send.
        result.locator(".history-followup button").click()
        expect(page.locator("#options-dialog")).not_to_be_visible()
        card = page.locator("#analysis-context-card")
        expect(card).to_have_attribute("data-analysis-id", saved_id)
        expect(card).to_contain_text("历史复盘区间")
        expect(card.locator(".analysis-refresh-button")).to_have_count(0)
        assert not chats
        page.locator("#send-button").click()
        expect(page.locator(".message.assistant")).to_have_count(1)
        assert len(chats) == 1 and chats[0]["analysis_id"] == saved_id
        expect(page.locator(".message-analysis-context")).to_contain_text("历史复盘")
        expect(page.locator(".message-sources")).to_contain_text("Option activity")
        expert_citation = page.locator('.message.assistant a[data-source-id="expert.volume"]')
        expect(expert_citation).to_have_text("专家来源 1")
        expect(expert_citation).to_have_attribute("data-source-id", "expert.volume")
        expect(expert_citation).to_have_attribute("href", "https://www.optionseducation.org/")
        expect(expert_citation).to_have_attribute("title", "Option activity and open-interest definitions")
        expect(page.locator(".message-sources .source-number")).to_have_text("1")
        page.locator(".expert-retrieval > summary").click()
        expect(page.locator(".expert-retrieval")).to_contain_text("不是结论正确率")
        expect(page.locator(".analysis-inline-citation")).to_have_count(1)
        page.locator(".analysis-inline-citation").click()
        expect(page.locator(".analysis-evidence-card")).to_be_visible()

        # The existing saved-analysis action dispatches back to this historical report.
        before = len(posts)
        card.locator(".analysis-text-button").first.click()
        expect(page.locator("#options-dialog")).to_be_visible()
        expect(result).to_have_attribute("data-analysis-id", saved_id)
        assert len(posts) == before
        page.keyboard.press("Escape")
        page.locator("#language-toggle").click()
        expect(expert_citation).to_have_text("Expert source 1")
        expect(expert_citation).to_have_attribute("data-source-id", "expert.volume")
        expect(page.locator(".message-sources .source-number")).to_have_text("1")
        open_options()
        expect(panel.locator("summary").first).to_contain_text("Historical review")
        expect(result.locator(".history-derived-boundary")).to_contain_text("not an official close")
        expect(result.locator(".history-change").first).to_contain_text("Full-session coverage is unverified")
        page.locator("#history-demo").click()
        expect(result).to_have_attribute("data-source-kind", "demo")
        expect(result.locator(".history-source-badge")).to_contain_text("Synthetic teaching data")
        expect(result.locator(".history-chart figcaption")).to_contain_text("Synthetic teaching data")
        assert len(chats) == 1
        SHOTS.mkdir(parents=True, exist_ok=True)
        result.locator(".history-chart").screenshot(path=str(SHOTS / f"history-chart-{width}.png"), animations="disabled")
        result.scroll_into_view_if_needed()
        page.screenshot(path=str(SHOTS / f"history-review-{width}.png"), animations="disabled")
        assert page.locator("#options-dialog").evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        return {"width": width, "height": height, "page_errors": errors, "local_fixture_posts": len(posts), "explicit_fixture_chat_posts": len(chats), "real_broker_calls": 0, "external_model_calls": 0}
    except Exception:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"failed-{width}.png"))
        raise
    finally:
        context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "result_version": "v13_human_citation_label_revision", "status": "running", "viewports": [],
              "scope": "All API requests intercepted; synthetic rows are analyzed by the real deterministic history builder. No real IBKR or external model calls. UI checks do not validate imported provenance or trading-session coverage."}
    try:
        with sync_playwright() as runner:
            browser = runner.chromium.launch(channel="msedge", headless=True)
            for width, height in ((320,740),(390,844),(1440,1000)):
                report["viewports"].append(check(browser,args.base.rstrip("/"),width,height))
            browser.close()
        report["checks"] = ["history_deeplink_and_no_automatic_data_or_model_request", "empty_templates_contain_no_fabricated_market_rows",
                            "server_owned_demo_label_remains_synthetic", "local_json_preview_and_explicit_import", "client_drops_untrusted_verified_source_and_demo_flags",
                            "blank_is_missing_and_zero_is_preserved", "four_plain_questions", "missing_chart_points_break_lines", "missing_oi_asof_has_no_fake_aggregate",
                            "change_units_and_incomparability", "csv_import", "oversized_or_malformed_files_block_post", "foreign_currency_multiplier_or_unknown_price_basis_is_not_relabelled", "failed_request_preserves_previous_review",
                            "saved_broker_archive_is_distinct_from_demo", "partial_intraday_bars_are_not_official_closes_or_full_day_volume",
                            "historical_attach_prefills_without_sending", "historical_context_has_no_live_refresh", "explicit_send_separates_local_evidence_and_expert_sources",
                            "retrieval_rank_is_not_accuracy", "saved_history_dispatches_without_new_capture", "chinese_and_english", "mobile_containment"]
        report["status"] = "passed"
    except Exception as failure:
        report.update(status="failed",error=str(failure))
        raise
    finally:
        REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({"status":report["status"],"report":str(REPORT),"viewports":len(report["viewports"])},ensure_ascii=False))


if __name__ == "__main__":
    main()
