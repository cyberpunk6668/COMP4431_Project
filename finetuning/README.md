# FinPilot local LoRA experiment

This folder contains an actual supervised fine-tuning experiment, not a claim that a hosted DeepSeek model was trained. The default chat service remains DeepSeek plus local retrieval. A separate optional engine uses the public Qwen3-0.6B model and the project-trained adapter after training completes.

## What is trained

The adapter targets grounded response behaviour: explain the supplied financial concept, state a caveat, include the provided source ID, and retain an educational boundary in Chinese or English. LoRA trains low-rank updates in attention projections while keeping base parameters frozen. This is a real parameter update; RAG and system prompts alone are not fine-tuning.

The public model is [`Qwen/Qwen3-0.6B`](https://huggingface.co/Qwen/Qwen3-0.6B), pinned to revision `c1899de289a04d12100db370d81485cdf75e47ca`. The publisher's model files use Apache-2.0. PyTorch reports **596,049,920 unique base parameters**, consistent with its 0.6B name. With the LoRA adapter there are **598,343,680 unique parameters**, of which **2,293,760 are trainable** (0.383352% of the adapted model). The approximately 1.5GB safetensors file stores 751,632,384 tensor elements because the tied language head and token embedding are both serialized; stored elements must not be confused with unique parameters. The base model is downloaded to an external Hugging Face cache, not committed into the project or source ZIP. The small adapter is saved under `models/finpilot-lora/`.

## Reproduce on an NVIDIA GPU

Tested target: Windows x64, Python 3.11, NVIDIA RTX 4070 Laptop GPU with 8GB VRAM. Use a separate environment so the web application's dependencies stay small.

```powershell
python -m venv .venv-ml
.\.venv-ml\Scripts\python.exe -m pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cu128
.\.venv-ml\Scripts\python.exe -m pip install -r requirements-ml.txt
$env:FINPILOT_HF_HOME = 'E:/CodexData/cache/huggingface'
.\.venv-ml\Scripts\python.exe scripts/download_model.py
.\.venv-ml\Scripts\python.exe scripts/train_lora.py
.\.venv-ml\Scripts\python.exe scripts/evaluate_lora.py
```

The cache environment variable is optional; without it, the usual Hugging Face cache under the current user's home is used. Downloading the CUDA PyTorch wheel takes several GB and the model weights approximately 1.5GB. There is no hosted GPU charge or private dataset upload. CPU fallback is deliberately not automatic for this training script.

For inference on another compatible computer, install the ML environment and run only `download_model.py`; the provided trained adapter can be reused without retraining. Use the cache setting in the application's local configuration as documented by the main README.

The implementation machine's proxy stalled whole multi-GB HTTP responses. The successful run used the optional `finetuning/download_cuda_wheel.py` and `finetuning/download_base_ranges.py` fallbacks: they fetch only the fixed official URLs with HTTP Range, resume completed chunks, and verify the complete file against the official PyTorch index SHA-256 or official Hugging Face LFS SHA-256 before use. Preallocated file size alone is **not** download completion. These helpers are provided to reproduce that networking workaround; they do not replace integrity checks, install a driver, or disable TLS validation.

## Data and leakage boundaries

`build_dataset.py` creates project-authored questions and curated reference-based answers from the existing official-source financial education summaries. It does not use user conversations, API credentials, account data, or undisclosed teacher-model output.

The split is by **knowledge topic group**, not random question rows: 12 training topics / 144 examples, 3 validation topics / 12 examples, 3 held-out test topics / 12 examples. Both languages of a topic stay in the same split. Hashes, exact group lists and provenance are in `data/manifest.json`. Prompts share a small family of styles across splits, which is explicitly a limitation; this is not a representative independent finance benchmark.

Only completion tokens contribute to loss. User input, the system prompt and supplied reference tokens have label `-100`. Non-thinking mode uses Qwen's explicit `enable_thinking=False` chat template consistently for training and evaluation. Inputs exceeding the configured maximum are rejected rather than silently truncating the target answer.

## Training evidence and evaluation

The presence of training scripts is not evidence of completed training. Completion is recorded only after optimizer updates and adapter serialization succeed, using `training_manifest.json` with `trained=true`, optimizer steps, hyperparameters, dataset hashes, adapter SHA-256, timing and GPU memory. Training history is saved to `reports/finetuning_training.json`. Exact artifacts and actual achieved metrics should be read from those files.

`evaluate_lora.py` evaluates the same pinned base with and without the adapter, using identical reference context and deterministic greedy generation. It records assistant-token loss, expected citation IDs, unknown citation IDs, three-section format, educational caveats, EOS completion and all generated responses. These metrics measure a narrow formatting/grounding behaviour, not general financial accuracy, factual entailment, investment suitability or robust safety. Generated answers can still be wrong. A lower validation loss alone does not prove improved usefulness.

## Why not “fine-tuned DeepSeek”

The current [DeepSeek API reference](https://api-docs.deepseek.com/api/create-chat-completion/) documents inference, files and search/fetch routes. No hosted fine-tuning-job endpoint was found in the reviewed official reference; the provided key authorizes inference, not arbitrary weight updates. This is an observation about the reviewed documented API, not a universal claim about private enterprise offerings. A separate [DeepSeek R1 announcement](https://api-docs.deepseek.com/news/news250120/) permits using certain model outputs for downstream training/distillation, which is different from providing a hosted fine-tuning service. This experiment uses original project targets and does not rely on that permission.

## Primary technical sources

- [Qwen model card and non-thinking mode](https://huggingface.co/Qwen/Qwen3-0.6B)
- [Qwen Apache-2.0 license](https://huggingface.co/Qwen/Qwen3-0.6B/blob/c1899de289a04d12100db370d81485cdf75e47ca/LICENSE)
- [Hugging Face PEFT quick tour](https://huggingface.co/docs/peft/en/quicktour)
- [PEFT LoRA reference](https://huggingface.co/docs/peft/en/package_reference/lora)
- [TRL supervised fine-tuning dataset formats](https://huggingface.co/docs/trl/en/sft_trainer)
- [Official PyTorch CUDA installation](https://pytorch.org/get-started/locally/)

Implementation uses a small transparent PyTorch training loop plus PEFT; it does not claim to use TRL/QLoRA/Unsloth. BF16 LoRA is sufficient for this model size on the observed GPU, avoiding an unnecessary quantization dependency.
