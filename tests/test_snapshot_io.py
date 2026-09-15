"""Load .rag-store.json even when a killed writer appended extra JSON."""
from __future__ import annotations

import json
import os
import sys

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)


def test_load_snapshot_dict_valid(tmp_path):
    from snapshot_io import load_snapshot_dict

    path = tmp_path / "ok.json"
    path.write_text(json.dumps({"points": [{"id": 1}], "count": 1}), encoding="utf-8")
    data = load_snapshot_dict(str(path))
    assert data["count"] == 1
    assert data["points"][0]["id"] == 1


def test_load_snapshot_dict_extra_data(tmp_path):
    from snapshot_io import load_snapshot_dict

    path = tmp_path / "extra.json"
    path.write_text('{"points":[{"id":7}],"count":1}{"garbage":true}', encoding="utf-8")
    data = load_snapshot_dict(str(path))
    assert data["points"][0]["id"] == 7
    assert data["count"] == 1


def test_load_snapshot_dict_missing_and_garbage(tmp_path):
    from snapshot_io import load_snapshot_dict

    missing = load_snapshot_dict(str(tmp_path / "nope.json"))
    assert missing["points"] == []
    bad = tmp_path / "bad.json"
    bad.write_text("not-json", encoding="utf-8")
    data = load_snapshot_dict(str(bad))
    assert data["points"] == []
