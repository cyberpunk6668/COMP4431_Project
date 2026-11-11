"""Safe transport facts survive API errors and partial batches."""
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.options_ibkr import IBKROptionsError


DIAGNOSTICS = {"stage": "underlying", "requested_market_data_type": 3,
               "received_market_data_types": [3], "broker_codes": [10167],
               "entitlement_status": "realtime_unsubscribed_delayed_available",
               "data_status": "no_reference", "underlying_fields": [],
               "interface_status": "market_callbacks_received"}


class UnavailableGateway:
    async def snapshot(self, *args):
        error = IBKROptionsError("ibkr_underlying_unavailable", "PRIVATE BROKER STRING MUST NOT ESCAPE")
        error.diagnostics = DIAGNOSTICS.copy()
        raise error


def client(tmp_path):
    return TestClient(create_app(Settings(api_key="", offline=True, db_path=tmp_path / "diag.sqlite3"), options_provider=UnavailableGateway()))


def test_failed_analysis_preserves_allowlisted_transport_facts_without_broker_text(tmp_path):
    response = client(tmp_path).post("/api/options/analyze", json={"symbol": "AAPL", "market_data_type": 3})
    assert response.status_code == 424
    assert response.json()["detail"]["diagnostics"] == DIAGNOSTICS
    assert "PRIVATE BROKER" not in response.text
    assert response.json()["detail"]["code"] == "ibkr_underlying_unavailable"


def test_partial_batch_error_keeps_actual_feed_and_delayed_notice(tmp_path):
    response = client(tmp_path).post("/api/options/batch", json={"items": [{"symbol": "AAPL"}, {"symbol": "MSFT"}]})
    assert response.status_code == 200
    result = response.json()
    assert result["analysis_id"] is None and not result["reports"]
    assert all(failure["diagnostics"] == DIAGNOSTICS for failure in result["failures"])
    assert "PRIVATE BROKER" not in response.text
