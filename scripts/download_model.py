"""Download ONLY the pinned public base weights/tokenizer, without training.

Run using .venv-ml Python. Uses FINPILOT_HF_HOME/HF_HOME or Hugging Face's
standard cache. No API key or private conversation is used.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finetuning.model_config import BASE_MODEL_ID, BASE_REVISION, configure_cache

configure_cache()
from huggingface_hub import snapshot_download


def download_model():
    return snapshot_download(
        BASE_MODEL_ID, revision=BASE_REVISION,
        allow_patterns=["config.json", "generation_config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt", "LICENSE", "README.md"],
        max_workers=2,
    )


if __name__ == "__main__":
    folder = download_model()
    print(json.dumps({"base_model_id": BASE_MODEL_ID, "base_revision": BASE_REVISION, "snapshot": folder}, indent=2))
