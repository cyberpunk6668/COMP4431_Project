"""Opt-in acceptance of explicit refresh, immutable history and real-model chat.

Default: no external requests. --cloud-fixture: synthetic market captures,
real local analytics/API persistence and at most two real DeepSeek calls.
--gateway: two actual AAPL captures requested as delayed and one real model
call. No automatic retries. Only safe summaries go into reports; provider-text
diagnostics without prompts, headers or accounts stay in ignored tmp/.
"""
import argparse
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import math
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from uuid import UUID
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_options_chat_live_v10 import fingerprint, original_evidence, require_ok, safe_text


def synthetic_snapshot(symbol, expiry, stamp, newer):
    """Stable paired contracts; put volume share changes from .60 to .70."""
    stamp = stamp.isoformat()
    quotes = []
    for index, strike in enumerate((95, 100, 105)):
        for right in ("C", "P"):
            call = right == "C"
            quotes.append({
                "strike": strike, "right": right, "expiration": expiry,
                "bid": 4.85 if newer else 4.8, "ask": 5.15 if newer else 5.2,
                "volume": (45 if call else 105) if newer else (40 if call else 60),
                "open_interest": (90 if call else 135) if newer else (80 if call else 120),
                "delta": ((.65, .5, .25) if call else (-.25, -.5, -.65))[index],
                "implied_volatility": (.24 if call else .28) if newer else (.22 if call else .26),
                "greeks_basis": "model", "market_data_type": 3,
                **{key: stamp for key in ("received_at", "quote_received_at", "greeks_received_at", "volume_received_at", "open_interest_received_at")},
            })
    return {"source": "fixture", "symbol": symbol, "expiration": expiry, "currency": "USD",
            "trading_class": symbol, "multiplier": 100, "exchange": "SMART",
            "requested_market_data_type": 3, "requested_strikes": [95, 100, 105],
            "started_at": stamp, "received_at": stamp, "quotes": quotes,
            "underlying": {"price": 100, "bid": 99.9, "ask": 100.1, "price_basis": "midpoint",
                           "market_data_type": 3, "received_at": stamp}}


class FixtureGateway:
    def __init__(self):
        newest = datetime.now(UTC) - timedelta(seconds=1)
        oldest = newest - timedelta(seconds=5)
        ny = ZoneInfo("America/New_York")
        if oldest.astimezone(ny).date() != newest.astimezone(ny).date():
            newest, oldest = oldest, oldest - timedelta(seconds=5)
        self.times, self.calls = (oldest, newest), []

    async def snapshot(self, symbol, expiry, strike_count, market_data_type):
        assert len(self.calls) < 2, "Only initial collection and one refresh are allowed"
        assert symbol == "DEMO" and market_data_type == 3 and strike_count == 3
        if self.calls:
            assert expiry == "2030-01-18", "Refresh must reuse the resolved expiry"
        self.calls.append({"symbol": symbol, "expiry": expiry, "strike_count": strike_count, "market_data_type": market_data_type})
        return synthetic_snapshot(symbol, expiry or "2030-01-18", self.times[len(self.calls) - 1], len(self.calls) == 2)

    async def status(self):
        return {"provider": "fixture", "status": "synthetic", "tcp_reachable": False}


def local_values(record):
    collective = record["collective"]
    shares = {item["id"]: item["value"] for item in collective["evidence"]}
    return {
        "quote_coverage": record["quality"]["quote_coverage"],
        "volume_put_share": shares["volume_put_share"], "oi_put_share": shares["oi_put_share"],
        "volume_total": collective["distributions"]["volume"]["total"],
        "oi_total": collective["distributions"]["open_interest"]["total"],
        "median_spread": collective["liquidity"]["median_relative_spread_pct"],
        "atm_iv": collective["volatility"]["atm_iv"],
    }


def validate_comparison(previous, current, synthetic=False):
    comparison = current["refresh_comparison"]
    assert current["previous_analysis_id"] == comparison["previous_analysis_id"] == previous["analysis_id"]
    old, new = previous["snapshot"], current["snapshot"]
    before_time, after_time = datetime.fromisoformat(old["received_at"]), datetime.fromisoformat(new["received_at"])
    assert before_time < after_time <= datetime.now(UTC), "Receipt times must strictly increase and remain in the past"
    assert comparison["previous_captured_at"] == old["received_at"]
    assert comparison["current_captured_at"] == new["received_at"]
    assert len(comparison["scopes"]) == 1
    scope = comparison["scopes"][0]
    assert scope["symbol"] == old["symbol"] == new["symbol"]
    assert scope["expiry"] == old["expiration"] == new["expiration"]
    assert scope["previous_received_at"] == old["received_at"] and scope["received_at"] == new["received_at"]
    assert scope["before_feed"] == previous["quality"]["market_data_status"]
    assert scope["after_feed"] == current["quality"]["market_data_status"]
    left, right = local_values(previous), local_values(current)
    evidence = {}
    for metric in scope["metrics"]:
        key = metric["id"]
        assert metric["before"] == left[key] and metric["after"] == right[key], "Comparison values differ from original local aggregates"
        if metric["status"] == "comparable":
            assert metric["before"] is not None and metric["after"] is not None
            scale = 100 if metric["unit"] == "fraction" else 1
            assert metric["delta"] is not None and math.isclose(metric["delta"], (right[key] - left[key]) * scale, abs_tol=1e-9)
            assert metric["reason"] is None
        else:
            assert metric["delta"] is None and metric["reason"], "Incomparable evidence must never invent a delta"
        direction = ("unavailable" if metric["delta"] is None else "increased" if metric["delta"] > 0
                     else "decreased" if metric["delta"] < 0 else "unchanged")
        assert metric["direction"] == direction, "Direction must be derived locally from the verified delta"
        evidence[f"change.{scope['id']}.{key}"] = {**deepcopy(metric),
            "symbol": scope["symbol"], "expiry": scope["expiry"],
            "previous_received_at": scope["previous_received_at"], "received_at": scope["received_at"],
            "before_feed": scope["before_feed"], "after_feed": scope["after_feed"]}
    if synthetic:
        assert before_time.astimezone(ZoneInfo("America/New_York")).date() == after_time.astimezone(ZoneInfo("America/New_York")).date()
        assert old["requested_strikes"] == new["requested_strikes"] == [95, 100, 105]
        assert all(old[key] == new[key] for key in ("symbol", "expiration", "trading_class", "currency", "multiplier"))
        assert scope["before_feed"] == scope["after_feed"] == "delayed"
        share = evidence[f"change.{scope['id']}.volume_put_share"]
        assert share["status"] == "comparable" and math.isclose(share["before"], .6) and math.isclose(share["after"], .7)
        assert math.isclose(share["delta"], 10) and share["delta_unit"] == "percentage_points"
    return evidence


def validate_answer(reply, previous, current, changes, *, require_change):
    assert reply["mode"] == "deepseek", "Real model answer was downgraded: " + str(reply.get("warning", "unknown"))
    assert not reply.get("warning")
    context = reply["analysis_context"]
    assert context["analysis_id"] == current["analysis_id"]
    assert context["previous_analysis_id"] == previous["analysis_id"]
    assert context["refresh_comparison"] == current["refresh_comparison"]
    assert context["realtime_guaranteed"] is False
    assert context["scopes"][0]["received_at"] == current["snapshot"]["received_at"]
    assert context["scopes"][0]["market_data_status"] == current["quality"]["market_data_status"]
    _, ordinary = original_evidence(current)
    allowed = set(ordinary) | set(changes)
    identifiers = context["evidence_ids"]
    assert set(identifiers) <= allowed and len(identifiers) == len(set(identifiers))
    if require_change:
        assert any(key.startswith("change.") for key in identifiers), "Refresh explanation omitted before/after evidence"
    assert list(dict.fromkeys(re.findall(r"\[([A-Za-z0-9_.-]+)\]", reply["answer"]))) == identifiers
    cards = context["evidence"]
    assert [item["id"] for item in cards] == identifiers
    checks = []
    for card in cards:
        if card["id"].startswith("change."):
            original = changes[card["id"]]
            for field in ("before", "after", "delta", "unit", "delta_unit", "status", "reason", "direction", "symbol", "expiry",
                          "previous_received_at", "received_at", "before_feed", "after_feed"):
                assert card[field] == original[field], "Model-facing change evidence differs from saved local comparison"
            assert card["value"] == original["after"]
            checks.append({"id": card["id"], "before": card["before"], "after": card["after"],
                           "delta": card["delta"], "status": card["status"], "matches_original": True})
        else:
            assert card["value"] == ordinary[card["id"]]["value"]
            checks.append({"id": card["id"], "value": card["value"], "matches_original": True})
    return {"mode": reply["mode"], "answer_excerpt": safe_text(reply["answer"])[:3000],
            "analysis_binding_matches": True, "comparison_retained": True,
            "realtime_guaranteed": False, "citations": checks}


def run(gateway_mode=False):
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app
    from app.options_chat import _read_response, _validate_changes

    destination = ROOT / "reports" / ("options_refresh_gateway_v11.json" if gateway_mode else "options_refresh_cloud_v11.json")
    diagnostic_path = ROOT / "tmp" / ("options-refresh-v11-diagnostic-gateway.json" if gateway_mode else "options-refresh-v11-diagnostic-cloud-fixture.json")
    report = {
        "checked_at": datetime.now(UTC).isoformat(), "status": "running", "turns": [], "checks": [],
        "scope": ("Actual local IB Gateway acceptance, requested as delayed: attempt an initial AAPL collection, then one explicit refresh and one real DeepSeek explanation only if collection succeeds. Actual attempt/success/model counters below determine what completed."
                  if gateway_mode else "Synthetic before/after market data, real local analytics and in-process API routes, real DeepSeek refresh explanation and follow-up. No IBKR connection; not live-market validation."),
        "privacy": "Temporary isolated database. Reports contain safe aggregate comparisons and controlled answer excerpts only; no keys, account fields, session IDs, raw quotes or prompts. Safe provider response diagnostics remain in tmp/ and must not be submitted.",
        "transport": "FastAPI TestClient plus actual external DeepSeek HTTPS",
        "automatic_retries": 0,
    }
    calls, diagnostics, captures, successful_captures = [], [], [], []
    previous = None
    try:
        with TemporaryDirectory(prefix="finpilot-refresh-v11-") as temporary:
            settings = Settings(db_path=Path(temporary) / "isolated.sqlite3")
            assert settings.online, "Configured online DeepSeek credentials are required"
            report["model"] = settings.model
            if gateway_mode:
                from app.options_ibkr import IBKROptionsProvider
                gateway = IBKROptionsProvider()
            else:
                gateway = FixtureGateway()
            snapshot = gateway.snapshot

            async def counted_snapshot(symbol, expiry, strike_count, market_data_type):
                assert len(captures) < 2, "Additional gateway capture blocked"
                captures.append({"symbol": symbol, "expiry": expiry, "strike_count": strike_count, "requested_market_data_type": market_data_type})
                captured = await snapshot(symbol, expiry, strike_count, market_data_type)
                successful_captures.append(True)
                return captured

            gateway.snapshot = counted_snapshot
            app = create_app(settings, options_provider=gateway)
            complete = app.state.options.llm.complete
            limit = 1 if gateway_mode else 2

            async def counted_complete(messages, **kwargs):
                assert previous is not None and len(captures) == 2, "Model called before explicit refresh collection"
                assert len(calls) < limit, "Extra model call blocked; no automatic retries"
                payload = json.loads(messages[-1]["content"])
                current = app.state.store.get_analysis(payload["saved_snapshot"]["analysis_id"])
                assert current is not None
                changes = validate_comparison(previous, current, synthetic=not gateway_mode)
                _, ordinary = original_evidence(current)
                sent = {item["id"]: item for item in payload["evidence"]}
                assert set(sent) == set(ordinary) | set(changes)
                for identifier, item in sent.items():
                    if identifier in changes:
                        assert item["value"] == changes[identifier]["after"]
                        assert item["delta"] == changes[identifier]["delta"]
                    else:
                        assert item["value"] == ordinary[identifier]["value"]
                calls.append({"prior_messages": len(messages) - 2, "sent_evidence_count": len(sent), "sent_change_count": len(changes)})
                content = await complete(messages, **kwargs)
                diagnostic = {"turn": len(calls), "provider_response": safe_text(content)[:15000]}
                try:
                    parts = _read_response(content, set(sent))
                    _validate_changes(parts, sent)
                    diagnostic["accepted_by_local_parser"] = True
                except (ValueError, TypeError) as error:
                    diagnostic.update(accepted_by_local_parser=False, validation_error=safe_text(error)[:500])
                diagnostics.append(diagnostic)
                diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
                diagnostic_path.write_text(json.dumps({"scope": "Safe provider text only, without prompts/headers/credentials/accounts; excluded from submission.", "turns": diagnostics},
                                                     ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
                return content

            app.state.options.llm.complete = counted_complete
            with TestClient(app) as client:
                previous = require_ok(client.post("/api/options/analyze", json={
                    "symbol": "AAPL" if gateway_mode else "DEMO", "radius": 1,
                    "market_data_type": 3, "interpret_with_llm": False,
                }))
                old_id = previous["analysis_id"]
                assert UUID(old_id).version == 4 and not calls and len(captures) == 1
                old_hash = fingerprint(previous)
                sid = require_ok(client.post("/api/sessions", json={"title": "隔离刷新验收"}), 201)["id"]
                require_ok(client.put(f"/api/sessions/{sid}/analysis", json={"analysis_id": old_id}))
                refreshed = require_ok(client.post(f"/api/sessions/{sid}/analysis/refresh", json={
                    "analysis_id": old_id, "language": "zh", "engine": "deepseek",
                }))
                assert refreshed["refreshed"] is True and refreshed["user_message"]
                new_id = refreshed["analysis_context"]["analysis_id"]
                assert new_id != old_id and UUID(new_id).version == 4
                current = require_ok(client.get("/api/options/analyses/" + new_id))
                changes = validate_comparison(previous, current, synthetic=not gateway_mode)
                report.update(old_analysis_id=old_id, new_analysis_id=new_id, old_fingerprint=old_hash,
                              old_captured_at=previous["snapshot"]["received_at"], new_captured_at=current["snapshot"]["received_at"],
                              before_feed=previous["quality"]["market_data_status"], after_feed=current["quality"]["market_data_status"],
                              comparison_status=current["refresh_comparison"]["status"],
                              local_changes=[{"id": key, **{field: item[field] for field in ("before", "after", "delta", "unit", "delta_unit", "status", "reason")}}
                                             for key, item in changes.items()])
                summary = {"mode": refreshed.get("mode"), "warning": refreshed.get("warning"), "answer_excerpt": safe_text(refreshed.get("answer", ""))[:3000]}
                report["turns"].append(summary)
                summary.update(validate_answer(refreshed, previous, current, changes, require_change=True))
                replies = [refreshed]
                if not gateway_mode:
                    followup = require_ok(client.post("/api/chat", json={
                        "session_id": sid, "message": "这个变化能说明多数人看空吗？请解释依据和局限。", "language": "zh", "engine": "deepseek",
                    }))
                    summary = {"mode": followup.get("mode"), "warning": followup.get("warning"), "answer_excerpt": safe_text(followup.get("answer", ""))[:3000]}
                    report["turns"].append(summary)
                    summary.update(validate_answer(followup, previous, current, changes, require_change=False))
                    replies.append(followup)
                assert len(calls) == limit and len(captures) == 2
                assert calls[0]["prior_messages"] == 0
                if not gateway_mode:
                    assert calls[1]["prior_messages"] == 2
                for container in (require_ok(client.get("/api/sessions/" + sid)), require_ok(client.get(f"/api/sessions/{sid}/export"))):
                    assert container["active_analysis_id"] == new_id
                    assert [item["analysis_id"] for item in container["analysis_history"]] == [new_id, old_id]
                    assert [item["is_current"] for item in container["analysis_history"]] == [True, False]
                    assert len(container["messages"]) == 2 * len(replies)
                    for index, reply in enumerate(replies):
                        assert container["messages"][2 * index + 1]["analysis_context"] == reply["analysis_context"]
                assert fingerprint(require_ok(client.get("/api/options/analyses/" + old_id))) == old_hash
                assert app.state.store.get_analysis(old_id) == previous
                assert require_ok(client.get("/api/options/analyses/" + new_id)) == current
                report.update(status="passed", history_count=2, model_requests=calls,
                              old_snapshot_unchanged=True, new_snapshot_unchanged_during_followup=True,
                              ibkr_captures=2 if gateway_mode else 0, synthetic_captures=0 if gateway_mode else 2)
                report["checks"] = ["explicit_refresh_only", "exact_saved_parameters_and_expiry", "new_server_uuid_and_previous_link",
                                    "local_before_after_delta_verified", "all_citations_resolve_to_local_evidence", "refresh_explanation_cites_change_evidence",
                                    "old_snapshot_hash_unchanged", "history_retains_both_versions", "session_export_preserves_context",
                                    "comparison_survives_followup" if not gateway_mode else "limited_data_never_generate_fake_deltas", "no_automatic_retry"]
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__)
        if isinstance(error, AssertionError):
            report["error_code"] = safe_text(error)[:250]
        raise
    finally:
        report["real_model_requests"] = len(calls)
        report["collection_attempts"] = captures
        report["collection_attempt_count"] = len(captures)
        report["successful_collection_count"] = len(successful_captures)
        report["ibkr_collection_attempts"] = len(captures) if gateway_mode else 0
        report["provider_validation"] = [{key: item[key] for key in ("turn", "accepted_by_local_parser", "validation_error") if key in item} for item in diagnostics]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "report": str(destination), "real_model_requests": len(calls)}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--cloud-fixture", action="store_true", help="Allow two real model calls with synthetic old/new market data; no IBKR")
    mode.add_argument("--gateway", action="store_true", help="Allow two AAPL delayed captures and one real model call")
    args = parser.parse_args()
    if not (args.cloud_fixture or args.gateway):
        parser.print_help()
        print("No mode selected: no external request was made.")
        return 0
    run(gateway_mode=args.gateway)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
