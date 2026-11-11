# FinPilot · English presenter notes

## Slide 1: FinPilot: Financial answers with evidence

Hello everyone. Our project is FinPilot, a bilingual chatbot for financial education. Users can learn financial concepts, run planning calculations, use browser-supported voice, and discuss saved market reports with visible evidence. We focused on three connected features: RAG for traceable explanations, a clear frontend, and an interactive companion on the web and desktop. Local functions handle the numbers, while the language model explains the results. Let us start with the RAG pipeline.

## Slide 2: RAG connects data with expert knowledge

Our RAG pipeline combines two kinds of evidence. Saved analyses provide numerical values, timestamps, and data limitations. Fourteen reviewed expert knowledge blocks provide financial concepts. We retrieve them using BM25 and Chinese character n-grams, then combine both rankings through reciprocal rank fusion, or RRF. DeepSeek receives both inputs, and the answer keeps local references separate from expert citations.

## Slide 3: Reliable grounding needs more than retrieval

The first challenge is bilingual wording. Domain aliases and two retrieval routes help reduce missed sources. The second is unsupported claims. We check citations against recognized topics and allow one repair. Missing values stay missing. These rules improve traceability, but cannot guarantee correctness. Next, we will show how the frontend presents this clearly.

## Slide 4: Frontend design keeps complex tasks usable

The frontend must keep financial answers, tools, and the assistant usable together. Our React homepage introduces the product, while the JavaScript workspace handles real tasks. First, we manage information density: desktop columns become drawers and a collapsible assistant on mobile. Second, animations need reliable fallbacks. The homepage uses GSAP and Motion, with a static poster if video fails, and respects reduced motion. Third, asynchronous requests can arrive out of order. Request IDs or cancellation prevent old calculations from replacing new input, and failed chats keep the draft. These choices make the interface clearer and easier to recover. Next is our companion.

## Slide 5: One companion, on the web and desktop

Our companion uses multi-frame WebP atlases rendered by Canvas2D. The web page and Electron desktop app share this renderer, and its listening, thinking, and speaking states follow actual operations. Animation cost is one challenge, so we load assets on demand, pause hidden animation, and provide a static fallback. Transparent windows add another challenge: we use alpha-based hit regions, drag handling, and panel placement near screen edges.

## Slide 6: Shared conversation, explicit control

Both interfaces share an explicitly selected conversation. The server saves messages, sends an SSE notification, and clients reload the record. We ignore responses from older connections, keeping the same evidence and limitations accessible.

