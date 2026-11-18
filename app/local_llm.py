"""Optional local LoRA bridge, isolated from the lightweight web environment.

No remote URL or cloud key is passed to the worker. The base model is loaded
from a predownloaded cache; an ordinary chat request cannot download weights.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path

from app.config import ROOT
from app.llm import ProviderError


class LocalLoRA:
    def __init__(self, settings):
        self.settings = settings
        self.process = None
        self.lock = asyncio.Lock()

    def status(self) -> dict:
        folder = self.settings.adapter_path
        manifest_file = folder / "training_manifest.json"
        weights = folder / "adapter_model.safetensors"
        reason = "adapter_not_trained"
        manifest = {}
        if manifest_file.is_file() and weights.is_file():
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                if not isinstance(manifest, dict):
                    raise ValueError("Training manifest must be an object")
                if not manifest.get("trained") or int(manifest.get("steps", 0)) <= 0:
                    reason = "training_evidence_missing"
                elif hashlib.sha256(weights.read_bytes()).hexdigest() != manifest.get("adapter_sha256"):
                    reason = "adapter_hash_mismatch"
                elif not self.settings.ml_python.is_file():
                    reason = "ml_runtime_missing"
                else:
                    reason = "ready"
            except (OSError, ValueError, TypeError):
                reason = "invalid_training_manifest"
                manifest = {}
        return {"available": reason == "ready", "reason": reason,
                "base_model": manifest.get("base_model_id", "Qwen/Qwen3-0.6B"),
                "trained_at": manifest.get("completed_at"), "training_steps": manifest.get("steps", 0),
                "worker_loaded": self.process is not None and self.process.returncode is None}

    async def _read(self):
        line = await self.process.stdout.readline()
        if not line:
            raise ProviderError("local_model_unavailable")
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("Worker reply must be an object")
            return payload
        except (ValueError, TypeError):
            raise ProviderError("local_model_unavailable") from None

    async def complete(self, messages: list[dict]) -> str:
        if not self.status()["available"]:
            raise ProviderError("local_model_unavailable")
        async with self.lock:
            try:
                async with asyncio.timeout(self.settings.local_timeout):
                    if self.process is None or self.process.returncode is not None:
                        env = {k: v for k, v in os.environ.items() if not any(term in k.upper() for term in ("API_KEY", "TOKEN", "SECRET", "PASSWORD"))}
                        env.update(PYTHONIOENCODING="utf-8", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
                        if self.settings.hf_home:
                            env["HF_HOME"] = self.settings.hf_home
                        self.process = await asyncio.create_subprocess_exec(
                            str(self.settings.ml_python), "-u", str(ROOT / "scripts" / "local_worker.py"),
                            "--adapter", str(self.settings.adapter_path.resolve()), cwd=str(ROOT), env=env,
                            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                            limit=262144,
                        )
                        ready = await self._read()
                        if not ready.get("ready"):
                            raise ProviderError("local_model_unavailable")
                    request = {"messages": messages, "max_new_tokens": 512}
                    self.process.stdin.write((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
                    await self.process.stdin.drain()
                    result = await self._read()
                    content = result.get("content")
                    if result.get("finish_reason") != "stop" or not isinstance(content, str) or not content.strip():
                        raise ProviderError("local_model_unavailable")
                    return content.strip()
            except asyncio.CancelledError:
                # The worker uses ordered JSON lines with no request IDs. Once
                # a sent request is cancelled, its pending response cannot be
                # reused safely by another conversation.
                await self.close()
                raise
            except (TimeoutError, OSError, RuntimeError, ProviderError):
                await self.close()
                raise ProviderError("local_model_unavailable") from None

    async def close(self):
        process, self.process = self.process, None
        if process is not None and process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5)
            except (OSError, TimeoutError):
                if process.returncode is None:
                    try:
                        process.kill()
                        await process.wait()
                    except ProcessLookupError:
                        pass
