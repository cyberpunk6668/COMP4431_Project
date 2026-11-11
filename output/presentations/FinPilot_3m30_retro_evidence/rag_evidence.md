# RAG implementation evidence

Read-only extraction from the current working tree. Source files were not changed. Code blocks below are contiguous verbatim extracts, not pseudocode.

## Two lexical scores, one fused ranking

Source: `app/expert_knowledge.py:135-146`. 12 contiguous original lines.

BM25 term scoring and weighted Chinese character overlap are ranked separately, then combined by reciprocal rank fusion.

```python
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
```

Source SHA256: `0c2d328de53f2e8b2132b60397e6b377663c0d5af57e0cf4f05ba28e9e1d07a4`

## Reject sources that do not support the recognized topic

Source: `app/expert_grounding.py:205-214`. 10 contiguous original lines.

Each paragraph cites only supplied source IDs. Its recognized claim facets must be covered by the cited sources.

```python
        cited = [key for key in part.get("evidence_ids", []) if str(key).startswith("expert.")]
        if any(key not in sources for key in cited):
            raise ValueError(where + "Expert citation was not in the retrieved context")
        if any(key not in sources and key not in local_ids for key in part.get("evidence_ids", [])):
            raise ValueError(where + "Unknown local or expert reference")
        support = {facet for key in cited for facet in sources[key].get("supports", []) if facet in SUPPORT_FACETS}
        missing = facets - support
        if missing:
            raise ValueError(where + "Expert citation does not support claim facets: " + ",".join(sorted(missing)))
        unrelated = [key for key in cited if not set(sources[key].get("supports", [])) & facets]
```

Source SHA256: `f3f2509ea5282b050c9b2deeaba2f7ca0260cbd3927862290c072f4f3823a008`

## One initial answer, at most one repair

Source: `app/history_chat.py:320-325`. 6 contiguous original lines.

range(2) bounds the initial generation plus one possible repair; the deadline bounds total answer time.

```python
                async with asyncio.timeout(ANSWER_DEADLINE_SECONDS):
                    for attempt in range(2):
                        attempts += 1
                        repairs += bool(attempt)
                        try:
                            content = await self.local_provider.complete(messages) if engine == "local" else await self.cloud.complete(messages, json_output=True)
```

Source SHA256: `4777a2d615176774c060a0a93ae41ba9c9764f197d08f19bc115b9ab86dc5af6`

## Report evidence

**Held-out retrieval Recall@4: 87.04%.**

- 24 questions: 18 relevant, 6 irrelevant; 14 reviewed documents.
- Relevant queries only. Same-team manual labels, small convenience sample.
- Measures raw retrieval, not answer accuracy, citation entailment or market prediction.
- Source: `reports/expert_retrieval_holdout_v14.json:41-62`.
- Current retriever file SHA256 matches the evaluated retriever: **True**.

Suggested exact English slide caption: **87.04% Recall@4 on 18 relevant held-out queries**.

Required nearby scope note: **24 questions total. Same-team labels. Retrieval only.**

## Fit and provenance notes

- Prefer two main code extracts: retrieval (12 lines), grounding (10 lines). The optional repair extract is a separate six-line proof if space permits; do not splice it onto the grounding code block.
- The retrieval block includes long expressions. Use a full-width code panel or an evidence appendix rather than shrinking it into an unreadable small side card.
- The retrieval code is unchanged relative to the recorded v14 hash. Grounding logic remains topic-rule checking, with current working-tree additions for recognizing historical/OI/time wording. It is still explicitly not a general entailment checker.
- The current grounding file contains extra functions for repair guidance and claim-topic preservation; original topic-check line range 205-214 remains valid in this snapshot.
- No external model or broker request was made for this extraction.
