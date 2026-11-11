from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.options_ibkr import IBKROptionsError
from test_options_workflow import FixtureGateway


class ExpiryGateway(FixtureGateway):
    expirations = ["2030-11-20", "2030-11-22"]

    def __init__(self):
        super().__init__()
        self.metadata_calls = []

    async def list_expirations(self, symbol):
        self.metadata_calls.append(symbol)
        return {"source": "ibkr", "symbol": symbol, "expirations": self.expirations,
                "trading_class": symbol, "currency": "USD", "date_kind": "expiration",
                "timezone": "America/New_York", "as_of": "2030-11-18T14:00:00+00:00"}

    async def snapshot(self, symbol, expiry, strike_count, market_data_type):
        if expiry and expiry not in self.expirations:
            raise IBKROptionsError("ibkr_expiration_unavailable", "Synthetic unavailable expiry",
                                   available_expirations=self.expirations)
        snapshot = await super().snapshot(symbol, expiry, strike_count, market_data_type)
        snapshot["symbol"] = symbol
        snapshot["expiration"] = expiry or self.expirations[0]
        for row in snapshot["quotes"]:
            row["expiration"] = snapshot["expiration"]
        return snapshot


def client(tmp_path, gateway):
    return TestClient(create_app(Settings(api_key="", offline=True, db_path=tmp_path / "db.sqlite3"), options_provider=gateway))


def test_expiration_endpoint_uses_metadata_without_quotes(tmp_path):
    gateway = ExpiryGateway()
    response = client(tmp_path, gateway).get("/api/options/expirations", params={"symbol": " aapl "})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["expirations"] == ["2030-11-20", "2030-11-22"]
    assert response.json()["date_kind"] == "expiration"
    assert gateway.metadata_calls == ["AAPL"] and not gateway.calls


def test_invalid_symbol_does_not_reach_gateway(tmp_path):
    gateway = ExpiryGateway()
    response = client(tmp_path, gateway).get("/api/options/expirations", params={"symbol": "../../.env"})
    assert response.status_code == 422
    assert not gateway.metadata_calls and not gateway.calls


def test_unsupported_date_returns_actual_choices_without_quotes(tmp_path):
    gateway = ExpiryGateway()
    response = client(tmp_path, gateway).post("/api/options/analyze", json={"symbol": "AAPL", "expiry": "2030-11-21"})
    assert response.status_code == 404
    assert response.json()["detail"]["available_expirations"] == gateway.expirations
    assert not gateway.calls


def test_batch_preserves_valid_results_and_date_choices_for_failed_item(tmp_path):
    gateway = ExpiryGateway()
    response = client(tmp_path, gateway).post("/api/options/batch", json={"items": [
        {"symbol": "AAPL"}, {"symbol": "AAPL", "expiry": "2030-11-21"},
    ]})
    assert response.status_code == 200
    data = response.json()
    assert len(data["reports"]) == 1
    assert data["failures"][0]["available_expirations"] == gateway.expirations
    assert len(gateway.calls) == 1
