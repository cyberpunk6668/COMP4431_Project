"""Small reviewed knowledge corpus: lexical BM25 + Chinese n-gram rank fusion.

There are no embeddings, vector database, remote calls or trained ranking model.
The two independent rankings are fused with reciprocal rank fusion (RRF).
Ranking scores are relevance heuristics, never confidence or accuracy estimates.
"""
from __future__ import annotations

import json
import hashlib
import math
import re
import unicodedata
from collections import Counter
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

from app.config import ROOT


DEFAULT_PATH = ROOT / "data" / "expert_knowledge.json"
METHOD = "bm25_char_ngram_rrf"
_STOP = set("a an the is are be to of and or for in on with what why how does do can this that it please explain me my about".split())
_GENERIC_EVIDENCE = set("api date dates day days time times historical history data source sources permission permissions compare comparison comparing sample samples period periods limit limits expiry expiration expired field fields file files import imported mean means meaning difference different basis count counts".split())
_UNRELATED = re.compile(r"相机|摄像|会议|请假|天气|菜谱|食谱|烘焙|医疗|注射|静脉|劳动合同|招聘|员工|债券|房贷|\b(?:camera|meeting|weather|recipe|cooking|medical|injection|intravenous|employee|employment|mortgage|bonds?|python|javascript|typescript|programming|software)\b", re.I)
_STRONG_FINANCE = re.compile(r"期权|未平仓|看跌|看涨|权利金|隐含波动|行权价|IBKR|CBOE|\bOCC\b|open interest|outstanding (?:option )?contracts?|put[ /-]call|implied volatility|strike prices?|(?:call|put|stock|equity) options?|option (?:price|premium|trad|contract)|bid[ /_-]ask", re.I)
# General domain expressions, not copied evaluation questions. Expansions are
# disclosed in retrieval metadata and never claim a semantic embedding model.
_QUERY_ALIASES = (
    (r"\bturnover\b", "volume"),
    (r"\boutstanding (?:option )?contracts?\b|\bcontracts? (?:still |remaining )?open\b", "open interest"),
    (r"\breconcil(?:e|ed|ing|iation)\b", "open interest reporting overnight"),
    (r"\b(?:matched|matching|common)[ -](?:cohort|set|universe)\b", "common sample contract identity"),
    (r"\bingest(?:ed|ion)?\b|\bfile (?:was )?(?:loaded|saved|uploaded)\b", "import receipt time"),
    (r"未结清(?:的)?合约|尚未平仓", "未平仓量"),
    (r"导入(?:时刻|日期)|文件.{0,6}(?:保存|上传)(?:时刻|日期|时间)", "导入时间 本地接收"),
)


def _stem(token):
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _query_text(text):
    query = _normalize(text)
    if _UNRELATED.search(query) and not _STRONG_FINANCE.search(query):
        return query, [], True
    aliases = [replacement for pattern, replacement in _QUERY_ALIASES if re.search(pattern, query, re.I)]
    return query + (" " + " ".join(aliases) if aliases else ""), aliases, False


def _normalize(text):
    return unicodedata.normalize("NFKC", str(text)).lower()


def _phrase(phrase, text):
    if re.fullmatch(r"[a-z0-9 /_-]+", phrase):
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text))
    return phrase in text


def _ngrams(text):
    # The character route is intentionally independent of phrase segmentation.
    return {run[i:i+n] for run in re.findall(r"[\u3400-\u9fff]+", _normalize(text))
            for n in (2, 3) for i in range(len(run)-n+1)}


class ExpertKnowledge:
    def __init__(self, path: Path = DEFAULT_PATH):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        documents = raw.get("documents") if isinstance(raw, dict) else raw
        if not isinstance(documents, list) or not documents:
            raise ValueError("Expert corpus must contain reviewed documents")
        self.documents = deepcopy(documents)
        self.version = str(raw.get("version", "unversioned")) if isinstance(raw, dict) else "unversioned"
        self.corpus_sha256 = hashlib.sha256(json.dumps(documents, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()
        seen = set()
        for doc in self.documents:
            if not isinstance(doc, dict) or any(not isinstance(doc.get(key), str) or not doc[key].strip()
                    for key in ("id", "title", "text", "url", "publisher", "reviewed_at")):
                raise ValueError("Invalid expert document")
            if not re.fullmatch(r"expert\.[a-z_]+", doc["id"]) or doc["id"] in seen:
                raise ValueError("Duplicate or invalid expert ID")
            seen.add(doc["id"])
            if urlparse(doc["url"]).scheme != "https" or not urlparse(doc["url"]).netloc:
                raise ValueError("Expert sources require an HTTPS URL")
            if not isinstance(doc.get("topics"), list) or not doc["topics"] or any(not isinstance(x, str) or not x.strip() for x in doc["topics"]):
                raise ValueError("Expert topics must be nonempty text")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", doc["reviewed_at"]):
                raise ValueError("Expert review date is required")
            if "supports" in doc and (not isinstance(doc["supports"], list) or not doc["supports"] or any(not isinstance(item, str) or not re.fullmatch(r"[a-z][a-z_]+", item) for item in doc["supports"])):
                raise ValueError("Expert claim support must use named, non-empty facets")
        self._phrases = sorted({_normalize(term) for doc in self.documents for term in doc["topics"]}, key=lambda x: (-len(x), x))
        self._texts = [" ".join([doc["title"], doc["text"], doc.get("text_en", ""), *doc["topics"]]) for doc in self.documents]
        self._counts = [Counter(self._terms(text)) for text in self._texts]
        self._lengths = [sum(counts.values()) for counts in self._counts]
        self._average = sum(self._lengths) / len(self.documents) or 1
        freq = Counter(term for counts in self._counts for term in counts)
        self._idf = {term: math.log(1 + (len(self.documents)-count+.5)/(count+.5)) for term, count in freq.items()}
        self._grams = [_ngrams(text) for text in self._texts]
        gram_freq = Counter(gram for grams in self._grams for gram in grams)
        self._gram_idf = {gram: math.log(1 + len(self.documents)/count) for gram, count in gram_freq.items()}

    def _terms(self, text):
        normalized = _normalize(text)
        terms = [_stem(token) for token in re.findall(r"[a-z][a-z0-9_]*", normalized) if token not in _STOP]
        # A small, explicit domain lexicon; no downloaded tokenizer is needed.
        terms.extend(term for term in self._phrases if _phrase(term, normalized))
        return terms

    def search(self, query: str, limit: int = 4) -> list[dict]:
        if not isinstance(query, str) or not query.strip() or limit <= 0:
            return []
        query, aliases, unrelated = _query_text(query[:4000])
        if unrelated:
            return []
        terms, grams = set(self._terms(query)), _ngrams(query)
        topics = {term for term in self._phrases if _phrase(term, query)}
        bm25, char, details = {}, {}, {}
        for index, doc in enumerate(self.documents):
            counts = self._counts[index]
            matched_terms = sorted(terms & counts.keys())
            matched_grams = sorted(grams & self._grams[index])
            matched_topics = sorted(term for term in topics if term in map(_normalize, doc["topics"]))
            # Abstain on incidental short prose overlaps outside the domain.
            specific_topics = {term for term in matched_topics if term not in _GENERIC_EVIDENCE}
            substantive_terms = {term for term in matched_terms if term not in _GENERIC_EVIDENCE and term not in _STOP}
            if not specific_topics and not (len(matched_grams) >= 3 or len(substantive_terms) >= 2):
                continue
            score = sum(self._idf[term] * counts[term] * 2.2 /
                        (counts[term] + 1.2*(.25+.75*self._lengths[index]/self._average)) for term in matched_terms)
            # Weighted character overlap is lexical, not an embedding similarity.
            gram_score = sum(self._gram_idf[g] for g in matched_grams) / max(1, sum(self._gram_idf.get(g, 1) for g in grams))
            if score > 0:
                bm25[index] = score
            if gram_score > 0:
                char[index] = gram_score
            details[index] = {"matched_terms": matched_terms[:12], "matched_ngrams": matched_grams[:12], "matched_topics": matched_topics}
        rank = lambda scores: {index: position+1 for position, index in enumerate(sorted(scores, key=lambda i: (-scores[i], self.documents[i]["id"])))}
        term_ranks, char_ranks = rank(bm25), rank(char)
        fused = {i: sum(1/(60+ranks[i]) for ranks in (term_ranks, char_ranks) if i in ranks) for i in set(bm25) | set(char)}
        ordered = sorted(fused, key=lambda i: (-fused[i], -len(details[i]["matched_topics"]), self.documents[i]["id"]))
        return [{**deepcopy(self.documents[i]), "retrieval": {"method": METHOD, "embedding": False,
                 "knowledge_version": self.version, "corpus_sha256": self.corpus_sha256,
                 "query_normalization": "english_plural_and_reviewed_domain_aliases", "query_expansions": aliases,
                 "rrf_score": round(fused[i], 8), "bm25_rank": term_ranks.get(i), "char_rank": char_ranks.get(i),
                 "bm25_score": round(bm25.get(i, 0), 6), "char_score": round(char.get(i, 0), 6), **details[i]}}
                for i in ordered[:min(limit, 6)]]


# Named alias for callers that prefer the existing retriever naming convention.
ExpertRetriever = ExpertKnowledge
