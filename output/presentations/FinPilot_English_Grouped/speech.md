# FinPilot - English presenter notes

## Slide 1: FinPilot

Hello everyone. Our project is FinPilot, a bilingual chatbot for financial education. We focused on three connected features: RAG for traceable explanations, a clear frontend, and an interactive companion on the web and desktop.

## Slide 2: The actual English workspace

This is the actual English workspace. Users can learn financial concepts, run planning calculations, and use browser-supported voice. Local functions handle the numbers, while the language model explains the results. Let us start with the RAG pipeline.

## Slide 3: RAG connects data with expert knowledge

Our RAG pipeline combines local evidence with reviewed expert knowledge. Saved analyses provide values, timestamps, and data limitations. Fourteen expert knowledge blocks explain financial concepts. The answer keeps local references separate from expert citations.

## Slide 4: Two routes, one ranking

We use BM25 and Chinese character n-grams, then combine their rankings with RRF. The colored code shows this step. The small held-out evaluation measures retrieval, rather than answer accuracy.

## Slide 5: Reliable grounding needs more than retrieval

Two challenges are bilingual wording and unsupported claims. Domain aliases improve matching. Topic-aware citation checks reject sources that fail to support a recognized claim.

## Slide 6: Missing values remain unavailable

Here, missing open interest remains null. It never becomes zero. We allow one repair, but these checks cannot guarantee correctness. Next is the frontend.

## Slide 7: Frontend design keeps complex tasks usable

Our React homepage introduces the product, while the JavaScript workspace handles real tasks. We designed the interface around readable information, resilient motion, and safe asynchronous updates.

## Slide 8: Real English views, responsive controls

These are actual English calculator forms. On narrow screens, headings and controls adapt to the available space. Request IDs prevent old calculation responses from replacing newer input.

## Slide 9: Motion with a safe fallback

Animations also need a reliable fallback. This code keeps a poster behind the video and falls back after two point five seconds. Users can reduce motion. These choices keep the interface usable. Next, we explain our companion.

## Slide 10: One companion, on the web and desktop

Our companion uses Canvas2D and WebP atlases. Its states follow user actions. Transparent windows need alpha-based hit regions, dragging, and panel placement.

## Slide 11: One shared 2D renderer

The English browser companion and Electron app share this renderer. Frame bounds, lazy loading, visibility pause, and static fallback manage animation cost.

## Slide 12: Shared conversation, explicit control

Users explicitly select a conversation. The server saves messages, sends an SSE notification, and clients reload the record.

## Slide 13: Guard stale responses, preserve the evidence

This guard rejects stale responses. The saved cloud run passed two turns, with physical input limits. The conversation keeps the same evidence.

