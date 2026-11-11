> Version note: this script and the original 8-slide PPTX describe the v1 baseline (45 server tests / 48 retrieval cases / 13 browser flows). For the v2 Avatar, local LoRA, and interface upgrade, use demo_upgrade_en.md and read the current validation reports.

# FinPilot v1 baseline - seven-minute English demonstration

Target length: 6 minutes 40 seconds, leaving a small buffer. Read the validation results from the actual reports; do not invent scores or user feedback.

## 0:00-0:40 | Problem and scope

“FinPilot is a finance education chatbot. Our target user is a student who wants to understand financial concepts and calculate simple planning scenarios. The system combines a bilingual chat interface, a local knowledge base, DeepSeek, and deterministic calculators. It does not provide live market prices or execute trades.”

Show the initial screen. Point out the current mode indicator, example prompts and navigation.

## 0:40-1:50 | Knowledge and traceability

Ask: “分散投资能保证不亏损吗？”

“The assistant explains that diversification can reduce concentration risk, but cannot guarantee a profit or remove all market risk. Below the answer are the retrieved sources. Users can open them and check the original information. These cards show retrieved evidence; they are not a guarantee that every generated sentence is correct.”

Open one relevant source. Explain that the knowledge base contains curated summaries of primary educational sources, rather than live financial news.

## 1:50-2:40 | Bilingual conversation

Switch to English and ask: “Why do bond prices usually fall when interest rates rise?”

“The system supports English and Chinese. We use bilingual knowledge and keyword matching to retrieve context. This is a lightweight local retrieval system. We did not fine-tune a model or deploy a vector database.”

Wait for the answer and identify the actual mode shown on screen. If offline, say so clearly.

## 2:40-3:50 | Financial calculation

Open compound interest. Set principal to 10,000, annual rate to 5%, years to 10 and monthly contribution to 500.

“This is a scenario, not a return forecast. The annual rate is nominal and compounded monthly. Contributions are made at the end of each month. The calculation is implemented in deterministic decimal arithmetic, so we do not rely on an LLM to calculate money. The formula and assumptions are visible.”

Change the rate to zero and explain the boundary case: final value equals starting principal plus total contributions. Briefly open the loan tool and show fixed-rate monthly payments. Mention that taxes, fees and changing rates are excluded.

## 3:50-4:35 | Persistence and usability

Create a second session, return to the first session, and export it.

“Sessions are stored in local SQLite. A user can resume or delete a conversation and export the messages with source references. This version is intended for a local classroom demo; it does not yet provide authenticated multi-user isolation.”

If the browser supports speech, show the microphone and read-aloud controls. If microphone permission is not available, explain the detected limitation and continue with typed input. Do not claim a successful recording without performing one.

## 4:35-5:30 | Architecture and reliability

“The frontend communicates with our FastAPI backend. The backend validates the request, routes calculations to dedicated functions, retrieves knowledge for questions, and calls DeepSeek when available. The API key remains on the server. If the provider is unavailable, the answer is explicitly labelled offline. A configured key is not the same as a verified successful API call.”

Show the technical architecture figure or API documentation. Describe prompt injection as a limitation requiring layered controls, rather than claiming a complete solution.

## 5:30-6:15 | Evaluation

Show the actual test report and `reports/evaluation.json`.

“We tested the calculation formulas and edge cases, API validation, session operations, and knowledge retrieval. The retrieval metrics are Recall at three and mean reciprocal rank. They measure the retriever on our fixed question set, not the complete accuracy of model-generated financial advice. Our test set was built during development, so an independent test set is still needed.”

“In this run, 45 server-side tests passed. All 48 fixed retrieval acceptance cases passed, with mean Recall at three and MRR at three of 1.00. We also verified the live DeepSeek connection. During manual review, we found a generated APY explanation with the error direction reversed, corrected the grounding and prompt, and passed a targeted live regression. This is why response-mode checks do not measure factual accuracy.”

Separate the live DeepSeek smoke result from offline test results. Browser interaction checks cover 13 scenarios; actual microphone recording still needs testing on the presentation machine.

## 6:15-6:40 | Limits and next steps

“The main limitations are a static knowledge base, lexical retrieval, variable cloud latency, browser-dependent speech, and the absence of live market data. Our next steps would be an independent evaluation set, stronger answer-to-source checks, and authenticated user isolation. FinPilot demonstrates a complete finance education workflow with traceable information and reproducible calculations.”

## Likely questions

**Why use lexical retrieval?** It is easy to inspect and reproduce for a small curated bilingual corpus. We would compare it with vector or hybrid retrieval using independent evaluation before increasing complexity.

**Did you fine-tune DeepSeek?** No. We integrate the official API and supply retrieved context through prompting.

**How do you avoid hallucinations?** We provide curated context, show references, constrain the task and separate arithmetic. These reduce risk, but do not eliminate hallucinations.

**Why is this a finance project rather than a generic chatbot?** The domain knowledge, jurisdiction caveats, calculation assumptions, risk explanations and source links are specific to financial education.

**Does offline mode use an LLM?** No. It is a clearly labelled local fallback using the curated knowledge. The mode indicator prevents it from being confused with a cloud response.

**Can the demo be deployed publicly?** Not as-is. It needs authentication, data isolation, HTTPS, rate limits and operational controls first.
