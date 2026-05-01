# RAG Evaluation & Dataset Management

> Implementation documentation for the HF `datasets` integration — evaluation harness + data management tools + user-facing features.

## What Changes for Users?

**User-facing features built on the datasets foundation:**

| Feature | Where | Description |
|---------|-------|-------------|
| Confidence Indicator | Search UI + Agent | Colored badge (High/Medium/Low) showing result reliability |
| Similar Questions | Search UI + Agent | "Try also:" suggestions when confidence is not high |
| Data Explorer | Search UI (Explorer tab) | Visual overview of all indexed knowledge |
| Feedback Loop | Search UI | "Was this helpful?" collects eval data from users |

When a user types a question, the enriched flow is:
`query → embed → vector search + BM25 → rerank → confidence score → display results + confidence badge + suggestions`

### Developer tools (backend evaluation harness)

The `datasets` library itself powers a **developer/maintenance tool** that answers: *"Is our search actually good? Is it getting better or worse over time?"*

| Persona | Benefit |
|---------|---------|
| **Developer (you)** | Can objectively measure if a code change improves or hurts search quality |
| **Future automation** | Eval metrics can trigger alerts if quality drops after reindex |
| **End user (direct)** | Sees confidence badges, gets related suggestions, can provide feedback |
| **End user (indirect)** | Better search quality over time because improvements are measurable |

## Why Datasets Are Important to RAG Search

RAG (Retrieval-Augmented Generation) quality depends entirely on **finding the right chunks**. Without measurement, you're flying blind:

### The Problem Without Evaluation
- You change chunking strategy → did search get better or worse? No way to know.
- You swap embedding models → is `bge-small` actually better than `MiniLM`? Can't tell.
- You add 10,000 new chunks → did you dilute the relevance of existing results? Unknown.
- A user reports "search doesn't find X" → is it one edge case or a systemic issue? Guessing.

### How Datasets Solve This
The `datasets` library provides the **structured data layer** that makes RAG measurable:

1. **Ground truth creation**: Store known-good query → relevant chunk pairs as a dataset
2. **Automated evaluation**: Run queries through the pipeline and compute precision/recall/MRR
3. **A/B comparison**: Run the same eval before and after any change → objective delta
4. **Feedback capture**: User clicks "helpful" → automatically generates new ground truth
5. **Data introspection**: See what's indexed, find gaps, identify over-representation

### The Virtuous Cycle
```
User searches → Confidence shown → User gives feedback → Eval dataset grows
    ↑                                                              ↓
    └──── Developer improves pipeline ←── Eval metrics reveal issues ←──┘
```

Each user interaction makes the next evaluation more reliable, which leads to better search, which leads to more positive interactions.

## Overview

Integrates the Hugging Face `datasets` library into Jarvis for two purposes:
1. **Evaluation**: Measure RAG retrieval quality with standard IR metrics
2. **Data Management**: Browse, filter, export, and inspect the RAG store as structured data

## Architecture

```
.rag-store.json (snapshot)
       │
       ├──► dataset_adapter.py ──► HF Dataset (view, filter, export, CSV)
       │
       ├──► eval_dataset.py ──► Evaluation Dataset (query + expected chunks)
       │
       └──► eval_runner.py ──► search_fn() ──► eval_metrics.py ──► EvalReport
```

## Files

| File | Purpose |
|------|---------|
| `scripts/rag/dataset_adapter.py` | Convert between .rag-store.json and HF Dataset |
| `scripts/rag/eval_dataset.py` | Evaluation dataset schema and CRUD |
| `scripts/rag/eval_metrics.py` | Precision@k, recall@k, MRR computation |
| `scripts/rag/eval_runner.py` | Run eval queries through RAG pipeline |
| `scripts/rag/seed_eval_data.py` | Bootstrap eval dataset from seed queries |
| `scripts/rag/eval_cli.py` | CLI for all eval/data management operations |
| `data/eval/eval-seed.json` | Human-curated seed evaluation queries |
| `tests/test_dataset_adapter.py` | Adapter tests (5 tests) |
| `tests/test_eval_dataset.py` | Eval dataset tests (4 tests) |
| `tests/test_eval_metrics.py` | Metrics tests (9 tests) |
| `tests/test_eval_runner.py` | Runner tests (3 tests) |

## CLI Usage

```bash
cd scripts/rag

# View store statistics
python eval_cli.py stats

# Browse chunks with filters
python eval_cli.py view --source briefing
python eval_cli.py view --query "vector search" --limit 10
python eval_cli.py view --type wiki_page --csv output.csv

# Export as HF Dataset (for notebooks, pandas, etc.)
python eval_cli.py export --no-vectors

# Bootstrap evaluation dataset
python eval_cli.py seed

# Run evaluation
python eval_cli.py eval --k 5 --output eval-report.json
```

## Evaluation Workflow

1. **Seed**: Run `python eval_cli.py seed` to create initial eval dataset from `data/eval/eval-seed.json`
2. **Review**: Check the auto-matched `relevant_ids` are correct (the seed script picks top-3 vector search results as candidates)
3. **Evaluate**: Run `python eval_cli.py eval` to get precision/recall/MRR scores
4. **Iterate**: After changes (new chunking, model upgrade, reranking), re-run eval to compare

## Metrics

| Metric | Description |
|--------|-------------|
| **Precision@k** | What fraction of top-k results are relevant |
| **Recall@k** | What fraction of relevant docs appear in top-k |
| **MRR** | 1/position of first relevant result (higher = relevant docs ranked higher) |

## Data Management Features

- **Filter by source**: `briefing`, `codebase`, `confluence`, `custom`
- **Filter by type**: `news`, `readme`, `wiki_page`, `method`, etc.
- **Text search**: Search within title and content
- **CSV export**: For Excel/spreadsheet analysis
- **HF Dataset export**: For Python notebooks (`ds.to_pandas()`)

## Dependencies

Added to `scripts/rag/requirements-rag.txt`:
- `datasets>=2.18.0` (HuggingFace Datasets library)
- Transitive: `pyarrow`, `dill`, `multiprocess`, `xxhash`, `fsspec`

## User-Facing Feature Implementation

### A) Confidence Indicator
- **Backend**: `search_ui.py` adds `confidence` field per result and `query_confidence` to API response
- **Agent**: `rag_engine.py` adds `confidence` to each source; `index.html` shows colored dots
- **Thresholds**: score >= 0.55 = High, >= 0.35 = Medium, < 0.35 = Low
- **Query-level**: High requires top_score >= 0.55 AND avg_score >= 0.35

### B) Similar Questions
- **Backend**: `GET /api/suggest?query=...` does low-threshold vector search, returns top-5 unique titles
- **Frontend**: Appears as clickable chips when query confidence is not "high"
- **Agent**: `agent_loop.py` includes suggestions in `answer_done` SSE event

### C) Data Explorer
- **Backend**: `GET /api/explorer-stats` returns source/type/date breakdown + top 20 titles
- **Frontend**: 4th tab "Explorer" in Search UI with CSS bar charts and timeline

### D) Feedback Loop
- **Backend**: `POST /api/feedback/helpful` stores eval candidates via `feedback_store.py`
- **Frontend**: "Did you find what you needed?" prompt after every search result set
- **Data flow**: User feedback → eval_candidates → can be promoted to eval dataset

## Connection to ML Integration Plan

This module connects to `plan-ml-integration.md` Task 3 (Training Data Generation):
- Evaluation dataset can feed fine-tuning pipelines
- Feedback-weighted chunks (from `feedback_store.py`) can auto-generate positive eval examples
- The `dataset_adapter.py` provides the bridge between Jarvis snapshot format and standard ML data formats

## Testing

```bash
# Run all eval-related tests
python -m pytest tests/test_dataset_adapter.py tests/test_eval_dataset.py tests/test_eval_metrics.py tests/test_eval_runner.py -v
```

21 tests total, all passing.
