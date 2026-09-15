"""Read `.rag-store.json` without bricking Search/Agent on trailing junk."""
from __future__ import annotations

import json
import os
from typing import Any


def load_snapshot_dict(path: str) -> dict[str, Any]:
    """Return the snapshot object. Extra concatenated JSON after the first value is ignored."""
    empty: dict[str, Any] = {"points": [], "count": 0}
    if not path or not os.path.isfile(path):
        return empty
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return empty
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            data, _end = json.JSONDecoder().raw_decode(raw)
        except json.JSONDecodeError:
            print(
                f"  WARNING: failed to load snapshot {path}; starting with empty collection",
                flush=True,
            )
            return empty
        print(
            f"  WARNING: extra data after first JSON value in {path}; using first object only",
            flush=True,
        )
    if not isinstance(data, dict):
        return empty
    data.setdefault("points", [])
    return data
