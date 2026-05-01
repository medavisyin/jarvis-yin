"""Feedback collection and aggregation for RAG quality improvement.

Records user interaction events (expand, copy, reformulate) and computes
per-chunk quality scores used for feedback-weighted ranking.
"""
import json
import os
import sys
import tempfile
import time
from threading import Lock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import FEEDBACK_PATH
_lock = Lock()
# In-memory cache: avoids re-reading the JSON on every get_chunk_score when
# the file has not changed (mtime match).
_cached: dict | None = None
_cached_mtime: float = -1.0


def _empty_store() -> dict:
    return {"events": [], "chunk_scores": {}}


def _read_disk_unlocked() -> tuple[dict, float]:
    """Read file from disk. Returns (data, mtime). Caller must not hold _lock."""
    if not os.path.exists(FEEDBACK_PATH):
        return _empty_store(), -1.0
    try:
        mtime = os.path.getmtime(FEEDBACK_PATH)
        with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return _empty_store(), os.path.getmtime(FEEDBACK_PATH) if os.path.exists(FEEDBACK_PATH) else -1.0
    if "events" not in data:
        data["events"] = []
    if "chunk_scores" not in data:
        data["chunk_scores"] = {}
    return data, mtime


def _load_locked() -> dict:
    """Return current store dict; refresh from disk when cache is stale."""
    global _cached, _cached_mtime
    if not os.path.exists(FEEDBACK_PATH):
        _cached = _empty_store()
        _cached_mtime = -1.0
        return _cached
    disk_mtime = os.path.getmtime(FEEDBACK_PATH)
    if _cached is not None and disk_mtime == _cached_mtime:
        return _cached
    data, mtime = _read_disk_unlocked()
    _cached = data
    _cached_mtime = mtime
    return _cached


def _save_atomic(data: dict) -> None:
    """Write JSON atomically (temp + replace) and refresh cache mtime."""
    global _cached, _cached_mtime
    parent = os.path.dirname(os.path.abspath(FEEDBACK_PATH)) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=parent, prefix=".rag-feedback-", suffix=".tmp", text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp_path, FEEDBACK_PATH)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    _cached = data
    _cached_mtime = os.path.getmtime(FEEDBACK_PATH)


_ACTION_WEIGHTS = {
    "expand": 1.0,
    "view_doc": 2.0,
    "copy": 3.0,
    "reformulate": -1.0,
    "click_link": 1.5,
}


def record_event(query: str, chunk_id: str, action: str, position: int = 0) -> None:
    weight = _ACTION_WEIGHTS.get(action, 0)
    with _lock:
        data = _load_locked()
        data["events"].append({
            "query": query,
            "chunk_id": str(chunk_id),
            "action": action,
            "position": position,
            "weight": weight,
            "timestamp": time.time(),
        })
        _save_atomic(data)


def get_chunk_score(chunk_id: str) -> float:
    """Aggregated quality score for a chunk (0.0 to 1.0). Default 0.5."""
    with _lock:
        data = _load_locked()
        return float(data.get("chunk_scores", {}).get(str(chunk_id), 0.5))


def aggregate_scores() -> dict[str, float]:
    """Recompute per-chunk quality scores from all events."""
    with _lock:
        data = _load_locked()
        scores: dict[str, float] = {}
        counts: dict[str, int] = {}
        now = time.time()
        decay_threshold = 90 * 86400  # 90 days

        for event in data.get("events", []):
            cid = event.get("chunk_id")
            if cid is None or cid == "":
                continue
            cid = str(cid)
            weight = event.get("weight", 0)
            age = now - event.get("timestamp", now)
            if age > decay_threshold:
                weight *= 0.5
            scores[cid] = scores.get(cid, 0) + weight
            counts[cid] = counts.get(cid, 0) + 1

        chunk_scores: dict[str, float] = {}
        for cid in scores:
            if counts[cid] < 3:
                continue
            raw = scores[cid] / counts[cid]
            chunk_scores[cid] = max(0.0, min(1.0, (raw + 3) / 6))

        data["chunk_scores"] = chunk_scores
        _save_atomic(data)
        return chunk_scores


def record_eval_candidate(query: str, chunk_id: str, relevant: bool) -> None:
    """Store a user-confirmed relevance judgment for use as future eval data."""
    with _lock:
        data = _load_locked()
        if "eval_candidates" not in data:
            data["eval_candidates"] = []
        data["eval_candidates"].append({
            "query": query,
            "chunk_id": str(chunk_id),
            "relevant": relevant,
            "timestamp": time.time(),
        })
        _save_atomic(data)


def get_eval_candidates() -> list[dict]:
    """Return all confirmed eval candidates."""
    with _lock:
        data = _load_locked()
        return data.get("eval_candidates", [])


def get_stats() -> dict:
    with _lock:
        data = _load_locked()
        return {
            "total_events": len(data.get("events", [])),
            "scored_chunks": len(data.get("chunk_scores", {})),
            "eval_candidates": len(data.get("eval_candidates", [])),
        }
