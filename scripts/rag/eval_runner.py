"""Evaluation runner — executes queries from the eval dataset against
the RAG pipeline and computes retrieval quality metrics.
"""
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Callable

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

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
