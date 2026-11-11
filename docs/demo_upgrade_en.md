# FinPilot v2 - additional-feature demonstration

Target length: about 6 minutes 40 seconds. This script covers the new Avatar, local LoRA experiment, and interface. Use FinPilot_Demo_EN_v2.pptx with the live v2 workspace and current reports. The original FinPilot_Demo_EN.pptx and demo_script_en.md describe the v1 baseline; do not silently relabel their old numbers.

## Before the presentation

Start the local web service, confirm the model selector, and open the current validation reports. If the local adapter is ready, warm it up with one synthetic finance question; otherwise describe it as unavailable and show the training evidence rather than pretending that an offline extract is model generation. Check microphone permissions and audible speech on the actual presentation machine. These hardware checks are not replaced by automated event tests.

Use only synthetic financial inputs. Keep configuration files and API credentials off screen. The 3D character, 2D fallback, and theme controls need no external avatar service.

## 0:00-0:45 | The reason for the upgrade

“Our first version already combined finance questions, traceable references, and deterministic calculators. Version two adds three concrete contributions: an interactive 2D/3D mentor, a reproducible small-model LoRA experiment, and a clearer interface for reading and checking evidence. The contribution is the working integration and its evaluation, rather than claiming a new foundation-model algorithm.”

Show the initial workspace and identify the original robot character.

## 0:45-1:45 | Genuine 3D and graceful fallback

Switch between 3D and 2D. Point out the renderer indicator.

“The 3D version is generated from actual meshes, materials, lighting, and a camera using Three.js. It is not a video or a rotated flat picture. The 2D version is an original local SVG of the same character. If WebGL2 is unavailable, the system uses that fallback while keeping chat and the tools available.”

Turn on reduced motion.

“The rendering loop pauses when reduced motion is selected or the avatar is hidden. The state label remains readable. We also release the rendering resources when the component is destroyed.”

## 1:45-2:50 | State, speech, and evidence

Ask: “分散投资为什么不能消除所有风险？” Watch the thinking state while the request is in progress. Once the answer appears, open the source excerpt and follow a matching citation.

“The character's state is driven by the actual interaction. Thinking means that a request is in progress. Listening is driven by the recognition event, and speaking starts when browser speech synthesis actually begins. The mouth motion is a procedural approximation; we do not claim phoneme-level lip synchronization.”

Start read-aloud only if audible synthesis has been checked. Let it speak for only a few seconds, point out the speaking state, and click the same read control to stop. Reading an entire long answer would consume too much of the seven-minute slot. Otherwise explain that the presentation machine has no working voice and continue with the text answer. Do not simulate a successful microphone recording.

## 2:50-4:15 | What was actually fine-tuned

Open the model selector and the training manifest or the readable training summary. Show the actual adapter hash and positive optimizer-step count.

“DeepSeek remains our default cloud model. Separately, we adapt Qwen3-0.6B with PEFT LoRA. The base parameters stay frozen, while low-rank matrices in the attention projections are trained. That is a real parameter update. Our retrieval and system prompts are useful, but they are not themselves fine-tuning.”

“The dataset contains project-authored questions and public-source reference summaries. Its topics are split into training, validation, and test groups so that both languages of a topic stay in one split. The task is to produce a grounded explanation, a caveat, and a valid source. We do not use private financial records.”

Show the same held-out question and supplied evidence before and after the adapter, using reports/finetuning_evaluation.json. Read only the actual achieved numbers. Mention regressions or failed examples as well as improvements. Never claim that Qwen LoRA is a fine-tuned DeepSeek or that it has outperformed DeepSeek.

## 4:15-5:15 | Why the new interface is useful

Toggle the theme and expand a source excerpt. Resize to the prepared mobile layout or open its real screenshot, clearly identifying screenshots as recorded evidence.

“The user can choose a light or dark theme, inspect the source excerpt without losing the conversation, and check the actual model used for each answer. The companion panel can collapse on small screens. Our limited Markdown renderer builds safe DOM structures, so raw model HTML is not executed.”

“These are implemented usability features. We have not conducted a user study, so we do not invent a percentage improvement in productivity or satisfaction.”

## 5:15-6:00 | Preserve the reliable finance tools

Use compound savings: principal 10,000, nominal annual rate 5%, ten years, month-end contribution 500. Confirm the displayed future value of 94,111.23 and its assumptions.

“The avatar and small model do not replace the numerical engine. Money is still computed in deterministic decimal arithmetic. This scenario excludes tax, fees, inflation, and market volatility; it is not a promised investment return.”

## 6:00-6:40 | Evaluation and limits

Read the final v2 test and browser counts from the reports. Identify the eight independent avatar checks separately from browser integration and real voice hardware checks.

“Our retrieval test is a small development acceptance set, and the LoRA test is a narrow topic-held-out, template-based experiment. Citation presence is not proof that every sentence is true. We previously found an APY explanation with the direction reversed, kept the original record, corrected it, and ran a targeted regression. The new features make the workflow more inspectable; they do not remove the need to check important financial claims.”

## Questions to prepare for

- **Why use a small local model?** It lets the team show real, reproducible adaptation within the available GPU resources. The default high-capability cloud service remains available.
- **How is LoRA different from RAG?** LoRA updates a small set of model parameters; RAG supplies relevant evidence at inference. The system uses both for different purposes.
- **Is the animation synchronized with phonemes?** No. It follows the speaking state with approximate mouth motion, and the report explicitly states that boundary.
- **What if the local model or GPU is unavailable?** The system exposes its availability honestly and falls back to curated knowledge extracts. It does not label those extracts as successful local-model generation.
- **Has this been user-tested?** Automated rendering and browser acceptance have been run. A representative user study and actual microphone/voice checks on other devices have not been claimed.
