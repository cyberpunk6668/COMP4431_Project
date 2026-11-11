"""Validate the guided demo using intercepted APIs and the real local Avatar.

API replies use synthetic test records and the real deterministic history
builder/retriever. No IBKR connection or external model call is made.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
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
from app.expert_knowledge import ExpertKnowledge

REPORT = ROOT / "reports/guided_demo_browser_v14.json"
SHOTS = ROOT / "reports/screenshots/guided-demo-v14"


def check(browser, base, width, height, entry="/demo"):
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
    context.add_init_script("localStorage.setItem('finpilot-session','existing-user-conversation');")
    page = context.new_page()
    page.set_default_timeout(10000)
    calls, archive_posts, search_gets, chat_posts, errors, held = [], [], [], [], [], []
    cases = {"archive": "fail", "search": "fail", "chat": "success", "models_unavailable": False}
    records = {}
    knowledge = ExpertKnowledge()
    ranked = knowledge.search("期权成交量与未平仓量", limit=2)
    if ranked:
        ranked[0]["retrieval"]["selection_reason"] = "query_facet"
    if len(ranked) > 1:
        ranked[1]["retrieval"]["selection_reason"] = "context_facet"
    facet = deepcopy(next(item for item in knowledge.documents if item["id"] == "expert.history_bars"))
    facet["retrieval"] = {"method": "curated_support_facet", "selection_reason": "required_facet", "embedding": False,
                          "bm25_rank": None, "char_rank": None, "rrf_score": None, "matched_topics": ["historical bars"]}
    hits = [hit for hit in ranked if hit["id"] != facet["id"]] + [facet]
    primary = hits[0]

    def archive(language):
        dataset = demo_dataset()
        dataset.update(symbol="AAPL", label="Controlled archived history fixture", bar_basis="derived_from_intraday_trades",
                       source_label="IBKR archive fixture; session coverage unverified")
        for index, row in enumerate(dataset["rows"]):
            row.pop("open_interest", None)
            row.pop("oi_asof_date", None)
            # Keep valid OHLC input; add explicit zero/missing display values below.
        record = analyze_history(HistoryDataset.model_validate(dataset), source_kind="ibkr_historical", language=language)
        record["analysis_id"] = str(UUID(int=700 + len(records)))
        record["contract_changes"][0].update(before=0, after=2.74, status="incomparable", change_pct=None)
        record["contract_changes"][1].update(before=10, after=None, status="incomparable", change_pct=None)
        record["daily"][0].update(volume_total=0, put_volume_share=None)
        record["daily"][1]["volume_total"] = None
        record["historical_capture"] = {"row_provenance": [{"trading_date": record["period"]["start"], "right": "C", "observed_hourly_bars": 8,
            "first_bar_at": "2026-11-06T14:30:00Z", "last_bar_at": "2026-11-06T21:00:00Z", "full_session_verified": False}]}
        records[record["analysis_id"]] = record
        return record

    def complete_chat(route, body):
        record = records[body["analysis_id"]]
        session_id = body.get("session_id") or "independent-demo-session-" + str(len(chat_posts))
        if cases["chat"] == "general":
            route.fulfill(json={"session_id": session_id, "answer": "A general answer without historical data.", "mode": "deepseek", "sources": [], "analysis_context": None})
            return
        meta = describe_history(record, body["language"])
        meta["evidence"] = [deepcopy(record["evidence"][-4])]
        meta["evidence"][0].update(id="h.contract.0.trade_close", label="同一合约所收末值", value=2.74, before=0, after=2.74,
                                      delta=None, status="incomparable", unit="USD", delta_unit="USD")
        meta["retrieval"] = {"method": "bm25_char_ngram_rrf", "embedding": False,
                             "hits": [{"id": item["id"], **item["retrieval"]} for item in hits]}
        meta["grounding"] = {"method": "reviewed_support_facets", "scope": "bounded_rule_checks_not_general_entailment",
                             "required_query_facets": ["volume_vs_oi"], "covered_facets": ["volume_vs_oi"],
                             "paragraphs": [{"part": 0, "claim_facets": ["volume_vs_oi"], "expert_source_ids": [primary["id"]],
                                             "supporting_sources": {"volume_vs_oi": [primary["id"]]}}]}
        source = {key: primary[key] for key in ("id", "title", "url", "publisher", "reviewed_at")}
        answer = f"历史记录应与可比性限制一起阅读 [h.contract.0.trade_close]。专业资料支持定义与边界 [{source['id']}]。 <img src=x onerror=alert(1)>"
        route.fulfill(json={"session_id": session_id, "answer": answer, "sources": [source], "mode": "offline" if cases["chat"] == "fallback" else "local-lora" if body["engine"] == "local" else "deepseek",
                            "warning": "network_or_timeout" if cases["chat"] == "fallback" else None, "analysis_context": meta})

    def respond(route):
        request = route.request
        parsed = urlsplit(request.url)
        path = parsed.path
        body = request.post_data_json if request.post_data else None
        calls.append({"method": request.method, "path": path, "body": body})
        if path == "/api/models":
            available = not cases["models_unavailable"]
            route.fulfill(json={"default": "deepseek", "models": [{"id": "deepseek", "label": "DeepSeek", "available": available}, {"id": "local", "label": "Local LoRA", "available": available}]})
        elif path == "/api/options/history/sample":
            archive_posts.append(body)
            if cases["archive"] == "fail":
                route.fulfill(status=404, json={"detail": {"message": "Synthetic archived sample unavailable"}})
            elif cases["archive"] == "hold":
                held.append((route, parse_qs(parsed.query).get("language", ["zh"])[0]))
            else:
                route.fulfill(json=archive(parse_qs(parsed.query).get("language", ["zh"])[0]))
        elif path == "/api/experts/search":
            search_gets.append(parse_qs(parsed.query)["q"][0])
            if cases["search"] == "fail":
                route.fulfill(status=503, json={"detail": "Synthetic search error"})
            else:
                route.fulfill(json=hits)
        elif path == "/api/chat":
            chat_posts.append(body)
            if cases["chat"] == "fail":
                route.fulfill(status=503, json={"detail": "Synthetic model error"})
            elif cases["chat"] == "hold":
                held.append((route, body))
            else:
                complete_chat(route, body)
        else:
            raise AssertionError(f"Unexpected API request: {request.method} {path}")

    context.route("**/api/**", respond)
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(base + entry, wait_until="domcontentloaded")
        expect(page.locator("#demo-model")).to_be_enabled()
        expect(page.locator("#demo-search")).to_be_disabled()
        expect(page.locator("#demo-explain")).to_be_disabled()
        assert [call["path"] for call in calls] == ["/api/models"]
        assert page.evaluate("localStorage.getItem('finpilot-session')") == "existing-user-conversation"
        expect(page.locator("#demo-motion")).to_be_checked()
        expect(page.locator(".fp-avatar")).to_have_attribute("data-reduced-motion", "true")
        page.locator("#demo-avatar-2d").focus()
        page.keyboard.press("Enter")
        expect(page.locator(".fp-avatar")).to_have_attribute("data-actual-mode", "2d")
        expect(page.locator("#demo-avatar-renderer")).to_have_text("2D / SVG")
        page.locator("#demo-avatar-3d").click()
        page.wait_for_function("() => document.querySelector('#demo-avatar-renderer').textContent === '3D / WEBGL' || document.getElementById('demo-avatar-note').textContent.includes('3D 不可用')")
        actual_mode = page.locator(".fp-avatar").get_attribute("data-actual-mode")
        if actual_mode == "3d":
            expect(page.locator(".fp-avatar__canvas")).to_have_count(1)
        else:
            expect(page.locator("#demo-avatar-note")).to_contain_text("当前显示真实 2D")

        # Archive errors are local and do not unlock downstream steps.
        page.locator("#demo-load").click()
        expect(page.locator("#demo-load-error")).to_contain_text("Synthetic archived sample unavailable")
        expect(page.locator("#demo-search")).to_be_disabled()
        cases["archive"] = "hold"
        page.locator("#demo-load").click()
        expect(page.locator("#demo-load")).to_be_disabled()
        expect(page.locator(".fp-avatar")).to_have_attribute("data-state", "thinking")
        page.locator("#demo-load").dispatch_event("click")
        assert len(archive_posts) == 2 and len(held) == 1
        route, language = held.pop()
        route.fulfill(json=archive(language))
        expect(page.locator("#demo-archive-result")).to_be_visible()
        first_id = page.locator("#demo-archive-result").get_attribute("data-analysis-id")
        expect(page.locator("#demo-search")).to_be_enabled()
        expect(page.locator("#demo-explain")).to_be_disabled()
        expect(page.locator("#demo-archive-result")).to_contain_text("不是官方收盘或结算价")
        expect(page.locator("#demo-archive-result")).to_contain_text("未返回，保持缺失")
        expect(page.locator(".contract-card").first).to_contain_text("0 USD")
        expect(page.locator(".contract-card").nth(1)).to_contain_text("未提供")
        page.locator("#demo-archive-result .quiet-details").last.locator("summary").click()
        expect(page.locator("#demo-archive-result table").last).to_contain_text("0 份合约")
        expect(page.locator("#demo-archive-result table").last).to_contain_text("未提供")
        assert not chat_posts and not search_gets

        # Suggestions only edit text; the explicit search button makes the GET.
        page.locator('[data-question="oi"]').click()
        assert not search_gets
        page.locator("#demo-search").focus()
        page.keyboard.press("Enter")
        expect(page.locator("#demo-search-error")).to_contain_text("Synthetic search error")
        expect(page.locator("#demo-explain")).to_be_disabled()
        cases["search"] = "success"
        page.locator("#demo-search").click()
        expect(page.locator(".expert-card")).to_have_count(len(hits))
        expect(page.locator("#demo-explain")).to_be_enabled()
        expect(page.locator("#demo-expert-results")).to_contain_text("每条回答实际采用")
        expect(page.locator(".expert-card").first).to_contain_text(primary["reviewed_at"])
        expect(page.locator(".expert-card").first).to_contain_text(primary["publisher"])
        page.locator(".expert-card").first.locator(".retrieval-details > summary").click()
        expect(page.locator(".expert-card").first).to_contain_text("不是准确率")
        expect(page.locator(".expert-card").first).to_contain_text("为问题或数据约束选用")
        expect(page.locator(".expert-card").first.locator(".retrieval-ranks")).to_have_count(1)
        curated = page.locator(f'.expert-card[data-source-id="{facet["id"]}"]')
        curated.locator(".retrieval-details > summary").click()
        expect(curated).to_contain_text("不是自然检索排名")
        expect(curated.locator(".retrieval-ranks")).to_have_count(0)
        assert not chat_posts
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.locator("#demo-experts").screenshot(path=str(SHOTS / f"expert-step-{width}.png"), animations="disabled")

        # Model calls are explicit, use the selected engine, and never inherit an existing session.
        page.locator("#demo-model").select_option("local")
        cases["chat"] = "hold"
        page.locator("#demo-explain").click()
        expect(page.locator("#demo-explain")).to_be_disabled()
        expect(page.locator("#demo-load")).to_be_disabled()
        expect(page.locator("#demo-model")).to_be_disabled()
        page.locator("#demo-explain").dispatch_event("click")
        assert len(chat_posts) == 1
        assert chat_posts[0]["session_id"] is None and chat_posts[0]["analysis_id"] == first_id and chat_posts[0]["engine"] == "local"
        cases["chat"] = "success"
        route, body = held.pop()
        complete_chat(route, body)
        expect(page.locator(".demo-message.assistant")).to_have_count(1)
        expect(page.locator(".demo-expert-reference")).to_have_text("专家来源 1")
        expect(page.locator(".demo-expert-reference")).to_have_attribute("data-source-id", primary["id"])
        assert page.locator(".demo-message img").count() == 0
        assert "<img" in page.locator(".demo-answer-text").inner_text()
        page.locator("button.demo-inline-reference").click()
        expect(page.locator(".demo-evidence-card")).to_be_visible()
        assert page.locator(".demo-evidence-card").evaluate("el => document.activeElement === el")
        expect(page.locator(".demo-evidence-card")).to_contain_text("不可直接比较")
        expect(page.locator(".demo-evidence-card")).to_contain_text("0 USD")
        expect(page.locator(".reply-source")).to_have_count(1)
        page.locator(".demo-grounding > summary").click()
        expect(page.locator(".demo-grounding")).to_contain_text("成交量与未平仓量区别")
        expect(page.locator(".demo-grounding")).to_contain_text("不是逐句事实证明")
        expect(page.locator(".demo-grounding")).to_contain_text("未识别的说法不在这套规则保证内")
        expect(page.locator(".demo-grounding a")).to_have_text(primary["title"])
        expect(page.locator(".demo-grounding a")).to_have_attribute("data-source-id", primary["id"])

        # Failed and local fallback answers preserve input/data and truthfully display mode.
        session_id = "independent-demo-session-1"
        cases["chat"] = "fail"
        page.locator("#demo-chat-input").fill("为什么不能把持仓缺失当作零？")
        page.locator("#demo-explain").click()
        expect(page.locator("#demo-ai-error")).to_contain_text("Synthetic model error")
        expect(page.locator("#demo-chat-input")).to_have_value("为什么不能把持仓缺失当作零？")
        expect(page.locator(".demo-message.assistant")).to_have_count(1)
        assert chat_posts[-1]["session_id"] == session_id
        cases["chat"] = "fallback"
        page.locator("#demo-chat-input").press("Enter")
        expect(page.locator(".demo-message.assistant")).to_have_count(2)
        expect(page.locator(".demo-message.assistant").last.locator(".message-mode")).to_have_text("本地说明")
        expect(page.locator(".demo-message.assistant").last).to_contain_text("实际返回模式")
        cases["chat"] = "general"
        page.locator("#demo-chat-input").fill("hello")
        page.locator("#demo-explain").click()
        expect(page.locator(".demo-message.assistant")).to_have_count(3)
        expect(page.locator(".demo-message.assistant").last).to_contain_text("普通问答没有使用历史数据依据")
        expect(page.locator(".demo-message.assistant").first).to_contain_text("历史区间")

        page.locator("#demo-language").click()
        expect(page.locator(".demo-expert-reference").first).to_have_text("Expert source 1")
        expect(page.locator("#demo-title")).to_contain_text("Explanations you can check")
        expect(page.locator(".demo-grounding").first.locator("summary")).to_have_text("Which knowledge topics were checked")
        expect(page.locator(".demo-message.assistant").last).to_contain_text("general answer did not use historical data")
        page.locator("#demo-ai").screenshot(path=str(SHOTS / f"ai-step-{width}.png"), animations="disabled")
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(SHOTS / f"guided-demo-{width}.png"), animations="disabled")
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
        assert page.evaluate("localStorage.getItem('finpilot-session')") == "existing-user-conversation"
        assert not any(call["path"].startswith("/api/sessions") or call["path"] in ("/api/options/analyze","/api/options/batch","/api/options/history/fetch") for call in calls)

        # Reloaded archives create a fresh demo context rather than reusing an old reply/session.
        cases["archive"] = "success"
        page.locator("#demo-load").click()
        expect(page.locator(".demo-message")).to_have_count(0)
        expect(page.locator("#demo-explain")).to_be_disabled()
        page.locator("#demo-search").click()
        expect(page.locator("#demo-explain")).to_be_enabled()
        cases["chat"] = "success"
        page.locator("#demo-explain").click()
        expect(page.locator(".demo-message.assistant")).to_have_count(1)
        assert chat_posts[-1]["session_id"] is None and chat_posts[-1]["analysis_id"] != first_id

        if width == 1440:
            cases["models_unavailable"] = True
            page.reload(wait_until="domcontentloaded")
            expect(page.locator("#demo-model-status")).to_contain_text("没有可用引擎")
            expect(page.locator("#demo-model")).to_be_disabled()
            page.locator("#demo-load").click()
            expect(page.locator("#demo-search")).to_be_enabled()
            page.locator("#demo-search").click()
            expect(page.locator(".expert-card")).to_have_count(len(hits))
            expect(page.locator("#demo-explain")).to_be_disabled()
        assert not errors, errors
        return {"width": width,"height": height,"avatar_actual_mode": actual_mode,"page_errors": errors,"fixture_archive_posts": len(archive_posts),"fixture_search_gets": len(search_gets),"explicit_fixture_chat_posts": len(chat_posts),"real_broker_calls": 0,"external_model_calls": 0}
    except Exception:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"failed-{width}.png"), full_page=False)
        raise
    finally:
        for route, _ in held:
            route.abort()
        context.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base",default="http://127.0.0.1:8000")
    parser.add_argument("--entry",default="/demo",choices=["/demo","/static/demo.html"])
    args=parser.parse_args()
    global REPORT
    if args.entry != "/demo":
        REPORT = ROOT / "reports/guided_demo_preview_v14.json"
    report={"checked_at":datetime.now(timezone.utc).isoformat(),"entry":args.entry,"status":"running","viewports":[],
            "scope":"All APIs intercepted; deterministic local analyzer/retriever and actual local Three.js/SVG Avatar. Synthetic records test interface contracts only, without real broker or external model requests."}
    try:
        with sync_playwright() as runner:
            browser=runner.chromium.launch(channel="msedge",headless=True)
            for width,height in ((320,740),(390,844),(1440,1000)):
                report["viewports"].append(check(browser,args.base.rstrip("/"),width,height,args.entry))
            browser.close()
        report["checks"]=["models_status_only_on_initial_load","no_existing_user_session_read_or_mutation","real_avatar_2d_3d_or_truthful_fallback","keyboard_avatar_switch","system_reduced_motion",
                          "archive_failure_does_not_unlock_later_steps","explicit_archive_replay_and_duplicate_lock","historical_period_contract_identity_and_partial_coverage","zero_is_not_missing_and_missing_oi_is_not_zero",
                          "suggestions_do_not_search_or_call_model","explicit_local_expert_search_and_error_state","publisher_reviewed_date_and_source_url","actual_dual_ranks_are_not_accuracy","curated_facets_are_not_natural_ranked_hits",
                          "candidate_sources_distinct_from_answer_citations","selected_ready_engine_and_null_first_demo_session","explicit_model_call_and_duplicate_lock","per_reply_data_cards_and_human_expert_citations","html_is_literal_text","failed_model_request_retains_draft_and_archive",
                          "local_fallback_mode_is_visible","general_questions_do_not_inherit_fake_historical_evidence","bounded_reviewed_topics_link_to_returned_sources_without_general_entailment_claim","chinese_english_labels","new_archive_resets_only_demo_context","unready_models_leave_archive_and_search_usable","mobile_containment"]
        report["status"]="passed"
    except Exception as error:
        report.update(status="failed",error=str(error))
        raise
    finally:
        REPORT.parent.mkdir(parents=True,exist_ok=True)
        REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({"status":report["status"],"report":str(REPORT),"viewports":len(report["viewports"])},ensure_ascii=False))


if __name__=="__main__":
    main()
