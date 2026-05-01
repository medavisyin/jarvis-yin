import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))

from eval_runner import run_evaluation, EvalReport
from eval_dataset import create_eval_dataset, add_eval_example, EvalExample


@pytest.fixture
def eval_dataset():
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
        return [
            {"id": rid, "text": f"text for {rid}", "score": 0.9 - i * 0.1}
            for i, rid in enumerate(results)
        ]
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
