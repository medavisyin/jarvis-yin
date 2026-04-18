# Chapter 8: Learning Roadmap — RAG, LLM & HuggingFace

This chapter is a **hands-on learning map** for a Java developer in healthcare IT who has already built **Jarvis** and wants to go deeper on retrieval-augmented generation (RAG), large language models (LLMs), and the Hugging Face ecosystem. Prefer **building and measuring** over passive reading.

---

## How to Use This Roadmap

- **Three parallel tracks:** RAG, LLM, HuggingFace — you can rotate weekly or focus one track at a time.
- **Levels:** Beginner → Intermediate → Advanced, with rough calendar hints (weeks are indicative; healthcare schedules vary).
- **Time estimates:** Per *resource* or *topic block* (e.g. “2–4 hours” = read + small experiment). Treat them as orders of magnitude, not deadlines.
- **Jarvis markers:** **`[Jarvis]`** = concept or pattern already present in your stack; use the roadmap to *name* what you built and decide what to improve next.
- **Docs in this repo:** Cross-links point at sibling files under `docs/` and `docs/implementation/` so you can connect theory to your code.

---

## Track 1: RAG (Retrieval-Augmented Generation)

### Beginner (Week 1–2)

**Topics**

- **What is RAG?** Pipeline: chunk → embed → index → retrieve → (optional) re-rank → prompt LLM. Start with **[Chapter 1: RAG concepts](ch1-rag-concepts.md)** in this repo.
- **Vector databases:** dense vectors, collections, filters, distance metrics (cosine vs dot vs L2). Compare design goals of **[Qdrant](https://qdrant.tech/documentation/)**, **[Pinecone](https://docs.pinecone.io/)**, **[Weaviate](https://weaviate.io/developers/weaviate)**, **[Chroma](https://docs.trychroma.com/)**. **`[Jarvis]`** uses Qdrant (see **[Qdrant know-how](implementation/know-how/qdrant-vector-db.md)** and **[vector search explained](ch3-vector-search-explained.md)**).
- **Embedding models:** turn text into vectors; same model at index and query time; domain mismatch hurts recall. **[Sentence Transformers documentation](https://sbert.net/)**; model selection **[MTEB leaderboard](https://huggingface.co/spaces/mteb/leaderboard)** (when you want numbers).
- **Chunking:** fixed-size windows, paragraph/section boundaries, semantic chunking (split when embedding similarity drops). Trade recall vs context pollution.

**Resources (with URLs)**

| Resource | Time | Notes |
|----------|------|--------|
| [Pinecone: What is RAG?](https://www.pinecone.io/learn/retrieval-augmented-generation/) | 1–2 h | Vendor tutorial; concepts transfer to any stack. |
| [LanceDB: Chunking strategies for RAG](https://lancedb.com/blog/chunking-strategies-for-rag/) | 1–2 h | Practical chunking patterns. |
| [Qdrant: Vector search filtering](https://qdrant.tech/documentation/concepts/filtering/) | 1 h | Filters matter in healthcare-style metadata (source, date, tenant). |
| YouTube: search **“RAG explained”** + channel **3Blue1Brown** “Transformer” (attention intuition) | 2–3 h | Visual intuition before papers. |
| Paper (skim): [RAG — Retrieval-Augmented Generation (Lewis et al., 2020)](https://arxiv.org/abs/2005.11401) | 2–3 h | Original framing; read abstract + figures first. |

---

### Intermediate (Week 3–4)

**Topics**

- **Hybrid search (sparse + dense):** BM25/keyword recall + vector semantic recall; fusion (e.g. RRF). **`[Jarvis]`** — hybrid BM25 + vector with RRF; see **[search UI implementation](implementation/rag/search-ui-impl.md)**.
- **Re-ranking:** bi-encoder (fast, candidate generation) vs cross-encoder (slow, pairwise scoring). **`[Jarvis]`** — cross-encoder re-ranking on top candidates; same doc as above.
- **Query rewriting & HyDE:** rewrite vague queries; *Hypothetical Document Embeddings* embed a synthetic answer as the query vector. **[HyDE (Gao et al., 2022)](https://arxiv.org/abs/2212.10496)**. **`[Jarvis]`** — optional Ollama-based rewrite for vague queries (not full HyDE unless you add it).
- **Evaluation:** MRR, NDCG, Recall@K; build a small labeled set (even 50 queries) for your domain. **[BEIR benchmark paper](https://arxiv.org/abs/2104.08663)** for metric context.
- **Frameworks:** **[LangChain](https://python.langchain.com/)**, **[LlamaIndex](https://docs.llamaindex.ai/)**, **[Haystack](https://docs.haystack.deepset.ai/)** — orchestration, connectors, abstractions. Jarvis is intentionally **custom Flask + scripts**; comparing frameworks helps you decide when *not* to stay custom.

**Resources**

| Resource | Time | Notes |
|----------|------|--------|
| [Cohere: Reranking overview](https://docs.cohere.com/docs/reranking) | 1 h | Clear API mental model (vendor docs). |
| [Azure AI Search: Hybrid search](https://learn.microsoft.com/en-us/azure/search/hybrid-search-overview) | 1–2 h | Enterprise-flavored hybrid patterns. |
| [LlamaIndex: Evaluation](https://docs.llamaindex.ai/en/stable/module_guides/evaluating/) | 2–4 h | Metrics + tooling ideas you can replicate without the framework. |
| Paper: [Reciprocal Rank Fusion (Cormack et al.)](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) | 1 h | Short; explains RRF intuition. |

---

### Advanced (Month 2–3)

**Topics**

- **Domain-adapted embeddings:** contrastive training on (query, relevant doc) pairs from *your* logs (privacy/consent first in healthcare).
- **RLHF / RL for retrieval:** reward models ranking helpful passages; research-heavy, not default for internal tools.
- **Multi-hop:** decompose question → sub-queries → merge evidence; higher complexity and failure modes.
- **Agentic RAG:** tool-calling loops (search again, refine query, summarize). See **[advanced RAG techniques](ch6-advanced-rag-techniques.md)** and **[RAG agent design](rag-agent-design.md)** in this repo.
- **Production:** horizontal scaling of vector DB, index versioning, latency SLOs, content freshness, **A/B tests** on retrieval params, observability (trace ID per query).

**Resources**

| Resource | Time | Notes |
|----------|------|--------|
| [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | 1–2 h | Grounds “agentic” patterns in engineering discipline. |
| [Google Cloud: RAG evaluation strategies](https://cloud.google.com/architecture/rag-eval-strategies) | 1–2 h | Production evaluation framing. |
| Paper: [Self-RAG (Asai et al., 2023)](https://arxiv.org/abs/2310.11511) | 3–5 h | Self-reflection tokens for retrieve / not retrieve. |
| Paper: [Corrective-RAG / CRAG (Yan et al., 2024)](https://arxiv.org/abs/2401.15884) | 3–5 h | Corrective retrieval actions. |

---

## Track 2: LLM (Large Language Models)

### Beginner (Week 1–2)

**Topics**

- **Transformers & attention:** self-attention as soft lookup; positional information; encoder vs decoder stacks. **[Attention Is All You Need](https://arxiv.org/abs/1706.03762)** (skim with a guide).
- **Tokenization:** BPE, SentencePiece; why “same words” can split differently; context length is in **tokens**, not characters.
- **Inference:** prefill vs decode, sampling (temperature, top-p), stop tokens; each API call is matrix math + memory bandwidth.
- **Local vs cloud:** latency, cost, data residency (critical in healthcare), ops burden. **`[Jarvis]`** — local **[Ollama](https://ollama.com/)** for optional query rewrite; see **[Ollama know-how](implementation/know-how/ollama-local-llm.md)**.
- **Local serving options:** **[vLLM](https://docs.vllm.ai/)** (throughput), **[llama.cpp](https://github.com/ggerganov/llama.cpp)** (CPU/GGUF-friendly), Ollama (simple packaging).

**Resources**

| Resource | Time | Notes |
|----------|------|--------|
| [Hugging Face: NLP Course — Transformers](https://huggingface.co/learn/nlp-course/chapter1/1) | 3–6 h | Official course; module 1 is enough to start. |
| [3Blue1Brown: But what is a GPT?](https://www.youtube.com/watch?v=wjZofJX0v4M) | ~1 h | Intuition for inference. |
| [OpenAI: Prompt engineering guide](https://platform.openai.com/docs/guides/prompt-engineering) | 1–2 h | Patterns apply to any chat model API. |

---

### Intermediate (Week 3–4)

**Topics**

- **Prompt engineering:** system vs user messages, few-shot examples, chain-of-thought (careful in regulated settings: trace reasoning for audit).
- **“Thinking” / reasoning models:** extended internal chains; APIs expose `think` flags or reasoning tokens on some stacks. **`[Jarvis]`** — Ollama **`qwen3`** with configurable think mode for rewrite path (see search UI doc).
- **Quantization:** GGUF (llama.cpp ecosystem), GPTQ, AWQ — smaller memory, sometimes quality loss; important for laptop deployment.
- **Context window:** trimming, summarization, retrieval instead of “paste everything”; lost-in-the-middle effect.
- **Function calling / tools:** JSON schema constrained outputs; same idea as FHIR-related “structured extraction” patterns.

**Resources**

| Resource | Time | Notes |
|----------|------|--------|
| [Anthropic: Prompt library & long context tips](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering) | 2–3 h | Strong general guidance. |
| [Ollama: Modelfile / parameters](https://github.com/ollama/ollama/blob/main/docs/modelfile.md) | 1 h | Local tuning entry point. |
| Paper (skim): [Lost in the Middle (Liu et al.)](https://arxiv.org/abs/2307.03172) | 1–2 h | Why long contexts need design, not just more tokens. |

---

### Advanced (Month 2–3)

**Topics**

- **Fine-tuning:** LoRA / QLoRA — update adapters, not full weights; smaller GPU footprint.
- **RLHF & DPO:** preference optimization vs human ranking pipelines; governance-heavy for clinical wording.
- **Evaluation:** HELM-style breadth vs domain-specific golden sets; human eval for safety-critical wording.
- **Serving at scale:** continuous batching, KV cache reuse, speculative decoding.
- **Multimodal:** vision-language models; audio; relevant as imaging and documentation become multimodal in healthcare IT.

**Resources**

| Resource | Time | Notes |
|----------|------|--------|
| [Hugging Face: PEFT / LoRA docs](https://huggingface.co/docs/peft/main/en/index) | 3–6 h | Matches Track 3 advanced topics. |
| [vLLM: Performance optimization](https://docs.vllm.ai/en/latest/performance/optimization.html) | 1–2 h | Serving concepts. |
| Paper: [LoRA (Hu et al., 2021)](https://arxiv.org/abs/2106.09685) | 2–4 h | The standard adapter fine-tuning reference. |
| Paper: [DPO (Rafailov et al.)](https://arxiv.org/abs/2305.18290) | 3–5 h | Preference optimization without explicit RM in the loop. |

---

## Track 3: HuggingFace Ecosystem

### Beginner (Week 1)

**Topics**

- **Hub:** model repos, dataset repos, **Spaces** (Gradio/Streamlit demos), versioning, licensing (check labels before internal use).
- **`transformers`:** `AutoModel`, `AutoTokenizer`, pipelines for quick experiments.
- **`sentence-transformers`:** `encode()` for embeddings; training hooks later. **`[Jarvis]`** — see **[Sentence Transformers know-how](implementation/know-how/sentence-transformers.md)**.
- **Model cards:** intended use, training data, limitations, bias — read these the way you read vendor DPA annexes.

**Resources**

| Resource | Time | Notes |
|----------|------|--------|
| [Hugging Face Hub documentation](https://huggingface.co/docs/hub/index) | 2–3 h | Navigation and workflows. |
| [Sentence Transformers: usage](https://sbert.net/docs/usage/usage.html) | 1–2 h | Aligns with Jarvis embedding path. |
| [Hugging Face: Model Cards explained](https://huggingface.co/docs/hub/model-cards) | 1 h | Habit for responsible adoption. |

---

### Intermediate (Week 2–3)

**Topics**

- **`datasets`:** `load_dataset`, `map`, streaming for large corpora.
- **`Trainer` API:** training loop abstraction; good bridge from “script kiddie” to reproducible training.
- **`tokenizers`:** fast tokenization, alignment with models.
- **`evaluate`:** BLEU, accuracy, etc.; pair with your retrieval metrics for RAG.
- **Spaces + Gradio:** quick UI for demos; **[Gradio docs](https://www.gradio.app/docs)**.

**Resources**

| Resource | Time | Notes |
|----------|------|--------|
| [Datasets documentation](https://huggingface.co/docs/datasets/main/en/index) | 3–5 h | Do one streaming exercise end-to-end. |
| [Transformers: Training loop](https://huggingface.co/docs/transformers/main/en/trainer) | 2–4 h | Train a tiny classifier first. |
| [Evaluate library](https://huggingface.co/docs/evaluate/main/en/index) | 1–2 h | Wire one metric into a notebook. |

---

### Advanced (Month 2)

**Topics**

- **Custom training:** own data collators, loss functions, multi-GPU later.
- **PEFT:** LoRA adapters; swap adapters per task.
- **Accelerate:** distributed training launcher patterns.
- **Optimum:** ONNX/TensorRT/OpenVINO paths for inference optimization.
- **TRL:** RLHF/DPO-style training with HF primitives.

**Resources**

| Resource | Time | Notes |
|----------|------|--------|
| [Accelerate documentation](https://huggingface.co/docs/accelerate/main/en/index) | 2–4 h | Start with CPU/multiple GPU overview. |
| [Optimum documentation](https://huggingface.co/docs/optimum/main/en/index) | 2–4 h | Pick one export target relevant to your deployment. |
| [TRL documentation](https://huggingface.co/docs/trl/main/en/index) | 4–8 h | Read DPO/SFT sections before running big jobs. |
| [HF Jobs / TRL cloud training](https://huggingface.co/docs/huggingface_hub/en/guides/jobs) | 2 h | Optional if you outgrow local GPU. |

---

## Recommended Learning Path for the Jarvis Developer

A **12-week** arc for someone who already shipped Jarvis: each week, **one theory block + one measurable change** (log metric, ablation, or small PR).

| Week | Focus | Hands-on Project |
|------|--------|------------------|
| 1 | RAG Beginner + LLM Beginner | Trace one search end-to-end in code: chunk → Qdrant → hybrid → rerank; annotate the call path in your editor. |
| 2 | HuggingFace Beginner | Swap or A/B two embedding models from the Hub; record latency and subjective recall on 10 real queries. |
| 3 | RAG Intermediate | Implement **Recall@K / nDCG** on a tiny labeled set (spreadsheet is fine); compare hybrid vs vector-only. |
| 4 | LLM Intermediate | Systematically tune rewrite prompts for vague queries; log before/after query text and click-through if you have UI signals. |
| 5–6 | HuggingFace Intermediate | **Fine-tune MiniLM** (or another small bi-encoder) on pairs from Jarvis feedback (privacy review first). |
| 7–8 | RAG Advanced | Prototype **corrective RAG**: detect low-confidence retrieval and trigger a second retrieval or user-facing clarification. |
| 9–10 | LLM Advanced | **LoRA** experiment on a small instruction set with **Qwen3** (or your default Ollama model) in a sandbox; compare to baseline prompts only. |
| 11–12 | Integration | **Closed loop:** feedback → dataset → fine-tune → export → wire into search or rewrite path → simple deploy checklist (version, rollback). |

---

## Key Papers to Read

Fifteen **seminal or high-signal** papers (newest first in places). Read **abstract + method figure** first; return for full detail when implementing.

1. **[Corrective-RAG (CRAG) (2024)](https://arxiv.org/abs/2401.15884)** — Retrieves, evaluates, and corrects bad retrievals before generation.  
2. **[Self-RAG (2023)](https://arxiv.org/abs/2310.11511)** — Model learns to retrieve, reflect, and cite via special tokens.  
3. **[RLHF — Training language models to follow instructions (Ouyang et al., 2022)](https://arxiv.org/abs/2203.02155)** — InstructGPT-style alignment pipeline.  
4. **[HyDE (2022)](https://arxiv.org/abs/2212.10496)** — Hypothetical document embeddings to improve query representation.  
5. **[Lost in the Middle (2023)](https://arxiv.org/abs/2307.03172)** — U-shaped attention to context: planning where to put facts in the prompt.  
6. **[BEIR (2021)](https://arxiv.org/abs/2104.08663)** — Heterogeneous zero-shot retrieval benchmark and evaluation practice.  
7. **[ColBERT (2020)](https://arxiv.org/abs/2004.12832)** — Late interaction for efficient retrieval quality vs bi-encoder speed.  
8. **[RAG — Retrieval-Augmented Generation (2020)](https://arxiv.org/abs/2005.11401)** — Foundational dense-passage + seq2seq knowledge-intensive NLP.  
9. **[Sentence-BERT (2019)](https://arxiv.org/abs/1908.10084)** — Siamese BERT networks for sentence embeddings that scale semantic search.  
10. **[BERT (2018)](https://arxiv.org/abs/1810.04805)** — Deep bidirectional pre-training; foundation for many encoders you still see in retrieval.  
11. **[Attention Is All You Need (2017)](https://arxiv.org/abs/1706.03762)** — Transformer architecture; the root of modern LLMs.  
12. **[Seq2Seq + Attention (2014)](https://arxiv.org/abs/1409.0473)** — Encoder-decoder attention precursor (optional historical context).  
13. **[LoRA (2021)](https://arxiv.org/abs/2106.09685)** — Low-rank adaptation for parameter-efficient fine-tuning.  
14. **[DPO (2023)](https://arxiv.org/abs/2305.18290)** — Direct preference optimization without explicit reward modeling.  
15. **[T5 — Exploring the limits of transfer learning (2019)](https://arxiv.org/abs/1910.10683)** — Text-to-text framing used in many RAG generators early on.  

---

## Enterprise vs Personal: Technology Choices

Healthcare IT often forces a move from a **personal Jarvis-style stack** to **managed, governed services**. Use this table to anticipate *why* teams make those jumps — not to imply your setup is “wrong” for learning or for low-risk personal knowledge work.

| Component | Jarvis (Personal) | Enterprise Alternative | Why Different |
|-----------|-------------------|------------------------|---------------|
| Vector DB | Qdrant in-memory / local | [Qdrant Cloud](https://qdrant.tech/documentation/cloud/), [Pinecone](https://www.pinecone.io/), [Weaviate Cloud](https://weaviate.io/) | **Scale** (millions of vectors, many QPS), backups, HA, **SLAs** for internal apps. |
| LLM | Ollama local | [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-services/openai-service), [AWS Bedrock](https://aws.amazon.com/bedrock/), [Anthropic API](https://www.anthropic.com/api) | **Stronger models**, predictable latency at scale, **vendor DPAs / BAA** paths for PHI-adjacent workflows (when contracted). |
| Embeddings | e.g. MiniLM / ST local | [OpenAI embeddings](https://platform.openai.com/docs/guides/embeddings), [Cohere embed](https://docs.cohere.com/docs/embeddings) | Often **higher quality** on general text; **no GPU ops**; centralized key management and audit logs. |
| Search | Custom Python (BM25 + vector + RRF) | [Elasticsearch vector search](https://www.elastic.co/guide/en/elasticsearch/reference/current/knn-search.html), [OpenSearch k-NN](https://docs.opensearch.org/docs/latest/vector-search/) | **Operational maturity**: index management, security plugins, existing SRE skills in Java/ops teams. |
| Framework | Custom Flask + scripts | [LangChain](https://python.langchain.com/), [LlamaIndex](https://www.llamaindex.ai/), [Haystack](https://haystack.deepset.ai/) | **Team velocity** and hiring pool; prebuilt connectors to enterprise data sources; tradeoff is abstraction weight. |
| Orchestration | Shell / cron / manual | [Airflow](https://airflow.apache.org/), [Prefect](https://www.prefect.io/), [Dagster](https://dagster.io/) | **Schedules, retries, lineage**, and monitoring when indexing is business-critical. |
| Auth | Single-user / none | OAuth2, SAML, [Azure AD](https://learn.microsoft.com/en-us/azure/active-directory/develop/) | **Multi-user**, audit trails, role-based access — mandatory for shared clinical or operational knowledge. |
| Monitoring | Logs, ad hoc metrics | [LangSmith](https://www.langchain.com/langsmith), [Weights & Biases](https://wandb.ai/site), [Datadog](https://www.datadoghq.com/) LLM features | **Traces**, eval hooks, alerting — needed when RAG is customer-facing or regulated. |

**When to favor enterprise alternatives**

- **Team size ~3+** backend engineers sharing ownership of retrieval → frameworks + shared search infra reduce bus factor.  
- **Data volume** beyond comfortable RAM / single-node Qdrant → managed vector DB or Elasticsearch with sharding.  
- **Compliance** (PHI, GDPR, internal security policy) → cloud APIs with **signed BAAs/DPAs**, private endpoints, and centralized secrets — local Ollama is still fine for **non-PHI** experimentation.  
- **SLOs** (e.g. p95 search under 500 ms) → dedicated serving (vLLM, managed inference) + caching + CDN for static UI.

**When staying “Jarvis-style” is rational**

- Personal knowledge, no PHI; **learning budget** prioritized over SLA.  
- **Air-gapped** or strict “no external API” labs — local models and embeddings win.  
- You want **full transparency** into every retrieval stage (which Jarvis documents in `implementation/rag/`).

---

## Quick index of Jarvis touchpoints in this repo

| Topic | Where in Jarvis docs |
|-------|----------------------|
| RAG concepts | [ch1-rag-concepts.md](ch1-rag-concepts.md) |
| Vector search | [ch3-vector-search-explained.md](ch3-vector-search-explained.md) |
| Hybrid + rerank + rewrite | [implementation/rag/search-ui-impl.md](implementation/rag/search-ui-impl.md) |
| Qdrant | [implementation/know-how/qdrant-vector-db.md](implementation/know-how/qdrant-vector-db.md) |
| Sentence Transformers | [implementation/know-how/sentence-transformers.md](implementation/know-how/sentence-transformers.md) |
| Ollama | [implementation/know-how/ollama-local-llm.md](implementation/know-how/ollama-local-llm.md) |
| ML + retrieval roadmap (earlier chapter) | [ch5-ml-roadmap.md](ch5-ml-roadmap.md), [ch7-ml-for-retrieval.md](ch7-ml-for-retrieval.md) |

---

*Chapter 8 — Learning roadmap for RAG, LLM, and Hugging Face. Update links as the field moves; prefer arXiv / official docs over SEO blogs when in doubt.*
