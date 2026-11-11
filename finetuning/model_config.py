"""Shared public model identity; no private or project-specific absolute paths."""
import os
from pathlib import Path

BASE_MODEL_ID = "Qwen/Qwen3-0.6B"
BASE_REVISION = "c1899de289a04d12100db370d81485cdf75e47ca"
ROOT = Path(__file__).resolve().parents[1]


def configure_cache() -> Path:
    value = os.getenv("FINPILOT_HF_HOME") or os.getenv("HF_HOME")
    folder = Path(value) if value else Path.home() / ".cache" / "huggingface"
    os.environ["HF_HOME"] = str(folder)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    return folder
