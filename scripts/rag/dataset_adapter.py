"""Adapter between Jarvis .rag-store.json and HuggingFace Dataset objects.

Enables structured data management: filtering, statistics, export,
and conversion of the RAG vector store.
"""
import json
from typing import Optional

from datasets import Dataset


PAYLOAD_FIELDS = [
    "title", "text", "source", "item_type", "date",
    "parent_title", "difficulty", "author",
]


def snapshot_to_dataset(
    snapshot_data: dict, include_vectors: bool = True
) -> Dataset:
    """Convert a parsed snapshot dict to a HF Dataset."""
    from datasets import Features, Value, Sequence

    points = snapshot_data.get("points", [])
    records = []
    for pt in points:
        row = {"id": str(pt["id"])}
        if include_vectors:
            row["vector"] = pt.get("vector", [])
        payload = pt.get("payload", {})
        for field in PAYLOAD_FIELDS:
            row[field] = str(payload.get(field, "") or "")
        records.append(row)

    feature_dict = {"id": Value("string")}
    if include_vectors:
        feature_dict["vector"] = Sequence(Value("float32"))
    for field in PAYLOAD_FIELDS:
        feature_dict[field] = Value("string")

    return Dataset.from_list(records, features=Features(feature_dict))


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
