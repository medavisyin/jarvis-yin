# Chapter 5: Machine Learning & Future Roadmap

> Can Jarvis learn and improve over time? What would it take to add ML?
> This chapter maps out the evolution from static retrieval to a learning system.

---

## The Big Question: Can Jarvis "Learn"?

**Today:** Jarvis still uses **pre-trained embeddings** (no fine-tuning yet), but it is **no longer static at the ranking layer**: feedback collection (thumbs up/down, implicit signals) and feedback-weighted ranking improve results over time. The big remaining learning leap is **embedding fine-tuning** and richer training data—not basic retrieval plumbing.

**The vision:** A system that improves its retrieval quality based on user behavior, fine-tunes its understanding of your domain, and adapts its responses to your preferences.

```
CURRENT STATE                          FUTURE STATE
─────────────                          ────────────
Static retrieval                       Adaptive retrieval
  ↓                                      ↓
Same results every time                Better results over time
  ↓                                      ↓
Generic embeddings                     Domain-tuned embeddings
  ↓                                      ↓
No quality awareness                   Self-evaluating
  ↓                                      ↓
Manual maintenance                     Self-improving
```

---

## Evolution Roadmap (6 Phases)

### Phase 1: Better Retrieval (No ML Required)

**Effort: Low-Medium | Impact: High | Timeline: Days**

**Status (April 2026): Completed.** Chunk overlap (1a), BM25 hybrid search with RRF (1b), cross-encoder re-ranking (1c), and **LLM query rewriting** (same engineering class as retrieval quality; implemented in `agent.py` as `_rewrite_query`) are live in Jarvis.

**Also active:** **Feedback collection** and weighted ranking (see Phase 3 patterns below) are running in production—the roadmap’s “collect feedback” step is underway even as later phases (training-data generation, fine-tuning, corrective RAG) remain.

These improvements mostly don't need *training* new models — just solid engineering (plus optional cross-encoder and BM25 libraries):

#### 1a. Chunk Overlap — **Done**

```python
# Current: no overlap
def _chunk_text(text, max_chars=500):
    # splits at paragraph boundaries, no overlap

# Improved: 100-char overlap
def _chunk_text(text, max_chars=500, overlap=100):
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunks.append(text[start:end])
        start = end - overlap  # overlap with previous chunk
    return chunks
```

**Why it matters:** Concepts that span chunk boundaries are currently lost. Overlap ensures both chunks contain the full concept.

#### 1b. Hybrid Search (BM25 + Vector) — **Done**

```python
# Current: vector only
results = client.query_points(query=embedding, limit=5)

# Improved: vector + keyword, then fuse
from rank_bm25 import BM25Okapi

vector_results = client.query_points(query=embedding, limit=10)
bm25_results = bm25_index.get_top_n(query_tokens, documents, n=10)
fused = reciprocal_rank_fusion(vector_results, bm25_results, k=60)
```

**Why it matters:** Vector search finds semantically similar content. BM25 finds exact keyword matches. Together they cover both "meaning" and "mention."

**Implementation:** Add a BM25 index alongside Qdrant. At query time, search both, then merge results using Reciprocal Rank Fusion (RRF). *(Implemented: `bm25_index.py`, search UI and agent paths.)*

#### 1c. Cross-Encoder Re-Ranking — **Done**

```python
# Current: return Qdrant results directly
return results[:5]

# Improved: re-rank with a cross-encoder
from sentence_transformers import CrossEncoder
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

# Score each (query, document) pair
pairs = [(query, r["text"]) for r in results[:20]]
scores = reranker.predict(pairs)
reranked = sorted(zip(results[:20], scores), key=lambda x: -x[1])
return [r for r, s in reranked[:5]]
```

**Why it matters:** Bi-encoders (like MiniLM) encode query and document separately — fast but approximate. Cross-encoders look at query+document together — slower but much more accurate. Using a cross-encoder to re-rank the top 20 results into the best 5 can improve precision by 15-30%. *(Implemented: `reranker.py`, `search_ui.py`.)*

---

### Phase 2: Query Intelligence (Light ML)

**Effort: Medium | Impact: Medium | Timeline: Weeks**

#### 2a. LLM Query Rewriting — **Done** *(see also Phase 1 status note above)*

```python
# Before searching, ask the LLM to improve the query
rewrite_prompt = f"""Rewrite this search query to be more specific and searchable.
Original: {user_query}
Context: The knowledge base contains AI briefings, Java code, Confluence wiki pages,
         and medical imaging (DICOM/FHIR) documentation.
Rewritten query:"""

better_query = ollama.generate(model="qwen3:1.7b", prompt=rewrite_prompt)
results = vector_search(better_query)
```

**Example:**
```
Original:  "what's that thing Jan mentioned about the new feature?"
Rewritten: "Jan Loeffler recent Confluence page new feature development"
```

**Why it matters:** Users ask vague questions. The LLM can expand them into precise search queries. This is cheap to implement since Jarvis already has Ollama.

#### 2b. Query Decomposition

```python
# For complex questions, break into sub-queries
decompose_prompt = f"""Break this question into 2-3 simpler search queries:
Question: {user_query}
Sub-queries:"""

sub_queries = ollama.generate(model="qwen3:1.7b", prompt=decompose_prompt)
# Search each sub-query, merge results
all_results = []
for sq in sub_queries:
    all_results.extend(vector_search(sq))
```

**Example:**
```
Original:  "Compare how P4M and Admin App handle authentication"
Sub-query 1: "P4M authentication implementation"
Sub-query 2: "Admin App authentication implementation"
Sub-query 3: "authentication comparison P4M Admin App"
```

---

### Phase 3: Feedback Loop (Real ML Begins)

**Effort: High | Impact: High | Timeline: Months**

This is where Jarvis starts **learning from you**.

**Status (April 2026): Active (partial).** Explicit thumbs and implicit signals are collected; feedback-weighted ranking is in use. Full **training-data pipelines**, **fine-tuned embeddings**, and **corrective RAG** remain future work.

#### 3a. Implicit Feedback Collection — **Active** (collection + API paths live; expand coverage as needed)

Track user behavior without asking explicit questions:

```python
# In the Search UI, track which results users click/expand
@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    data = request.get_json()
    # data = { query, clicked_chunk_id, position, action: "expand"|"view_doc"|"copy" }
    save_feedback(data)

# In the Agent, track which tool results the LLM actually uses
# (appears in the generated answer vs. ignored)
```

**What to track:**
| Signal | Meaning | Weight |
|--------|---------|:------:|
| User expands a chunk | Relevant | +1 |
| User views full document | Very relevant | +2 |
| User copies text | Highly relevant | +3 |
| User searches again (reformulates) | First results were bad | -1 |
| LLM cites a chunk in answer | Relevant | +2 |
| LLM ignores a chunk | Less relevant | -1 |

#### 3b. Feedback-Weighted Re-Ranking — **Active** (blend with vector / pipeline scores in search and agent flows)

Use collected feedback to boost/demote results:

```python
def search_with_feedback(query, results):
    for r in results:
        chunk_id = r["id"]
        # How often was this chunk useful in the past?
        feedback_score = get_feedback_score(chunk_id)
        # Blend vector similarity with historical usefulness
        r["final_score"] = 0.7 * r["vector_score"] + 0.3 * feedback_score
    return sorted(results, key=lambda r: -r["final_score"])
```

**This is the simplest form of ML:** a weighted combination of two signals (vector similarity + historical feedback). No neural network training needed — just statistics.

#### 3c. Feedback-Driven Chunk Quality Scoring

Over time, some chunks prove consistently useful and others are noise:

```python
# After 100+ queries with feedback:
chunk_quality = {
    "chunk_abc": {"shown": 50, "clicked": 35, "quality": 0.70},  # Good chunk
    "chunk_xyz": {"shown": 40, "clicked": 2,  "quality": 0.05},  # Bad chunk - maybe re-chunk?
}
```

Chunks with consistently low quality scores could be flagged for re-chunking or removal.

---

### Phase 4: Fine-Tuned Embeddings (Domain Adaptation)

**Effort: High | Impact: Very High | Timeline: Months**

The biggest single improvement possible: make the embedding model understand **your domain**.

#### Why Fine-Tune?

The default `all-MiniLM-L6-v2` was trained on general English text. It doesn't know that:
- "DICOM" and "medical imaging protocol" are closely related
- "P4M" and "PACS connector" belong to the same product
- "FHIR R4" and "HL7 interoperability standard" mean similar things
- "Vaadin" and "Java web UI framework" are the same concept

After fine-tuning on your data, the model would understand these domain-specific relationships.

#### How to Fine-Tune

```python
from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader

model = SentenceTransformer("all-MiniLM-L6-v2")

# Training data: pairs of (text_a, text_b, similarity_score)
# Generated from your feedback data or manually curated
train_examples = [
    InputExample(texts=["DICOM routing", "study forwarding in PACS"], label=0.9),
    InputExample(texts=["DICOM routing", "JavaScript styling"], label=0.1),
    InputExample(texts=["P4M authentication", "login flow in P4M Next"], label=0.85),
    # ... 200-500 examples is enough for significant improvement
]

train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=16)
train_loss = losses.CosineSimilarityLoss(model)

model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    epochs=3,
    warmup_steps=10,
)
model.save("models/jarvis-minilm-finetuned")
```

#### Where to Get Training Data

| Source | Method | Quality |
|--------|--------|:-------:|
| Feedback loop (Phase 3) | Clicked pairs = similar, skipped = dissimilar | High |
| Existing search logs | Queries + clicked results | Medium |
| LLM-generated | Ask GPT to generate similar/dissimilar pairs from your docs | Medium |
| Manual curation | You label 200-500 pairs | Highest |

**Expected improvement:** 10-20% better recall on domain-specific queries. Research shows even 200-500 labeled examples can significantly improve domain-specific retrieval.

#### After Fine-Tuning: Re-Index Everything

```bash
# The new model produces different vectors, so all chunks must be re-embedded
python reindex_all.py --force
```

---

### Phase 5: Self-Evaluating RAG (Corrective RAG)

**Effort: Very High | Impact: High | Timeline: Months**

#### Retrieval Validation

Before injecting context into the LLM, check if the retrieved results are actually relevant:

```python
def validate_retrieval(query, results):
    if not results or results[0]["score"] < 0.4:
        return "low_confidence"

    # Ask a small LLM: "Is this context relevant to the question?"
    validation_prompt = f"""Rate relevance (1-5):
    Question: {query}
    Context: {results[0]['text'][:200]}
    Rating:"""

    rating = ollama.generate(model="qwen3:1.7b", prompt=validation_prompt)

    if int(rating) < 3:
        return "irrelevant"
    return "good"
```

#### Adaptive Strategy

```python
quality = validate_retrieval(query, results)

if quality == "good":
    # Normal RAG flow
    answer = generate_with_context(query, results)
elif quality == "low_confidence":
    # Try query rewriting and search again
    rewritten = rewrite_query(query)
    results = vector_search(rewritten)
    answer = generate_with_context(query, results)
elif quality == "irrelevant":
    # Fall back to LLM's own knowledge (no context injection)
    answer = generate_without_context(query)
```

This is **Corrective RAG (CRAG)** — the system evaluates its own retrieval and adapts.

---

### Phase 6: Full Agentic RAG (Long-Term Vision)

**Effort: Very High | Impact: Transformative | Timeline: 6-12 months**

The ultimate evolution: Jarvis becomes a truly autonomous agent that:

```
User: "Prepare a summary of what changed in P4M this sprint,
       cross-reference with Jira tickets, and flag any risks."

Agent thinks:
  1. "I need sprint dates" → Check Jira for current sprint
  2. "I need code changes" → Git log for P4M repos
  3. "I need ticket details" → Jira API for sprint tickets
  4. "I need context" → RAG search for P4M architecture docs
  5. "Cross-reference" → Match commits to tickets
  6. "Flag risks" → Search for past incidents related to changed areas
  7. "Synthesize" → Generate structured report

Agent executes all 7 steps autonomously, retrying if any step fails,
and produces a comprehensive report.
```

#### What This Requires

| Capability | Current State | Needed |
|-----------|:------------:|:------:|
| Multi-step planning | Partial (ReAct loop) | Full planning with backtracking |
| Dynamic retrieval | Single-pass auto-RAG | Iterative retrieve-reason-retrieve |
| Self-reflection | None | Evaluate own answers, retry if poor |
| Memory across sessions | Chat history only | Semantic long-term memory |
| Multi-agent coordination | Single agent | Specialized sub-agents |
| Learning from outcomes | None | Track success/failure, adapt strategies |

---

## Implementation Priority Matrix

```
                        HIGH IMPACT
                            │
    ┌───────────────────────┼───────────────────────┐
    │                       │                       │
    │  Hybrid Search        │  Fine-Tune Embeddings │
    │  Re-Ranking           │  Feedback Loop        │
    │  (Phase 1b, 1c)       │  (Phase 3, 4)         │
    │                       │                       │
LOW ├───────────────────────┼───────────────────────┤ HIGH
EFFORT│                     │                       │ EFFORT
    │                       │                       │
    │  Chunk Overlap        │  Corrective RAG       │
    │  Query Rewriting      │  Full Agentic RAG     │
    │  (Phase 1a, 2a)       │  (Phase 5, 6)         │
    │                       │                       │
    └───────────────────────┼───────────────────────┘
                            │
                        LOW IMPACT
```

**Recommended order (updated April 2026):**
1. ~~Chunk overlap (Phase 1a)~~ — **Done**
2. ~~Cross-encoder re-ranking (Phase 1c)~~ — **Done**
3. ~~BM25 hybrid search (Phase 1b)~~ — **Done**
4. ~~LLM query rewriting (Phase 2a)~~ — **Done**
5. **Grow feedback data + export training pairs** (Phase 3 → 4 bridge) — in progress; more data improves ranking and fine-tuning
6. Fine-tuned embeddings (Phase 4) — 2-4 weeks, biggest single *remaining* improvement
7. Corrective RAG (Phase 5) — 2-4 weeks, self-healing retrieval
8. Full agentic (Phase 6) — ongoing, transformative

---

## Can Jarvis Use "Real" Machine Learning?

**Yes, absolutely.** Here's the spectrum:

| ML Level | What It Means | Jarvis Today | Jarvis Could |
|----------|--------------|:------------:|:------------:|
| **No ML** | Rule-based, static | Chunking, metadata | — |
| **Pre-trained ML** | Use models as-is | Embeddings (MiniLM) | — |
| **Transfer learning** | Fine-tune on your data | — | Fine-tune MiniLM |
| **Online learning** | Learn from feedback in real-time | Feedback-weighted ranking (partial) | Stronger LTR, more signals |
| **Reinforcement learning** | Optimize retrieval strategy via rewards | — | RLHF for retrieval |
| **Self-supervised** | Generate own training data | — | Auto-generate query-doc pairs |

The current system uses **pre-trained ML** (the embedding model) plus **feedback-weighted ranking** (statistics over collected signals). The roadmap above shows how to add **transfer learning** (fine-tuning), richer **online learning**, and **self-supervised** pair generation from your own documents.

---

## Key Takeaways

1. **Jarvis is already using ML** — the embedding model is a neural network trained on 1B+ text pairs. It's just not *learning* from your specific usage yet.

2. **Phase-1-style engineering wins are largely shipped** — Hybrid search, re-ranking, chunk overlap, and query rewriting are in. The next large gains are **fine-tuning** and **more / cleaner feedback-derived training data**.

3. **Feedback is the bridge to ML** — Collection and weighted ranking are **active**; growing signal volume unlocks better adaptive ranking, fine-tuning pairs, and self-evaluation.

4. **Fine-tuning is realistic** — You don't need thousands of examples. 200-500 labeled pairs can meaningfully improve domain-specific retrieval. The SentenceTransformers library makes this straightforward.

5. **Full agentic RAG is the long-term vision** — But it requires all the earlier phases as foundations. Don't skip to Phase 6.

---

*Back to: [Documentation Index](docs-index.md)*
