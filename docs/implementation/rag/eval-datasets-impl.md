# RAG Evaluation & Dataset Management

> Implementation documentation for the HF `datasets` integration — evaluation harness + data management tools.

## What Changes for Users?

**Current state: Nothing changes in the user-facing search workflow.**

When a user types a question in the Search UI or Agent, the flow remains:
`query → embed → vector search + BM25 → rerank → display results`

The `datasets` integration is a **developer/maintenance tool**, not a user-facing feature. It answers the question: *"Is our search actually good? Is it getting better or worse over time?"*

### Who benefits and how?

| Persona | Benefit |
|---------|---------|
| **Developer (you)** | Can objectively measure if a code change improves or hurts search quality |
| **Future automation** | Eval metrics can trigger alerts if quality drops after reindex |
| **End user (indirect)** | Better search quality over time because improvements are measurable |

### When would users notice a difference?

Users benefit **indirectly** when you use the eval tool to:
1. Compare embedding models → switch to one with higher recall → better search results
2. Tune chunking strategy → measure precision improvement → more relevant chunks shown
3. Adjust reranking → verify MRR improves → first result is more often correct

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
