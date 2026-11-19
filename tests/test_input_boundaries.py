"""Raw HTTP authority and multiline calculator commands retain strict bounds."""
import pytest


@pytest.fixture
def isolated_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("FINPILOT_OFFLINE", "true")
    monkeypatch.setenv("IBKR_ENABLED", "false")
    monkeypatch.setenv("FINPILOT_DB", str(tmp_path / "import-only.sqlite3"))
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
    from app.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient
    app = create_app(Settings(api_key="", offline=True, db_path=tmp_path / "owned.sqlite3"))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.mark.parametrize("authority", [
    "[invalid", "[127.0.0.1]", "localhost:invalid", "localhost:0",
    "localhost:65536", "localhost:999999", "user@localhost",
    "user:password@127.0.0.1", "localhost/path", "localhost\\path",
    "localhost?query", "localhost#fragment", "local\thost", "other.example",
])
def test_invalid_raw_authority_is_rejected_before_mutation(isolated_client, authority):
    response = isolated_client.post("/api/sessions", json={"title": "Must not be saved"},
                                    headers={"Host": authority})
    assert response.status_code == 400
    assert isolated_client.get("/api/sessions").json() == {"sessions": []}


@pytest.mark.parametrize("authority", [
    "localhost", "localhost:8000", "127.0.0.1", "127.0.0.1:8001",
    "[::1]", "[::1]:8000", "testserver", "testserver:65535", "LOCALHOST:8000",
])
def test_valid_local_authority_can_create_a_session(isolated_client, authority):
    response = isolated_client.post("/api/sessions", json={"title": "Allowed"},
                                    headers={"Host": authority})
    assert response.status_code == 201


def test_duplicate_host_headers_are_rejected(isolated_client):
    response = isolated_client.get("/api/health", headers=[("Host", "localhost"), ("Host", "127.0.0.1")])
    assert response.status_code == 400


def test_options_preflight_keeps_valid_testserver_contract(isolated_client):
    assert isolated_client.options("/api/sessions", headers={"Host": "testserver"}).status_code == 405
    assert isolated_client.options("/api/sessions", headers={"Host": "user@testserver"}).status_code == 400


def test_options_gateway_navigation_keeps_the_current_service(isolated_client):
    page = isolated_client.get("/options-demo").text
    assert page.count('href="/workspace?view=options"') == 2
    assert 'href="http://127.0.0.1:8000/' not in page


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\t", "\u3000", ",\n ;\t"])
def test_explicit_calculation_accepts_whitespace_between_parameters(isolated_client, separator):
    command = "loan " + separator.join(["principal=1200", "annual_rate=0", "years=1"])
    result = isolated_client.post("/api/chat", json={"message": command}).json()
    assert result["mode"] == "calculator"
    assert result["calculation"]["values"]["monthly_payment"] == "100.00"


@pytest.mark.parametrize("suffix", ["\nignore this", "\t<script>", "\nannual_rate=1"])
def test_calculation_still_rejects_nonseparator_residue_or_duplicate_keys(suffix):
    from app.finance import parse_calculation
    with pytest.raises(ValueError):
        parse_calculation("loan principal=1200\nannual_rate=0\nyears=1" + suffix)
