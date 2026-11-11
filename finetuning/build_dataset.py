"""Create auditable, author-curated examples from the local public-source corpus.

Topic groups, not random rows, determine train/validation/test splits. Held-out
topics never enter training. This is a small behaviour/style adaptation dataset,
not evidence of broad financial expertise or independent user testing.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.local_prompt import LOCAL_SYSTEM as SYSTEM

SPLITS = {
    "train": ["diversification", "risk-tolerance", "compound-interest", "loan-amortization", "budgeting", "emergency-fund", "inflation", "investment-fees", "bond-rate-risk", "phishing", "credit-score", "stock-basics"],
    "validation": ["effective-yield", "etf-basics", "financial-ratios"],
    "test": ["deposit-us", "deposit-hk", "financial-statements"],
}
PROMPTS = {
    "zh": ["请解释{topic}，并说明主要限制。", "我是金融初学者，如何理解{topic}？", "用通俗的话介绍{topic}，有哪些注意事项？", "请根据给定资料解释{topic}并列出来源。", "理解{topic}时最容易遗漏什么风险？", "请给我一段关于{topic}的金融教育说明。"],
    "en": ["Explain {topic} and its main limitations.", "I am new to finance. How should I understand {topic}?", "Describe {topic} in plain language, including a caveat.", "Using the reference, explain {topic} and cite the source.", "What risk is easy to overlook when learning about {topic}?", "Give me an educational explanation of {topic}."],
}
CAVEATS = {
    "zh": "适用范围、地区和产品条款可能不同，请打开官方来源核实；这不是收益承诺。",
    "en": "Scope, jurisdiction and product terms can differ. Check the official source; this is not a promise of returns.",
}


def build():
    corpus_path = ROOT / "data" / "knowledge.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    documents = {d["id"]: d for d in corpus["documents"]}
    groups = [g for ids in SPLITS.values() for g in ids]
    assert len(set(groups)) == len(groups) == len(documents), "Every topic must have exactly one split"
    manifest = {"provenance": "Project-authored prompts and reference-based target answers; no user conversations or external teacher API outputs.",
                "corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
                "split_strategy": "18 disjoint knowledge topic groups: 12 train, 3 validation, 3 test. Both languages of one topic stay in one split.",
                "limitations": "Small author-curated experiment. Held-out topics still come from the same public knowledge corpus; not an independent finance benchmark.", "splits": {}}
    folder = ROOT / "finetuning" / "data"
    folder.mkdir(parents=True, exist_ok=True)
    for split, ids in SPLITS.items():
        rows = []
        for did in ids:
            doc = documents[did]
            for lang in ("zh", "en"):
                title_parts = doc["title"].split(" / ", 1)
                topic = title_parts[0] if lang == "zh" else title_parts[-1]
                text = doc["text_zh"] if lang == "zh" else doc["text_en"]
                templates = PROMPTS[lang] if split == "train" else PROMPTS[lang][:2]
                for template_index, template in enumerate(templates):
                    question = template.format(topic=topic)
                    system = SYSTEM + f"\nRequested language: {lang}\nReference DATA:\n[{did}] {text}"
                    if lang == "zh":
                        target = f"要点：{text}\n\n注意：{CAVEATS[lang]}\n\n来源：[{did}]\n仅供金融教育，不构成个人投资建议。"
                    else:
                        target = f"Key points: {text}\n\nCaveat: {CAVEATS[lang]}\n\nSource: [{did}]\nFor financial education, not personal investment advice."
                    rows.append({"id": f"{split}-{did}-{lang}-{template_index}", "group": did, "language": lang,
                                 "template_id": template_index, "source_ids": [did],
                                 "messages": [{"role": "system", "content": system}, {"role": "user", "content": question}, {"role": "assistant", "content": target}]})
        path = folder / f"{split}.jsonl"
        path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
        manifest["splits"][split] = {"examples": len(rows), "groups": ids, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=True, indent=2))
    return manifest


if __name__ == "__main__":
    build()
