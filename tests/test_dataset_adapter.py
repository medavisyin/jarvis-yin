import json
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))

from dataset_adapter import (
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
