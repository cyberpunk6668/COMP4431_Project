"""Small, auditable bilingual lexical retriever. No network or embedding service.

BM25 ranks original bilingual summaries. Explicit vocabulary aliases bridge the
two languages; an alias is a relevance feature, never a command or a response.
This is retrieval augmentation, not model fine-tuning or a vector database.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path


_STOP = frozenset("a an and are as at be by can could did do does for from how i in into is it me my of on or please should tell than that the their there these they this to us was what when where which why will with would you your explain about give want need know if all not now any have has its".split())


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).lower()


def _tokens(value: str) -> list[str]:
    value = _normalize(value)
    result = []
    for token in re.findall(r"[a-z][a-z0-9]*(?:'[a-z]+)?", value):
        if token in _STOP:
            continue
        # Deliberately modest morphology; finance terminology often has acronyms.
        if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        result.append(token)
    for run in re.findall(r"[\u3400-\u9fff]+", value):
        # Character bigrams handle Chinese without a downloaded tokenizer/model.
        result.extend(run[i:i+2] for i in range(len(run)-1))
    return result


def _phrase_in(phrase: str, query: str) -> bool:
    phrase = _normalize(phrase)
    if re.fullmatch(r"[a-z0-9 ./'-]+", phrase):
        # Avoid interpreting 'apr' in 'apricot' or 'loan' in 'loanword'.
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", query))
    return phrase in query


class KnowledgeRetriever:
    """Load trusted local documents once, return at most ``limit`` matches.

    Results contain the source URL, original text, selected-language snippet and
    a ranking score. Scores are NOT probabilities or calibrated confidence.
    """

    def __init__(self, path: Path):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self.documents = raw["documents"] if isinstance(raw, dict) else raw
        if not isinstance(self.documents, list) or not self.documents:
            raise ValueError("Knowledge base must contain documents")
        ids = [d["id"] for d in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate knowledge document IDs")
        self._counts = []
        self._lengths = []
        frequency: Counter[str] = Counter()
        for doc in self.documents:
            for required in ("id", "title", "url", "text", "keywords", "updated_at"):
                if required not in doc:
                    raise ValueError(f"Missing knowledge field: {required}")
            counts = Counter(_tokens(doc["title"] + " " + doc["text"] + " " + " ".join(doc["keywords"])))
            self._counts.append(counts)
            self._lengths.append(sum(counts.values()))
            frequency.update(counts.keys())
        self._average_length = sum(self._lengths) / len(self.documents)
        n = len(self.documents)
        self._idf = {word: math.log(1 + (n-count+0.5)/(count+0.5)) for word, count in frequency.items()}

    def search(self, query: str, limit: int = 3) -> list[dict]:
        if not isinstance(query, str) or not query.strip() or limit <= 0:
            return []
        query = _normalize(query[:8000])
        tokens = set(_tokens(query))
        # Require a recognized topic phrase. Common prose overlaps alone are
        # insufficient evidence that a cooking/weather query is financial.
        hits = [[term for term in d["keywords"] if _phrase_in(term, query)] for d in self.documents]
        if not any(hits):
            return []
        matches = []
        for index, doc in enumerate(self.documents):
            counts = self._counts[index]
            score = 0.0
            for token in tokens:
                tf = counts.get(token, 0)
                if tf:
                    norm = 1.2 * (1 - 0.75 + 0.75*self._lengths[index]/self._average_length)
                    score += self._idf[token] * tf * 2.2 / (tf + norm)
            if hits[index]:
                # Long precise phrases outrank generic overlapping text.
                score += 7 + min(12, sum(min(len(term), 12)/4 for term in hits[index]))
            # A candidate needs its own alias; do not pad results with unrelated
            # documents merely to return three citations.
            if not hits[index]:
                continue
            text = doc["text_zh"] if re.search(r"[\u3400-\u9fff]", query) else doc["text_en"]
            matches.append({"id": doc["id"], "title": doc["title"], "url": doc["url"],
                            "category": doc.get("category", "education"), "updated_at": doc["updated_at"],
                            "snippet": text, "text": doc["text"], "score": round(score, 4)})
        matches.sort(key=lambda d: (-d["score"], d["id"]))
        return matches[:min(int(limit), 10)]
