import hashlib
import json
import asyncio
from types import SimpleNamespace

import pytest

from fastapi.testclient import TestClient

from app.config import Settings
from app.local_llm import LocalLoRA
from app.llm import ProviderError
from app.local_prompt import LOCAL_SYSTEM
from app.main import create_app


def test_training_evidence_and_hash_required(tmp_path):
    config = Settings(adapter_path=tmp_path, ml_python=tmp_path / "python.exe")
    provider = LocalLoRA(config)
    assert not provider.status()["available"]
    (tmp_path / "adapter_model.safetensors").write_bytes(b"test weights")
    manifest = {"trained": True, "steps": 20, "adapter_sha256": "bad"}
    (tmp_path / "training_manifest.json").write_text(json.dumps(manifest))
    assert provider.status()["reason"] == "adapter_hash_mismatch"
    manifest["adapter_sha256"] = hashlib.sha256(b"test weights").hexdigest()
    (tmp_path / "training_manifest.json").write_text(json.dumps(manifest))
    assert provider.status()["reason"] == "ml_runtime_missing"


@pytest.mark.parametrize("reply", [b"null\n", b"[]\n", b'"text"\n', b"not-json\n"])
def test_invalid_worker_replies_are_provider_errors(tmp_path, reply):
    class Reply:
        async def readline(self):
            return reply
    provider = LocalLoRA(Settings(adapter_path=tmp_path))
    provider.process = SimpleNamespace(stdout=Reply())
    with pytest.raises(ProviderError, match="local_model_unavailable"):
        asyncio.run(provider._read())


@pytest.mark.parametrize("manifest", [None, [], "text"])
def test_malformed_manifest_does_not_break_model_catalogue(tmp_path, manifest):
    (tmp_path / "training_manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "adapter_model.safetensors").write_bytes(b"test")
    provider = LocalLoRA(Settings(adapter_path=tmp_path))
    assert provider.status()["reason"] == "invalid_training_manifest"


def test_no_training_claim_without_artifact(tmp_path):
    app = create_app(Settings(api_key="", offline=True, db_path=tmp_path / "db", adapter_path=tmp_path / "missing"))
    client = TestClient(app)
    local = next(x for x in client.get("/api/models").json()["models"] if x["id"] == "local")
    assert not local["available"] and local["training_steps"] == 0
    result = client.post("/api/chat", json={"message": "什么是复利？", "engine": "local"}).json()
    assert result["mode"] == "offline"
    assert result["warning"] == "local_model_unavailable"


def test_local_mode_is_explicit_and_tool_path_preserved(tmp_path):
    app = create_app(Settings(api_key="", offline=True, db_path=tmp_path / "db", adapter_path=tmp_path / "missing"))
    class StubLocal:
        def status(self):
            return {"available": True}
        async def complete(self, messages):
            return "Compound interest earns interest on interest. [compound-interest]"
    app.state.service.local_provider = StubLocal()
    client = TestClient(app)
    result = client.post("/api/chat", json={"message": "Explain compound interest", "engine": "local", "language": "en"}).json()
    assert result["mode"] == "local-lora" and result["sources"]
    saved = client.get(f"/api/sessions/{result['session_id']}").json()
    assert saved["messages"][1]["mode"] == "local-lora"
    tool = client.post("/api/chat", json={"message": "loan principal=1200 annual_rate=0 years=1", "engine": "local"}).json()
    assert tool["mode"] == "calculator"


def test_training_and_runtime_instructions_do_not_drift():
    from finetuning.build_dataset import SYSTEM
    assert SYSTEM == LOCAL_SYSTEM
