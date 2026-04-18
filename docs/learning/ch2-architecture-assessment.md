# Chapter 2: Architecture Assessment — Where Does Jarvis Sit?

> An honest evaluation of Jarvis against the industry-standard RAG taxonomy.
> What it does well, what's missing, and what category it falls into.

---

## The RAG Maturity Spectrum (2025-2026 Taxonomy)

The AI community recognizes five levels of RAG architecture:

```
Level 1          Level 2          Level 3          Level 4          Level 5
─────────────────────────────────────────────────────────────────────────────
NAIVE RAG    →  ADVANCED RAG  →  MODULAR RAG  →  CORRECTIVE RAG → AGENTIC RAG
                                                  (CRAG)

Simple           Optimized        Pluggable        Self-healing     Autonomous
pipeline         pipeline         components       retrieval        reasoning
```

### Level 1: Naive RAG
```
Query → Embed → Vector Search → Top-K → LLM → Answer
```
- Single embedding model, single retrieval step
- No query preprocessing, no re-ranking
- Fixed chunking, no overlap
- Works but has low precision and recall

### Level 2: Advanced RAG
```
Query → Rewrite → Hybrid Search → Re-rank → LLM → Answer
         ↑          (vector+BM25)    ↑
    Query expansion            Cross-encoder
```
- Query rewriting/expansion before search
- Hybrid retrieval (vector + keyword/BM25)
- Cross-encoder re-ranking after retrieval
- Optimized chunking with overlap
- Metadata filtering

### Level 3: Modular RAG
```
Query → Router → [Search Module A] → Fusion → Re-rank → LLM
                 [Search Module B]
                 [Memory Module]
                 [Knowledge Graph]
```
- Interchangeable retrieval modules
- Query routing to different search strategies
- Memory and caching layers
- Can mix dense, sparse, and graph retrieval

### Level 4: Corrective RAG (CRAG)
```
Query → Retrieve → Validate → [Good? → Use it]
                              [Bad?  → Web search / rephrase / retry]
```
- Evaluates retrieval quality before using it
- Falls back to alternative sources if retrieval is poor
- Self-correcting retrieval pipeline

### Level 5: Agentic RAG
```
Query → Agent → [Plan] → [Retrieve] → [Reason] → [Retrieve again?]
                   ↑          ↓              ↓
              [Reflect]   [Tools]      [Multi-hop]
```
- LLM autonomously decides when and how to search
- Multi-step reasoning with iterative retrieval
- Tool use, planning, and reflection
- Dynamic memory management
- Can coordinate multiple agents

---

## Jarvis: Honest Assessment

### What Jarvis Does (Feature-by-Feature)

| Feature | Jarvis Has It? | How? |
|---------|:-:|------|
| Vector search | **Yes** | Qdrant cosine similarity, 384-dim MiniLM |
| Metadata filtering | **Yes** | Date, source, type, difficulty, author filters |
| Auto-RAG injection | **Yes** | Always searches before sending to LLM |
| Entity-aware search | **Yes** | Team name aliases trigger author-filtered queries |
| Keyword-aware routing | **Yes** | Wiki/git/Jira keywords trigger specialized searches |
| Tool calling | **Yes** | ReAct loop with git, Jira, Confluence, image tools |
| Streaming responses | **Yes** | SSE token-by-token streaming |
| Session memory | **Yes** | Persistent chat history across restarts |
| Adaptive context window | **Yes** | Scales `num_ctx` based on actual content length |
| Multiple content types | **Yes** | PDF, MD, Java, Wiki, custom knowledge |
| Incremental indexing | **Yes** | Change detection with manifest |
| Query rewriting | **Yes** | LLM-based expansion via `_rewrite_query` in `agent.py` |
| Hybrid search (BM25) | **Yes** | BM25 + vector with RRF (`bm25_index.py`, search + agent paths) |
| Re-ranking | **Yes** | Cross-encoder re-ranking (`reranker.py`, `search_ui.py`) |
| Chunk overlap | **Yes** | Overlap applied across all five indexers |
| Retrieval validation | **No** | No quality check on retrieved results |
| Feedback loop | **Partial** | Thumbs up/down, implicit signals, feedback-weighted ranking (`feedback_store.py`) |
| Multi-hop retrieval | **No** | Single retrieval pass (tools can search again, but not systematic) |
| Fine-tuned embeddings | **No** | Uses off-the-shelf MiniLM model |

### The Verdict: Jarvis Sits at Level 2 (Advanced RAG) + Agentic Shell

**Implemented Advanced RAG (as of April 2026):** chunk overlap on all indexers; BM25 hybrid search with reciprocal rank fusion (RRF); cross-encoder re-ranking; LLM query rewriting; feedback collection with feedback-weighted ranking.

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  RETRIEVAL CORE:  ████████████████░░░░  Advanced RAG (Level 2) │
│                                                                  │
│  - Hybrid dense + BM25 with RRF fusion                           │
│  - Cross-encoder re-ranking on candidate sets                    │
│  - Chunk overlap + structured paragraph chunking                 │
│  - LLM query rewriting before search                             │
│  - Feedback-weighted ranking (thumbs + implicit signals)         │
│  - No systematic retrieval quality validation yet                │
│                                                                  │
│  AGENT SHELL:     ████████████████░░░░  Proto-Agentic (Level 4) │
│                                                                  │
│  - Auto-RAG context injection (smart!)                           │
│  - Entity-aware multi-query search                               │
│  - Keyword-based tool routing                                    │
│  - ReAct tool loop (up to 8 iterations)                          │
│  - Streaming SSE with tool status                                │
│  - Session memory                                                │
│                                                                  │
│  OVERALL:         ████████████████░░░░  Level 2 retrieval         │
│                   with strong agentic capabilities               │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**In plain English:** The retrieval stack now matches **Advanced RAG**: hybrid retrieval, re-ranking, overlap, query rewriting, and a live feedback signal for ranking. The agent layer remains a capable proto-Agentic shell (tools, streaming, memory). The next major upgrades are **embedding fine-tuning**, **retrieval validation (CRAG-style)**, and deeper modular routing—not rebuilding basic search.

---

## What Jarvis Does Well (Strengths)

### 1. Zero-Infrastructure Simplicity
No external database server, no cloud services, no Docker. Everything runs from Python scripts with an in-memory Qdrant and a JSON file. This is a **huge** advantage for a single-developer setup.

### 2. Auto-RAG Is a Smart Design Choice
Instead of relying on the LLM to decide "should I search?", Jarvis **always** searches. This means even small/fast models get grounded answers. Many production systems have adopted this pattern.

### 3. Entity-Aware Multi-Query
The team-name aliasing (`"Jan"` → `"Jan Loeffler"` → author-filtered search) is a form of **query augmentation** that's actually more advanced than many tutorials show. It's not LLM-based rewriting, but it's effective for the use case.

### 4. Practical Tool Integration
Git commit summaries, Jira reports, Confluence search — these are real-world integrations that most RAG demos don't have. The keyword-based auto-routing (running tools in parallel with RAG search) is efficient.

### 5. Comprehensive Content Pipeline
The 16 fetch scripts (10 AI + 6 world news including Chinese political/financial news), PDF generation, audio generation, glossary maintenance, and multi-source indexing represent a complete **knowledge management system**, not just a chatbot.

---

## What's Missing (Gaps)

### Addressed (formerly Gaps 1–5)
Hybrid search (BM25 + vector + RRF), cross-encoder re-ranking, chunk overlap, LLM query rewriting, and feedback collection with weighted ranking are **implemented**. See [Chapter 6 — Advanced RAG Techniques](ch6-advanced-rag-techniques.md) and the implementation status note there.

### Gap 1: No Embedding Fine-Tuning
**Impact: High (for domain-specific lift).** Embeddings remain off-the-shelf MiniLM. Domain fine-tuning (200–500 pairs) is the next high-impact ML step; see [Chapter 5](ch5-ml-roadmap.md) and the [ML Integration Plan](plan-ml-integration.md).

### Gap 2: No Retrieval Validation
**Impact: Medium.** If search returns weak results, the agent still injects them. A validation step could trigger rewrite, alternate retrieval, or abstention—Corrective RAG (CRAG).

### Gap 3: Limited Modular Routing
**Impact: Medium (long-term).** Retrieval is advanced but not yet a pluggable router across multiple specialized indexes or strategies (Modular RAG).

### Gap 4: No Systematic Multi-Hop Retrieval
**Impact: Medium.** Tools can search again ad hoc, but there is no first-class multi-hop retrieve–reason loop.

---

## Comparison Table: Jarvis vs. Each Level

| Capability | Naive | Advanced | Modular | CRAG | Agentic | **Jarvis** |
|-----------|:-----:|:--------:|:-------:|:----:|:-------:|:----------:|
| Dense vector search | Yes | Yes | Yes | Yes | Yes | **Yes** |
| Metadata filtering | — | Yes | Yes | Yes | Yes | **Yes** |
| Query rewriting | — | Yes | Yes | Yes | Yes | **Yes** |
| Hybrid search (BM25) | — | Yes | Yes | Yes | Yes | **Yes** |
| Re-ranking | — | Yes | Yes | Yes | Yes | **Yes** |
| Chunk overlap | — | Yes | Yes | Yes | Yes | **Yes** |
| Feedback-weighted ranking | — | — | — | — | Varies | **Yes** |
| Modular retrieval | — | — | Yes | Yes | Yes | — |
| Retrieval validation | — | — | — | Yes | Yes | — |
| Self-correction | — | — | — | Yes | Yes | — |
| Tool calling | — | — | — | — | Yes | **Yes** |
| Multi-step reasoning | — | — | — | — | Yes | **Partial** |
| Session memory | — | — | — | — | Yes | **Yes** |
| Auto-RAG injection | — | — | — | — | Varies | **Yes** |
| Entity-aware search | — | — | — | — | Varies | **Yes** |

---

## The Upgrade Path (Priority Order)

If you wanted to evolve Jarvis further, here's the updated priority order (Phase-1-style retrieval work is **done**):

| Priority | Upgrade | Effort | Impact | Moves To |
|:--------:|---------|:------:|:------:|:--------:|
| ~~1–4~~ | ~~Chunk overlap, re-ranking, hybrid, query rewrite~~ | — | — | **Done (Advanced RAG)** |
| 1 | Collect feedback & generate training pairs for fine-tuning | Medium | High | ML-enhanced |
| 2 | Fine-tune embeddings (domain adaptation) | High | High | ML-enhanced |
| 3 | Add retrieval validation | Medium | Medium | CRAG |
| 4 | Expand feedback-driven quality scoring & re-chunking hints | Medium | Medium | ML-enhanced |
| 5 | Add knowledge graph / modular routing | Very High | High | Modular |

Each of these is explored in detail in [Chapter 5 — ML & Future Roadmap](ch5-ml-roadmap.md).

---

## Summary

> Jarvis sits at **Level 2 (Advanced RAG)** for retrieval **with a proto-Agentic shell**. The
> retrieval stack includes hybrid BM25+vector (RRF), cross-encoder re-ranking, chunk overlap,
> LLM query rewriting, and feedback-weighted ranking. The agent layer adds auto-RAG, entity-aware
> search, tool calling, streaming, and sessions.
>
> The highest-impact **next** steps are **embedding fine-tuning**, richer **training data** from
> feedback, and **retrieval validation (CRAG)**—not another pass on basic dense-only search.

---

*Next: [Chapter 3 — Vector Search & Embeddings Deep Dive](ch3-vector-search-explained.md)*
