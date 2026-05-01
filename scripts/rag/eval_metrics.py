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
