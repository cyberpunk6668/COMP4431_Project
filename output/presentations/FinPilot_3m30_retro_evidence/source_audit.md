# Technical fact check

Read-only review of the current repository. No live provider or broker calls were made for this presentation review.

## RAG

- `app/expert_knowledge.py:116`: reviewed lexical retrieval with BM25 and Chinese character n-grams; RRF at line 146. The file explicitly excludes embeddings and a vector database.
- `app/expert_grounding.py:147`: question/context support facets supplement relevant knowledge. Paragraph checks begin at line 195.
- `app/history_chat.py:287`: local analysis, expert retrieval and provider context integration. Repair is bounded.
- `reports/expert_retrieval_holdout_v14.json`: 14 documents; 24 held-out questions, including 18 relevant and 6 irrelevant. Recall@4 = 0.870370 over relevant questions. Labels are from the same team; this is not an external answer-accuracy benchmark.

## Frontend

- `frontend/package.json`: React / TypeScript / Vite homepage with GSAP and Motion.
- `web/app.js` and `web/styles.css`: native JavaScript / CSS workspace, responsive navigation and assistant panels.
- `frontend/src/components/Hero.tsx:102`: video readiness, poster fallback, reduced motion.
- `web/app.js:1069`: chat pending controls. Calculator request sequences around line 1155.
- Existing UI reports cover controlled browser checks. They do not prove real speech hardware, all browsers or performance gains.

## Companion

- `web/companion/renderer.js`: Canvas2D, multi-frame WebP atlases, operation-linked states, lazy loading, visibility pause and static fallback.
- `desktop/main.cjs`: Electron transparent window and desktop controls.
- `web/pet.js`: alpha-based hit regions, drag handling and panel placement.
- `web/companion/client.js` and `app/companion.py`: explicitly selected shared session, SSE notifications, authoritative rereads and stale-generation filtering.
- `web/companion/licenses/ATTRIBUTION.md`: character from YunYueSama / 上善无形 / ZipZipPipe; CC BY-NC-SA 4.0 underlying character plus upstream attribution terms. Retain full license files.
- 1.09 MiB describes runtime character images, not the complete Electron application.
- Historical failed attempt: `reports/pet_cloud_v15-20261111T124026586357Z.json`. The newer final `reports/pet_cloud_v15.json` passes both actual DeepSeek turns. `reports/companion_acceptance_v15.json` records 3 generations, 1 repair and 0 new IB requests. Physical pointer/hardware certification remains limited; this deck update did not rerun the tests.
- `reports/native_instrumentation_v15.json`: passed_instrumented with physical_mouse_tested=false. Instrumentation does not prove physical pointer acceptance.

## Presentation language and timing

The course project PDF asks for presentation and live demonstration in English within seven minutes (tentative), plus Q&A. This requested 3:30 deck is the explanation segment. It does not replace the required live demo.

Member names and IDs are not known. Use Speaker 1–4, with no invented identities.
