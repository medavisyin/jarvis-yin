# HF Datasets Integration Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Integrate the Hugging Face `datasets` library into Jarvis for RAG evaluation (measuring retrieval quality) and data management (versioned, structured access to indexed content).

**Architecture:** Two modules — (1) an evaluation harness that uses `datasets` to store question-answer-context triples and compute retrieval metrics (MRR, recall@k, precision@k), and (2) a data management layer that exports/imports the RAG store as a HF Dataset for inspection, filtering, and versioning. Both integrate with the existing `.rag-store.json` snapshot.

**Tech Stack:** `datasets` (HuggingFace), `evaluate` (optional, for metrics), existing `sentence-transformers`, `qdrant_client`, `rank_bm25`

---

## Status

| Task | Status | Notes |
|------|:------:|-------|
| 1. Install & Verify | **Done** | `datasets` 4.8.5 installed, import verified |
| 2. RAG Store Dataset Adapter | **Done** | `dataset_adapter.py` — 5 tests passing |
| 3. Evaluation Dataset Schema | **Done** | `eval_dataset.py` — 4 tests passing |
| 4. Retrieval Metrics Module | **Done** | `eval_metrics.py` — 9 tests passing |
| 5. Evaluation Runner | **Done** | `eval_runner.py` — 3 tests passing |
| 6. Seed Evaluation Data | **Done** | `seed_eval_data.py` + `data/eval/eval-seed.json` (8 queries) |
| 7. CLI Commands | **Done** | `eval_cli.py` — export, stats, view, eval, seed |

---

## Task 1: Install & Verify

**Files:**
- Modify: `scripts/rag/requirements-rag.txt` (create if not exists)
- Test: manual Python import check

**Step 1: Install the datasets library**

Run:
```bash
pip install datasets
```

**Step 2: Create requirements file for RAG dependencies**

Create `scripts/rag/requirements-rag.txt`:
```text
sentence-transformers>=2.2.0
qdrant-client>=1.7.0
rank-bm25>=0.2.2
datasets>=2.18.0
pypdf>=3.0.0
```

**Step 3: Verify import works**

Run:
```bash
python -c "from datasets import Dataset, Features, Value, Sequence; print('datasets OK')"
```
Expected: `datasets OK`

---

## Task 2: RAG Store Dataset Adapter

**Files:**
- Create: `scripts/rag/dataset_adapter.py`
- Test: `tests/test_dataset_adapter.py`

**Purpose:** Convert between `.rag-store.json` (Jarvis snapshot format) and HF `Dataset` objects for inspection, filtering, export.

**Step 1: Write the failing test**

Create `tests/test_dataset_adapter.py`:
```python
import json
import os
import tempfile
import pytest
from scripts.rag.dataset_adapter import (
    snapshot_to_dataset,
    dataset_to_snapshot,
    load_snapshot_as_dataset,
)


@pytest.fixture
def sample_snapshot(tmp_path):
    data = {
        "count": 2,
        "points": [
            {
                "id": "abc-001",
                "vector": [0.1] * 384,
                "payload": {
                    "title": "Test Document 1",
                    "text": "This is a test chunk about machine learning.",
                    "source": "briefing",
                    "item_type": "news",
                    "date": "2026-04-30",
                },
            },
            {
                "id": "abc-002",
                "vector": [0.2] * 384,
                "payload": {
                    "title": "Test Document 2",
                    "text": "Another chunk about vector databases.",
                    "source": "codebase",
                    "item_type": "readme",
                    "date": "2026-04-30",
                },
            },
        ],
    }
    path = tmp_path / ".rag-store.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_snapshot_to_dataset_returns_dataset(sample_snapshot):
    ds = load_snapshot_as_dataset(sample_snapshot)
    assert len(ds) == 2
    assert "title" in ds.column_names
    assert "text" in ds.column_names
    assert "source" in ds.column_names
    assert "id" in ds.column_names


def test_snapshot_to_dataset_preserves_content(sample_snapshot):
    ds = load_snapshot_as_dataset(sample_snapshot)
    assert ds[0]["title"] == "Test Document 1"
    assert "machine learning" in ds[0]["text"]
    assert ds[1]["source"] == "codebase"


def test_dataset_to_snapshot_roundtrip(sample_snapshot, tmp_path):
    ds = load_snapshot_as_dataset(sample_snapshot)
    out_path = str(tmp_path / "out.json")
    dataset_to_snapshot(ds, out_path)

    with open(out_path, "r", encoding="utf-8") as f:
        restored = json.load(f)
    assert restored["count"] == 2
    assert len(restored["points"]) == 2
    assert restored["points"][0]["payload"]["title"] == "Test Document 1"


def test_snapshot_to_dataset_without_vectors(sample_snapshot):
    ds = load_snapshot_as_dataset(sample_snapshot, include_vectors=False)
    assert "vector" not in ds.column_names
    assert "text" in ds.column_names


def test_filter_by_source(sample_snapshot):
    ds = load_snapshot_as_dataset(sample_snapshot)
    filtered = ds.filter(lambda x: x["source"] == "briefing")
    assert len(filtered) == 1
    assert filtered[0]["title"] == "Test Document 1"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dataset_adapter.py -v`
Expected: FAIL with import errors

**Step 3: Write implementation**

Create `scripts/rag/dataset_adapter.py`:
```python
"""Adapter between Jarvis .rag-store.json and HuggingFace Dataset objects.

Enables structured data management: filtering, statistics, export,
and conversion of the RAG vector store.
"""
import json
from typing import Optional

from datasets import Dataset


def snapshot_to_dataset(
    snapshot_data: dict, include_vectors: bool = True
) -> Dataset:
    """Convert a parsed snapshot dict to a HF Dataset."""
    points = snapshot_data.get("points", [])
    records = []
    for pt in points:
        row = {"id": pt["id"]}
        if include_vectors:
            row["vector"] = pt.get("vector", [])
        payload = pt.get("payload", {})
        row["title"] = payload.get("title", "")
        row["text"] = payload.get("text", "")
        row["source"] = payload.get("source", "")
        row["item_type"] = payload.get("item_type", "")
        row["date"] = payload.get("date", "")
        row["parent_title"] = payload.get("parent_title", "")
        row["difficulty"] = payload.get("difficulty", "")
        row["author"] = payload.get("author", "")
        records.append(row)
    return Dataset.from_list(records)


def load_snapshot_as_dataset(
    snapshot_path: str, include_vectors: bool = True
) -> Dataset:
    """Load .rag-store.json and return as a HF Dataset."""
    with open(snapshot_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return snapshot_to_dataset(data, include_vectors=include_vectors)


def dataset_to_snapshot(
    ds: Dataset,
    output_path: str,
    vectors: Optional[list[list[float]]] = None,
) -> None:
    """Convert a HF Dataset back to .rag-store.json format.

    If the dataset contains a 'vector' column, uses it.
    Otherwise, pass vectors separately or they'll be empty.
    """
    points = []
    for i, row in enumerate(ds):
        vec = row.get("vector", [])
        if not vec and vectors and i < len(vectors):
            vec = vectors[i]
        payload = {
            k: v
            for k, v in row.items()
            if k not in ("id", "vector") and v
        }
        points.append({
            "id": row["id"],
            "vector": vec,
            "payload": payload,
        })
    snapshot = {"count": len(points), "points": points}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dataset_adapter.py -v`
Expected: All 5 tests PASS

---

## Task 3: Evaluation Dataset Schema

**Files:**
- Create: `scripts/rag/eval_dataset.py`
- Test: `tests/test_eval_dataset.py`

**Purpose:** Define the evaluation dataset schema — question/query + expected relevant chunk IDs + optional ground-truth answer. This is the "gold standard" test set.

**Step 1: Write the failing test**

Create `tests/test_eval_dataset.py`:
```python
import tempfile
import pytest
from scripts.rag.eval_dataset import (
    create_eval_dataset,
    add_eval_example,
    load_eval_dataset,
    EvalExample,
)


def test_create_empty_eval_dataset():
    ds = create_eval_dataset()
    assert len(ds) == 0
    assert "query" in ds.column_names
    assert "relevant_ids" in ds.column_names
    assert "answer" in ds.column_names
    assert "category" in ds.column_names


def test_add_eval_example():
    ds = create_eval_dataset()
    example = EvalExample(
        query="What is RAG?",
        relevant_ids=["chunk-001", "chunk-002"],
        answer="Retrieval-Augmented Generation combines search with LLM.",
        category="concept",
    )
    ds = add_eval_example(ds, example)
    assert len(ds) == 1
    assert ds[0]["query"] == "What is RAG?"
    assert ds[0]["relevant_ids"] == ["chunk-001", "chunk-002"]


def test_save_and_load_eval_dataset(tmp_path):
    ds = create_eval_dataset()
    ds = add_eval_example(
        ds,
        EvalExample(
            query="How does vector search work?",
            relevant_ids=["vec-001"],
            answer="By finding nearest neighbors in embedding space.",
            category="technical",
        ),
    )
    path = str(tmp_path / "eval_set")
    ds.save_to_disk(path)

    loaded = load_eval_dataset(path)
    assert len(loaded) == 1
    assert loaded[0]["query"] == "How does vector search work?"


def test_multiple_examples():
    ds = create_eval_dataset()
    for i in range(5):
        ds = add_eval_example(
            ds,
            EvalExample(
                query=f"Query {i}",
                relevant_ids=[f"id-{i}"],
                answer=f"Answer {i}",
                category="test",
            ),
        )
    assert len(ds) == 5
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eval_dataset.py -v`
Expected: FAIL with import errors

**Step 3: Write implementation**

Create `scripts/rag/eval_dataset.py`:
```python
"""Evaluation dataset management for RAG quality measurement.

Stores query -> expected relevant chunks mappings used to compute
retrieval metrics (MRR, recall@k, precision@k).
"""
from dataclasses import dataclass, field
from typing import Optional

from datasets import Dataset, Features, Sequence, Value


EVAL_FEATURES = Features(
    {
        "query": Value("string"),
        "relevant_ids": Sequence(Value("string")),
        "answer": Value("string"),
        "category": Value("string"),
        "difficulty": Value("string"),
        "notes": Value("string"),
    }
)


@dataclass
class EvalExample:
    query: str
    relevant_ids: list[str]
    answer: str = ""
    category: str = ""
    difficulty: str = "medium"
    notes: str = ""


def create_eval_dataset() -> Dataset:
    """Create an empty evaluation dataset with the standard schema."""
    return Dataset.from_dict(
        {
            "query": [],
            "relevant_ids": [],
            "answer": [],
            "category": [],
            "difficulty": [],
            "notes": [],
        },
        features=EVAL_FEATURES,
    )


def add_eval_example(ds: Dataset, example: EvalExample) -> Dataset:
    """Append a single evaluation example to the dataset."""
    from datasets import concatenate_datasets

    new_row = Dataset.from_dict(
        {
            "query": [example.query],
            "relevant_ids": [example.relevant_ids],
            "answer": [example.answer],
            "category": [example.category],
            "difficulty": [example.difficulty],
            "notes": [example.notes],
        },
        features=EVAL_FEATURES,
    )
    return concatenate_datasets([ds, new_row])


def load_eval_dataset(path: str) -> Dataset:
    """Load a saved evaluation dataset from disk."""
    return Dataset.load_from_disk(path)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eval_dataset.py -v`
Expected: All 4 tests PASS

---

## Task 4: Retrieval Metrics Module

**Files:**
- Create: `scripts/rag/eval_metrics.py`
- Test: `tests/test_eval_metrics.py`

**Purpose:** Compute standard retrieval quality metrics given retrieved results vs. expected relevant IDs.

**Step 1: Write the failing test**

Create `tests/test_eval_metrics.py`:
```python
import pytest
from scripts.rag.eval_metrics import (
    precision_at_k,
    recall_at_k,
    mrr,
    compute_metrics,
)


def test_precision_at_k_all_relevant():
    retrieved = ["a", "b", "c"]
    relevant = {"a", "b", "c"}
    assert precision_at_k(retrieved, relevant, k=3) == 1.0


def test_precision_at_k_none_relevant():
    retrieved = ["x", "y", "z"]
    relevant = {"a", "b"}
    assert precision_at_k(retrieved, relevant, k=3) == 0.0


def test_precision_at_k_partial():
    retrieved = ["a", "x", "b", "y"]
    relevant = {"a", "b"}
    assert precision_at_k(retrieved, relevant, k=4) == 0.5


def test_recall_at_k_all_found():
    retrieved = ["a", "b", "c", "d"]
    relevant = {"a", "b"}
    assert recall_at_k(retrieved, relevant, k=4) == 1.0


def test_recall_at_k_partial():
    retrieved = ["a", "x", "y"]
    relevant = {"a", "b", "c"}
    assert recall_at_k(retrieved, relevant, k=3) == pytest.approx(1 / 3)


def test_mrr_first_position():
    retrieved = ["a", "b", "c"]
    relevant = {"a"}
    assert mrr(retrieved, relevant) == 1.0


def test_mrr_second_position():
    retrieved = ["x", "a", "b"]
    relevant = {"a"}
    assert mrr(retrieved, relevant) == 0.5


def test_mrr_not_found():
    retrieved = ["x", "y", "z"]
    relevant = {"a"}
    assert mrr(retrieved, relevant) == 0.0


def test_compute_metrics_batch():
    results = [
        (["a", "b", "c"], {"a", "c"}),
        (["x", "a", "y"], {"a"}),
    ]
    metrics = compute_metrics(results, k=3)
    assert "precision@3" in metrics
    assert "recall@3" in metrics
    assert "mrr" in metrics
    assert 0 <= metrics["precision@3"] <= 1.0
    assert 0 <= metrics["recall@3"] <= 1.0
    assert 0 <= metrics["mrr"] <= 1.0
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eval_metrics.py -v`
Expected: FAIL with import errors

**Step 3: Write implementation**

Create `scripts/rag/eval_metrics.py`:
```python
"""Retrieval quality metrics for RAG evaluation.

Computes precision@k, recall@k, and MRR (Mean Reciprocal Rank)
against a gold-standard set of relevant document IDs.
"""


def precision_at_k(
    retrieved_ids: list[str], relevant_ids: set[str], k: int
) -> float:
    """Fraction of top-k retrieved results that are relevant."""
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for rid in top_k if rid in relevant_ids)
    return hits / len(top_k)


def recall_at_k(
    retrieved_ids: list[str], relevant_ids: set[str], k: int
) -> float:
    """Fraction of relevant docs found in top-k results."""
    if not relevant_ids:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = sum(1 for rid in top_k if rid in relevant_ids)
    return hits / len(relevant_ids)


def mrr(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """Mean Reciprocal Rank: 1/position of first relevant result."""
    for i, rid in enumerate(retrieved_ids, start=1):
        if rid in relevant_ids:
            return 1.0 / i
    return 0.0


def compute_metrics(
    results: list[tuple[list[str], set[str]]], k: int = 5
) -> dict[str, float]:
    """Compute averaged metrics over a batch of query results.

    Args:
        results: list of (retrieved_ids, relevant_ids) tuples
        k: cutoff for precision/recall
    """
    if not results:
        return {f"precision@{k}": 0.0, f"recall@{k}": 0.0, "mrr": 0.0}

    precisions = []
    recalls = []
    mrrs = []
    for retrieved, relevant in results:
        precisions.append(precision_at_k(retrieved, relevant, k))
        recalls.append(recall_at_k(retrieved, relevant, k))
        mrrs.append(mrr(retrieved, relevant))

    n = len(results)
    return {
        f"precision@{k}": sum(precisions) / n,
        f"recall@{k}": sum(recalls) / n,
        "mrr": sum(mrrs) / n,
    }
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eval_metrics.py -v`
Expected: All 9 tests PASS

---

## Task 5: Evaluation Runner

**Files:**
- Create: `scripts/rag/eval_runner.py`
- Test: `tests/test_eval_runner.py`

**Purpose:** Run evaluation queries through the actual RAG pipeline, compare results against ground truth, and produce a metrics report.

**Step 1: Write the failing test**

Create `tests/test_eval_runner.py`:
```python
import json
import pytest
from unittest.mock import patch, MagicMock
from scripts.rag.eval_runner import run_evaluation, EvalReport


@pytest.fixture
def eval_dataset():
    from scripts.rag.eval_dataset import create_eval_dataset, add_eval_example, EvalExample

    ds = create_eval_dataset()
    ds = add_eval_example(
        ds,
        EvalExample(
            query="What is vector search?",
            relevant_ids=["vec-001", "vec-002"],
            category="concept",
        ),
    )
    ds = add_eval_example(
        ds,
        EvalExample(
            query="How does BM25 work?",
            relevant_ids=["bm25-001"],
            category="technical",
        ),
    )
    return ds


def make_mock_search(mapping: dict):
    """Create a mock search function that returns predefined results."""
    def mock_search(query, top_k=5, **kwargs):
        results = mapping.get(query, [])
        return [{"id": rid, "text": f"text for {rid}", "score": 0.9 - i * 0.1}
                for i, rid in enumerate(results)]
    return mock_search


def test_run_evaluation_returns_report(eval_dataset):
    search_fn = make_mock_search({
        "What is vector search?": ["vec-001", "other-001", "vec-002"],
        "How does BM25 work?": ["bm25-001", "other-002"],
    })
    report = run_evaluation(eval_dataset, search_fn, k=5)
    assert isinstance(report, EvalReport)
    assert report.metrics["mrr"] > 0
    assert report.metrics["precision@5"] > 0
    assert report.metrics["recall@5"] > 0
    assert report.num_queries == 2


def test_run_evaluation_perfect_retrieval(eval_dataset):
    search_fn = make_mock_search({
        "What is vector search?": ["vec-001", "vec-002"],
        "How does BM25 work?": ["bm25-001"],
    })
    report = run_evaluation(eval_dataset, search_fn, k=5)
    assert report.metrics["recall@5"] == 1.0
    assert report.metrics["mrr"] == 1.0


def test_run_evaluation_no_hits(eval_dataset):
    search_fn = make_mock_search({
        "What is vector search?": ["wrong-001", "wrong-002"],
        "How does BM25 work?": ["wrong-003"],
    })
    report = run_evaluation(eval_dataset, search_fn, k=5)
    assert report.metrics["recall@5"] == 0.0
    assert report.metrics["mrr"] == 0.0
    assert report.metrics["precision@5"] == 0.0
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eval_runner.py -v`
Expected: FAIL with import errors

**Step 3: Write implementation**

Create `scripts/rag/eval_runner.py`:
```python
"""Evaluation runner — executes queries from the eval dataset against
the RAG pipeline and computes retrieval quality metrics.
"""
import json
import time
from dataclasses import dataclass, field
from typing import Callable

from datasets import Dataset

from eval_metrics import compute_metrics, precision_at_k, recall_at_k, mrr


@dataclass
class EvalReport:
    metrics: dict[str, float]
    num_queries: int
    per_query: list[dict] = field(default_factory=list)
    timestamp: str = ""
    k: int = 5

    def to_dict(self) -> dict:
        return {
            "metrics": self.metrics,
            "num_queries": self.num_queries,
            "per_query": self.per_query,
            "timestamp": self.timestamp,
            "k": self.k,
        }

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)


def run_evaluation(
    eval_ds: Dataset,
    search_fn: Callable,
    k: int = 5,
) -> EvalReport:
    """Run all eval queries through search_fn and compute metrics.

    Args:
        eval_ds: HF Dataset with columns: query, relevant_ids, category
        search_fn: callable(query, top_k=k) -> list[dict] with 'id' key
        k: cutoff for precision/recall metrics
    """
    results_batch = []
    per_query = []

    for row in eval_ds:
        query = row["query"]
        relevant = set(row["relevant_ids"])
        search_results = search_fn(query, top_k=k)
        retrieved = [r["id"] for r in search_results]

        results_batch.append((retrieved, relevant))
        per_query.append({
            "query": query,
            "category": row.get("category", ""),
            "retrieved": retrieved,
            "relevant": list(relevant),
            "precision": precision_at_k(retrieved, relevant, k),
            "recall": recall_at_k(retrieved, relevant, k),
            "mrr": mrr(retrieved, relevant),
        })

    metrics = compute_metrics(results_batch, k=k)

    return EvalReport(
        metrics=metrics,
        num_queries=len(eval_ds),
        per_query=per_query,
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        k=k,
    )
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eval_runner.py -v`
Expected: All 3 tests PASS

---

## Task 6: Seed Evaluation Data

**Files:**
- Create: `scripts/rag/seed_eval_data.py`
- Create: `data/eval/eval-seed.json` (human-curated seed questions)

**Purpose:** Provide a starting set of evaluation queries with known-good chunk IDs, bootstrapped from the existing RAG store.

**Step 1: Create seed data file**

Create `data/eval/eval-seed.json`:
```json
[
  {
    "query": "What is RAG and how does it work?",
    "relevant_ids": [],
    "answer": "Retrieval-Augmented Generation combines a retrieval system with an LLM to ground responses in factual documents.",
    "category": "concept",
    "difficulty": "easy",
    "notes": "Populate relevant_ids after indexing by running seed script"
  },
  {
    "query": "How does hybrid search combine vector and BM25?",
    "relevant_ids": [],
    "answer": "Uses Reciprocal Rank Fusion to merge rankings from dense vector similarity and sparse BM25 keyword matching.",
    "category": "technical",
    "difficulty": "medium",
    "notes": "Populate relevant_ids after indexing"
  },
  {
    "query": "What embedding model does Jarvis use?",
    "relevant_ids": [],
    "answer": "all-MiniLM-L6-v2 from sentence-transformers, producing 384-dimensional vectors.",
    "category": "system",
    "difficulty": "easy",
    "notes": "Populate relevant_ids after indexing"
  },
  {
    "query": "How is the cross-encoder reranker used?",
    "relevant_ids": [],
    "answer": "cross-encoder/ms-marco-MiniLM-L-6-v2 scores query-document pairs after initial retrieval to reorder results by relevance.",
    "category": "technical",
    "difficulty": "medium",
    "notes": "Populate relevant_ids after indexing"
  },
  {
    "query": "What data sources are indexed in Jarvis?",
    "relevant_ids": [],
    "answer": "Daily AI briefings, codebase projects, Confluence pages, and custom knowledge files.",
    "category": "system",
    "difficulty": "easy",
    "notes": "Populate relevant_ids after indexing"
  }
]
```

**Step 2: Write seed script**

Create `scripts/rag/seed_eval_data.py`:
```python
"""Bootstrap evaluation dataset by matching seed queries against the live RAG store.

Runs each seed query through vector search and picks top-3 results as
'relevant_ids' candidates. Human review is still needed to confirm/adjust.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from config import REPORTS_ROOT
from eval_dataset import create_eval_dataset, add_eval_example, EvalExample

SEED_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "eval", "eval-seed.json"
)
EVAL_SAVE_PATH = os.path.join(REPORTS_ROOT, "eval-dataset")


def main():
    from rag_engine import get_embed_model, get_qdrant, vector_search

    get_qdrant()

    with open(SEED_PATH, "r", encoding="utf-8") as f:
        seeds = json.load(f)

    ds = create_eval_dataset()
    for seed in seeds:
        results = vector_search(seed["query"], top_k=3)
        candidate_ids = [r["id"] for r in results] if results else []

        if seed["relevant_ids"]:
            ids = seed["relevant_ids"]
        else:
            ids = candidate_ids

        ds = add_eval_example(
            ds,
            EvalExample(
                query=seed["query"],
                relevant_ids=ids,
                answer=seed.get("answer", ""),
                category=seed.get("category", ""),
                difficulty=seed.get("difficulty", "medium"),
                notes=seed.get("notes", ""),
            ),
        )
        print(f"  [{seed['category']}] {seed['query']}")
        print(f"    -> candidates: {candidate_ids[:3]}")

    ds.save_to_disk(EVAL_SAVE_PATH)
    print(f"\nEval dataset saved to: {EVAL_SAVE_PATH}")
    print(f"Total examples: {len(ds)}")
    print("\nREVIEW: Check relevant_ids are correct before running evaluation.")


if __name__ == "__main__":
    main()
```

**Step 3: Run the seed script (after RAG store is populated)**

Run: `cd scripts/rag && python seed_eval_data.py`
Expected: Prints candidate IDs for each query, saves eval dataset to disk.

---

## Task 7: CLI Commands

**Files:**
- Create: `scripts/rag/eval_cli.py`

**Purpose:** Provide CLI access to: (1) export RAG store as Dataset, (2) run evaluation, (3) show metrics summary.

**Step 1: Write the CLI**

Create `scripts/rag/eval_cli.py`:
```python
"""CLI for RAG evaluation and dataset management.

Usage:
    python eval_cli.py export [--no-vectors] [--output PATH]
    python eval_cli.py stats
    python eval_cli.py eval [--k 5] [--output PATH]
    python eval_cli.py seed
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from config import REPORTS_ROOT, SNAPSHOT_PATH


def cmd_export(args):
    """Export RAG store as a HF Dataset."""
    from dataset_adapter import load_snapshot_as_dataset

    include_vectors = not args.no_vectors
    ds = load_snapshot_as_dataset(SNAPSHOT_PATH, include_vectors=include_vectors)
    out = args.output or os.path.join(REPORTS_ROOT, "rag-dataset-export")
    ds.save_to_disk(out)
    print(f"Exported {len(ds)} chunks to: {out}")
    print(f"Columns: {ds.column_names}")


def cmd_stats(args):
    """Show statistics about the RAG store."""
    from dataset_adapter import load_snapshot_as_dataset

    ds = load_snapshot_as_dataset(SNAPSHOT_PATH, include_vectors=False)
    print(f"Total chunks: {len(ds)}")
    print(f"\nBy source:")
    sources = {}
    for row in ds:
        src = row.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
    for src, count in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"  {src}: {count}")

    print(f"\nBy item_type:")
    types = {}
    for row in ds:
        t = row.get("item_type", "unknown")
        types[t] = types.get(t, 0) + 1
    for t, count in sorted(types.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")


def cmd_eval(args):
    """Run evaluation against the RAG pipeline."""
    from datasets import Dataset
    from eval_runner import run_evaluation
    from rag_engine import get_qdrant, vector_search

    get_qdrant()

    eval_path = os.path.join(REPORTS_ROOT, "eval-dataset")
    if not os.path.exists(eval_path):
        print("No eval dataset found. Run 'seed' first.")
        sys.exit(1)

    eval_ds = Dataset.load_from_disk(eval_path)
    print(f"Running evaluation on {len(eval_ds)} queries (k={args.k})...\n")

    def search_fn(query, top_k=5):
        return vector_search(query, top_k=top_k)

    report = run_evaluation(eval_ds, search_fn, k=args.k)

    print("=" * 50)
    print("  RAG Evaluation Results")
    print("=" * 50)
    print(f"  Queries evaluated: {report.num_queries}")
    print(f"  Precision@{args.k}:     {report.metrics[f'precision@{args.k}']:.3f}")
    print(f"  Recall@{args.k}:        {report.metrics[f'recall@{args.k}']:.3f}")
    print(f"  MRR:              {report.metrics['mrr']:.3f}")
    print("=" * 50)

    if args.output:
        report.save(args.output)
        print(f"\nFull report saved to: {args.output}")


def cmd_seed(args):
    """Run seed script to bootstrap eval dataset."""
    import seed_eval_data
    seed_eval_data.main()


def main():
    parser = argparse.ArgumentParser(description="RAG Evaluation & Data Management CLI")
    sub = parser.add_subparsers(dest="command")

    p_export = sub.add_parser("export", help="Export RAG store as HF Dataset")
    p_export.add_argument("--no-vectors", action="store_true")
    p_export.add_argument("--output", type=str)

    p_stats = sub.add_parser("stats", help="Show RAG store statistics")

    p_eval = sub.add_parser("eval", help="Run retrieval evaluation")
    p_eval.add_argument("--k", type=int, default=5)
    p_eval.add_argument("--output", type=str)

    p_seed = sub.add_parser("seed", help="Bootstrap eval dataset from seed queries")

    args = parser.parse_args()
    commands = {
        "export": cmd_export,
        "stats": cmd_stats,
        "eval": cmd_eval,
        "seed": cmd_seed,
    }
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

**Step 2: Test CLI commands**

Run: `cd scripts/rag && python eval_cli.py stats`
Expected: Prints chunk counts by source and item_type.

Run: `cd scripts/rag && python eval_cli.py export --no-vectors --output C:/reports/ai/rag-export-test`
Expected: Exports dataset without vectors.

---

## Integration Notes

- **No changes to existing RAG pipeline** — this is purely additive (new files only)
- **Evaluation dataset persists at** `{REPORTS_ROOT}/eval-dataset/` (Arrow format via HF `save_to_disk`)
- **Seed data source** `data/eval/eval-seed.json` is human-curated and version-controlled
- **Future additions:** After accumulating feedback data (from `feedback_store.py`), auto-generate eval examples from high-confidence positive feedback events
- **Connects to plan-ml-integration Task 3** (Training Data Generation) — the eval dataset can also feed fine-tuning pipelines

---

## Future Enhancements (not in scope for this plan)

- [ ] Auto-generate eval examples from user feedback signals
- [ ] Category-level metrics breakdown (concept vs. technical vs. system)
- [ ] Temporal evaluation (track metric trends over time as index grows)
- [ ] Integration with `evaluate` library for additional metrics (nDCG, MAP)
- [ ] CI/CD gate: fail build if metrics drop below threshold
