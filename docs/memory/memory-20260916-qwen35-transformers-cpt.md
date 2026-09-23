# Memory: Qwen3.5 4B Transformers Continued Pre-training Evaluation

**Generated**: 2026-09-16
**Last updated**: 2026-09-16
**Project**: c:\jarvis
**Focus**: Whether Hugging Face Transformers can continued-pretrain Qwen3.5 4B locally and export the result to Ollama

---

## Goal & Scope (required)

Produce a capability verdict: can Transformers continued-pretrain existing Qwen3.5 4B on extra text, then use that checkpoint in local Ollama. Evaluation only — no implementation, no alternative-tool how-to.

---

## Key Decisions (required)

1. **Task is continued pre-training, not from-scratch pre-training and not instruct fine-tune**: User chose keep-training existing Qwen3.5 4B on extra text, then use it in Ollama.
2. **Deliverable is a capability verdict only**: No implementation and no cloud/alternative-tool playbook.
3. **Hardware constraint is this machine**: Intel UHD Graphics, no NVIDIA CUDA GPU.
4. **Rejected: start-from-Ollama-GGUF as the training base**: Ollama `qwen3.5:4b` is a quantized GGUF for inference; Transformers CPT needs the Hugging Face Base safetensors.

---

## Confirmed Assumptions (required)

- Model of interest is the local Ollama tag `qwen3.5:4b` / Hugging Face `Qwen/Qwen3.5-4B` family.
- Target inference runtime after training is local Ollama.
- Success = a clear yes/no on this machine + Transformers + Ollama export.

---

## Constraints & Non-Goals (include when relevant)

- Local Intel UHD Graphics only (no CUDA).
- No implementation of a training pipeline.
- No alternative-tool / cloud how-to (user explicitly chose verdict only).

---

## Key Discoveries (required)

- Hugging Face Transformers **can** continued-pretrain `Qwen/Qwen3.5-4B-Base` in principle: causal LM via `Trainer` / custom loop. Architecture id is `qwen3_5`; needs Transformers **5.2+ / git main** (not 4.x).
- Qwen3.5-4B is **not** a vanilla Llama-style 4B: hybrid Gated DeltaNet + Gated Attention, vision encoder, vocab **248320**, native context 262k, ~4–5B params. BF16 weights ~10 GB.
- Full continued pre-training / full FT is GPU-class work. Public recipes: QLoRA on ~24 GB NVIDIA, full FT on ~96 GB NVIDIA. AdamW optimizer states dominate memory.
- **Ollama does not train.** Local `qwen3.5:4b` (3.4 GB GGUF, Ollama 0.33.2) is inference-only. CPT must start from HF Base `.safetensors`, then convert via llama.cpp `convert_hf_to_gguf.py` and `ollama create`.
- This machine (checked 2026-09-16): Intel UHD Graphics (~2 GB AdapterRAM), **~64 GB RAM**, `torch 2.11.0+cpu` with `cuda=False` and `xpu=False`. Stock PyTorch will not use UHD for this training. Practical CPT here is **no**.
- Export path after training **elsewhere** is plausible: this Ollama 0.33.2 already loads official `qwen3.5:4b`, so the architecture is supported for inference.

---

## Runtime Evidence (include when relevant)

- GPU: Intel(R) UHD Graphics, AdapterRAM 2147479552, driver 32.0.101.6078
- RAM: TotalPhysicalMemory 68388900864 (~64 GB)
- Ollama 0.33.2: `qwen3.5:4b` 3.4 GB, also `qwen3:1.7b`, `qwen3-vl:8b`
- Python 3.13.14, torch 2.11.0+cpu, cuda False, xpu False

---

## Open Risks (include when relevant)

- Community GGUFs of Qwen3.5 have historically failed on older Ollama llama.cpp pins (`unknown model architecture: qwen35`). Official `ollama pull qwen3.5:4b` already works on 0.33.2; a home-converted GGUF could still mismatch if llama.cpp converter and Ollama's vendored runtime disagree.

---

## Current State (required)

- **Working**: Evaluation complete; local hardware/Ollama/torch inspected.
- **Pending**: None (verdict-only task).
- **Blocked**: None.

---

## Next Steps (required)

1. [x] Confirm requirements (CPT, Intel UHD, verdict only)
2. [x] Inspect local GPU/RAM/Ollama/torch
3. [x] Deliver capability verdict
4. [ ] Only if user later asks: practical GPU/cloud CPT path and GGUF export

---

## Notes for Next Session (include when relevant)

- Do not propose training from the Ollama GGUF.
- Do not treat Intel UHD + CPU torch as a viable CPT accelerator for 4B Qwen3.5.
- Correct start checkpoint: `Qwen/Qwen3.5-4B-Base` (not the post-trained `Qwen/Qwen3.5-4B` unless the user wants to continue from the instruct/chat model).

---

## References (required)

- https://github.com/huggingface/transformers
- https://huggingface.co/Qwen/Qwen3.5-4B-Base
- https://huggingface.co/Qwen/Qwen3.5-4B
- https://github.com/ggml-org/llama.cpp/pull/19468 (Qwen3.5 GGUF conversion)
- Local: Ollama `qwen3.5:4b` on this machine

---

**Confirmed at**: 2026-09-16
