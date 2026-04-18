"""Cross-encoder re-ranker for search results.

Gracefully degrades: if the model cannot be loaded (e.g. offline and not
cached), reranking is silently skipped and results are returned as-is.
"""
import os
import traceback
from threading import Lock

_reranker = None
_load_failed = False
_lock = Lock()


def get_reranker():
    global _reranker, _load_failed
    # Fast path after successful load (no lock).
    if _reranker is not None:
        return _reranker
    with _lock:
        if _load_failed:
            return None
        if _reranker is None:
            try:
                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                from sentence_transformers import CrossEncoder
                _reranker = CrossEncoder(
                    "cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512
                )
            except Exception:
                traceback.print_exc()
                print("[reranker] Cross-encoder model unavailable — reranking disabled")
                _load_failed = True
                return None
        return _reranker


def rerank(query: str, results: list[dict], top_k: int = 5) -> list[dict]:
    if not results or len(results) <= 1:
        return results[:top_k]
    reranker = get_reranker()
    if reranker is None:
        return results[:top_k]
    pairs = [(query, (r.get("text") or "")[:400]) for r in results]
    try:
        scores = reranker.predict(pairs)
    except Exception:
        traceback.print_exc()
        print("[reranker] predict() failed — returning top_k without scores", flush=True)
        return results[:top_k]
    ranked = sorted(zip(results, scores), key=lambda x: -float(x[1]))
    for r, s in ranked:
        r["rerank_score"] = float(s)
    return [r for r, _ in ranked[:top_k]]
