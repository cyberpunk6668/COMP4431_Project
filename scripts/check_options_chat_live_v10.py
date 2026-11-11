"""Explicitly opt in to real-model acceptance of saved option-analysis chat.

No arguments perform no gateway/model requests. --cloud-fixture uses synthetic
market snapshots, real local analytics/HTTP routes, and at most two DeepSeek
requests without retries. --gateway is a separate opt-in to one read-only AAPL
delayed snapshot and one model question. All database state is temporary.
Run from the repository root with ``python -m scripts.check_options_chat_live_v10``.
"""
import argparse
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
QUESTIONS = (
    "请对比这两组期权数据，用白话解释主要差异、对应依据，以及这些数据不能说明什么。",
    "为什么看跌合约更活跃，不能直接说明多数人看空？请结合刚才这批数据说明依据和局限。",
)


def synthetic_snapshot(symbol, expiration=None):
    """Two distinct samples, each with paired volume, inventory and quote data."""
    stamp = datetime.now(UTC).isoformat()
    expiry = expiration or (datetime.now(UTC).date() + timedelta(days=21)).isoformat()
    mode = 3 if symbol == "AAA" else 4
    quotes = []
    for index, strike in enumerate((90, 95, 100, 105, 110)):
        for right in ("C", "P"):
            if symbol == "AAA":
                volume = (5, 10, 70, 10, 5)[index] if right == "C" else (2, 5, 12, 3, 3)[index]
            else:
                volume = 10 if right == "C" else 25
            delta = ((0.8, 0.65, 0.5, 0.25, 0.1) if right == "C" else (-0.1, -0.25, -0.5, -0.65, -0.8))[index]
            quotes.append({
                "strike": strike, "right": right, "expiration": expiry,
                "bid": 4.8 if symbol == "AAA" else 4.7, "ask": 5.2 if symbol == "AAA" else 5.3,
                "volume": volume, "open_interest": 100 if right == "C" else 200,
                "delta": delta, "implied_volatility": 0.22 if right == "C" else 0.30,
                "greeks_basis": "model", "market_data_type": mode,
                **{key: stamp for key in ("received_at", "quote_received_at", "greeks_received_at", "volume_received_at", "open_interest_received_at")},
            })
    return {
        "source": "fixture", "symbol": symbol, "expiration": expiry, "currency": "USD",
        "trading_class": symbol, "multiplier": 100, "exchange": "SMART",
        "requested_market_data_type": mode, "requested_strikes": [90, 95, 100, 105, 110],
        "started_at": stamp, "received_at": stamp, "quotes": quotes,
        "underlying": {"price": 100, "bid": 99.9, "ask": 100.1, "price_basis": "midpoint",
                       "market_data_type": mode, "received_at": stamp},
    }


class FixtureGateway:
    """Does not import, instantiate or communicate with an IBKR client."""
    def __init__(self):
        self.calls = []

    async def snapshot(self, symbol, expiry, strike_count, market_data_type):
        assert symbol in {"AAA", "BBB"}
        self.calls.append({"symbol": symbol, "requested_mode": market_data_type})
        return deepcopy(synthetic_snapshot(symbol, expiry))

    async def status(self):
        return {"provider": "fixture", "status": "synthetic", "tcp_reachable": False}


def require_ok(response, expected=200):
    # Never print a response body, provider payload or credential in diagnostics.
    if response.status_code != expected:
        code = None
        try:
            detail = response.json().get("detail")
            if isinstance(detail, dict) and re.fullmatch(r"[a-z0-9_]{1,80}", str(detail.get("code", ""))):
                code = detail["code"]
        except (ValueError, AttributeError):
            pass
        raise AssertionError(f"Unexpected HTTP status {response.status_code} for {response.request.url.path}; code={code}")
    return response.json()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()


def safe_text(value):
    value = re.sub(r"\bsk-[A-Za-z0-9_-]{16,}", "[credential-redacted]", str(value))
    return re.sub(r"\b(?:DU|U|F|I)[0-9]{5,12}\b", "[account-redacted]", value)


def original_evidence(record):
    """Resolve the same canonical IDs from the untouched local analysis result."""
    from app.options_chat import QUALITY_METRICS, SAFE_METRICS

    reports = record.get("reports") or [record]
    evidence = {}
    for index, item in enumerate(reports):
        for entry in item["collective"]["evidence"]:
            if entry["id"] in SAFE_METRICS:
                evidence[f"g{index}.{entry['id']}"] = {"value": entry["value"], "unit": entry.get("unit", ""), "scope": f"g{index}"}
        for key, (_, _, unit) in QUALITY_METRICS.items():
            if key in item["quality"]:
                evidence[f"g{index}.quality_{key}"] = {"value": item["quality"][key], "unit": unit, "scope": f"g{index}"}
    for entry in record.get("comparison", {}).get("evidence", []):
        if re.fullmatch(r"report_[1-4]_(?:quote_coverage|median_relative_spread_pct|put_volume_share|atm_iv)", entry["id"]):
            index = int(entry["id"].split("_")[1]) - 1
            evidence["comparison." + entry["id"]] = {"value": entry["value"], "unit": entry.get("unit", ""), "scope": "comparison", "scope_ids": [f"g{index}"]}
    return reports, evidence


def run(gateway_mode=False):
    # Imports and Settings initialization happen only after explicit CLI opt-in.
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app

    destination = ROOT / "reports" / ("options_chat_gateway_v10.json" if gateway_mode else "options_chat_cloud_v10.json")
    report = {
        "checked_at": datetime.now(UTC).isoformat(), "status": "running",
        "scope": ("Real local IB Gateway AAPL snapshot requested as delayed, real DeepSeek, temporary isolated database. Not a guarantee of real-time quotes or investment correctness."
                  if gateway_mode else "Synthetic market data, real local analytics and TestClient API routes, real DeepSeek. No IBKR connection. Not live-market validation."),
        "privacy": "No API key, account fields, session identifier, model prompts, raw provider JSON or raw contract quotes are saved in this report. Controlled server-answer excerpts and aggregate evidence are retained for review. Separate safe provider-response diagnostics are confined to tmp/ and excluded from submission.",
        "transport": "In-process FastAPI TestClient; actual external DeepSeek HTTPS request(s).",
        "automatic_retries": 0, "turns": [], "checks": [],
    }
    cloud_calls = []
    evidence, analysis_id = {}, None
    diagnostics = []
    diagnostic_path = ROOT / "tmp" / ("options-chat-v10-diagnostic-gateway.json" if gateway_mode else "options-chat-v10-diagnostic-cloud-fixture.json")
    archived_failure = ROOT / "tmp/options_chat_cloud_v10_failed_initial.json"
    if not gateway_mode and archived_failure.is_file():
        report["prior_failed_fixture_requests"] = json.loads(archived_failure.read_text(encoding="utf-8"))["real_model_requests"]
    try:
        with TemporaryDirectory(prefix="finpilot-options-chat-v10-") as temporary:
            settings = Settings(db_path=Path(temporary) / "isolated.sqlite3")
            assert settings.online, "Configured DeepSeek credentials and online mode are required"
            report["model"] = settings.model
            limit = 1 if gateway_mode else 2
            gateway = None
            if gateway_mode:
                from app.options_ibkr import IBKROptionsProvider
                gateway = IBKROptionsProvider()
            else:
                gateway = FixtureGateway()
            app = create_app(settings, options_provider=gateway)
            complete = app.state.options.llm.complete

            async def counted_complete(messages, **kwargs):
                assert len(cloud_calls) < limit, "Additional real-model call blocked; automatic retries are forbidden"
                assert analysis_id and evidence, "Unexpected model request before the saved-analysis chat stage"
                payload = json.loads(messages[-1]["content"])
                assert set(payload) == {"question", "language", "saved_snapshot", "evidence", "plain_language_context", "term_relations"}
                assert payload["saved_snapshot"]["analysis_id"] == analysis_id
                assert {item["id"] for item in payload["evidence"]} == set(evidence)
                for item in payload["evidence"]:
                    assert item["value"] == evidence[item["id"]]["value"], "Outgoing model evidence differs from saved local aggregates"
                cloud_calls.append({"json_output": bool(kwargs.get("json_output")),
                                    "sent_evidence_count": len(payload["evidence"]),
                                    "prior_chat_messages": len(messages) - 2})
                content = await complete(messages, **kwargs)
                from app.options_chat import _read_response
                diagnostic = {"turn": len(cloud_calls), "market_source": "real IBKR" if gateway_mode else "synthetic fixture",
                              "provider_response": safe_text(content)[:15000]}
                try:
                    _read_response(content, set(evidence))
                    diagnostic["accepted_by_local_parser"] = True
                except (ValueError, TypeError) as error:
                    diagnostic.update(accepted_by_local_parser=False, validation_error=safe_text(error)[:500],
                                      error_type=type(error).__name__)
                diagnostics.append(diagnostic)
                diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
                diagnostic_path.write_text(json.dumps({
                    "scope": "Safe provider response only; no prompts, headers, credentials, account fields or contract quotes. Not for submission.",
                    "turns": diagnostics,
                }, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
                return content

            app.state.options.llm.complete = counted_complete
            with TestClient(app) as client:
                # Both API entry points persist results. Interpretation is left
                # off: real-model budget is reserved exclusively for chat turns.
                single = require_ok(client.post("/api/options/analyze", json={
                    "symbol": "AAPL" if gateway_mode else "AAA", "radius": 1 if gateway_mode else 2,
                    "market_data_type": 3, "interpret_with_llm": False,
                }))
                assert UUID(single["analysis_id"]).version == 4
                assert require_ok(client.get("/api/options/analyses/" + single["analysis_id"])) == single
                record = single
                if not gateway_mode:
                    record = require_ok(client.post("/api/options/batch", json={
                        "items": [{"symbol": "AAA"}, {"symbol": "BBB"}], "radius": 2,
                        "market_data_type": 3, "interpret_with_llm": False,
                    }))
                    assert len(record["reports"]) == 2 and not record["failures"]
                    assert record["analysis_id"] != single["analysis_id"]
                analysis_id = record["analysis_id"]
                assert UUID(analysis_id).version == 4 and not cloud_calls
                stored = require_ok(client.get("/api/options/analyses/" + analysis_id))
                assert stored == record
                reports, evidence = original_evidence(record)
                assert evidence and len(reports) == (1 if gateway_mode else 2)
                assert all(any(key.startswith(f"g{index}.") and entry["value"] is not None
                               for key, entry in evidence.items()) for index in range(len(reports)))
                from app.options_chat import _read_response
                try:
                    _read_response('{"response":[{"kind":"observation","text":"这个观察没有保存的证据。","evidence_ids":["unknown.metric"]}]}', set(evidence))
                except ValueError:
                    report["unknown_evidence_rejected_locally"] = True
                else:
                    raise AssertionError("Unknown evidence reference was accepted")
                original_digest = fingerprint(record)
                session = require_ok(client.post("/api/sessions", json={"title": "隔离期权追问验收"}), 201)
                sid = session["id"]
                unknown = client.post("/api/chat", json={"session_id": sid, "message": "解释这批数据", "analysis_id": str(uuid4())})
                assert unknown.status_code == 404 and not cloud_calls
                assert require_ok(client.get("/api/sessions/" + sid))["messages"] == []
                binding = require_ok(client.put(f"/api/sessions/{sid}/analysis", json={"analysis_id": analysis_id}))
                assert binding["active_analysis_id"] == analysis_id
                report["analysis_id"] = analysis_id
                report["analysis_fingerprint"] = original_digest
                report["market_scopes"] = [{
                    "symbol": item["snapshot"]["symbol"], "expiration": item["snapshot"]["expiration"],
                    "source": item["snapshot"]["source"], "received_at": item["snapshot"]["received_at"],
                    "market_data_status": item["quality"]["market_data_status"],
                    "local_evidence_count": len(item["collective"]["evidence"]),
                } for item in reports]
                questions = ("请用白话解释这批期权数据的依据和局限；为什么看跌合约更活跃不能直接说明多数人看空？",) if gateway_mode else QUESTIONS
                replies = []
                for index, question in enumerate(questions):
                    payload = {"session_id": sid, "message": question, "language": "zh", "engine": "deepseek"}
                    if index == 0:
                        payload["analysis_id"] = analysis_id
                    response = require_ok(client.post("/api/chat", json=payload))
                    assert len(cloud_calls) == index + 1, "Expected exactly one real-model request per chat turn"
                    summary = {"mode": response.get("mode"), "warning": response.get("warning"),
                               "answer_excerpt": safe_text(response.get("answer", ""))[:3000]}
                    report["turns"].append(summary)
                    summary.update(validate_reply(response, record, evidence, require_citations=not gateway_mode))
                    if index == 0 and not gateway_mode:
                        used = {scope for item in response["analysis_context"]["evidence"]
                                for scope in item.get("scope_ids", [item["scope"]])}
                        assert {"g0", "g1"} <= used, "The comparison answer must cite saved evidence from both samples"
                    summary["model_request"] = cloud_calls[-1]
                    replies.append(response)
                saved_session = require_ok(client.get("/api/sessions/" + sid))
                exported = require_ok(client.get(f"/api/sessions/{sid}/export"))
                assert saved_session["active_analysis_id"] == exported["active_analysis_id"] == analysis_id
                assert len(saved_session["messages"]) == len(exported["messages"]) == 2 * len(questions)
                for index, response in enumerate(replies):
                    expected_context = response["analysis_context"]
                    for container in (saved_session, exported):
                        assert container["messages"][2 * index + 1]["analysis_context"] == expected_context
                assert require_ok(client.get("/api/options/analyses/" + analysis_id)) == record
                assert fingerprint(app.state.store.get_analysis(analysis_id)) == original_digest
                assert len(cloud_calls) == limit
                if not gateway_mode:
                    assert cloud_calls[0]["prior_chat_messages"] == 0
                    assert cloud_calls[1]["prior_chat_messages"] == 2
                if not gateway_mode:
                    assert len(gateway.calls) == 3
                    report["synthetic_snapshot_requests"] = len(gateway.calls)
                    report["ibkr_requests"] = 0
                report["real_model_requests"] = len(cloud_calls)
                report["checks"] = [
                    "server_generated_persistent_uuid", "single_and_batch_saved" if not gateway_mode else "one_aapl_snapshot_saved",
                    "unknown_analysis_rejected_before_cloud", "local_evidence_values_match_original",
                    "unknown_evidence_rejected_locally", "all_citations_resolve", "scope_time_feed_retained", "same_session_binding_persists",
                    "session_and_export_preserve_context", "original_saved_analysis_unchanged",
                    "outgoing_model_evidence_matches_saved_aggregates", "one_model_request_per_turn_no_retry",
                ]
                report["interpretation_limits"] = "Automated acceptance verifies source grounding, model mode, evidence references and persistence. It does not establish universal correctness of financial reasoning or present market conditions."
                report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        # Error bodies can contain private provider content; only save the type.
        report["error_type"] = type(error).__name__
        if isinstance(error, AssertionError):
            report["error_code"] = safe_text(error)[:250]
        report["real_model_requests"] = len(cloud_calls)
        raise
    finally:
        if diagnostics:
            report["provider_validation"] = [{key: item[key] for key in ("turn", "accepted_by_local_parser", "validation_error") if key in item}
                                             for item in diagnostics]
        if not gateway_mode:
            report["cumulative_fixture_model_requests"] = report.get("prior_failed_fixture_requests", 0) + len(cloud_calls)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "report": str(destination), "real_model_requests": len(cloud_calls)}, ensure_ascii=False))


def validate_reply(response, record, evidence, *, require_citations=True):
    """Check references against original aggregates, never recompute model values."""
    assert response["mode"] == "deepseek", "Real DeepSeek reply was downgraded: " + str(response.get("warning", "unknown"))
    assert not response.get("warning"), "Successful cloud acceptance must not contain a fallback warning"
    assert isinstance(response["answer"], str) and response["answer"].strip()
    context = response["analysis_context"]
    assert context["analysis_id"] == record["analysis_id"]
    assert context["realtime_guaranteed"] is False
    reports = record.get("reports") or [record]
    assert len(context["scopes"]) == len(reports)
    for index, (scope, original) in enumerate(zip(context["scopes"], reports)):
        snapshot = original["snapshot"]
        assert scope["id"] == f"g{index}"
        assert scope["symbol"] == snapshot["symbol"]
        assert scope["expiry"] == snapshot["expiration"]
        assert datetime.fromisoformat(scope["received_at"]) == datetime.fromisoformat(snapshot["received_at"])
        assert scope["market_data_status"] == original["quality"]["market_data_status"]
        assert scope["time_status"] == "known" and scope["snapshot_age_seconds"] >= 0
        assert scope["stale"] == (scope["snapshot_age_seconds"] > context["freshness_threshold_seconds"])
        assert scope["assessment_status"] == original["collective"]["assessment"]["status"]
        assert scope["quote_coverage"] == original["quality"]["quote_coverage"]
    assert datetime.fromisoformat(context["captured_at"]) == min(datetime.fromisoformat(item["snapshot"]["received_at"]) for item in reports)
    completed = record.get("completed_at", record.get("analyzed_at"))
    assert datetime.fromisoformat(context["completed_at"]) == datetime.fromisoformat(completed)
    identifiers = context["evidence_ids"]
    assert len(identifiers) == len(set(identifiers)), "Evidence references must not be duplicated"
    assert identifiers or not require_citations, "The sample-specific answer must cite saved evidence"
    assert set(identifiers) <= set(evidence), "Unknown evidence reference appeared in the reply"
    cards = context["evidence"]
    assert [item["id"] for item in cards] == identifiers
    assert list(dict.fromkeys(re.findall(r"\[([A-Za-z0-9_.-]+)\]", response["answer"]))) == identifiers
    checks = []
    for item in cards:
        original = evidence[item["id"]]
        assert item["value"] == original["value"] and item["unit"] == original["unit"]
        assert item["scope"] == original["scope"]
        scope_id = original.get("scope_ids", [original["scope"]])[0]
        scope = context["scopes"][int(scope_id[1:])]
        assert item["symbol"] == scope["symbol"] and item["expiry"] == scope["expiry"]
        assert item["received_at"] == scope["received_at"] and item["market_data_status"] == scope["market_data_status"]
        assert item["status"] == ("available" if item["value"] is not None else "unavailable")
        checks.append({"id": item["id"], "value": item["value"], "unit": item["unit"], "matches_original": True})
    return {
        "mode": response["mode"], "analysis_binding_matches": True,
        "answer_characters": len(response["answer"]), "cited_evidence": checks,
        "scopes_and_original_times_match": True, "realtime_guaranteed": False,
        "snapshot_stale": context["stale"],
        "has_snapshot_notice": "未重新获取行情" in response["answer"],
        "contains_direction_or_purpose_limit_terms": bool(re.search(r"不能|无法|不代表|买卖双方|买方|卖方|对冲|保护|组合|开平仓", response["answer"])),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--cloud-fixture", action="store_true", help="Explicitly allow two real DeepSeek requests with synthetic market data; no IBKR")
    mode.add_argument("--gateway", action="store_true", help="Explicitly allow one real AAPL delayed snapshot and one real DeepSeek request")
    args = parser.parse_args()
    if not (args.cloud_fixture or args.gateway):
        parser.print_help()
        print("No opt-in mode selected: no gateway or model request was made.")
        return 0
    run(gateway_mode=args.gateway)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
