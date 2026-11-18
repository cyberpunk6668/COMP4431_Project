import asyncio

import httpx
import pytest

from app.config import Settings
from app.llm import DeepSeek, ProviderError


@pytest.mark.parametrize("error", [httpx.RemoteProtocolError("closed"), httpx.ProxyError("proxy"), httpx.ReadTimeout("timeout")])
def test_transport_failure_does_not_leak_or_crash(monkeypatch, error):
    class BrokenClient:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, *args, **kwargs):
            raise error
    monkeypatch.setattr(httpx, "AsyncClient", BrokenClient)
    with pytest.raises(ProviderError, match="network_or_timeout"):
        asyncio.run(DeepSeek(Settings(api_key="test-only")).complete([]))


def test_absolute_provider_deadline(monkeypatch):
    class SlowClient:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, *args, **kwargs):
            await asyncio.sleep(10)
    monkeypatch.setattr(httpx, "AsyncClient", SlowClient)
    with pytest.raises(ProviderError, match="network_or_timeout"):
        asyncio.run(DeepSeek(Settings(api_key="test-only", timeout=0.01)).complete([]))


@pytest.mark.parametrize("payload", [
    None, [], {"choices": None}, {"choices": []}, {"choices": {}},
    {"choices": [None]}, {"choices": [[]]},
    {"choices": [{"finish_reason": "stop", "message": None}]},
    {"choices": [{"finish_reason": "stop", "message": []}]},
])
def test_malformed_success_payload_is_a_provider_error(monkeypatch, payload):
    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            return httpx.Response(200, json=payload)

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    with pytest.raises(ProviderError, match="invalid_response"):
        asyncio.run(DeepSeek(Settings(api_key="test-only")).complete([]))
