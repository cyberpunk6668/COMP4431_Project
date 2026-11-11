"""Compare the same pinned base model with and without the trained adapter.

Measures assistant-token loss plus narrow format/citation behaviour on held-out
topic groups. Scores do not measure broad financial correctness or suitability.
"""
import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finetuning.model_config import BASE_MODEL_ID, BASE_REVISION, ROOT, configure_cache

configure_cache()
import torch
from peft import PeftModel
from finetuning.runtime import collate, encode_example, load_base, prompt_ids, read_rows


def evaluate(model, tokenizer, rows, max_length, generation_limit):
    model.eval()
    model.config.use_cache = True
    losses, outputs = [], []
    with torch.inference_mode():
        for row in rows:
            encoded = encode_example(tokenizer, row, max_length)
            batch = {key: value.to("cuda:0") for key, value in collate(tokenizer, [encoded]).items()}
            loss = float(model(**batch).loss)
            losses.append(loss)
            ids = torch.tensor([prompt_ids(tokenizer, row["messages"][:-1])], device="cuda:0")
            tick = time.perf_counter()
            generated = model.generate(input_ids=ids, attention_mask=torch.ones_like(ids), max_new_tokens=generation_limit,
                do_sample=False, pad_token_id=tokenizer.pad_token_id, eos_token_id=tokenizer.eos_token_id,
                repetition_penalty=1.05)
            answer = tokenizer.decode(generated[0][ids.shape[-1]:], skip_special_tokens=True).strip()
            source_ids = row["source_ids"]
            citations = re.findall(r"\[([a-zA-Z0-9_-]+)\]", answer)
            headings = ("要点", "注意", "来源") if row["language"] == "zh" else ("Key points", "Caveat", "Source")
            # Diagnostic anchors only: finding words/numbers does not prove the
            # relationship between them is true. Raw answers must be reviewed.
            anchors = {
                "deposit-us": [(r"250[,，]?000|25\s*万",), (r"FDIC",), (r"ownership|所有权|类别",), (r"per depositor|每位存款人|每个存款人",)],
                "deposit-hk": [(r"800[,，]?000|80\s*万",), (r"Hong Kong|香港",), (r"member|成员",), (r"eligible|资格",)],
                "financial-statements": [(r"balance sheet|资产负债表",), (r"income statement|利润表",), (r"cash.flow|现金流",), (r"period|期间|时点",)],
            }[row["group"]]
            anchor_fraction = sum(any(re.search(pattern, answer, re.I) for pattern in group) for group in anchors)/len(anchors)
            outputs.append({"id": row["id"], "group": row["group"], "language": row["language"], "question": row["messages"][1]["content"],
                "answer": answer, "reference_answer": row["messages"][-1]["content"], "assistant_loss": loss,
                "latency_ms": round((time.perf_counter()-tick)*1000, 2), "generated_tokens": int(generated.shape[-1]-ids.shape[-1]),
                "terminated_with_eos": bool(generated[0][-1].item() == tokenizer.eos_token_id),
                "expected_citation_present": all(sid in citations for sid in source_ids),
                "reference_answer_exact_match": answer == row["messages"][-1]["content"],
                "reference_anchor_coverage": anchor_fraction,
                "manual_source_faithfulness_review_required": True,
                "no_unknown_citation_ids": all(sid in source_ids for sid in citations),
                "three_section_format": all(heading.lower() in answer.lower() for heading in headings),
                "educational_disclaimer_present": bool(re.search("仅供金融教育|financial education|not personal investment advice|不构成.*建议", answer, re.I))})
    count = len(outputs)
    return {"mean_assistant_example_loss": sum(losses)/len(losses), "mean_reference_anchor_coverage": sum(o["reference_anchor_coverage"] for o in outputs)/count,
            "reference_answer_exact_match_rate": sum(o["reference_answer_exact_match"] for o in outputs)/count,
            "metrics": {key+"_rate": sum(bool(o[key]) for o in outputs)/count for key in (
                "expected_citation_present", "no_unknown_citation_ids", "three_section_format", "educational_disclaimer_present", "terminated_with_eos")},
            "outputs": outputs}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", type=Path, default=ROOT / "models" / "finpilot-lora")
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--max-new-tokens", type=int, default=384)
    args = parser.parse_args()
    manifest = json.loads((args.adapter / "training_manifest.json").read_text(encoding="utf-8"))
    adapter_hash = hashlib.sha256((args.adapter / "adapter_model.safetensors").read_bytes()).hexdigest()
    assert manifest["trained"] and manifest["steps"] > 0 and adapter_hash == manifest["adapter_sha256"]
    torch.manual_seed(42)
    torch.set_num_threads(4)
    model, tokenizer = load_base(local_files_only=True)
    rows = read_rows(ROOT / "finetuning" / "data" / "test.jsonl")
    print(json.dumps({"status": "evaluating_base", "test_examples": len(rows)}), flush=True)
    baseline = evaluate(model, tokenizer, rows, args.max_length, args.max_new_tokens)
    print(json.dumps({"status": "evaluating_adapter", "base_loss": baseline["mean_assistant_example_loss"]}), flush=True)
    adapted = PeftModel.from_pretrained(model, str(args.adapter), is_trainable=False)
    finetuned = evaluate(adapted, tokenizer, rows, args.max_length, args.max_new_tokens)
    report = {"evaluated_at": datetime.now(timezone.utc).isoformat(), "base_model_id": BASE_MODEL_ID, "base_revision": BASE_REVISION,
        "adapter_sha256": adapter_hash, "test_examples": len(rows), "held_out_topic_groups": sorted({row["group"] for row in rows}),
        "generation": {"do_sample": False, "max_new_tokens": args.max_new_tokens, "repetition_penalty": 1.05, "enable_thinking": False},
        "baseline": baseline, "finetuned": finetuned,
        "limits": "Only 12 author-curated prompts from 3 held-out corpus topics; same templates occur in training. Loss is mean per-example assistant-token cross entropy. Behaviour regex metrics and factual anchor coverage are narrow diagnostics, not factual accuracy, semantic entailment or safety guarantees. Both variants receive identical supplied evidence. Raw output source-faithfulness review is still required. This is not a DeepSeek comparison."}
    path = ROOT / "reports" / "finetuning_evaluation.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "completed", "baseline_loss": baseline["mean_assistant_example_loss"], "finetuned_loss": finetuned["mean_assistant_example_loss"],
                      "baseline_metrics": baseline["metrics"], "finetuned_metrics": finetuned["metrics"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
