# Implementation Plan: Advanced RAG Upgrades

> Concrete, step-by-step plan to upgrade Jarvis from Naive RAG to Advanced RAG.
> Each task includes the exact files to change, code patterns, and acceptance criteria.

---

## Implementation Status

> **All 4 tasks completed** (April 2026). See the implementation details below.

| Task | Status | Implemented In |
|------|:------:|---------------|
| 1. Chunk Overlap | **Done** | All 5 indexers (`index_briefing.py`, `index_codebase.py`, `index_custom.py`, `index_confluence.py`, `index_confluence_user.py`) |
| 2. BM25 Hybrid Search | **Done** | `bm25_index.py` (new), `search_ui.py`, `agent.py` |
| 3. Cross-Encoder Re-Ranking | **Done** | `reranker.py` (new), `search_ui.py` |
| 4. LLM Query Rewriting | **Done** | `agent.py`, `search_ui.py` (details in Task 4 note below) |

### New Files Created
| File | Purpose |
|------|---------|
| `scripts/rag/bm25_index.py` | BM25 keyword search index using `rank_bm25` |
| `scripts/rag/reranker.py` | Cross-encoder re-ranker using `ms-marco-MiniLM-L-6-v2` |
| `scripts/rag/feedback_store.py` | User feedback collection and aggregation |

### Additional Enhancements (Beyond Plan)
- **Pipeline Visibility**: Search UI shows RAG pipeline stages, hit counts, and timing
- **Score Breakdown**: Each result shows vector_score, rerank_score, feedback_score
- **Human-in-the-Loop Scoring**: Thumbs up/down buttons on search results for manual feedback
- **Auto-feedback**: Expanding a chunk automatically records a positive signal
- **Search UI query rewrite**: `pipeline_info` includes `original_query` / `rewritten_query`; UI shows “Query Rewrite” with struck-through original and blue rewritten text
- **Reranker resilience**: `reranker.py` and `search_ui.py` degrade gracefully if `ms-marco-MiniLM-L-6-v2` or the reranker call fails

---

## Goal

Move Jarvis from **Level 1 (Naive RAG)** to **Level 2 (Advanced RAG)** by adding:
1. Chunk overlap
2. BM25 hybrid search
3. Cross-encoder re-ranking
4. LLM query rewriting

**Expected outcome:** 25-40% improvement in retrieval precision on domain-specific queries.

---

## Task 1: Chunk Overlap

**Priority:** Highest | **Effort:** 2-4 hours | **Impact:** Medium

### What to Change

**File:** `scripts/rag/index_briefing.py` — function `_chunk_text()`

### Current Code
```python
def _chunk_text(text: str, max_chars: int = 500) -> List[str]:
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks if chunks else [text[:max_chars]]
```

### Target Code
```python
def _chunk_text(text: str, max_chars: int = 500, overlap: int = 100) -> List[str]:
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    prev_tail = ""
    for para in paragraphs:
        candidate = (prev_tail + "\n\n" + para).strip() if prev_tail and not current else para
        if not current:
            current = candidate
            continue
        if len(current) + len(para) > max_chars and current:
            chunks.append(current.strip())
            # Keep the last `overlap` chars as context for the next chunk
            prev_tail = current[-overlap:] if len(current) > overlap else current
            current = prev_tail + "\n\n" + para
        else:
            current = current + "\n\n" + para
    if current.strip():
        chunks.append(current.strip())
    return chunks if chunks else [text[:max_chars]]
```

### Also Update
- `scripts/rag/index_codebase.py` — apply overlap to doc/config chunking
- `scripts/rag/index_custom.py` — apply overlap to markdown/text chunking
- `scripts/rag/index_confluence.py` — apply overlap to wiki page chunking

### Acceptance Criteria
- [x] `_chunk_text("A"*300 + "\n\n" + "B"*300, max_chars=500, overlap=100)` produces chunks where the second chunk starts with the last 100 chars of the first
- [x] Run `reindex_all.py --force` successfully
- [x] Total chunk count increases by ~10-15% (expected from overlap)
- [x] Search quality spot-check: queries that previously missed split concepts now find them

### After Implementation
```bash
python scripts/rag/reindex_all.py --force-briefings
```

---

## Task 2: BM25 Hybrid Search

**Priority:** High | **Effort:** 1-2 days | **Impact:** High

### New Dependency
```bash
pip install rank-bm25
```

### Architecture

```
Query
  ├── Vector Search (Qdrant) ──→ Top 20 results with cosine scores
  │
  ├── BM25 Search (in-memory) ─→ Top 20 results with BM25 scores
  │
  └── Reciprocal Rank Fusion ──→ Merged Top 10 results
```

### Files to Change

**New file:** `scripts/rag/bm25_index.py`
```python
"""BM25 keyword index that runs alongside Qdrant vector search."""
import json
from rank_bm25 import BM25Okapi

SNAPSHOT_PATH = "C:/reports/ai/.rag-store.json"

_bm25 = None
_corpus_ids = None

def _tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercase tokenizer."""
    return text.lower().split()

def get_bm25():
    global _bm25, _corpus_ids
    if _bm25 is None:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        corpus = []
        _corpus_ids = []
        for p in data["points"]:
            text = p["payload"].get("text", "") + " " + p["payload"].get("title", "")
            corpus.append(_tokenize(text))
            _corpus_ids.append(p["id"])
        _bm25 = BM25Okapi(corpus)
    return _bm25, _corpus_ids

def bm25_search(query: str, top_k: int = 20) -> list[tuple[str, float]]:
    """Return list of (point_id, bm25_score) tuples."""
    bm25, ids = get_bm25()
    tokens = _tokenize(query)
    scores = bm25.get_scores(tokens)
    top_indices = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
    return [(ids[i], float(scores[i])) for i in top_indices if scores[i] > 0]

def reset():
    global _bm25, _corpus_ids
    _bm25 = None
    _corpus_ids = None
```

**Modify:** `scripts/rag/search_ui.py` — `/api/search` endpoint
```python
# After vector search, also do BM25 search, then fuse
from bm25_index import bm25_search, reset as bm25_reset

def reciprocal_rank_fusion(vector_results, bm25_results, k=60):
    """Merge two ranked lists using RRF. k=60 is standard."""
    scores = {}
    for rank, r in enumerate(vector_results):
        rid = r["id"]
        scores[rid] = scores.get(rid, 0) + 1.0 / (k + rank + 1)
    for rank, (pid, _) in enumerate(bm25_results):
        scores[pid] = scores.get(pid, 0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])
```

**Modify:** `scripts/rag/agent.py` — `_vector_search` and `_auto_rag_search`

### Acceptance Criteria
- [x] Query "FHIR-R4" returns results containing the exact string (BM25 catches it)
- [x] Query "healthcare interoperability" still returns FHIR results (vector catches it)
- [x] Hybrid results are better than either alone on 10 test queries
- [x] BM25 index loads in < 5 seconds
- [x] No regression on existing search quality

---

## Task 3: Cross-Encoder Re-Ranking

**Priority:** High | **Effort:** 1 day | **Impact:** High

### New Dependency
```bash
pip install sentence-transformers  # already installed, just use CrossEncoder
```

### Architecture

```
Hybrid Search (Task 2) → Top 20 candidates
    │
    ▼
Cross-Encoder Re-Ranking → Top 5 final results
    (scores each query+document pair together)
```

### Files to Change

**New file:** `scripts/rag/reranker.py`
```python
"""Cross-encoder re-ranker for search results."""
from sentence_transformers import CrossEncoder

_reranker = None

def get_reranker():
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512)
    return _reranker

def rerank(query: str, results: list[dict], top_k: int = 5) -> list[dict]:
    """Re-rank results using cross-encoder. Returns top_k best results."""
    if not results:
        return results
    reranker = get_reranker()
    pairs = [(query, r.get("text", "")[:400]) for r in results]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(results, scores), key=lambda x: -x[1])
    return [r for r, s in ranked[:top_k]]
```

**Modify:** `scripts/rag/search_ui.py` — `/api/search` endpoint
```python
# After hybrid fusion, re-rank the top 20 down to top_k
from reranker import rerank
final_results = rerank(query, fused_top_20, top_k=top_k)
```

**Modify:** `scripts/rag/agent.py` — `_auto_rag_search`

### Performance Note
Cross-encoder is ~50ms per pair on CPU. For 20 candidates: ~1 second total. Acceptable for search, may be too slow for auto-RAG (add only to search_ui.py first, then optionally to agent.py).

### Graceful degradation (current behavior)
If **`cross-encoder/ms-marco-MiniLM-L-6-v2`** cannot be loaded (for example, offline without a cached model), **`reranker.py`** logs a warning and returns the candidate list unchanged. **`search_ui.py`** also catches broader exceptions around the reranker call so search still completes with fusion order.

### Acceptance Criteria
- [x] Re-ranked results are measurably better on 10 test queries (manual evaluation)
- [x] Re-ranking adds < 2 seconds to search latency
- [x] Model loads in < 10 seconds on first use
- [x] No regression on simple queries

---

## Task 4: LLM Query Rewriting

**Priority:** Medium | **Effort:** 1 day | **Impact:** Medium

### Architecture

```
User Query: "what's that thing about the new feature?"
    │
    ▼
LLM Rewrite (qwen3:1.7b, fast): "recent feature development updates P4M"
    │
    ▼
Hybrid Search + Re-Ranking
```

### Implementation Note (Current)

Task 4 logic lives in **`agent.py`** for the chat auto-RAG path and in **`search_ui.py`** for the standalone Search UI, so vague queries get consistent rewriting behavior in both servers. The Search UI uses Ollama **`/api/chat`** with **`qwen3:1.7b`** and **`think: false`** (see `search-ui-impl.md`).

### Files to Change

**Modify:** `scripts/rag/agent.py` — add to `_auto_rag_search`
```python
def _rewrite_query(user_query: str) -> str:
    """Use a small fast model to rewrite vague queries."""
    prompt = (
        "Rewrite this search query to be specific and searchable. "
        "The knowledge base contains AI briefings, Java code docs, "
        "Confluence wiki pages, and medical imaging (DICOM/FHIR) docs.\n\n"
        f"Original: {user_query}\n"
        "Rewritten:"
    )
    try:
        resp = ollama.generate(model="qwen3:1.7b", prompt=prompt,
                               options={"num_predict": 50, "num_ctx": 256})
        rewritten = resp["response"].strip().split("\n")[0]
        if len(rewritten) > 10:
            return rewritten
    except Exception:
        pass
    return user_query
```

**Also modify:** `scripts/rag/search_ui.py` — run the same style of vague-query detection and LLM rewrite **before** hybrid retrieval (Ollama **`/api/chat`**, model **`qwen3:1.7b`**, **`think: false`**), populate **`pipeline_info.original_query`** / **`pipeline_info.rewritten_query`**, and surface a **Query Rewrite** line in the pipeline UI (see `search-ui-impl.md`).

### When to Rewrite
Only rewrite if the query is vague (short, contains pronouns, no technical terms):
```python
def _should_rewrite(query: str) -> bool:
    vague_signals = ["that thing", "the stuff", "what's", "something about",
                     "you know", "the other", "last time"]
    return (len(query.split()) < 6 or
            any(v in query.lower() for v in vague_signals))
```

### Acceptance Criteria
- [x] "what's that thing Jan mentioned?" gets rewritten to something searchable
- [x] Clear queries like "FHIR R4 Patient resource" are NOT rewritten
- [x] Rewriting adds < 3 seconds (using qwen3:1.7b)
- [x] No regression on clear queries

---

## Implementation Order (Completed)

All tasks were implemented in a single sprint (April 2026):
- Task 1 (Chunk Overlap) — Applied to all 5 indexers with 100-char default overlap
- Task 2 (BM25 Hybrid) — New `bm25_index.py` module + RRF fusion in both servers
- Task 3 (Re-Ranking) — New `reranker.py` module + integration in `search_ui.py`
- Task 4 (Query Rewriting) — Integrated into `agent.py` auto-RAG pipeline and `search_ui.py` `/api/search` pipeline

## Verification Plan

After all 4 tasks, run this evaluation:

| Test Query | Expected Improvement |
|-----------|---------------------|
| "FHIR-R4" | BM25 catches exact match (was missed by vector-only) |
| "what Jan worked on" | Query rewrite + entity search finds wiki pages |
| "DICOM routing configuration" | Re-ranking promotes the most relevant chunk |
| "P4M authentication flow" | Overlap ensures split concepts are found |
| "latest AI news about transformers" | Hybrid catches both semantic + keyword matches |

---

## Files Created/Modified Summary

| File | Action | Task |
|------|--------|:----:|
| `scripts/rag/index_briefing.py` | Modify `_chunk_text()` | 1 |
| `scripts/rag/index_codebase.py` | Modify chunking | 1 |
| `scripts/rag/index_custom.py` | Modify chunking | 1 |
| `scripts/rag/index_confluence.py` | Modify chunking | 1 |
| `scripts/rag/bm25_index.py` | **New file** | 2 |
| `scripts/rag/search_ui.py` | Add hybrid + RRF + rewrite + reranker error handling | 2, 3, 4 |
| `scripts/rag/agent.py` | Add hybrid + rewrite | 2, 4 |
| `scripts/rag/reranker.py` | **New file** | 3 |

## New Dependencies

```
rank-bm25>=0.2.2    # BM25 keyword search (Task 2)
sentence-transformers   # CrossEncoder for re-ranking (Task 3, already installed)
# cross-encoder model auto-downloads on first use (Task 3)
```
