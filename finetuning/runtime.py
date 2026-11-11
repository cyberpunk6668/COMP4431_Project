"""Shared low-memory loading and assistant-only tokenization for training/eval."""
import json
from pathlib import Path

from finetuning.model_config import BASE_MODEL_ID, BASE_REVISION, configure_cache

configure_cache()
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def load_base(local_files_only=True):
    if not torch.cuda.is_available():
        raise RuntimeError("This experiment requires an NVIDIA CUDA GPU. Install the documented CUDA PyTorch wheel.")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID, revision=BASE_REVISION, local_files_only=local_files_only)
    tokenizer.padding_side = "right"
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL_ID, revision=BASE_REVISION, torch_dtype=dtype,
                device_map={"": "cuda:0"}, low_cpu_mem_usage=True, attn_implementation="sdpa", local_files_only=local_files_only)
    return model, tokenizer


def prompt_ids(tokenizer, messages):
    # Non-thinking prompt has an empty think block, matching inference exactly.
    return tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, enable_thinking=False)


def encode_example(tokenizer, row, max_length):
    prefix = prompt_ids(tokenizer, row["messages"][:-1])
    # Tokenize the completion separately. This makes the loss boundary exact,
    # with no accidental training on prompt or reference tokens.
    completion = tokenizer(row["messages"][-1]["content"], add_special_tokens=False)["input_ids"] + [tokenizer.eos_token_id]
    ids = prefix + completion
    if len(ids) > max_length:
        raise ValueError(f"Example {row['id']} has {len(ids)} tokens, exceeds max_length={max_length}; do not silently truncate targets")
    return {"input_ids": ids, "attention_mask": [1] * len(ids), "labels": [-100] * len(prefix) + completion}


def read_rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def collate(tokenizer, rows):
    longest = max(len(row["input_ids"]) for row in rows)
    result = {}
    for key in ("input_ids", "attention_mask", "labels"):
        padding = -100 if key == "labels" else tokenizer.pad_token_id if key == "input_ids" else 0
        result[key] = torch.tensor([row[key] + [padding] * (longest-len(row[key])) for row in rows], dtype=torch.long)
    return result
