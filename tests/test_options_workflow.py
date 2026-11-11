from datetime import UTC, datetime, timedelta
import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.llm import ProviderError
from app.main import create_app
from app.options_ibkr import IBKROptionsError


def make_snapshot(mode=1):
    stamp = datetime.now(UTC).isoformat()
    expiry = (datetime.now(UTC).date() + timedelta(days=21)).isoformat()
    return {
        "source": "ibkr", "symbol": "TEST", "expiration": expiry, "currency": "USD",
        "started_at": stamp, "received_at": stamp, "requested_strikes": [95, 100, 105],
        "underlying": {"price": 100, "price_basis": "midpoint", "bid": 99.9, "ask": 100.1,
                       "market_data_type": mode, "received_at": stamp},
        "quotes": [
            {"right": side, "strike": strike, "expiration": expiry, "bid": 2, "ask": 2.2,
             "volume": 10 if side == "C" else 15, "open_interest": 100 if side == "C" else 140,
             "market_data_type": mode, "received_at": stamp, "quote_received_at": stamp,
             "volume_received_at": stamp, "open_interest_received_at": stamp}
            for strike in [95, 100, 105] for side in ("C", "P")
        ],
    }


class FixtureGateway:
    def __init__(self, mode=1, error=None):
        self.mode, self.error, self.calls = mode, error, []

    async def status(self):
        return {"status": "tcp_ready", "tcp_reachable": True, "provider": "ibkr"}

    async def snapshot(self, symbol, expiry, strike_count, market_data_type):
        self.calls.append((symbol, expiry, strike_count, market_data_type))
        if self.error:
            raise IBKROptionsError(self.error, "Synthetic broker failure")
        return make_snapshot(self.mode)


def make_client(tmp_path, gateway):
    settings = Settings(api_key="test-only", offline=False, db_path=tmp_path / "test.sqlite3")
    app = create_app(settings, options_provider=gateway)
    return TestClient(app), app.state.options


def test_batch_routes_without_cloud_or_session_persistence(tmp_path):
    gateway = FixtureGateway()
    client, service = make_client(tmp_path, gateway)

    async def unexpected(*args, **kwargs):
        raise AssertionError("Cloud was not requested")

    service.llm.complete = unexpected
    assert client.get("/api/options/status").json()["tcp_reachable"]
    result = client.post("/api/options/analyze", json={"symbol": " test ", "radius": 1})
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    data = result.json()
    assert gateway.calls == [("TEST", None, 3, None)]
    assert data["quality"]["market_data_status"] == "live"
    assert data["metrics"]["put_call_volume"]["value"] == 1.5
    assert data["interpretation"] == {"status": "skipped", "reason": "not_requested"}
    assert client.get("/api/sessions").json() == {"sessions": []}


def test_cloud_receives_only_aggregates_and_returns_generated_report(tmp_path):
    client, service = make_client(tmp_path, FixtureGateway())

    async def select(messages, *, json_output):
        assert json_output
        evidence = json.loads(messages[-1]["content"])
        assert evidence["cohorts"][0]["market_data_status"] == "live"
        records = {item["id"]: item for item in evidence["cohorts"][0]["evidence"]}
        assert records["g0.volume_put_share"]["value"] == 0.6
        assert set(evidence) == {"scope", "cohorts", "comparisons", "cohort_relations"}
        refs = ["g0.volume_put_share", "g0.oi_put_share"]
        return json.dumps({
            "summary": {"text": "Sample activity and inventory indicate different relative emphases.", "evidence_ids": refs},
            "observations": [
                {"text": "Put activity exceeds call activity in the sampled contracts.", "evidence_ids": refs[:1]},
                {"text": "Outstanding inventory describes a separate reporting cycle.", "evidence_ids": refs[1:]},
            ], "conflicts": [],
            "scenarios": [{"condition": "If the relative activity persists in a comparable sample",
                           "implication": "Check whether the inventory distribution also changes.", "evidence_ids": refs}],
            "limitations": ["The sampled window covers a single expiry."],
        })

    service.llm.complete = select
    result = client.post("/api/options/analyze", json={"symbol": "TEST", "radius": 1, "interpret_with_llm": True, "language": "en"})
    data = result.json()
    assert data["interpretation"]["status"] == "ok"
    assert data["interpretation"]["evidence"] == ["g0.oi_put_share", "g0.volume_put_share"]
    assert data["interpretation"]["text"].startswith("Sample activity")


def test_insufficient_delayed_data_never_triggers_cloud(tmp_path):
    gateway = FixtureGateway(mode=3)
    client, service = make_client(tmp_path, gateway)
    original_capture = gateway.snapshot

    async def no_contract_fields(*args):
        snapshot = await original_capture(*args)
        snapshot["quotes"] = []
        return snapshot

    gateway.snapshot = no_contract_fields

    async def unexpected(*args, **kwargs):
        raise AssertionError("Delayed data passed the quality gate")

    service.llm.complete = unexpected
    data = client.post("/api/options/analyze", json={"symbol": "TEST", "market_data_type": 3, "interpret_with_llm": True}).json()
    assert gateway.calls == [("TEST", None, 9, 3)]
    assert data["quality"]["market_data_status"] == "delayed"
    assert data["interpretation"] == {"status": "unavailable", "reason": "evidence_insufficient"}


def test_invalid_cloud_output_and_provider_failure_preserve_calculations(tmp_path):
    client, service = make_client(tmp_path, FixtureGateway())

    async def invent(messages, *, json_output):
        return '{"evidence":["invented_metric"]}'

    service.llm.complete = invent
    body = {"symbol": "TEST", "interpret_with_llm": True}
    data = client.post("/api/options/analyze", json=body).json()
    assert data["interpretation"]["reason"] == "unverified_model_output"
    assert data["metrics"]["put_call_volume"]["value"] == 1.5

    async def fail(messages, *, json_output):
        raise ProviderError("network_or_timeout")

    service.llm.complete = fail
    data = client.post("/api/options/analyze", json=body).json()
    assert data["interpretation"]["reason"] == "network_or_timeout"
    assert data["metrics"]["put_call_volume"]["value"] == 1.5


def test_missing_entitlement_and_invalid_requests_are_explicit(tmp_path):
    gateway = FixtureGateway(error="ibkr_entitlement_missing")
    client, _ = make_client(tmp_path, gateway)
    for body in ({"symbol": "???"}, {"symbol": "AAPL", "expiry": "2026-02-30"}, {"symbol": "AAPL", "radius": 7}):
        assert client.post("/api/options/analyze", json=body).status_code == 422
    assert not gateway.calls
    response = client.post("/api/options/analyze", json={"symbol": "AAPL"})
    assert response.status_code == 424
    assert response.json()["detail"]["code"] == "ibkr_entitlement_missing"
