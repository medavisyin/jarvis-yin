"""
RAG retrieval engine — vector search, BM25 hybrid, and auto-RAG logic.

Provides the core search capabilities used by both tool functions and the
agent loop's automatic context prefetch.
"""

import json
import os
import sys
from typing import Any

from config import PROJECT_GRAPH_PATH, SNAPSHOT_PATH

COLLECTION = "ai_briefings"
VECTOR_SIZE = 384
OLLAMA_MODEL_FAST = "qwen3:1.7b"
OLLAMA_HOST = "http://localhost:11434"

# ---------------------------------------------------------------------------
# Globals (lazy-loaded)
# ---------------------------------------------------------------------------
_embed_model = None
_qdrant_client = None
_qdrant_points: list[dict[str, Any]] = []
_qdrant_points_snapshot_mtime: float = 0.0


# ---------------------------------------------------------------------------
# Embedding + Qdrant initialization
# ---------------------------------------------------------------------------
def get_embed_model():
    global _embed_model
    if _embed_model is None:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embed_model


def get_qdrant():
    global _qdrant_client, _qdrant_points, _qdrant_points_snapshot_mtime
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import (
            Distance, VectorParams, PointStruct,
            HnswConfigDiff, OptimizersConfigDiff,
        )
        _qdrant_client = QdrantClient(":memory:")
        _qdrant_points = []
        _qdrant_points_snapshot_mtime = 0.0
        _qdrant_client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
            optimizers_config=OptimizersConfigDiff(indexing_threshold=0),
        )
        if os.path.exists(SNAPSHOT_PATH):
            _qdrant_points_snapshot_mtime = os.path.getmtime(SNAPSHOT_PATH)
            with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            points = data.get("points", [])
            _qdrant_points = [
                {"id": p.get("id"), "payload": dict(p.get("payload") or {})}
                for p in points
            ]
            batch_size = 500
            for i in range(0, len(points), batch_size):
                batch = [
                    PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
                    for p in points[i:i + batch_size]
                ]
                _qdrant_client.upsert(collection_name=COLLECTION, points=batch)
            print(f"  Loaded {len(points)} points from snapshot", flush=True)
    return _qdrant_client


def get_qdrant_points() -> list[dict[str, Any]]:
    """Access the cached point metadata (id + payload, no vectors)."""
    get_qdrant()  # ensure loaded
    return _qdrant_points


def sync_qdrant_points_from_snapshot() -> None:
    """Reload `_qdrant_points` if `.rag-store.json` changed (e.g. after toolbar reindex)."""
    global _qdrant_points, _qdrant_points_snapshot_mtime
    if not os.path.exists(SNAPSHOT_PATH):
        return
    mtime = os.path.getmtime(SNAPSHOT_PATH)
    if mtime <= _qdrant_points_snapshot_mtime:
        return
    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    points = data.get("points", [])
    _qdrant_points = [
        {"id": p.get("id"), "payload": dict(p.get("payload") or {})}
        for p in points
    ]
    _qdrant_points_snapshot_mtime = mtime


# ---------------------------------------------------------------------------
# Core search functions
# ---------------------------------------------------------------------------
def batch_encode(texts: list[str]) -> list[list[float]]:
    """Encode multiple texts in a single forward pass (much faster than N separate calls)."""
    model = get_embed_model()
    embeddings = model.encode(texts, batch_size=len(texts), normalize_embeddings=True)
    return [e.tolist() for e in embeddings]


def vector_search(query: str, top_k: int = 5, min_score: float = 0.3,
                  conditions: list | None = None,
                  embedding: list[float] | None = None) -> list[dict]:
    """Hybrid search: vector (Qdrant) + BM25 keyword, merged via Reciprocal Rank Fusion."""
    from qdrant_client.models import Filter
    client = get_qdrant()
    if embedding is None:
        embedding = get_embed_model().encode(query).tolist()
    query_filter = Filter(must=conditions) if conditions else None
    fetch_limit = max(top_k * 3, 20)
    response = client.query_points(
        collection_name=COLLECTION,
        query=embedding,
        query_filter=query_filter,
        limit=fetch_limit,
        score_threshold=min_score,
        with_payload=True,
    )
    vector_results = []
    for hit in response.points:
        p = hit.payload
        vector_results.append({
            "id": str(hit.id),
            "title": p.get("title", "Untitled"),
            "date": p.get("date", ""),
            "source": p.get("source", ""),
            "item_type": p.get("item_type", ""),
            "text": p.get("text", "")[:300],
            "score": round(hit.score, 3),
            "url": p.get("url", ""),
        })

    # BM25 hybrid fusion
    try:
        rag_dir = os.path.dirname(os.path.abspath(__file__))
        if rag_dir not in sys.path:
            sys.path.insert(0, rag_dir)
        from bm25_index import bm25_search
        bm25_hits = bm25_search(query, top_k=fetch_limit)
        if bm25_hits:
            rrf_scores: dict[str, float] = {}
            rrf_data: dict[str, dict] = {}
            k = 60
            for rank, r in enumerate(vector_results):
                rid = r["id"]
                rrf_scores[rid] = rrf_scores.get(rid, 0) + 1.0 / (k + rank + 1)
                rrf_data[rid] = r
            for rank, (pid, _bscore, payload) in enumerate(bm25_hits):
                pid_s = str(pid)
                rrf_scores[pid_s] = rrf_scores.get(pid_s, 0) + 1.0 / (k + rank + 1)
                if pid_s not in rrf_data:
                    rrf_data[pid_s] = {
                        "id": pid_s,
                        "title": payload.get("title", "Untitled"),
                        "date": payload.get("date", ""),
                        "source": payload.get("source", ""),
                        "item_type": payload.get("item_type", ""),
                        "text": (payload.get("text") or "")[:300],
                        "score": 0.0,
                        "url": payload.get("url", ""),
                    }
            fused = sorted(rrf_scores.items(), key=lambda x: -x[1])
            vector_results = [rrf_data[rid] for rid, _ in fused if rid in rrf_data]
    except (ImportError, Exception):
        pass

    return vector_results[:top_k]


# ---------------------------------------------------------------------------
# Query rewriting
# ---------------------------------------------------------------------------
def should_rewrite_query(query: str) -> bool:
    vague_signals = ["that thing", "the stuff", "what's", "something about",
                     "you know", "the other", "last time", "earlier", "before"]
    q = query.lower()
    return len(query.split()) < 5 or any(v in q for v in vague_signals)


def rewrite_query(user_query: str) -> str:
    """Use the fast model to rewrite vague queries into searchable terms."""
    try:
        import requests as _req
        resp = _req.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL_FAST,
                "messages": [
                    {"role": "system", "content": "Rewrite the search query to be specific. Output ONLY the rewritten query, nothing else."},
                    {"role": "user", "content": f"Rewrite for a knowledge base containing AI briefings, Java code docs, Confluence wiki, DICOM/FHIR docs:\n\nOriginal: {user_query}\nRewritten:"},
                ],
                "stream": False,
                "think": False,
                "options": {"num_predict": 50, "num_ctx": 256},
            },
            timeout=15,
        )
        rewritten = resp.json().get("message", {}).get("content", "").strip().split("\n")[0]
        if len(rewritten) > 8:
            return rewritten
    except Exception:
        pass
    return user_query


# ---------------------------------------------------------------------------
# Project graph helper
# ---------------------------------------------------------------------------
def load_project_graph() -> dict:
    if not os.path.isfile(PROJECT_GRAPH_PATH):
        return {}
    try:
        with open(PROJECT_GRAPH_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Auto-RAG search (main retrieval pipeline for the agent)
# ---------------------------------------------------------------------------
def auto_rag_search(user_query: str, q_lower: str) -> tuple[str, list[dict]]:
    """Run all auto-RAG searches with batched embeddings. Returns (context_str, sources)."""
    from qdrant_client.models import FieldCondition, MatchValue

    _team_names = {
        "jan": "Jan Loeffler", "jan loeffler": "Jan Loeffler",
        "raymond": "Rong Yin", "rong": "Rong Yin",
        "charlotte": "Charlotte Jiang", "christoph": "Christoph Scheben",
        "tobias": "Tobias Troesch",
    }
    _wiki_kw = ("wiki", "confluence", "documentation", "page")

    texts_to_encode = [user_query]
    matched_names = []
    for name_kw, full_name in _team_names.items():
        if name_kw in q_lower:
            matched_names.append(full_name)
            if full_name not in texts_to_encode:
                texts_to_encode.append(full_name)

    embeddings = batch_encode(texts_to_encode)
    emb_map = dict(zip(texts_to_encode, embeddings))

    auto_results = vector_search(
        user_query, top_k=5, min_score=0.25, embedding=emb_map[user_query])

    extra_results = []
    for full_name in matched_names:
        author_cond = [FieldCondition(key="author", match=MatchValue(value=full_name))]
        extra_results.extend(vector_search(
            user_query, top_k=5, min_score=0.1,
            conditions=author_cond, embedding=emb_map[user_query]))
        extra_results.extend(vector_search(
            full_name, top_k=3, min_score=0.2, embedding=emb_map[full_name]))

    if any(kw in q_lower for kw in _wiki_kw):
        wiki_cond = [FieldCondition(key="item_type", match=MatchValue(value="wiki_page"))]
        extra_results.extend(vector_search(
            user_query, top_k=3, min_score=0.2,
            conditions=wiki_cond, embedding=emb_map[user_query]))

    _project_kw = (
        "project", "dependency", "dependencies", "depends", "impact",
        "architecture", "module", "pom", "maven", "connect", "relationship",
        "rest api", "endpoint", "framework", "service", "microservice",
        "code", "class", "implement", "api", "review", "source",
    )
    if any(kw in q_lower for kw in _project_kw):
        code_types = ("code_doc", "project_summary", "project_identity", "project_dependency")
        for ct in code_types:
            code_cond = [FieldCondition(key="item_type", match=MatchValue(value=ct))]
            extra_results.extend(vector_search(
                user_query, top_k=3, min_score=0.15,
                conditions=code_cond, embedding=emb_map[user_query]))

        graph = load_project_graph()
        if graph:
            mentioned = []
            for pname in graph.get("projects", {}):
                if pname.lower().replace("-", " ") in q_lower or pname.lower() in q_lower:
                    mentioned.append(pname)
            for pname in mentioned:
                pinfo = graph["projects"].get(pname, {})
                related = {
                    d["target"] for d in pinfo.get("internal_dependencies", [])
                    if isinstance(d, dict) and d.get("target")
                }
                related.update(pinfo.get("depended_by", []))
                for rname in list(related)[:5]:
                    r_cond = [FieldCondition(key="parent_title", match=MatchValue(value=rname))]
                    extra_results.extend(vector_search(
                        user_query, top_k=2, min_score=0.1,
                        conditions=r_cond, embedding=emb_map[user_query]))

    seen_titles = set()
    all_results = []
    for r in auto_results + extra_results:
        if r["title"] not in seen_titles:
            seen_titles.add(r["title"])
            all_results.append(r)

    # If results are poor and query looks vague, try rewriting
    top_score = all_results[0]["score"] if all_results else 0
    if (not all_results or top_score < 0.35) and should_rewrite_query(user_query):
        rewritten = rewrite_query(user_query)
        if rewritten != user_query:
            rewritten_emb = get_embed_model().encode(rewritten).tolist()
            retry_results = vector_search(rewritten, top_k=5, min_score=0.2, embedding=rewritten_emb)
            for r in retry_results:
                if r["title"] not in seen_titles:
                    seen_titles.add(r["title"])
                    all_results.append(r)

    sources: list[dict] = []
    if not all_results:
        return "", sources

    is_project_query = any(kw in q_lower for kw in _project_kw)
    max_results = 8 if is_project_query else 5
    lines = []
    for r in all_results[:max_results]:
        lines.append(f"- [{r['source']}] {r['title']} ({r['date']}): {r['text'][:150]}")
        sources.append({"source": r["source"], "title": r["title"],
                         "item_type": r.get("item_type", "")})
    context = (
        "\n\n--- Relevant context from knowledge base ---\n"
        + "\n".join(lines)
        + "\n--- End context ---\n"
    )

    project_names_in_results = set()
    for r in all_results[:max_results]:
        src = r.get("source", "")
        if src.startswith("project:"):
            project_names_in_results.add(src.split(":", 1)[1])
    if len(project_names_in_results) >= 2:
        graph = load_project_graph()
        if graph:
            graph_lines = []
            for pn in sorted(project_names_in_results):
                pdata = graph.get("projects", {}).get(pn, {})
                if not pdata:
                    continue
                deps = [d["target"] for d in pdata.get("internal_dependencies", [])
                        if isinstance(d, dict) and d.get("target")]
                by = pdata.get("depended_by", [])
                coords = pdata.get("coordinates", "")
                graph_lines.append(f"- {pn} ({coords})")
                if deps:
                    graph_lines.append(f"    depends on: {', '.join(deps)}")
                if by:
                    graph_lines.append(f"    used by: {', '.join(by)}")
            if graph_lines:
                context += (
                    "\n\n--- Project Relationships ---\n"
                    + "\n".join(graph_lines)
                    + "\n--- End Relationships ---\n"
                )

    return context, sources
