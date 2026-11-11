"""Actual LoRA supervised fine-tuning, without a paid service or private data."""
import argparse
import hashlib
import json
import platform
import random
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finetuning.model_config import BASE_MODEL_ID, BASE_REVISION, ROOT, configure_cache

configure_cache()
import torch
from peft import LoraConfig, get_peft_model
from torch.utils.data import DataLoader

from finetuning.build_dataset import build
from finetuning.runtime import collate, encode_example, load_base, read_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--learning-rate", type=float, default=0.0002)
    parser.add_argument("--output", type=Path, default=ROOT / "models" / "finpilot-lora")
    args = parser.parse_args()
    if args.epochs < 1:
        raise ValueError("epochs must be positive")
    torch.manual_seed(42)
    random.seed(42)
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = True
    build()
    model, tokenizer = load_base(local_files_only=True)
    dataset_manifest = json.loads((ROOT / "finetuning" / "data" / "manifest.json").read_text(encoding="utf-8"))
    rows = read_rows(ROOT / "finetuning" / "data" / "train.jsonl")
    encoded = [encode_example(tokenizer, row, args.max_length) for row in rows]
    validation = [encode_example(tokenizer, row, args.max_length) for row in read_rows(ROOT / "finetuning" / "data" / "validation.jsonl")]
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05,
                target_modules=["q_proj", "k_proj", "v_proj", "o_proj"], bias="none", task_type="CAUSAL_LM"))
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    loader = DataLoader(encoded, batch_size=1, shuffle=True, collate_fn=lambda batch: collate(tokenizer, batch), num_workers=0)
    optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=args.learning_rate, weight_decay=0.01)
    accum = 4
    started_at = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    history, steps, microsteps = [], 0, 0
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    report_path = ROOT / "reports" / "finetuning_training.json"
    report_path.parent.mkdir(exist_ok=True)
    torch.cuda.reset_peak_memory_stats()
    print(json.dumps({"status": "training", "examples": len(encoded), "trainable_parameters": trainable,
                      "total_parameters": total, "max_tokens": max(len(row['input_ids']) for row in encoded), "gpu": torch.cuda.get_device_name(0)}, indent=2), flush=True)
    for epoch in range(args.epochs):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        loss_sum = 0.0
        for batch_index, batch in enumerate(loader):
            batch = {k: value.to("cuda:0") for k, value in batch.items()}
            loss = model(**batch).loss
            if not torch.isfinite(loss):
                raise RuntimeError("Non-finite loss; no trained manifest will be issued")
            loss_sum += float(loss.detach())
            (loss / accum).backward()
            microsteps += 1
            if (batch_index + 1) % accum == 0 or batch_index + 1 == len(loader):
                torch.nn.utils.clip_grad_norm_((p for p in model.parameters() if p.requires_grad), 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                steps += 1
                if steps % 6 == 0:
                    print(json.dumps({"epoch": epoch+1, "optimizer_step": steps, "mean_loss_so_far": round(loss_sum/(batch_index+1), 5), "elapsed_seconds": round(time.perf_counter()-start, 1)}), flush=True)
        model.eval()
        with torch.inference_mode():
            validation_loss = sum(float(model(**{k: value.to('cuda:0') for k, value in collate(tokenizer, [row]).items()}).loss) for row in validation)/len(validation)
        event = {"epoch": epoch+1, "train_mean_example_loss": loss_sum/len(loader), "validation_mean_example_loss": validation_loss, "optimizer_steps": steps}
        history.append(event)
        print(json.dumps(event), flush=True)
        model.save_pretrained(out, safe_serialization=True)
        report_path.write_text(json.dumps({"status": "running", "started_at": started_at, "history": history, "optimizer_steps": steps}, indent=2), encoding="utf-8")
    adapter_path = out / "adapter_model.safetensors"
    completed_at = datetime.now(timezone.utc).isoformat()
    manifest = {"trained": True, "base_model_id": BASE_MODEL_ID, "base_revision": BASE_REVISION,
                "started_at": started_at, "completed_at": completed_at, "steps": steps, "microsteps": microsteps,
                "adapter_sha256": hashlib.sha256(adapter_path.read_bytes()).hexdigest(), "adapter_bytes": adapter_path.stat().st_size,
                "method": "LoRA supervised fine-tuning with assistant-only loss", "lora_rank": 8, "lora_alpha": 16,
                "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"], "epochs": args.epochs,
                "learning_rate": args.learning_rate, "gradient_accumulation_steps": accum, "batch_size": 1,
                "max_sequence_length": args.max_length, "enable_thinking": False,
                "trainable_parameters": trainable, "total_parameters_with_adapter": total,
                "trainable_percent": round(trainable/total*100, 6), "dataset": dataset_manifest,
                "duration_seconds": round(time.perf_counter()-start, 2), "peak_gpu_allocated_mib": round(torch.cuda.max_memory_allocated()/1024**2, 2),
                "hardware": {"gpu": torch.cuda.get_device_name(0), "gpu_total_mib": round(torch.cuda.get_device_properties(0).total_memory/1024**2), "python": platform.python_version(), "torch": torch.__version__},
                "history": history, "limits": "Small author-curated behaviour adaptation experiment, not a guarantee of financial factual accuracy and not a DeepSeek fine-tune."}
    from huggingface_hub import hf_hub_download
    license_path = hf_hub_download(BASE_MODEL_ID, "LICENSE", revision=BASE_REVISION, local_files_only=True)
    shutil.copyfile(license_path, out / "LICENSE")
    manifest["license"] = "Apache-2.0 (base model and derived adapter; official base LICENSE included)"
    card = f'''# FinPilot Finance Behaviour LoRA

## Identity and intended use

This is a real locally trained LoRA adapter for `{BASE_MODEL_ID}` at revision `{BASE_REVISION}`. It is not a fine-tuned DeepSeek model. It is an optional small-model experiment for financial education, paired with trusted local retrieved context and deterministic calculators.

Completed: {completed_at}. Optimizer steps: {steps}; epochs: {args.epochs}; LoRA rank: 8; trainable parameters: {trainable:,} ({manifest["trainable_percent"]}% of the model with adapter). Adapter SHA-256: `{manifest["adapter_sha256"]}`.

## Training

Targets attention q/k/v/o projections with BF16/FP16 frozen base weights and trainable LoRA updates. Assistant-only cross-entropy loss; prompts and references are masked. Batch size 1; gradient accumulation 4; learning rate {args.learning_rate}; maximum sequence {args.max_length}; thinking disabled. Actual run duration: {manifest["duration_seconds"]} seconds; peak allocated GPU memory: {manifest["peak_gpu_allocated_mib"]} MiB.

Data: 144 project-authored reference-based Chinese/English examples in 12 topic groups; 12 validation examples in 3 different groups; 12 test examples in 3 different groups. No private conversations, credentials, accounts or undisclosed teacher API output. See `finetuning/data/manifest.json` for dataset provenance and hashes.

## Evaluation and limits

The run log is `reports/finetuning_training.json`. The separate base/adapter comparison is `reports/finetuning_evaluation.json` after that script actually executes; do not infer evaluation success from this card. Reference evidence is provided to both variants. Narrow citation/format diagnostics are not financial factual accuracy or production safety. Topics and prompt families are small and author-curated. The model can hallucinate, omit caveats or follow an inappropriate request. There is no demonstrated superiority over DeepSeek. No live prices, trading, personal recommendations or return guarantees are provided.

## License and distribution

The public base model is Apache-2.0; the derived adapter is distributed under Apache-2.0 with its official LICENSE included. The base weights must be obtained separately from the official pinned Qwen repository. The source package contains the adapter, not the approximately 1.5GB base weights or the Python ML environment.
'''
    (out / "MODEL_CARD.md").write_text(card, encoding="utf-8")
    (out / "training_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(json.dumps({"status": "completed", **manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "completed", "steps": steps, "duration_seconds": manifest["duration_seconds"], "adapter_sha256": manifest["adapter_sha256"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
