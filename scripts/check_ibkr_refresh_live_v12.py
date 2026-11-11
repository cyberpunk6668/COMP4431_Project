"""Opt-in REAL IBKR capture -> refresh/compare -> two DeepSeek chat turns.

Default: zero external requests, including health checks. --live requires an
explicit --market-data-type. No fixture provider, network retry, account read
or order API is used. Default execution isolates all state in a temporary DB.
--base instead exercises an existing loopback HTTP server and removes only this
script's session; its immutable saved analyses remain on that server.

Do not run concurrently with another process using the configured IBKR client
ID. A full workflow can pass with limited data, but only complete, timestamped
bid/ask evidence in BOTH captures earns the separate full_quotes designation.
Open interest, last/close prices and model Greeks never count as complete BBO.
Each answer permits at most one local-validation schema repair, so the two chat
turns have at most four provider generations in total. Network failures do not
trigger a retry. HTTP mode reports server attempt counters without treating them
as an independent observation of provider-internal traffic.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import replace
from datetime import UTC, date, datetime
import json
import math
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from urllib.parse import urlsplit
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_options_chat_live_v10 import fingerprint, original_evidence, require_ok, safe_text
from scripts.check_options_refresh_live_v11 import validate_answer, validate_comparison


FOLLOWUP = "结合刚才刷新后的这批真实期权数据，哪些前后变化可以核验，哪些不能确定？为什么这些变化不能直接说明多数人看空或资金流入？"


def numeric(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def stamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(UTC) if result.utcoffset() is not None else None
    except (ValueError, OverflowError):
        return None


def bbo(row):
    bid, ask = numeric(row.get("bid")), numeric(row.get("ask"))
    return bid is not None and ask is not None and bid > 0 and ask >= bid


def _safe_quote(row):
    # Deliberately whitelist ordinary market fields, never arbitrary broker data.
    values = {field: numeric(row.get(field)) for field in (
        "strike", "bid", "ask", "last", "close", "volume", "open_interest",
        "implied_volatility", "delta", "gamma", "vega", "theta",
    )}
    values.update({field: row.get(field) for field in (
        "right", "expiration", "greeks_basis", "market_data_type", "received_at",
        "quote_received_at", "greeks_received_at", "volume_received_at", "open_interest_received_at",
        "close_received_at", "last_trade_at", "price_basis", "quote_basis",
    ) if row.get(field) is not None})
    return values


def audit_capture(record):
    """Verify numeric quote coverage and field basis independently of an LLM."""
    from app.options_analytics import MODE_LABELS, _requested_strikes, _sample_rows

    snapshot, quality = record["snapshot"], record["quality"]
    assert snapshot.get("source") == "ibkr", "Only actual IBKR-sourced captures are accepted"
    received = stamp(snapshot.get("received_at"))
    analyzed = stamp(record.get("analyzed_at"))
    assert received is not None and analyzed is not None, "Missing timezone-aware capture timestamps"
    assert received <= analyzed <= datetime.now(UTC), "Capture/analyze time is invalid or in the future"
    strikes = _requested_strikes(snapshot)
    assert strikes, "No requested strike window returned"
    rows, excluded, ambiguous = _sample_rows(snapshot, strikes)
    requested = 2 * len(strikes)
    assert quality.get("requested_contracts") == requested, "Quality denominator differs from requested contracts"
    numeric_rows = [row for row in rows.values() if bbo(row)]
    actual_coverage = len(numeric_rows) / requested
    assert quality.get("valid_quote_contracts") == len(numeric_rows), "Valid-quote count does not match numeric bid/ask fields"
    assert numeric(quality.get("quote_coverage")) is not None
    assert math.isclose(quality["quote_coverage"], actual_coverage, abs_tol=1e-12), "Quote coverage must not count OI, close or last as a BBO"

    cutoff = numeric(quality.get("freshness_seconds")) or 30
    actual_feed = quality.get("market_data_status", "unknown")

    def qualifying(row):
        quoted = stamp(row.get("quote_received_at"))
        return (bbo(row) and quoted is not None and 0 <= (analyzed - quoted).total_seconds() <= cutoff
                and MODE_LABELS.get(row.get("market_data_type")) == actual_feed)

    timestamped = [row for row in numeric_rows if stamp(row.get("quote_received_at")) is not None]
    qualified = [row for row in numeric_rows if qualifying(row)]
    underlying = snapshot.get("underlying", {})
    price = numeric(underlying.get("price"))
    basis = underlying.get("price_basis")
    midpoint = underlying.get("price_basis") in {"mid", "midpoint"}
    midpoint = bool(midpoint and bbo(underlying) and price is not None
                    and math.isclose(price, (underlying["bid"] + underlying["ask"]) / 2, rel_tol=1e-6))
    reference_verified = midpoint
    if basis in {"last", "close"}:
        reference_value = numeric(underlying.get(basis))
        reference_verified = bool(price is not None and reference_value is not None and reference_value > 0
                                  and math.isclose(price, reference_value, rel_tol=1e-9))
        assert reference_verified, "Underlying reference price does not match its explicit last/close basis"
    underlying_time = stamp(underlying.get("quote_received_at"))
    underlying_qualified = (midpoint and underlying_time is not None
                            and 0 <= (analyzed - underlying_time).total_seconds() <= cutoff
                            and MODE_LABELS.get(underlying.get("market_data_type")) == actual_feed)
    full = bool(underlying_qualified and len(qualified) == requested and actual_feed in MODE_LABELS.values()
                and excluded == 0 and ambiguous == 0)
    limitations = []
    if not midpoint:
        limitations.append("Underlying reference is not a verified positive bid/ask midpoint; last/close is a limited reference.")
    elif not underlying_qualified:
        limitations.append("Underlying midpoint lacks matching confirmed feed or qualifying local quote time.")
    if len(numeric_rows) < requested:
        limitations.append("Some or all option contracts lack valid positive bid/ask quotes; OI/last/close/Greeks do not replace them.")
    if len(qualified) < len(numeric_rows):
        limitations.append("Some numeric BBOs lack confirmed matching feed or qualifying local receipt time.")
    if actual_feed not in MODE_LABELS.values():
        limitations.append("Actual received feed type is mixed, unknown or unavailable.")
    if actual_feed != "live":
        limitations.append("Actual data is not consistently live; recently received delayed/frozen data is not current exchange pricing.")
    if excluded or ambiguous:
        limitations.append("Out-of-window or ambiguous duplicate contract rows were excluded.")
    available = {field: sum(numeric(row.get(field)) is not None for row in rows.values()) for field in (
        "bid", "ask", "last", "close", "volume", "open_interest", "implied_volatility", "delta",
    )}
    example_rows = qualified or numeric_rows or list(rows.values())
    return {
        "source": "ibkr", "symbol": snapshot.get("symbol"), "expiry": snapshot.get("expiration"),
        "received_at": snapshot["received_at"], "analyzed_at": record["analyzed_at"],
        "timestamp_basis": snapshot.get("timestamp_basis", "local_callback_arrival"),
        "requested_market_data_type": snapshot.get("requested_market_data_type"),
        "actual_feed": actual_feed,
        "option_feed_types": sorted({row.get("market_data_type") for row in rows.values() if type(row.get("market_data_type")) is int}),
        "requested_contracts": requested, "numeric_bbo_contracts": len(numeric_rows),
        "timestamped_bbo_contracts": len(timestamped), "qualified_bbo_contracts_at_capture": len(qualified),
        "verified_numeric_quote_coverage": actual_coverage,
        "market_data_level": "full_quotes" if full else "limited",
        "complete_bbo_evidence": full, "underlying_verified_midpoint": midpoint,
        "underlying_reference_basis_verified": bool(reference_verified),
        "underlying_qualified_at_capture": bool(underlying_qualified),
        "underlying_example": {**{key: numeric(underlying.get(key)) for key in ("price", "bid", "ask", "last", "close")},
                               **{key: underlying.get(key) for key in ("price_basis", "received_at", "quote_received_at", "close_received_at", "market_data_type", "last_trade_at")}},
        "field_availability_contracts": available,
        "greeks_bases": sorted({row.get("greeks_basis") for row in rows.values() if isinstance(row.get("greeks_basis"), str)}),
        "safe_option_examples": [_safe_quote(row) for row in example_rows[:2]],
        "transport_diagnostics": snapshot.get("diagnostics"),
        "limitations": limitations,
        "latency_note": "All receipt times, including close_received_at, are local callback times, not exchange timestamps or proof of end-to-end latency. Unknown last_trade_at remains unknown; receiving a prior close does not establish a trade time.",
    }


def destination(base):
    path = ROOT / "reports" / ("ibkr_refresh_http_v12.json" if base else "ibkr_refresh_live_v12.json")
    if path.exists():
        path = path.with_stem(path.stem + "_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def capture_response(response, report):
    try:
        return require_ok(response)
    except AssertionError:
        try:
            detail = response.json().get("detail", {})
            if isinstance(detail, dict) and isinstance(detail.get("diagnostics"), dict):
                report.setdefault("provider_diagnostics", []).append(detail["diagnostics"])
        except (ValueError, AttributeError):
            pass
        raise


def generation_summary(reply, counters):
    attempts, repairs = reply.get("generation_attempts"), reply.get("schema_repair_attempts")
    assert type(attempts) is int and 0 <= attempts <= 2, "Invalid server generation attempt count"
    assert type(repairs) is int and 0 <= repairs <= 1, "Invalid server schema-repair count"
    assert repairs == max(0, attempts - 1), "Schema repair count differs from bounded generation attempts"
    counters["server_reported_generation_attempts"] += attempts
    counters["server_reported_schema_repair_attempts"] += repairs
    return {"server_reported_generation_attempts": attempts, "server_reported_schema_repair_attempts": repairs}


def run_workflow(client, args, report, counters, app=None):
    report["phase"] = "initial_capture"
    counters["capture_http_requests"] += 1
    previous = capture_response(client.post("/api/options/analyze", json={
        "symbol": args.symbol, "expiry": args.expiry, "radius": args.radius,
        "market_data_type": args.market_data_type, "interpret_with_llm": False, "language": args.language,
    }), report)
    old_id = previous["analysis_id"]
    assert UUID(old_id).version == 4
    old_hash = fingerprint(previous)
    report["phase"] = "initial_quote_audit"
    report["captures"] = [audit_capture(previous)]
    session = require_ok(client.post("/api/sessions", json={"title": "IBKR v12 isolated refresh acceptance"}), 201)
    sid = session["id"]
    try:
        require_ok(client.put(f"/api/sessions/{sid}/analysis", json={"analysis_id": old_id}))
        counters["model_turn_http_requests"] += 1
        counters["capture_http_requests"] += 1
        report["phase"] = "refresh_capture_and_first_model"
        refreshed = capture_response(client.post(f"/api/sessions/{sid}/analysis/refresh", json={
            "analysis_id": old_id, "engine": "deepseek", "language": args.language,
        }), report)
        report["turns"].append({"mode": refreshed.get("mode"), "warning": refreshed.get("warning"),
                                "answer_excerpt": safe_text(refreshed.get("answer", ""))[:3500],
                                **generation_summary(refreshed, counters)})
        assert refreshed.get("refreshed") is True and refreshed.get("user_message")
        new_id = refreshed["analysis_context"]["analysis_id"]
        assert new_id != old_id and UUID(new_id).version == 4
        current = require_ok(client.get("/api/options/analyses/" + new_id))
        report["phase"] = "refresh_quote_and_comparison_audit"
        report["captures"].append(audit_capture(current))
        changes = validate_comparison(previous, current)
        report.update(old_analysis_id=old_id, new_analysis_id=new_id, old_fingerprint=old_hash,
                      comparison_status=current["refresh_comparison"]["status"],
                      local_changes=[{"id": key, **{field: entry[field] for field in (
                          "before", "after", "delta", "unit", "delta_unit", "status", "reason", "direction")}}
                                     for key, entry in changes.items()])
        report["phase"] = "first_model_validation"
        report["turns"][-1].update(validate_answer(refreshed, previous, current, changes, require_change=True))
        counters["confirmed_deepseek_replies"] += 1
        followup_message = FOLLOWUP if args.language == "zh" else (
            "Using the options data we just refreshed, which before/after changes are verifiable and which remain uncertain? "
            "Why do these differences not directly show that most people are bearish or that money is flowing in?")
        counters["model_turn_http_requests"] += 1
        report["phase"] = "followup_model"
        followup = require_ok(client.post("/api/chat", json={
            "session_id": sid, "message": followup_message, "language": args.language, "engine": "deepseek",
        }))
        report["turns"].append({"mode": followup.get("mode"), "warning": followup.get("warning"),
                                "answer_excerpt": safe_text(followup.get("answer", ""))[:3500],
                                **generation_summary(followup, counters)})
        report["phase"] = "followup_model_validation"
        report["turns"][-1].update(validate_answer(followup, previous, current, changes, require_change=False))
        counters["confirmed_deepseek_replies"] += 1
        report["phase"] = "persistence_history_and_hash_validation"
        for container in (require_ok(client.get("/api/sessions/" + sid)),
                          require_ok(client.get(f"/api/sessions/{sid}/export"))):
            assert container["active_analysis_id"] == new_id
            assert [item["analysis_id"] for item in container["analysis_history"]] == [new_id, old_id]
            assert [item["is_current"] for item in container["analysis_history"]] == [True, False]
            assert len(container["messages"]) == 4
            assert container["messages"][0]["content"] == refreshed["user_message"]
            assert container["messages"][2]["content"] == followup_message
            for index, reply in enumerate((refreshed, followup)):
                assert container["messages"][2 * index + 1]["analysis_context"] == reply["analysis_context"]
        assert fingerprint(require_ok(client.get("/api/options/analyses/" + old_id))) == old_hash
        assert require_ok(client.get("/api/options/analyses/" + new_id)) == current
        assert counters["capture_http_requests"] == counters["model_turn_http_requests"] == counters["confirmed_deepseek_replies"] == 2
        if app:
            assert counters["gateway_capture_attempts"] == counters["gateway_capture_successes"] == 2
            assert 2 <= counters["real_model_requests"] <= 4
            assert counters["initial_model_requests"] == 2 and counters["schema_repair_requests"] <= 2
            assert counters["server_reported_generation_attempts"] == counters["real_model_requests"]
            assert counters["server_reported_schema_repair_attempts"] == counters["schema_repair_requests"]
            initial_calls = [call for call in report["model_calls"] if call["phase"] == "initial"]
            assert initial_calls[0]["prior_messages"] == 0 and initial_calls[1]["prior_messages"] == 2
        full = all(item["complete_bbo_evidence"] for item in report["captures"])
        report.update(phase="complete", workflow_status="passed", status="passed" if full else "passed_limited",
                      market_data_level="full_quotes" if full else "limited", full_quote_validation=full,
                      old_snapshot_unchanged=True, new_snapshot_unchanged_during_followup=True,
                      analysis_history_count=2, persisted_chat_turns=2,
                      checks=["two_actual_ibkr_captures", "two_real_deepseek_replies", "no_fixture_data",
                              "independently_verified_numeric_quote_coverage_and_basis", "explicit_feed_and_resolved_expiry_preserved",
                              "local_before_after_values_and_delta_verified", "actual_unchanged_values_are_allowed",
                              "new_context_used_by_continuous_followup", "all_citations_resolve_to_saved_local_evidence",
                              "two_versions_retained_and_old_hash_unchanged", "session_and_export_preserve_two_chat_turns",
                              "no_automatic_network_retry", "schema_repair_bounded_once_per_answer", "full_quotes_distinguished_from_partial_fields"])
    finally:
        removed = client.delete("/api/sessions/" + sid)
        report["owned_session_removed"] = removed.status_code == 200 and removed.json().get("deleted") is True
        if not report["owned_session_removed"]:
            report.update(status="failed", cleanup_error="owned_session_cleanup_failed")
        if not app:
            report["http_owned_immutable_analyses_retained"] = 2 if len(report.get("captures", [])) == 2 else 1


def run(args):
    path = destination(args.base)
    started = perf_counter()
    counters = {"capture_http_requests": 0, "model_turn_http_requests": 0, "confirmed_deepseek_replies": 0,
                "gateway_capture_attempts": 0 if not args.base else None,
                "gateway_capture_successes": 0 if not args.base else None,
                "real_model_requests": 0 if not args.base else None,
                "initial_model_requests": 0 if not args.base else None,
                "schema_repair_requests": 0 if not args.base else None,
                "server_reported_generation_attempts": 0, "server_reported_schema_repair_attempts": 0}
    report = {"checked_at": datetime.now(UTC).isoformat(), "status": "running", "workflow_status": "running",
              "scope": "Actual IBKR initial capture and explicit refresh, local comparison, real DeepSeek refresh explanation and continuous follow-up. No fixtures or network retries; at most one schema repair per answer.",
              "privacy": "Only whitelisted ordinary market values, aggregate evidence and safe answer excerpts are saved; no credentials, account fields, session IDs, raw protocol data or prompts.",
              "transport": "loopback HTTP service" if args.base else "FastAPI TestClient with isolated temporary database",
              "state_isolation": "owned session only; immutable test analyses retained on HTTP server" if args.base else "temporary database removed at exit",
              "request": {"symbol": args.symbol, "expiry": args.expiry, "radius": args.radius,
                          "market_data_type": args.market_data_type, "language": args.language},
              "automatic_network_retries": 0, "schema_repair_limit_per_answer": 1,
              "generation_attempt_limit_per_answer": 2, "provider_request_limit_total": 4,
              "turns": [], "model_calls": [], "captures": [], "counters": counters}
    try:
        with ExitStack() as stack:
            if args.base:
                import httpx
                client = stack.enter_context(httpx.Client(base_url=args.base, timeout=300, follow_redirects=False, trust_env=False))
                health = require_ok(client.get("/api/health"))
                assert health.get("mode") == "deepseek", "HTTP service is not configured for DeepSeek"
                report.update(app_version=health.get("version"), model=health.get("model"), base=args.base,
                              model_count_note="HTTP mode checks two requested model turns and two DeepSeek replies; provider-internal counters cannot be inspected.")
                run_workflow(client, args, report, counters)
            else:
                from fastapi.testclient import TestClient
                from app.config import Settings
                from app.main import create_app
                from app.options_ibkr import IBKRConfig, IBKROptionsProvider
                from app.options_chat import _read_response, _validate_changes
                temporary = stack.enter_context(TemporaryDirectory(prefix="finpilot-ibkr-v12-"))
                settings = Settings(db_path=Path(temporary) / "isolated.sqlite3")
                assert settings.online, "Configured online DeepSeek credentials are required"
                config = IBKRConfig.from_env()
                assert config.enabled, "IBKR_ENABLED must be explicitly enabled in server configuration"
                if args.client_id is not None:
                    config = replace(config, client_id=args.client_id)
                provider = IBKROptionsProvider(config)
                original_snapshot = provider.snapshot

                async def counted_snapshot(symbol, expiry, count, mode):
                    assert counters["gateway_capture_attempts"] < 2, "Additional IBKR capture blocked"
                    assert symbol == args.symbol and mode == args.market_data_type
                    counters["gateway_capture_attempts"] += 1
                    result = await original_snapshot(symbol, expiry, count, mode)
                    assert result.get("source") == "ibkr", "Non-IBKR data rejected"
                    counters["gateway_capture_successes"] += 1
                    return result

                provider.snapshot = counted_snapshot
                app = create_app(settings, options_provider=provider)
                original_complete = app.state.options_chat.cloud.complete
                diagnostics = []
                diagnostic_path = ROOT / "tmp" / ("ibkr-refresh-v12-diagnostic-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json")

                async def counted_complete(messages, **kwargs):
                    assert counters["gateway_capture_successes"] == 2, "Model request before the explicit refresh is blocked"
                    assert counters["real_model_requests"] < 4, "Additional model call blocked by the total generation budget"
                    counters["real_model_requests"] += 1
                    payload = json.loads(messages[-1]["content"])
                    repair = isinstance(payload.get("schema_repair"), dict)
                    if repair:
                        assert report["model_calls"] and report["model_calls"][-1]["phase"] == "initial", "Only one schema repair is allowed per answer"
                        assert counters["initial_model_requests"] == counters["model_turn_http_requests"], "Schema repair belongs to another answer"
                        counters["schema_repair_requests"] += 1
                    else:
                        assert counters["initial_model_requests"] < 2, "Additional initial generation blocked"
                        counters["initial_model_requests"] += 1
                        assert counters["initial_model_requests"] == counters["model_turn_http_requests"]
                    current = app.state.store.get_analysis(payload["saved_snapshot"]["analysis_id"])
                    previous = app.state.store.get_analysis(current["previous_analysis_id"])
                    changes = validate_comparison(previous, current)
                    _, ordinary = original_evidence(current)
                    sent = {item["id"]: item for item in payload["evidence"]}
                    assert set(sent) == set(changes) | set(ordinary)
                    for identifier, entry in sent.items():
                        if identifier in changes:
                            assert entry["value"] == changes[identifier]["after"]
                            assert entry["delta"] == changes[identifier]["delta"]
                        else:
                            assert entry["value"] == ordinary[identifier]["value"]
                    report["model_calls"].append({"answer_turn": counters["model_turn_http_requests"],
                                                   "phase": "schema_repair" if repair else "initial",
                                                   "prior_messages": len(messages) - 2 - (2 if repair else 0),
                                                   "evidence_count": len(sent), "change_evidence_count": len(changes)})
                    content = await original_complete(messages, **kwargs)
                    diagnostic = {"generation": counters["real_model_requests"], "answer_turn": counters["model_turn_http_requests"],
                                  "phase": "schema_repair" if repair else "initial", "provider_response": safe_text(content)[:15000]}
                    try:
                        parts = _read_response(content, set(sent))
                        _validate_changes(parts, sent)
                        diagnostic["accepted_by_local_parser"] = True
                    except (ValueError, TypeError) as error:
                        diagnostic.update(accepted_by_local_parser=False, validation_error=safe_text(error)[:500])
                    diagnostics.append(diagnostic)
                    diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
                    diagnostic_path.write_text(json.dumps({"scope": "Safe model text only, no prompts/headers/credentials/accounts; exclude from submission.", "turns": diagnostics}, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
                    return content

                app.state.options_chat.cloud.complete = counted_complete
                report.update(app_version=app.version, model=settings.model,
                              model_count_note="Exact in-process counters: two broker captures, two initial answer generations, at most one schema repair per answer and at most four provider generations total; no network retries.")
                client = stack.enter_context(TestClient(app))
                run_workflow(client, args, report, counters, app)
    except Exception as error:
        report.update(status="failed", workflow_status="failed", error_type=type(error).__name__)
        if isinstance(error, AssertionError):
            message = safe_text(error)
            report["error_code"] = re.sub(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", "[test-id]", message, flags=re.I)[:400]
    report["elapsed_seconds"] = round(perf_counter() - started, 3)
    report["limits"] = list(dict.fromkeys(limit for capture in report["captures"] for limit in capture["limitations"]))
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "workflow_status": report["workflow_status"],
                      "market_data_level": report.get("market_data_level"), "report": path.relative_to(ROOT).as_posix(),
                      "counters": counters}, ensure_ascii=True, indent=2))
    return int(report["status"] not in {"passed", "passed_limited"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Allow two real IBKR captures and two chat turns, at most four DeepSeek generations including bounded schema repairs")
    parser.add_argument("--market-data-type", type=int, choices=(1, 2, 3, 4), help="Required with --live; requested feed, never a claim about actual received feed")
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--expiry", help="Optional broker-listed expiration (YYYY-MM-DD); omitted uses nearest available")
    parser.add_argument("--radius", type=int, choices=range(1, 7), default=1)
    parser.add_argument("--language", choices=("zh", "en"), default="zh")
    parser.add_argument("--base", help="Optional existing loopback HTTP service, e.g. http://127.0.0.1:8000")
    parser.add_argument("--client-id", type=int, help="Optional in-process IBKR client ID; coordinate with other gateway users before running")
    args = parser.parse_args()
    if not args.live:
        parser.print_help()
        print("No --live: zero external requests; no gateway, health or model request was made.")
        return 0
    if args.market_data_type is None:
        parser.error("--live requires an explicit --market-data-type")
    args.symbol = args.symbol.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]*(?:[ .-][A-Z0-9]+)?", args.symbol) or len(args.symbol) > 12:
        parser.error("Invalid stock/ETF symbol")
    if args.expiry:
        try:
            assert re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", args.expiry)
            date.fromisoformat(args.expiry)
        except (AssertionError, ValueError):
            parser.error("--expiry must be a valid YYYY-MM-DD date")
    if args.client_id is not None and not 1 <= args.client_id <= 2**31 - 1:
        parser.error("Invalid client ID")
    if args.base:
        args.base = args.base.rstrip("/")
        parsed = urlsplit(args.base)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path or parsed.query:
            parser.error("--base must be a loopback HTTP origin")
        if args.client_id is not None:
            parser.error("--client-id is configured by the server in --base mode")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
