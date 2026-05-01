import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))

from eval_dataset import (
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
