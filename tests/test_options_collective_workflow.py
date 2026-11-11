"""Collective workflow regression tests use synthetic snapshots and a fake LLM."""
from copy import deepcopy
import asyncio
import json

import pytest

from app.options_ibkr import IBKROptionsError
from test_options_workflow import make_client, make_snapshot


class SequenceGateway:
    def __init__(self, mode=1, fail_symbols=()):
        self.mode = mode
        self.fail_symbols = set(fail_symbols)
        self.calls = []

    async def status(self):
        return {"status": "tcp_ready", "provider": "ibkr", "tcp_reachable": True}

    async def snapshot(self, symbol, expiry, strike_count, market_data_type):
        self.calls.append((symbol, expiry, strike_count, market_data_type))
        if symbol in self.fail_symbols:
            raise IBKROptionsError("ibkr_entitlement_missing", "Private account U1234567 diagnostic")
        result = deepcopy(make_snapshot(mode=market_data_type or self.mode))
        result["symbol"] = symbol
        if expiry:
            result["expiration"] = expiry
            for quote in result["quotes"]:
                quote["expiration"] = expiry
        for quote in result["quotes"]:
            if symbol == "MSFT":
                quote["volume"] = 30 if quote["right"] == "C" else 10
        return result


def ids_from_messages(messages):
    payload = json.loads(messages[-1]["content"])
    ids = [item["id"] for cohort in payload["cohorts"] for item in cohort["evidence"]]
    ids.extend(item["id"] for item in payload["comparisons"])
    return payload, ids


def assert_aggregate_fields_only(value):
    forbidden = {"quotes", "symbol", "expiration", "bid", "ask", "last", "account", "strike", "received_at"}
    if isinstance(value, dict):
        assert not forbidden.intersection(value)
        for child in value.values():
            assert_aggregate_fields_only(child)
    elif isinstance(value, list):
        for child in value:
            assert_aggregate_fields_only(child)


def model_report(ids):
    assert len(ids) >= 2
    return {
        "summary": {"text": "The sample combines relative activity with quote quality evidence.", "evidence_ids": ids[:2]},
        "observations": [
            {"text": "Relative activity differs within the sampled contracts.", "evidence_ids": ids[:1]},
            {"text": "Quote coverage controls how strongly this pattern can be described.", "evidence_ids": ids[1:2]},
        ],
        "conflicts": [],
        "scenarios": [{"condition": "If comparable evidence remains available", "implication": "Recheck whether the pattern persists across the same sample.", "evidence_ids": ids[:2]}],
        "limitations": ["The observation covers the sampled contracts at their collection times."],
    }


def test_batch_collects_each_item_and_calls_model_once(tmp_path):
    gateway = SequenceGateway()
    client, service = make_client(tmp_path, gateway)
    model_calls = []

    async def synthesize(messages, *, json_output):
        assert json_output
        payload, ids = ids_from_messages(messages)
        model_calls.append(payload)
        assert len(payload["cohorts"]) == 2
        serialized = json.dumps(payload)
        assert "AAPL" not in serialized and "MSFT" not in serialized
        assert_aggregate_fields_only(payload)
        return json.dumps(model_report(ids))

    service.llm.complete = synthesize
    response = client.post("/api/options/batch", json={
        "items": [{"symbol": " aapl "}, {"symbol": "MSFT"}],
        "radius": 1, "interpret_with_llm": True,
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert [report["snapshot"]["symbol"] for report in result["reports"]] == ["AAPL", "MSFT"]
    assert len(gateway.calls) == 2 and len(model_calls) == 1
    assert not result["failures"]
    assert result["comparison"]
    assert result["interpretation"]["status"] == "ok"
    assert len(result["interpretation"]["report"]["observations"]) >= 2
    assert result["completed_at"]
    assert all(report["capture_age_seconds"] >= 0 for report in result["reports"])


def test_batch_partial_failure_keeps_success_and_safe_diagnostic(tmp_path):
    gateway = SequenceGateway(fail_symbols={"FAIL"})
    client, _ = make_client(tmp_path, gateway)
    response = client.post("/api/options/batch", json={"items": [{"symbol": "AAPL"}, {"symbol": "FAIL"}]})
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["reports"]) == 1
    assert data["reports"][0]["snapshot"]["symbol"] == "AAPL"
    assert data["failures"][0]["symbol"] == "FAIL"
    assert data["failures"][0]["code"] == "ibkr_entitlement_missing"
    assert "U1234567" not in response.text
    assert data["interpretation"]["status"] == "skipped"


def test_default_and_explicit_expiry_resolving_to_same_scope_are_not_double_counted(tmp_path):
    gateway = SequenceGateway()
    client, _ = make_client(tmp_path, gateway)
    expiry = make_snapshot()["expiration"]
    response = client.post("/api/options/batch", json={"items": [{"symbol": "AAPL"}, {"symbol": "AAPL", "expiry": expiry}]})
    assert response.status_code == 200
    result = response.json()
    assert len(result["reports"]) == 1
    assert result["failures"][0]["code"] == "duplicate_resolved_contract_scope"


@pytest.mark.parametrize("items", [[], [{"symbol": "AAPL"}] * 2,
    [{"symbol": symbol} for symbol in ("A", "B", "C", "D", "E")]])
def test_batch_rejects_empty_duplicate_and_oversized_requests(tmp_path, items):
    gateway = SequenceGateway()
    client, _ = make_client(tmp_path, gateway)
    assert client.post("/api/options/batch", json={"items": items}).status_code == 422
    assert not gateway.calls


def test_delayed_snapshot_can_have_descriptive_joint_model_analysis(tmp_path):
    gateway = SequenceGateway(mode=3)
    client, service = make_client(tmp_path, gateway)
    model_calls = []

    async def synthesize(messages, *, json_output):
        payload, ids = ids_from_messages(messages)
        model_calls.append(payload)
        assert payload["cohorts"][0]["market_data_status"] == "delayed"
        return json.dumps(model_report(ids))

    service.llm.complete = synthesize
    response = client.post("/api/options/analyze", json={"symbol": "AAPL", "interpret_with_llm": True})
    assert response.status_code == 200, response.text
    result = response.json()
    assert not result["quality"]["llm_eligible"]
    assert result["collective"]["assessment"]["status"] == "descriptive"
    assert result["interpretation"]["status"] == "ok" and len(model_calls) == 1


@pytest.mark.parametrize("fault", ["unknown_reference", "numeric_prose", "missing_observations"])
def test_model_validation_rejects_bad_claims_without_losing_analysis(tmp_path, fault):
    client, service = make_client(tmp_path, SequenceGateway())

    async def bad_report(messages, *, json_output):
        _, ids = ids_from_messages(messages)
        report = model_report(ids)
        if fault == "unknown_reference":
            report["summary"]["evidence_ids"] = ["made_up.metric"]
        elif fault == "numeric_prose":
            report["summary"]["text"] = "The sample implies a guaranteed gain of 100%."
        else:
            report["observations"] = []
        return json.dumps(report)

    service.llm.complete = bad_report
    response = client.post("/api/options/analyze", json={"symbol": "AAPL", "interpret_with_llm": True})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["interpretation"]["status"] == "unavailable"
    assert result["interpretation"]["reason"] == "unverified_model_output"
    assert result["collective"]["assessment"]["findings"]
    assert result["metrics"]["put_call_volume"]["value"] == 1.5


def test_chinese_cohort_identifiers_resolve_locally_and_repair_is_bounded(tmp_path):
    client, service = make_client(tmp_path, SequenceGateway())
    calls = []

    async def corrected(messages, *, json_output):
        calls.append(messages)
        payload = json.loads(messages[1]["content"])
        ids = [item["id"] for group in payload["cohorts"] for item in group["evidence"]]
        if len(calls) == 1:
            return '{"summary":"invalid schema"}'
        report = model_report(ids)
        report["summary"]["text"] = "g0的成交与持仓结构需要结合相同样本的报价条件解释。"
        return json.dumps(report)

    service.llm.complete = corrected
    result = client.post("/api/options/analyze", json={"symbol": "AAPL", "interpret_with_llm": True}).json()
    assert len(calls) == 2
    assert result["interpretation"]["status"] == "ok"
    assert result["interpretation"]["report"]["summary"]["text"].startswith("AAPL（")


def test_causal_pricing_expectation_is_rejected(tmp_path):
    client, service = make_client(tmp_path, SequenceGateway())
    calls = []

    async def unsupported(messages, *, json_output):
        calls.append(True)
        payload = json.loads(messages[1]["content"])
        ids = [item["id"] for group in payload["cohorts"] for item in group["evidence"]]
        report = model_report(ids)
        report["summary"]["text"] = "成交占比不同就应该出现定价分化。"
        return json.dumps(report)

    service.llm.complete = unsupported
    result = client.post("/api/options/analyze", json={"symbol": "AAPL", "interpret_with_llm": True}).json()
    assert len(calls) == 2
    assert result["interpretation"]["reason"] == "unverified_model_output"
    assert result["collective"]["assessment"]["findings"]


def test_narrative_deadline_preserves_collective_analysis(tmp_path, monkeypatch):
    client, service = make_client(tmp_path, SequenceGateway())
    monkeypatch.setattr("app.options_service.NARRATIVE_DEADLINE_SECONDS", 0.01)

    async def slow_model(*args, **kwargs):
        await asyncio.sleep(5)

    service.llm.complete = slow_model
    result = client.post("/api/options/analyze", json={"symbol": "AAPL", "interpret_with_llm": True}).json()
    assert result["interpretation"]["reason"] == "network_or_timeout"
    assert result["collective"]["assessment"]["findings"]
