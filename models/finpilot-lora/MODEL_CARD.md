# FinPilot Finance Behaviour LoRA

## Identity and intended use

This is a real locally trained LoRA adapter for `Qwen/Qwen3-0.6B` at revision `c1899de289a04d12100db370d81485cdf75e47ca`. It is not a fine-tuned DeepSeek model. It is an optional small-model experiment for financial education, paired with trusted local retrieved context and deterministic calculators.

Completed: 2026-11-10T09:45:05.645101+00:00. Optimizer steps: 108; epochs: 3; LoRA rank: 8; trainable parameters: 2,293,760 (0.383352% of the model with adapter). Adapter SHA-256: `5b8b9c5ea3e75d0c86fdc05189b617fcd2f9fb84d7637beffa1a661d68fb9d0a`.

## Training

Targets attention q/k/v/o projections with BF16/FP16 frozen base weights and trainable LoRA updates. Assistant-only cross-entropy loss; prompts and references are masked. Batch size 1; gradient accumulation 4; learning rate 0.0002; maximum sequence 512; thinking disabled. Actual run duration: 181.51 seconds; peak allocated GPU memory: 1912.63 MiB.

Data: 144 project-authored reference-based Chinese/English examples in 12 topic groups; 12 validation examples in 3 different groups; 12 test examples in 3 different groups. No private conversations, credentials, accounts or undisclosed teacher API output. See `finetuning/data/manifest.json` for dataset provenance and hashes.

## Evaluation and limits

The run log is `reports/finetuning_training.json`. The separate base/adapter comparison is `reports/finetuning_evaluation.json` after that script actually executes; do not infer evaluation success from this card. Reference evidence is provided to both variants. Narrow citation/format diagnostics are not financial factual accuracy or production safety. Topics and prompt families are small and author-curated. The model can hallucinate, omit caveats or follow an inappropriate request. There is no demonstrated superiority over DeepSeek. No live prices, trading, personal recommendations or return guarantees are provided.

## License and distribution

The public base model is Apache-2.0; the derived adapter is distributed under Apache-2.0 with its official LICENSE included. The base weights must be obtained separately from the official pinned Qwen repository. The source package contains the adapter, not the approximately 1.5GB base weights or the Python ML environment.

## Recorded comparison on 2026-11-10

The actual 12-prompt, 3-held-out-topic comparison has completed. Base versus adapter: expected source citation 8/12 versus 12/12; three-section format 0/12 versus 12/12; educational disclaimer 0/12 versus 12/12. Mean per-example assistant loss was 1.4411243 versus 0.0042106. All answers in both variants terminated with EOS; no unknown citation IDs were generated.

All 12 adapted outputs exactly reproduce the supplied reference target plus the learned format. This is evidence for conditioned copying/style adaptation; it must not be sold as independently measured financial reasoning accuracy. All 24 outputs and the narrow source review, including baseline regressions, are preserved in reports/finetuning_evaluation.json and reports/finetuning_source_review.json.
