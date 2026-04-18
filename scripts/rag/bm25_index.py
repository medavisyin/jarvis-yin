"""BM25 keyword index that runs alongside Qdrant vector search."""
import json
import os
import re
import sys
import traceback
from threading import Lock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import SNAPSHOT_PATH

_bm25 = None
_corpus_ids = None
_corpus_payloads = None
_lock = Lock()
_snapshot_mtime: float = 0.0


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _ensure_loaded():
    """Reload index only when snapshot path is missing or file mtime advances.

    Callers must hold ``_lock``. On JSON/read errors, clears the index and
    bumps mtime so the same broken file is not re-read on every request.
    """
    global _bm25, _corpus_ids, _corpus_payloads, _snapshot_mtime
    if not os.path.exists(SNAPSHOT_PATH):
        _bm25 = None
        _corpus_ids = None
        _corpus_payloads = None
        _snapshot_mtime = 0.0
        return
    mtime = os.path.getmtime(SNAPSHOT_PATH)
    if _bm25 is not None and mtime <= _snapshot_mtime:
        return
    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        print(f"[bm25_index] Failed to read snapshot: {e}", flush=True)
        traceback.print_exc()
        _bm25 = None
        _corpus_ids = None
        _corpus_payloads = None
        _snapshot_mtime = mtime
        return
    try:
        from rank_bm25 import BM25Okapi
    except ImportError as e:
        print(f"[bm25_index] rank_bm25 not installed: {e}", flush=True)
        _bm25 = None
        _corpus_ids = []
        _corpus_payloads = []
        _snapshot_mtime = mtime
        return
    corpus = []
    new_ids = []
    new_payloads = []
    for p in data.get("points", []):
        payload = p.get("payload") or {}
        text = (payload.get("text", "") + " " + payload.get("title", "")).strip()
        corpus.append(_tokenize(text))
        new_ids.append(p.get("id"))
        new_payloads.append(payload)
    _bm25 = BM25Okapi(corpus) if corpus else None
    _corpus_ids = new_ids
    _corpus_payloads = new_payloads
    _snapshot_mtime = mtime


def get_bm25():
    with _lock:
        _ensure_loaded()
        return _bm25, _corpus_ids


def bm25_search(query: str, top_k: int = 20) -> list[tuple]:
    """Return (id, score, payload) tuples. Thread-safe vs :func:`reset`."""
    with _lock:
        _ensure_loaded()
        bm25, ids, payloads = _bm25, _corpus_ids, _corpus_payloads
    if bm25 is None or not ids:
        return []
    tokens = _tokenize(query)
    if not tokens:
        return []
    scores = bm25.get_scores(tokens)
    top_indices = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
    return [(str(ids[i]), float(scores[i]), payloads[i])
            for i in top_indices if scores[i] > 0]


def reset():
    global _bm25, _corpus_ids, _corpus_payloads, _snapshot_mtime
    with _lock:
        _bm25 = None
        _corpus_ids = None
        _corpus_payloads = None
        _snapshot_mtime = 0.0
