# Implementation Guide: search_ui.py

## Overview

`search_ui.py` is the Flask-based semantic search interface for the Jarvis RAG store. It lives at `scripts/rag/search_ui.py` (about 1020 lines). The app serves a single-page UI with **embedded HTML/CSS/JS** in the `HTML_TEMPLATE` string (not a separate templates folder), loads the same embedding model and Qdrant snapshot as the indexers, and exposes JSON APIs for search, library browsing, maintenance, and background “index new briefings” jobs. Default listen address: **`127.0.0.1:18888`** (override with `python search_ui.py <port>`).

## Technologies

- **Flask:** `Flask`, `request`, `jsonify`, `render_template_string`
- **sentence-transformers:** query embedding for vector search
- **qdrant-client:** `query_points`, `scroll`, filters (`Filter`, `FieldCondition`, `MatchValue`, `Range`)
- **threading:** background worker for `/api/index-new`
- **stdlib:** `json`, `os`, `re`, `sys`, `time`, `traceback`, `uuid`, among others
- **UI:** one large `HTML_TEMPLATE` constant for zero-asset deployment

## Advanced RAG Modules

The search pipeline now includes several additional modules that enhance retrieval quality:

### BM25 Hybrid Search (`bm25_index.py`)
- Provides keyword-based search alongside vector search
- Uses `rank_bm25` library with a regex tokenizer
- Results merged with vector results via Reciprocal Rank Fusion (RRF, k=60)
- Lazy-loaded with thread safety

### Cross-Encoder Re-Ranking (`reranker.py`)
- Re-ranks the top 20 hybrid search candidates
- Uses `sentence_transformers.CrossEncoder` with `ms-marco-MiniLM-L-6-v2`
- Adds ~1 second latency for significantly better precision when the model is available
- Lazy-loaded model with thread safety
- **Graceful degradation:** If the cross-encoder model cannot be loaded (for example, offline with no cached weights), the module logs a warning and returns candidates **unchanged** instead of failing. `search_ui.py` wraps reranker calls in a broad `try`/`except` so other retrieval errors also fall back to the pre-rerank ordering.

### LLM Query Rewriting (optional, via Ollama)
- For **vague** queries—fewer than five words or phrases that match vague signals (for example, “that thing”, “something about”)—the UI calls **Ollama** at `/api/chat` with model **`qwen3:1.7b`** and **`think: false`** to produce a clearer search string before hybrid retrieval.
- The **original** query is shown **struck through** and the **rewritten** query in **blue** in the pipeline info box.
- If Ollama is unavailable or the call fails, search proceeds with the user’s original query (no hard dependency on an LLM for the app to run).

### Feedback Store (`feedback_store.py`)
- Records user interaction events (expand, copy, view_doc, reformulate, thumbs_up, thumbs_down)
- Stores events in `C:/reports/ai/.rag-feedback.json`
- Provides per-chunk quality scores with time decay (90-day half-life)
- Scores blended into final ranking (80% vector + 20% feedback)

## Architecture

1. **Startup:** Lazy helpers load `SentenceTransformer` and a process-global Qdrant client. The client is backed by an in-memory collection populated from the on-disk snapshot when present (same pattern as other RAG scripts).
2. **GET /** — Renders `HTML_TEMPLATE` with a short stats string from the snapshot metadata.
3. **API layer** — All `/api/*` routes return JSON (except the HTML page). Search and library use Qdrant; delete mutates the JSON snapshot file and clears the cached client so the next request reloads.

There is **no chat/generation LLM** in this service: core retrieval is Qdrant vector search, BM25 hybrid search with RRF fusion, cross-encoder re-ranking (when available), and feedback-weighted blending. **Optional** query rewriting uses a small Ollama model for vague queries only; the server still works without Ollama.

## API reference

### `GET /`

Serves the search UI. Injects `stats` into the template (chunk count summary from the snapshot).

### `GET /api/search`

Semantic search over the collection. The search performs **hybrid retrieval** (vector + BM25) with **Reciprocal Rank Fusion (RRF)** to merge keyword and dense rankings. Results are **re-ranked** with a cross-encoder for higher precision. **Feedback scores** from historical user interactions are **blended into the final ranking** (alongside vector/hybrid signals).

**Query parameters:**

| Parameter | Description |
|-----------|-------------|
| `query` | Required for meaningful results; empty query returns `{ results: [], error: "Empty query" }` |
| `top_k` | Maximum number of hits to return from vector retrieval (passed to Qdrant as `limit`; default `10`) |
| `min_score` | Minimum cosine similarity for vector matches; points below this score are excluded (`score_threshold` on Qdrant query; default `0.5`) |
| `date_from` / `date_to` | Filter on payload `date` (`Range` gte/lte) |
| `source` | Exact match on `source` |
| `difficulty` | Exact match on `difficulty` |
| `item_type` | Exact match on `item_type` |

**Response:** `{ results, query, total, pipeline_info }` where each result includes `title`, `date`, `source`, `difficulty`, `item_type`, `url`, `text`, `score`, `filename`, `parent_title`. The **`pipeline_info`** object summarizes stages (e.g. vector search, BM25, RRF, re-ranking, feedback blending). When a rewrite ran, **`pipeline_info`** also includes **`original_query`** and **`rewritten_query`**; the client shows a **“Query Rewrite”** line (original struck through, rewritten highlighted).

### `POST /api/feedback`

Records a user interaction event for feedback-weighted ranking.

**Request body:**

| Field | Description |
|-------|-------------|
| `query` | The search query |
| `chunk_id` | The chunk that was interacted with |
| `action` | Event type: `expand`, `view_doc`, `copy`, `reformulate` |
| `position` | Rank position of the result (0-based) |

**Response:** `{ recorded: true }`

### `GET /api/document`

Returns chunks belonging to one logical document.

**Query parameters:** `filename` and/or `parent_title` (at least one required).

**Behavior:** `scroll` with `Filter` on those payload fields, up to 500 points; chunks in response order as returned by scroll (not re-sorted by chunk index in all cases).

**Response:** `filename`, `parent_title`, `total_chunks`, `chunks` (each with `title`, `text`, `item_type`, `date`).

### `GET /api/chunk-analysis`

Diagnostics for index composition: scans the collection in pages of 500 via `scroll` and aggregates counts **by `source`** and **by `item_type`**.

**Response:** `{ total, by_source, by_type }`.

### `GET /api/library`

Builds a browsable list of documents by grouping points on `parent_title` or `filename` or `title`.

**Query parameters:** optional `item_type` filter.

**Response:** `{ documents, total_documents, total_chunks }`. Each document entry includes `title`, `date`, `source`, `item_type`, `filename`, `chunks` (count). The full list is built in memory from a complete scroll (no URL pagination parameters).

### `POST /api/delete`

Removes points from the **snapshot JSON file** whose payload matches the given criteria.

**JSON body:** `filename`, `parent_title` (at least one required). Matching logic is implemented in `_matches_delete` (exact payload match rules).

**Response:** `{ removed, remaining }` or error if no snapshot. On success with removals, the in-process Qdrant client is reset to force reload.

### `POST /api/index-new`

Starts a **background thread** (`_run_index_new`) that finds briefing date folders under `REPORTS_ROOT` not yet represented in the store (by scanning existing points’ dates for briefing-like sources), indexes missing dates with `index_briefing.index_date_folder`, then saves the snapshot.

**Response:** `{ job_id, status: "started" }`.

### `GET /api/index-new/<job_id>`

Polls job state from an in-memory `_jobs` dict.

**Response:** `{ status, result, new_items }` or 404 if unknown job.

## Search flow

1. Client sends `GET /api/search?query=...` with optional filters.
2. If the query is vague (short or matches vague-signal phrases), the server may **rewrite** it via Ollama `qwen3:1.7b` (`/api/chat`, `think: false`); otherwise the search string is unchanged. Rewrite details are reflected in `pipeline_info` (`original_query` / `rewritten_query`) and in the UI pipeline box.
3. Server encodes the **effective** query with `SentenceTransformer.encode` and runs Qdrant vector search with optional `Filter`, `limit`, and `score_threshold=min_score`.
4. BM25 keyword search runs over the in-memory index; vector and BM25 lists are fused with RRF (k=60).
5. Top candidates are re-ranked with the cross-encoder when the model loads successfully; on failure, ordering from fusion is kept. Feedback scores from `feedback_store` are blended into final ordering (80% retrieval / 20% feedback).
6. Payload fields are mapped into the JSON result list; `pipeline_info` is attached to the response.

## UI features

- Filter controls wired to the query API (`source`, date range, `item_type`, `difficulty`, `min_score`, `top_k`).
- Library view backed by `/api/library`.
- Chunk analysis view backed by `/api/chunk-analysis`.
- Document drill-down via `/api/document`.
- Delete and “index new” operations for operators maintaining the store.
- Stats line on the home page from snapshot metadata.

## Configuration

Paths and collection names are aligned with `index_briefing` (e.g. `SNAPSHOT_PATH`, `COLLECTION`, `REPORTS_ROOT`, model name)—see the constants at the top of `search_ui.py`. Port: `18888` by default or first CLI argument.

## Design decisions

- **Single-file UI:** Embedding the front end in `HTML_TEMPLATE` avoids static file hosting and keeps deployment to “run one Python file.”
- **GET for search:** Parameters are query-string based, which simplifies browser refreshes and sharing URLs.
- **Snapshot-centric delete:** Delete edits the canonical JSON snapshot and drops the client cache so behavior stays consistent with the file-backed source of truth.
- **Background indexing:** Long-running indexing must not block Flask’s request thread; a daemon thread plus job polling keeps the UX responsive.
- **Optional rewrite-only LLM:** Chat answers are not generated here; optional Ollama-based rewriting improves vague queries while keeping the service usable when Ollama is down.
