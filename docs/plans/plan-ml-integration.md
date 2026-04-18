# Implementation Plan: Machine Learning Integration

> Step-by-step plan to add ML capabilities to Jarvis — from feedback collection
> to fine-tuned embeddings to self-evaluating retrieval.

---

## Implementation Status

| Task | Status | Notes |
|------|:------:|-------|
| 1. Feedback Collection | **Done** | `feedback_store.py` created, `/api/feedback` endpoint on both servers |
| 2. Feedback-Weighted Ranking | **Done** | Integrated into `search_ui.py` search pipeline |
| 3. Training Data Generation | Pending | Waiting for sufficient feedback data accumulation |
| 4. Embedding Fine-Tuning | Pending | Depends on Task 3 |
| 5. Retrieval Self-Evaluation | Pending | Query rewriting (from Advanced RAG plan) partially covers this |

---

## Goal

Transform Jarvis from a **static retrieval system** into a **learning system** that improves over time through:
1. User feedback collection
2. Feedback-weighted ranking
3. Domain-specific embedding fine-tuning
4. Retrieval quality self-evaluation

**Prerequisite:** Complete the [Advanced RAG Plan](plan-advanced-rag.md) first (Tasks 1-3 at minimum).

---

## Task 1: Feedback Collection Infrastructure

**Priority:** Highest | **Effort:** 2-3 days | **Impact:** Enables all subsequent ML tasks

### What to Build

A lightweight feedback system that tracks how users interact with search results.

### Architecture

```
User interacts with Search UI
    │
    ├── Expands a chunk → implicit positive signal
    ├── Views full document → strong positive signal
    ├── Copies text → strongest positive signal
    ├── Searches again (reformulates) → negative signal for previous results
    │
    ▼
Feedback API → feedback-store.json
    │
    ▼
Periodic aggregation → chunk quality scores
```

### New File: `scripts/rag/feedback_store.py`

> **Implemented** — `feedback_store.py` includes additional features beyond the plan:
> - Thread-safe file I/O with `Lock`
> - Event decay for entries older than 90 days (50% weight)
> - Manual scoring support via thumbs up/down buttons in the Search UI
> - `get_stats()` function for feedback analytics

```python
"""Feedback collection and aggregation for RAG quality improvement."""
import json
import os
import time
from threading import Lock

FEEDBACK_PATH = "C:/reports/ai/.rag-feedback.json"
_lock = Lock()

def _load():
    if os.path.exists(FEEDBACK_PATH):
        with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"events": [], "chunk_scores": {}}

def _save(data):
    with open(FEEDBACK_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def record_event(query: str, chunk_id: str, action: str, position: int):
    """Record a user interaction event.
    action: 'expand', 'view_doc', 'copy', 'reformulate'
    position: rank position in results (0-based)
    """
    weights = {"expand": 1.0, "view_doc": 2.0, "copy": 3.0, "reformulate": -1.0}
    with _lock:
        data = _load()
        data["events"].append({
            "query": query,
            "chunk_id": chunk_id,
            "action": action,
            "position": position,
            "weight": weights.get(action, 0),
            "timestamp": time.time(),
        })
        _save(data)

def get_chunk_score(chunk_id: str) -> float:
    """Get aggregated quality score for a chunk (0.0 to 1.0)."""
    data = _load()
    return data.get("chunk_scores", {}).get(chunk_id, 0.5)

def aggregate_scores():
    """Recompute chunk quality scores from all events."""
    data = _load()
    scores = {}
    counts = {}
    for event in data["events"]:
        cid = event["chunk_id"]
        scores[cid] = scores.get(cid, 0) + event["weight"]
        counts[cid] = counts.get(cid, 0) + 1
    # Normalize to 0-1 range
    chunk_scores = {}
    for cid in scores:
        raw = scores[cid] / counts[cid]
        chunk_scores[cid] = max(0.0, min(1.0, (raw + 3) / 6))  # map [-3,3] to [0,1]
    data["chunk_scores"] = chunk_scores
    _save(data)
    return chunk_scores
```

### Modify: `scripts/rag/search_ui.py`

Add feedback API endpoint:
```python
@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    data = request.get_json() or {}
    record_event(
        query=data.get("query", ""),
        chunk_id=data.get("chunk_id", ""),
        action=data.get("action", ""),
        position=data.get("position", 0),
    )
    return jsonify({"recorded": True})
```

Add JavaScript tracking to the HTML template:
```javascript
// Track chunk expansion
function toggleChunk(id) {
  // ... existing code ...
  if (el.style.display === 'block') {
    fetch('/api/feedback', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        query: lastQuery,
        chunk_id: id,
        action: 'expand',
        position: parseInt(id.split('-')[1]) || 0
      })
    });
  }
}
```

### Acceptance Criteria
- [x] Feedback events are recorded to `.rag-feedback.json`
- [x] Each event has query, chunk_id, action, position, weight, timestamp
- [x] `aggregate_scores()` produces per-chunk quality scores
- [x] No performance impact on search (feedback is fire-and-forget)

---

## Task 2: Feedback-Weighted Ranking

**Priority:** High | **Effort:** 1-2 days | **Impact:** Medium

### What to Build

Blend vector similarity scores with historical feedback scores.

> **Implemented** — The Search UI now shows:
> - Pipeline info box with stage-by-stage details (Vector → BM25+RRF → Rerank)
> - Per-result score breakdown (vector_score, rerank_score, feedback_score)
> - Thumbs up/down buttons for explicit human feedback
> - Auto-feedback on chunk expansion

### Modify: `scripts/rag/search_ui.py` — `/api/search`

```python
from feedback_store import get_chunk_score

# After getting results from Qdrant (and optionally re-ranking):
for result in results:
    feedback_score = get_chunk_score(result["id"])
    # Blend: 80% vector similarity + 20% historical feedback
    result["final_score"] = 0.8 * result["score"] + 0.2 * feedback_score

results.sort(key=lambda r: -r["final_score"])
```

### Tuning Parameters
- `alpha = 0.8` (vector weight) — start conservative, increase feedback weight as more data accumulates
- Minimum 10 events per chunk before feedback affects ranking
- Decay old events: events older than 90 days get 50% weight

### Acceptance Criteria
- [x] Chunks that users frequently expand rank higher over time
- [x] New chunks (no feedback) are unaffected (default score 0.5)
- [x] Ranking blend is configurable via constants
- [x] Works correctly with < 10 events (falls back to pure vector score)

---

## Task 3: Training Data Generation

**Priority:** High | **Effort:** 3-5 days | **Impact:** Enables Task 4

### What to Build

Generate labeled training pairs for embedding fine-tuning from three sources:

### Source A: Feedback Data (Best Quality)

```python
def generate_pairs_from_feedback():
    """Convert feedback events into (query, positive_doc, negative_doc) triplets."""
    data = _load()
    triplets = []
    # Group events by query
    by_query = {}
    for event in data["events"]:
        q = event["query"]
        by_query.setdefault(q, []).append(event)

    for query, events in by_query.items():
        positives = [e for e in events if e["weight"] > 0]
        negatives = [e for e in events if e["weight"] < 0]
        # Also: chunks shown but never interacted with = weak negatives
        for pos in positives:
            for neg in negatives:
                triplets.append({
                    "query": query,
                    "positive": get_chunk_text(pos["chunk_id"]),
                    "negative": get_chunk_text(neg["chunk_id"]),
                })
    return triplets
```

### Source B: LLM-Generated Pairs (Medium Quality, High Volume)

```python
def generate_synthetic_pairs(chunks, model="qwen3:1.7b", n=500):
    """Ask LLM to generate questions that each chunk answers."""
    pairs = []
    for chunk in random.sample(chunks, min(n, len(chunks))):
        prompt = (
            "Generate a natural question that this text answers. "
            "Only output the question, nothing else.\n\n"
            f"Text: {chunk['text'][:300]}\n"
            "Question:"
        )
        resp = ollama.generate(model=model, prompt=prompt,
                               options={"num_predict": 50})
        question = resp["response"].strip()
        if len(question) > 10:
            pairs.append({"query": question, "positive": chunk["text"]})
    return pairs
```

### Source C: Manual Curation (Highest Quality)

Create a JSON file `C:/reports/ai/.training-pairs.json`:
```json
[
  {
    "query": "DICOM routing configuration",
    "positive": "The PACS connector forwards studies based on routing rules...",
    "negative": "JavaScript React component for the dashboard..."
  },
  {
    "query": "P4M authentication flow",
    "positive": "P4M uses Spring Security with JWT tokens for API auth...",
    "negative": "The AI briefing pipeline collects data from 15 sources..."
  }
]
```

### Target: 500-1000 Training Pairs
| Source | Expected Pairs | Quality |
|--------|:-:|:-:|
| Feedback data | 100-300 (after 2-4 weeks of use) | High |
| LLM-generated | 300-500 | Medium |
| Manual curation | 50-100 | Highest |

### Acceptance Criteria
- [ ] Script generates triplets from feedback data
- [ ] Script generates synthetic pairs from chunks via LLM
- [ ] Manual pairs file format is documented
- [ ] Combined dataset has 500+ pairs
- [ ] Pairs are deduplicated and validated

---

## Task 4: Embedding Fine-Tuning

**Priority:** High | **Effort:** 1-2 weeks | **Impact:** Very High

### What to Build

Fine-tune `all-MiniLM-L6-v2` on your domain data to produce `jarvis-minilm-finetuned`.

### New File: `scripts/rag/finetune_embeddings.py`

```python
"""Fine-tune the embedding model on domain-specific training pairs."""
import json
from sentence_transformers import (
    SentenceTransformer, InputExample, losses, evaluation
)
from torch.utils.data import DataLoader

MODEL_NAME = "all-MiniLM-L6-v2"
OUTPUT_DIR = "C:/reports/ai/models/jarvis-minilm-finetuned"
TRAINING_DATA = "C:/reports/ai/.training-pairs.json"

def load_training_data():
    with open(TRAINING_DATA, "r", encoding="utf-8") as f:
        pairs = json.load(f)

    examples = []
    for p in pairs:
        if "negative" in p:
            # Triplet: (anchor, positive, negative)
            examples.append(InputExample(
                texts=[p["query"], p["positive"], p["negative"]]
            ))
        else:
            # Pair: (query, positive) with similarity 1.0
            examples.append(InputExample(
                texts=[p["query"], p["positive"]], label=1.0
            ))
    return examples

def train():
    model = SentenceTransformer(MODEL_NAME)
    examples = load_training_data()
    print(f"Training on {len(examples)} examples")

    # Split 90/10 for train/eval
    split = int(len(examples) * 0.9)
    train_examples = examples[:split]
    eval_examples = examples[split:]

    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=16)

    # Use TripletLoss for triplets, CosineSimilarityLoss for pairs
    has_triplets = any(len(e.texts) == 3 for e in train_examples)
    if has_triplets:
        train_loss = losses.TripletLoss(model)
    else:
        train_loss = losses.CosineSimilarityLoss(model)

    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=3,
        warmup_steps=int(len(train_dataloader) * 0.1),
        output_path=OUTPUT_DIR,
        show_progress_bar=True,
    )
    print(f"Model saved to {OUTPUT_DIR}")

if __name__ == "__main__":
    train()
```

### Modify: All Indexers and Servers

Change model loading to prefer fine-tuned model:
```python
def _get_model():
    global _model
    if _model is None:
        finetuned = "C:/reports/ai/models/jarvis-minilm-finetuned"
        model_name = finetuned if os.path.isdir(finetuned) else "all-MiniLM-L6-v2"
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(model_name)
    return _model
```

### After Fine-Tuning: Full Reindex Required
```bash
# The new model produces different vectors — all chunks must be re-embedded
python scripts/rag/reindex_all.py --force
```

### Evaluation
Compare before/after on 20 test queries:
```python
def evaluate(model, test_queries):
    """Compute Mean Reciprocal Rank on test queries."""
    mrr = 0
    for q in test_queries:
        results = search(q, model)
        # Find rank of the known-relevant document
        for rank, r in enumerate(results):
            if r["id"] == q["relevant_id"]:
                mrr += 1.0 / (rank + 1)
                break
    return mrr / len(test_queries)
```

### Acceptance Criteria
- [ ] Fine-tuned model saved to `C:/reports/ai/models/jarvis-minilm-finetuned/`
- [ ] Model loads successfully in all indexers and servers
- [ ] MRR improves by >= 10% on test queries vs base model
- [ ] No catastrophic forgetting (general queries still work)
- [ ] Full reindex completes successfully with new model

---

## Task 5: Retrieval Self-Evaluation (Corrective RAG)

**Priority:** Medium | **Effort:** 1 week | **Impact:** High

### What to Build

Before injecting context into the LLM, evaluate whether the retrieved results are actually relevant.

### Modify: `scripts/rag/agent.py` — `_auto_rag_search`

```python
def _evaluate_retrieval(query: str, results: list[dict]) -> str:
    """Evaluate retrieval quality. Returns 'good', 'marginal', or 'poor'."""
    if not results:
        return "poor"

    top_score = results[0].get("score", 0)
    if top_score > 0.7:
        return "good"
    if top_score > 0.4:
        return "marginal"

    # For marginal cases, ask LLM to validate
    context_preview = results[0].get("text", "")[:200]
    prompt = (
        f"Is this context relevant to the question? Answer only YES or NO.\n"
        f"Question: {query}\n"
        f"Context: {context_preview}\n"
        f"Answer:"
    )
    try:
        resp = ollama.generate(model="qwen3:1.7b", prompt=prompt,
                               options={"num_predict": 5, "num_ctx": 256})
        if "YES" in resp["response"].upper():
            return "marginal"
    except Exception:
        pass
    return "poor"

# In _auto_rag_search:
quality = _evaluate_retrieval(user_query, all_results)
if quality == "poor":
    # Try query rewriting and search again
    rewritten = _rewrite_query(user_query)
    all_results = _vector_search(rewritten, top_k=5)
    quality = _evaluate_retrieval(user_query, all_results)
if quality == "poor":
    # Give up on RAG, let LLM answer from its own knowledge
    context_block = "(No relevant context found in knowledge base.)"
```

### Acceptance Criteria
- [ ] Queries with good retrieval (score > 0.7) proceed normally
- [ ] Queries with poor retrieval trigger query rewriting retry
- [ ] If retry also fails, LLM answers without context (no hallucinated context)
- [ ] Evaluation adds < 3 seconds to response time
- [ ] Log evaluation outcomes for monitoring

---

## Implementation Timeline

```
Month 1:  Task 1 (Feedback Collection) + Task 2 (Feedback-Weighted Ranking)
          └── Start collecting data immediately
          └── Feedback weighting can use even small amounts of data

Month 2:  Task 3 (Training Data Generation)
          └── By now, 2-4 weeks of feedback data accumulated
          └── Generate synthetic pairs to supplement
          └── Manually curate 50-100 high-quality pairs

Month 3:  Task 4 (Embedding Fine-Tuning)
          └── Train on combined dataset (500+ pairs)
          └── Evaluate and iterate
          └── Full reindex with fine-tuned model

Month 4:  Task 5 (Corrective RAG)
          └── Builds on all previous improvements
          └── Self-evaluating retrieval with fallback strategies
```

## New Files Summary

| File | Purpose | Task |
|------|---------|:----:|
| `scripts/rag/feedback_store.py` | Feedback collection + aggregation | 1 |
| `scripts/rag/finetune_embeddings.py` | Embedding fine-tuning script | 4 |
| `C:/reports/ai/.rag-feedback.json` | Feedback event store | 1 |
| `C:/reports/ai/.training-pairs.json` | Manual training pairs | 3 |
| `C:/reports/ai/models/jarvis-minilm-finetuned/` | Fine-tuned model | 4 |

## New Dependencies

```
# No new pip packages needed — all use existing sentence-transformers + ollama
# rank-bm25 is from the Advanced RAG plan
```
