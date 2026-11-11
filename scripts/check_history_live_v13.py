"""Opt-in real Edge / HTTP historical capture and expert-grounded follow-up QA.

Without --live: no browser, HTTP, broker or model requests and no report changes.
With --live: one history/fetch (three bounded historical requests), then exactly
two UI chat turns. Each answer may use the server's single schema repair; no
script or network retries are made. Only the sidebar session-list GET is privacy
filtered. Financial, expert and chat responses are never mocked. Only the owned
session is deleted; the immutable historical analysis remains for audit.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from time import perf_counter
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/history_cloud_v13.json"
SHOTS = ROOT / "reports/screenshots/history-v13-live"
QUESTIONS = (
    "用白话复盘这几天的历史数据，标明能确认的变化和不能比较的部分，并给出专家依据。",
    "这些数据能说明现在市场看空吗？未平仓量为什么没有给出？",
)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()


def safe_text(value):
    value = re.sub(r"\bsk-[A-Za-z0-9_-]{6,}|\bBearer\s+[^\s\"']+", "[credential-redacted]", str(value), flags=re.I)
    value = re.sub(r"\b(?:DU|U|F|I)[0-9]{5,12}\b", "[account-redacted]", value, flags=re.I)
    return re.sub(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", "[identifier-redacted]", value, flags=re.I)


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _equal(actual, expected):
    if _finite(actual) and _finite(expected):
        assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), "Local evidence number was changed"
    else:
        assert type(actual) is type(expected) and actual == expected, "Local evidence field was changed"


def read_response(response, report, expected=200):
    if response.status != expected:
        code = None
        try:
            detail = response.json().get("detail")
            if isinstance(detail, dict) and re.fullmatch(r"[a-z0-9_]{1,80}", str(detail.get("code", ""))):
                code = detail["code"]
                diagnostics = detail.get("diagnostics")
                if isinstance(diagnostics, dict):
                    # Do not copy arbitrary server strings, raw payloads or account fields.
                    report["provider_diagnostics"] = {key: value for key, value in diagnostics.items()
                        if key in {"stage", "history_requests", "historical_requests", "requested", "received", "error_codes", "elapsed_seconds"}
                        and (type(value) in (int, float, bool) or key == "stage" and isinstance(value, str) and re.fullmatch(r"[a-z0-9_]{1,80}", value)
                             or key == "error_codes" and isinstance(value, list) and all(type(x) is int for x in value))}
        except (ValueError, AttributeError):
            pass
        raise AssertionError(f"HTTP {response.status} for owned acceptance request; code={code}")
    return response.json()


def audit_history(record, requested):
    """Independent checks against the returned immutable record, not model prose."""
    assert record["analysis_kind"] == "historical_options"
    assert record["source"]["kind"] == "ibkr_historical" and record["source"]["verified"] is True
    assert record["source"].get("verification_scope"), "Gateway provenance scope must be stated"
    assert record["bar_basis"] == "derived_from_intraday_trades"
    assert record["symbol"] == requested["symbol"] and record["expiry"] == requested["expiry"]
    assert UUID(record["analysis_id"]).version == 4
    capture = record.get("historical_capture") or record.get("extra", {}).get("historical_capture")
    assert isinstance(capture, dict) and capture["history_requests"] == 3, "Expected three server-reported historical requests"
    aggregation = capture["aggregation"]
    assert aggregation["native_eod"] is False and aggregation["full_session_verified"] is False
    assert aggregation["timezone"] == "America/New_York"
    assert capture["request"]["what_to_show"] == "TRADES" and capture["request"]["keep_up_to_date"] is False
    assert capture["request"]["bar_size"] == "1 hour"
    days = [item["date"] for item in record["daily"]]
    assert len(days) >= 2 and days == sorted(set(days))
    assert record["period"] == {"start": days[0], "end": days[-1]}
    assert days[-1] < datetime.now(UTC).astimezone(ZoneInfo("America/New_York")).date().isoformat()
    assert all(item.get("oi_total") is None and item.get("put_oi_share") is None and item.get("oi_asof_date") is None for item in record["daily"])
    assert all(row["strike"] == requested["strike"] and row["right"] in {"C", "P"} and row.get("open_interest") is None for row in record["rows"])
    assert {row["right"] for row in record["rows"]} == {"C", "P"}
    evidence = {item["id"]: item for item in record["evidence"]}
    assert len(evidence) == len(record["evidence"]), "Duplicate historical evidence IDs"
    for item in record["changes"]:
        if "volume" in item["id"]:
            assert item["status"] == "incomparable" and item["delta"] is None
            assert item["reason"] == "historical_bar_coverage_unverified"
        if "oi" in item["id"]:
            assert item["before"] is None and item["after"] is None and item["delta"] is None
    comparable_prices = []
    for item in evidence.values():
        if "status" not in item:
            continue
        if item["status"] != "comparable":
            assert item.get("delta") is None
            continue
        assert _finite(item["before"]) and _finite(item["after"]) and _finite(item["delta"])
        expected = item["after"] - item["before"]
        if item["unit"] == "fraction":
            expected *= 100
            assert item["delta_unit"] == "percentage_points"
        _equal(item["delta"], expected)
        expected_direction = "increase" if expected > 0 else "decrease" if expected < 0 else "unchanged"
        assert item["direction"] in {expected_direction, {"increase": "increased", "decrease": "decreased", "unchanged": "unchanged"}[expected_direction]}
        if item["id"].startswith(("h.contract.", "h.underlying.")):
            comparable_prices.append(item["id"])
    assert len([key for key in comparable_prices if key.startswith("h.contract.")]) == 2
    assert "h.underlying.trade_close" in comparable_prices
    assert len(record.get("underlying_history", [])) >= 2
    return {
        "source": "ibkr_historical", "source_verified_scope": "Returned by configured Gateway only; no independent exchange calibration or complete-session verification",
        "captured_at": capture.get("checked_at"), "ingested_at": record.get("ingested_at"),
        "bar_basis": record["bar_basis"], "period": record["period"], "dates": days,
        "server_reported_history_requests": capture["history_requests"],
        "request": {key: capture["request"].get(key) for key in ("symbol", "expiry", "strike", "calendar_days", "bar_size", "what_to_show", "use_rth", "keep_up_to_date", "start_inclusive_utc", "end_exclusive_utc")},
        "aggregation": {key: aggregation.get(key) for key in ("kind", "native_eod", "partial_bars", "full_session_verified", "timezone")},
        "daily": [{key: item.get(key) for key in ("date", "received_contracts", "common_contracts", "volume_total", "put_volume_share", "oi_total", "put_oi_share", "oi_asof_date")} for item in record["daily"]],
        "comparable_price_evidence_ids": comparable_prices,
        "local_changes": [{key: item.get(key) for key in ("id", "before", "after", "delta", "delta_unit", "unit", "status", "reason", "direction")} for item in record["changes"]],
        "historical_oi_available": False, "instantaneous_bbo_available": False,
    }


def audit_answer(reply, record, *, require_data):
    assert reply.get("mode") == "deepseek" and not reply.get("warning"), "A real validated DeepSeek reply is required"
    attempts, repairs = reply.get("generation_attempts"), reply.get("schema_repair_attempts")
    assert type(attempts) is int and 1 <= attempts <= 2
    assert type(repairs) is int and 0 <= repairs <= 1 and attempts == repairs + 1
    context = reply["analysis_context"]
    assert context["analysis_id"] == record["analysis_id"] and context["analysis_kind"] == "historical_options"
    assert context["source"] == "ibkr_historical" and context["historical_data"] is True
    assert context["period"] == record["period"] and context["stale"] is False and context["realtime_guaranteed"] is False
    assert context["verification_scope"] == record["source"]["verification_scope"]
    assert context["scopes"][0]["market_data_status"] == "historical"
    assert context["scopes"][0]["symbol"] == record["symbol"] and context["scopes"][0]["expiry"] == record["expiry"]
    assert context["captured_at"] == datetime.fromisoformat(record["ingested_at"].replace("Z", "+00:00")).astimezone(UTC).isoformat()
    assert "未经独立交易所校准" in context["notice"] and "不代表当前行情" in context["notice"]
    original = {item["id"]: item for item in record["evidence"]}
    local = {item["id"]: item for item in context["evidence"]}
    assert len(local) == len(context["evidence"]) and set(local) <= original.keys()
    assert context["evidence_ids"] == list(local)
    for identifier, item in local.items():
        source = original[identifier]
        for key in ("value", "unit", "before", "after", "delta", "delta_unit", "status", "reason", "direction", "trading_date", "previous_trading_date", "oi_asof_date"):
            if key in source:
                _equal(item.get(key), source[key])
        assert item["scope"] == "history" and item["market_data_status"] == "historical"
    if require_data:
        assert local, "Historical review should cite local observations, not only generic definitions"
    knowledge = {doc["id"]: doc for doc in json.loads((ROOT / "data/expert_knowledge.json").read_text(encoding="utf-8"))["documents"]}
    retrieval = context["retrieval"]
    assert retrieval["method"] == "bm25_char_ngram_rrf" and retrieval["embedding"] is False
    hits = {item["id"] for item in retrieval["hits"]}
    assert hits <= knowledge.keys()
    experts = {item["id"]: item for item in reply["sources"]}
    assert experts, "Expert-grounded questions must return cited expert sources"
    assert set(experts) <= hits and context["expert_source_ids"] == list(experts)
    for identifier, item in experts.items():
        for key in ("title", "url", "publisher", "reviewed_at"):
            assert item[key] == knowledge[identifier][key]
    citations = set(re.findall(r"\[([A-Za-z][A-Za-z0-9_.-]*)\]", reply["answer"]))
    assert citations == set(local) | set(experts), "Unknown, omitted or mismatched inline citation"
    prose = reply["answer"].split("\n\n", 1)[-1]
    prose = re.sub(r"\[[A-Za-z][A-Za-z0-9_.-]*\]", "", prose)
    assert not any(char.isdigit() for char in prose), "Model prose supplied a figure outside local cards"
    return {
        "mode": reply["mode"], "warning": reply.get("warning"),
        "server_reported_generation_attempts": attempts, "server_reported_schema_repair_attempts": repairs,
        "answer_excerpt": safe_text(reply["answer"])[:6000],
        "local_evidence_ids": list(local), "expert_source_ids": list(experts),
        "cited_comparable_price": any(item.get("status") == "comparable" and identifier.startswith(("h.contract.", "h.underlying.")) for identifier, item in local.items()),
        "cited_incomparable_measure": any(item.get("status") == "incomparable" for item in local.values()),
        "cited_missing_oi": any("oi" in identifier and item.get("value") is None for identifier, item in local.items()),
        "evidence_values": [{key: item[key] for key in ("id", "value", "unit", "before", "after", "delta", "status", "reason") if key in item} for item in local.values()],
    }


def run(base, requested):
    from playwright.sync_api import expect, sync_playwright

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    report_path = REPORT if not REPORT.exists() else REPORT.with_stem(REPORT.stem + "-" + run_id)
    shot_dir = SHOTS / run_id
    report = {"checked_at": datetime.now(UTC).isoformat(), "status": "running", "phase": "initializing",
              "transport": "Actual Edge 1440x1000 → loopback HTTP → IBKR historical provider and DeepSeek",
              "privacy": "Fresh context; session-list GET privacy filtered to owned session; sidebar screenshots masked. No headers, keys, account data or session IDs recorded.",
              "no_financial_response_mocking": True, "automatic_script_retries": 0, "automatic_network_retries": 0,
              "model_budget": {"answer_turns": 2, "maximum_generations": 4, "maximum_schema_repairs_per_answer": 1},
              "provider_count_visibility": "Historical and model attempt counts are server-reported; browser observes HTTP/UI turns, not provider-internal protocol calls.",
              "turns": [], "screenshots": [], "checks": [], "counters": {"history_fetch_http_requests": 0, "chat_http_requests": 0, "confirmed_deepseek_replies": 0}}
    started = perf_counter()
    errors, blocked = [], []
    owned_sid, analysis_id, context, page, browser = None, None, None, None, None
    try:
        with sync_playwright() as runner:
            browser = runner.chromium.launch(channel="msedge", headless=True)
            report["browser"] = {"channel": "msedge", "version": browser.version, "headless": True, "viewport": {"width": 1440, "height": 1000}}
            context = browser.new_context(base_url=base, viewport={"width": 1440, "height": 1000}, reduced_motion="reduce", timezone_id="Asia/Shanghai")
            request = context.request
            try:
                report["phase"] = "health"
                health = read_response(request.get(base + "/api/health", timeout=10000, max_retries=0), report)
                assert health.get("version") == "13.0.0", "A restarted v13 server is required"
                assert health.get("mode") in {"deepseek", "online"}, "Cloud chat is not configured"
                report["app_version"] = health["version"]
                report["phase"] = "historical_capture"
                report["counters"]["history_fetch_http_requests"] += 1
                saved = read_response(request.post(base + "/api/options/history/fetch", data=requested, timeout=300000, max_retries=0), report)
                analysis_id = saved.get("analysis_id")
                report["analysis_id"] = analysis_id
                report["phase"] = "historical_capture_audit"
                report["capture"] = audit_history(saved, requested)
                old_hash = fingerprint(saved)
                report["analysis_fingerprint"] = old_hash
                own = read_response(request.post(base + "/api/sessions", data={"title": "Historical v13 owned browser acceptance"}, timeout=10000, max_retries=0), report, 201)
                owned_sid = own["id"]
                read_response(request.put(f"{base}/api/sessions/{owned_sid}/analysis", data={"analysis_id": analysis_id}, timeout=10000, max_retries=0), report)
                own_row = {key: own[key] for key in ("id", "title", "created_at", "updated_at")}

                def guard(route):
                    incoming = route.request
                    path = urlsplit(incoming.url).path
                    if incoming.method == "GET" and path == "/api/sessions":
                        route.fulfill(json={"sessions": [own_row]})
                        return
                    if incoming.method == "POST" and path == "/api/chat":
                        body = incoming.post_data_json
                        index = report["counters"]["chat_http_requests"]
                        if (index < 2 and body.get("session_id") == owned_sid and body.get("analysis_id") == analysis_id
                                and body.get("message") == QUESTIONS[index] and body.get("language") == "zh" and body.get("engine") == "deepseek"):
                            report["counters"]["chat_http_requests"] += 1
                            route.continue_()
                            return
                    if incoming.method == "GET" and path in {"/api/health", "/api/models", "/api/options/status",
                            f"/api/sessions/{owned_sid}", f"/api/sessions/{owned_sid}/export", f"/api/options/analyses/{analysis_id}"}:
                        route.continue_()
                        return
                    blocked.append({"method": incoming.method, "path": safe_text(path)})
                    route.abort()

                context.route("**/api/**", guard)
                context.add_init_script("localStorage.setItem('finpilot-session', %s);localStorage.setItem('finpilot-language','zh');localStorage.setItem('finpilot-engine','deepseek');" % json.dumps(owned_sid))
                page = context.new_page()
                page.set_default_timeout(15000)
                page.on("pageerror", lambda error: errors.append(safe_text(error)))
                report["phase"] = "initial_ui_context"
                page.goto(base + "/workspace", wait_until="domcontentloaded")
                card, editor = page.locator("#analysis-context-card"), page.locator("#message-input")
                expect(card).to_be_visible()
                expect(card).to_have_attribute("data-analysis-id", analysis_id)
                expect(card).to_contain_text("历史复盘区间")
                expect(card).to_contain_text(saved["period"]["start"])
                expect(card).to_contain_text(saved["period"]["end"])
                expect(card).to_contain_text("本地网关返回")
                expect(card.locator(".analysis-refresh-button")).to_have_count(0)
                expect(page.locator("#model-select")).to_have_value("deepseek")
                replies = []
                for index, question in enumerate(QUESTIONS):
                    report["phase"] = f"turn_{index+1}_ui_send"
                    editor.fill(question)
                    with page.expect_response(lambda value: value.request.method == "POST" and urlsplit(value.url).path == "/api/chat", timeout=90000) as response:
                        page.locator("#send-button").click()
                    reply = read_response(response.value, report)
                    summary = {"mode": reply.get("mode"), "warning": reply.get("warning"), "answer_excerpt": safe_text(reply.get("answer", ""))[:6000],
                               "server_reported_generation_attempts": reply.get("generation_attempts"), "server_reported_schema_repair_attempts": reply.get("schema_repair_attempts")}
                    report["turns"].append(summary)
                    report["phase"] = f"turn_{index+1}_reply_validation"
                    summary.update(audit_answer(reply, saved, require_data=index == 0))
                    replies.append(reply)
                    report["counters"]["confirmed_deepseek_replies"] += 1
                    report["phase"] = f"turn_{index+1}_ui_validation"
                    expect(editor).to_be_enabled()
                    expect(editor).to_have_value("")
                    expect(card).to_have_attribute("data-analysis-id", analysis_id)
                    expect(card.locator(".analysis-refresh-button")).to_have_count(0)
                    messages = page.locator("#chat-messages .message.assistant")
                    expect(messages).to_have_count(index + 1)
                    latest = messages.last
                    expect(latest.locator(".message-mode")).to_contain_text("DeepSeek")
                    expect(latest.locator(".message-warning")).to_have_count(0)
                    expect(latest.locator(".message-body")).to_contain_text(reply["answer"].split("\n\n", 1)[0])
                    expect(latest.locator(".message-analysis-context")).to_have_attribute("data-analysis-id", analysis_id)
                    expect(latest.locator(".source-card")).to_have_count(len(reply["sources"]))
                    expect(latest.locator(".expert-retrieval")).to_have_count(1)
                    for identifier in reply["analysis_context"]["evidence_ids"]:
                        expect(latest.locator(f'.analysis-evidence-card[data-evidence-id="{identifier}"]')).to_have_count(1)
                        expect(latest.locator(f'.analysis-inline-citation[data-evidence-id="{identifier}"]').first).to_be_visible()
                    for source in reply["sources"]:
                        expect(latest.locator(f'.inline-citation[data-source-id="{source["id"]}"]').first).to_have_attribute("href", source["url"])
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "Horizontal overflow"
                    latest.scroll_into_view_if_needed()
                    shot_dir.mkdir(parents=True, exist_ok=True)
                    shot = shot_dir / f"historical-turn-{index+1}-desktop.png"
                    page.screenshot(path=str(shot), animations="disabled", mask=[page.locator("#sidebar"), page.locator("#session-list")])
                    report["screenshots"].append(shot.relative_to(ROOT).as_posix())
                report["phase"] = "persistence_export_and_fixed_snapshot"
                for endpoint in (f"/api/sessions/{owned_sid}", f"/api/sessions/{owned_sid}/export"):
                    session = read_response(request.get(base + endpoint, timeout=15000, max_retries=0), report)
                    assert session["active_analysis_id"] == analysis_id and len(session["messages"]) == 4
                    assert [item["analysis_id"] for item in session["analysis_history"]] == [analysis_id]
                    for index, reply in enumerate(replies):
                        assert session["messages"][index*2]["content"] == QUESTIONS[index]
                        stored = session["messages"][index*2+1]
                        assert stored["content"] == reply["answer"] and stored["analysis_context"] == reply["analysis_context"] and stored["sources"] == reply["sources"]
                assert fingerprint(read_response(request.get(base + f"/api/options/analyses/{analysis_id}", timeout=15000, max_retries=0), report)) == old_hash
                page.reload(wait_until="domcontentloaded")
                expect(page.locator("#chat-messages .message.assistant")).to_have_count(2)
                expect(card.locator(".analysis-refresh-button")).to_have_count(0)
                assert page.locator("#chat-messages .message-mode").all_text_contents() and all("DeepSeek" in label for label in page.locator("#chat-messages .message-mode").all_text_contents())
                assert not errors and not blocked, "Page error or unapproved API request"
                assert report["counters"] == {"history_fetch_http_requests": 1, "chat_http_requests": 2, "confirmed_deepseek_replies": 2}
                assert sum(item["server_reported_generation_attempts"] for item in report["turns"]) <= 4
                assert re.search(r"未平仓|持仓", replies[1]["answer"]) and re.search(r"缺失|未提供|不提供|未返回|无法|不能|不支持", replies[1]["answer"])
                report.update(status="passed_limited", workflow_status="passed", phase="complete", old_snapshot_unchanged=True,
                              persisted_chat_turns=2, analysis_history_count=1, current_market_inference=False,
                              limits=["Historical hourly TRADES aggregated locally; not native EOD, settlement or synchronized BBO.",
                                      "Full-session coverage unverified; volume changes are incomparable.", "Historical OI, per-contract IV and Greeks are unavailable.",
                                      "Gateway-returned provenance is not independent exchange calibration; no current market sentiment or price prediction established."])
                report["checks"] = ["one_real_fetch_three_server_reported_history_requests", "two_real_ui_deepseek_answers", "local_data_and_expert_ids_and_values_verified",
                                    "source_period_and_historical_scope_visible", "live_refresh_hidden", "same_context_continuous_followup",
                                    "session_and_export_preserve_context_and_retrieval", "fixed_analysis_hash_unchanged", "reload_persistence", "no_pageerror_or_horizontal_overflow", "owned_session_privacy"]
            except Exception as error:
                report.update(status="failed", workflow_status="failed", error_type=type(error).__name__)
                if isinstance(error, AssertionError):
                    report["error_code"] = safe_text(error)[:500]
                if page is not None:
                    try:
                        shot_dir.mkdir(parents=True, exist_ok=True)
                        shot = shot_dir / "historical-failed.png"
                        page.screenshot(path=str(shot), animations="disabled", mask=[page.locator("#sidebar"), page.locator("#session-list")])
                        report["screenshots"].append(shot.relative_to(ROOT).as_posix())
                    except Exception:
                        pass
            finally:
                if owned_sid:
                    try:
                        deleted = request.delete(f"{base}/api/sessions/{owned_sid}", timeout=15000, max_retries=0)
                        report["owned_session_removed"] = deleted.status == 200 and deleted.json().get("deleted") is True
                    except Exception:
                        report["owned_session_removed"] = False
                    if not report["owned_session_removed"]:
                        report.update(status="failed", workflow_status="failed", cleanup_error="owned_session_cleanup_failed")
                report["immutable_analyses_retained"] = int(analysis_id is not None)
                context.close()
                browser.close()
    except Exception as error:
        report.update(status="failed", workflow_status="failed", error_type=type(error).__name__)
    finally:
        report["page_errors"], report["blocked_requests"] = errors, blocked
        report["elapsed_seconds"] = round(perf_counter()-started, 3)
        attempts = [item.get("server_reported_generation_attempts") for item in report["turns"]]
        repairs = [item.get("server_reported_schema_repair_attempts") for item in report["turns"]]
        report["server_reported_total_generation_attempts"] = sum(attempts) if attempts and all(type(x) is int for x in attempts) else None
        report["server_reported_initial_generation_calls"] = len(attempts)
        report["server_reported_repair_calls"] = sum(repairs) if repairs and all(type(x) is int for x in repairs) else None
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "phase": report.get("phase"), "report": report_path.relative_to(ROOT).as_posix(),
                          "counters": report["counters"], "server_reported_total_generation_attempts": report["server_reported_total_generation_attempts"]}, ensure_ascii=False))
    return 0 if report["status"] == "passed_limited" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Allow one real IBKR historical capture and two real UI model turns; at most four generations including bounded schema repairs")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--expiry", default="2026-11-13")
    parser.add_argument("--strike", type=float, default=350.)
    parser.add_argument("--days", type=int, choices=(3, 4, 5), default=5)
    args = parser.parse_args()
    if not args.live:
        parser.print_help()
        print("No --live: zero external requests. Browser, HTTP, broker and models were not started; reports unchanged.")
        return 0
    base = args.base.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path or parsed.query or parsed.fragment or parsed.username:
        parser.error("--base must be a loopback HTTP origin")
    if not re.fullmatch(r"[A-Z][A-Z0-9]{0,11}", args.symbol) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.expiry) or not _finite(args.strike) or not 0 < args.strike <= 1000000:
        parser.error("Use a valid symbol, ISO expiration date and finite positive strike")
    return run(base, {"symbol": args.symbol, "expiry": args.expiry, "strike": args.strike, "days": args.days})


if __name__ == "__main__":
    raise SystemExit(main())
