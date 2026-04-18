# AI glossary, trends & reading aids

Quick reference for **terms that often appear** in briefings, papers, and vendor blogs. Use it to decode PDF/audio content and to keep **English technical vocabulary** consistent (especially in Chinese narration).

**Living document:** After **each** daily briefing run, the agent **appends** new or niche terms from that day into **Briefing additions (by date)** at the bottom (one `### YYYY-MM-DD` block per run). Do not duplicate rows that already exist in the main tables; merge near-synonyms into one row when obvious.

## How to use

- Skim **Core vocabulary** when a term in the briefing is unclear.
- **Trends** are coarse labels — not predictions — to classify “why this headline keeps showing up.”
- **Acronyms** collects tokens that TTS should often leave in English.
- After each report, check the latest **Briefing additions** block for what was new that day.

---

## Core vocabulary

| Term | Plain English | Why it shows up in news |
|------|----------------|-------------------------|
| **LLM** (large language model) | A model trained to predict/generate text; can chat, summarize, code | Product launches, benchmarks, safety debates |
| **Transformer** | Architecture using **attention** to relate distant words/tokens; basis of most modern LLMs | Papers, “new architecture” stories |
| **Attention** | Mechanism that weights which input parts matter for each output token | Technical posts, efficiency tricks (e.g. KV cache) |
| **Token** | Chunk of text (word/subword) the model reads; **context window** = max tokens in one pass | Pricing, “long context” releases |
| **Pre-training** | Train on huge text/code; general capability | Model family announcements |
| **Fine-tuning** | Further train on a smaller dataset for a task/style | Domain adapters, “medical” models |
| **RLHF / preference tuning** | Train with human (or AI) feedback so outputs are more helpful/safe | Alignment, policy changes |
| **RAG** (retrieval-augmented generation) | Fetch docs/data at query time, then generate with that context | Enterprise AI, “grounded” answers |
| **Embedding** | Numeric vector representing text/image for similarity search | Search, RAG, clustering |
| **Agent** | System that plans, calls tools/APIs, and loops until a goal | “Autonomous” product narratives |
| **Tool use / function calling** | Model outputs structured calls your app executes | Integration patterns (FHIR, DICOM services) |
| **MoE** (mixture of experts) | Sub-networks (“experts”); only some run per token — saves compute | Big model efficiency stories |
| **Quantization** | Lower precision (e.g. 8-bit) to shrink model / speed inference | On-device, local LLM releases |
| **Distillation** | Train a smaller model to imitate a larger one | Fast/cheap deployment |
| **LoRA / adapter** | Small trainable layers instead of full fine-tune | Customization without huge GPUs |
| **Inference** | Running a trained model on new inputs (vs training) | Serving, latency, cost |
| **Eval / benchmark** | Standard tests (MMLU, coding, math) to compare models | Leaderboards, “SOTA” claims |
| **Hallucination** | Confident but false output | Clinical/regulated domains = high risk |
| **Multimodal** | Model takes more than one modality (text + image/audio/video) | Radiology-like use cases in research |

---

## Deployment & stack (often relevant to backend devs)

| Term | Meaning |
|------|---------|
| **API** (REST/JSON, streaming) | How apps call models; **SSE** = server-sent events for token streams |
| **ONNX / ONNX Runtime** | Portable model format + runtime (usable from Java via bindings) |
| **GGUF** | Quantized weights format common for local tools (**llama.cpp**, etc.) |
| **vLLM, TGI** | High-throughput **serving** stacks for LLMs |
| **GPU / TPU** | Hardware accelerators; “**H100**” etc. = datacenter training/inference chips |

---

## Safety & policy (headline language)

| Term | Meaning |
|------|---------|
| **Alignment** | Making models behave according to human intent/values |
| **Red-teaming** | Adversarial testing for misuse/jailbreaks |
| **Guardrails** | Filters, policies, classifiers around a model |

---

## Trend buckets (for context, not investment advice)

- **Bigger context + cheaper inference:** Long documents, “one prompt many pages”, edge devices.
- **Agents + tools:** Less “chat only”, more orchestration (maps to clinical workflow automation — with strong governance).
- **Open weights vs API-only:** Tradeoff between control/privacy (local) and convenience (hosted).
- **Evals as product:** Benchmarks and “leaderboards” drive marketing; check task match to *your* use case.
- **Regulated domains:** Healthcare finance emphasize **auditability**, **human-in-the-loop**, and **data residency**.

---

## Acronyms to keep in English (TTS / subtitles)

Use English pronunciation or spell-out once, then acronym: **LLM, RAG, API, GPU, FHIR, DICOM, HIPAA (US), GDPR (EU), ONNX, JSON, REST, SSE, MoE, RLHF, LoRA, KV (cache), TPU, SOTA**.

---

## Related file

- **`knowledge-scope.md`** — your personal baseline (languages, stack, how deep explanations should go).

---

## Briefing additions (by date)

*New terms from daily briefings — append one dated subsection per run. Format:*

```markdown
### YYYY-MM-DD
| Term | Plain English | Source / context (optional) |
|------|----------------|-----------------------------|
| ... | ... | e.g. Hugging Face paper |
```

### 2026-04-07
| Term | Plain English | Source / context (optional) |
|------|----------------|-----------------------------|
| **DETR** (Detection Transformer) | End-to-end object detection architecture using transformers; treats detection as a set prediction problem | Arxiv ML — HI-MoE paper |
| **Latent reasoning** | Model "thinks" in embedding space rather than producing visible chain-of-thought text; harder to interpret | Arxiv ML — interpretability paper |
| **Self-play** | Training technique where a model generates its own training data by playing against itself | Arxiv AI — QED-Nano |
| **SFT** (Supervised Fine-Tuning) | Standard fine-tuning on labeled examples; often the first stage before RL | Arxiv AI — QED-Nano training recipe |
| **Kolmogorov complexity** | Theoretical measure of the shortest program that produces a given output; used to prove limits of AI safety verification | Arxiv AI — safety incompleteness paper |
| **Missense mutation** | DNA change that swaps one amino acid for another in a protein; can cause diseases like cystic fibrosis | DeepMind — AlphaMissense |
| **On-device / Edge AI** | Running AI models locally on user hardware (phone, workstation) without cloud; key for privacy and offline use | TechCrunch — Google offline dictation |
| **Harness design** | The scaffolding, prompts, and orchestration layer around an AI agent; often matters more than the model itself | Anthropic Engineering blog |
| **SWE-bench** | Benchmark for evaluating AI agents on real-world software engineering tasks (bug fixes from GitHub issues) | Anthropic — infrastructure noise paper |
| **Agentic coding** | AI systems that autonomously plan, write, test, and iterate on code (vs. simple autocomplete) | Anthropic — Claude Code auto mode |
| **AlphaGenome** | DeepMind's DNA sequence model for predicting regulatory variant effects; published in Nature, available via API | DeepMind blog |

### 2026-04-08
| Term | Plain English | Source / context (optional) |
|------|----------------|-----------------------------|
| **STL** (Signal Temporal Logic) | Formal language for specifying time-dependent behavior rules (e.g. "temperature must stay below X for Y seconds"); used here to analyze RL agent behavior | Arxiv ML — stratification paper |
| **GNN** (Graph Neural Network) | Neural network that operates on graph-structured data (nodes + edges) rather than flat tables; learns by aggregating info from neighboring nodes | Arxiv ML — power outage prediction |
| **Contrastive learning** | Training technique where the model learns by comparing similar and dissimilar example pairs | Arxiv ML — SA-HGNN paper |
| **Data attribution** | Tracing which training data points contributed to a model's specific outputs; the AI equivalent of git blame | Arxiv ML — adaptive learning paper |
| **MemMachine** | Memory architecture for AI agents that separates ground-truth facts from personalization preferences to prevent memory drift | Arxiv AI — personalized agents paper |
| **ANX protocol** | Protocol-first design for AI agent communication; 3EX architecture separates Execution, Experience, and Exchange layers (like REST for agents) | Arxiv AI — agent interaction paper |
| **Terminal-Bench** | Benchmark for evaluating AI agents on terminal/command-line tasks; Anthropic showed 6% infrastructure noise on version 2.0 | Anthropic — infrastructure noise |
| **Approval fatigue** | When users stop paying attention to permission prompts because they approve most of them; addressed by auto-mode classifiers | Anthropic — Claude Code auto mode |
| **SIMA 2** | DeepMind's generalist AI agent that can follow instructions, reason about goals, converse, and self-improve in 3D environments; powered by Gemini | DeepMind blog |
| **AlphaEarth** | DeepMind's AI for creating detailed planetary maps from satellite imagery | DeepMind blog |
| **Mythos** | Anthropic's new AI model previewed for cybersecurity applications (threat detection, vulnerability analysis, security code review) | TechCrunch — Anthropic |
| **Terafab** | Elon Musk's massive chip fabrication initiative; Intel signed on as partner | TechCrunch — Intel |
| **Trainium / Inferentia** | Amazon's custom AI chips for training and inference; adopted by Uber as alternative to Nvidia | TechCrunch — Uber |
| **Agent-first process redesign** | Designing workflows where AI agents are primary actors and humans provide oversight/handle exceptions, rather than adding AI to existing processes | MIT Technology Review |
| **GitNexus** | Client-side code intelligence engine that creates a knowledge graph from your codebase without a server; 1,195 stars on GitHub Trending | GitHub Trending |

### 2026-04-09
| Term | Plain English | Source / context (optional) |
|------|----------------|-----------------------------|
| **TTT** (Test-Time Training) | Updating a subset of model weights during inference so the model can adapt to new data on the fly, without retraining from scratch | Arxiv ML — In-Place TTT paper |
| **Fast weights** | A small subset of model parameters that can be updated at inference time (as opposed to the main "slow" weights fixed after training) | Arxiv ML — In-Place TTT |
| **TPO** (Target Policy Optimization) | RL training method that separates "what to reinforce" from "how to update parameters"; constructs a target distribution first, then fits the policy to it | Arxiv ML — TPO paper |
| **Trajectory-aware grading** | Evaluating an AI agent by recording and scoring every step it takes, not just the final output; catches unsafe actions that produce correct results | Arxiv AI — Claw-Eval |
| **Pass@k / Pass^k** | Evaluation metrics: Pass@k = best of k attempts (lucky outcomes count); Pass^k = all k attempts must pass (tests consistency) | Arxiv AI — Claw-Eval |
| **Epistemic blinding** | Inference-time protocol to detect whether an LLM is reasoning from provided context or regurgitating memorized training data | Arxiv AI — Epistemic Blinding paper |
| **Managed Agents** | Anthropic's hosted service for long-horizon agent work; decouples the model ("brain") from the harness/tools ("hands") via stable interfaces | Anthropic Engineering blog |
| **Context anxiety** | Behavior where an LLM wraps up tasks prematurely as it senses its context limit approaching; observed in Claude Sonnet 4.5 but gone in Opus 4.5 | Anthropic — Managed Agents |
| **Project Glasswing** | Anthropic's defensive cybersecurity coalition with Cisco and other partners; deploys restricted Mythos model for security only | The Rundown AI |
| **Gym-Anything** | Framework that converts arbitrary software applications into environments where AI agents can be trained and evaluated | Arxiv ML |
| **World model** | AI system that builds an internal representation of its environment and can predict consequences of actions before taking them | Arxiv ML — multi-token prediction paper |
| **LiteRT-LM** | Google's lightweight runtime for running language models on edge devices (phones, embedded systems) | GitHub Trending |

### 2026-04-10
| Term | Plain English | Source / context (optional) |
|------|----------------|-----------------------------|
| **Data deletion / data attribution** | Predicting how a model would behave if specific training data were removed; key for privacy (GDPR "right to be forgotten") and interpretability | Arxiv ML — "How to sketch a learning algorithm" |
| **Arithmetic circuit sketching** | Technique for locally approximating a computation graph using higher-order derivatives in random complex directions; enables efficient data deletion | Arxiv ML — sketching paper |
| **Split learning** | Distributed ML approach that partitions a model between edge devices and a server; only intermediate activations ("smashed data") cross the network | Arxiv ML — SL-FAC paper |
| **Smashed data** | The intermediate activations and gradients transmitted between client and server in split learning; compressing these is the key efficiency challenge | Arxiv ML — SL-FAC |
| **Neural ODE** | Neural network that models continuous-time dynamics using ordinary differential equations; enables physics-informed predictions | Arxiv ML — GNN-ODE digital twins |
| **T-STAR** (Tree-structured Self-Taught Agent Rectification) | Framework that organizes agent trajectories into a "Cognitive Tree" to assign credit at the step level, not just the trajectory level | Arxiv AI — T-STAR paper |
| **Cognitive Tree** | Data structure that merges functionally similar steps across multiple agent trajectories; enables fine-grained reward attribution | Arxiv AI — T-STAR |
| **Surgical Policy Optimization** | RL update strategy that concentrates gradient updates on critical divergence points in the Cognitive Tree rather than all steps uniformly | Arxiv AI — T-STAR |
| **Declared reflective runtime** | Protocol that externalizes agent state, confidence signals, and hypothetical transitions into inspectable structure; separates LLM contribution from scaffolding | Arxiv AI — "How Much LLM Does a Self-Revising Agent Need?" |
| **Infrastructure noise** | Variation in benchmark scores caused by differences in compute resources, timeouts, and environment config rather than model capability | Anthropic Engineering — eval noise paper |
| **Muse Spark** | Meta Superintelligence Labs' first model release; competitive but not top-of-leaderboard; backed by Meta's 3B+ daily users and data | The Rundown AI / TechCrunch |
| **Hermes Agent** | NousResearch's open-source "agent that grows with you"; 6,485 GitHub stars in one day | GitHub Trending |
| **Archon** | Open-source harness builder for AI coding; makes agentic coding deterministic and repeatable | GitHub Trending |
| **opendataloader-pdf** | Java-based open-source PDF parser for AI-ready data; automates PDF accessibility; 1,124 stars | GitHub Trending |
