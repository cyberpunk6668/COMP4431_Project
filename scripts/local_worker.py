"""Persistent JSON-lines local inference worker. Run by app.local_llm only.

Requires requirements-ml.txt. It uses ONLY cached weights (never remote code).
"""
import argparse
import json
import sys
from pathlib import Path


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", required=True)
    args = parser.parse_args()
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel

        adapter = Path(args.adapter)
        manifest = json.loads((adapter / "training_manifest.json").read_text(encoding="utf-8"))
        base_id = manifest["base_model_id"]
        revision = manifest["base_revision"]
        torch.set_num_threads(4)
        cuda = torch.cuda.is_available()
        dtype = torch.bfloat16 if cuda and torch.cuda.is_bf16_supported() else torch.float16 if cuda else torch.float32
        tokenizer = AutoTokenizer.from_pretrained(base_id, revision=revision, local_files_only=True, trust_remote_code=False)
        model = AutoModelForCausalLM.from_pretrained(base_id, revision=revision, local_files_only=True,
                    trust_remote_code=False, torch_dtype=dtype, low_cpu_mem_usage=True,
                    device_map={"": "cuda:0" if cuda else "cpu"}, attn_implementation="sdpa")
        model = PeftModel.from_pretrained(model, str(adapter), local_files_only=True)
        model.eval()
        emit({"ready": True, "device": "cuda" if cuda else "cpu"})
    except Exception:
        emit({"ready": False, "error": "local_model_unavailable"})
        return 1
    for line in sys.stdin:
        try:
            request = json.loads(line)
            # Bound context for the 8GB experimental model. Knowledge remains grounded in the server prompt.
            messages = request["messages"]
            if len(messages) > 4:
                messages = [messages[0], *messages[-3:]]
            prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
            inputs = tokenizer(prompt, return_tensors="pt", truncation=False)
            if inputs["input_ids"].shape[-1] > 8192:
                emit({"error": "local_context_too_long"})
                continue
            inputs = inputs.to(model.device)
            with torch.inference_mode():
                output = model.generate(**inputs, max_new_tokens=min(int(request.get("max_new_tokens", 512)), 512),
                            do_sample=False, repetition_penalty=1.05, pad_token_id=tokenizer.eos_token_id)
            generated = output[0, inputs["input_ids"].shape[-1]:]
            eos = model.generation_config.eos_token_id
            stop_ids = set(eos if isinstance(eos, list) else [eos]) | {tokenizer.eos_token_id}
            if not len(generated) or int(generated[-1]) not in stop_ids:
                emit({"error": "local_response_truncated", "finish_reason": "length"})
                continue
            content = tokenizer.decode(generated, skip_special_tokens=True).strip()
            emit({"content": content, "finish_reason": "stop"})
        except Exception:
            emit({"error": "local_model_unavailable"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
