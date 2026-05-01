"""Evaluation dataset management for RAG quality measurement.

Stores query -> expected relevant chunks mappings used to compute
retrieval metrics (MRR, recall@k, precision@k).
"""
from dataclasses import dataclass
from typing import Optional

from datasets import Dataset, Features, Sequence, Value, concatenate_datasets


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
