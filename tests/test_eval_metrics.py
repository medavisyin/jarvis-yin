import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))

from eval_metrics import (
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
