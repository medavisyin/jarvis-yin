"""
Jarvis — AI-powered RAG assistant using Qwen3-VL:8b via Ollama.

Answers questions with context from the Qdrant RAG store, performs multi-step
reasoning via tool calling, analyzes images, and invokes available skills
(Jira, commit summaries, briefing search, Confluence) as tools.

Usage:
  python agent.py [port]
  Opens at http://localhost:18889 (or custom port)

Dependencies: pip install ollama qdrant-client sentence-transformers flask pypdf
"""
import base64
import glob
import json
import logging
import os
import re
import uuid
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Iterator

from flask import Flask, Response, request, jsonify, render_template_string, make_response, send_file

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import (
    CHAT_SESSIONS_DIR,
    JIRA_REPORT_SCRIPT,
    KNOWLEDGE_ROOT,
    NOTES_FILE,
    REPORTS_ROOT,
    SNAPSHOT_PATH,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OLLAMA_MODEL = os.environ.get("RAG_AGENT_MODEL", "qwen3.5:4b")
OLLAMA_MODEL_FAST = "qwen3:1.7b"
OLLAMA_MODEL_NARRATION = os.environ.get("RAG_NARRATION_MODEL", "qwen3:1.7b")
OLLAMA_HOST = "http://localhost:11434"
COLLECTION = "ai_briefings"
VECTOR_SIZE = 384
JIRA_SCRIPT = JIRA_REPORT_SCRIPT
MAX_AGENT_ITERATIONS = 8
TOOL_TIMEOUT_SECONDS = 120

REPO_CONFIG = [
    {"name": "P4M Next", "path": "d:/projects/p4m"},
    {"name": "Admin App", "path": "d:/projects/admin-app"},
    {"name": "Core Framework", "path": "d:/projects/core-framework"},
    {"name": "Vaadin UI", "path": "d:/projects/vaadin-ui"},
    {"name": "AWS Infrastructure P4M EKS", "path": "d:/p4m_cloud_project/aws-infra-p4m-eks"},
    {"name": "RIS Utilization Dashboard", "path": "D:/cto/scm/ris-utilization-dashboard"},
    {"name": "B4M Next", "path": "d:/projects/b4m.next"},
    {"name": "Application Server", "path": "d:/projects/applicationserver"},
    {"name": "Apache Dist", "path": "d:/projects/apache-dist"},
    {"name": "Communication Stack", "path": "d:/projects/communication-stack"},
    {"name": "Identity Server", "path": "d:/projects/identityserver"},
    {"name": "Keycloak", "path": "d:/projects/keycloak"},
    {"name": "Local Gateway", "path": "d:/projects/local-gateway"},
    {"name": "Local Gateway Plugins", "path": "d:/projects/local-gateway-plugins"},
    {"name": "Parent", "path": "d:/projects/parent"},
    {"name": "SMS Service", "path": "d:/projects/sms-service"},
    {"name": "SMS Service Client", "path": "d:/projects/sms-service-client"},
    {"name": "Teleradiology Cloud Backend", "path": "d:/projects/teleradiology-cloud-backend"},
]

SYSTEM_PROMPT_FULL = """\
You are a RAG-powered AI assistant for the medavis Portal4Med.next (P4M) team. \
You have access to a knowledge base of daily AI briefings, research papers, \
Confluence wiki pages, Jira tickets, and project documentation. You also have \
vision capabilities and can analyze images.

Team context:
- Jan Loeffler — CTO, leads architecture and technical strategy
- Rong Yin (Raymond) — Developer, Squad 5
- Charlotte Jiang — Developer, Squad 5
- Christoph Scheben — Developer
- Tobias Troesch — Developer
- The product is Portal4Med.next (P4M), a medical radiology portal built with \
Java/WildFly/Vaadin, deployed on AWS EKS.

Relevant context from the knowledge base is automatically injected into each \
question. Use this context to answer. If the context is relevant, cite the \
sources (date, title, source name).

You also have tools for actions that require live data:
- `jira_report` — current open Jira tickets, sprint status, team workload
- `commit_summary` — recent git commits across monitored repositories
- `confluence_search` — search team wiki pages beyond auto-injected context
- `briefing_search` — search AI briefings with date/source filters
- `rag_search` — deeper search if auto-context is insufficient
- `analyze_image` — focused re-analysis of an uploaded image

Rules:
- Answer using the injected context first. Only call tools if the context is \
insufficient or the user asks for live data (Jira tickets, git commits).
- When the user uploads an image, analyze it directly from the message.
- If results are insufficient, say so honestly rather than hallucinating.
- Keep answers concise and focused.
- Answer in the same language the user uses."""

SYSTEM_PROMPT_COMPACT = """\
You are a P4M team AI assistant. Answer using the provided context. \
Cite sources (date, title). Be concise. Answer in the user's language. \
Team: Jan Loeffler (CTO), Rong Yin/Raymond (Dev), Charlotte Jiang (Dev), \
Christoph Scheben (Dev), Tobias Troesch (Dev). \
Product: Portal4Med.next (P4M) — Java/Vaadin radiology portal on AWS EKS."""

# ---------------------------------------------------------------------------
# Globals (lazy-loaded)
# ---------------------------------------------------------------------------
_embed_model = None
_qdrant_client = None
_qdrant_points: list[dict[str, Any]] = []
_qdrant_points_snapshot_mtime: float = 0.0

_toolbar_jobs: dict[str, dict[str, Any]] = {}
_toolbar_jobs_lock = threading.Lock()
_chunk_analysis_cache: dict[str, Any] | None = None
_chunk_analysis_cache_time: float = 0.0
_chunk_analysis_cache_lock = threading.Lock()
CHUNK_ANALYSIS_CACHE_TTL = 60

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Qdrant / Embedding helpers (reuse pattern from search_ui.py)
# ---------------------------------------------------------------------------
def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embed_model


def _get_qdrant():
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


def _sync_qdrant_points_from_snapshot() -> None:
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


def _batch_encode(texts: list[str]) -> list[list[float]]:
    """Encode multiple texts in a single forward pass (much faster than N separate calls)."""
    model = _get_embed_model()
    embeddings = model.encode(texts, batch_size=len(texts), normalize_embeddings=True)
    return [e.tolist() for e in embeddings]


def _vector_search(query: str, top_k: int = 5, min_score: float = 0.3,
                   conditions: list | None = None,
                   embedding: list[float] | None = None) -> list[dict]:
    """Hybrid search: vector (Qdrant) + BM25 keyword, merged via Reciprocal Rank Fusion."""
    from qdrant_client.models import Filter
    client = _get_qdrant()
    if embedding is None:
        embedding = _get_embed_model().encode(query).tolist()
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

    # BM25 hybrid fusion (graceful fallback if rank_bm25 not installed)
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


# ===================================================================
# TOOL IMPLEMENTATIONS
# ===================================================================

def tool_rag_search(query: str, top_k: int = 3, min_score: float = 0.3) -> str:
    """Semantic search across the full RAG store."""
    results = _vector_search(query, top_k=min(top_k, 5), min_score=min_score)
    if not results:
        return "No relevant results found in the knowledge base."
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. [{r['source']}] {r['title']} ({r['date']}, score={r['score']})\n"
            f"   {r['text'][:300]}"
        )
    return "\n\n".join(lines)


def tool_briefing_search(query: str, date_from: str = "", date_to: str = "",
                         source: str = "") -> str:
    """Date-filtered search across AI briefings."""
    from qdrant_client.models import FieldCondition, MatchValue, Range
    conditions = []
    if date_from:
        conditions.append(FieldCondition(key="date", range=Range(gte=date_from)))
    if date_to:
        conditions.append(FieldCondition(key="date", range=Range(lte=date_to)))
    if source:
        conditions.append(FieldCondition(key="source", match=MatchValue(value=source)))
    results = _vector_search(query, top_k=3, min_score=0.25, conditions=conditions or None)
    if not results:
        return "No briefing results found for the given filters."
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. [{r['date']}] {r['title']} (source={r['source']}, score={r['score']})\n"
            f"   {r['text'][:300]}"
        )
    return "\n\n".join(lines)


def tool_confluence_search(query: str, space: str = "") -> str:
    """Search indexed Confluence wiki pages."""
    from qdrant_client.models import FieldCondition, MatchValue
    conditions = [FieldCondition(key="item_type", match=MatchValue(value="wiki_page"))]
    if space:
        conditions.append(FieldCondition(key="space", match=MatchValue(value=space)))
    results = _vector_search(query, top_k=3, min_score=0.25, conditions=conditions)
    if not results:
        return "No Confluence wiki pages found matching the query."
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. {r['title']} ({r['date']}, score={r['score']})\n"
            f"   {r['text'][:300]}"
        )
    return "\n\n".join(lines)


def tool_jira_report(report_dir: str = "") -> str:
    """Run the Jira/Confluence daily report and return the summary."""
    if not report_dir:
        report_dir = os.path.join(REPORTS_ROOT, datetime.now().strftime("%Y-%m-%d"))
    if not os.path.isfile(JIRA_SCRIPT):
        return f"Error: Jira report script not found at {JIRA_SCRIPT}"
    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", JIRA_SCRIPT,
             "-ReportDir", report_dir],
            capture_output=True, text=True, timeout=TOOL_TIMEOUT_SECONDS,
        )
        output = result.stdout.strip()
        if result.returncode != 0 and result.stderr:
            output += f"\n[stderr]: {result.stderr[:300]}"
        return output[:2000] if output else "Jira report completed but produced no output."
    except subprocess.TimeoutExpired:
        return "Error: Jira report timed out."
    except Exception as e:
        return f"Error running Jira report: {e}"


AUTHOR_ALIASES = {
    "rong yin": ["rong yin", "rong.yin"],
    "raymond shen": ["raymond shen"],
    "belen liu": ["belen liu", "belen.liu"],
    "eason li": ["eason li", "eason.li"],
    "johnny yang": ["johnny yang", "johnny.yang"],
    "charlotte jiang": ["charlotte jiang", "charlotte.jiang"],
    "christoph scheben": ["christoph scheben", "christoph.scheben"],
    "tobias troesch": ["tobias troesch", "tobias.troesch", "tobias.trösch"],
    "jan loeffler": ["jan loeffler", "jan.loeffler", "jan löffler"],
}


def _author_matches(git_author: str, filter_names: list[str]) -> bool:
    """Check if a git author name matches any of the filter names (case-insensitive, alias-aware)."""
    if not filter_names:
        return True
    git_lower = git_author.strip().lower()
    for name in filter_names:
        name_lower = name.strip().lower()
        if git_lower == name_lower:
            return True
        aliases = AUTHOR_ALIASES.get(name_lower, [])
        if git_lower in aliases:
            return True
    return False


def tool_commit_summary(hours: int = 24, authors: list[str] | None = None,
                        since_date: str = "", until_date: str = "") -> str:
    """Fetch remotes for key repos and scan all repos for recent commits."""
    if since_date:
        since_str = since_date + "T00:00:00"
    else:
        since = datetime.now() - timedelta(hours=hours)
        since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
    until_str = (until_date + "T23:59:59") if until_date else ""
    all_commits: list[str] = []
    fetched = 0
    scanned = 0

    repos = list(REPO_CONFIG)
    known_paths = {os.path.normpath(r["path"]).lower() for r in repos}
    projects_root = "d:/projects"
    if os.path.isdir(projects_root):
        for entry in os.listdir(projects_root):
            full = os.path.join(projects_root, entry)
            if os.path.isdir(os.path.join(full, ".git")):
                norm = os.path.normpath(full).lower()
                if norm not in known_paths:
                    repos.append({"name": entry, "path": full})
                    known_paths.add(norm)

    configured_paths = {os.path.normpath(r["path"]).lower() for r in REPO_CONFIG}
    for repo in repos:
        repo_path = repo["path"]
        if not os.path.isdir(repo_path):
            continue
        if os.path.normpath(repo_path).lower() in configured_paths:
            try:
                subprocess.run(
                    ["git", "-C", repo_path, "fetch", "--all", "--prune"],
                    capture_output=True, text=True, timeout=30,
                )
                fetched += 1
            except Exception:
                pass

        try:
            git_cmd = ["git", "-C", repo_path, "log", "--all",
                       f"--since={since_str}", "--format=%h|%an|%s|%ci"]
            if until_str:
                git_cmd.insert(5, f"--until={until_str}")
            result = subprocess.run(
                git_cmd,
                capture_output=True, text=True, timeout=30,
            )
            scanned += 1
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                seen = set()
                for line in lines:
                    parts = line.split("|", 3)
                    if len(parts) >= 4 and parts[0] not in seen:
                        if not _author_matches(parts[1], authors or []):
                            continue
                        seen.add(parts[0])
                        all_commits.append(
                            f"[{repo['name']}] {parts[0]} by {parts[1]}: {parts[2]} ({parts[3]})"
                        )
        except Exception:
            continue

    author_info = f" for {', '.join(authors)}" if authors else ""
    if since_date and until_date:
        period = f" ({since_date} to {until_date})"
    elif since_date:
        period = f" (since {since_date})"
    else:
        period = f" in the last {hours} hours"
    info = f"Scanned {scanned} repos ({fetched} fetched from remotes).\n"
    if not all_commits:
        return info + f"No commits found{author_info}{period}."
    return info + f"Found {len(all_commits)} commits{author_info}{period}:\n\n" + "\n".join(all_commits[:200])


def tool_analyze_image(image_description_request: str) -> str:
    """Placeholder — vision analysis is handled inline by the agent loop."""
    return (
        "Image analysis is performed directly by the model when the user "
        "uploads an image. The image is already in the conversation context."
    )


# ===================================================================
# TOOL REGISTRY (Ollama-compatible JSON schemas)
# ===================================================================

TOOL_FUNCTIONS = {
    "rag_search": tool_rag_search,
    "briefing_search": tool_briefing_search,
    "confluence_search": tool_confluence_search,
    "jira_report": tool_jira_report,
    "commit_summary": tool_commit_summary,
    "analyze_image": tool_analyze_image,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": (
                "Semantic search across the full RAG knowledge base: AI briefings, "
                "raw research articles, custom documents, learning guides, and wiki pages."
            ),
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "top_k": {"type": "integer", "description": "Max results (default 5)"},
                    "min_score": {"type": "number", "description": "Min relevance 0-1 (default 0.3)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "briefing_search",
            "description": (
                "Date-filtered search across daily AI briefings. Use when the user "
                "asks about AI news on specific dates or from specific sources."
            ),
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "date_from": {"type": "string", "description": "Start date YYYY-MM-DD (optional)"},
                    "date_to": {"type": "string", "description": "End date YYYY-MM-DD (optional)"},
                    "source": {"type": "string", "description": "Source filter e.g. 'arxiv' (optional)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confluence_search",
            "description": (
                "Search indexed Confluence wiki pages from the team's knowledge base."
            ),
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "space": {"type": "string", "description": "Confluence space key (optional)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jira_report",
            "description": (
                "Run the Jira/Confluence daily report to get current open tickets, "
                "sprint status, and recent wiki updates for the team."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "report_dir": {
                        "type": "string",
                        "description": "Output directory for the report (optional, defaults to today's folder)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "commit_summary",
            "description": (
                "Get recent commit activity across 6 monitored git repositories "
                "(P4M Next, Admin App, Core Framework, Vaadin UI, AWS Infra, RIS Dashboard)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {
                        "type": "integer",
                        "description": "Look back N hours (default 24)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_image",
            "description": (
                "Request a focused re-analysis of the user's uploaded image. "
                "Only use this if you need a second, more targeted look at the image."
            ),
            "parameters": {
                "type": "object",
                "required": ["image_description_request"],
                "properties": {
                    "image_description_request": {
                        "type": "string",
                        "description": "What to focus on in the image",
                    },
                },
            },
        },
    },
]


# ===================================================================
# AGENT LOOP (ReAct-style)
# ===================================================================

def _execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Dispatch a tool call and return its string result."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return f"Error: unknown tool '{name}'"
    try:
        return fn(**arguments)
    except Exception as e:
        return f"Error executing {name}: {e}"


def _should_rewrite_query(query: str) -> bool:
    vague_signals = ["that thing", "the stuff", "what's", "something about",
                     "you know", "the other", "last time", "earlier", "before"]
    q = query.lower()
    return len(query.split()) < 5 or any(v in q for v in vague_signals)


def _rewrite_query(user_query: str) -> str:
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


def _auto_rag_search(user_query: str, q_lower: str) -> tuple[str, list[dict]]:
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

    embeddings = _batch_encode(texts_to_encode)
    emb_map = dict(zip(texts_to_encode, embeddings))

    auto_results = _vector_search(
        user_query, top_k=5, min_score=0.25, embedding=emb_map[user_query])

    extra_results = []
    for full_name in matched_names:
        author_cond = [FieldCondition(key="author", match=MatchValue(value=full_name))]
        extra_results.extend(_vector_search(
            user_query, top_k=5, min_score=0.1,
            conditions=author_cond, embedding=emb_map[user_query]))
        extra_results.extend(_vector_search(
            full_name, top_k=3, min_score=0.2, embedding=emb_map[full_name]))

    if any(kw in q_lower for kw in _wiki_kw):
        wiki_cond = [FieldCondition(key="item_type", match=MatchValue(value="wiki_page"))]
        extra_results.extend(_vector_search(
            user_query, top_k=3, min_score=0.2,
            conditions=wiki_cond, embedding=emb_map[user_query]))

    seen_titles = set()
    all_results = []
    for r in auto_results + extra_results:
        if r["title"] not in seen_titles:
            seen_titles.add(r["title"])
            all_results.append(r)

    # If results are poor and query looks vague, try rewriting
    top_score = all_results[0]["score"] if all_results else 0
    if (not all_results or top_score < 0.35) and _should_rewrite_query(user_query):
        rewritten = _rewrite_query(user_query)
        if rewritten != user_query:
            rewritten_emb = _get_embed_model().encode(rewritten).tolist()
            retry_results = _vector_search(rewritten, top_k=5, min_score=0.2, embedding=rewritten_emb)
            for r in retry_results:
                if r["title"] not in seen_titles:
                    seen_titles.add(r["title"])
                    all_results.append(r)

    sources: list[dict] = []
    if not all_results:
        return "", sources

    lines = []
    for r in all_results[:5]:
        lines.append(f"- [{r['source']}] {r['title']} ({r['date']}): {r['text'][:150]}")
        sources.append({"source": r["source"], "title": r["title"]})
    context = (
        "\n\n--- Relevant context from knowledge base ---\n"
        + "\n".join(lines)
        + "\n--- End context ---\n"
    )
    return context, sources


def _auto_tool_commit() -> str:
    return tool_commit_summary(hours=72)


def _auto_tool_jira() -> str:
    return tool_jira_report()


_SUMMARY_CACHE: dict[str, str] = {}
_RECENT_KEEP = 6  # keep last N messages in full
_SUMMARIZE_THRESHOLD = 8  # start summarizing when history exceeds this many messages


def _summarize_history(old_messages: list[dict], cache_key: str = "") -> str:
    """Compress older conversation messages into a concise memory block.
    Uses the fast LLM model. Results are cached by cache_key to avoid
    re-summarizing the same prefix on every request."""
    if cache_key and cache_key in _SUMMARY_CACHE:
        return _SUMMARY_CACHE[cache_key]

    transcript = []
    for m in old_messages:
        role = m.get("role", "?").upper()
        content = (m.get("content", "") or "")[:500]
        transcript.append(f"{role}: {content}")
    text = "\n".join(transcript)

    prompt = (
        "Summarize this conversation between a student and tutor into a concise memory block. "
        "Include: key topics discussed, what the student learned, any mistakes corrected, "
        "and the student's current level of understanding. Keep it under 300 words.\n\n"
        f"{text}"
    )
    try:
        import requests as _req
        resp = _req.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL_FAST,
                "messages": [
                    {"role": "system", "content": "You are a conversation summarizer. Be concise and factual."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "think": False,
                "options": {"num_predict": 400, "num_ctx": 4096, "temperature": 0.3},
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Ollama returned {resp.status_code}")
        summary = resp.json().get("message", {}).get("content", "").strip()
        if not summary:
            raise RuntimeError("Empty summary from LLM")
    except Exception as e:
        logging.warning("History summarization failed: %s", e)
        summary = f"[Previous conversation: {len(old_messages)} exchanges about various topics]"
        return summary  # don't cache failures

    if cache_key:
        if len(_SUMMARY_CACHE) > 100:
            _SUMMARY_CACHE.pop(next(iter(_SUMMARY_CACHE)))
        _SUMMARY_CACHE[cache_key] = summary
    return summary


def run_agent(user_query: str, image_b64: str | None = None,
              conversation_history: list[dict] | None = None,
              system_prompt_override: str | None = None,
              rag_query_override: str | None = None):
    """
    Generator that yields SSE events as the agent reasons.
    Uses streaming LLM output for perceived-instant responses.

    Args:
        rag_query_override: If set, use this string for RAG search instead of
            user_query. Useful when the user's raw input (e.g. "topic 16")
            needs to be resolved to a meaningful search term.

    Events:
      {"type": "thinking", "tool": "...", "args": {...}}
      {"type": "tool_result", "tool": "...", "preview": "..."}
      {"type": "token", "content": "..."}
      {"type": "answer_done", "sources": [...]}
      {"type": "error", "message": "..."}
    """
    import ollama

    effective_model = OLLAMA_MODEL
    yield {"type": "model", "model": effective_model}

    messages: list[dict] = []  # system prompt added after context decision

    if conversation_history:
        n = len(conversation_history)
        if n > _SUMMARIZE_THRESHOLD:
            old_msgs = conversation_history[: n - _RECENT_KEEP]
            recent_msgs = conversation_history[n - _RECENT_KEEP :]
            cache_key = f"{n - _RECENT_KEEP}:{hash(str(old_msgs[-1].get('content', '')[:100]))}"
            yield {"type": "thinking", "tool": "memory_summarize",
                   "args": {"old_messages": len(old_msgs), "recent_kept": len(recent_msgs)}}
            summary = _summarize_history(old_msgs, cache_key)
            messages.append({"role": "system",
                             "content": f"[CONVERSATION MEMORY]\n{summary}\n[END MEMORY]"})
            for msg in recent_msgs:
                messages.append({"role": msg["role"], "content": msg["content"]})
        else:
            for msg in conversation_history:
                messages.append({"role": msg["role"], "content": msg["content"]})

    collected_sources: list[dict] = []

    rag_search_query = rag_query_override or user_query
    q_lower = user_query.lower()
    _commit_kw = ("commit", "git log", "pushed", "merged", "code change", "repository activity")
    _jira_kw = ("jira", "ticket", "sprint", "backlog", "open issue", "task status")
    need_commits = any(kw in q_lower for kw in _commit_kw)
    need_jira = any(kw in q_lower for kw in _jira_kw)

    # Run auto-RAG and auto-tools in parallel using threads
    rag_context = ""
    auto_tool_context = ""
    futures = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures["rag"] = pool.submit(_auto_rag_search, rag_search_query, rag_search_query.lower())
        if need_commits:
            yield {"type": "thinking", "tool": "commit_summary (auto)", "args": {"hours": 72}}
            futures["commits"] = pool.submit(_auto_tool_commit)
        if need_jira:
            yield {"type": "thinking", "tool": "jira_report (auto)", "args": {}}
            futures["jira"] = pool.submit(_auto_tool_jira)

        for key, future in futures.items():
            try:
                result = future.result(timeout=60)
                if key == "rag":
                    rag_context, rag_sources = result
                    collected_sources.extend(rag_sources)
                    if rag_context:
                        rag_display = rag_search_query[:80]
                        if rag_query_override:
                            rag_display = f"{rag_query_override[:60]} (resolved from: {user_query[:20]})"
                        yield {"type": "thinking", "tool": "rag_search (auto)",
                               "args": {"query": rag_display}}
                elif key == "commits":
                    auto_tool_context += f"\n\n--- Git commit data ---\n{result}\n--- End commit data ---\n"
                    yield {"type": "tool_result", "tool": "commit_summary", "preview": result[:200]}
                elif key == "jira":
                    auto_tool_context += f"\n\n--- Jira report ---\n{result[:1500]}\n--- End Jira report ---\n"
                    yield {"type": "tool_result", "tool": "jira_report", "preview": result[:200]}
            except Exception:
                pass

    context_block = rag_context + auto_tool_context
    has_auto_context = bool(context_block.strip())

    if system_prompt_override:
        sys_prompt = system_prompt_override
    elif has_auto_context:
        sys_prompt = SYSTEM_PROMPT_COMPACT
    else:
        sys_prompt = SYSTEM_PROMPT_FULL
    messages.insert(0, {"role": "system", "content": sys_prompt})

    if has_auto_context:
        if system_prompt_override:
            augmented_query = (
                f"USER QUESTION: {user_query}\n\n"
                f"SUPPLEMENTARY REFERENCE MATERIAL (use to enrich your answer, "
                f"but follow the teaching structure in your system prompt first):\n"
                f"{context_block}"
            )
        else:
            augmented_query = (
                f"USER QUESTION: {user_query}\n\n"
                f"IMPORTANT: Use ONLY the following retrieved data to answer. "
                f"Do NOT say 'no information found' if the data below is relevant.\n"
                f"{context_block}"
            )
    else:
        augmented_query = user_query

    history_len = sum(len(m.get("content", "")) for m in messages)
    ctx_len = len(augmented_query) + len(sys_prompt) + history_len
    if system_prompt_override:
        num_ctx = 8192 if ctx_len < 6000 else 16384
    else:
        num_ctx = 2048 if ctx_len < 1500 else 4096 if ctx_len < 6000 else 8192 if ctx_len < 14000 else 16384

    user_msg: dict[str, Any] = {"role": "user", "content": augmented_query}
    if image_b64:
        user_msg["images"] = [image_b64]
    messages.append(user_msg)

    # Skip tool schemas when auto-routing already handled the heavy tools.
    # This saves ~2000 tokens of context and speeds up prefill significantly.
    has_auto_context = bool(context_block.strip())
    use_tools = not has_auto_context

    for iteration in range(MAX_AGENT_ITERATIONS):
        try:
            call_kwargs: dict[str, Any] = {
                "model": effective_model,
                "messages": messages,
                "stream": True,
                "think": False,
                "options": {"num_ctx": num_ctx, "num_predict": 4096},
            }
            if use_tools:
                call_kwargs["tools"] = TOOL_SCHEMAS
            stream = ollama.chat(**call_kwargs)
        except Exception as e:
            yield {"type": "error", "message": f"Ollama error: {e}"}
            return

        full_content = ""
        tool_calls = []
        for chunk in stream:
            c = chunk.message
            if c.content:
                full_content += c.content
                yield {"type": "token", "content": c.content}
            if c.tool_calls:
                tool_calls.extend(c.tool_calls)

        if not tool_calls:
            yield {"type": "answer_done", "sources": collected_sources}
            return

        messages.append({"role": "assistant", "content": full_content,
                         "tool_calls": tool_calls})

        for call in tool_calls:
            tool_name = call.function.name
            tool_args = call.function.arguments or {}

            yield {"type": "thinking", "tool": tool_name, "args": tool_args}

            if tool_name == "analyze_image" and image_b64:
                focus = tool_args.get("image_description_request", "Describe this image in detail")
                try:
                    vision_resp = ollama.chat(
                        model=OLLAMA_MODEL,  # always use vision model for images
                        messages=[{
                            "role": "user",
                            "content": focus,
                            "images": [image_b64],
                        }],
                        stream=False,
                        think=False,
                        options={"num_ctx": 2048, "num_predict": 512},
                    )
                    result_str = vision_resp.message.content or "No analysis produced."
                except Exception as e:
                    result_str = f"Vision analysis error: {e}"
            else:
                result_str = _execute_tool(tool_name, tool_args)

            preview = result_str[:200] + ("..." if len(result_str) > 200 else "")
            yield {"type": "tool_result", "tool": tool_name, "preview": preview}

            if tool_name in ("rag_search", "briefing_search", "confluence_search"):
                for line in result_str.split("\n\n"):
                    m = re.match(r'\d+\.\s*\[([^\]]*)\]\s*(.+?)\s*\(', line)
                    if m:
                        collected_sources.append({
                            "source": m.group(1),
                            "title": m.group(2).strip(),
                        })

            messages.append({"role": "tool", "content": result_str})

    yield {
        "type": "error",
        "message": f"Agent reached maximum iterations ({MAX_AGENT_ITERATIONS}) without a final answer.",
    }


# ===================================================================
# FLASK ROUTES
# ===================================================================

SYSTEM_PROMPT_AI_LEARNING = """\
You are an AI tutor teaching a Java developer about RAG, LLM, and HuggingFace technologies. \
The student is a beginner in AI/ML and wants to build deep understanding from the ground up.

IMPORTANT — Teaching structure (you MUST follow this order for every topic):
1. FIRST: Explain the fundamental concept in plain English — what it is, why it exists, how it works in general. Assume the student knows nothing about this topic. Start from zero.
2. THEN: Go deeper — explain the theory, key algorithms, trade-offs, and common patterns. Give enough depth that the student truly understands.
3. ONLY AFTER steps 1 and 2: Connect to the student's Jarvis project as a real-world example to reinforce what was taught.

Do NOT jump straight to project-specific details. Always teach the general knowledge first.

Teaching style:
- Use plain English, avoid jargon without explanation
- When introducing a term, always define it simply first (e.g., "Embedding — a way to turn text into numbers that capture meaning")
- Break complex topics into small, digestible pieces
- Use analogies and real-world comparisons to explain abstract concepts
- Include code snippets when helpful
- At the end of each lesson, suggest what to learn next

Knowledge sources (use in this priority):
1. The RAG knowledge base — pull from indexed books, PDFs, and documentation first
2. If the knowledge base lacks depth on a topic, explain from your own training knowledge
3. ALWAYS provide learning references at the end of each answer:
   - Link to relevant documentation, tutorials, or articles (use real URLs)
   - Suggest specific book chapters or sections if available in the knowledge base
   - Format as: "📚 Learn more:" followed by a bullet list of links

The student's system (Jarvis) uses: Qdrant (vector DB), SentenceTransformers (MiniLM-L6-v2), \
BM25 hybrid search, cross-encoder reranking, Ollama (qwen3.5:4b, qwen3:1.7b), Flask."""

SYSTEM_PROMPT_ENGLISH_LEARNING = """\
You are a tech English tutor helping a non-native speaker improve their technical communication. \
The student is a Java developer in healthcare IT.

When the student selects a news article topic, you MUST:
1. First, give a brief summary of the article in simple English
2. Then analyze the article content — extract and teach:
   - Key technical phrases and expressions (with definitions and example usage)
   - How to pronounce or present difficult terms
   - Useful sentence patterns for demos/presentations (e.g., "Let me walk you through...", "The key takeaway is...")
3. Show how a native speaker would explain this topic in a meeting or presentation
4. Only AFTER the analysis, invite the student to ask questions or practice

When the student writes free text:
- ALWAYS correct grammar or word choice errors (show correction + explain why)
- Suggest better phrasing for technical communication
- Answer in English, explain grammar rules simply"""

SYSTEM_PROMPT_CASUAL_ENGLISH = """\
You are a friendly English conversation tutor helping a non-native speaker improve their everyday English.

When the student selects a news article topic, you MUST:
1. First, give a brief summary of the article in simple, everyday English
2. Then analyze the article content — extract and teach:
   - Useful casual phrases, idioms, and natural expressions from the article
   - Vocabulary for daily life and social situations
   - How a native speaker would casually tell a friend about this news
3. Include cultural context when relevant (Western social norms, common reactions)
4. Show example conversations: "If you were telling a colleague about this, you might say..."
5. Only AFTER the analysis, invite the student to ask questions or practice

When the student writes free text:
- ALWAYS correct grammar and word choice errors (show correction + brief explanation)
- Suggest more natural phrasing
- Be warm, encouraging, and conversational
- Answer in English, keep explanations simple and practical"""

SYSTEM_PROMPT_AWS_CERT = """\
You are an AWS certification tutor preparing a Java developer for the \
AWS Certified AI Practitioner (AIF-C01) exam. The student has a strong \
software engineering background but is building AI/ML knowledge from \
foundational level. All teaching and communication must be in English.

The exam has 5 domains:
  Domain 1 — Fundamentals of AI and ML (20%)
  Domain 2 — Fundamentals of Generative AI (24%)
  Domain 3 — Applications of Foundation Models (28%)
  Domain 4 — Guidelines for Responsible AI (14%)
  Domain 5 — Security, Compliance & Governance (14%)

You operate in two modes — TEACH and QUIZ — based on the student's request:

=== TEACH MODE (default) ===
Triggered by: "teach me ...", a topic name, a domain/task reference, or any knowledge question.
Teaching structure (follow this order):
1. State which domain and task this topic belongs to, and its exam weight.
2. Explain the concept from zero — assume the student knows nothing about this topic. \
Define every term before using it.
3. Go deeper — AWS services involved, how they work, trade-offs, when to use what.
4. Exam tips — what the exam tests about this topic, common wrong-answer traps.
5. Suggest what to study next based on the roadmap.

=== QUIZ MODE ===
Triggered by: "quiz me on ...", "test me ...", "practice questions for ...".
Quiz structure:
1. Generate 5 multiple-choice questions matching the AIF-C01 exam format \
(4 options: A/B/C/D, exactly one correct answer).
2. Present ALL 5 questions at once (numbered Q1–Q5).
3. Wait for the student's answers.
4. After receiving answers, score them (X/5) and explain each answer — \
why the correct answer is right AND why each wrong answer is wrong.
5. Identify weak areas and suggest topics to review.

=== PROGRESS MODE ===
Triggered by: "progress", "show progress", "how am I doing", "status".
Show a summary of domains studied, quiz scores, and recommended next steps.

Knowledge sources (priority order):
1. The RAG knowledge base — indexed AIF-C01 study books, slides, and structured notes
2. Your own training knowledge about AWS services and AI/ML concepts
3. Web references (if provided) as supplementary material

Teaching style:
- Clear, structured explanations with real-world analogies
- Always connect concepts to specific AWS services
- Use tables for comparisons (e.g., Bedrock vs SageMaker)
- Include "Exam tip:" callouts for high-yield points
- At the end of each lesson, provide 📚 references to learn more

Key exam facts to always keep in mind:
- Customization order: Prompt Engineering → RAG → Fine-tuning → Pre-training
- Amazon Bedrock = managed FMs via API (no infrastructure)
- Amazon SageMaker = full ML platform (build/train/deploy)
- Responsible AI = FEPST (Fairness, Explainability, Privacy, Safety, Transparency)
- Domains 2+3 = 52% of exam — focus heavily on GenAI and Bedrock"""


def _resolve_topic_from_history(query: str, history: list[dict]) -> str | None:
    """If query is a topic number reference (e.g. '16', 'topic 16'), resolve it
    to the actual topic title from the most recent assistant message that
    contains a topic-selection numbered list. Prefers messages with topic
    selection markers ('Pick a topic', 'Type a number'). Skips bold items."""
    import re
    m = re.match(r"^(?:topic\s*)?#?\s*(\d{1,2})\s*$", query.strip(), re.IGNORECASE)
    if not m:
        return None
    target_num = int(m.group(1))
    _topic_markers = ("pick a topic", "type a number", "choose a topic",
                      "select a topic", "topics to choose")
    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if not any(marker in content.lower() for marker in _topic_markers):
            continue
        numbered = re.findall(r"^\s*(\d{1,2})\.\s+(.+)$", content, re.MULTILINE)
        if not numbered:
            continue
        for num_str, title in numbered:
            clean = title.strip()
            if clean.startswith("**"):
                continue
            if int(num_str) == target_num:
                return clean
    return None


def _wants_more_topics(query: str) -> bool:
    """Detect if the user is asking for new/different topics."""
    q = query.lower().strip()
    signals = [
        "more topic", "other topic", "new topic", "different topic",
        "change topic", "switch topic", "another topic",
        "give me more", "show me more", "next topic",
        "refresh topic", "更多", "换一个",
    ]
    return any(s in q for s in signals)


def _fetch_fresh_topics(session_id: str, history: list[dict]) -> str:
    """Fetch topics not already shown in the conversation history."""
    already_shown = set()
    for msg in history:
        if msg.get("role") != "assistant":
            continue
        import re
        for _, title in re.findall(r"^\s*\d{1,2}\.\s+(.+)$", msg.get("content", ""), re.MULTILINE):
            already_shown.add(title.strip().lower())

    lines = []
    if session_id == _LEARNING_SESSION_IDS.get("english_learning"):
        all_titles = _load_recent_ai_news_titles()
        fresh = [t for t in all_titles if t.strip().lower() not in already_shown]
        for i, t in enumerate(fresh[:20], 1):
            lines.append(f"{i}. {t}")
    elif session_id == _LEARNING_SESSION_IDS.get("casual_english"):
        all_items = _load_recent_world_news_titles()
        fresh = [it for it in all_items if it["title"].strip().lower() not in already_shown]
        for i, it in enumerate(fresh[:20], 1):
            lines.append(f"{i}. [{it['category']}] {it['title']}")
    return "\n".join(lines)


_WEB_SEARCH_PROXY = os.environ.get("BRIEFING_PROXY", "socks5://localhost:10808")


def _web_search_references(query: str, num_results: int = 5) -> str:
    """Search the web for learning references using DuckDuckGo HTML (no API key).
    Uses the same SOCKS proxy as the fetcher scripts."""
    try:
        import httpx
        from html.parser import HTMLParser

        class _DDGParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results: list[dict] = []
                self._in_link = False
                self._cur: dict = {}

            def handle_starttag(self, tag, attrs):
                d = dict(attrs)
                if tag == "a" and "result__a" in d.get("class", ""):
                    self._in_link = True
                    href = d.get("href", "")
                    if "uddg=" in href:
                        from urllib.parse import unquote, urlparse, parse_qs
                        parsed = parse_qs(urlparse(href).query)
                        href = unquote(parsed.get("uddg", [href])[0])
                    self._cur = {"url": href, "title": ""}

            def handle_data(self, data):
                if self._in_link:
                    self._cur["title"] += data

            def handle_endtag(self, tag):
                if tag == "a" and self._in_link:
                    self._in_link = False
                    if self._cur.get("url", "").startswith("http"):
                        self.results.append(self._cur)
                    self._cur = {}

        kwargs: dict = {
            "timeout": 15,
            "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis/1.0"},
            "params": {"q": query},
        }
        if _WEB_SEARCH_PROXY:
            kwargs["proxy"] = _WEB_SEARCH_PROXY
        resp = httpx.get("https://html.duckduckgo.com/html/", **kwargs)
        if resp.status_code != 200:
            return ""
        parser = _DDGParser()
        parser.feed(resp.text)
        refs = parser.results[:num_results]
        if not refs:
            return ""
        lines = ["\n📚 Learn more:"]
        for r in refs:
            lines.append(f"- [{r['title'].strip()}]({r['url']})")
        return "\n".join(lines)
    except Exception as e:
        print(f"[web-search] Failed: {e}")
        return ""


def _fetch_article_content(title: str, session_id: str) -> str:
    """Fetch the full article summary/content for a given topic title.
    Searches world news JSON (for casual english), briefing JSON (for tech english),
    the learning roadmap + docs (for AI learning), or AWS cert study notes."""
    title_lower = title.strip().lower()
    if session_id == _LEARNING_SESSION_IDS.get("aws_cert"):
        parts = []
        roadmap = _load_aws_cert_roadmap()
        if roadmap:
            import re
            sections = re.split(r"(?=^## )", roadmap, flags=re.MULTILINE)
            for section in sections:
                if title_lower in section.lower():
                    parts.append(section[:3000])
                    break
            if not parts:
                for section in sections:
                    for line in section.split("\n"):
                        if title_lower in line.lower():
                            parts.append(section[:3000])
                            break
                    if parts:
                        break
        import re as _re2
        dm = _re2.search(r"domain\s*(\d)", title_lower)
        tm = _re2.search(r"task\s*(\d)\.(\d)", title_lower)
        _aws_domain_file_map = {
            "1": "01-ai-ml-fundamentals.md",
            "2": "02-genai-fundamentals.md",
            "3": "03-foundation-models.md",
            "4": "04-responsible-ai.md",
            "5": "05-security-compliance.md",
        }
        aws_notes_dir = os.path.join(KNOWLEDGE_ROOT, "notes", "aws_ai_p1")
        if os.path.isdir(aws_notes_dir):
            target_files = []
            if dm:
                d_num = dm.group(1)
                if d_num in _aws_domain_file_map:
                    target_files = [_aws_domain_file_map[d_num]]
            elif tm:
                d_num = tm.group(1)
                if d_num in _aws_domain_file_map:
                    target_files = [_aws_domain_file_map[d_num]]
            else:
                target_files = sorted(f for f in os.listdir(aws_notes_dir)
                                      if f.endswith(".md"))
            for fname in target_files:
                fpath = os.path.join(aws_notes_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    if title_lower in content.lower() or dm or tm:
                        if tm:
                            task_key = f"Task {tm.group(1)}.{tm.group(2)}"
                            sections = _re2.split(r"(?=^## )", content,
                                                  flags=_re2.MULTILINE)
                            for section in sections:
                                if task_key.lower() in section.lower():
                                    parts.append(
                                        f"From {fname}:\n\n{section[:4000]}")
                                    break
                        elif dm:
                            parts.append(f"From {fname}:\n\n{content[:5000]}")
                        else:
                            sections = _re2.split(r"(?=^## )", content,
                                                  flags=_re2.MULTILINE)
                            for section in sections:
                                if title_lower in section.lower():
                                    parts.append(
                                        f"From {fname}:\n\n{section[:3000]}")
                                    break
                        if len(parts) >= 3:
                            break
                except OSError:
                    continue
        return "\n\n---\n\n".join(parts) if parts else ""
    elif session_id == _LEARNING_SESSION_IDS.get("ai_learning"):
        roadmap = _load_ai_learning_roadmap()
        if roadmap:
            import re
            sections = re.split(r"(?=^## )", roadmap, flags=re.MULTILINE)
            for section in sections:
                if title_lower in section.lower():
                    return section[:3000]
        docs_dir = os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "docs"))
        if os.path.isdir(docs_dir):
            for fname in os.listdir(docs_dir):
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(docs_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    if title_lower in content.lower():
                        import re
                        sections = re.split(r"(?=^## )", content, flags=re.MULTILINE)
                        for section in sections:
                            if title_lower in section.lower():
                                return f"From {fname}:\n\n{section[:3000]}"
                except OSError:
                    continue
        return ""
    elif session_id == _LEARNING_SESSION_IDS.get("casual_english"):
        for d_offset in range(7):
            dt = (datetime.now() - timedelta(days=d_offset)).strftime("%Y-%m-%d")
            wn_path = os.path.join(REPORTS_ROOT, dt, "world-news", "world-news-data.json")
            if not os.path.isfile(wn_path):
                wn_path = os.path.join(REPORTS_ROOT, dt, "world-news-data.json")
            if os.path.isfile(wn_path):
                try:
                    with open(wn_path, "r", encoding="utf-8") as f:
                        wdata = json.load(f)
                    for cat in wdata.get("categories", []):
                        for article in cat.get("items", cat.get("articles", [])):
                            if article.get("title", "").strip().lower() == title_lower:
                                parts = [f"Title: {article.get('title', '')}"]
                                if article.get("source"):
                                    parts.append(f"Source: {article['source']}")
                                if article.get("url"):
                                    parts.append(f"URL: {article['url']}")
                                if article.get("summary"):
                                    parts.append(f"\n{article['summary']}")
                                points = article.get("points", [])
                                if points:
                                    parts.append("\nKey points:")
                                    for p in points:
                                        parts.append(f"- {p}")
                                return "\n".join(parts)
                except Exception:
                    continue
    elif session_id == _LEARNING_SESSION_IDS.get("english_learning"):
        for d_offset in range(7):
            dt = (datetime.now() - timedelta(days=d_offset)).strftime("%Y-%m-%d")
            for fname in ("briefing-data-filtered.json", "briefing-data.json"):
                json_path = os.path.join(REPORTS_ROOT, dt, fname)
                if os.path.isfile(json_path):
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        for section in data.get("sections", []):
                            for item in section.get("items", []):
                                if item.get("title", "").strip().lower() == title_lower:
                                    parts = [f"Title: {item.get('title', '')}"]
                                    if item.get("source"):
                                        parts.append(f"Source: {item['source']}")
                                    if item.get("url"):
                                        parts.append(f"URL: {item['url']}")
                                    if item.get("summary"):
                                        parts.append(f"\n{item['summary']}")
                                    if item.get("body"):
                                        parts.append(f"\n{item['body'][:2000]}")
                                    return "\n".join(parts)
                    except Exception:
                        continue
    return ""


@app.route("/api/agent", methods=["POST"])
def api_agent():
    """Main agent endpoint. Accepts JSON with query, optional image, optional history."""
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Empty query"}), 400

    image_b64 = data.get("image")
    history = data.get("history", [])
    session_id = data.get("session_id", "")

    learning_prompt = None
    is_learning = False
    if session_id == _LEARNING_SESSION_IDS.get("ai_learning"):
        learning_prompt = SYSTEM_PROMPT_AI_LEARNING
        is_learning = True
    elif session_id == _LEARNING_SESSION_IDS.get("english_learning"):
        learning_prompt = SYSTEM_PROMPT_ENGLISH_LEARNING
        is_learning = True
    elif session_id == _LEARNING_SESSION_IDS.get("casual_english"):
        learning_prompt = SYSTEM_PROMPT_CASUAL_ENGLISH
        is_learning = True
    elif session_id == _LEARNING_SESSION_IDS.get("aws_cert"):
        learning_prompt = SYSTEM_PROMPT_AWS_CERT
        is_learning = True

    is_aws_cert = session_id == _LEARNING_SESSION_IDS.get("aws_cert")
    rag_query_override = None
    effective_query = query
    web_refs = ""

    if is_aws_cert:
        query_lower = query.strip().lower()
        import re as _re
        _progress_triggers = ("progress", "show progress", "how am i doing",
                              "status", "my progress", "show status")
        _quiz_pattern = _re.compile(
            r"^(?:quiz|test|exam)\s+(?:me\s+)?(?:on\s+)?(.+)$"
            r"|^practice\s+(?:questions?\s+)?(?:for\s+|on\s+|about\s+)?(.+)$",
            _re.IGNORECASE,
        )
        _teach_pattern = _re.compile(
            r"^teach\s+(?:me\s+)?(?:about\s+)?(.+)$", _re.IGNORECASE
        )
        _domain_pattern = _re.compile(
            r"domain\s*(\d)", _re.IGNORECASE
        )
        _task_pattern = _re.compile(
            r"task\s*(\d)\.(\d)", _re.IGNORECASE
        )

        if query_lower in _progress_triggers:
            progress = _load_aws_cert_progress()
            progress_text = _format_aws_cert_progress(progress)
            effective_query = (
                f"The student asked to see their study progress. "
                f"Here is their current progress data:\n\n{progress_text}\n\n"
                f"Present this progress summary to them and recommend what to study next "
                f"based on the weakest domains. Be encouraging."
            )
        elif (qm := _quiz_pattern.match(query.strip())):
            quiz_topic = (qm.group(1) or qm.group(2) or query).strip()
            rag_query_override = f"AWS AIF-C01 {quiz_topic}"
            article_content = _fetch_article_content(quiz_topic, session_id)
            _update_aws_cert_progress(quiz_topic, "quiz")
            effective_query = (
                f"QUIZ MODE: Generate 5 multiple-choice questions about \"{quiz_topic}\" "
                f"in AIF-C01 exam format (4 options A/B/C/D, one correct).\n"
            )
            if article_content:
                effective_query += f"\nReference material:\n{article_content}\n"
            effective_query += (
                f"\nPresent all 5 questions numbered Q1-Q5, then wait for the "
                f"student's answers before scoring."
            )
        elif (tm := _teach_pattern.match(query.strip())):
            teach_topic = tm.group(1).strip()
            rag_query_override = f"AWS AIF-C01 {teach_topic}"
            article_content = _fetch_article_content(teach_topic, session_id)
            _update_aws_cert_progress(teach_topic, "teach")
            effective_query = (
                f"TEACH MODE: Teach the student about \"{teach_topic}\".\n"
            )
            if article_content:
                effective_query += f"\nReference material:\n{article_content}\n"
            effective_query += (
                f"\nFollow the teaching structure: domain context → concept from zero "
                f"→ deeper with AWS services → exam tips → next steps."
            )
        else:
            dm = _domain_pattern.search(query)
            tm2 = _task_pattern.search(query)
            if dm or tm2:
                article_content = _fetch_article_content(query, session_id)
                rag_query_override = f"AWS AIF-C01 {query}"
                topic_for_progress = query.strip()
                _update_aws_cert_progress(topic_for_progress, "teach")
                if article_content:
                    effective_query = (
                        f"The student wants to learn about: \"{query}\".\n\n"
                        f"Reference material:\n{article_content}\n\n"
                        f"Teach this following the TEACH MODE structure."
                    )
            else:
                rag_query_override = f"AWS AIF-C01 {query}"
                article_content = _fetch_article_content(query, session_id)
                if article_content:
                    effective_query = (
                        f"The student asks: \"{query}\"\n\n"
                        f"Reference material:\n{article_content}\n\n"
                        f"Answer using the reference material and your knowledge. "
                        f"Always note which exam domain this relates to."
                    )
                else:
                    web_refs = _web_search_references(
                        f"AWS AIF-C01 {query} certification", 3
                    )

    elif is_learning:
        resolved = _resolve_topic_from_history(query, history)
        if resolved:
            rag_query_override = resolved
            article_content = _fetch_article_content(resolved, session_id)
            if session_id == _LEARNING_SESSION_IDS.get("ai_learning"):
                web_refs = _web_search_references(f"{resolved} tutorial guide", 5)
            if article_content:
                if session_id == _LEARNING_SESSION_IDS.get("ai_learning"):
                    effective_query = (
                        f"The student selected topic: \"{resolved}\".\n\n"
                        f"Here is the full article content:\n{article_content}\n\n"
                        f"Teach them about this topic using the article above. "
                        f"Original input: {query}"
                    )
                else:
                    effective_query = (
                        f"The student selected topic: \"{resolved}\".\n\n"
                        f"Here is the full article content:\n{article_content}\n\n"
                        f"Analyze this article NOW. Do NOT ask the student questions first. "
                        f"Start by summarizing the article, then extract and teach the key "
                        f"phrases, expressions, and vocabulary from it. Show how to discuss "
                        f"this topic naturally in English. Original input: {query}"
                    )
            else:
                effective_query = (
                    f"The student selected topic: \"{resolved}\". "
                    f"Analyze this topic and teach them using the retrieved context below. "
                    f"Do NOT ask questions first — start teaching directly. "
                    f"Original input: {query}"
                )
        elif session_id == _LEARNING_SESSION_IDS.get("ai_learning") and not _wants_more_topics(query):
            web_refs = _web_search_references(f"{query} AI machine learning tutorial", 5)
        elif _wants_more_topics(query) and session_id != _LEARNING_SESSION_IDS.get("ai_learning"):
            topic_ctx = _fetch_fresh_topics(session_id, history)
            if topic_ctx:
                effective_query = (
                    f"The student wants new topics. Here are fresh topics to present:\n\n"
                    f"{topic_ctx}\n\n"
                    f"Present these as a new numbered list and ask the student to pick one. "
                    f"Original input: {query}"
                )

    if web_refs:
        effective_query += (
            f"\n\nIMPORTANT: At the end of your answer, include these real web references "
            f"for further learning (copy them exactly as-is, do not modify the URLs):\n\n{web_refs}"
        )

    def generate():
        for event in run_agent(effective_query, image_b64=image_b64,
                               conversation_history=history,
                               system_prompt_override=learning_prompt,
                               rag_query_override=rag_query_override):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        if web_refs:
            yield f"data: {json.dumps({'type': 'answer_chunk', 'content': chr(10) + chr(10) + web_refs + chr(10)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    """Record a user interaction event for feedback-weighted ranking."""
    try:
        rag_dir = os.path.dirname(os.path.abspath(__file__))
        if rag_dir not in sys.path:
            sys.path.insert(0, rag_dir)
        from feedback_store import record_event
        data = request.get_json() or {}
        record_event(
            query=data.get("query", ""),
            chunk_id=data.get("chunk_id", ""),
            action=data.get("action", ""),
            position=data.get("position", 0),
        )
        return jsonify({"recorded": True})
    except ImportError:
        return jsonify({"recorded": False, "error": "feedback_store not available"})


@app.route("/api/health")
def api_health():
    """Health check — verifies Ollama and Qdrant are reachable."""
    status = {"ollama": False, "qdrant": False, "model": OLLAMA_MODEL,
              "fast_model": OLLAMA_MODEL_FAST}
    try:
        import ollama
        models = ollama.list()
        available = [m.model for m in models.models] if models.models else []
        status["ollama"] = True
        status["ollama_models"] = available
        status["model_loaded"] = any(OLLAMA_MODEL in m for m in available)
    except Exception as e:
        status["ollama_error"] = str(e)

    try:
        client = _get_qdrant()
        info = client.get_collection(COLLECTION)
        status["qdrant"] = True
        status["qdrant_points"] = info.points_count or info.vectors_count
    except Exception as e:
        status["qdrant_error"] = str(e)

    return jsonify(status)


_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), ".global_settings.json")

_GLOBAL_SETTINGS_DEFAULTS = {
    "audio_lang_ai": "zh",
    "audio_lang_world": "zh",
    "audio_lang_china": "zh",
    "audio_lang_knowledge": "zh",
    "deepseek_api_key": "",
}


def _load_settings() -> dict:
    """Load settings from disk, merging with defaults."""
    settings = dict(_GLOBAL_SETTINGS_DEFAULTS)
    if os.path.isfile(_SETTINGS_FILE):
        try:
            with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.loads(f.read())
            settings.update(saved)
        except Exception:
            pass
    return settings


def _save_settings(settings: dict):
    """Persist settings to disk."""
    try:
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            f.write(json.dumps(settings, indent=2, ensure_ascii=False))
    except Exception:
        pass


_GLOBAL_SETTINGS = _load_settings()


def _get_deepseek_key() -> str:
    """Return the configured DeepSeek API key (settings > env var)."""
    return (_GLOBAL_SETTINGS.get("deepseek_api_key") or "").strip() \
        or os.environ.get("DEEPSEEK_API_KEY", "")


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    """Get or update global settings."""
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        for k in _GLOBAL_SETTINGS_DEFAULTS:
            if k in data:
                _GLOBAL_SETTINGS[k] = data[k]
        _save_settings(_GLOBAL_SETTINGS)
        return jsonify({"ok": True, "settings": _settings_safe()})
    return jsonify(_settings_safe())


def _settings_safe() -> dict:
    """Return settings with API key masked for GET responses."""
    out = dict(_GLOBAL_SETTINGS)
    key = out.get("deepseek_api_key", "")
    if key and len(key) > 8:
        out["deepseek_api_key_masked"] = key[:4] + "****" + key[-4:]
    else:
        out["deepseek_api_key_masked"] = ""
    out.pop("deepseek_api_key", None)
    return out


@app.route("/api/settings/deepseek-key", methods=["POST"])
def api_settings_deepseek_key():
    """Set the DeepSeek API key (separate endpoint for security)."""
    data = request.get_json(silent=True) or {}
    key = (data.get("api_key") or "").strip()
    _GLOBAL_SETTINGS["deepseek_api_key"] = key
    _save_settings(_GLOBAL_SETTINGS)
    masked = key[:4] + "****" + key[-4:] if len(key) > 8 else ("****" if key else "")
    return jsonify({"ok": True, "masked": masked})


@app.route("/api/deepseek/test", methods=["POST"])
def api_deepseek_test():
    """Test the DeepSeek API connection with a simple chat completion."""
    data = request.get_json(silent=True) or {}
    api_key = (data.get("api_key") or "").strip() or _get_deepseek_key()
    if not api_key:
        return jsonify({"ok": False, "error": "No API key configured"}), 400

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        response = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say hello in one sentence."},
            ],
            max_tokens=50,
            stream=False,
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}},
            timeout=30,
        )
        msg = response.choices[0].message
        return jsonify({
            "ok": True,
            "model": response.model or "unknown",
            "reply": msg.content or "",
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            } if response.usage else {},
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/switch-model", methods=["GET", "POST"])
def api_switch_model():
    """Get or set the active Ollama model."""
    global OLLAMA_MODEL
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        new_model = data.get("model", "").strip()
        if new_model:
            OLLAMA_MODEL = new_model
            return jsonify({"model": OLLAMA_MODEL, "changed": True})
        return jsonify({"error": "No model specified"}), 400
    return jsonify({"model": OLLAMA_MODEL})


# ---------------------------------------------------------------------------
# Chat session persistence (JSON files under REPORTS_ROOT/.chat-sessions)
# ---------------------------------------------------------------------------

def _ensure_chat_sessions_dir() -> None:
    os.makedirs(CHAT_SESSIONS_DIR, exist_ok=True)


def _parse_session_id(session_id: str) -> str | None:
    try:
        return str(uuid.UUID(session_id))
    except (ValueError, TypeError):
        return None


def _session_file_path(session_id: str) -> str:
    return os.path.join(CHAT_SESSIONS_DIR, f"{session_id}.json")


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _load_session_file(session_id: str) -> dict | None:
    path = _session_file_path(session_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _save_session_file(data: dict) -> bool:
    sid = data.get("id")
    if not sid:
        return False
    _ensure_chat_sessions_dir()
    path = _session_file_path(sid)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


@app.route("/api/sessions", methods=["GET"])
def api_sessions_list():
    """List recent chat sessions (metadata only), newest first, max 50."""
    _ensure_chat_sessions_dir()
    items = []
    try:
        for name in os.listdir(CHAT_SESSIONS_DIR):
            if not name.endswith(".json"):
                continue
            sid = name[:-5]
            if _parse_session_id(sid) is None:
                continue
            path = os.path.join(CHAT_SESSIONS_DIR, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            messages = data.get("messages")
            if not isinstance(messages, list):
                messages = []
            items.append({
                "id": data.get("id", sid),
                "title": data.get("title", "Untitled"),
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
                "message_count": len(messages),
            })
    except OSError as e:
        return jsonify({"error": str(e)}), 500

    items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    items = items[:50]
    return jsonify({"sessions": items})


@app.route("/api/sessions", methods=["POST"])
def api_sessions_create():
    """Create a new empty chat session."""
    _ensure_chat_sessions_dir()
    sid = str(uuid.uuid4())
    now = _now_iso()
    data = {
        "id": sid,
        "title": "New Chat",
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    if not _save_session_file(data):
        return jsonify({"error": "Failed to create session file"}), 500
    return jsonify(data)


@app.route("/api/sessions/<session_id>", methods=["GET"])
def api_sessions_get(session_id):
    sid = _parse_session_id(session_id)
    if not sid:
        return jsonify({"error": "Invalid session id"}), 400
    data = _load_session_file(sid)
    if not data:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(data)


@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def api_sessions_delete(session_id):
    sid = _parse_session_id(session_id)
    if not sid:
        return jsonify({"error": "Invalid session id"}), 400
    path = _session_file_path(sid)
    if not os.path.isfile(path):
        return jsonify({"error": "Session not found"}), 404
    try:
        os.remove(path)
    except OSError as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True, "id": sid})


@app.route("/api/sessions/<session_id>/messages", methods=["POST"])
def api_sessions_append_messages(session_id):
    sid = _parse_session_id(session_id)
    if not sid:
        return jsonify({"error": "Invalid session id"}), 400
    data = _load_session_file(sid)
    if not data:
        return jsonify({"error": "Session not found"}), 404

    body = request.get_json(silent=True) or {}
    user_msg = (body.get("user_message") or "").strip()
    assistant_msg = body.get("assistant_message")
    if assistant_msg is None:
        assistant_msg = ""
    else:
        assistant_msg = str(assistant_msg)
    if not user_msg and not assistant_msg:
        return jsonify({"error": "user_message or assistant_message is required"}), 400

    now = _now_iso()
    messages = data.get("messages")
    if not isinstance(messages, list):
        messages = []

    user_count_before = sum(1 for m in messages if isinstance(m, dict) and m.get("role") == "user")
    if user_count_before == 0 and user_msg:
        data["title"] = user_msg[:60]

    if user_msg:
        messages.append({"role": "user", "content": user_msg, "timestamp": now})
    if assistant_msg:
        messages.append({"role": "assistant", "content": assistant_msg, "timestamp": now})
    data["messages"] = messages
    data["updated_at"] = now

    if not _save_session_file(data):
        return jsonify({"error": "Failed to save session"}), 500
    return jsonify({
        "ok": True,
        "id": sid,
        "title": data["title"],
        "updated_at": data["updated_at"],
        "message_count": len(messages),
    })


@app.route("/api/sessions/<session_id>/clear", methods=["POST"])
def api_sessions_clear(session_id):
    """Clear all messages from a session, keeping the session itself."""
    sid = _parse_session_id(session_id)
    if not sid:
        return jsonify({"error": "Invalid session id"}), 400
    data = _load_session_file(sid)
    if not data:
        return jsonify({"error": "Session not found"}), 404
    data["messages"] = []
    data["updated_at"] = _now_iso()
    if not _save_session_file(data):
        return jsonify({"error": "Failed to save session"}), 500
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Learning Notes API
# ---------------------------------------------------------------------------

def _load_notes() -> list[dict]:
    if os.path.isfile(NOTES_FILE):
        try:
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return []


def _save_notes(notes: list[dict]) -> bool:
    try:
        os.makedirs(os.path.dirname(NOTES_FILE), exist_ok=True)
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


@app.route("/api/notes", methods=["GET"])
def api_notes_list():
    notes = _load_notes()
    tag = request.args.get("tag")
    if tag:
        notes = [n for n in notes if tag.lower() in [str(t).lower() for t in n.get("tags", []) if t]]
    notes.sort(key=lambda n: n.get("created_at", ""), reverse=True)
    return jsonify(notes)


@app.route("/api/notes", methods=["POST"])
def api_notes_create():
    body = request.get_json(silent=True) or {}
    content = (body.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content is required"}), 400
    note = {
        "id": str(uuid.uuid4()),
        "content": content,
        "title": body.get("title", content[:80]).strip(),
        "tags": body.get("tags", []),
        "session_id": body.get("session_id", ""),
        "session_type": body.get("session_type", ""),
        "created_at": _now_iso(),
    }
    notes = _load_notes()
    notes.append(note)
    if not _save_notes(notes):
        return jsonify({"error": "Failed to save"}), 500
    return jsonify(note), 201


@app.route("/api/notes/<note_id>", methods=["PUT"])
def api_notes_update(note_id):
    body = request.get_json(silent=True) or {}
    new_content = (body.get("content") or "").strip()
    if not new_content:
        return jsonify({"error": "content is required"}), 400
    notes = _load_notes()
    found = None
    for n in notes:
        if n.get("id") == note_id:
            found = n
            break
    if not found:
        return jsonify({"error": "Note not found"}), 404
    found["content"] = new_content
    found["title"] = new_content[:80].split("\n")[0]
    found["updated_at"] = _now_iso()
    if not _save_notes(notes):
        return jsonify({"error": "Failed to save"}), 500
    return jsonify({"ok": True, "note": found})


@app.route("/api/notes/<note_id>", methods=["DELETE"])
def api_notes_delete(note_id):
    notes = _load_notes()
    before = len(notes)
    notes = [n for n in notes if n.get("id") != note_id]
    if len(notes) == before:
        return jsonify({"error": "Note not found"}), 404
    if not _save_notes(notes):
        return jsonify({"error": "Failed to save"}), 500
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Toolbar API (background jobs, chunk stats, quick tools)
# ---------------------------------------------------------------------------

def _rag_scripts_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _run_index_new_briefings(job_id: str) -> None:
    """Index only NEW briefing date folders not yet in the RAG store."""
    status = "error"
    msg = ""
    try:
        rag_dir = _rag_scripts_dir()
        briefings_root = REPORTS_ROOT

        existing_dates = set()
        client = _get_qdrant()
        offset = None
        while True:
            result = client.scroll(
                collection_name=COLLECTION, limit=500, offset=offset,
                with_payload=["date", "source"], with_vectors=False,
            )
            points, next_offset = result
            for p in points:
                src = p.payload.get("source", "")
                if src in ("PDF Briefing", "learning-guide") or src.startswith("arxiv") or src.startswith("techcrunch"):
                    d = p.payload.get("date", "")
                    if d:
                        existing_dates.add(d)
            if next_offset is None:
                break
            offset = next_offset

        all_dates = sorted(
            d for d in os.listdir(briefings_root)
            if os.path.isdir(os.path.join(briefings_root, d))
            and re.match(r'\d{4}-\d{2}-\d{2}', d)
        )
        new_dates = [d for d in all_dates if d not in existing_dates]

        if not new_dates:
            status = "done"
            msg = f"No new briefings to index. {len(all_dates)} folders already indexed."
        else:
            sys.path.insert(0, rag_dir)
            from index_briefing import index_date_folder
            model = _get_embed_model()
            total_chunks = 0
            for date_folder_name in new_dates:
                folder_path = os.path.join(briefings_root, date_folder_name)
                try:
                    count = index_date_folder(folder_path, client, model)
                    total_chunks += count
                except Exception as e:
                    msg += f"\n  Error indexing {date_folder_name}: {e}"

            from index_briefing import _save_snapshot
            _save_snapshot(client)
            status = "done"
            msg = f"Indexed {len(new_dates)} new briefing(s) ({total_chunks} chunks). Skipped {len(existing_dates)} already indexed."
    except Exception as e:
        msg = f"Error: {e}\n{traceback.format_exc()}"
    with _toolbar_jobs_lock:
        j = _toolbar_jobs.get(job_id)
        if j:
            j["status"] = status
            j["result"] = msg


def _compute_chunk_analysis() -> dict[str, Any]:
    client = _get_qdrant()
    by_source: dict[str, int] = {}
    by_type: dict[str, int] = {}
    total = 0
    offset = None
    while True:
        result = client.scroll(
            collection_name=COLLECTION,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points, next_offset = result
        for p in points:
            total += 1
            pl = p.payload or {}
            src = str(pl.get("source") or "(unknown)")
            it = str(pl.get("item_type") or "(unknown)")
            by_source[src] = by_source.get(src, 0) + 1
            by_type[it] = by_type.get(it, 0) + 1
        if next_offset is None:
            break
        offset = next_offset
    return {
        "total": total,
        "by_source": by_source,
        "by_type": by_type,
    }


@app.route("/api/toolbar/reindex", methods=["POST"])
def api_toolbar_reindex():
    job_id = str(uuid.uuid4())
    started = _now_iso()
    with _toolbar_jobs_lock:
        _toolbar_jobs[job_id] = {
            "status": "running",
            "started": started,
            "result": "",
            "kind": "index_new",
        }
    threading.Thread(target=_run_index_new_briefings, args=(job_id,), daemon=True).start()
    return jsonify({"job_id": job_id, "status": "started"})


@app.route("/api/toolbar/reindex/<job_id>", methods=["GET"])
@app.route("/api/toolbar/wiki-fetch/<job_id>", methods=["GET"])
def api_toolbar_job_status(job_id: str):
    with _toolbar_jobs_lock:
        job = _toolbar_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404
    return jsonify({"job_id": job_id, **job})


@app.route("/api/toolbar/chunk-analysis", methods=["GET"])
def api_toolbar_chunk_analysis():
    global _chunk_analysis_cache, _chunk_analysis_cache_time
    now = time.time()
    with _chunk_analysis_cache_lock:
        if (
            _chunk_analysis_cache is not None
            and (now - _chunk_analysis_cache_time) < CHUNK_ANALYSIS_CACHE_TTL
        ):
            return jsonify(_chunk_analysis_cache)
    data = _compute_chunk_analysis()
    with _chunk_analysis_cache_lock:
        _chunk_analysis_cache = data
        _chunk_analysis_cache_time = time.time()
    return jsonify(data)


@app.route("/api/toolbar/wiki-fetch", methods=["POST"])
def api_toolbar_wiki_fetch():
    data = request.get_json(silent=True) or {}
    users = data.get("users")
    if not users:
        single = (data.get("user") or "").strip()
        users = [single] if single else ["Rong Yin"]
    users = [u.strip() for u in users if u.strip()]
    if not users:
        users = ["Rong Yin"]
    date_from = (data.get("date_from") or "").strip()
    date_to = (data.get("date_to") or "").strip()
    job_id = str(uuid.uuid4())
    started = _now_iso()
    with _toolbar_jobs_lock:
        _toolbar_jobs[job_id] = {
            "status": "running",
            "started": started,
            "result": "",
            "kind": "wiki_fetch",
            "users": users,
            "progress": f"0/{len(users)} users",
        }

    def _run_multi_user(jid, user_list, d_from, d_to):
        results = []
        for idx, user in enumerate(user_list):
            with _toolbar_jobs_lock:
                _toolbar_jobs[jid]["progress"] = f"{idx}/{len(user_list)} users ({user}...)"
            try:
                script = os.path.join(os.path.dirname(__file__), "index_confluence_user.py")
                cmd = [sys.executable, script, user]
                if d_from:
                    cmd.extend(["--date-from", d_from])
                if d_to:
                    cmd.extend(["--date-to", d_to])
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=600,
                    cwd=os.path.dirname(__file__),
                )
                out = proc.stdout.strip()
                results.append(f"[{user}] {out[-200:]}" if out else f"[{user}] done (no output)")
            except Exception as e:
                results.append(f"[{user}] error: {e}")
        summary = "\n".join(results)
        with _toolbar_jobs_lock:
            _toolbar_jobs[jid]["status"] = "done"
            _toolbar_jobs[jid]["result"] = summary[-3000:]
            _toolbar_jobs[jid]["progress"] = f"{len(user_list)}/{len(user_list)} users"

    threading.Thread(
        target=_run_multi_user, args=(job_id, users, date_from, date_to), daemon=True
    ).start()
    return jsonify({"job_id": job_id, "status": "started", "users": users})


@app.route("/api/toolbar/commit-summary", methods=["POST"])
def api_toolbar_commit_summary():
    data = request.get_json(silent=True) or {}
    raw_hours = data.get("hours", 24)
    try:
        hours = int(raw_hours)
    except (TypeError, ValueError):
        hours = 24
    hours = max(1, min(hours, 24 * 30))
    authors = data.get("authors") or None
    if isinstance(authors, list):
        authors = [a for a in authors if isinstance(a, str) and a.strip()]
        if not authors:
            authors = None
    else:
        authors = None
    since_date = data.get("since_date", "")
    until_date = data.get("until_date", "")
    result = tool_commit_summary(hours=hours, authors=authors,
                                 since_date=since_date, until_date=until_date)
    return jsonify({"result": result})


@app.route("/api/toolbar/jira-report", methods=["POST"])
def api_toolbar_jira_report():
    result = tool_jira_report()
    return jsonify({"result": result})


# ---------------------------------------------------------------------------
# Trend analysis (RAG + reports + streaming LLM)
# ---------------------------------------------------------------------------

_TREND_AI_TYPES = frozenset({"news_item", "arxiv_paper", "github_trending"})
_TREND_JIRA_TYPES = frozenset({"jira_ticket", "wiki_page"})


def _trend_date_prefix(payload: dict[str, Any]) -> str:
    d = payload.get("date") or ""
    if isinstance(d, str) and len(d) >= 10:
        return d[:10]
    return ""


def _payload_in_date_range(payload: dict[str, Any], start_s: str, end_s: str) -> bool:
    dp = _trend_date_prefix(payload)
    if len(dp) < 10:
        return False
    return start_s <= dp <= end_s


def _iter_trend_payloads() -> Iterator[dict[str, Any]]:
    """Payloads from `_qdrant_points` snapshot cache, or live Qdrant scroll if cache empty."""
    _get_qdrant()
    _sync_qdrant_points_from_snapshot()
    if _qdrant_points:
        for entry in _qdrant_points:
            yield entry.get("payload") or {}
        return
    client = _get_qdrant()
    offset = None
    while True:
        result = client.scroll(
            collection_name=COLLECTION,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points, next_offset = result
        for pt in points:
            yield pt.payload or {}
        if next_offset is None:
            break
        offset = next_offset


def _format_rag_item_line(p: dict[str, Any], text_max: int = 400) -> str:
    title = p.get("title", "Untitled")
    src = p.get("source", "")
    dt = p.get("date", "")
    it = p.get("item_type", "")
    text = (p.get("text") or "").replace("\n", " ").strip()[:text_max]
    auth = p.get("author")
    auth_s = f" | author={auth}" if auth else ""
    return f"- [{src}] ({dt}) [{it}]{auth_s} {title}: {text}"


def _top_rag_items_for_types(
    types: frozenset[str] | set[str],
    start_s: str,
    end_s: str,
    limit: int = 25,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in _iter_trend_payloads():
        it = str(payload.get("item_type") or "")
        if it not in types:
            continue
        if not _payload_in_date_range(payload, start_s, end_s):
            continue
        rows.append(dict(payload))
    rows.sort(key=lambda x: _trend_date_prefix(x) or "", reverse=True)
    return rows[:limit]


def _read_commit_reports_range(start_s: str, end_s: str, per_file_cap: int = 12000) -> str:
    parts: list[str] = []
    cur = datetime.strptime(start_s, "%Y-%m-%d").date()
    end_d = datetime.strptime(end_s, "%Y-%m-%d").date()
    while cur <= end_d:
        folder = os.path.join(REPORTS_ROOT, cur.strftime("%Y-%m-%d"))
        if os.path.isdir(folder):
            for path in sorted(glob.glob(os.path.join(folder, "commit-report-*.md"))):
                try:
                    with open(path, encoding="utf-8") as f:
                        body = f.read(per_file_cap)
                    parts.append(f"=== {os.path.basename(path)} ({cur}) ===\n{body}")
                except OSError:
                    pass
        cur += timedelta(days=1)
    return "\n\n".join(parts)


def _read_atlassian_reports_range(start_s: str, end_s: str, per_file_cap: int = 16000) -> str:
    parts: list[str] = []
    cur = datetime.strptime(start_s, "%Y-%m-%d").date()
    end_d = datetime.strptime(end_s, "%Y-%m-%d").date()
    while cur <= end_d:
        folder = os.path.join(REPORTS_ROOT, cur.strftime("%Y-%m-%d"))
        if os.path.isdir(folder):
            for path in sorted(glob.glob(os.path.join(folder, "atlassian*.md"))):
                try:
                    with open(path, encoding="utf-8") as f:
                        body = f.read(per_file_cap)
                    parts.append(f"=== {os.path.basename(path)} ({cur}) ===\n{body}")
                except OSError:
                    pass
        cur += timedelta(days=1)
    return "\n\n".join(parts)


def _build_trend_analysis_prompt(
    categories: list[str],
    days: int,
    start_s: str,
    end_s: str,
    blocks: list[str],
) -> str:
    cat_line = ", ".join(categories) if categories else "(none)"
    header = (
        f"You are an analyst for a software team (Portal4Med / P4M). "
        f"Date range: {start_s} to {end_s} (last {days} day(s)). "
        f"Selected categories: {cat_line}.\n\n"
        "Below is retrieved data from an internal RAG knowledge base and optional report files. "
        "Do NOT invent facts not supported by the data; clearly mark speculation as such.\n\n"
    )
    instructions = (
        "\n\n--- Your analysis (structured markdown) ---\n"
        "1. **Trends per category** — bullet summary for each category that had data.\n"
        "2. **Recurring themes** — patterns that appear across multiple items or days.\n"
        "3. **New vs continuing** — what emerged recently vs ongoing threads.\n"
        "4. **Predictions** — brief, grounded outlook for likely near-term developments (label uncertain reasoning).\n"
        "5. **Recommended actions** — concrete next steps for the team.\n"
    )
    body = "\n\n".join(blocks) if blocks else "(No data matched the filters.)"
    return header + body + instructions


@app.route("/api/toolbar/trend-analysis", methods=["POST"])
def api_toolbar_trend_analysis():
    data = request.get_json(silent=True) or {}
    raw_cats = data.get("categories") or []
    if not isinstance(raw_cats, list):
        raw_cats = []
    categories = [c for c in raw_cats if isinstance(c, str) and c.strip()]
    try:
        days = int(data.get("days", 7))
    except (TypeError, ValueError):
        days = 7
    days = max(1, min(days, 90))

    today = datetime.now().date()
    start_d = today - timedelta(days=days - 1)
    start_s = start_d.strftime("%Y-%m-%d")
    end_s = today.strftime("%Y-%m-%d")

    cats = set(categories)
    blocks: dict[str, str] = {}

    if "ai_news" in cats:
        items = _top_rag_items_for_types(_TREND_AI_TYPES, start_s, end_s, limit=30)
        if items:
            lines = [_format_rag_item_line(p) for p in items]
            blocks["ai_news"] = "\n".join(lines)
        else:
            blocks["ai_news"] = "(No matching RAG items in range.)"

    if "world_news" in cats:
        items = _top_rag_items_for_types(frozenset({"world_news"}), start_s, end_s, limit=25)
        if items:
            lines = [_format_rag_item_line(p) for p in items]
            blocks["world_news"] = "\n".join(lines)
        else:
            blocks["world_news"] = "(No matching RAG items in range.)"

    if "wiki" in cats:
        items = _top_rag_items_for_types(frozenset({"wiki_page"}), start_s, end_s, limit=30)
        if items:
            lines = [_format_rag_item_line(p) for p in items]
            blocks["wiki"] = "\n".join(lines)
        else:
            blocks["wiki"] = "(No matching RAG items in range.)"

    if "jira" in cats:
        items = _top_rag_items_for_types(_TREND_JIRA_TYPES, start_s, end_s, limit=35)
        jira_lines = [_format_rag_item_line(p) for p in items] if items else []
        atl = _read_atlassian_reports_range(start_s, end_s)
        sec = ""
        if jira_lines:
            sec += "RAG items:\n" + "\n".join(jira_lines) + "\n\n"
        if atl.strip():
            sec += "Atlassian reports:\n" + atl[:8000]
        elif not jira_lines:
            sec = "(No Jira RAG items or atlassian reports in range.)"
        blocks["jira"] = sec

    if "commits" in cats:
        cr = _read_commit_reports_range(start_s, end_s)
        blocks["commits"] = cr[:8000] if cr.strip() else "(No commit reports in range.)"

    cat_labels = {
        "ai_news": "AI News", "world_news": "World News",
        "wiki": "Wiki Pages", "jira": "Jira & Atlassian", "commits": "Git Commits"
    }
    cat_blocks = blocks

    def _stream_one_category(req_mod, cat_key, block_text):
        """Analyze one category via chat API with thinking disabled for speed."""
        label = cat_labels.get(cat_key, cat_key)
        user_msg = (
            f"Based on the following {label} data from the last {days} days "
            f"({start_s} to {end_s}), provide **predictions for the next 1-2 weeks**.\n\n"
            f"For each prediction:\n"
            f"- State the prediction clearly\n"
            f"- Cite which data points support it\n"
            f"- Rate confidence: High / Medium / Low\n"
            f"- Note potential impact on our team\n\n"
            f"Think deeply about patterns, trajectories, and implications before answering.\n\n"
            f"DATA:\n{block_text[:6000]}"
        )
        try:
            resp = req_mod.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": OLLAMA_MODEL_FAST,
                    "messages": [
                        {"role": "system", "content": "You are a strategic analyst for a software team. Think carefully about trends and make well-reasoned predictions."},
                        {"role": "user", "content": user_msg},
                    ],
                    "stream": True,
                    "think": True,
                    "options": {"num_predict": 4096, "temperature": 0.4},
                },
                stream=True,
                timeout=300,
            )
            raw = ""
            in_think = False
            for line in resp.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            raw += token
                            if "<think>" in raw and not in_think:
                                in_think = True
                            if in_think:
                                if "</think>" in raw:
                                    after = raw.split("</think>", 1)[-1]
                                    in_think = False
                                    raw = after
                                    if after.strip():
                                        yield after
                                continue
                            yield token
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            yield f"\n\n[Error analyzing {label}: {e}]\n"

    def generate():
        import requests as req
        full_text = ""
        ordered_cats = [c for c in categories if c in cat_blocks]
        for idx, cat_key in enumerate(ordered_cats):
            label = cat_labels.get(cat_key, cat_key)
            header = f"\n\n## {label} — Predictions\n\n"
            full_text += header
            yield f"data: {json.dumps({'type':'token','content':header})}\n\n"
            for token in _stream_one_category(req, cat_key, cat_blocks[cat_key]):
                full_text += token
                yield f"data: {json.dumps({'type':'token','content':token})}\n\n"
            if idx < len(ordered_cats) - 1:
                sep = "\n\n---\n"
                full_text += sep
                yield f"data: {json.dumps({'type':'token','content':sep})}\n\n"
        yield f"data: {json.dumps({'type':'done','content':full_text,'start':start_s,'end':end_s})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# AI News Knowledge Base
# ---------------------------------------------------------------------------
_AI_KB_PATH = os.path.join(REPORTS_ROOT, ".ai-news-kb.json")


def _load_ai_kb() -> dict[str, Any]:
    if os.path.exists(_AI_KB_PATH):
        with open(_AI_KB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"items": [], "last_scanned": None}


def _save_ai_kb(kb: dict[str, Any]) -> None:
    with open(_AI_KB_PATH, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=1)


def _extract_items_from_briefing_json(folder: str, date_str: str) -> list[dict[str, Any]]:
    """Extract news items from briefing-data JSON or fall back to PDF extraction."""
    items: list[dict[str, Any]] = []
    found_json = False
    for fname in ("briefing-data-filtered.json", "briefing-data.json"):
        path = os.path.join(folder, fname)
        if os.path.exists(path):
            found_json = True
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for src_block in data.get("per_source_data", []):
                    source = src_block.get("name") or src_block.get("source_name") or "Unknown"
                    for it in src_block.get("items", []):
                        title = it.get("title", "").strip()
                        if not title:
                            continue
                        summary = it.get("summary", "") or ""
                        if isinstance(summary, list):
                            summary = " ".join(summary)
                        points = it.get("points", [])
                        if isinstance(points, list) and points:
                            summary = (summary + " " + " ".join(str(p) for p in points[:3])).strip()
                        url = it.get("url", "") or it.get("link", "") or ""
                        items.append({
                            "date": date_str,
                            "source": source,
                            "title": title,
                            "summary": summary[:500],
                            "url": url,
                            "category": "",
                        })
            except (json.JSONDecodeError, OSError):
                pass
            break

    if not found_json:
        items = _extract_items_from_pdf(folder, date_str)
    return items


def _extract_items_from_pdf(folder: str, date_str: str) -> list[dict[str, Any]]:
    """Extract news items from ai-briefing.pdf using text parsing."""
    pdf_path = os.path.join(folder, "ai-briefing.pdf")
    if not os.path.exists(pdf_path):
        return []
    items: list[dict[str, Any]] = []
    _known_sources = {
        "Arxiv Machine Learning", "Arxiv AI", "OpenAI", "Anthropic",
        "Google DeepMind", "TechCrunch", "The Rundown", "GitHub Trending",
        "MIT Technology Review",
    }
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        full_text = "\n".join(page.extract_text() or "" for page in reader.pages)

        current_source = ""
        lines = full_text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Source headers: "Arxiv Machine Learning (Deep Tech & Papers)" or "OpenAI News (Lab Blog)"
            source_match = re.match(r"^(?:★\s*)?(.+?)\s*\(.+\)\s*$", line)
            if source_match:
                candidate = source_match.group(1).strip()
                # Verify it looks like a known source (fuzzy)
                for ks in _known_sources:
                    if ks.lower() in candidate.lower() or candidate.lower() in ks.lower():
                        current_source = candidate
                        break
                i += 1
                continue
            title_match = re.match(r"^(\d+)\.\s+(.+)", line)
            if title_match and current_source:
                title = title_match.group(2).strip()
                summary_parts: list[str] = []
                url = ""
                j = i + 1
                while j < len(lines) and j < i + 30:
                    sl = lines[j].strip()
                    if re.match(r"^\d+\.\s+", sl):
                        break
                    if re.match(r"^(?:★\s*)?(.+?)\s*\(.+\)\s*$", sl):
                        for ks in _known_sources:
                            if ks.lower() in sl.lower():
                                break
                        else:
                            j += 1
                            continue
                        break
                    url_match = re.search(r"(https?://\S+)", sl)
                    if url_match and not url:
                        url = url_match.group(1).rstrip(")")
                    if sl.startswith("What this paper is about") or sl.startswith("What"):
                        summary_parts.append(sl)
                    elif sl and not sl.startswith("Analyst Note") and not sl.startswith("Impact Forecast") and not sl.startswith("Source:"):
                        if len(summary_parts) < 5:
                            summary_parts.append(sl)
                    j += 1
                summary = " ".join(summary_parts)[:500]
                if title and len(title) > 5:
                    items.append({
                        "date": date_str,
                        "source": current_source,
                        "title": title,
                        "summary": summary,
                        "url": url,
                        "category": "",
                    })
            i += 1
    except Exception:
        pass
    return items


def _categorize_items_batch(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use LLM to assign categories to uncategorized items."""
    uncategorized = [it for it in items if not it.get("category")]
    if not uncategorized:
        return items

    batch_size = 25
    categories_list = [
        "LLM & Foundation Models", "AI Agents & Tools", "Computer Vision",
        "NLP & Language", "Robotics & Embodied AI", "AI Safety & Ethics",
        "AI Infrastructure & MLOps", "AI in Healthcare", "AI Business & Funding",
        "Open Source & Community", "Research & Papers", "Other"
    ]
    cat_str = ", ".join(categories_list)

    import requests as req_mod
    for start in range(0, len(uncategorized), batch_size):
        batch = uncategorized[start:start + batch_size]
        lines = []
        for i, it in enumerate(batch):
            lines.append(f"{i+1}. [{it['source']}] {it['title']}: {it['summary'][:120]}")
        prompt = (
            f"Categorize each news item into exactly one category from: {cat_str}\n"
            f"Reply with ONLY a numbered list like:\n1. Category Name\n2. Category Name\n\n"
            f"Items:\n" + "\n".join(lines)
        )
        try:
            resp = req_mod.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": OLLAMA_MODEL_FAST,
                    "messages": [
                        {"role": "system", "content": "You categorize AI news items. Reply with ONLY the numbered category list, nothing else."},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "think": False,
                    "options": {"num_predict": 512, "temperature": 0.1},
                },
                timeout=60,
            )
            resp.raise_for_status()
            text = resp.json().get("message", {}).get("content", "")
            for line in text.strip().split("\n"):
                m = re.match(r"(\d+)\.\s*(.+)", line.strip())
                if m:
                    idx = int(m.group(1)) - 1
                    cat = m.group(2).strip().rstrip(".")
                    if 0 <= idx < len(batch):
                        if cat in categories_list:
                            batch[idx]["category"] = cat
                        else:
                            best = min(categories_list, key=lambda c: abs(len(c) - len(cat)))
                            batch[idx]["category"] = best
        except Exception:
            pass

    for it in uncategorized:
        if not it.get("category"):
            it["category"] = "Other"
    return items


@app.route("/api/toolbar/ai-news-kb", methods=["GET"])
def api_ai_news_kb_get():
    kb = _load_ai_kb()
    return jsonify({
        "items": kb["items"],
        "last_scanned": kb.get("last_scanned"),
        "total": len(kb["items"]),
    })


@app.route("/api/toolbar/ai-news-kb/scan", methods=["POST"])
def api_ai_news_kb_scan():
    """Scan all report folders, extract items from JSONs, categorize, merge with existing KB."""
    kb = _load_ai_kb()
    existing_keys: set[str] = set()
    for it in kb["items"]:
        existing_keys.add(f"{it['date']}|{it['title']}")

    new_items: list[dict[str, Any]] = []
    report_root = REPORTS_ROOT
    for entry in sorted(os.listdir(report_root)):
        folder = os.path.join(report_root, entry)
        if not os.path.isdir(folder) or not re.match(r"\d{4}-\d{2}-\d{2}$", entry):
            continue
        extracted = _extract_items_from_briefing_json(folder, entry)
        for it in extracted:
            key = f"{it['date']}|{it['title']}"
            if key not in existing_keys:
                new_items.append(it)
                existing_keys.add(key)

    if new_items:
        _categorize_items_batch(new_items)
        kb["items"].extend(new_items)
        kb["items"].sort(key=lambda x: x.get("date", ""), reverse=True)

    kb["last_scanned"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _save_ai_kb(kb)

    return jsonify({
        "new_count": len(new_items),
        "total": len(kb["items"]),
        "last_scanned": kb["last_scanned"],
    })


@app.route("/api/toolbar/ai-news-kb/summary", methods=["POST"])
def api_ai_news_kb_summary():
    """Generate an AI summary of the knowledge base with learning links."""
    kb = _load_ai_kb()
    if not kb["items"]:
        return jsonify({"error": "No items in KB. Run Scan first."}), 400

    recent = kb["items"][:80]
    cat_groups: dict[str, list[str]] = {}
    for it in recent:
        cat = it.get("category", "Other")
        cat_groups.setdefault(cat, []).append(
            f"- [{it['source']}] ({it['date']}) {it['title']}: {it['summary'][:100]}"
        )

    data_block = ""
    for cat, lines in sorted(cat_groups.items()):
        data_block += f"\n### {cat}\n" + "\n".join(lines[:12]) + "\n"

    user_msg = (
        f"Below is a categorized AI news knowledge base ({len(recent)} items). "
        f"Provide:\n"
        f"1. **Top Themes** — the 5-8 dominant themes across all categories\n"
        f"2. **Key Developments** — the most impactful 5-8 items with a plain-English explanation "
        f"of the technology (assume the reader is a Java developer learning AI)\n"
        f"3. **Learning Path** — for each key development, suggest a concrete resource "
        f"(paper link, GitHub repo, tutorial, blog post) with estimated time to learn\n"
        f"4. **Emerging Trends** — what's gaining momentum and likely to matter in 2-4 weeks\n"
        f"5. **Connections to Healthcare IT** — any items relevant to medical imaging, DICOM, FHIR\n\n"
        f"DATA:\n{data_block[:8000]}"
    )

    import requests as req_mod

    def generate():
        try:
            resp = req_mod.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": OLLAMA_MODEL_FAST,
                    "messages": [
                        {"role": "system", "content": "You are an AI technology analyst writing for a Java developer in healthcare IT. Be specific, cite items from the data, and include actionable learning resources."},
                        {"role": "user", "content": user_msg},
                    ],
                    "stream": True,
                    "think": False,
                    "options": {"num_predict": 3072, "temperature": 0.3},
                },
                stream=True,
                timeout=300,
            )
            full = ""
            for line in resp.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            full += token
                            yield f"data: {json.dumps({'type':'token','content':token})}\n\n"
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        pass
            yield f"data: {json.dumps({'type':'done','content':full})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Audio from Knowledge
# ---------------------------------------------------------------------------
_audio_jobs: dict[str, dict] = {}


def _generate_knowledge_audio(job_id: str, item_type: str,
                              selected_parents: list[str],
                              language: str):
    """Background worker: gather RAG content for selected items, enrich via web, generate narration, produce MP3."""
    try:
        _audio_jobs[job_id]["status"] = "searching"
        _get_qdrant()
        _sync_qdrant_points_from_snapshot()

        items = []
        for entry in _qdrant_points:
            pl = entry.get("payload") or {}
            if pl.get("item_type") != item_type:
                continue
            parent = pl.get("parent_title") or pl.get("filename") or pl.get("title") or "Untitled"
            if selected_parents and parent not in selected_parents:
                continue
            items.append({
                "title": pl.get("title", "Untitled"),
                "date": (pl.get("date") or "")[:10],
                "source": pl.get("source", ""),
                "type": pl.get("item_type", ""),
                "text": (pl.get("text") or ""),
            })

        if not items:
            _audio_jobs[job_id]["status"] = "done"
            _audio_jobs[job_id]["error"] = "No matching content found in the knowledge base for the selected criteria."
            return

        _audio_jobs[job_id]["status"] = "searching_web"
        _audio_jobs[job_id]["items_found"] = len(items)

        rag_sections = []
        total_chars = 0
        content_cap = 40000
        for it in items:
            text = it["text"].strip()
            if total_chars + len(text) > content_cap:
                text = text[:max(0, content_cap - total_chars)]
            if text:
                rag_sections.append(f"### {it['title']}\n{text}")
                total_chars += len(text)
            if total_chars >= content_cap:
                break
        rag_block = "\n\n".join(rag_sections)

        key_topics = set()
        for it in items[:5]:
            key_topics.add(it["title"])
        web_block = ""
        if key_topics:
            search_query = " ".join(list(key_topics)[:3])[:120]
            web_refs = _web_search_references(search_query + " latest news update", 5)
            if web_refs:
                web_block = web_refs

        _audio_jobs[job_id]["status"] = "generating_script"

        if language == "en":
            voice = "en-US-AndrewNeural"
            lang_instruction = "Write in conversational English."
            section_rag = "FROM KNOWLEDGE BASE"
            section_web = "LATEST FROM THE WEB"
        else:
            voice = "zh-CN-YunxiNeural"
            lang_instruction = "用中文写播客旁白。技术术语保留英文。Write the narration in Chinese (中文)."
            section_rag = "知识库内容"
            section_web = "最新网上资讯"

        web_instruction = ""
        if web_block:
            web_instruction = f"""

Also include a section about latest web findings. Clearly separate it from the knowledge base content.
Section 1 header: [{section_rag}]
Section 2 header: [{section_web}]

Web references found:
{web_block}"""

        user_msg = f"""{lang_instruction} Write a LONG, comprehensive educational podcast narration (~10 minutes of spoken content, approximately 8000-12000 characters). Cover ALL the content below in depth. Explain concepts, provide context, discuss implications, and connect ideas across topics. Make it feel like a real educational podcast episode — engaging, thorough, and informative. Output ONLY the narration text.

Knowledge base content:
{rag_block}{web_instruction}"""

        import requests as _requests
        resp = _requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL_FAST,
                "messages": [
                    {"role": "system", "content": "You are an educational podcast narrator producing long-form content. Create comprehensive, in-depth narrations that thoroughly teach the listener. Cover every topic with full explanations, context, examples, and insights. Aim for ~10 minutes of spoken content. No markdown, no formatting — pure narration text."},
                    {"role": "user", "content": user_msg},
                ],
                "stream": False,
                "think": True,
                "options": {"temperature": 0.7, "num_predict": 16384},
            },
            timeout=900,
        )
        resp.raise_for_status()
        resp_data = resp.json()
        narration = resp_data.get("message", {}).get("content", "").strip()
        if not narration:
            narration = resp_data.get("thinking", "").strip()

        narration = re.sub(r"</?think>", "", narration).strip()
        narration = re.sub(r"```[a-z]*\n?", "", narration).strip()
        narration = narration.strip("`").strip()
        for prefix in ["Narration:", "Script:", "Podcast Script:", "Here is", "Here's"]:
            if narration.lower().startswith(prefix.lower()):
                narration = narration[len(prefix):].strip()
        narration = _clean_narration_for_tts(narration)

        if not narration:
            _audio_jobs[job_id]["status"] = "done"
            _audio_jobs[job_id]["error"] = "LLM returned empty narration."
            return
        _audio_jobs[job_id]["status"] = "generating_audio"
        _audio_jobs[job_id]["narration_length"] = len(narration)

        import asyncio
        import edge_tts
        import tempfile

        today_str = datetime.now().strftime("%Y-%m-%d")
        out_dir = os.path.join(REPORTS_ROOT, today_str)
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%H%M%S")
        out_filename = f"knowledge-audio-{ts}.mp3"
        out_path = os.path.join(out_dir, out_filename)

        async def _do_tts():
            chunks = []
            chunk_size = 2000
            text = narration
            while text:
                if len(text) <= chunk_size:
                    chunks.append(text)
                    break
                split_at = text.rfind("。", 0, chunk_size)
                if split_at < 0:
                    split_at = text.rfind(".", 0, chunk_size)
                if split_at < 0:
                    split_at = chunk_size
                else:
                    split_at += 1
                chunks.append(text[:split_at])
                text = text[split_at:].strip()

            if len(chunks) == 1:
                comm = edge_tts.Communicate(chunks[0], voice, rate="-5%", pitch="+0Hz")
                await comm.save(out_path)
            else:
                part_paths = []
                for i, chunk in enumerate(chunks):
                    part = os.path.join(out_dir, f"_ka_part_{i}.mp3")
                    comm = edge_tts.Communicate(chunk, voice, rate="-5%", pitch="+0Hz")
                    await comm.save(part)
                    part_paths.append(part)
                import shutil
                ffmpeg = shutil.which("ffmpeg")
                if ffmpeg:
                    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as lf:
                        for p in part_paths:
                            lf.write(f"file '{os.path.abspath(p).replace(chr(92), '/')}'\n")
                        list_path = lf.name
                    subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0",
                                    "-i", list_path, "-c", "copy", out_path],
                                   check=True, capture_output=True)
                    os.unlink(list_path)
                else:
                    with open(out_path, "wb") as out:
                        for p in part_paths:
                            with open(p, "rb") as pf:
                                out.write(pf.read())
                for p in part_paths:
                    try:
                        os.remove(p)
                    except OSError:
                        pass

        asyncio.run(_do_tts())

        _audio_jobs[job_id]["status"] = "done"
        _audio_jobs[job_id]["output_path"] = out_path
        _audio_jobs[job_id]["output_url"] = f"/api/toolbar/audio-file/{today_str}/{out_filename}"
        _audio_jobs[job_id]["narration_preview"] = narration[:500]

    except Exception as e:
        _audio_jobs[job_id]["status"] = "done"
        _audio_jobs[job_id]["error"] = str(e)
        traceback.print_exc()


@app.route("/api/toolbar/audio-knowledge", methods=["POST"])
def api_audio_knowledge():
    data = request.get_json(silent=True) or {}
    item_type = data.get("item_type", "")
    selected_parents = data.get("selected_parents", [])
    language = data.get("language", "zh")
    if not item_type:
        return jsonify({"error": "Missing item_type"}), 400
    job_id = str(uuid.uuid4())[:8]
    _audio_jobs[job_id] = {"status": "queued", "created": datetime.now().isoformat()}
    threading.Thread(
        target=_generate_knowledge_audio,
        args=(job_id, item_type, selected_parents, language),
        daemon=True,
    ).start()
    return jsonify({"job_id": job_id})


@app.route("/api/toolbar/audio-knowledge/history", methods=["GET"])
def api_audio_knowledge_history():
    """List previously generated knowledge-audio MP3 files."""
    history = []
    if os.path.isdir(REPORTS_ROOT):
        for date_dir in sorted(os.listdir(REPORTS_ROOT), reverse=True):
            date_path = os.path.join(REPORTS_ROOT, date_dir)
            if not os.path.isdir(date_path) or len(date_dir) != 10:
                continue
            for fname in sorted(os.listdir(date_path), reverse=True):
                if fname.startswith("knowledge-audio-") and fname.endswith(".mp3"):
                    fpath = os.path.join(date_path, fname)
                    size_kb = round(os.path.getsize(fpath) / 1024)
                    time_part = fname.replace("knowledge-audio-", "").replace(".mp3", "")
                    display_time = f"{time_part[:2]}:{time_part[2:4]}:{time_part[4:]}" if len(time_part) == 6 else time_part
                    history.append({
                        "date": date_dir,
                        "filename": fname,
                        "display": f"{date_dir} {display_time}",
                        "size_kb": size_kb,
                        "url": f"/api/toolbar/audio-file/{date_dir}/{fname}",
                    })
            if len(history) >= 20:
                break
    return jsonify({"history": history})


@app.route("/api/toolbar/audio-knowledge/items", methods=["GET"])
def api_audio_knowledge_items():
    """List available documents grouped by parent_title for a given item_type."""
    item_type = request.args.get("type", "")
    if not item_type:
        return jsonify({"error": "Missing 'type' parameter"}), 400

    _get_qdrant()
    _sync_qdrant_points_from_snapshot()

    groups: dict[str, dict] = {}
    for entry in _qdrant_points:
        pl = entry.get("payload") or {}
        if pl.get("item_type") != item_type:
            continue
        parent = pl.get("parent_title") or pl.get("filename") or pl.get("title") or "Untitled"
        date_val = (pl.get("date") or "")[:10]
        chunk_title = pl.get("title", "")
        point_id = entry.get("id", "")

        if parent not in groups:
            groups[parent] = {"parent_title": parent, "date": date_val, "chunks": [], "chunk_count": 0}
        groups[parent]["chunk_count"] += 1
        if date_val and (not groups[parent]["date"] or date_val > groups[parent]["date"]):
            groups[parent]["date"] = date_val

        if item_type == "book_chapter" and chunk_title and chunk_title != parent:
            existing_titles = {c["title"] for c in groups[parent]["chunks"]}
            if chunk_title not in existing_titles:
                groups[parent]["chunks"].append({"title": chunk_title, "id": str(point_id)})

    result = sorted(groups.values(), key=lambda g: g.get("date") or "", reverse=True)
    for g in result:
        g["chunks"].sort(key=lambda c: c.get("title", ""))

    show_dates = item_type in ("news_item", "raw_content", "learning_guide")
    return jsonify({"items": result, "show_dates": show_dates, "item_type": item_type})


@app.route("/api/toolbar/audio-knowledge/<job_id>", methods=["GET"])
def api_audio_knowledge_status(job_id):
    job = _audio_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/api/toolbar/audio-file/<date_str>/<filename>")
def api_serve_audio_file(date_str, filename):
    """Serve generated files (audio, PDF) for playback/download."""
    file_path = os.path.join(REPORTS_ROOT, date_str, filename)
    if not os.path.isfile(file_path):
        return jsonify({"error": "File not found"}), 404
    mime = "audio/mpeg"
    if filename.endswith(".pdf"):
        mime = "application/pdf"
    return send_file(file_path, mimetype=mime, as_attachment=False,
                     download_name=filename)


@app.route("/api/toolbar/report-content/<date_str>/<filename>")
def api_serve_report_content(date_str, filename):
    """Return the text content of a report file (markdown/text) for inline rendering."""
    if not filename.endswith((".md", ".txt")):
        return jsonify({"error": "Only .md and .txt files supported"}), 400
    file_path = os.path.join(REPORTS_ROOT, date_str, filename)
    if not os.path.isfile(file_path):
        return jsonify({"error": "File not found"}), 404
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({"filename": filename, "content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Daily Fetch (full briefing pipeline + commit + jira)
# ---------------------------------------------------------------------------

_daily_fetch_jobs: dict[str, dict] = {}


_log = logging.getLogger(__name__)


def _ollama_narration_call(system_prompt: str, user_prompt: str, max_tokens: int = 8192, timeout: int = 600) -> str:
    """Low-level Ollama call for narration generation using the fast narration model."""
    import requests as _requests

    resp = _requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json={
            "model": OLLAMA_MODEL_NARRATION,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "think": False,
            "options": {"temperature": 0.7, "num_predict": max_tokens},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    narration = resp.json().get("message", {}).get("content", "").strip()
    narration = re.sub(r"</?think>", "", narration).strip()
    narration = re.sub(r"```[a-z]*\n?", "", narration).strip()
    narration = narration.strip("`").strip()
    for prefix in ["Narration:", "Script:", "Podcast Script:", "旁白:", "播客脚本:"]:
        if narration.lower().startswith(prefix.lower()):
            narration = narration[len(prefix):].strip()
    return narration


def _generate_briefing_narration(content: str, content_type: str = "ai") -> str:
    """Use Ollama to generate a Chinese podcast narration from briefing content.

    Legacy single-call path — kept for backward compatibility when called directly.
    Daily Fetch audio now uses _generate_segmented_narrations instead.
    """
    if content_type == "world":
        system_prompt = (
            "你是一位专业的国际新闻播报员，用流畅自然的中文播报世界新闻。"
            "语气正式但不生硬，像真正的新闻播客。不要用markdown格式，只输出纯文本旁白。"
        )
        user_prompt = (
            "用中文写一段世界新闻播客旁白（约5-8分钟口播内容，约4000-6000字）。"
            "涵盖以下所有新闻要点，提供背景分析和影响解读。技术术语和人名保留英文。"
            "只输出旁白文本。\n\n"
            f"{content}"
        )
    else:
        system_prompt = (
            "你是一位AI科技播客主播，用生动有趣的中文讲解AI和科技新闻。"
            "风格轻松专业，像和朋友聊天一样。不要用markdown格式，只输出纯文本旁白。"
        )
        user_prompt = (
            "用中文写一段AI科技播客旁白（约8-12分钟口播内容，约6000-10000字）。"
            "深入讲解以下所有内容，解释概念、分析趋势、讨论影响。技术术语保留英文。"
            "只输出旁白文本。\n\n"
            f"{content}"
        )
    return _ollama_narration_call(system_prompt, user_prompt, max_tokens=32768, timeout=1800)


def _generate_segmented_narrations(
    segments: list[dict],
    content_type: str = "ai",
    lang: str = "zh",
) -> list[str]:
    """Generate narrations per source/category segment using the fast model.

    *segments* is a list of dicts:
        {"name": "<source or category name>", "content": "<items text>"}
    *lang* is "zh" for Chinese narration or "en" for English.

    Returns a list of narration strings (one per segment, in order).
    The first segment gets an intro, the last gets an outro.
    """
    total = len(segments)
    narrations: list[str] = []
    use_en = lang == "en"

    for idx, seg in enumerate(segments):
        is_first = idx == 0
        is_last = idx == total - 1
        seg_name = seg["name"]
        seg_content = seg["content"]
        min_chars = max(400, len(seg_content) // 3)
        max_chars = max(800, len(seg_content) // 2)

        if content_type == "world":
            if use_en:
                system_prompt = (
                    "You are a professional international news anchor. "
                    "Write in fluent, natural English for a podcast. No markdown, plain text only."
                )
                intro_line = "Start with a brief opening line for this world news podcast segment. " if is_first else ""
                outro_line = "End with a brief sign-off thanking listeners. " if is_last else ""
                user_prompt = (
                    f"Write an English podcast narration about the '{seg_name}' section "
                    f"(approximately {min_chars}-{max_chars} words). "
                    f"{intro_line}Provide background analysis and impact interpretation. "
                    f"{outro_line}Output narration text only.\n\n{seg_content}"
                )
            else:
                system_prompt = (
                    "你是一位专业的国际新闻播报员，用流畅自然的中文播报世界新闻。"
                    "语气正式但不生硬，像真正的新闻播客。不要用markdown格式，只输出纯文本旁白。"
                    "重要规则：全部用中文写作，不要翻译或复述原文英文内容，不要附加英文段落。"
                    "只有人名和专有名词保留英文。"
                )
                intro_line = "以一句简短的开场白开始这期世界新闻播客，然后进入以下板块内容。" if is_first else ""
                outro_line = "在板块结束后加上简短的结束语，感谢收听。" if is_last else ""
                user_prompt = (
                    f"用中文写一段关于「{seg_name}」板块的世界新闻播客旁白"
                    f"（约{min_chars}-{max_chars}字）。"
                    f"{intro_line}"
                    "提供背景分析和影响解读。只有人名和专有名词保留英文，其余全部用中文表达。"
                    f"{outro_line}"
                    "只输出中文旁白文本。\n\n"
                    f"以下是素材（请用中文重新组织讲解，不要直接翻译或附加原文）：\n\n"
                    f"{seg_content}"
                )
        else:
            if use_en:
                system_prompt = (
                    "You are an AI technology podcast host. Write in engaging, conversational English. "
                    "Professional but friendly, like chatting with a friend. No markdown, plain text only."
                )
                intro_line = "Start with a brief opening for this AI tech podcast segment. " if is_first else ""
                outro_line = "End with a brief sign-off. " if is_last else ""
                user_prompt = (
                    f"Write an English podcast narration about the '{seg_name}' section "
                    f"(approximately {min_chars}-{max_chars} words). "
                    f"{intro_line}Explain concepts, analyze trends, discuss impact. "
                    f"{outro_line}Output narration text only.\n\n{seg_content}"
                )
            else:
                system_prompt = (
                    "你是一位AI科技播客主播，用生动有趣的中文讲解AI和科技新闻。"
                    "风格轻松专业，像和朋友聊天一样。不要用markdown格式，只输出纯文本旁白。"
                    "重要规则：全部用中文写作，不要翻译或复述原文英文内容，不要附加英文段落。"
                    "只有专有名词（如公司名、模型名、技术名词）保留英文。"
                )
                intro_line = "以一句简短的开场白开始这期AI科技播客，然后进入以下板块内容。" if is_first else ""
                outro_line = "在板块结束后加上简短的结束语，感谢收听。" if is_last else ""
                user_prompt = (
                    f"用中文写一段关于「{seg_name}」板块的AI科技播客旁白"
                    f"（约{min_chars}-{max_chars}字）。"
                    f"{intro_line}"
                    "深入讲解内容，解释概念、分析趋势、讨论影响。"
                    "只有专有名词保留英文，其余全部用中文表达，不要重复或附加英文原文。"
                    f"{outro_line}"
                    "只输出中文旁白文本。\n\n"
                    f"以下是英文素材（请用中文重新组织讲解，不要直接翻译或附加原文）：\n\n"
                    f"{seg_content}"
                )

        _log.info("Generating narration segment %d/%d: %s (%d chars input)",
                   idx + 1, total, seg_name, len(seg_content))
        try:
            narration = _ollama_narration_call(system_prompt, user_prompt, max_tokens=8192, timeout=600)
            if narration and len(narration) > 50:
                narrations.append(narration)
                _log.info("Segment %d/%d done: %d chars narration", idx + 1, total, len(narration))
            else:
                _log.warning("Segment %d/%d returned too short narration (%d chars), skipping",
                             idx + 1, total, len(narration) if narration else 0)
        except Exception as e:
            _log.warning("Segment %d/%d failed: %s", idx + 1, total, str(e)[:200])

    return narrations


def _tts_segments_to_mp3(narrations: list[str], out_path: str, voice: str = "zh-CN-YunxiNeural"):
    """Convert a list of narration segments to a single combined MP3."""
    import asyncio
    import edge_tts
    import shutil
    import tempfile

    out_dir = os.path.dirname(out_path)
    voices_to_try = [voice] + [v for v in _TTS_VOICE_FALLBACKS if v != voice]
    all_part_paths: list[str] = []

    async def _save_chunk(chunk_text, chunk_path):
        for v in voices_to_try:
            for attempt in range(2):
                try:
                    comm = edge_tts.Communicate(chunk_text, v, rate="-5%", pitch="+0Hz")
                    await comm.save(chunk_path)
                    return v
                except Exception:
                    if attempt < 1:
                        await asyncio.sleep(2)
            _log.warning("Voice %s failed for chunk, trying next fallback", v)
        raise RuntimeError(f"All TTS voices failed for chunk ({len(chunk_text)} chars)")

    async def _do_tts():
        chunk_size = 2000
        for seg_idx, narration in enumerate(narrations):
            narration = _clean_narration_for_tts(narration)
            chunks: list[str] = []
            text = narration
            while text:
                if len(text) <= chunk_size:
                    chunks.append(text)
                    break
                split_at = text.rfind("。", 0, chunk_size)
                if split_at < 0:
                    split_at = text.rfind(".", 0, chunk_size)
                if split_at < 0:
                    split_at = chunk_size
                else:
                    split_at += 1
                chunks.append(text[:split_at])
                text = text[split_at:].strip()

            for ci, chunk in enumerate(chunks):
                part = os.path.join(out_dir, f"_df_seg{seg_idx}_part{ci}.mp3")
                await _save_chunk(chunk, part)
                all_part_paths.append(part)

        if not all_part_paths:
            return
        if len(all_part_paths) == 1:
            os.replace(all_part_paths[0], out_path)
            return

        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as lf:
                for p in all_part_paths:
                    lf.write(f"file '{os.path.abspath(p).replace(chr(92), '/')}'\n")
                list_path = lf.name
            subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0",
                            "-i", list_path, "-c", "copy", out_path],
                           check=True, capture_output=True)
            os.unlink(list_path)
        else:
            with open(out_path, "wb") as out:
                for p in all_part_paths:
                    with open(p, "rb") as pf:
                        out.write(pf.read())

        for p in all_part_paths:
            try:
                os.remove(p)
            except OSError:
                pass
        _log.info("Segmented TTS done (%d segments, %d chunks merged)", len(narrations), len(all_part_paths))

    asyncio.run(_do_tts())


_TTS_VOICE_FALLBACKS = ["zh-CN-YunxiNeural", "zh-CN-YunjianNeural", "zh-CN-XiaoxiaoNeural"]


def _clean_narration_for_tts(text: str) -> str:
    """Strip markdown formatting and sound-effect annotations that break TTS."""
    text = re.sub(r"\*\*\*([^*]+)\*\*\*", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"---+", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"（音效[^）]*）", "", text)
    text = re.sub(r"（背景音乐[^）]*）", "", text)
    text = re.sub(r"（过渡音效[^）]*）", "", text)
    text = re.sub(r"【[^】]*】", "", text)
    text = re.sub(r"（注[^）]*）", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _tts_to_mp3(narration: str, out_path: str, voice: str = "zh-CN-YunxiNeural"):
    """Convert narration text to MP3 via Edge-TTS with chunking, concatenation, and voice fallback."""
    import asyncio
    import edge_tts
    import shutil
    import tempfile

    narration = _clean_narration_for_tts(narration)

    chunk_size = 2000
    chunks = []
    text = narration
    while text:
        if len(text) <= chunk_size:
            chunks.append(text)
            break
        split_at = text.rfind("。", 0, chunk_size)
        if split_at < 0:
            split_at = text.rfind(".", 0, chunk_size)
        if split_at < 0:
            split_at = chunk_size
        else:
            split_at += 1
        chunks.append(text[:split_at])
        text = text[split_at:].strip()

    out_dir = os.path.dirname(out_path)
    voices_to_try = [voice] + [v for v in _TTS_VOICE_FALLBACKS if v != voice]

    async def _save_chunk(chunk_text, chunk_path):
        for v in voices_to_try:
            for attempt in range(2):
                try:
                    comm = edge_tts.Communicate(chunk_text, v, rate="-5%", pitch="+0Hz")
                    await comm.save(chunk_path)
                    return v
                except Exception:
                    if attempt < 1:
                        await asyncio.sleep(2)
            _log.warning("Voice %s failed for chunk, trying next fallback", v)
        raise RuntimeError(f"All TTS voices failed for chunk ({len(chunk_text)} chars)")

    async def _do_tts():
        if len(chunks) == 1:
            used_voice = await _save_chunk(chunks[0], out_path)
            _log.info("TTS done (1 chunk, voice=%s)", used_voice)
            return
        part_paths = []
        for i, chunk in enumerate(chunks):
            part = os.path.join(out_dir, f"_df_tts_part_{i}.mp3")
            used_voice = await _save_chunk(chunk, part)
            part_paths.append(part)
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as lf:
                for p in part_paths:
                    lf.write(f"file '{os.path.abspath(p).replace(chr(92), '/')}'\n")
                list_path = lf.name
            subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0",
                            "-i", list_path, "-c", "copy", out_path],
                           check=True, capture_output=True)
            os.unlink(list_path)
        else:
            with open(out_path, "wb") as out:
                for p in part_paths:
                    with open(p, "rb") as pf:
                        out.write(pf.read())
        for p in part_paths:
            try:
                os.remove(p)
            except OSError:
                pass
        _log.info("TTS done (%d chunks merged, voice=%s)", len(chunks), used_voice)

    asyncio.run(_do_tts())


def _run_daily_fetch(job_id: str, *, only_steps: list | None = None, target_date: str | None = None):
    """Background worker: run full briefing pipeline, then commit report + Jira daily.

    If *only_steps* is provided (non-empty list), only those pipeline steps are
    executed — used by the "Continue" button to finish an incomplete run.
    """
    import subprocess as sp
    job = _daily_fetch_jobs[job_id]
    today = target_date or datetime.now().strftime("%Y-%m-%d")
    output_dir = os.path.join(REPORTS_ROOT, today)
    _should_run = lambda step_name: not only_steps or step_name in only_steps  # noqa: E731
    os.makedirs(output_dir, exist_ok=True)
    scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    steps = []

    try:
        job["status"] = "fetching"
        if _should_run("fetch_sources"):
            job["step"] = "Running AI + world news fetchers..."
            try:
                run_all = os.path.join(scripts_dir, "pipeline", "run-all-sources.py")
                r = sp.run(
                    ["python", run_all, "--output-dir", output_dir, "--proxy", "socks5://localhost:10808"],
                    capture_output=True, text=False, timeout=600, cwd=scripts_dir
                )
                stdout = r.stdout.decode("utf-8", errors="replace") if r.stdout else ""
                steps.append({"step": "fetch_sources", "exit_code": r.returncode, "output": stdout[-500:]})
            except Exception as e:
                steps.append({"step": "fetch_sources", "exit_code": 1, "output": str(e)[:300]})

        if _should_run("topic_dedup"):
            job["step"] = "Running topic deduplication..."
            try:
                filter_script = os.path.join(scripts_dir, "pipeline", "filter_topics.py")
                input_json = os.path.join(output_dir, "briefing-data.json")
                filtered_json = os.path.join(output_dir, "briefing-data-filtered.json")
                if os.path.exists(input_json):
                    r2 = sp.run(
                        ["python", filter_script, input_json, filtered_json, "--mode", "aggressive"],
                        capture_output=True, text=False, timeout=60, cwd=scripts_dir
                    )
                    stdout2 = r2.stdout.decode("utf-8", errors="replace") if r2.stdout else ""
                    steps.append({"step": "topic_dedup", "exit_code": r2.returncode, "output": stdout2[-300:]})
            except Exception as e:
                steps.append({"step": "topic_dedup", "exit_code": 1, "output": str(e)[:200]})

        commit_text = ""
        if _should_run("commit_report"):
            job["step"] = "Running commit report (48h)..."
            try:
                commit_script = os.path.join(scripts_dir, "tools", "commit-report.ps1")
                if os.path.exists(commit_script):
                    rc = sp.run(
                        ["powershell", "-ExecutionPolicy", "Bypass", "-File", commit_script,
                         "-Hours", "48", "-OutputDir", REPORTS_ROOT],
                        capture_output=True, text=False, timeout=300, cwd=scripts_dir
                    )
                    raw_out = rc.stdout.decode("utf-8", errors="replace") if rc.stdout else ""
                    if "---DATA_START---" in raw_out:
                        commit_text = raw_out.split("---DATA_START---")[1].split("---DATA_END---")[0].strip()
                    else:
                        commit_text = raw_out[-2000:]
                    steps.append({"step": "commit_report", "exit_code": rc.returncode,
                                  "output": raw_out[:raw_out.find("---DATA_START---")][-500:] if "---DATA_START---" in raw_out else raw_out[-500:]})
                else:
                    commit_text = tool_commit_summary(hours=48)
                    steps.append({"step": "commit_report", "exit_code": 0, "output": commit_text[:500]})
            except Exception as e:
                steps.append({"step": "commit_report", "exit_code": 1, "output": str(e)[:200]})

        jira_text = ""
        if _should_run("jira_daily"):
            job["step"] = "Running Jira daily report..."
            try:
                if os.path.exists(JIRA_SCRIPT):
                    r3 = sp.run(
                        ["powershell", "-ExecutionPolicy", "Bypass", "-File", JIRA_SCRIPT,
                         "-ReportDir", output_dir],
                        capture_output=True, text=False, timeout=120
                    )
                    jira_text = r3.stdout.decode("utf-8", errors="replace") if r3.stdout else ""
                    steps.append({"step": "jira_daily", "exit_code": r3.returncode, "output": jira_text[:500]})
                else:
                    steps.append({"step": "jira_daily", "exit_code": -1, "output": f"Script not found: {JIRA_SCRIPT}"})
                if not jira_text.strip():
                    jira_report = os.path.join(output_dir, f"atlassian-daily-report-{today.replace('-', '')}.md")
                    if os.path.exists(jira_report):
                        with open(jira_report, "r", encoding="utf-8") as jf:
                            jira_text = jf.read()
            except Exception as e:
                steps.append({"step": "jira_daily", "exit_code": 1, "output": str(e)[:200]})

        wiki_text = ""
        if _should_run("wiki_fetch"):
            job["step"] = "Running Wiki Fetch for all team members..."
            _WIKI_USERS = [
                "Rong Yin", "Raymond Shen", "Charlotte Jiang",
                "Christoph Scheben", "Tobias Troesch",
                "Belen Liu", "Eason Li", "Johnny Yang",
            ]
            try:
                script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index_confluence_user.py")
                wiki_results = []
                all_user_pages_detail = {}
                total_wiki_pages = 0
                total_wiki_chunks = 0
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                for idx, user in enumerate(_WIKI_USERS):
                    job["step"] = f"Wiki Fetch ({idx + 1}/{len(_WIKI_USERS)}: {user})..."
                    try:
                        cmd = [sys.executable, script, user, "--date-from", yesterday, "--report-json"]
                        proc = sp.run(cmd, capture_output=True, text=True, timeout=120,
                                      cwd=os.path.dirname(os.path.abspath(__file__)))
                        out = proc.stdout.strip()
                        user_pages = 0
                        user_chunks = 0
                        m_done = re.search(r"Indexed (\d+) chunks from (\d+) wiki pages", out)
                        if m_done:
                            user_chunks = int(m_done.group(1))
                            user_pages = int(m_done.group(2))
                        else:
                            m_found = re.search(r"Found (\d+) pages", out)
                            if m_found:
                                user_pages = int(m_found.group(1))
                        page_details = []
                        m_json = re.search(r"REPORT_JSON:(.+)", out)
                        if m_json:
                            try:
                                import json as _wj
                                page_details = _wj.loads(m_json.group(1))
                            except Exception:
                                pass
                        total_wiki_pages += user_pages
                        total_wiki_chunks += user_chunks
                        wiki_results.append(f"[{user}] {user_pages} pages, {user_chunks} chunks")
                        if page_details:
                            all_user_pages_detail[user] = page_details
                    except Exception as e:
                        wiki_results.append(f"[{user}] error: {str(e)[:80]}")
                wiki_text = "\n".join(wiki_results)
                # --- Generate AI change summaries for wiki pages ---
                def _wiki_ai_summary(page_detail: dict) -> str:
                    """Use Ollama to summarize what changed on a wiki page."""
                    title = page_detail.get("title", "")
                    raw_summary = page_detail.get("summary", "").strip()
                    headings = page_detail.get("headings", [])
                    if not raw_summary:
                        return ""
                    context_parts = [f"Page title: {title}"]
                    if headings:
                        context_parts.append(f"Sections: {', '.join(headings[:8])}")
                    context_parts.append(f"Content excerpt:\n{raw_summary}")
                    context = "\n".join(context_parts)
                    try:
                        import requests as _req
                        resp = _req.post(
                            f"{OLLAMA_HOST}/api/chat",
                            json={
                                "model": OLLAMA_MODEL_FAST,
                                "messages": [
                                    {"role": "system", "content": (
                                        "You are a concise technical writer. Given a Confluence wiki page's content, "
                                        "write a 1-2 sentence summary of what this page covers or what was likely updated. "
                                        "Focus on the key changes or topics. Be specific and factual. "
                                        "Output only the summary, no labels or prefixes."
                                    )},
                                    {"role": "user", "content": context},
                                ],
                                "stream": False,
                                "think": False,
                                "options": {"temperature": 0.3, "num_predict": 200},
                            },
                            timeout=30,
                        )
                        resp.raise_for_status()
                        result = resp.json().get("message", {}).get("content", "").strip()
                        result = re.sub(r"</?think>", "", result).strip()
                        return result
                    except Exception:
                        return ""

                if all_user_pages_detail:
                    job["step"] = "Generating AI summaries for wiki pages..."
                    for user, details in all_user_pages_detail.items():
                        for pg in details:
                            ai_sum = _wiki_ai_summary(pg)
                            if ai_sum:
                                pg["ai_summary"] = ai_sum

                wiki_report_path = os.path.join(output_dir, f"wiki-fetch-{today}.md")
                with open(wiki_report_path, "w", encoding="utf-8") as wf:
                    wf.write(f"# Wiki Fetch Report — {today}\n\n")
                    wf.write(f"Fetched pages updated since {yesterday} for {len(_WIKI_USERS)} team members.\n\n")
                    wf.write(f"**Total: {total_wiki_pages} pages, {total_wiki_chunks} chunks indexed**\n\n")
                    for line in wiki_results:
                        wf.write(f"- {line}\n")
                    if all_user_pages_detail:
                        wf.write("\n---\n\n## Page Details\n\n")
                        for user, details in all_user_pages_detail.items():
                            wf.write(f"### {user}\n\n")
                            for pg in details:
                                title = pg.get("title", "Untitled")
                                url = pg.get("url", "")
                                space = pg.get("space", "")
                                modified = pg.get("modified_at", "")
                                headings = pg.get("headings", [])
                                ai_summary = pg.get("ai_summary", "")
                                if url:
                                    wf.write(f"- **[{title}]({url})**")
                                else:
                                    wf.write(f"- **{title}**")
                                if space:
                                    wf.write(f" — *{space}*")
                                if modified:
                                    wf.write(f" (modified: {modified})")
                                wf.write("\n")
                                if ai_summary:
                                    wf.write(f"  > **Summary:** {ai_summary}\n")
                                elif pg.get("summary", "").strip():
                                    brief = pg["summary"].strip()[:200] + ("..." if len(pg["summary"].strip()) > 200 else "")
                                    wf.write(f"  > {brief}\n")
                                if headings:
                                    wf.write(f"  > Sections: {', '.join(headings[:5])}\n")
                                if url:
                                    wf.write(f"  > [Open in Confluence]({url})\n")
                                wf.write("\n")
                steps.append({"step": "wiki_fetch", "exit_code": 0,
                              "output": f"{total_wiki_pages} wiki pages ({total_wiki_chunks} chunks) from {len(_WIKI_USERS)} users"})
            except Exception as e:
                steps.append({"step": "wiki_fetch", "exit_code": 1, "output": str(e)[:300]})

        job["step"] = "Building daily summary..."
        ai_key_points = ""
        world_key_points = ""
        try:
            data_file = os.path.join(output_dir, "briefing-data-filtered.json")
            if not os.path.exists(data_file):
                data_file = os.path.join(output_dir, "briefing-data.json")
            if os.path.exists(data_file):
                import json as _json
                with open(data_file, "r", encoding="utf-8") as df:
                    bdata = _json.load(df)
                psd = bdata.get("per_source_data", [])
                items_list = []
                if isinstance(psd, list):
                    for src_block in psd:
                        src_name = src_block.get("source_name", "")
                        for it in src_block.get("items", [])[:3]:
                            items_list.append(f"- [{src_name}] {it.get('title', 'Untitled')}")
                ai_key_points = "\n".join(items_list[:15]) if items_list else "No AI news items"

            wn_file = os.path.join(output_dir, "world-news", "world-news-data.json")
            if os.path.exists(wn_file):
                import json as _json
                with open(wn_file, "r", encoding="utf-8") as wf:
                    wdata = _json.load(wf)
                wn_items = []
                cats = wdata.get("categories") or []
                if isinstance(cats, list):
                    for cat_block in cats:
                        cat_name = cat_block.get("label") or cat_block.get("category", "")
                        for it in (cat_block.get("items") or [])[:2]:
                            title = it.get("title", "")
                            if title:
                                wn_items.append(f"- [{cat_name}] {title}")
                elif isinstance(cats, dict):
                    for cat_name, cat_items in cats.items():
                        for it in (cat_items if isinstance(cat_items, list) else [])[:2]:
                            title = it.get("title", "")
                            if title:
                                wn_items.append(f"- [{cat_name}] {title}")
                world_key_points = "\n".join(wn_items[:12]) if wn_items else "No world news items"
        except Exception:
            pass

        summary_parts = []
        summary_parts.append(f"=== Daily Fetch Summary ({today}) ===\n")

        summary_parts.append("## AI News Key Points")
        summary_parts.append(ai_key_points or "No data")
        summary_parts.append("")

        summary_parts.append("## World News Key Points")
        summary_parts.append(world_key_points or "No data")
        summary_parts.append("")

        summary_parts.append("## Git Commits (Last 48h)")
        summary_parts.append(commit_text[:4000] if commit_text else "No commits found")
        summary_parts.append("")

        summary_parts.append("## Jira Daily Report")
        summary_parts.append(jira_text[:4000] if jira_text else "No Jira report available")

        job["daily_summary"] = "\n".join(summary_parts)

        # --- Audio generation: AI Briefing (segmented per-source) ---
        if _should_run("ai_audio"):
            job["step"] = "Generating AI briefing audio (segmented)..."
            try:
                data_file = os.path.join(output_dir, "briefing-data-filtered.json")
                if not os.path.exists(data_file):
                    data_file = os.path.join(output_dir, "briefing-data.json")
                if os.path.exists(data_file):
                    import json as _json
                    with open(data_file, "r", encoding="utf-8") as df:
                        bdata = _json.load(df)
                    ai_segments: list[dict] = []
                    for src_block in (bdata.get("per_source_data") or []):
                        src_name = src_block.get("source_name", "")
                        items_text_parts = []
                        for it in src_block.get("items", [])[:5]:
                            title = it.get("title", "")
                            summary_text = it.get("summary", "") or it.get("description", "")
                            if title:
                                items_text_parts.append(f"{title}\n{summary_text}")
                        if items_text_parts:
                            ai_segments.append({
                                "name": src_name or "AI News",
                                "content": "\n\n".join(items_text_parts),
                            })
                    if ai_segments:
                        ai_lang = _GLOBAL_SETTINGS.get("audio_lang_ai", "zh")
                        ai_voice = "en-US-AndrewNeural" if ai_lang == "en" else "zh-CN-YunxiNeural"
                        job["step"] = f"Generating AI narration ({len(ai_segments)} segments, lang={ai_lang})..."
                        narrations_ai = _generate_segmented_narrations(ai_segments, "ai", lang=ai_lang)
                        if narrations_ai:
                            total_chars = sum(len(n) for n in narrations_ai)
                            ai_mp3 = os.path.join(output_dir, "ai-briefing.mp3")
                            _tts_segments_to_mp3(narrations_ai, ai_mp3, voice=ai_voice)
                            steps.append({"step": "ai_audio", "exit_code": 0,
                                          "output": f"Generated ai-briefing.mp3 ({len(narrations_ai)} segments, {total_chars} chars total)"})
                        else:
                            steps.append({"step": "ai_audio", "exit_code": 1, "output": "All narration segments failed"})
                    else:
                        steps.append({"step": "ai_audio", "exit_code": -1, "output": "Insufficient briefing content"})
                else:
                    steps.append({"step": "ai_audio", "exit_code": -1, "output": "No briefing data file found"})
            except Exception as e:
                steps.append({"step": "ai_audio", "exit_code": 1, "output": str(e)[:300]})

        # --- Ensure world-news-data.json exists (merge recovery) ---
        if _should_run("world_news_merge"):
            wn_dir = os.path.join(output_dir, "world-news")
            wn_merged_path = os.path.join(wn_dir, "world-news-data.json")
            if os.path.isdir(wn_dir) and not os.path.isfile(wn_merged_path):
                source_jsons = [f for f in os.listdir(wn_dir)
                                if f.endswith(".json") and f != "world-news-timing.json"]
                if source_jsons:
                    job["step"] = "Merging world news sources..."
                    try:
                        merge_script = os.path.join(
                            os.path.dirname(os.path.abspath(__file__)), "..", "pipeline", "run-world-news.py")
                        wn_merge_cmd = [sys.executable, merge_script,
                                        "--output-dir", wn_dir, "--no-fetch", "--no-translate"]
                        has_no_fetch = False
                        try:
                            help_proc = sp.run([sys.executable, merge_script, "--help"],
                                               capture_output=True, text=True, timeout=10)
                            has_no_fetch = "--no-fetch" in (help_proc.stdout or "")
                        except Exception:
                            pass

                        if has_no_fetch:
                            proc = sp.run(wn_merge_cmd, capture_output=True, text=True, timeout=120,
                                          cwd=os.path.dirname(merge_script))
                            steps.append({"step": "world_news_merge", "exit_code": proc.returncode,
                                          "output": (proc.stdout or "")[-200:]})
                        else:
                            sys.path.insert(0, os.path.dirname(merge_script))
                            from importlib import import_module
                            try:
                                wn_mod = import_module("run-world-news".replace("-", "_"))
                            except ModuleNotFoundError:
                                import importlib.util
                                spec = importlib.util.spec_from_file_location("run_world_news", merge_script)
                                wn_mod = importlib.util.module_from_spec(spec)
                                spec.loader.exec_module(wn_mod)
                            merged = wn_mod.merge_news(wn_dir)
                            import json as _jm
                            with open(wn_merged_path, "w", encoding="utf-8") as mf:
                                _jm.dump(merged, mf, ensure_ascii=False, indent=2)
                            steps.append({"step": "world_news_merge", "exit_code": 0,
                                          "output": f"Merged {merged.get('total_items', 0)} items from {len(source_jsons)} sources"})
                    except Exception as e:
                        steps.append({"step": "world_news_merge", "exit_code": 1, "output": str(e)[:300]})
            else:
                steps.append({"step": "world_news_merge", "exit_code": 0, "output": "Already merged"})

        # --- Audio generation: World News + China News (split by source) ---
        _CHINA_SOURCE_TAG = "中国新闻"

        def _pick_wn_text(it, prefer_zh):
            if prefer_zh:
                title = it.get("title_zh") or it.get("title", "")
                summary_text = it.get("summary_zh") or it.get("summary", "") or it.get("description", "")
            else:
                title = it.get("title", "")
                summary_text = it.get("summary", "") or it.get("description", "")
            return title, summary_text

        def _build_audio_segments(categories, source_filter, prefer_zh, max_per_cat=4):
            """Build narration segments from categories, filtering by source."""
            segs = []
            if not isinstance(categories, list):
                return segs
            for cat_block in categories:
                cat_name = cat_block.get("label") or cat_block.get("category", "")
                parts = []
                for it in (cat_block.get("items") or []):
                    src = it.get("source", "")
                    if not source_filter(src):
                        continue
                    title, summary_text = _pick_wn_text(it, prefer_zh)
                    if title:
                        parts.append(f"{title}\n{summary_text}")
                    if len(parts) >= max_per_cat:
                        break
                if parts:
                    segs.append({"name": cat_name or "News", "content": "\n\n".join(parts)})
            return segs

        if _should_run("world_audio"):
            job["step"] = "Generating world news audio..."
            try:
                wn_file = os.path.join(output_dir, "world-news", "world-news-data.json")
                if os.path.exists(wn_file):
                    import json as _json
                    with open(wn_file, "r", encoding="utf-8") as wf:
                        wdata = _json.load(wf)
                    categories = wdata.get("categories") or []

                    wn_lang = _GLOBAL_SETTINGS.get("audio_lang_world", "zh")
                    wn_voice = "en-US-AndrewNeural" if wn_lang == "en" else "zh-CN-YunxiNeural"
                    wn_segments = _build_audio_segments(
                        categories,
                        source_filter=lambda s: _CHINA_SOURCE_TAG not in s,
                        prefer_zh=(wn_lang == "zh"),
                    )
                    if wn_segments:
                        job["step"] = f"Generating world narration ({len(wn_segments)} segments, lang={wn_lang})..."
                        narrations_wn = _generate_segmented_narrations(wn_segments, "world", lang=wn_lang)
                        if narrations_wn:
                            total_chars = sum(len(n) for n in narrations_wn)
                            wn_mp3 = os.path.join(output_dir, "world-news.mp3")
                            _tts_segments_to_mp3(narrations_wn, wn_mp3, voice=wn_voice)
                            steps.append({"step": "world_audio", "exit_code": 0,
                                          "output": f"Generated world-news.mp3 ({len(narrations_wn)} segments, {total_chars} chars)"})
                        else:
                            steps.append({"step": "world_audio", "exit_code": 1, "output": "World narration failed"})
                    else:
                        steps.append({"step": "world_audio", "exit_code": -1, "output": "No international news content"})
                else:
                    steps.append({"step": "world_audio", "exit_code": -1, "output": "No world news data file found"})
            except Exception as e:
                steps.append({"step": "world_audio", "exit_code": 1, "output": str(e)[:300]})

        if _should_run("china_audio"):
            job["step"] = "Generating Chinese news audio..."
            try:
                wn_file = os.path.join(output_dir, "world-news", "world-news-data.json")
                if os.path.exists(wn_file):
                    import json as _json
                    with open(wn_file, "r", encoding="utf-8") as wf:
                        wdata = _json.load(wf)
                    categories = wdata.get("categories") or []

                    cn_lang = _GLOBAL_SETTINGS.get("audio_lang_china", "zh")
                    cn_voice = "en-US-AndrewNeural" if cn_lang == "en" else "zh-CN-YunxiNeural"
                    cn_segments = _build_audio_segments(
                        categories,
                        source_filter=lambda s: _CHINA_SOURCE_TAG in s,
                        prefer_zh=(cn_lang == "zh"),
                        max_per_cat=15,
                    )
                    if cn_segments:
                        job["step"] = f"Generating China narration ({len(cn_segments)} segments, lang={cn_lang})..."
                        narrations_cn = _generate_segmented_narrations(cn_segments, "world", lang=cn_lang)
                        if narrations_cn:
                            total_chars = sum(len(n) for n in narrations_cn)
                            cn_mp3 = os.path.join(output_dir, "china-news.mp3")
                            _tts_segments_to_mp3(narrations_cn, cn_mp3, voice=cn_voice)
                            steps.append({"step": "china_audio", "exit_code": 0,
                                          "output": f"Generated china-news.mp3 ({len(narrations_cn)} segments, {total_chars} chars)"})
                        else:
                            steps.append({"step": "china_audio", "exit_code": 1, "output": "China narration failed"})
                    else:
                        steps.append({"step": "china_audio", "exit_code": -1, "output": "No Chinese news content"})
                else:
                    steps.append({"step": "china_audio", "exit_code": -1, "output": "No world news data file found"})
            except Exception as e:
                steps.append({"step": "china_audio", "exit_code": 1, "output": str(e)[:300]})

        job["status"] = "done"
        job["step"] = "Complete"
        job["steps"] = steps

        files = []
        for f_name in os.listdir(output_dir):
            fpath = os.path.join(output_dir, f_name)
            if os.path.isfile(fpath):
                files.append({"name": f_name, "size_kb": round(os.path.getsize(fpath) / 1024, 1)})
        job["files"] = sorted(files, key=lambda x: x["name"])

    except Exception as e:
        job["status"] = "error"
        job["step"] = str(e)
        job["steps"] = steps


@app.route("/api/toolbar/daily-fetch", methods=["POST"])
def api_daily_fetch():
    """Start the daily fetch pipeline as a background job."""
    import uuid
    job_id = str(uuid.uuid4())[:8]
    _daily_fetch_jobs[job_id] = {"status": "starting", "step": "Initializing...", "steps": [], "files": []}
    t = threading.Thread(target=_run_daily_fetch, args=(job_id,), daemon=True)
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/api/toolbar/daily-fetch/continue", methods=["POST"])
def api_daily_fetch_continue():
    """Continue a partially-completed daily fetch — runs only the missing steps."""
    import uuid
    data = request.get_json(silent=True) or {}
    only_steps = data.get("steps") or []
    target_date = data.get("date") or datetime.now().strftime("%Y-%m-%d")
    job_id = str(uuid.uuid4())[:8]
    _daily_fetch_jobs[job_id] = {"status": "starting", "step": "Continuing...", "steps": [], "files": []}
    t = threading.Thread(
        target=_run_daily_fetch,
        args=(job_id,),
        kwargs={"only_steps": only_steps, "target_date": target_date},
        daemon=True,
    )
    t.start()
    return jsonify({"job_id": job_id, "running_steps": only_steps})


@app.route("/api/toolbar/daily-fetch/<job_id>", methods=["GET"])
def api_daily_fetch_status(job_id):
    """Poll daily fetch job status."""
    job = _daily_fetch_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/api/toolbar/daily-fetch/history", methods=["GET"])
def api_daily_fetch_history():
    """Return report files and metadata for a given date (default: most recent)."""
    target_date = request.args.get("date", "")
    if not target_date:
        date_dirs = sorted(
            [d for d in os.listdir(REPORTS_ROOT)
             if os.path.isdir(os.path.join(REPORTS_ROOT, d)) and d[:4].isdigit()],
            reverse=True,
        )
        target_date = date_dirs[0] if date_dirs else ""
    if not target_date:
        return jsonify({"date": "", "files": [], "available_dates": []})

    date_dir = os.path.join(REPORTS_ROOT, target_date)
    files = []
    if os.path.isdir(date_dir):
        for f_name in sorted(os.listdir(date_dir)):
            fpath = os.path.join(date_dir, f_name)
            if os.path.isfile(fpath):
                files.append({
                    "name": f_name,
                    "size_kb": round(os.path.getsize(fpath) / 1024, 1),
                })

    ai_count = 0
    wn_count = 0
    jira_tickets = 0
    confluence_pages = 0

    briefing_file = os.path.join(date_dir, "briefing-data-filtered.json")
    if not os.path.isfile(briefing_file):
        briefing_file = os.path.join(date_dir, "briefing-data.json")
    if os.path.isfile(briefing_file):
        try:
            with open(briefing_file, "r", encoding="utf-8") as f:
                bd = json.load(f)
            for src in (bd.get("per_source_data") or []):
                ai_count += len(src.get("items") or [])
        except Exception:
            pass

    cn_count = 0
    _CHINA_TAG = "中国新闻"
    wn_file = os.path.join(date_dir, "world-news", "world-news-data.json")
    if os.path.isfile(wn_file):
        try:
            with open(wn_file, "r", encoding="utf-8") as f:
                wd = json.load(f)
            cats = wd.get("categories") or []
            if isinstance(cats, list):
                for c in cats:
                    for it in (c.get("items") or []):
                        src = it.get("source", "")
                        if _CHINA_TAG in src:
                            cn_count += 1
                        else:
                            wn_count += 1
            elif isinstance(cats, dict):
                for v in cats.values():
                    wn_count += len(v) if isinstance(v, list) else 0
        except Exception:
            pass

    jira_file = os.path.join(date_dir, f"atlassian-daily-report-{target_date.replace('-', '')}.md")
    if os.path.isfile(jira_file):
        try:
            with open(jira_file, "r", encoding="utf-8") as f:
                content = f.read()
            import re as _re
            m = _re.search(r"(\d+) open ticket", content)
            if m:
                jira_tickets = int(m.group(1))
            m2 = _re.search(r"(\d+) pages", content, _re.IGNORECASE)
            if m2:
                confluence_pages = int(m2.group(1))
        except Exception:
            pass

    wiki_pages = 0
    if os.path.isdir(date_dir):
        for fn in os.listdir(date_dir):
            if fn.startswith("wiki-fetch-") and fn.endswith(".md"):
                try:
                    with open(os.path.join(date_dir, fn), "r", encoding="utf-8") as wf:
                        wc = wf.read()
                    import re as _re2
                    m_total = _re2.search(r"\*\*Total:\s*(\d+)\s*pages", wc)
                    if m_total:
                        wiki_pages = int(m_total.group(1))
                    else:
                        wiki_pages = wc.count("pages,")
                except Exception:
                    pass
                break

    has_audio = os.path.isfile(os.path.join(date_dir, "ai-briefing.mp3"))
    has_wn_audio = os.path.isfile(os.path.join(date_dir, "world-news.mp3"))
    has_cn_audio = os.path.isfile(os.path.join(date_dir, "china-news.mp3"))
    has_pdf = os.path.isfile(os.path.join(date_dir, "ai-briefing.pdf"))

    has_sources = os.path.isfile(os.path.join(date_dir, "briefing-data.json"))
    has_filtered = os.path.isfile(os.path.join(date_dir, "briefing-data-filtered.json"))
    has_commit = any(f.startswith("commit-report-") and f.endswith(".md") for f in os.listdir(date_dir)) if os.path.isdir(date_dir) else False
    has_jira = os.path.isfile(jira_file)
    has_wiki = any(f.startswith("wiki-fetch-") and f.endswith(".md") for f in os.listdir(date_dir)) if os.path.isdir(date_dir) else False
    has_wn_data = os.path.isfile(wn_file)

    wn_dir = os.path.join(date_dir, "world-news")
    has_wn_source_jsons = False
    if os.path.isdir(wn_dir) and not has_wn_data:
        has_wn_source_jsons = any(
            f.endswith(".json") and f != "world-news-timing.json" and f != "world-news-data.json"
            for f in os.listdir(wn_dir)
        )

    missing_steps = []
    if not has_sources:
        missing_steps.append("fetch_sources")
    if has_sources and not has_filtered:
        missing_steps.append("topic_dedup")
    if not has_commit:
        missing_steps.append("commit_report")
    if not has_jira:
        missing_steps.append("jira_daily")
    if not has_wiki:
        missing_steps.append("wiki_fetch")
    if has_wn_source_jsons and not has_wn_data:
        missing_steps.append("world_news_merge")
    if (has_sources or has_filtered) and not has_audio:
        missing_steps.append("ai_audio")
    if has_wn_data and not has_wn_audio and wn_count > 0:
        missing_steps.append("world_audio")
    elif not has_wn_data and has_wn_source_jsons and not has_wn_audio:
        missing_steps.append("world_audio")
    if has_wn_data and not has_cn_audio and cn_count > 0:
        missing_steps.append("china_audio")
    elif not has_wn_data and has_wn_source_jsons and not has_cn_audio:
        missing_steps.append("china_audio")

    date_dirs = sorted(
        [d for d in os.listdir(REPORTS_ROOT)
         if os.path.isdir(os.path.join(REPORTS_ROOT, d)) and d[:4].isdigit()],
        reverse=True,
    )[:30]

    return jsonify({
        "date": target_date,
        "files": files,
        "stats": {
            "ai_items": ai_count,
            "world_news_items": wn_count,
            "china_news_items": cn_count,
            "jira_tickets": jira_tickets,
            "confluence_pages": confluence_pages,
            "wiki_pages": wiki_pages,
        },
        "has_audio": has_audio,
        "has_wn_audio": has_wn_audio,
        "has_cn_audio": has_cn_audio,
        "has_pdf": has_pdf,
        "missing_steps": missing_steps,
        "available_dates": date_dirs,
    })


# ---------------------------------------------------------------------------
# Learning Sessions (special persistent sessions)
# ---------------------------------------------------------------------------

_LEARNING_SESSION_IDS = {
    "ai_learning": "00000000-0000-0000-0000-000000000001",
    "english_learning": "00000000-0000-0000-0000-000000000002",
    "casual_english": "00000000-0000-0000-0000-000000000003",
    "aws_cert": "00000000-0000-0000-0000-000000000004",
}


def _get_or_create_learning_session(session_type: str) -> dict:
    """Get or create a special persistent learning session."""
    sid = _LEARNING_SESSION_IDS.get(session_type)
    if not sid:
        return {}
    data = _load_session_file(sid)
    if data:
        return data
    _ensure_chat_sessions_dir()
    now = _now_iso()
    titles = {
        "ai_learning": "AI Learning — RAG, LLM & HuggingFace",
        "english_learning": "English Learning — Tech Communication",
        "casual_english": "Casual English — World News & Daily Life",
        "aws_cert": "AWS AIF-C01 — Certified AI Practitioner",
    }
    data = {
        "id": sid,
        "title": titles.get(session_type, "Learning"),
        "created_at": now,
        "updated_at": now,
        "messages": [],
        "session_type": session_type,
    }
    _save_session_file(data)
    return data


def _load_ai_learning_roadmap() -> str:
    """Load the ch8 roadmap as context for AI learning sessions."""
    roadmap_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "docs", "ch8-learning-roadmap.md"
    )
    try:
        with open(os.path.normpath(roadmap_path), "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _load_aws_cert_roadmap() -> str:
    """Load the AWS AIF-C01 certification roadmap."""
    roadmap_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "docs", "aws-cert-learning-roadmap.md"
    )
    try:
        with open(os.path.normpath(roadmap_path), "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


_AWS_CERT_PROGRESS_PATH = os.path.join(REPORTS_ROOT, ".aws-cert-progress.json")


def _load_aws_cert_progress() -> dict:
    """Load AWS cert study progress from disk."""
    try:
        with open(_AWS_CERT_PROGRESS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {
            "domains": {str(i): {"topics_taught": [], "topics_quizzed": [],
                                  "quiz_scores": [], "completion_pct": 0}
                        for i in range(1, 6)},
            "overall_readiness": 0,
            "last_activity": "",
        }


def _save_aws_cert_progress(progress: dict) -> None:
    """Persist AWS cert study progress to disk."""
    progress["last_activity"] = _now_iso()
    try:
        with open(_AWS_CERT_PROGRESS_PATH, "w", encoding="utf-8") as f:
            json.dump(progress, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print(f"[aws-cert] Failed to save progress: {e}")


def _update_aws_cert_progress(topic: str, mode: str, score: int = 0,
                              total: int = 0) -> dict:
    """Record a teach or quiz event in the progress tracker.
    mode: 'teach' or 'quiz'. Returns updated progress."""
    progress = _load_aws_cert_progress()
    domain_keywords = {
        "1": ["ai ", "ml ", "machine learning", "neural network", "supervised",
              "unsupervised", "reinforcement", "lifecycle", "pipeline",
              "classification", "regression", "clustering", "inferencing",
              "comprehend", "lex", "transcribe", "translate", "rekognition",
              "textract", "personalize", "fraud detector", "forecast", "kendra",
              "evaluation metric", "mlops", "data drift"],
        "2": ["generative ai", "genai", "transformer", "token", "embedding",
              "foundation model", "hallucination", "diffusion", "bedrock",
              "sagemaker", "amazon q", "nova", "partyrock", "chunking",
              "multimodal"],
        "3": ["prompt engineering", "few-shot", "zero-shot", "chain-of-thought",
              "rag", "fine-tuning", "fine-tune", "pre-training", "rlhf",
              "knowledge base", "rouge", "bleu", "bertscore", "inference param",
              "temperature", "top-p", "top-k", "model evaluation",
              "provisioned throughput", "prompt caching"],
        "4": ["responsible ai", "fairness", "explainability", "bias",
              "transparency", "safety", "fepst", "clarify", "a2i",
              "guardrail", "toxicity", "human-in-the-loop", "model card"],
        "5": ["security", "iam", "kms", "encryption", "macie", "privatelink",
              "compliance", "governance", "data lineage", "data quality",
              "gdpr", "hipaa", "artifact", "audit manager", "config",
              "trusted advisor", "shared responsibility", "glue",
              "lake formation", "cost explorer", "budgets"],
    }
    topic_lower = topic.lower()
    import re as _re_prog
    _dm = _re_prog.search(r"domain\s*(\d)", topic_lower)
    if _dm and _dm.group(1) in domain_keywords:
        matched_domain = _dm.group(1)
    else:
        matched_domain = "1"
        for d_num, keywords in domain_keywords.items():
            if any(kw in topic_lower for kw in keywords):
                matched_domain = d_num
                break
    d = progress["domains"].setdefault(matched_domain, {
        "topics_taught": [], "topics_quizzed": [],
        "quiz_scores": [], "completion_pct": 0,
    })
    if mode == "teach":
        if topic not in d["topics_taught"]:
            d["topics_taught"].append(topic)
    elif mode == "quiz":
        if topic not in d["topics_quizzed"]:
            d["topics_quizzed"].append(topic)
        if total > 0:
            d["quiz_scores"].append({
                "topic": topic, "score": score, "total": total,
                "date": _now_iso(),
            })
    domain_weights = {"1": 20, "2": 24, "3": 28, "4": 14, "5": 14}
    total_readiness = 0
    for d_num in ["1", "2", "3", "4", "5"]:
        dd = progress["domains"].get(d_num, {})
        taught = len(dd.get("topics_taught", []))
        quizzed = len(dd.get("topics_quizzed", []))
        pct = min(100, (taught * 8 + quizzed * 12))
        dd["completion_pct"] = pct
        total_readiness += pct * domain_weights.get(d_num, 20) / 100
    progress["overall_readiness"] = round(total_readiness)
    _save_aws_cert_progress(progress)
    return progress


def _format_aws_cert_progress(progress: dict) -> str:
    """Format progress as a readable summary for the LLM or welcome message."""
    domain_names = {
        "1": "Fundamentals of AI and ML",
        "2": "Fundamentals of Generative AI",
        "3": "Applications of Foundation Models",
        "4": "Guidelines for Responsible AI",
        "5": "Security, Compliance & Governance",
    }
    domain_weights = {"1": "20%", "2": "24%", "3": "28%", "4": "14%", "5": "14%"}
    lines = ["## Study Progress\n"]
    for d_num in ["1", "2", "3", "4", "5"]:
        dd = progress["domains"].get(d_num, {})
        pct = dd.get("completion_pct", 0)
        taught = len(dd.get("topics_taught", []))
        quizzed = len(dd.get("topics_quizzed", []))
        scores = dd.get("quiz_scores", [])
        avg = ""
        if scores:
            avg_score = sum(s["score"] for s in scores) / len(scores)
            avg_total = sum(s["total"] for s in scores) / len(scores)
            avg = f" | Avg quiz: {avg_score:.1f}/{avg_total:.0f}"
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        lines.append(
            f"**Domain {d_num}** ({domain_weights[d_num]}) — {domain_names[d_num]}\n"
            f"  {bar} {pct}% | {taught} taught, {quizzed} quizzed{avg}\n"
        )
    readiness = progress.get("overall_readiness", 0)
    lines.append(f"\n**Overall Exam Readiness: {readiness}%**")
    if readiness < 30:
        lines.append("📌 *Keep going! Focus on Domains 2 & 3 (52% of exam).*")
    elif readiness < 60:
        lines.append("📌 *Good progress! Review weak domains and take more quizzes.*")
    elif readiness < 80:
        lines.append("📌 *Almost there! Do full practice exams to find remaining gaps.*")
    else:
        lines.append("🎯 *Looking strong! Consider scheduling the exam.*")
    return "\n".join(lines)


def _load_recent_ai_news_titles() -> list[str]:
    """Load recent AI news titles for English learning topic selection."""
    titles = []
    try:
        kb = _load_ai_kb()
        for item in kb.get("items", [])[:50]:
            t = item.get("title", "").strip()
            if t:
                titles.append(t)
    except Exception:
        pass
    if not titles:
        for d_offset in range(7):
            dt = (datetime.now() - timedelta(days=d_offset)).strftime("%Y-%m-%d")
            json_path = os.path.join(REPORTS_ROOT, dt, "briefing-data-filtered.json")
            if not os.path.isfile(json_path):
                json_path = os.path.join(REPORTS_ROOT, dt, "briefing-data.json")
            if os.path.isfile(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for section in data.get("sections", []):
                        for item in section.get("items", []):
                            t = item.get("title", "").strip()
                            if t and len(titles) < 50:
                                titles.append(t)
                except Exception:
                    pass
    return titles


def _load_recent_world_news_titles() -> list[dict]:
    """Load recent world news titles for casual English learning."""
    items = []
    for d_offset in range(7):
        dt = (datetime.now() - timedelta(days=d_offset)).strftime("%Y-%m-%d")
        wn_path = os.path.join(REPORTS_ROOT, dt, "world-news", "world-news-data.json")
        if not os.path.isfile(wn_path):
            wn_path = os.path.join(REPORTS_ROOT, dt, "world-news-data.json")
        if os.path.isfile(wn_path):
            try:
                with open(wn_path, "r", encoding="utf-8") as f:
                    wdata = json.load(f)
                for cat in wdata.get("categories", []):
                    cat_name = cat.get("label", cat.get("category", "General"))
                    for article in cat.get("items", cat.get("articles", [])):
                        t = article.get("title", "").strip()
                        if t and len(items) < 50:
                            items.append({"title": t, "category": cat_name,
                                          "summary": article.get("summary", "")[:200]})
            except Exception as exc:
                logging.warning("Failed to load world news from %s: %s", wn_path, exc)
    return items


@app.route("/api/toolbar/learning-session", methods=["POST"])
def api_learning_session():
    """Get or create a special learning session."""
    body = request.get_json(silent=True) or {}
    session_type = body.get("type", "ai_learning")
    if session_type not in _LEARNING_SESSION_IDS:
        return jsonify({"error": "Invalid learning type"}), 400
    data = _get_or_create_learning_session(session_type)
    return jsonify(data)


@app.route("/api/toolbar/learning-context", methods=["GET"])
def api_learning_context():
    """Get learning context: roadmap topics for AI, news titles for English."""
    ltype = request.args.get("type", "ai_learning")
    if ltype == "ai_learning":
        roadmap = _load_ai_learning_roadmap()
        topics = []
        current_track = ""
        current_level = ""
        for line in roadmap.split("\n"):
            if line.startswith("## Track"):
                current_track = line.replace("## ", "").strip()
            elif line.startswith("### "):
                current_level = line.replace("### ", "").strip()
            elif line.startswith("- **") and current_track:
                topic_name = line.split("**")[1] if "**" in line else line[4:]
                topics.append({
                    "track": current_track,
                    "level": current_level,
                    "topic": topic_name.strip(":").strip(),
                })
        return jsonify({"type": "ai_learning", "topics": topics})
    elif ltype == "english_learning":
        titles = _load_recent_ai_news_titles()
        return jsonify({"type": "english_learning", "news_titles": titles})
    elif ltype == "casual_english":
        items = _load_recent_world_news_titles()
        return jsonify({"type": "casual_english", "news_items": items})
    elif ltype == "aws_cert":
        roadmap = _load_aws_cert_roadmap()
        domains = []
        current_domain = ""
        current_task = ""
        for line in roadmap.split("\n"):
            if line.startswith("## Domain"):
                current_domain = line.replace("## ", "").strip()
                current_task = ""
            elif line.startswith("### Task"):
                current_task = line.replace("### ", "").strip()
            elif line.startswith("- **") and current_domain:
                topic_name = line.split("**")[1] if "**" in line else line[4:]
                domains.append({
                    "domain": current_domain,
                    "task": current_task,
                    "topic": topic_name.strip(":").strip(),
                })
        progress = _load_aws_cert_progress()
        return jsonify({
            "type": "aws_cert",
            "domains": domains,
            "progress": progress,
        })
    return jsonify({"error": "Unknown type"}), 400


# ---------------------------------------------------------------------------
# Donor Analysis
# ---------------------------------------------------------------------------

def _score_donor(donor: dict, recipient_cmv: str = "negative") -> dict:
    """Score a donor based on clinical criteria. Returns score breakdown."""
    scores = {}
    total = 0.0

    mot_score = 0
    stock = donor.get("stock", [])
    if isinstance(stock, list):
        for s in stock:
            t = s.get("type", "") if isinstance(s, dict) else str(s)
            if "MOT30" in t:
                mot_score = max(mot_score, 3)
            elif "MOT20" in t:
                mot_score = max(mot_score, 2)
            elif "MOT10" in t:
                mot_score = max(mot_score, 1)
    motility = donor.get("motility", "")
    if "IUI" in motility:
        mot_score += 0.5
    scores["sperm_quality"] = round(min(mot_score, 3.5) / 3.5 * 30, 1)
    total += scores["sperm_quality"]

    cmv = donor.get("cmv_status", "").lower()
    if recipient_cmv == "negative":
        scores["cmv_match"] = 20.0 if "neg" in cmv else 0.0
    else:
        scores["cmv_match"] = 20.0
    total += scores["cmv_match"]

    gen = donor.get("genetic_matching", "").lower()
    scores["genetic_screening"] = 10.0 if gen == "yes" else 0.0
    total += scores["genetic_screening"]

    stock_total = 0
    if isinstance(stock, list):
        for s in stock:
            details = s.get("details", "") if isinstance(s, dict) else ""
            nums = [int(x) for x in str(details).split() if x.isdigit()]
            stock_total += sum(nums)
    if stock_total >= 10:
        scores["stock_availability"] = 15.0
    elif stock_total >= 5:
        scores["stock_availability"] = 10.0
    elif stock_total >= 1:
        scores["stock_availability"] = 5.0
    else:
        scores["stock_availability"] = 0.0
    total += scores["stock_availability"]

    id_rel = donor.get("id_release", donor.get("id_option", "")).lower()
    scores["id_release"] = 5.0 if "yes" in id_rel or "release" in id_rel else 0.0
    total += scores["id_release"]

    face = donor.get("cryos_face_matching", "").lower()
    scores["face_matching"] = 5.0 if face == "yes" else 0.0
    total += scores["face_matching"]

    profile = donor.get("profile_type", "").lower()
    scores["profile_depth"] = 5.0 if profile == "extended" else 2.0
    total += scores["profile_depth"]

    height_str = donor.get("height__cm", "0")
    try:
        height = int(height_str)
    except (ValueError, TypeError):
        height = 0
    if 175 <= height <= 190:
        scores["physical_preference"] = 10.0
    elif 170 <= height <= 195:
        scores["physical_preference"] = 7.0
    elif height > 0:
        scores["physical_preference"] = 4.0
    else:
        scores["physical_preference"] = 0.0
    total += scores["physical_preference"]

    scores["total"] = round(total, 1)
    return scores


@app.route("/api/donor-analysis", methods=["GET"])
def api_donor_analysis():
    """Return all donors with scores."""
    recipient_cmv = request.args.get("recipient_cmv", "negative")
    donors_file = os.path.join(REPORTS_ROOT, datetime.now().strftime("%Y-%m-%d"), "cryos-donors.json")
    if not os.path.exists(donors_file):
        all_dates = sorted([d for d in os.listdir(REPORTS_ROOT)
                           if os.path.isfile(os.path.join(REPORTS_ROOT, d, "cryos-donors.json"))],
                          reverse=True)
        if all_dates:
            donors_file = os.path.join(REPORTS_ROOT, all_dates[0], "cryos-donors.json")
        else:
            return jsonify({"error": "No donor data found. Run parse-cryos-donors.py first."}), 404

    with open(donors_file, "r", encoding="utf-8") as f:
        donors = json.load(f)
    results = []
    for d in donors:
        scores = _score_donor(d, recipient_cmv)
        results.append({**d, "_scores": scores, "_total_score": scores["total"]})

    results.sort(key=lambda x: x["_total_score"], reverse=True)
    return jsonify({
        "donors": results,
        "count": len(results),
        "source_file": donors_file,
        "scoring_weights": {
            "sperm_quality": "30 (MOT level + IUI prep)",
            "cmv_match": "20 (critical for CMV-neg recipients)",
            "stock_availability": "15 (vial count)",
            "genetic_screening": "10 (carrier screening available)",
            "physical_preference": "10 (height 175-190cm optimal)",
            "id_release": "5 (identity disclosure at 18)",
            "face_matching": "5 (Cryos face matching available)",
            "profile_depth": "5 (Extended vs Basic profile)",
        }
    })


@app.route("/api/donor-analysis/ai-reason", methods=["POST"])
def api_donor_ai_reason():
    """Use a strong LLM (qwen3-vl:8b) to analyze and reason about top donors. Returns SSE stream."""
    data = request.get_json(silent=True) or {}
    top_n = data.get("top_n", 20)
    recipient_cmv = data.get("recipient_cmv", "negative")

    donors_file = os.path.join(REPORTS_ROOT, datetime.now().strftime("%Y-%m-%d"), "cryos-donors.json")
    if not os.path.exists(donors_file):
        all_dates = sorted([d for d in os.listdir(REPORTS_ROOT)
                           if os.path.isfile(os.path.join(REPORTS_ROOT, d, "cryos-donors.json"))],
                          reverse=True)
        if all_dates:
            donors_file = os.path.join(REPORTS_ROOT, all_dates[0], "cryos-donors.json")
        else:
            return jsonify({"error": "No donor data found."}), 404

    with open(donors_file, "r", encoding="utf-8") as f:
        donors = json.load(f)
    scored = []
    for d in donors:
        scores = _score_donor(d, recipient_cmv)
        scored.append({**d, "_scores": scores, "_total_score": scores["total"]})
    scored.sort(key=lambda x: x["_total_score"], reverse=True)
    top = scored[:top_n]

    summary_lines = [f"Top {top_n} Cryos Sperm Donors (recipient CMV: {recipient_cmv}):"]
    for i, d in enumerate(top, 1):
        sc = d["_scores"]
        stock_count = 0
        for s in d.get("stock", []):
            if isinstance(s, dict):
                nums = [int(x) for x in str(s.get("details", "")).split() if x.isdigit()]
                stock_count += sum(nums)
        summary_lines.append(
            f"{i}. ID={d.get('donor_id','')} Score={d['_total_score']:.0f}/100 "
            f"Race={d.get('race','')} Ethnicity={d.get('ethnicity','')} Height={d.get('height__cm','')}cm "
            f"Eyes={d.get('eye_colour','')} Hair={d.get('hair_colour','')} Blood={d.get('blood_type','')} "
            f"CMV={d.get('cmv_status','')} ShipFrom={d.get('shipped_from','')} Profile={d.get('profile_type','')} "
            f"Stock={stock_count} vials | "
            f"Quality={sc.get('sperm_quality',0)}/30 CMV={sc.get('cmv_match',0)}/20 "
            f"Stock={sc.get('stock_availability',0)}/15 Genetic={sc.get('genetic_screening',0)}/10 "
            f"Physical={sc.get('physical_preference',0)}/10"
        )

    prompt = "\n".join(summary_lines) + (
        "\n\nYou are a fertility consultant AI. Analyze these top donors in detail. For each donor:\n"
        "1. Explain WHY they scored high (which criteria contributed most)\n"
        "2. Note any concerns or trade-offs\n"
        "3. Highlight unique advantages\n\n"
        "Then provide your FINAL RECOMMENDATION: pick the best 5 donors and explain your reasoning "
        "considering sperm quality (MOT level), health matching (CMV), stock availability, "
        "genetic screening, physical characteristics, and profile completeness.\n\n"
        "Be thorough and clinical. Do NOT invent data not provided."
    )

    def generate():
        import requests as req
        try:
            resp = req.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are a clinical donor analysis expert. Be thorough and precise."},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": True,
                    "think": False,
                    "options": {"num_predict": 8192, "temperature": 0.3},
                },
                stream=True, timeout=600,
            )
            full_text = ""
            for line in resp.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            full_text += token
                            yield f"data: {json.dumps({'type':'token','content':token})}\n\n"
                        if chunk.get("done"):
                            yield f"data: {json.dumps({'type':'done','content':full_text})}\n\n"
                            break
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/donor-analysis/pdf", methods=["POST"])
def api_donor_analysis_pdf():
    """Generate a PDF report of top donors."""
    data = request.get_json(silent=True) or {}
    top_n = data.get("top_n", 20)
    recipient_cmv = data.get("recipient_cmv", "negative")
    reason_text = data.get("reason_text", "")
    language = data.get("language", "en")

    donors_file = os.path.join(REPORTS_ROOT, datetime.now().strftime("%Y-%m-%d"), "cryos-donors.json")
    if not os.path.exists(donors_file):
        all_dates = sorted([d for d in os.listdir(REPORTS_ROOT)
                           if os.path.isfile(os.path.join(REPORTS_ROOT, d, "cryos-donors.json"))],
                          reverse=True)
        if all_dates:
            donors_file = os.path.join(REPORTS_ROOT, all_dates[0], "cryos-donors.json")
        else:
            return jsonify({"error": "No donor data found."}), 404

    with open(donors_file, "r", encoding="utf-8") as f:
        donors = json.load(f)
    scored = []
    for d in donors:
        scores = _score_donor(d, recipient_cmv)
        scored.append({**d, "_scores": scores, "_total_score": scores["total"]})
    scored.sort(key=lambda x: x["_total_score"], reverse=True)
    top = scored[:top_n]

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
    except ImportError:
        return jsonify({"error": "reportlab not installed"}), 500

    today = datetime.now().strftime("%Y-%m-%d")
    pdf_dir = os.path.join(REPORTS_ROOT, today)
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f"donor-analysis-top{top_n}.pdf")

    doc = SimpleDocTemplate(pdf_path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    zh = language == "zh"
    if zh:
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            for s in styles.byName.values():
                s.fontName = "STSong-Light"
        except Exception:
            pass

    title_text = f"Cryos 捐赠者分析 - 前 {top_n} 名" if zh else f"Cryos Donor Analysis - Top {top_n}"
    sub_text = f"生成日期: {today} | 接受者 CMV: {recipient_cmv}" if zh else f"Generated: {today} | Recipient CMV: {recipient_cmv}"
    elements.append(Paragraph(title_text, styles["Title"]))
    elements.append(Paragraph(sub_text, styles["Normal"]))
    elements.append(Spacer(1, 12))

    if reason_text:
        rec_title = "推荐摘要:" if zh else "Recommendation Summary:"
        elements.append(Paragraph(rec_title, styles["Heading2"]))
        for line in reason_text.split("\n"):
            if line.strip():
                elements.append(Paragraph(line.strip(), styles["Normal"]))
        elements.append(Spacer(1, 12))

    if zh:
        header = ["排名", "ID", "评分", "种族", "身高", "眼睛", "头发",
                  "血型", "CMV", "发货地", "MOT", "库存"]
    else:
        header = ["Rank", "ID", "Score", "Race", "Height", "Eyes", "Hair",
                  "Blood", "CMV", "Ship From", "MOT", "Stock"]
    from reportlab.lib.styles import ParagraphStyle
    link_style = ParagraphStyle("link", parent=styles["Normal"], fontSize=7,
                                textColor=colors.HexColor("#1a73e8"), alignment=1)
    if zh:
        link_style.fontName = "STSong-Light"

    table_data = [header]
    for rank, d in enumerate(top, 1):
        stock_count = 0
        mot_best = ""
        for s in d.get("stock", []):
            if isinstance(s, dict):
                details = s.get("details", "")
                nums = [int(x) for x in str(details).split() if x.isdigit()]
                stock_count += sum(nums)
                if not mot_best:
                    mot_best = s.get("type", "")
        did = d.get("donor_id", "")
        profile_url = f"https://www.cryosinternational.com/en-gb/dk-shop/private/dk-donor-profile/?name={did}"
        id_cell = Paragraph(f'<a href="{profile_url}" color="blue">{did}</a>', link_style)
        table_data.append([
            str(rank), id_cell, f"{d['_total_score']:.0f}",
            d.get("race", ""), d.get("height__cm", ""), d.get("eye_colour", ""),
            d.get("hair_colour", ""), d.get("blood_type", ""), d.get("cmv_status", ""),
            d.get("shipped_from", ""), mot_best, str(stock_count),
        ])

    t = Table(table_data, repeatRows=1)
    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2a2d3a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f5")]),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]
    if zh:
        table_style.append(("FONTNAME", (0, 0), (-1, -1), "STSong-Light"))
    t.setStyle(TableStyle(table_style))
    elements.append(t)
    elements.append(Spacer(1, 20))

    crit_title = "评分标准:" if zh else "Scoring Criteria:"
    elements.append(Paragraph(crit_title, styles["Heading3"]))
    if zh:
        criteria = [
            "精子质量 (30分): MOT30+=3, MOT20=2, MOT10=1; IUI-ready加分",
            "CMV匹配 (20分): 接受者CMV阴性时至关重要",
            "库存量 (15分): 10+管=15, 5+=10, 1+=5",
            "遗传筛查 (10分): 携带者筛查可用",
            "身体偏好 (10分): 身高175-190cm最佳",
            "身份公开 (5分): 18岁后身份披露选项",
            "面部匹配 (5分): Cryos面部匹配可用",
            "档案深度 (5分): Extended=5, Basic=2",
        ]
    else:
        criteria = [
            "Sperm Quality (30pts): MOT30+=3, MOT20=2, MOT10=1; IUI-ready bonus",
            "CMV Match (20pts): Critical if recipient is CMV-negative",
            "Stock Availability (15pts): 10+ vials=15, 5+=10, 1+=5",
            "Genetic Screening (10pts): Carrier screening available",
            "Physical Preference (10pts): Height 175-190cm optimal",
            "ID Release (5pts): Identity disclosure option",
            "Face Matching (5pts): Cryos face matching available",
            "Profile Depth (5pts): Extended=5, Basic=2",
        ]
    for c in criteria:
        elements.append(Paragraph(f"- {c}", styles["Normal"]))

    doc.build(elements)
    return jsonify({
        "pdf_path": pdf_path,
        "pdf_url": f"/api/toolbar/audio-file/{today}/donor-analysis-top{top_n}.pdf",
    })


# ---------------------------------------------------------------------------
# Stock Analysis API
# ---------------------------------------------------------------------------
_stock_path = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stock")
)
_rag_config = sys.modules.get("config")

import importlib.util as _ilu
_stock_cfg_spec = _ilu.spec_from_file_location(
    "stock_config", os.path.join(_stock_path, "config.py")
)
_stock_config = _ilu.module_from_spec(_stock_cfg_spec)
_stock_cfg_spec.loader.exec_module(_stock_config)


_STOCK_MODULES = [
    "config", "fetch_market_data", "technical_analysis", "report_technical",
    "fundamental_analysis", "sentiment", "features", "model_xgboost",
    "model_price_predictor", "prediction_tracker", "llm_reasoning",
    "watchlist", "scanner", "hot_sectors", "market_sentiment",
    "black_swan_detector", "china_market_data", "model_timing",
    "backtest_engine",
]


def _with_stock_imports(fn):
    """Decorator that swaps sys.modules['config'] to stock config for the call.

    Also flushes cached stock modules so they re-import with the correct
    config — prevents 'cannot import STOCK_DATA_DIR from config' when
    a stock module was first imported with the parent scripts/config.py.
    """
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        prev_config = sys.modules.get("config")
        prev_mods = {m: sys.modules.pop(m) for m in _STOCK_MODULES if m in sys.modules}

        sys.modules["config"] = _stock_config
        if _stock_path not in sys.path:
            sys.path.insert(0, _stock_path)
        try:
            return fn(*args, **kwargs)
        finally:
            for m in _STOCK_MODULES:
                if m in sys.modules and m != "config":
                    del sys.modules[m]
            if prev_config is not None:
                sys.modules["config"] = prev_config
            elif "config" in sys.modules:
                del sys.modules["config"]
    return wrapper


@app.route("/api/stock/analyze", methods=["POST"])
@_with_stock_imports
def api_stock_analyze():
    """Run stock analysis (technical, fundamental, sentiment, or full)."""
    body = request.get_json(silent=True) or {}
    symbol = body.get("symbol", "").strip()
    mode = body.get("mode", "full")

    if not symbol or not symbol.isdigit():
        return jsonify({"error": "请输入有效的股票代码 (纯数字)"}), 400

    try:
        result = {}

        if mode in ("technical", "full"):
            from report_technical import generate_report as gen_tech, save_report
            from technical_analysis import analyze as tech_analyze
            analysis = tech_analyze(symbol)
            save_report(symbol, analysis)
            result["technical_report"] = gen_tech(symbol, analysis)

        if mode in ("fundamental", "full"):
            from fundamental_analysis import fetch_fundamentals, generate_fundamental_report
            fetch_fundamentals(symbol)
            result["fundamental_report"] = generate_fundamental_report(symbol)

        if mode in ("sentiment", "full"):
            from sentiment import analyze_stock_sentiment, generate_sentiment_report
            analyze_stock_sentiment(symbol)
            result["sentiment_report"] = generate_sentiment_report(symbol)

        if mode in ("xgboost", "full"):
            from model_xgboost import train_and_predict, generate_xgb_report
            xgb_result = train_and_predict(symbol)
            result["xgb_report"] = generate_xgb_report(symbol, xgb_result)

        if mode in ("fund_flow", "full"):
            try:
                from china_market_data import stock_fund_flow_signals
                ff = stock_fund_flow_signals(symbol)
                phase = ff.get("smart_money_phase", "无信号")
                score = ff.get("accumulation_score", 0)
                detail = ff.get("detail", "")
                lines = [
                    "# 资金流向 & 聪明钱分析",
                    f"**聪明钱阶段: {phase}** (布局得分: {score}/100)",
                    "",
                ]
                if detail:
                    lines.append(f"> {detail}")
                    lines.append("")
                lines.append(f"| 指标 | 值 |")
                lines.append(f"|---|---|")
                lines.append(f"| 3日主力净流入 | {ff.get('main_net_3d', 'N/A')} |")
                lines.append(f"| 10日主力净流入 | {ff.get('main_net_10d', 'N/A')} |")
                lines.append(f"| 3日主力净占比 | {ff.get('main_pct_3d', 'N/A')}% |")
                lines.append(f"| 超大单占比 | {ff.get('super_large_ratio', 'N/A')} |")
                lines.append(f"| 价格-资金背离 | {ff.get('fund_price_divergence', 'N/A')} |")
                lines.append("")
                phase_guide = {
                    "布局期": "资金持续流入但价格未涨,主力正在悄悄吸筹 → **可以考虑建仓**",
                    "拉升期": "资金流入且价格已涨,追高风险大 → **谨慎追高,T+1风险**",
                    "出货期": "资金流出但价格仍涨,主力可能在出货 → **不建议买入**",
                    "观察期": "有资金流入迹象但未达布局标准 → **继续观察**",
                    "无信号": "资金流向不明确 → **暂无明确方向**",
                }
                lines.append(f"**建议:** {phase_guide.get(phase, '')}")
                result["fund_flow_report"] = "\n".join(lines)
            except Exception as e:
                log.debug("资金流向分析 %s 失败: %s", symbol, e)

        if mode == "full":
            from llm_reasoning import generate_prediction
            result["prediction_report"] = generate_prediction(symbol, stream=False)

        return jsonify(result)

    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": f"分析失败: {exc}"}), 500


@app.route("/api/stock/analyze/deepseek", methods=["POST"])
@_with_stock_imports
def api_stock_analyze_deepseek():
    """Run DeepSeek API analysis for a stock (final LLM step only)."""
    body = request.get_json(silent=True) or {}
    symbol = body.get("symbol", "").strip()

    if not symbol or not symbol.isdigit():
        return jsonify({"error": "请输入有效的股票代码 (纯数字)"}), 400

    try:
        from llm_reasoning import generate_prediction_deepseek
        result = generate_prediction_deepseek(symbol)
        return jsonify(result)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": f"DeepSeek 分析失败: {exc}"}), 500


@app.route("/api/stock/watchlist", methods=["GET"])
@_with_stock_imports
def api_stock_watchlist_get():
    """Get the watchlist with latest prices."""
    try:
        from watchlist import get_watchlist_with_prices
        stocks = get_watchlist_with_prices()
        return jsonify({"stocks": stocks})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/watchlist", methods=["POST"])
@_with_stock_imports
def api_stock_watchlist_add():
    """Add a stock to the watchlist."""
    body = request.get_json(silent=True) or {}
    symbol = body.get("symbol", "").strip()
    name = body.get("name", "").strip()
    sector = body.get("sector", "").strip()
    if not symbol:
        return jsonify({"error": "缺少股票代码"}), 400
    try:
        from watchlist import add_stock
        result = add_stock(symbol, name, sector)
        return jsonify(result)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/watchlist/<symbol>", methods=["DELETE"])
@_with_stock_imports
def api_stock_watchlist_remove(symbol):
    """Remove a stock from the watchlist."""
    try:
        from watchlist import remove_stock
        result = remove_stock(symbol)
        return jsonify(result)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/watchlist/refresh", methods=["POST"])
@_with_stock_imports
def api_stock_watchlist_refresh():
    """Refresh all watchlist data."""
    try:
        from watchlist import refresh_all_data
        refresh_all_data()
        return jsonify({"ok": True})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/scan/start", methods=["POST"])
@_with_stock_imports
def api_stock_scan_start():
    """Start AI stock scanner."""
    try:
        body = request.get_json(silent=True) or {}
        use_ds = body.get("use_deepseek", False)
        from scanner import start_scan
        result = start_scan(use_deepseek=use_ds)
        return jsonify(result)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/scan/status", methods=["GET"])
@_with_stock_imports
def api_stock_scan_status():
    """Get scan progress and partial results."""
    try:
        from scanner import get_scan_status
        return jsonify(get_scan_status())
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/scan/stop", methods=["POST"])
@_with_stock_imports
def api_stock_scan_stop():
    """Stop running scan."""
    try:
        from scanner import stop_scan
        return jsonify(stop_scan())
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/scan/result", methods=["GET"])
@_with_stock_imports
def api_stock_scan_result():
    """Get latest scan result."""
    try:
        from scanner import get_latest_result
        result = get_latest_result()
        if result:
            return jsonify(result)
        return jsonify({"error": "暂无扫描结果"}), 404
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/scan/history", methods=["GET"])
@_with_stock_imports
def api_stock_scan_history():
    """Get scan history with performance tracking."""
    try:
        from scanner import get_history
        return jsonify({"history": get_history()})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/scan/dates", methods=["GET"])
@_with_stock_imports
def api_stock_scan_dates():
    """List available scan dates."""
    try:
        from scanner import list_scan_dates
        return jsonify({"dates": list_scan_dates()})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/scan/result/<date_str>", methods=["GET"])
@_with_stock_imports
def api_stock_scan_result_by_date(date_str):
    """Get scan result for a specific date."""
    try:
        from scanner import get_result_by_date
        result = get_result_by_date(date_str)
        if result:
            return jsonify(result)
        return jsonify({"error": "该日期无扫描结果"}), 404
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


# --- Daily Training & Price Prediction ---

_train_thread = None
_train_lock = __import__("threading").Lock()


@app.route("/api/stock/train/daily", methods=["POST"])
@_with_stock_imports
def api_stock_train_daily():
    """Train price prediction models for all watchlist stocks."""
    global _train_thread
    import threading

    with _train_lock:
        if _train_thread is not None and _train_thread.is_alive():
            return jsonify({"ok": False, "error": "训练正在进行中"})

    def _run_training():
        import importlib.util as _ilu
        _stock_dir = os.path.dirname(os.path.abspath(__file__))
        _stock_dir = os.path.join(os.path.dirname(_stock_dir), "stock")
        if _stock_dir not in sys.path:
            sys.path.insert(0, _stock_dir)
        _cfg_path = os.path.join(_stock_dir, "config.py")
        _spec = _ilu.spec_from_file_location("config", _cfg_path)
        _cfg = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_cfg)
        sys.modules["config"] = _cfg

        for mod_name in ["watchlist", "model_price_predictor", "prediction_tracker",
                         "fetch_market_data", "technical_analysis", "features"]:
            if mod_name in sys.modules:
                del sys.modules[mod_name]

        from watchlist import list_stocks
        from model_price_predictor import train_price_prediction
        from prediction_tracker import record_prediction, backfill_actuals, get_latest_verification, get_accuracy_stats, get_aggregate_stats
        from fetch_market_data import update_stock_data

        stocks = list_stocks()
        progress_path = os.path.join(_cfg.STOCK_REPORTS_ROOT, "train_progress.json")
        progress = {
            "status": "running",
            "total": len(stocks),
            "completed": 0,
            "current": "",
            "results": [],
            "verifications": [],
            "started_at": __import__("datetime").datetime.now().isoformat(),
        }

        def _save_prog():
            with open(progress_path, "w", encoding="utf-8") as fp:
                __import__("json").dump(progress, fp, ensure_ascii=False, indent=2, default=str)

        _save_prog()

        for i, stock in enumerate(stocks):
            sym = stock.get("symbol", "")
            if not sym:
                continue
            progress["current"] = f"{stock.get('name', sym)} ({sym})"
            _save_prog()

            try:
                update_stock_data(sym)
                n_filled = backfill_actuals(sym)

                verification = get_latest_verification(sym)
                if verification:
                    verification["symbol"] = sym
                    verification["name"] = stock.get("name", "")
                    progress["verifications"].append(verification)

                result = train_price_prediction(sym)
                if "error" not in result:
                    record_prediction(sym, result)
                    stats = get_accuracy_stats(sym)
                    progress["results"].append({
                        "symbol": sym,
                        "name": stock.get("name", ""),
                        "predictions": result.get("predictions"),
                        "change_pct": result.get("change_pct"),
                        "current_close": result.get("current_close"),
                        "health": stats.get("health"),
                    })
                else:
                    progress["results"].append({
                        "symbol": sym, "error": result["error"]
                    })
            except Exception as e:
                progress["results"].append({"symbol": sym, "error": str(e)})

            progress["completed"] = i + 1
            _save_prog()

        try:
            watchlist_symbols = [s.get("symbol") for s in stocks if s.get("symbol")]
            progress["aggregate_stats"] = get_aggregate_stats(watchlist_symbols)
        except Exception:
            pass

        try:
            from market_sentiment import fetch_all_sentiment
            progress["sentiment"] = fetch_all_sentiment()
        except Exception:
            pass

        try:
            from black_swan_detector import scan_world_news
            progress["black_swan"] = scan_world_news()
        except Exception:
            pass

        progress["status"] = "done"
        progress["finished_at"] = __import__("datetime").datetime.now().isoformat()
        _save_prog()

    with _train_lock:
        _train_thread = __import__("threading").Thread(target=_run_training, daemon=True)
        _train_thread.start()

    return jsonify({"ok": True, "message": "训练已启动"})


@app.route("/api/stock/train/status", methods=["GET"])
@_with_stock_imports
def api_stock_train_status():
    """Get daily training progress."""
    try:
        from config import STOCK_REPORTS_ROOT
        import json as _json
        path = os.path.join(STOCK_REPORTS_ROOT, "train_progress.json")
        if not os.path.isfile(path):
            return jsonify({"status": "idle"})
        with open(path, encoding="utf-8") as f:
            progress = _json.load(f)
        progress["running"] = _train_thread is not None and _train_thread.is_alive()
        return jsonify(progress)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/predict/<symbol>", methods=["GET"])
@_with_stock_imports
def api_stock_predict(symbol):
    """Get price prediction and tracking stats for a symbol."""
    try:
        from model_price_predictor import load_price_prediction
        from prediction_tracker import get_accuracy_stats
        pred = load_price_prediction(symbol)
        stats = get_accuracy_stats(symbol)
        return jsonify({"prediction": pred, "accuracy": stats})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/sentiment", methods=["GET"])
@_with_stock_imports
def api_stock_sentiment():
    """Fetch or return cached market sentiment (Fear/Greed + VIX)."""
    try:
        from market_sentiment import fetch_all_sentiment, load_cached_sentiment
        force = request.args.get("refresh", "").lower() in ("1", "true", "yes")
        if force:
            data = fetch_all_sentiment()
        else:
            data = load_cached_sentiment()
            if not data:
                data = fetch_all_sentiment()
        return jsonify(data)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/blackswan", methods=["GET"])
@_with_stock_imports
def api_stock_blackswan():
    """Scan world news for black swan events affecting industries."""
    try:
        from black_swan_detector import scan_world_news, load_cached_alerts
        force = request.args.get("refresh", "").lower() in ("1", "true", "yes")
        date_str = request.args.get("date")
        if force or not load_cached_alerts():
            data = scan_world_news(date_str)
        else:
            data = load_cached_alerts()
        return jsonify(data)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/risk/<symbol>", methods=["GET"])
@_with_stock_imports
def api_stock_risk(symbol):
    """Check if a stock is at risk from detected black swan events."""
    try:
        from black_swan_detector import check_stock_risk
        from watchlist import get_watchlist
        wl = get_watchlist()
        sector = ""
        for s in wl:
            if s["symbol"] == symbol:
                sector = s.get("sector", "")
                break
        risk = check_stock_risk(symbol, sector)
        return jsonify(risk or {"symbol": symbol, "alerts": [], "max_severity": None})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


# --- Timing Model & Backtest ---

_timing_thread = None
_timing_lock = __import__("threading").Lock()


@app.route("/api/stock/timing/train", methods=["POST"])
@_with_stock_imports
def api_stock_timing_train():
    """Train timing models for all watchlist stocks."""
    global _timing_thread
    import threading

    with _timing_lock:
        if _timing_thread is not None and _timing_thread.is_alive():
            return jsonify({"ok": False, "error": "择时训练正在进行中"})

    def _run_timing_training():
        import importlib.util as _ilu
        _stock_dir = os.path.dirname(os.path.abspath(__file__))
        _stock_dir = os.path.join(os.path.dirname(_stock_dir), "stock")
        if _stock_dir not in sys.path:
            sys.path.insert(0, _stock_dir)
        _cfg_path = os.path.join(_stock_dir, "config.py")
        _spec = _ilu.spec_from_file_location("config", _cfg_path)
        _cfg = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_cfg)
        sys.modules["config"] = _cfg

        for mod_name in ["watchlist", "model_timing", "features",
                         "technical_analysis", "china_market_data",
                         "fetch_market_data"]:
            if mod_name in sys.modules:
                del sys.modules[mod_name]

        from watchlist import list_stocks
        from model_timing import train_timing_model

        stocks = list_stocks()
        progress_path = os.path.join(_cfg.STOCK_REPORTS_ROOT, "timing_progress.json")
        progress = {
            "status": "running",
            "total": len(stocks),
            "completed": 0,
            "current": "",
            "results": [],
            "started_at": __import__("datetime").datetime.now().isoformat(),
        }

        def _save_prog():
            with open(progress_path, "w", encoding="utf-8") as fp:
                __import__("json").dump(progress, fp, ensure_ascii=False, indent=2, default=str)

        _save_prog()

        for i, stock in enumerate(stocks):
            sym = stock.get("symbol", "")
            if not sym:
                continue
            progress["current"] = f"{stock.get('name', sym)} ({sym})"
            _save_prog()

            try:
                result = train_timing_model(sym)
                progress["results"].append({
                    "symbol": sym,
                    "name": stock.get("name", ""),
                    "status": result.get("status", "error"),
                    "buy_metrics": result.get("buy_metrics"),
                    "exit_metrics": result.get("exit_metrics"),
                })
            except Exception as e:
                progress["results"].append({"symbol": sym, "error": str(e)})

            progress["completed"] = i + 1
            _save_prog()

        progress["status"] = "done"
        progress["finished_at"] = __import__("datetime").datetime.now().isoformat()
        _save_prog()

    with _timing_lock:
        _timing_thread = __import__("threading").Thread(target=_run_timing_training, daemon=True)
        _timing_thread.start()

    return jsonify({"ok": True, "message": "择时训练已启动"})


@app.route("/api/stock/timing/status", methods=["GET"])
@_with_stock_imports
def api_stock_timing_status():
    """Get timing training progress."""
    try:
        from config import STOCK_REPORTS_ROOT
        import json as _json
        path = os.path.join(STOCK_REPORTS_ROOT, "timing_progress.json")
        if not os.path.isfile(path):
            return jsonify({"status": "idle"})
        with open(path, encoding="utf-8") as f:
            progress = _json.load(f)
        progress["running"] = _timing_thread is not None and _timing_thread.is_alive()
        return jsonify(progress)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/timing/predict/<symbol>", methods=["GET"])
@_with_stock_imports
def api_stock_timing_predict(symbol):
    """Get timing signal for a single stock."""
    try:
        from model_timing import predict_timing
        result = predict_timing(symbol)
        return jsonify(result)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/timing/predict-all", methods=["GET"])
@_with_stock_imports
def api_stock_timing_predict_all():
    """Get timing signals for all watchlist stocks."""
    try:
        from model_timing import predict_batch
        from watchlist import list_stocks
        stocks = list_stocks()
        symbols = [s["symbol"] for s in stocks if s.get("symbol")]
        results = predict_batch(symbols)
        for r in results:
            for s in stocks:
                if s["symbol"] == r["symbol"]:
                    r["name"] = s.get("name", "")
                    break
        return jsonify({"predictions": results})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/backtest/<symbol>", methods=["POST"])
@_with_stock_imports
def api_stock_backtest(symbol):
    """Run backtest for a symbol."""
    try:
        from backtest_engine import run_backtest
        body = request.get_json(silent=True) or {}
        strategy = body.get("strategy", "timing")
        capital = float(body.get("capital", 500000))
        result = run_backtest(symbol, strategy=strategy, initial_capital=capital)
        from dataclasses import asdict
        return jsonify(asdict(result))
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/backtest/<symbol>", methods=["GET"])
@_with_stock_imports
def api_stock_backtest_get(symbol):
    """Get latest backtest result for a symbol."""
    try:
        from backtest_engine import load_latest_backtest
        strategy = request.args.get("strategy", "timing")
        result = load_latest_backtest(symbol, strategy)
        if result:
            return jsonify(result)
        return jsonify({"error": "无回测结果, 请先运行回测"}), 404
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/china-data", methods=["GET"])
@_with_stock_imports
def api_stock_china_data():
    """Fetch all China market data (northbound, margin, limit pool, etc)."""
    try:
        from china_market_data import fetch_all_china_data
        data = fetch_all_china_data()
        return jsonify(data)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/china-data/fund-flow/<symbol>", methods=["GET"])
@_with_stock_imports
def api_stock_fund_flow(symbol):
    """Get individual stock fund flow signals."""
    try:
        from china_market_data import stock_fund_flow_signals
        data = stock_fund_flow_signals(symbol)
        return jsonify(data)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stock/national-team", methods=["GET"])
@_with_stock_imports
def api_stock_national_team():
    """Monitor national team ETF share changes."""
    try:
        from china_market_data import (national_team_monitor, national_team_trend,
                                       national_team_period_stats, national_team_backfill_history,
                                       national_team_fund_signals)
        snapshot = national_team_monitor()
        backfill = national_team_backfill_history(days=90)
        trend = national_team_trend()
        period_stats = national_team_period_stats()
        fund_signals = national_team_fund_signals()
        return jsonify({"snapshot": snapshot, "trend": trend,
                        "period_stats": period_stats, "backfill": backfill,
                        "fund_signals": fund_signals})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


# ===================================================================
# WEB UI
# ===================================================================

AGENT_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Jarvis — AI Assistant</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:#0f1117;color:#e0e0e0;height:100vh;display:flex;flex-direction:column;overflow:hidden}
.app-layout{display:flex;flex:1;min-height:0;position:relative;overflow:hidden}
.main-column{flex:1;display:flex;flex-direction:column;min-width:0;min-height:0}
.sidebar-toggle{background:transparent;border:1px solid #3a3d4a;color:#a0a4b8;border-radius:6px;
                padding:6px 10px;cursor:pointer;font-size:1.15em;line-height:1;flex-shrink:0}
.sidebar-toggle:hover{background:#2a2d3a;color:#e0e0e0}
.session-sidebar{width:260px;flex:0 0 auto;background:#131520;border-right:1px solid #2a2d3a;
                 display:flex;flex-direction:column;overflow:hidden;
                 transition:flex-basis .25s ease,width .25s ease,opacity .2s ease,border-color .2s ease,transform .25s ease}
.session-sidebar.collapsed{flex-basis:0;width:0;min-width:0;max-width:0;opacity:0;border-right-color:transparent;pointer-events:none}
.session-sidebar-inner{width:260px;flex:1;display:flex;flex-direction:column;min-height:0;padding:12px;box-sizing:border-box}
.session-sidebar .new-chat-sidebar{width:100%;padding:8px 12px;background:#2a2d3a;color:#e0e0e0;
                                   border:1px solid #3a3d4a;border-radius:8px;cursor:pointer;font-size:.85em;font-weight:500}
.session-sidebar .new-chat-sidebar:hover{background:#3a3d4a}
.session-list{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:4px;margin-top:8px;padding-right:2px}
.session-item{position:relative;padding:10px 30px 10px 10px;border-radius:8px;cursor:pointer;border:1px solid transparent;
               transition:background .15s,border-color .15s}
.session-item:hover{background:#1e2230}
.session-item.active{background:#252836;border-color:#3a4d7a}
.session-title{font-size:.85em;color:#e0e0e0;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.35}
.session-time{font-size:.68em;color:#6b7280;margin-top:4px}
.session-del{position:absolute;top:6px;right:4px;width:24px;height:24px;border:none;border-radius:4px;background:transparent;
             color:#8b8fa4;cursor:pointer;font-size:16px;line-height:24px;padding:0;display:flex;align-items:center;justify-content:center}
.session-del:hover{background:#3a1a1a;color:#f87171}
.sidebar-scrim{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:250}
.sidebar-scrim.visible{display:block}
@media (max-width:767px){
  .session-sidebar{position:fixed;left:0;top:0;bottom:0;z-index:300;flex:none;width:260px;max-width:260px;opacity:1;
                   pointer-events:auto;border-right:1px solid #2a2d3a;transform:translateX(0)}
  .session-sidebar.collapsed{transform:translateX(-100%);width:260px;max-width:260px;flex-basis:auto;opacity:1;pointer-events:none}
  .session-sidebar:not(.collapsed){box-shadow:4px 0 24px rgba(0,0,0,.5)}
}
.header{background:#161822;padding:14px 24px;border-bottom:1px solid #2a2d3a;
        display:flex;align-items:center;gap:16px;flex-shrink:0}
.header h1{font-size:1.2em;color:#c4c8f0;font-weight:600}
.header .status{font-size:0.78em;padding:3px 10px;border-radius:12px;font-weight:500}
.status-ok{background:#1a3a2a;color:#4ade80}
.status-err{background:#3a1a1a;color:#f87171}
.header .model-select{margin-left:auto;padding:5px 10px;background:#1e2030;color:#a0a4b8;
                      border:1px solid #3a3d4a;border-radius:6px;font-size:0.82em;outline:none}
.header .model-select:focus{border-color:#4a6cf7}
.header .reset-btn{padding:6px 16px;background:#2a2d3a;color:#a0a4b8;
                   border:1px solid #3a3d4a;border-radius:6px;cursor:pointer;font-size:0.85em}
.header .reset-btn:hover{background:#3a3d4a;color:#e0e0e0}
.chat-area{flex:1;overflow-y:auto;padding:20px 24px;display:flex;flex-direction:column;gap:16px;min-height:0}
.msg{max-width:85%;padding:14px 18px;border-radius:12px;line-height:1.65;font-size:0.94em;
     word-wrap:break-word;white-space:pre-wrap}
.msg-user{align-self:flex-end;background:#2563eb;color:white;border-bottom-right-radius:4px}
.msg-assistant{align-self:flex-start;background:#1e2030;border:1px solid #2a2d3a;
               border-bottom-left-radius:4px}
.msg-assistant a{color:#60a5fa}
.msg-user-img{max-width:300px;max-height:200px;border-radius:8px;margin-top:8px;display:block}
.msg-actions{display:flex;gap:6px;margin-top:6px;justify-content:flex-end;opacity:0;transition:opacity .2s}
.msg:hover .msg-actions{opacity:1}
.note-btn{background:none;border:1px solid #3a3d5a;border-radius:4px;color:#8b8fa4;cursor:pointer;
          font-size:0.8em;padding:2px 8px;transition:all .2s}
.note-btn:hover{background:#2563eb;color:white;border-color:#2563eb}
.note-btn.saved{color:#10b981;border-color:#10b981}
.notes-panel{position:fixed;right:0;top:0;width:380px;height:100vh;background:#13151f;
             border-left:1px solid #2a2d3a;z-index:200;transform:translateX(100%);
             transition:transform .3s;display:flex;flex-direction:column}
.notes-panel.open{transform:translateX(0)}
.notes-header{padding:16px;border-bottom:1px solid #2a2d3a;display:flex;justify-content:space-between;align-items:center}
.notes-header h3{margin:0;color:#e0e0e0;font-size:1.1em}
.notes-body{flex:1;overflow-y:auto;padding:12px}
.note-card{background:#1e2030;border:1px solid #2a2d3a;border-radius:8px;margin-bottom:8px;overflow:hidden}
.note-header{display:flex;align-items:center;padding:10px 12px;cursor:pointer;gap:8px}
.note-header:hover{background:#252840}
.note-header .note-arrow{color:#666;font-size:0.7em;transition:transform 0.2s;flex-shrink:0}
.note-card.open .note-header .note-arrow{transform:rotate(90deg)}
.note-header .note-title{flex:1;font-size:0.88em;color:#c0c0c0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.note-header .note-date{font-size:0.7em;color:#555;flex-shrink:0}
.note-body{display:none;padding:0 12px 10px;border-top:1px solid #2a2d3a}
.note-card.open .note-body{display:block}
.note-body .note-content{font-size:0.88em;color:#c0c0c0;line-height:1.6;max-height:400px;overflow-y:auto;padding-top:8px}
.note-body .note-actions{display:flex;gap:6px;margin-top:8px;padding-top:8px;border-top:1px solid #2a2d3a}
.note-body .note-action-btn{background:none;border:1px solid #3a3d5a;color:#888;cursor:pointer;font-size:0.78em;padding:3px 10px;border-radius:4px}
.note-body .note-action-btn:hover{color:#c0c0c0;border-color:#60a5fa}
.note-body .note-action-btn.danger:hover{color:#ef4444;border-color:#ef4444}
.note-tags{display:flex;gap:4px;flex-wrap:wrap;margin-top:6px}
.note-tag{font-size:0.7em;background:#2563eb33;color:#60a5fa;padding:1px 6px;border-radius:10px}
.note-edit-area{width:100%;min-height:150px;background:#151725;color:#c0c0c0;border:1px solid #3a3d5a;border-radius:4px;padding:8px;font-size:0.85em;font-family:inherit;resize:vertical;margin-top:8px}
.note-edit-actions{display:flex;gap:6px;margin-top:6px}
.note-edit-actions button{padding:4px 14px;border-radius:4px;border:none;cursor:pointer;font-size:0.8em}
.note-edit-actions .save-btn{background:#2563eb;color:#fff}
.note-edit-actions .save-btn:hover{background:#3b82f6}
.note-edit-actions .cancel-btn{background:#333;color:#aaa}
.note-edit-actions .cancel-btn:hover{background:#444}
.thinking{align-self:flex-start;padding:10px 16px;background:#1a1d2e;border:1px dashed #3a3d5a;
          border-radius:8px;font-size:0.85em;color:#8b8fa4;display:flex;align-items:center;gap:10px}
.thinking .spinner{width:16px;height:16px;border:2px solid #3a3d5a;border-top-color:#60a5fa;
                   border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.tool-badge{display:inline-block;padding:2px 8px;background:#2a2d3a;border-radius:4px;
            font-family:monospace;font-size:0.85em;color:#a78bfa}
.sources{margin-top:10px;padding:10px 14px;background:#161822;border:1px solid #2a2d3a;
         border-radius:8px;font-size:0.82em}
.sources summary{cursor:pointer;color:#60a5fa;font-weight:500;margin-bottom:6px}
.sources .src-item{padding:3px 0;color:#8b8fa4}
.input-area{background:#161822;border-top:1px solid #2a2d3a;padding:14px 24px;flex-shrink:0}
.input-row{display:flex;gap:10px;align-items:flex-end;max-width:100%}
.input-row textarea{flex:1;background:#1e2030;border:1px solid #2a2d3a;border-radius:8px;
                    color:#e0e0e0;padding:12px 14px;font-size:0.95em;resize:none;
                    font-family:inherit;min-height:48px;max-height:200px;outline:none}
.input-row textarea:focus{border-color:#4a6cf7}
.input-row textarea::placeholder{color:#555}
.img-btn{background:#2a2d3a;border:1px solid #3a3d4a;border-radius:8px;padding:10px 12px;
         cursor:pointer;color:#a0a4b8;font-size:1.1em;transition:background .2s}
.img-btn:hover{background:#3a3d4a}
.img-btn.has-img{background:#1a3a2a;border-color:#4ade80;color:#4ade80}
.send-btn{background:#4a6cf7;border:none;border-radius:8px;padding:10px 22px;
          color:white;font-size:0.95em;cursor:pointer;font-weight:500;transition:background .2s}
.send-btn:hover{background:#3b5ce4}
.send-btn:disabled{opacity:0.5;cursor:not-allowed}
.img-preview{margin-top:8px;position:relative;display:inline-block}
.img-preview img{max-height:80px;border-radius:6px;border:1px solid #2a2d3a}
.img-preview .remove{position:absolute;top:-6px;right:-6px;background:#f87171;color:white;
                     border:none;border-radius:50%;width:20px;height:20px;cursor:pointer;
                     font-size:12px;line-height:20px;text-align:center}
.agent-toolbar{background:#161822;border-bottom:1px solid #2a2d3a;flex-shrink:0;padding:4px 12px}
.toolbar-inner{display:flex;flex-wrap:wrap;gap:2px;align-items:center}
.toolbar-cat{position:relative;border-radius:6px}
.toolbar-cat-header{display:inline-flex;align-items:center;gap:4px;background:transparent;border:1px solid transparent;
                   color:#a0a4b8;font-size:0.75em;font-weight:600;text-transform:uppercase;letter-spacing:.03em;
                   padding:5px 10px;cursor:pointer;text-align:left;font-family:inherit;border-radius:6px;
                   transition:background .15s,border-color .15s,color .15s}
.toolbar-cat-header:hover{color:#c4c8f0;background:#1e2030;border-color:#2a2d3a}
.toolbar-cat.open .toolbar-cat-header{color:#c4c8f0;background:#1e2030;border-color:#3a3d4a}
.toolbar-cat-chevron{display:inline-block;font-size:0.7em;color:#6b7280;transition:transform .15s}
.toolbar-cat.open .toolbar-cat-chevron{transform:rotate(180deg)}
.toolbar-cat-body{display:none;position:absolute;top:100%;left:0;z-index:100;min-width:200px;
                  background:#1a1d2e;border:1px solid #2a2d3a;border-radius:8px;padding:6px;
                  box-shadow:0 8px 24px rgba(0,0,0,0.4);margin-top:2px;
                  flex-wrap:wrap;gap:5px 6px}
.toolbar-cat.open .toolbar-cat-body{display:flex}
.toolbar-btn{display:inline-flex;align-items:center;gap:5px;background:#1e2030;border:1px solid #2a2d3a;
               color:#c4c8e0;border-radius:999px;padding:4px 11px;font-size:0.78em;cursor:pointer;
               font-family:inherit;transition:background .15s,border-color .15s,color .15s;white-space:nowrap}
.toolbar-btn:hover{background:#2a2d3a;border-color:#3a3d4a;color:#e0e0e0}
.toolbar-btn:disabled{opacity:0.55;cursor:not-allowed}
.toolbar-btn .mini-spin{width:12px;height:12px;border:2px solid #3a3d5a;border-top-color:#60a5fa;
                        border-radius:50%;animation:spin .8s linear infinite;flex-shrink:0}
.msg-system{align-self:flex-start;background:#1a1d28;border:1px dashed #3a4555;color:#9ca3af;
            font-size:0.88em;border-bottom-left-radius:4px;max-width:92%}
.msg-system .sys-label{color:#60a5fa;font-weight:600;margin-bottom:6px;font-size:0.92em}
.sys-toggle{display:inline-block;margin-top:8px;padding:4px 12px;background:#2a2d3a;border:1px solid #4a4d5a;
            color:#60a5fa;border-radius:4px;cursor:pointer;font-size:0.85em;transition:background .2s}
.sys-toggle:hover{background:#3a3d4a}
.sys-hidden-block{display:none}
.toast-container{position:fixed;bottom:20px;right:20px;z-index:400;display:flex;flex-direction:column;
                 gap:8px;pointer-events:none;max-width:min(360px,calc(100vw - 32px))}
.toast{pointer-events:auto;background:#1e2030;border:1px solid #3a3d4a;color:#e0e0e0;padding:10px 14px;
       border-radius:8px;font-size:0.84em;box-shadow:0 4px 16px rgba(0,0,0,.45);
       animation:toastIn .22s ease}
@keyframes toastIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.68);z-index:350;display:none;
               align-items:center;justify-content:center;padding:20px}
.modal-overlay.open{display:flex}
.modal-panel{background:#161822;border:1px solid #2a2d3a;border-radius:12px;max-width:680px;width:100%;
             max-height:86vh;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 12px 40px rgba(0,0,0,.55)}
.modal-head{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid #2a2d3a}
.modal-head h2{font-size:1em;color:#c4c8f0;font-weight:600}
.modal-close{background:transparent;border:none;color:#8b8fa4;font-size:1.5em;line-height:1;cursor:pointer;
             padding:4px 8px;border-radius:6px}
.modal-close:hover{background:#2a2d3a;color:#e0e0e0}
.modal-content{padding:12px 16px 16px;overflow-y:auto;flex:1}
.modal-stat{font-size:0.9em;color:#a0a4b8;margin-bottom:12px}
.wiki-user-check{display:flex;align-items:center;gap:8px;font-size:0.88em;color:#c4c8f0;cursor:pointer;
                 padding:6px 10px;border-radius:6px;transition:background .15s}
.wiki-user-check:hover{background:#1e2030}
.wiki-user-check input[type="checkbox"]{accent-color:#4a6cf7;width:16px;height:16px;cursor:pointer}
.data-table{width:100%;border-collapse:collapse;font-size:0.8em;margin-bottom:16px}
.data-table th,.data-table td{padding:7px 10px;text-align:left;border-bottom:1px solid #2a2d3a;vertical-align:top}
.data-table th{color:#8b8fa4;font-weight:600}
.data-table td.num,.data-table th:nth-child(2),.data-table th:nth-child(3){text-align:right}
.data-table-wrap{max-height:220px;overflow-y:auto;border:1px solid #2a2d3a;border-radius:8px}
</style>
</head>
<body>
<div class="sidebar-scrim" id="sidebarScrim" onclick="closeSidebarMobile()"></div>
<div class="app-layout">
<aside class="session-sidebar" id="sessionSidebar" aria-label="Chat sessions">
  <div class="session-sidebar-inner">
    <button type="button" class="new-chat-sidebar" onclick="newChat()">New Chat</button>
    <div class="session-list" id="sessionList"></div>
  </div>
</aside>
<div class="main-column">
<div class="header">
  <button type="button" class="sidebar-toggle" id="sidebarToggle" onclick="toggleSidebar()" title="Sessions">&#9776;</button>
  <h1>Jarvis</h1>
  <span class="status" id="status">checking...</span>
  <select class="model-select" id="modelSelect" onchange="switchModel(this.value)" title="Switch LLM model">
    <option value="qwen3.5:4b">qwen3.5:4b (default)</option>
    <option value="qwen3-vl:8b">qwen3-vl:8b (vision)</option>
    <option value="qwen3:1.7b">qwen3:1.7b (fast)</option>
  </select>
  <button type="button" id="btnGlobalSettings" onclick="openGlobalSettings()" title="Global Settings"
    style="background:none;border:1px solid #3a3d4a;color:#a0a4b8;border-radius:6px;padding:4px 8px;cursor:pointer;font-size:1em;margin-left:6px">&#9881;</button>
</div>

<!-- Global Settings Modal -->
<div id="globalSettingsModal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;justify-content:center;align-items:center">
  <div style="background:#1a1d2e;border:1px solid #2a2d3e;border-radius:12px;padding:24px;width:440px;max-width:90vw;max-height:90vh;overflow-y:auto">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0;color:#e0e0e0;font-size:1.1em">&#9881; Global Settings</h3>
      <button onclick="closeGlobalSettings()" style="background:none;border:none;color:#8b8fa4;font-size:1.3em;cursor:pointer">&times;</button>
    </div>
    <div style="margin-bottom:16px">
      <div style="color:#8b8fa4;font-size:0.78em;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px">Audio Language / 音频语言</div>
      <div style="display:flex;flex-direction:column;gap:10px">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:#0f1117;border-radius:6px;border:1px solid #2a2d3e">
          <span style="font-size:0.88em;color:#e0e0e0">&#127911; AI Briefing</span>
          <select id="settAudioAi" style="background:#1a1d2e;color:#a0a4b8;border:1px solid #3a3d4a;border-radius:4px;padding:4px 8px;font-size:0.85em">
            <option value="zh">中文</option><option value="en">English</option>
          </select>
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:#0f1117;border-radius:6px;border:1px solid #2a2d3e">
          <span style="font-size:0.88em;color:#e0e0e0">&#127758; World News</span>
          <select id="settAudioWorld" style="background:#1a1d2e;color:#a0a4b8;border:1px solid #3a3d4a;border-radius:4px;padding:4px 8px;font-size:0.85em">
            <option value="zh">中文</option><option value="en">English</option>
          </select>
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:#0f1117;border-radius:6px;border:1px solid #2a2d3e">
          <span style="font-size:0.88em;color:#e0e0e0">&#127464;&#127475; 中国新闻</span>
          <select id="settAudioChina" style="background:#1a1d2e;color:#a0a4b8;border:1px solid #3a3d4a;border-radius:4px;padding:4px 8px;font-size:0.85em">
            <option value="zh">中文</option><option value="en">English</option>
          </select>
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:#0f1117;border-radius:6px;border:1px solid #2a2d3e">
          <span style="font-size:0.88em;color:#e0e0e0">&#128214; Knowledge Audio</span>
          <select id="settAudioKnowledge" style="background:#1a1d2e;color:#a0a4b8;border:1px solid #3a3d4a;border-radius:4px;padding:4px 8px;font-size:0.85em">
            <option value="zh">中文</option><option value="en">English</option>
          </select>
        </div>
      </div>
    </div>
    <hr style="border:none;border-top:1px solid #2a2d3e;margin:16px 0">
    <div style="margin-bottom:16px">
      <div style="color:#8b8fa4;font-size:0.78em;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px">API Keys</div>
      <div style="display:flex;flex-direction:column;gap:10px">
        <div style="padding:10px 12px;background:#0f1117;border-radius:6px;border:1px solid #2a2d3e">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
            <span style="font-size:0.88em;color:#e0e0e0">&#128273; DeepSeek API</span>
            <span id="dsKeyStatus" style="font-size:0.72em;padding:2px 6px;border-radius:4px;background:#1e293b;color:#8b8fa4"></span>
          </div>
          <div style="display:flex;gap:6px">
            <input id="settDeepseekKey" type="password" placeholder="sk-..."
              style="flex:1;background:#1a1d2e;color:#e0e0e0;border:1px solid #3a3d4a;border-radius:4px;padding:6px 10px;font-size:0.82em;font-family:monospace">
            <button onclick="toggleDsKeyVisibility()" title="Show/Hide"
              style="background:#2a2d3e;color:#a0a4b8;border:none;border-radius:4px;padding:4px 8px;cursor:pointer;font-size:0.85em">&#128065;</button>
          </div>
          <div style="display:flex;gap:6px;margin-top:8px">
            <button onclick="saveDsKey()" style="background:#10b981;color:white;border:none;border-radius:4px;padding:5px 12px;cursor:pointer;font-size:0.78em">Save Key</button>
            <button onclick="testDsKey()" id="btnTestDs" style="background:#3b82f6;color:white;border:none;border-radius:4px;padding:5px 12px;cursor:pointer;font-size:0.78em">&#9889; Test</button>
            <button onclick="clearDsKey()" style="background:#374151;color:#f87171;border:none;border-radius:4px;padding:5px 12px;cursor:pointer;font-size:0.78em">Clear</button>
          </div>
          <div id="dsTestResult" style="margin-top:8px;font-size:0.78em;color:#8b8fa4;display:none"></div>
        </div>
      </div>
    </div>
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px">
      <button onclick="closeGlobalSettings()" style="background:#2a2d3e;color:#a0a4b8;border:none;border-radius:6px;padding:8px 16px;cursor:pointer;font-size:0.85em">Cancel</button>
      <button onclick="saveGlobalSettings()" style="background:#3b82f6;color:white;border:none;border-radius:6px;padding:8px 16px;cursor:pointer;font-size:0.85em">Save</button>
    </div>
  </div>
</div>
<div class="agent-toolbar" id="agentToolbar" aria-label="Quick actions">
  <div class="toolbar-inner">
    <div class="toolbar-cat" id="toolbarCatMedavis">
      <button type="button" class="toolbar-cat-header" onclick="toggleToolbarCat('toolbarCatMedavis')">
        <span>Medavis</span><span class="toolbar-cat-chevron">&#9660;</span>
      </button>
      <div class="toolbar-cat-body">
        <button type="button" class="toolbar-btn" id="btnWikiFetch" onclick="openWikiFetchModal()" title="Fetch wiki pages for team members">&#8983; Wiki Fetch</button>
        <button type="button" class="toolbar-btn" id="btnJiraDaily" onclick="toolbarJiraDaily(this)" title="Jira daily report">&#9776; Jira Daily</button>
        <button type="button" class="toolbar-btn" onclick="openCommitSummaryModal()" title="Ask the agent for commit summary">&#9998; Commit Summary</button>
        <button type="button" class="toolbar-btn" onclick="openTeamActivityModal()" title="Team activity query">&#9673; Team Activity</button>
      </div>
    </div>
    <div class="toolbar-cat" id="toolbarCatUsage">
      <button type="button" class="toolbar-cat-header" onclick="toggleToolbarCat('toolbarCatUsage')">
        <span>Usage Tools</span><span class="toolbar-cat-chevron">&#9660;</span>
      </button>
      <div class="toolbar-cat-body">
        <button type="button" class="toolbar-btn" onclick="openAudioKnowledgeModal()" title="Generate audio from knowledge base">&#9834; Audio from Knowledge</button>
        <button type="button" class="toolbar-btn" onclick="openExplainThisModal()" title="Deep-dive explanation of any AI/tech topic">&#128218; Explain This</button>
      </div>
    </div>
    <div class="toolbar-cat" id="toolbarCatAnalysis">
      <button type="button" class="toolbar-cat-header" onclick="toggleToolbarCat('toolbarCatAnalysis')">
        <span>Data Analysis</span><span class="toolbar-cat-chevron">&#9660;</span>
      </button>
      <div class="toolbar-cat-body">
        <button type="button" class="toolbar-btn" onclick="openTrendAnalysis()" title="Analyze trends from RAG data with AI predictions">&#128200; Trend Analysis</button>
        <button type="button" class="toolbar-btn" onclick="openAiNewsKB()" title="AI News knowledge base: categorize, track, and learn">&#129302; AI News KB</button>
      </div>
    </div>
    <div class="toolbar-cat" id="toolbarCatPersonal">
      <button type="button" class="toolbar-cat-header" onclick="toggleToolbarCat('toolbarCatPersonal')">
        <span>Personal</span><span class="toolbar-cat-chevron">&#9660;</span>
      </button>
      <div class="toolbar-cat-body">
        <button type="button" class="toolbar-btn" onclick="openDonorAnalysis()" title="Analyze and score donor profiles">&#128300; Donor Analysis</button>
        <button type="button" class="toolbar-btn" id="btnDailyFetch" onclick="openDailyFetchModal()" title="Run full daily briefing pipeline + commit report + Jira daily">&#128240; Daily Fetch</button>
      </div>
    </div>
    <div class="toolbar-cat" id="toolbarCatLearning">
      <button type="button" class="toolbar-cat-header" onclick="toggleToolbarCat('toolbarCatLearning')">
        <span>Learning</span><span class="toolbar-cat-chevron">&#9660;</span>
      </button>
      <div class="toolbar-cat-body">
        <button type="button" class="toolbar-btn" onclick="openAILearning()" title="AI/RAG/LLM learning with roadmap and deep-dive lessons">&#127891; AI Learning</button>
        <button type="button" class="toolbar-btn" onclick="openEnglishLearning()" title="Tech English learning from AI news: phrases, demos, corrections">&#128187; Tech English</button>
        <button type="button" class="toolbar-btn" onclick="openCasualEnglish()" title="Casual English learning from world news: daily conversation, idioms">&#127758; Casual English</button>
        <button type="button" class="toolbar-btn" onclick="openAWSCert()" title="AWS Certified AI Practitioner (AIF-C01) exam preparation: teach &amp; quiz modes">&#127942; AWS AIF-C01</button>
        <button type="button" class="toolbar-btn" onclick="toggleNotesPanel()" title="View and manage your saved learning notes">&#128221; My Notes</button>
      </div>
    </div>
    <div class="toolbar-cat" id="toolbarCatStock">
      <button type="button" class="toolbar-cat-header" onclick="toggleToolbarCat('toolbarCatStock')">
        <span>Stock</span><span class="toolbar-cat-chevron">&#9660;</span>
      </button>
      <div class="toolbar-cat-body">
        <button type="button" class="toolbar-btn" onclick="openStockModal()" title="A股个股分析与AI预测">&#128200; 股票分析</button>
        <button type="button" class="toolbar-btn" onclick="openWatchlistModal()" title="管理自选股列表">&#11088; 自选股</button>
        <button type="button" class="toolbar-btn" onclick="openScannerModal()" title="AI全市场扫描推荐TOP5">&#127775; AI推荐</button>
        <button type="button" class="toolbar-btn" onclick="openPriceTrainModal()" title="明日价格预测训练 (自选股)">&#127919; 价格预测</button>
        <button type="button" class="toolbar-btn" onclick="openNationalTeamModal()" title="国家队ETF份额监控 (汇金/社保等)">&#127961; 国家队</button>
      </div>
    </div>
  </div>
</div>

<div class="notes-panel" id="notesPanel">
  <div class="notes-header">
    <h3>&#128221; My Learning Notes</h3>
    <button onclick="toggleNotesPanel()" style="background:none;border:none;color:#999;font-size:1.3em;cursor:pointer">&times;</button>
  </div>
  <div style="padding:8px 16px;border-bottom:1px solid #2a2d3a">
    <select id="notesFilter" onchange="loadNotes()" style="width:100%;padding:6px;background:#1a1d2e;color:#c0c0c0;border:1px solid #3a3d5a;border-radius:4px">
      <option value="">All Notes</option>
      <option value="ai_learning">AI Learning</option>
      <option value="tech_english">Tech English</option>
      <option value="casual_english">Casual English</option>
      <option value="general">General</option>
    </select>
  </div>
  <div class="notes-body" id="notesBody"></div>
</div>
<div class="chat-area" id="chat"></div>
<div class="input-area">
  <div class="img-preview" id="imgPreview" style="display:none">
    <img id="imgThumb">
    <button class="remove" onclick="removeImage()">&times;</button>
  </div>
  <div class="input-row">
    <button class="img-btn" id="imgBtn" onclick="document.getElementById('imgInput').click()" title="Upload image">&#128247;</button>
    <input type="file" id="imgInput" accept="image/*" style="display:none" onchange="handleImage(this)">
    <textarea id="queryInput" placeholder="Ask anything... (Enter to send, Shift+Enter for newline)"
              rows="1" autofocus></textarea>
    <button class="send-btn" id="sendBtn" onclick="sendMessage()">Send</button>
  </div>
  </div>
</div>
</div>

<div id="toastContainer" class="toast-container" aria-live="polite"></div>

<div id="wikiFetchModal" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="wikiFetchModalTitle">
  <div class="modal-panel" style="max-width:420px">
    <div class="modal-head">
      <h2 id="wikiFetchModalTitle">Wiki Fetch &#8212; Select Team Members</h2>
      <button type="button" class="modal-close" onclick="closeWikiFetchModal()" title="Close">&times;</button>
    </div>
    <div class="modal-content" style="padding:16px 20px">
      <p style="font-size:0.82em;color:#8b8fa4;margin-bottom:12px">Select users whose Confluence wiki pages to fetch and index into RAG:</p>
      <div id="wikiFetchUserList" style="display:flex;flex-direction:column;gap:8px">
        <label class="wiki-user-check"><input type="checkbox" value="Rong Yin" checked> Rong Yin</label>
        <label class="wiki-user-check"><input type="checkbox" value="Raymond Shen"> Raymond Shen</label>
        <label class="wiki-user-check"><input type="checkbox" value="Charlotte Jiang"> Charlotte Jiang</label>
        <label class="wiki-user-check"><input type="checkbox" value="Christoph Scheben"> Christoph Scheben</label>
        <label class="wiki-user-check"><input type="checkbox" value="Tobias Troesch"> Tobias Troesch</label>
        <label class="wiki-user-check"><input type="checkbox" value="Jan Loeffler"> Jan Loeffler (CTO)</label>
        <label class="wiki-user-check"><input type="checkbox" value="Belen Liu"> Belen Liu</label>
        <label class="wiki-user-check"><input type="checkbox" value="Eason Li"> Eason Li</label>
        <label class="wiki-user-check"><input type="checkbox" value="Johnny Yang"> Johnny Yang</label>
      </div>
      <div style="margin-top:14px;display:flex;gap:12px;align-items:center">
        <label style="font-size:0.82em;color:#8b8fa4">From:</label>
        <input type="date" id="wikiFetchDateFrom" style="background:#1e2030;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:4px 8px;font-size:0.82em">
        <label style="font-size:0.82em;color:#8b8fa4">To:</label>
        <input type="date" id="wikiFetchDateTo" style="background:#1e2030;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:4px 8px;font-size:0.82em">
      </div>
      <div style="display:flex;gap:10px;margin-top:16px;justify-content:flex-end">
        <button type="button" class="toolbar-btn" onclick="wikiFetchSelectAll()" style="font-size:0.78em">Select All</button>
        <button type="button" class="toolbar-btn" onclick="wikiFetchSelectNone()" style="font-size:0.78em">None</button>
        <button type="button" class="send-btn" id="wikiFetchStartBtn" onclick="startWikiFetch()" style="padding:8px 20px;font-size:0.88em">Fetch Selected</button>
      </div>
    </div>
  </div>
</div>

<div id="commitSummaryModal" class="modal-overlay" role="dialog" aria-modal="true">
  <div class="modal-panel" style="max-width:440px">
    <div class="modal-head">
      <h2>Commit Summary &#8212; Options</h2>
      <button type="button" class="modal-close" onclick="closeCommitSummaryModal()" title="Close">&times;</button>
    </div>
    <div class="modal-content" style="padding:16px 20px">
      <p style="font-size:0.82em;color:#8b8fa4;margin-bottom:12px">Select team members and date range for the commit summary:</p>
      <div id="commitMemberList" style="display:flex;flex-direction:column;gap:8px">
        <label class="wiki-user-check"><input type="checkbox" value="Rong Yin" checked> Rong Yin</label>
        <label class="wiki-user-check"><input type="checkbox" value="Raymond Shen" checked> Raymond Shen</label>
        <label class="wiki-user-check"><input type="checkbox" value="Charlotte Jiang" checked> Charlotte Jiang</label>
        <label class="wiki-user-check"><input type="checkbox" value="Christoph Scheben" checked> Christoph Scheben</label>
        <label class="wiki-user-check"><input type="checkbox" value="Tobias Troesch" checked> Tobias Troesch</label>
        <label class="wiki-user-check"><input type="checkbox" value="Jan Loeffler"> Jan Loeffler (CTO)</label>
        <label class="wiki-user-check"><input type="checkbox" value="Belen Liu" checked> Belen Liu</label>
        <label class="wiki-user-check"><input type="checkbox" value="Eason Li" checked> Eason Li</label>
        <label class="wiki-user-check"><input type="checkbox" value="Johnny Yang" checked> Johnny Yang</label>
      </div>
      <div style="margin-top:14px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <label style="font-size:0.82em;color:#8b8fa4">From:</label>
        <input type="date" id="commitDateFrom" style="background:#1e2030;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:4px 8px;font-size:0.82em">
        <label style="font-size:0.82em;color:#8b8fa4">To:</label>
        <input type="date" id="commitDateTo" style="background:#1e2030;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:4px 8px;font-size:0.82em">
      </div>
      <div style="display:flex;gap:10px;margin-top:16px;justify-content:flex-end">
        <button type="button" class="toolbar-btn" onclick="modalSelectAll('commitMemberList')" style="font-size:0.78em">Select All</button>
        <button type="button" class="toolbar-btn" onclick="modalSelectNone('commitMemberList')" style="font-size:0.78em">None</button>
        <button type="button" class="send-btn" onclick="startCommitSummary()" style="padding:8px 20px;font-size:0.88em">Generate Summary</button>
      </div>
    </div>
  </div>
</div>

<div id="teamActivityModal" class="modal-overlay" role="dialog" aria-modal="true">
  <div class="modal-panel" style="max-width:440px">
    <div class="modal-head">
      <h2>Team Activity &#8212; Options</h2>
      <button type="button" class="modal-close" onclick="closeTeamActivityModal()" title="Close">&times;</button>
    </div>
    <div class="modal-content" style="padding:16px 20px">
      <p style="font-size:0.82em;color:#8b8fa4;margin-bottom:12px">Select team members and date range for the activity report:</p>
      <div id="activityMemberList" style="display:flex;flex-direction:column;gap:8px">
        <label class="wiki-user-check"><input type="checkbox" value="Rong Yin" checked> Rong Yin</label>
        <label class="wiki-user-check"><input type="checkbox" value="Raymond Shen" checked> Raymond Shen</label>
        <label class="wiki-user-check"><input type="checkbox" value="Charlotte Jiang" checked> Charlotte Jiang</label>
        <label class="wiki-user-check"><input type="checkbox" value="Christoph Scheben" checked> Christoph Scheben</label>
        <label class="wiki-user-check"><input type="checkbox" value="Tobias Troesch" checked> Tobias Troesch</label>
        <label class="wiki-user-check"><input type="checkbox" value="Jan Loeffler"> Jan Loeffler (CTO)</label>
        <label class="wiki-user-check"><input type="checkbox" value="Belen Liu" checked> Belen Liu</label>
        <label class="wiki-user-check"><input type="checkbox" value="Eason Li" checked> Eason Li</label>
        <label class="wiki-user-check"><input type="checkbox" value="Johnny Yang" checked> Johnny Yang</label>
      </div>
      <div style="margin-top:14px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <label style="font-size:0.82em;color:#8b8fa4">From:</label>
        <input type="date" id="activityDateFrom" style="background:#1e2030;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:4px 8px;font-size:0.82em">
        <label style="font-size:0.82em;color:#8b8fa4">To:</label>
        <input type="date" id="activityDateTo" style="background:#1e2030;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:4px 8px;font-size:0.82em">
      </div>
      <div style="display:flex;gap:10px;margin-top:16px;justify-content:flex-end">
        <button type="button" class="toolbar-btn" onclick="modalSelectAll('activityMemberList')" style="font-size:0.78em">Select All</button>
        <button type="button" class="toolbar-btn" onclick="modalSelectNone('activityMemberList')" style="font-size:0.78em">None</button>
        <button type="button" class="send-btn" onclick="startTeamActivity()" style="padding:8px 20px;font-size:0.88em">Generate Report</button>
      </div>
    </div>
  </div>
</div>

<div id="audioKnowledgeModal" class="modal-overlay" role="dialog" aria-modal="true">
  <div class="modal-panel" style="max-width:520px">
    <div class="modal-head">
      <h2>&#9834; Audio from Knowledge</h2>
      <button type="button" class="modal-close" onclick="closeAudioKnowledgeModal()" title="Close">&times;</button>
    </div>
    <div class="modal-content" style="padding:16px 20px">

      <!-- Step 1: Pick source type + history -->
      <div id="audioStep1">
        <p style="font-size:0.82em;color:#8b8fa4;margin-bottom:12px">Step 1: Choose a content source</p>
        <div id="audioSourceTypeList" style="display:flex;flex-direction:column;gap:8px">
          <label class="wiki-user-check" style="padding:8px 12px;border-radius:8px;cursor:pointer"><input type="radio" name="audioSourceType" value="news_item" style="accent-color:#4a6cf7"> AI Briefings / News</label>
          <label class="wiki-user-check" style="padding:8px 12px;border-radius:8px;cursor:pointer"><input type="radio" name="audioSourceType" value="raw_content" style="accent-color:#4a6cf7"> Raw Articles</label>
          <label class="wiki-user-check" style="padding:8px 12px;border-radius:8px;cursor:pointer"><input type="radio" name="audioSourceType" value="wiki_page" style="accent-color:#4a6cf7"> Wiki Pages</label>
          <label class="wiki-user-check" style="padding:8px 12px;border-radius:8px;cursor:pointer"><input type="radio" name="audioSourceType" value="code_doc" style="accent-color:#4a6cf7"> Code Documentation</label>
          <label class="wiki-user-check" style="padding:8px 12px;border-radius:8px;cursor:pointer"><input type="radio" name="audioSourceType" value="book_chapter" style="accent-color:#4a6cf7"> Books / Learning</label>
          <label class="wiki-user-check" style="padding:8px 12px;border-radius:8px;cursor:pointer"><input type="radio" name="audioSourceType" value="project_doc" style="accent-color:#4a6cf7"> Project Docs</label>
        </div>
        <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:16px">
          <button type="button" class="toolbar-btn" onclick="closeAudioKnowledgeModal()" style="font-size:0.78em">Cancel</button>
          <button type="button" class="send-btn" id="btnAudioNext" onclick="audioStepNext()" style="padding:8px 20px;font-size:0.88em">Next &#8594;</button>
        </div>
        <div id="audioHistorySection" style="margin-top:18px;border-top:1px solid #2a2d3a;padding-top:14px;display:none">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap">
            <p style="font-size:0.82em;color:#8b8fa4;margin:0">&#128266; Previously generated audio:</p>
            <input type="date" id="audioHistoryDate" style="background:#1e2030;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:3px 6px;font-size:0.78em" onchange="_filterAudioHistory()">
            <button type="button" class="toolbar-btn" onclick="document.getElementById('audioHistoryDate').value='';_filterAudioHistory()" style="font-size:0.70em;padding:2px 6px">All</button>
          </div>
          <div id="audioHistoryList" style="max-height:200px;overflow-y:auto;display:flex;flex-direction:column;gap:6px"></div>
        </div>
      </div>

      <!-- Step 2: Pick items -->
      <div id="audioStep2" style="display:none">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
          <button type="button" class="toolbar-btn" onclick="audioStepBack()" style="font-size:0.78em;padding:4px 10px">&#8592; Back</button>
          <p style="font-size:0.82em;color:#8b8fa4;margin:0">Step 2: Select items from <strong id="audioStep2TypeLabel"></strong></p>
        </div>
        <div id="audioItemsLoading" style="display:flex;align-items:center;gap:8px;padding:12px 0">
          <div class="mini-spin" style="width:14px;height:14px;border:2px solid #3a3d5a;border-top-color:#60a5fa;border-radius:50%;animation:spin .8s linear infinite"></div>
          <span style="font-size:0.82em;color:#9ca3af">Loading items...</span>
        </div>
        <div id="audioItemsContainer" style="display:none">
          <div style="display:flex;gap:8px;margin-bottom:8px">
            <button type="button" class="toolbar-btn" onclick="audioSelectAll()" style="font-size:0.72em;padding:3px 8px">Select All</button>
            <button type="button" class="toolbar-btn" onclick="audioSelectNone()" style="font-size:0.72em;padding:3px 8px">Select None</button>
            <span id="audioItemCount" style="font-size:0.72em;color:#6b7280;margin-left:auto;align-self:center"></span>
          </div>
          <div id="audioItemsList" style="max-height:280px;overflow-y:auto;display:flex;flex-direction:column;gap:4px;padding-right:4px"></div>
        </div>
        <div style="margin-top:12px;margin-bottom:14px;display:flex;gap:12px;align-items:center">
          <label style="font-size:0.82em;color:#8b8fa4">Language:</label>
          <select id="audioLanguage" style="background:#1e2030;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:4px 8px;font-size:0.82em">
            <option value="zh" selected>Chinese (&#20013;&#25991;)</option>
            <option value="en">English</option>
          </select>
        </div>
        <div style="display:flex;gap:10px;justify-content:flex-end">
          <button type="button" class="toolbar-btn" onclick="closeAudioKnowledgeModal()" style="font-size:0.78em">Cancel</button>
          <button type="button" class="send-btn" id="btnGenerateAudio" onclick="startAudioKnowledge()" style="padding:8px 20px;font-size:0.88em">&#9834; Generate Audio</button>
        </div>
        <div id="audioProgress" style="display:none;margin-top:14px;padding:12px;background:#1a1d28;border:1px dashed #3a4555;border-radius:8px">
          <div style="display:flex;align-items:center;gap:8px">
            <div class="mini-spin" style="width:14px;height:14px;border:2px solid #3a3d5a;border-top-color:#60a5fa;border-radius:50%;animation:spin .8s linear infinite"></div>
            <span id="audioProgressText" style="font-size:0.82em;color:#9ca3af">Starting...</span>
          </div>
          <div id="audioResult" style="display:none;margin-top:10px"></div>
        </div>
      </div>

    </div>
  </div>
</div>

<div id="explainThisModal" class="modal-overlay" role="dialog" aria-modal="true">
  <div class="modal-panel" style="max-width:460px">
    <div class="modal-head">
      <h2>&#128218; Explain This &#8212; Deep Dive</h2>
      <button type="button" class="modal-close" onclick="closeExplainThisModal()" title="Close">&times;</button>
    </div>
    <div class="modal-content" style="padding:16px 20px">
      <p style="font-size:0.82em;color:#8b8fa4;margin-bottom:12px">Enter a topic from AI news or tech. Jarvis will search the knowledge base and the web to give you an in-depth explanation.</p>
      <div style="margin-bottom:14px">
        <label style="font-size:0.82em;color:#8b8fa4;display:block;margin-bottom:6px">Topic to explain:</label>
        <input type="text" id="explainTopic" placeholder="e.g. LoRA fine-tuning, RLHF, attention mechanism, FHIR R4..."
               style="width:100%;background:#1e2030;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:10px 14px;font-size:0.92em;box-sizing:border-box">
      </div>
      <div style="margin-bottom:14px">
        <label style="font-size:0.82em;color:#8b8fa4;display:block;margin-bottom:6px">Depth:</label>
        <div style="display:flex;gap:10px">
          <label class="wiki-user-check" style="flex:1;justify-content:center"><input type="radio" name="explainDepth" value="quick" style="accent-color:#4a6cf7"> Quick (2-3 min read)</label>
          <label class="wiki-user-check" style="flex:1;justify-content:center"><input type="radio" name="explainDepth" value="deep" checked style="accent-color:#4a6cf7"> Deep Dive (5-10 min)</label>
        </div>
      </div>
      <div style="margin-bottom:14px">
        <label class="wiki-user-check"><input type="checkbox" id="explainWebSearch" checked> Also search the web for latest information</label>
      </div>
      <div style="display:flex;gap:10px;justify-content:flex-end">
        <button type="button" class="toolbar-btn" onclick="closeExplainThisModal()" style="font-size:0.78em">Cancel</button>
        <button type="button" class="send-btn" onclick="startExplainThis()" style="padding:8px 20px;font-size:0.88em">&#128218; Explain</button>
      </div>
    </div>
  </div>
</div>

<div id="donorAnalysisModal" class="modal-overlay" role="dialog" aria-modal="true">
  <div class="modal-panel" style="max-width:95vw;max-height:90vh;width:1100px">
    <div class="modal-head">
      <h2>&#128300; Donor Analysis</h2>
      <button type="button" class="modal-close" onclick="closeDonorAnalysis()" title="Close">&times;</button>
    </div>
    <div class="modal-content" style="padding:12px 16px">
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:10px">
        <label style="font-size:0.82em;color:#8b8fa4">Recipient CMV:</label>
        <select id="donorCmvFilter" style="background:#1e2030;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:4px 8px;font-size:0.82em">
          <option value="negative">Negative</option>
          <option value="positive">Positive</option>
        </select>
        <button type="button" class="send-btn" id="btnDonorLoad" onclick="loadDonorAnalysis()" style="padding:6px 16px;font-size:0.82em">Load &amp; Score</button>
        <button type="button" class="toolbar-btn" id="btnDonorTop10" onclick="donorTop10()" style="font-size:0.78em" disabled>Top 20 + AI Reasoning</button>
        <label style="font-size:0.82em;color:#8b8fa4">PDF Lang:</label>
        <select id="donorPdfLang" style="background:#1e2030;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:4px 8px;font-size:0.82em">
          <option value="en">English</option>
          <option value="zh">Chinese</option>
        </select>
        <button type="button" class="toolbar-btn" id="btnDonorPdf" onclick="donorExportPdf()" style="font-size:0.78em" disabled>Export PDF</button>
        <span id="donorCount" style="font-size:0.78em;color:#8b8fa4"></span>
      </div>
      <div id="donorTableWrap" style="max-height:65vh;overflow:auto">
        <p style="font-size:0.82em;color:#8b8fa4">Click "Load &amp; Score" to analyze donor profiles.</p>
      </div>
      <div id="donorTop10Result" style="display:none;margin-top:12px;padding:12px;background:#1e2030;border-radius:8px;max-height:30vh;overflow-y:auto;font-size:0.82em;white-space:pre-wrap;color:#c4c8f0"></div>
    </div>
  </div>
</div>

<div id="dailyFetchModal" class="modal-overlay" role="dialog" aria-modal="true">
  <div class="modal-panel" style="max-width:620px">
    <div class="modal-head">
      <h2>&#128240; Daily Fetch</h2>
      <button type="button" class="modal-close" onclick="closeDailyFetchModal()" title="Close">&times;</button>
    </div>
    <div class="modal-content" style="padding:16px 20px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap">
        <span style="font-size:0.82em;color:#8b8fa4">Browse date:</span>
        <input type="date" id="dfHistoryDate" style="background:#1e2030;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:4px 8px;font-size:0.82em" onchange="loadDailyFetchHistory(this.value)">
        <button type="button" class="toolbar-btn" id="dfPrevDay" onclick="dfNavDay(-1)" style="font-size:0.75em;padding:3px 8px">&larr; Prev</button>
        <button type="button" class="toolbar-btn" id="dfNextDay" onclick="dfNavDay(1)" style="font-size:0.75em;padding:3px 8px">Next &rarr;</button>
        <span id="dfDateLabel" style="font-size:0.88em;font-weight:600;color:#c4c8f0"></span>
      </div>
      <div id="dfHistoryContent" style="min-height:120px">
        <p style="font-size:0.82em;color:#6b7280">Loading...</p>
      </div>
      <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:16px;border-top:1px solid #2a2d3a;padding-top:14px;align-items:center">
        <button type="button" class="toolbar-btn" onclick="closeDailyFetchModal()" style="font-size:0.78em">Close</button>
        <button type="button" class="send-btn" id="btnContinueDailyFetch" onclick="continueDailyFetchFromModal()" style="padding:8px 16px;font-size:0.85em;display:none;background:#d97706;border-color:#d97706">&#9654; Continue</button>
        <button type="button" class="send-btn" id="btnRunDailyFetch" onclick="runDailyFetchFromModal()" style="padding:8px 20px;font-size:0.88em">&#9654; Run Today's Fetch</button>
      </div>
      <div id="dfRunProgress" style="display:none;margin-top:14px;padding:12px;background:#1a1d28;border:1px dashed #3a4555;border-radius:8px">
        <div style="display:flex;align-items:center;gap:8px">
          <span class="mini-spin" style="display:inline-block;width:16px;height:16px;border:2px solid #4a6cf7;border-top-color:transparent;border-radius:50%;animation:spin 1s linear infinite"></span>
          <span id="dfRunProgressText" style="font-size:0.82em;color:#c4c8f0">Starting...</span>
        </div>
      </div>
    </div>
  </div>
</div>

<div id="trendAnalysisModal" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="trendAnalysisModalTitle">
  <div class="modal-panel" style="max-width:95vw;max-height:92vh;width:960px;background:#0f1117;border:1px solid #2a2d3e">
    <div class="modal-head" style="border-bottom:1px solid #2a2d3e">
      <h2 id="trendAnalysisModalTitle">&#128200; Trend Analysis</h2>
      <button type="button" class="modal-close" onclick="closeTrendAnalysis()" title="Close">&times;</button>
    </div>
    <div class="modal-content" style="padding:14px 18px;background:#0f1117">
      <p style="font-size:0.82em;color:#8b8fa4;margin-bottom:12px">Select categories and a date window. Data comes from the RAG store (filtered by item type and date), commit reports under the reports directory, and Atlassian daily markdown when Jira is selected.</p>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start">
        <div style="background:#1a1d2e;border:1px solid #2a2d3e;border-radius:8px;padding:12px">
          <div style="font-size:0.78em;color:#60a5fa;margin-bottom:8px;font-weight:600">Categories</div>
          <div id="trendCategoryList" style="display:flex;flex-direction:column;gap:6px">
            <label class="wiki-user-check"><input type="checkbox" id="taCatAiNews" value="ai_news" checked> AI News</label>
            <label class="wiki-user-check"><input type="checkbox" id="taCatWorldNews" value="world_news" checked> World News</label>
            <label class="wiki-user-check"><input type="checkbox" id="taCatCommits" value="commits" checked> Commits</label>
            <label class="wiki-user-check"><input type="checkbox" id="taCatJira" value="jira" checked> Jira <span style="color:#6b7280;font-size:0.9em">(per-person items in RAG + reports)</span></label>
            <label class="wiki-user-check"><input type="checkbox" id="taCatWiki" value="wiki" checked> Wiki Pages</label>
          </div>
        </div>
        <div style="background:#1a1d2e;border:1px solid #2a2d3e;border-radius:8px;padding:12px">
          <div style="font-size:0.78em;color:#60a5fa;margin-bottom:8px;font-weight:600">Date range</div>
          <label class="wiki-user-check" style="display:block;margin-bottom:6px"><input type="radio" name="trendDays" id="taDays7" value="7" checked style="accent-color:#4a6cf7"> Last 7 days</label>
          <label class="wiki-user-check" style="display:block;margin-bottom:6px"><input type="radio" name="trendDays" id="taDays14" value="14" style="accent-color:#4a6cf7"> Last 14 days</label>
          <label class="wiki-user-check" style="display:block"><input type="radio" name="trendDays" id="taDays30" value="30" style="accent-color:#4a6cf7"> Last 30 days</label>
        </div>
      </div>
      <div style="display:flex;gap:10px;margin-top:14px;align-items:center;flex-wrap:wrap">
        <button type="button" class="send-btn" id="btnTrendAnalyze" onclick="runTrendAnalysis()" style="padding:8px 20px;font-size:0.88em">Analyze</button>
        <span id="trendAnalysisStatus" style="font-size:0.78em;color:#8b8fa4"></span>
      </div>
      <div id="trendAnalysisResult" style="display:none;margin-top:14px;padding:14px;background:#1a1d2e;border:1px solid #2a2d3e;border-radius:8px;max-height:52vh;overflow-y:auto;font-size:0.84em;line-height:1.6;color:#c4c8f0"></div>
    </div>
  </div>
</div>

<div id="aiNewsKBModal" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="aiNewsKBTitle">
  <div class="modal-panel" style="max-width:96vw;max-height:94vh;width:1100px;background:#0f1117;border:1px solid #2a2d3e">
    <div class="modal-head" style="border-bottom:1px solid #2a2d3e">
      <h2 id="aiNewsKBTitle">&#129302; AI News Knowledge Base</h2>
      <button type="button" class="modal-close" onclick="closeAiNewsKB()" title="Close">&times;</button>
    </div>
    <div class="modal-content" style="padding:14px 18px;background:#0f1117">
      <p style="font-size:0.82em;color:#8b8fa4;margin-bottom:10px">Reads AI briefing PDFs, categorizes news items, and builds a persistent knowledge base. Each run merges new items with existing data so you can track topics over time.</p>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px">
        <button type="button" class="send-btn" id="btnAiKBScan" onclick="runAiNewsKBScan()" style="padding:8px 18px;font-size:0.86em">&#128269; Scan &amp; Update</button>
        <button type="button" class="toolbar-btn" id="btnAiKBSummary" onclick="runAiNewsKBSummary()" style="font-size:0.78em" disabled>&#9733; AI Summary</button>
        <span id="aiKBStatus" style="font-size:0.78em;color:#8b8fa4"></span>
        <span id="aiKBStats" style="font-size:0.78em;color:#60a5fa;margin-left:auto"></span>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:10px;align-items:center;flex-wrap:wrap">
        <input type="text" id="aiKBFilter" placeholder="Filter by keyword..." oninput="filterAiKBTable()" style="background:#1a1d2e;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:5px 10px;font-size:0.82em;width:200px">
        <select id="aiKBCatFilter" onchange="filterAiKBTable()" style="background:#1a1d2e;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:5px 8px;font-size:0.82em">
          <option value="">All Categories</option>
        </select>
        <select id="aiKBSourceFilter" onchange="filterAiKBTable()" style="background:#1a1d2e;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:5px 8px;font-size:0.82em">
          <option value="">All Sources</option>
        </select>
      </div>
      <div id="aiKBTableWrap" style="max-height:52vh;overflow-y:auto;border:1px solid #2a2d3e;border-radius:8px">
        <table style="width:100%;border-collapse:collapse;font-size:0.78em">
          <thead style="position:sticky;top:0;background:#1a1d2e;z-index:1">
            <tr>
              <th style="padding:6px 8px;text-align:left;color:#60a5fa;border-bottom:1px solid #2a2d3e;cursor:pointer" onclick="sortAiKBTable('date')">Date &#8597;</th>
              <th style="padding:6px 8px;text-align:left;color:#60a5fa;border-bottom:1px solid #2a2d3e;cursor:pointer" onclick="sortAiKBTable('category')">Category &#8597;</th>
              <th style="padding:6px 8px;text-align:left;color:#60a5fa;border-bottom:1px solid #2a2d3e;cursor:pointer" onclick="sortAiKBTable('source')">Source &#8597;</th>
              <th style="padding:6px 8px;text-align:left;color:#60a5fa;border-bottom:1px solid #2a2d3e">Title</th>
              <th style="padding:6px 8px;text-align:left;color:#60a5fa;border-bottom:1px solid #2a2d3e">Link</th>
            </tr>
          </thead>
          <tbody id="aiKBTableBody"></tbody>
        </table>
      </div>
      <div id="aiKBSummaryResult" style="display:none;margin-top:14px;padding:14px;background:#1a1d2e;border:1px solid #2a2d3e;border-radius:8px;max-height:40vh;overflow-y:auto;font-size:0.84em;line-height:1.6;color:#c4c8f0"></div>
    </div>
  </div>
</div>

<!-- Stock Analysis Modal -->
<div id="stockAnalysisModal" class="modal-overlay" role="dialog" aria-modal="true">
  <div class="modal-panel" style="max-width:96vw;max-height:94vh;width:900px;background:#0f1117;border:1px solid #2a2d3e">
    <div class="modal-head" style="border-bottom:1px solid #2a2d3e">
      <h2>&#128200; A股分析 &amp; AI预测</h2>
      <button type="button" class="modal-close" onclick="closeStockModal()" title="Close">&times;</button>
    </div>
    <div class="modal-content" style="padding:14px 18px;background:#0f1117">
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
        <input type="text" id="stockSymbolInput" placeholder="输入股票代码 (如 600519)" style="background:#1a1d2e;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:8px 12px;font-size:0.88em;width:180px">
        <button type="button" class="send-btn" id="btnStockAnalyze" onclick="runStockAnalysis()" style="padding:8px 18px;font-size:0.86em">&#128200; 全面分析</button>
        <button type="button" class="toolbar-btn" id="btnStockTech" onclick="runStockTech()" style="font-size:0.78em">技术分析</button>
        <button type="button" class="toolbar-btn" id="btnStockFund" onclick="runStockFund()" style="font-size:0.78em">基本面</button>
        <button type="button" class="toolbar-btn" id="btnStockSent" onclick="runStockSent()" style="font-size:0.78em">情绪分析</button>
        <button type="button" class="toolbar-btn" id="btnStockXGB" onclick="runStockXGB()" style="font-size:0.78em">ML预测</button>
        <button type="button" class="toolbar-btn" id="btnStockFF" onclick="runStockFF()" style="font-size:0.78em">&#128176; 聪明钱</button>
        <label style="display:flex;align-items:center;gap:4px;font-size:0.78em;color:#a0a4b8;cursor:pointer;margin-left:8px" title="同时使用 DeepSeek API 分析">
          <input type="checkbox" id="stockUseDeepseek" style="accent-color:#3b82f6">
          <span>&#128171; DeepSeek</span>
        </label>
        <span id="stockStatus" style="font-size:0.78em;color:#8b8fa4;margin-left:auto"></span>
      </div>
      <div id="stockResultTabs" style="display:none;margin-bottom:8px">
        <button onclick="showStockTab('local')" id="stockTabLocal" style="background:#3b82f6;color:white;border:none;border-radius:6px 6px 0 0;padding:6px 14px;font-size:0.82em;cursor:pointer">&#127968; 本地 Ollama</button>
        <button onclick="showStockTab('deepseek')" id="stockTabDs" style="background:#1e293b;color:#64748b;border:none;border-radius:6px 6px 0 0;padding:6px 14px;font-size:0.82em;cursor:pointer">&#128171; DeepSeek</button>
      </div>
      <div id="stockResult" style="max-height:65vh;overflow-y:auto;border:1px solid #2a2d3e;border-radius:8px;padding:14px;background:#1a1d2e;font-size:0.84em;line-height:1.6;color:#c4c8f0;white-space:pre-wrap">
        <p style="color:#6b7280">输入股票代码后点击"全面分析"开始。支持沪深A股代码。</p>
      </div>
      <div id="stockResultDs" style="display:none;max-height:65vh;overflow-y:auto;border:1px solid #1e3a5f;border-radius:8px;padding:14px;background:#0c1220;font-size:0.84em;line-height:1.6;color:#c4c8f0;white-space:pre-wrap"></div>
    </div>
  </div>
</div>

<!-- Watchlist Modal -->
<div id="watchlistModal" class="modal-overlay" role="dialog" aria-modal="true">
  <div class="modal-panel" style="max-width:96vw;max-height:94vh;width:800px;background:#0f1117;border:1px solid #2a2d3e">
    <div class="modal-head" style="border-bottom:1px solid #2a2d3e">
      <h2>&#11088; 自选股管理</h2>
      <button type="button" class="modal-close" onclick="closeWatchlistModal()" title="Close">&times;</button>
    </div>
    <div class="modal-content" style="padding:14px 18px;background:#0f1117">
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
        <input type="text" id="watchlistAddSymbol" placeholder="代码 (600519)" style="background:#1a1d2e;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:6px 10px;font-size:0.82em;width:100px">
        <input type="text" id="watchlistAddName" placeholder="名称 (贵州茅台)" style="background:#1a1d2e;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:6px 10px;font-size:0.82em;width:120px">
        <input type="text" id="watchlistAddSector" placeholder="行业" style="background:#1a1d2e;border:1px solid #3a3d4a;color:#c4c8f0;border-radius:6px;padding:6px 10px;font-size:0.82em;width:80px">
        <button type="button" class="send-btn" onclick="addToWatchlist()" style="padding:6px 14px;font-size:0.82em">+ 添加</button>
        <button type="button" class="toolbar-btn" onclick="refreshWatchlist()" style="font-size:0.78em">&#8635; 刷新数据</button>
        <span id="watchlistStatus" style="font-size:0.78em;color:#8b8fa4;margin-left:auto"></span>
      </div>
      <div id="watchlistTable" style="max-height:60vh;overflow-y:auto;border:1px solid #2a2d3e;border-radius:8px">
        <table style="width:100%;border-collapse:collapse;font-size:0.82em">
          <thead style="position:sticky;top:0;background:#1a1d2e;z-index:1">
            <tr>
              <th style="padding:6px 8px;text-align:left;color:#60a5fa;border-bottom:1px solid #2a2d3e">代码</th>
              <th style="padding:6px 8px;text-align:left;color:#60a5fa;border-bottom:1px solid #2a2d3e">名称</th>
              <th style="padding:6px 8px;text-align:right;color:#60a5fa;border-bottom:1px solid #2a2d3e">最新价</th>
              <th style="padding:6px 8px;text-align:right;color:#60a5fa;border-bottom:1px solid #2a2d3e">涨跌%</th>
              <th style="padding:6px 8px;text-align:left;color:#60a5fa;border-bottom:1px solid #2a2d3e">行业</th>
              <th style="padding:6px 8px;text-align:center;color:#60a5fa;border-bottom:1px solid #2a2d3e">操作</th>
            </tr>
          </thead>
          <tbody id="watchlistBody"></tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<!-- AI Scanner Modal -->
<div id="scannerModal" class="modal-overlay" role="dialog" aria-modal="true">
  <div class="modal-panel" style="max-width:96vw;max-height:94vh;width:950px;background:#0f1117;border:1px solid #2a2d3e">
    <div class="modal-head" style="border-bottom:1px solid #2a2d3e">
      <h2>&#127775; AI 股票推荐</h2>
      <button type="button" class="modal-close" onclick="closeScannerModal()" title="Close">&times;</button>
    </div>
    <div class="modal-content" style="padding:14px 18px;background:#0f1117">
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
        <button type="button" class="send-btn" id="btnScanStart" onclick="startScan()" style="padding:8px 18px;font-size:0.86em">&#127775; 开始扫描</button>
        <button type="button" class="toolbar-btn" id="btnScanStop" onclick="stopScan()" style="font-size:0.78em" disabled>&#9724; 停止</button>
        <button type="button" class="toolbar-btn" onclick="loadScanHistory()" style="font-size:0.78em">&#128203; 历史记录</button>
        <label style="display:flex;align-items:center;gap:4px;font-size:0.78em;color:#a0a4b8;cursor:pointer;margin-left:8px" title="Layer 3 使用 DeepSeek 判断 TOP 10（替代本地LLM，更科学）">
          <input type="checkbox" id="scanUseDeepseek" style="accent-color:#3b82f6">
          <span>&#128171; DeepSeek</span>
        </label>
        <span id="scanStatus" style="font-size:0.78em;color:#8b8fa4;margin-left:auto"></span>
      </div>
      <div id="scanProgress" style="display:none;margin-bottom:12px">
        <div style="background:#1a1d2e;border-radius:8px;overflow:hidden;height:24px;border:1px solid #2a2d3e">
          <div id="scanProgressBar" style="height:100%;background:linear-gradient(90deg,#3b82f6,#8b5cf6);transition:width 0.5s;width:0%;display:flex;align-items:center;justify-content:center">
            <span id="scanProgressText" style="font-size:0.72em;color:#fff;font-weight:600"></span>
          </div>
        </div>
        <div id="scanPhase" style="font-size:0.76em;color:#8b8fa4;margin-top:4px"></div>
      </div>
      <div id="scanResult" style="max-height:62vh;overflow-y:auto;border:1px solid #2a2d3e;border-radius:8px;padding:14px;background:#1a1d2e;font-size:0.84em;line-height:1.6;color:#c4c8f0">
        <p style="color:#6b7280">点击"开始扫描"启动AI全市场分析。扫描过程分3层：</p>
        <p style="color:#6b7280">1. 全市场快速筛选 → 2. 分批详细分析 → 3. LLM综合评分</p>
        <p style="color:#6b7280;font-size:0.9em;margin-top:8px">扫描过程中可以查看部分结果，中断后可继续。</p>
      </div>
    </div>
  </div>
</div>

<!-- Price Prediction Training Modal -->
<div id="priceTrainModal" class="modal-overlay" role="dialog" aria-modal="true">
  <div class="modal-panel" style="max-width:96vw;max-height:94vh;width:950px;background:#0f1117;border:1px solid #2a2d3e">
    <div class="modal-head" style="border-bottom:1px solid #2a2d3e">
      <h2>&#127919; 明日价格预测</h2>
      <button type="button" class="modal-close" onclick="closePriceTrainModal()" title="Close">&times;</button>
    </div>
    <div class="modal-content" style="padding:14px 18px;background:#0f1117">
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
        <button type="button" class="send-btn" id="btnTrainStart" onclick="startDailyTraining()" style="padding:8px 18px;font-size:0.86em">&#128640; 开始训练</button>
        <span id="trainStatus" style="font-size:0.78em;color:#8b8fa4;margin-left:auto"></span>
      </div>
      <div id="trainProgress" style="display:none;margin-bottom:12px">
        <div style="background:#1a1d2e;border-radius:8px;overflow:hidden;height:24px;border:1px solid #2a2d3e">
          <div id="trainProgressBar" style="height:100%;background:linear-gradient(90deg,#10b981,#3b82f6);transition:width 0.5s;width:0%;display:flex;align-items:center;justify-content:center">
            <span id="trainProgressText" style="font-size:0.72em;color:#fff;font-weight:600"></span>
          </div>
        </div>
        <div id="trainPhase" style="font-size:0.76em;color:#8b8fa4;margin-top:4px"></div>
      </div>
      <div id="trainResult" style="max-height:62vh;overflow-y:auto;border:1px solid #2a2d3e;border-radius:8px;padding:14px;background:#1a1d2e;font-size:0.84em;line-height:1.6;color:#c4c8f0">
        <p style="color:#6b7280">点击"开始训练"为自选股训练明日价格预测模型。</p>
        <p style="color:#6b7280">训练内容: 预测明日收盘价、最高价、最低价</p>
        <p style="color:#6b7280;font-size:0.9em;margin-top:8px">训练完成后可查看每只股票的预测价格和历史准确率。</p>
      </div>
    </div>
  </div>
</div>

<!-- National Team ETF Monitor Modal -->
<div id="nationalTeamModal" class="modal-overlay" role="dialog" aria-modal="true">
  <div class="modal-panel" style="max-width:96vw;max-height:94vh;width:960px;background:#0f1117;border:1px solid #2a2d3e">
    <div class="modal-head" style="border-bottom:1px solid #2a2d3e">
      <h2>&#127961; 国家队ETF监控</h2>
      <button type="button" class="modal-close" onclick="closeNationalTeamModal()" title="Close">&times;</button>
    </div>
    <div class="modal-content" style="padding:14px 18px;background:#0f1117">
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
        <button type="button" class="send-btn" id="btnNTFetch" onclick="fetchNationalTeam()" style="padding:8px 18px;font-size:0.86em">&#128202; 获取最新数据</button>
        <span id="ntStatus" style="font-size:0.78em;color:#8b8fa4;margin-left:auto"></span>
      </div>
      <div id="ntResult" style="max-height:68vh;overflow-y:auto;border:1px solid #2a2d3e;border-radius:8px;padding:14px;background:#1a1d2e;font-size:0.84em;line-height:1.6;color:#c4c8f0">
        <p style="color:#6b7280">点击"获取最新数据"查看国家队核心ETF份额变动。</p>
        <p style="color:#6b7280;font-size:0.9em">监控16只核心ETF (9宽基 + 7行业)，跟踪汇金/社保/央企资金动向。</p>
        <p style="color:#6b7280;font-size:0.85em;margin-top:4px">数据来源: 上交所/深交所 ETF 份额公告</p>
      </div>
    </div>
  </div>
</div>

<script>
const chatEl = document.getElementById('chat');
const queryInput = document.getElementById('queryInput');
const sendBtn = document.getElementById('sendBtn');
const statusEl = document.getElementById('status');
let conversationHistory = [];
let currentImageB64 = null;
let isStreaming = false;
let currentSessionId = null;
let lastOutgoingUserText = '';
let sidebarCollapsed = window.innerWidth < 768;
let lastViewportMobile = window.innerWidth < 768;

function applySidebarClass() {
  const sb = document.getElementById('sessionSidebar');
  const scrim = document.getElementById('sidebarScrim');
  if (!sb) return;
  sb.classList.toggle('collapsed', sidebarCollapsed);
  if (window.innerWidth < 768) {
    scrim.classList.toggle('visible', !sidebarCollapsed);
  } else if (scrim) {
    scrim.classList.remove('visible');
  }
}

function toggleSidebar() {
  sidebarCollapsed = !sidebarCollapsed;
  applySidebarClass();
}

function closeSidebarMobile() {
  if (window.innerWidth < 768) {
    sidebarCollapsed = true;
    applySidebarClass();
  }
}

function syncSidebarForViewport() {
  const m = window.innerWidth < 768;
  if (m !== lastViewportMobile) {
    lastViewportMobile = m;
    sidebarCollapsed = m;
    applySidebarClass();
  }
}

window.addEventListener('resize', syncSidebarForViewport);

function showToast(message) {
  const c = document.getElementById('toastContainer');
  if (!c) return;
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = message;
  c.appendChild(t);
  setTimeout(function() {
    t.style.opacity = '0';
    t.style.transition = 'opacity .25s ease';
    setTimeout(function() { t.remove(); }, 280);
  }, 4000);
}

function toggleToolbarCat(catId) {
  const el = document.getElementById(catId);
  if (!el) return;
  const wasOpen = el.classList.contains('open');
  document.querySelectorAll('.toolbar-cat.open').forEach(c => c.classList.remove('open'));
  if (!wasOpen) el.classList.add('open');
}
document.addEventListener('click', function(e) {
  if (!e.target.closest('.toolbar-cat')) {
    document.querySelectorAll('.toolbar-cat.open').forEach(c => c.classList.remove('open'));
  }
});

function toolbarReindexSpinner(btn, on) {
  if (!btn) return;
  let spin = btn.querySelector('.mini-spin');
  if (on) {
    if (!spin) {
      spin = document.createElement('span');
      spin.className = 'mini-spin';
      btn.insertBefore(spin, btn.firstChild);
    }
    spin.style.display = 'inline-block';
  } else if (spin) {
    spin.style.display = 'none';
  }
}

function openWikiFetchModal() {
  const today = new Date();
  const monthAgo = new Date(today);
  monthAgo.setMonth(monthAgo.getMonth() - 1);
  const toEl = document.getElementById('wikiFetchDateTo');
  const fromEl = document.getElementById('wikiFetchDateFrom');
  if (toEl && !toEl.value) toEl.value = today.toISOString().slice(0, 10);
  if (fromEl && !fromEl.value) fromEl.value = monthAgo.toISOString().slice(0, 10);
  document.getElementById('wikiFetchModal').classList.add('open');
}
function closeWikiFetchModal() {
  document.getElementById('wikiFetchModal').classList.remove('open');
}
function wikiFetchSelectAll() {
  document.querySelectorAll('#wikiFetchUserList input[type="checkbox"]').forEach(function(cb) { cb.checked = true; });
}
function wikiFetchSelectNone() {
  document.querySelectorAll('#wikiFetchUserList input[type="checkbox"]').forEach(function(cb) { cb.checked = false; });
}
async function startWikiFetch() {
  const checks = document.querySelectorAll('#wikiFetchUserList input[type="checkbox"]:checked');
  const users = Array.from(checks).map(function(cb) { return cb.value; });
  if (users.length === 0) { showToast('Select at least one team member'); return; }
  const dateFrom = document.getElementById('wikiFetchDateFrom').value || '';
  const dateTo = document.getElementById('wikiFetchDateTo').value || '';
  closeWikiFetchModal();
  await newChat();
  const btn = document.getElementById('btnWikiFetch');
  try {
    const r = await fetch('/api/toolbar/wiki-fetch', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ users: users, date_from: dateFrom, date_to: dateTo }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Failed to start');
    showToast('Wiki fetch started for ' + users.length + ' user(s)');
    if (btn) { btn.disabled = true; toolbarReindexSpinner(btn, true); }
    const pollUrl = '/api/toolbar/wiki-fetch/' + encodeURIComponent(d.job_id);
    const poll = setInterval(async function() {
      try {
        const sr = await fetch(pollUrl);
        const sd = await sr.json();
        if (sd.status === 'done' || sd.status === 'error') {
          clearInterval(poll);
          if (btn) { btn.disabled = false; toolbarReindexSpinner(btn, false); }
          const tail = (sd.result || '').substring(0, 300);
          if (sd.status === 'done') {
            showToast(tail ? ('Wiki fetch complete: ' + tail) : 'Wiki fetch complete');
          } else {
            showToast('Wiki fetch failed' + (tail ? (': ' + tail) : ''));
          }
          checkHealth();
        } else if (sd.progress) {
          showToast('Wiki fetch: ' + sd.progress);
        }
      } catch (err) {
        clearInterval(poll);
        if (btn) { btn.disabled = false; toolbarReindexSpinner(btn, false); }
      }
    }, 3000);
  } catch (e) {
    showToast('Wiki fetch error: ' + e.message);
    if (btn) { btn.disabled = false; toolbarReindexSpinner(btn, false); }
  }
}

function addSystemMessage(label, text) {
  const div = document.createElement('div');
  div.className = 'msg msg-system';
  div.innerHTML = '<div class="sys-label">' + escHtml(label) + '</div><div style="white-space:pre-wrap">' + escHtml(text || '') + '</div>';
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function addCollapsibleSystemMessage(label, text, previewLines) {
  previewLines = previewLines || 12;
  const lines = (text || '').split('\n');
  const total = lines.length;
  if (total <= previewLines + 3) {
    addSystemMessage(label, text);
    return;
  }
  const headerLines = [];
  let dataStart = 0;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].startsWith('[') || lines[i].trim() === '') {
      if (lines[i].startsWith('[')) { dataStart = i; break; }
    } else {
      headerLines.push(lines[i]);
    }
  }
  if (dataStart === 0) dataStart = headerLines.length;
  const dataLines = lines.slice(dataStart);
  const previewData = dataLines.slice(0, previewLines);
  const hiddenData = dataLines.slice(previewLines);
  const hiddenCount = hiddenData.length;

  const div = document.createElement('div');
  div.className = 'msg msg-system';
  const uid = 'sys_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
  div.innerHTML = '<div class="sys-label">' + escHtml(label) + '</div>' +
    '<div style="white-space:pre-wrap">' + escHtml(headerLines.join('\n')) + '\n' +
    escHtml(previewData.join('\n')) +
    '<div id="' + uid + '" class="sys-hidden-block">' + escHtml('\n' + hiddenData.join('\n')) + '</div>' +
    '</div>' +
    '<span class="sys-toggle" onclick="toggleSysBlock(\'' + uid + '\', this, ' + hiddenCount + ')">' +
    'Show all (' + hiddenCount + ' more entries)' +
    '</span>';
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function toggleSysBlock(uid, btn, count) {
  const block = document.getElementById(uid);
  if (!block) return;
  const hidden = block.classList.toggle('sys-hidden-block');
  btn.textContent = hidden ? 'Show all (' + count + ' more entries)' : 'Collapse';
  chatEl.scrollTop = chatEl.scrollHeight;
}

async function toolbarCommitFetch24(btn) {
  if (!btn) btn = document.getElementById('btnCommitFetch');
  if (btn) { btn.disabled = true; toolbarReindexSpinner(btn, true); }
  showToast('Fetching commits (48h) — scanning all repos…');
  try {
    const r = await fetch('/api/toolbar/commit-summary', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ hours: 48 }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Request failed');
    const report = d.result || '';
    if (!report) { showToast('No commits found in the last 48 hours'); return; }
    addCollapsibleSystemMessage('Commit fetch (48h)', report, 12);
    conversationHistory.push({role: 'assistant', content: '[Git Commits Last 48h]\n' + report});
    showToast('Generating commit summary…');
    if (!isStreaming) {
      queryInput.value = 'IMPORTANT: Use ONLY the latest commit data block above (the one marked [Git Commits Last 48h]). Ignore any older commit data in the conversation. Summarize ALL commits: group by team member and repository, highlight key changes, and note any patterns. Do NOT invent job titles or roles for anyone.';
      sendMessage();
    }
  } catch (e) {
    showToast('Commit fetch failed: ' + e.message);
  } finally {
    if (btn) { btn.disabled = false; toolbarReindexSpinner(btn, false); }
  }
}

async function toolbarJiraDaily(btn) {
  if (!btn) btn = document.getElementById('btnJiraDaily');
  if (btn) { btn.disabled = true; toolbarReindexSpinner(btn, true); }
  await newChat();
  showToast('Running Jira report — this takes ~30 seconds…');
  try {
    const r = await fetch('/api/toolbar/jira-report', { method: 'POST' });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Request failed');
    const report = d.result || '';
    if (!report) { showToast('Jira report returned empty — check if Atlassian API is reachable'); return; }
    addSystemMessage('Jira daily report', report);
    conversationHistory.push({role: 'assistant', content: '[Jira/Confluence Daily Report]\n' + report});
    showToast('Generating team activity summary…');
    if (!isStreaming) {
      queryInput.value = 'Summarize the Jira daily report above: group open tickets and activity by team member, highlight blockers or high-priority items, and note sprint progress. Include Confluence page updates.';
      sendMessage();
    }
  } catch (e) {
    showToast('Jira report failed: ' + e.message);
  } finally {
    if (btn) { btn.disabled = false; toolbarReindexSpinner(btn, false); }
  }
}

function openExplainThisModal() {
  document.getElementById('explainTopic').value = '';
  document.getElementById('explainThisModal').classList.add('open');
  setTimeout(function() { document.getElementById('explainTopic').focus(); }, 100);
}
function closeExplainThisModal() {
  document.getElementById('explainThisModal').classList.remove('open');
}

async function startExplainThis() {
  var topic = document.getElementById('explainTopic').value.trim();
  if (!topic) { showToast('Please enter a topic to explain'); return; }
  var depth = document.querySelector('input[name="explainDepth"]:checked');
  var depthVal = depth ? depth.value : 'deep';
  var useWeb = document.getElementById('explainWebSearch').checked;
  closeExplainThisModal();

  var depthLabel = depthVal === 'quick' ? 'quick overview' : 'deep dive';
  showToast('Preparing ' + depthLabel + ' on "' + topic + '"...');

  var depthInstruction = depthVal === 'quick'
    ? 'Give a concise explanation (2-3 paragraphs). Cover: what it is, why it matters, and one practical example.'
    : 'Give a comprehensive deep-dive explanation. Cover: 1) What it is and core concepts, 2) How it works technically, 3) Why it matters in the AI/tech landscape, 4) Practical applications and examples, 5) How it relates to Java/medtech/healthcare if applicable, 6) Resources to learn more. Use clear analogies for complex concepts.';

  var webInstruction = useWeb
    ? 'The user also wants you to search the web for the latest information on this topic. Use your web search tool if available.'
    : '';

  var prompt = 'EXPLAIN THIS: "' + topic + '"\n\n' +
    depthInstruction + '\n' +
    webInstruction + '\n' +
    'Search the knowledge base (RAG) for any relevant context about this topic from previous briefings, articles, or documentation. ' +
    'Combine RAG context with your own knowledge to provide the most helpful explanation. ' +
    'Format with clear headings and structure. If the topic appeared in recent AI briefings, reference those.';

  if (!isStreaming) {
    queryInput.value = prompt;
    sendMessage();
  }
}

var _dfCurrentDate = '';
var _dfMissingSteps = [];
function openDailyFetchModal() {
  document.getElementById('dailyFetchModal').classList.add('open');
  document.getElementById('dfRunProgress').style.display = 'none';
  document.getElementById('btnRunDailyFetch').disabled = false;
  document.getElementById('btnContinueDailyFetch').style.display = 'none';
  loadDailyFetchHistory('');
}
function closeDailyFetchModal() {
  document.getElementById('dailyFetchModal').classList.remove('open');
}
function dfNavDay(offset) {
  if (!_dfCurrentDate) return;
  var d = new Date(_dfCurrentDate + 'T12:00:00');
  d.setDate(d.getDate() + offset);
  loadDailyFetchHistory(d.toISOString().slice(0, 10));
}
async function loadDailyFetchHistory(date) {
  var el = document.getElementById('dfHistoryContent');
  el.innerHTML = '<p style="font-size:0.82em;color:#6b7280">Loading...</p>';
  try {
    var url = '/api/toolbar/daily-fetch/history' + (date ? '?date=' + date : '');
    var resp = await fetch(url);
    var data = await resp.json();
    _dfCurrentDate = data.date || '';
    _dfMissingSteps = data.missing_steps || [];
    document.getElementById('dfHistoryDate').value = _dfCurrentDate;
    document.getElementById('dfDateLabel').textContent = _dfCurrentDate || 'No data';
    var contBtn = document.getElementById('btnContinueDailyFetch');
    if (_dfMissingSteps.length > 0 && data.files && data.files.length > 0) {
      contBtn.style.display = '';
      contBtn.disabled = false;
    } else {
      contBtn.style.display = 'none';
    }
    if (!data.date || !data.files || data.files.length === 0) {
      el.innerHTML = '<p style="font-size:0.88em;color:#f59e0b;text-align:center;padding:24px 0">No reports found for this date.</p>';
      return;
    }
    var s = data.stats || {};
    var h = '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px">';
    h += '<div style="background:#1a1d2e;border-radius:8px;padding:10px 14px;border:1px solid #2a2d3e">';
    h += '<div style="font-size:0.72em;color:#8b8fa4;text-transform:uppercase;letter-spacing:0.5px">AI News</div>';
    h += '<div style="font-size:1.3em;font-weight:700;color:#60a5fa">' + (s.ai_items || 0) + ' <span style="font-size:0.55em;font-weight:400">items</span></div></div>';
    h += '<div style="background:#1a1d2e;border-radius:8px;padding:10px 14px;border:1px solid #2a2d3e">';
    h += '<div style="font-size:0.72em;color:#8b8fa4;text-transform:uppercase;letter-spacing:0.5px">World News</div>';
    h += '<div style="font-size:1.3em;font-weight:700;color:#f59e0b">' + (s.world_news_items || 0) + ' <span style="font-size:0.55em;font-weight:400">items</span></div></div>';
    h += '<div style="background:#1a1d2e;border-radius:8px;padding:10px 14px;border:1px solid #2a2d3e">';
    h += '<div style="font-size:0.72em;color:#8b8fa4;text-transform:uppercase;letter-spacing:0.5px">\u4e2d\u56fd\u65b0\u95fb</div>';
    h += '<div style="font-size:1.3em;font-weight:700;color:#ef4444">' + (s.china_news_items || 0) + ' <span style="font-size:0.55em;font-weight:400">items</span></div></div>';
    h += '<div style="background:#1a1d2e;border-radius:8px;padding:10px 14px;border:1px solid #2a2d3e">';
    h += '<div style="font-size:0.72em;color:#8b8fa4;text-transform:uppercase;letter-spacing:0.5px">Jira Tickets</div>';
    h += '<div style="font-size:1.3em;font-weight:700;color:#a78bfa">' + (s.jira_tickets || 0) + '</div></div>';
    h += '<div style="background:#1a1d2e;border-radius:8px;padding:10px 14px;border:1px solid #2a2d3e">';
    h += '<div style="font-size:0.72em;color:#8b8fa4;text-transform:uppercase;letter-spacing:0.5px">Confluence</div>';
    h += '<div style="font-size:1.3em;font-weight:700;color:#34d399">' + (s.confluence_pages || 0) + ' <span style="font-size:0.55em;font-weight:400">pages</span></div></div>';
    h += '<div style="background:#1a1d2e;border-radius:8px;padding:10px 14px;border:1px solid #2a2d3e">';
    h += '<div style="font-size:0.72em;color:#8b8fa4;text-transform:uppercase;letter-spacing:0.5px">Wiki Fetch</div>';
    h += '<div style="font-size:1.3em;font-weight:700;color:#38bdf8">' + (s.wiki_pages || 0) + ' <span style="font-size:0.55em;font-weight:400">pages</span></div></div>';
    h += '</div>';
    if (_dfMissingSteps.length > 0) {
      var stepLabels = {fetch_sources:'Source Fetch',topic_dedup:'Topic Dedup',commit_report:'Commit Report',jira_daily:'Jira Report',wiki_fetch:'Wiki Fetch',world_news_merge:'World News Merge',ai_audio:'AI Audio',world_audio:'World Audio',china_audio:'\u4e2d\u56fd\u65b0\u95fb Audio'};
      h += '<div style="background:#2a1a0a;border:1px solid #d97706;border-radius:8px;padding:10px 14px;margin-bottom:14px">';
      h += '<div style="font-size:0.78em;font-weight:600;color:#f59e0b;margin-bottom:6px">Incomplete — missing steps:</div>';
      h += '<div style="display:flex;flex-wrap:wrap;gap:6px">';
      for (var mi = 0; mi < _dfMissingSteps.length; mi++) {
        var sl = stepLabels[_dfMissingSteps[mi]] || _dfMissingSteps[mi];
        h += '<span style="background:#3a2a0a;border:1px solid #d97706;border-radius:4px;padding:2px 8px;font-size:0.78em;color:#fbbf24">' + escHtml(sl) + '</span>';
      }
      h += '</div></div>';
    }
    if (data.has_audio || data.has_wn_audio || data.has_cn_audio) {
      h += '<div style="margin-bottom:14px">';
      if (data.has_audio) {
        h += '<div style="font-size:0.78em;font-weight:600;color:#60a5fa;margin-bottom:4px">AI Briefing Audio</div>';
        h += '<audio controls style="width:100%;height:32px;margin-bottom:8px" src="/api/toolbar/audio-file/' + escHtml(data.date) + '/ai-briefing.mp3"></audio>';
      }
      if (data.has_wn_audio) {
        h += '<div style="font-size:0.78em;font-weight:600;color:#f59e0b;margin-bottom:4px">World News Audio</div>';
        h += '<audio controls style="width:100%;height:32px;margin-bottom:8px" src="/api/toolbar/audio-file/' + escHtml(data.date) + '/world-news.mp3"></audio>';
      }
      if (data.has_cn_audio) {
        h += '<div style="font-size:0.78em;font-weight:600;color:#ef4444;margin-bottom:4px">\u4e2d\u56fd\u65b0\u95fb Audio</div>';
        h += '<audio controls style="width:100%;height:32px;margin-bottom:8px" src="/api/toolbar/audio-file/' + escHtml(data.date) + '/china-news.mp3"></audio>';
      }
      h += '</div>';
    }
    var mdFiles = data.files.filter(function(f) { return f.name.endsWith('.md'); });
    if (mdFiles.length > 0) {
      h += '<div style="font-size:0.75em;color:#6b7280;margin-bottom:6px">Reports:</div>';
      h += '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px">';
      for (var i = 0; i < mdFiles.length; i++) {
        var f = mdFiles[i];
        h += '<button type="button" onclick="loadDfReportContent(\'' + escHtml(data.date) + '\',\'' + escHtml(f.name) + '\',this)" style="background:#1e2a3e;border:1px solid #3a5a8a;border-radius:5px;padding:4px 10px;font-size:0.82em;color:#c4c8f0;cursor:pointer" title="' + f.size_kb + ' KB">' + escHtml(f.name) + '</button>';
      }
      h += '</div>';
      h += '<div id="dfReportPreview" style="display:none;max-height:40vh;overflow-y:auto;background:#0f1117;border:1px solid #2a2d3a;border-radius:8px;padding:14px 16px;font-size:0.82em;color:#c4c8f0;line-height:1.6"></div>';
    }
    el.innerHTML = h;
  } catch(e) {
    el.innerHTML = '<p style="font-size:0.82em;color:#ef4444">Error loading history: ' + escHtml(e.message) + '</p>';
  }
}
async function runDailyFetchFromModal() {
  var btn = document.getElementById('btnRunDailyFetch');
  btn.disabled = true;
  var progressEl = document.getElementById('dfRunProgress');
  var progressText = document.getElementById('dfRunProgressText');
  progressEl.style.display = 'block';
  progressText.textContent = 'Starting pipeline...';
  addSystemMessage('Daily Fetch started — running AI sources, world news, commit report, Jira, and audio generation. This may take 5-10 minutes...');
  try {
    var resp = await fetch('/api/toolbar/daily-fetch', {method:'POST'});
    var data = await resp.json();
    var jobId = data.job_id;
    var poll = setInterval(async function() {
      try {
        var sr = await fetch('/api/toolbar/daily-fetch/' + jobId);
        var st = await sr.json();
        progressText.textContent = st.step || 'Working...';
        if (st.status === 'done') {
          clearInterval(poll);
          progressEl.querySelector('.mini-spin').style.display = 'none';
          var steps = st.steps || [];
          var stepHtml = '<div style="margin-top:8px">';
          for (var i = 0; i < steps.length; i++) {
            var ok = steps[i].exit_code === 0;
            var icon = ok ? '<span style="color:#34d399">&#10004;</span>' : '<span style="color:#ef4444">&#10008;</span>';
            stepHtml += '<div style="font-size:0.78em;color:#c4c8f0;margin:2px 0">' + icon + ' ' + escHtml(steps[i].step) + (ok ? '' : ' — ' + escHtml((steps[i].output || '').substring(0, 80))) + '</div>';
          }
          stepHtml += '</div>';
          progressText.innerHTML = '<span style="color:#34d399;font-weight:600">Complete!</span>' + stepHtml;
          btn.disabled = false;
          loadDailyFetchHistory(new Date().toISOString().slice(0, 10));
          var dailySummary = st.daily_summary || '';
          addCollapsibleSystemMessage('Daily Fetch Results', dailySummary, 20);
          var today = new Date().toISOString().slice(0, 10);
          var audioHtml = '<div style="margin:10px 0;padding:12px;background:#1a1d2e;border-radius:8px;border:1px solid #2a2d3e">' +
            '<div style="font-weight:600;color:#60a5fa;margin-bottom:8px">AI Briefing Audio</div>' +
            '<audio controls style="width:100%;margin-bottom:6px" src="/api/toolbar/audio-file/' + today + '/ai-briefing.mp3"></audio>' +
            '<div style="font-weight:600;color:#f59e0b;margin:12px 0 8px">World News Audio</div>' +
            '<audio controls style="width:100%;margin-bottom:6px" src="/api/toolbar/audio-file/' + today + '/world-news.mp3"></audio>' +
            '<div style="font-weight:600;color:#ef4444;margin:12px 0 8px">中国新闻 Audio</div>' +
            '<audio controls style="width:100%;margin-bottom:6px" src="/api/toolbar/audio-file/' + today + '/china-news.mp3"></audio>' +
            '</div>';
          var audioMsg = document.createElement('div');
          audioMsg.className = 'system-msg';
          audioMsg.innerHTML = audioHtml;
          document.getElementById('chatMessages').appendChild(audioMsg);
          scrollToBottom();
          var summaryPrompt = 'The daily fetch pipeline just completed. Below is the full data collected today. Please provide a comprehensive daily briefing summary in the following format:\\n\\n1. **AI News Highlights** (top 5 most important items with 1-sentence each)\\n2. **World News Highlights** (top 5 items)\\n3. **Team Activity** (summarize git commits by person and key changes)\\n4. **Jira Updates** (summarize ticket activity)\\n5. **Action Items** (anything that needs attention)\\n\\nHere is the data:\\n\\n' + dailySummary;
          conversationHistory.push({role:'user', content: summaryPrompt});
          sendMessage(summaryPrompt);
        } else if (st.status === 'error') {
          clearInterval(poll);
          progressEl.querySelector('.mini-spin').style.display = 'none';
          progressText.innerHTML = '<span style="color:#ef4444;font-weight:600">Error:</span> ' + escHtml(st.step || 'unknown');
          btn.disabled = false;
        }
      } catch(pe) { /* polling error, retry */ }
    }, 4000);
  } catch(e) {
    progressText.textContent = 'Error: ' + e.message;
    btn.disabled = false;
  }
}
async function continueDailyFetchFromModal() {
  if (!_dfMissingSteps.length) return;
  var contBtn = document.getElementById('btnContinueDailyFetch');
  var runBtn = document.getElementById('btnRunDailyFetch');
  contBtn.disabled = true;
  runBtn.disabled = true;
  var progressEl = document.getElementById('dfRunProgress');
  var progressText = document.getElementById('dfRunProgressText');
  progressEl.style.display = 'block';
  progressText.textContent = 'Continuing: ' + _dfMissingSteps.join(', ') + '...';
  addSystemMessage('Daily Fetch continuing — running missing steps: ' + _dfMissingSteps.join(', ') + '. Audio generation may take 20-30 min...');
  try {
    var resp = await fetch('/api/toolbar/daily-fetch/continue', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({steps: _dfMissingSteps, date: _dfCurrentDate})
    });
    var data = await resp.json();
    var jobId = data.job_id;
    var poll = setInterval(async function() {
      try {
        var sr = await fetch('/api/toolbar/daily-fetch/' + jobId);
        var st = await sr.json();
        progressText.textContent = st.step || 'Working...';
        if (st.status === 'done') {
          clearInterval(poll);
          progressEl.querySelector('.mini-spin').style.display = 'none';
          var steps = st.steps || [];
          var stepHtml = '<div style="margin-top:8px">';
          for (var i = 0; i < steps.length; i++) {
            var ok = steps[i].exit_code === 0;
            var icon = ok ? '<span style="color:#34d399">&#10004;</span>' : '<span style="color:#ef4444">&#10008;</span>';
            stepHtml += '<div style="font-size:0.78em;color:#c4c8f0;margin:2px 0">' + icon + ' ' + escHtml(steps[i].step) + (ok ? '' : ' — ' + escHtml((steps[i].output || '').substring(0, 80))) + '</div>';
          }
          stepHtml += '</div>';
          progressText.innerHTML = '<span style="color:#34d399;font-weight:600">Continue complete!</span>' + stepHtml;
          contBtn.disabled = false;
          runBtn.disabled = false;
          addSystemMessage('Daily Fetch continue finished for ' + _dfCurrentDate);
          setTimeout(function() { loadDailyFetchHistory(_dfCurrentDate); }, 5000);
        } else if (st.status === 'error') {
          clearInterval(poll);
          progressEl.querySelector('.mini-spin').style.display = 'none';
          progressText.innerHTML = '<span style="color:#ef4444;font-weight:600">Error:</span> ' + escHtml(st.step || 'unknown');
          contBtn.disabled = false;
          runBtn.disabled = false;
        }
      } catch(pe) { /* polling error, retry */ }
    }, 4000);
  } catch(e) {
    progressText.textContent = 'Error: ' + e.message;
    contBtn.disabled = false;
    runBtn.disabled = false;
  }
}
async function loadDfReportContent(dateStr, filename, btn) {
  var preview = document.getElementById('dfReportPreview');
  if (!preview) return;
  var btns = btn.parentElement.querySelectorAll('button');
  btns.forEach(function(b) { b.style.borderColor = '#3a5a8a'; b.style.background = '#1e2a3e'; });
  btn.style.borderColor = '#60a5fa';
  btn.style.background = '#1e3a5e';
  preview.style.display = 'block';
  preview.innerHTML = '<span style="color:#6b7280">Loading...</span>';
  try {
    var resp = await fetch('/api/toolbar/report-content/' + encodeURIComponent(dateStr) + '/' + encodeURIComponent(filename));
    var data = await resp.json();
    if (data.error) { preview.textContent = 'Error: ' + data.error; return; }
    var md = data.content || '';
    var rendered = md
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/^### (.+)$/gm, '<h4 style="color:#60a5fa;margin:14px 0 6px;font-size:1em">$1</h4>')
      .replace(/^## (.+)$/gm, '<h3 style="color:#a78bfa;margin:16px 0 8px;font-size:1.1em">$1</h3>')
      .replace(/^# (.+)$/gm, '<h2 style="color:#f59e0b;margin:18px 0 10px;font-size:1.2em">$1</h2>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong style="color:#e2e8f0">$1</strong>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" style="color:#60a5fa;text-decoration:underline">$1</a>')
      .replace(/^\|(.+)\|$/gm, function(match) {
        var cells = match.split('|').filter(function(c) { return c.trim() !== ''; });
        if (cells.every(function(c) { return /^[\s-:]+$/.test(c); })) return '';
        return '<tr>' + cells.map(function(c) { return '<td style="padding:3px 8px;border:1px solid #2a2d3a">' + c.trim() + '</td>'; }).join('') + '</tr>';
      })
      .replace(/^- (.+)$/gm, '<li style="margin:2px 0;list-style:disc inside">$1</li>')
      .replace(/^---+$/gm, '<hr style="border-color:#2a2d3a;margin:12px 0">')
      .replace(/\n{2,}/g, '<br><br>')
      .replace(/\n/g, '<br>');
    rendered = rendered.replace(/(<tr>[\s\S]*?<\/tr>(?:\s*<tr>[\s\S]*?<\/tr>)*)/g,
      '<table style="border-collapse:collapse;width:100%;margin:8px 0;font-size:0.92em">$1</table>');
    preview.innerHTML = '<div style="font-size:0.72em;color:#6b7280;margin-bottom:8px;display:flex;justify-content:space-between">' +
      '<span>' + escHtml(filename) + '</span>' +
      '<a href="/api/toolbar/audio-file/' + encodeURIComponent(dateStr) + '/' + encodeURIComponent(filename) + '" download style="color:#60a5fa;text-decoration:none">Download</a>' +
      '</div>' + rendered;
  } catch(e) {
    preview.textContent = 'Error: ' + e.message;
  }
}

var _donorData = null;
function openDonorAnalysis() {
  document.getElementById('donorTableWrap').innerHTML = '<p style="font-size:0.82em;color:#8b8fa4">Click "Load &amp; Score" to analyze donor profiles.</p>';
  document.getElementById('donorTop10Result').style.display = 'none';
  document.getElementById('btnDonorTop10').disabled = true;
  document.getElementById('btnDonorPdf').disabled = true;
  document.getElementById('donorCount').textContent = '';
  _donorData = null;
  document.getElementById('donorAnalysisModal').classList.add('open');
}
function closeDonorAnalysis() {
  document.getElementById('donorAnalysisModal').classList.remove('open');
}

function openTrendAnalysis() {
  document.getElementById('trendAnalysisStatus').textContent = '';
  var res = document.getElementById('trendAnalysisResult');
  res.style.display = 'none';
  res.textContent = '';
  document.getElementById('btnTrendAnalyze').disabled = false;
  document.getElementById('trendAnalysisModal').classList.add('open');
}
function closeTrendAnalysis() {
  document.getElementById('trendAnalysisModal').classList.remove('open');
}

async function runTrendAnalysis() {
  var checks = document.querySelectorAll('#trendCategoryList input[type="checkbox"]:checked');
  var categories = Array.from(checks).map(function(cb) { return cb.value; });
  if (categories.length === 0) { showToast('Select at least one category'); return; }
  var days = 7;
  var d14 = document.getElementById('taDays14');
  var d30 = document.getElementById('taDays30');
  if (d14 && d14.checked) days = 14;
  else if (d30 && d30.checked) days = 30;

  var btn = document.getElementById('btnTrendAnalyze');
  var statusEl = document.getElementById('trendAnalysisStatus');
  var resultEl = document.getElementById('trendAnalysisResult');
  btn.disabled = true;
  statusEl.textContent = 'Collecting data and streaming ' + days + '-day analysis via Ollama...';
  resultEl.style.display = 'block';
  resultEl.innerHTML = '';
  var fullText = '';
  try {
    var resp = await fetch('/api/toolbar/trend-analysis', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ categories: categories, days: days })
    });
    if (!resp.ok) {
      var errJ = await resp.json().catch(function() { return {}; });
      resultEl.textContent = 'Error: ' + (errJ.error || resp.statusText || 'request failed');
      statusEl.textContent = '';
      return;
    }
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      var lines = decoder.decode(chunk.value, {stream: true}).split('\\n');
      lines.forEach(function(line) {
        if (line.startsWith('data: ')) {
          try {
            var ev = JSON.parse(line.substring(6));
            if (ev.type === 'token') { fullText += ev.content || ''; resultEl.innerHTML = _simpleMarkdownToHtml(fullText); }
            if (ev.type === 'done') {
              fullText = ev.content || fullText;
              resultEl.innerHTML = _simpleMarkdownToHtml(fullText);
              var range = (ev.start && ev.end) ? (' (' + ev.start + ' to ' + ev.end + ')') : '';
              addSystemMessage('Trend Analysis', 'Completed' + range + '. Full report is in the Trend Analysis modal.');
            }
            if (ev.type === 'error') {
              resultEl.textContent = 'Error: ' + (ev.message || 'unknown');
              statusEl.textContent = '';
            }
          } catch (e) {}
        }
      });
    }
    statusEl.textContent = '';
  } catch (e) {
    resultEl.textContent = 'Error: ' + e.message;
    statusEl.textContent = '';
  } finally {
    btn.disabled = false;
  }
}

var _aiKBItems = [];
var _aiKBSortCol = 'date';
var _aiKBSortAsc = false;

function openAiNewsKB() {
  document.getElementById('aiKBStatus').textContent = 'Loading...';
  document.getElementById('aiKBSummaryResult').style.display = 'none';
  document.getElementById('aiNewsKBModal').classList.add('open');
  fetch('/api/toolbar/ai-news-kb').then(function(r){return r.json()}).then(function(d){
    _aiKBItems = d.items || [];
    _aiKBRenderTable();
    _aiKBUpdateFilters();
    document.getElementById('aiKBStatus').textContent = '';
    document.getElementById('aiKBStats').textContent = d.total + ' items | Last scan: ' + (d.last_scanned || 'never');
    document.getElementById('btnAiKBSummary').disabled = _aiKBItems.length === 0;
  }).catch(function(e){ document.getElementById('aiKBStatus').textContent = 'Error: ' + e.message; });
}
function closeAiNewsKB() { document.getElementById('aiNewsKBModal').classList.remove('open'); }

function _aiKBRenderTable() {
  var tbody = document.getElementById('aiKBTableBody');
  var keyword = (document.getElementById('aiKBFilter').value || '').toLowerCase();
  var catF = document.getElementById('aiKBCatFilter').value;
  var srcF = document.getElementById('aiKBSourceFilter').value;
  var filtered = _aiKBItems.filter(function(it) {
    if (catF && it.category !== catF) return false;
    if (srcF && it.source !== srcF) return false;
    if (keyword && (it.title + ' ' + it.summary + ' ' + it.source).toLowerCase().indexOf(keyword) < 0) return false;
    return true;
  });
  filtered.sort(function(a, b) {
    var va = (a[_aiKBSortCol] || '').toLowerCase();
    var vb = (b[_aiKBSortCol] || '').toLowerCase();
    if (va < vb) return _aiKBSortAsc ? -1 : 1;
    if (va > vb) return _aiKBSortAsc ? 1 : -1;
    return 0;
  });
  var html = '';
  var shown = Math.min(filtered.length, 500);
  for (var i = 0; i < shown; i++) {
    var it = filtered[i];
    var linkHtml = it.url ? '<a href="' + it.url.replace(/"/g,'&quot;') + '" target="_blank" style="color:#60a5fa;text-decoration:none" title="' + it.url.replace(/"/g,'&quot;') + '">&#128279;</a>' : '';
    var catBadge = it.category ? '<span style="background:#2a2d3e;padding:1px 6px;border-radius:4px;font-size:0.9em;white-space:nowrap">' + _escHtml(it.category) + '</span>' : '';
    var rowId = 'aikb-row-' + i;
    html += '<tr style="border-bottom:1px solid #1a1d2e;cursor:pointer" onclick="toggleAiKBSummary(\'' + rowId + '\')">'
      + '<td style="padding:4px 8px;color:#8b8fa4;white-space:nowrap">' + _escHtml(it.date) + '</td>'
      + '<td style="padding:4px 8px">' + catBadge + '</td>'
      + '<td style="padding:4px 8px;color:#8b8fa4">' + _escHtml(it.source) + '</td>'
      + '<td style="padding:4px 8px;color:#e0e0e0">' + _escHtml(it.title) + '</td>'
      + '<td style="padding:4px 8px;text-align:center">' + linkHtml + '</td>'
      + '</tr>';
    if (it.summary) {
      html += '<tr id="' + rowId + '" style="display:none"><td colspan="5" style="padding:4px 8px 10px 28px;color:#9ca3af;font-size:0.92em;line-height:1.5;border-bottom:1px solid #2a2d3e">' + _escHtml(it.summary) + '</td></tr>';
    }
  }
  if (filtered.length > 500) html += '<tr><td colspan="5" style="padding:8px;color:#8b8fa4;text-align:center">Showing 500 of ' + filtered.length + ' items</td></tr>';
  tbody.innerHTML = html || '<tr><td colspan="5" style="padding:12px;color:#8b8fa4;text-align:center">No items found</td></tr>';
}

function _escHtml(s) { var d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

function _aiKBUpdateFilters() {
  var cats = {}, srcs = {};
  _aiKBItems.forEach(function(it) { if (it.category) cats[it.category] = 1; if (it.source) srcs[it.source] = 1; });
  var catSel = document.getElementById('aiKBCatFilter');
  var srcSel = document.getElementById('aiKBSourceFilter');
  var oldCat = catSel.value, oldSrc = srcSel.value;
  catSel.innerHTML = '<option value="">All Categories</option>';
  Object.keys(cats).sort().forEach(function(c) { catSel.innerHTML += '<option value="' + _escHtml(c) + '">' + _escHtml(c) + '</option>'; });
  srcSel.innerHTML = '<option value="">All Sources</option>';
  Object.keys(srcs).sort().forEach(function(s) { srcSel.innerHTML += '<option value="' + _escHtml(s) + '">' + _escHtml(s) + '</option>'; });
  catSel.value = oldCat; srcSel.value = oldSrc;
}

function filterAiKBTable() { _aiKBRenderTable(); }

function toggleAiKBSummary(rowId) {
  var row = document.getElementById(rowId);
  if (row) row.style.display = row.style.display === 'none' ? '' : 'none';
}

function sortAiKBTable(col) {
  if (_aiKBSortCol === col) { _aiKBSortAsc = !_aiKBSortAsc; }
  else { _aiKBSortCol = col; _aiKBSortAsc = true; }
  _aiKBRenderTable();
}

async function runAiNewsKBScan() {
  var btn = document.getElementById('btnAiKBScan');
  var status = document.getElementById('aiKBStatus');
  btn.disabled = true;
  status.textContent = 'Scanning report folders and categorizing with AI...';
  try {
    var resp = await fetch('/api/toolbar/ai-news-kb/scan', { method: 'POST' });
    var d = await resp.json();
    if (!resp.ok) { status.textContent = 'Error: ' + (d.error || 'scan failed'); return; }
    status.textContent = d.new_count + ' new items added.';
    document.getElementById('aiKBStats').textContent = d.total + ' items | Last scan: ' + d.last_scanned;
    var resp2 = await fetch('/api/toolbar/ai-news-kb');
    var d2 = await resp2.json();
    _aiKBItems = d2.items || [];
    _aiKBRenderTable();
    _aiKBUpdateFilters();
    document.getElementById('btnAiKBSummary').disabled = _aiKBItems.length === 0;
  } catch (e) {
    status.textContent = 'Error: ' + e.message;
  } finally {
    btn.disabled = false;
  }
}

function _simpleMarkdownToHtml(text) {
  var s = _escHtml(text);
  s = s.replace(/^### (.+)$/gm, '<h4 style="color:#60a5fa;margin:10px 0 4px">$1</h4>');
  s = s.replace(/^## (.+)$/gm, '<h3 style="color:#60a5fa;margin:12px 0 6px">$1</h3>');
  s = s.replace(/^# (.+)$/gm, '<h2 style="color:#60a5fa;margin:14px 0 6px">$1</h2>');
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong style="color:#e0e0e0">$1</strong>');
  s = s.replace(/^- (.+)$/gm, '<li style="margin:2px 0;margin-left:16px">$1</li>');
  s = s.replace(/^(\d+)\. (.+)$/gm, '<li style="margin:2px 0;margin-left:16px">$1. $2</li>');
  s = s.replace(/\n/g, '<br>');
  return s;
}

async function runAiNewsKBSummary() {
  var btn = document.getElementById('btnAiKBSummary');
  var status = document.getElementById('aiKBStatus');
  var resultEl = document.getElementById('aiKBSummaryResult');
  btn.disabled = true;
  status.textContent = 'Generating AI summary...';
  resultEl.style.display = 'block';
  resultEl.innerHTML = '';
  var fullText = '';
  try {
    var resp = await fetch('/api/toolbar/ai-news-kb/summary', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'
    });
    if (!resp.ok) {
      var errJ = await resp.json().catch(function(){return {};});
      resultEl.textContent = 'Error: ' + (errJ.error || resp.statusText);
      status.textContent = '';
      return;
    }
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      var lines = decoder.decode(chunk.value, {stream: true}).split('\\n');
      lines.forEach(function(line) {
        if (line.startsWith('data: ')) {
          try {
            var ev = JSON.parse(line.substring(6));
            if (ev.type === 'token') { fullText += ev.content || ''; resultEl.innerHTML = _simpleMarkdownToHtml(fullText); }
            if (ev.type === 'done') { fullText = ev.content || fullText; resultEl.innerHTML = _simpleMarkdownToHtml(fullText); }
            if (ev.type === 'error') { resultEl.textContent = 'Error: ' + (ev.message || 'unknown'); }
          } catch(e) {}
        }
      });
    }
    status.textContent = '';
    addSystemMessage('AI News KB', 'Summary generated. See the AI News KB modal for details.');
  } catch (e) {
    resultEl.textContent = 'Error: ' + e.message;
    status.textContent = '';
  } finally {
    btn.disabled = false;
  }
}

async function loadDonorAnalysis() {
  var cmv = document.getElementById('donorCmvFilter').value;
  var btn = document.getElementById('btnDonorLoad');
  btn.disabled = true; btn.textContent = 'Loading...';
  document.getElementById('donorTableWrap').innerHTML = '<p style="font-size:0.82em;color:#8b8fa4">Scoring donors...</p>';
  try {
    var resp = await fetch('/api/donor-analysis?recipient_cmv=' + cmv);
    var data = await resp.json();
    if (data.error) { document.getElementById('donorTableWrap').innerHTML = '<p style="color:#f87171">' + escHtml(data.error) + '</p>'; return; }
    _donorData = data;
    document.getElementById('donorCount').textContent = data.count + ' donors scored';
    document.getElementById('btnDonorTop10').disabled = false;
    document.getElementById('btnDonorPdf').disabled = false;
    renderDonorTable(data.donors);
  } catch(e) {
    document.getElementById('donorTableWrap').innerHTML = '<p style="color:#f87171">Error: ' + escHtml(e.message) + '</p>';
  } finally { btn.disabled = false; btn.textContent = 'Load & Score'; }
}

function renderDonorTable(donors) {
  var cols = ['#','ID','Score','Race','Ethnicity','Height','Eyes','Hair','Blood','CMV','Ship From','Profile','Face Match','Genetic','Stock'];
  var html = '<table style="width:100%;border-collapse:collapse;font-size:0.75em;color:#c4c8f0"><thead><tr>';
  cols.forEach(function(c) { html += '<th style="padding:4px 6px;background:#2a2d3a;color:#60a5fa;position:sticky;top:0;text-align:left;white-space:nowrap">' + c + '</th>'; });
  html += '</tr></thead><tbody>';
  donors.forEach(function(d, i) {
    var sc = d._total_score || 0;
    var bg = i % 2 === 0 ? '#1a1d2e' : '#1e2030';
    var scoreColor = sc >= 80 ? '#4ade80' : sc >= 60 ? '#60a5fa' : sc >= 40 ? '#fbbf24' : '#f87171';
    var stockCount = 0;
    (d.stock || []).forEach(function(s) { var nums = (s.details||'').match(/\\d+/g); if(nums) nums.forEach(function(n){stockCount+=parseInt(n)}); });
    html += '<tr style="background:' + bg + '">';
    html += '<td style="padding:3px 6px">' + (i+1) + '</td>';
    html += '<td style="padding:3px 6px"><a href="' + escHtml(d.url||'') + '" target="_blank" style="color:#60a5fa">' + escHtml(d.donor_id||'') + '</a></td>';
    html += '<td style="padding:3px 6px;color:' + scoreColor + ';font-weight:bold">' + sc.toFixed(0) + '</td>';
    html += '<td style="padding:3px 6px">' + escHtml(d.race||'') + '</td>';
    html += '<td style="padding:3px 6px">' + escHtml(d.ethnicity||'') + '</td>';
    html += '<td style="padding:3px 6px">' + escHtml(d.height__cm||'') + '</td>';
    html += '<td style="padding:3px 6px">' + escHtml(d.eye_colour||'') + '</td>';
    html += '<td style="padding:3px 6px">' + escHtml(d.hair_colour||'') + '</td>';
    html += '<td style="padding:3px 6px">' + escHtml(d.blood_type||'') + '</td>';
    html += '<td style="padding:3px 6px">' + escHtml(d.cmv_status||'') + '</td>';
    html += '<td style="padding:3px 6px">' + escHtml(d.shipped_from||'') + '</td>';
    html += '<td style="padding:3px 6px">' + escHtml(d.profile_type||'') + '</td>';
    html += '<td style="padding:3px 6px">' + escHtml(d.cryos_face_matching||'') + '</td>';
    html += '<td style="padding:3px 6px">' + escHtml(d.genetic_matching||'') + '</td>';
    html += '<td style="padding:3px 6px">' + stockCount + '</td>';
    html += '</tr>';
  });
  html += '</tbody></table>';
  document.getElementById('donorTableWrap').innerHTML = html;
}

async function donorTop10() {
  if (!_donorData) return;
  var btn = document.getElementById('btnDonorTop10');
  btn.disabled = true; btn.textContent = 'Analyzing with qwen3-vl:8b...';
  var resultEl = document.getElementById('donorTop10Result');
  resultEl.style.display = 'block';
  resultEl.textContent = 'Sending top 20 donors to qwen3-vl:8b for deep analysis... (this may take a few minutes)';
  try {
    var resp = await fetch('/api/donor-analysis/ai-reason', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({top_n: 20, recipient_cmv: document.getElementById('donorCmvFilter').value})
    });
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var fullText = '';
    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      var lines = decoder.decode(chunk.value, {stream: true}).split('\\n');
      lines.forEach(function(line) {
        if (line.startsWith('data: ')) {
          try {
            var ev = JSON.parse(line.substring(6));
            if (ev.type === 'token') { fullText += ev.content || ''; resultEl.textContent = fullText; }
            if (ev.type === 'done') { fullText = ev.content || fullText; resultEl.textContent = fullText; }
            if (ev.type === 'error') { resultEl.textContent = 'Error: ' + (ev.message||'unknown'); }
          } catch(e) {}
        }
      });
    }
    _donorData._reasonText = fullText;
  } catch(e) {
    resultEl.textContent = 'Error: ' + e.message;
  } finally { btn.disabled = false; btn.textContent = 'Top 20 + AI Reasoning'; }
}

async function donorExportPdf() {
  if (!_donorData) return;
  var btn = document.getElementById('btnDonorPdf');
  btn.disabled = true; btn.textContent = 'Generating PDF...';
  try {
    var resp = await fetch('/api/donor-analysis/pdf', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        top_n: 20,
        recipient_cmv: document.getElementById('donorCmvFilter').value,
        reason_text: _donorData._reasonText || '',
        language: document.getElementById('donorPdfLang').value
      })
    });
    var data = await resp.json();
    if (data.error) { showToast('PDF error: ' + data.error); return; }
    showToast('PDF generated!');
    window.open(data.pdf_url, '_blank');
  } catch(e) { showToast('Error: ' + e.message); }
  finally { btn.disabled = false; btn.textContent = 'Export PDF'; }
}

var _audioSelectedType = '';
var _audioTypeLabels = {
  'news_item': 'AI Briefings / News',
  'raw_content': 'Raw Articles',
  'wiki_page': 'Wiki Pages',
  'code_doc': 'Code Documentation',
  'book_chapter': 'Books / Learning',
  'project_doc': 'Project Docs'
};

function openAudioKnowledgeModal() {
  document.getElementById('audioStep1').style.display = '';
  document.getElementById('audioStep2').style.display = 'none';
  document.querySelectorAll('input[name="audioSourceType"]').forEach(function(r) { r.checked = false; });
  document.getElementById('audioKnowledgeModal').classList.add('open');
  _loadAudioHistory();
}
var _audioHistoryData = [];
async function _loadAudioHistory() {
  var section = document.getElementById('audioHistorySection');
  try {
    var r = await fetch('/api/toolbar/audio-knowledge/history');
    var d = await r.json();
    _audioHistoryData = d.history || [];
    if (_audioHistoryData.length === 0) { section.style.display = 'none'; return; }
    document.getElementById('audioHistoryDate').value = '';
    _renderAudioHistory(_audioHistoryData);
    section.style.display = '';
  } catch (e) { section.style.display = 'none'; }
}
function _filterAudioHistory() {
  var dateVal = document.getElementById('audioHistoryDate').value;
  if (!dateVal) { _renderAudioHistory(_audioHistoryData); return; }
  _renderAudioHistory(_audioHistoryData.filter(function(h) { return h.date === dateVal; }));
}
function _renderAudioHistory(items) {
  var list = document.getElementById('audioHistoryList');
  list.innerHTML = '';
  if (items.length === 0) {
    list.innerHTML = '<div style="font-size:0.78em;color:#6b7280;padding:6px">No audio files for this date.</div>';
    return;
  }
  items.forEach(function(h) {
    var row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 8px;background:#1a1d28;border-radius:6px';
    row.innerHTML = '<audio controls preload="none" style="height:28px;flex:1" src="' + escHtml(h.url) + '"></audio>' +
      '<span style="font-size:0.75em;color:#8b8fa4;white-space:nowrap">' + escHtml(h.display) + '</span>' +
      '<span style="font-size:0.70em;color:#6b7280">' + h.size_kb + 'KB</span>' +
      '<a href="' + escHtml(h.url) + '" download style="font-size:0.72em;color:#60a5fa;text-decoration:none" title="Download">&#8681;</a>';
    list.appendChild(row);
  });
}
function closeAudioKnowledgeModal() {
  document.getElementById('audioKnowledgeModal').classList.remove('open');
}

async function audioStepNext() {
  var sel = document.querySelector('input[name="audioSourceType"]:checked');
  if (!sel) { showToast('Select a content source first'); return; }
  _audioSelectedType = sel.value;
  document.getElementById('audioStep2TypeLabel').textContent = _audioTypeLabels[_audioSelectedType] || _audioSelectedType;
  document.getElementById('audioStep1').style.display = 'none';
  document.getElementById('audioStep2').style.display = '';
  document.getElementById('audioItemsLoading').style.display = 'flex';
  document.getElementById('audioItemsContainer').style.display = 'none';
  document.getElementById('audioProgress').style.display = 'none';
  document.getElementById('audioResult').style.display = 'none';
  document.getElementById('btnGenerateAudio').disabled = false;

  try {
    var r = await fetch('/api/toolbar/audio-knowledge/items?type=' + encodeURIComponent(_audioSelectedType));
    var d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Failed to load items');
    _renderAudioItems(d.items, d.show_dates, _audioSelectedType === 'book_chapter');
  } catch (e) {
    document.getElementById('audioItemsLoading').style.display = 'none';
    document.getElementById('audioItemsContainer').style.display = 'block';
    document.getElementById('audioItemsList').innerHTML = '<div style="color:#f87171;font-size:0.82em">Error loading items: ' + escHtml(e.message) + '</div>';
  }
}

function _renderAudioItems(items, showDates, isBook) {
  var list = document.getElementById('audioItemsList');
  list.innerHTML = '';
  if (!items || items.length === 0) {
    list.innerHTML = '<div style="color:#9ca3af;font-size:0.82em;padding:8px">No items found for this source type.</div>';
    document.getElementById('audioItemsLoading').style.display = 'none';
    document.getElementById('audioItemsContainer').style.display = 'block';
    document.getElementById('audioItemCount').textContent = '0 items';
    return;
  }
  var totalCount = 0;
  items.forEach(function(group) {
    if (isBook && group.chunks && group.chunks.length > 0) {
      var header = document.createElement('div');
      header.style.cssText = 'font-size:0.82em;font-weight:600;color:#c4c8f0;padding:6px 0 2px;border-bottom:1px solid #2a2d3a;margin-top:8px';
      header.textContent = group.parent_title + ' (' + group.chunks.length + ' chapters)';
      list.appendChild(header);
      group.chunks.forEach(function(ch) {
        totalCount++;
        var lbl = document.createElement('label');
        lbl.className = 'wiki-user-check';
        lbl.style.cssText = 'padding:4px 8px 4px 20px;font-size:0.80em';
        lbl.innerHTML = '<input type="checkbox" class="audio-item-cb" value="' + escHtml(group.parent_title) + '" data-chapter="' + escHtml(ch.title) + '" checked> ' + escHtml(ch.title);
        list.appendChild(lbl);
      });
    } else {
      totalCount++;
      var lbl = document.createElement('label');
      lbl.className = 'wiki-user-check';
      lbl.style.cssText = 'padding:6px 8px;font-size:0.82em';
      var dateStr = (showDates && group.date) ? ' <span style="color:#6b7280;font-size:0.9em">(' + escHtml(group.date) + ')</span>' : '';
      var countStr = ' <span style="color:#6b7280;font-size:0.85em">[' + group.chunk_count + ' chunks]</span>';
      lbl.innerHTML = '<input type="checkbox" class="audio-item-cb" value="' + escHtml(group.parent_title) + '" checked> ' + escHtml(group.parent_title) + dateStr + countStr;
      list.appendChild(lbl);
    }
  });
  document.getElementById('audioItemsLoading').style.display = 'none';
  document.getElementById('audioItemsContainer').style.display = 'block';
  document.getElementById('audioItemCount').textContent = totalCount + ' items';
}

function audioSelectAll() {
  document.querySelectorAll('.audio-item-cb').forEach(function(cb) { cb.checked = true; });
}
function audioSelectNone() {
  document.querySelectorAll('.audio-item-cb').forEach(function(cb) { cb.checked = false; });
}

function audioStepBack() {
  document.getElementById('audioStep2').style.display = 'none';
  document.getElementById('audioStep1').style.display = '';
}

async function startAudioKnowledge() {
  var checks = document.querySelectorAll('.audio-item-cb:checked');
  if (checks.length === 0) { showToast('Select at least one item'); return; }
  var parentSet = new Set();
  checks.forEach(function(cb) { parentSet.add(cb.value); });
  var selectedParents = Array.from(parentSet);
  var language = document.getElementById('audioLanguage').value;

  document.getElementById('btnGenerateAudio').disabled = true;
  var progressEl = document.getElementById('audioProgress');
  var progressText = document.getElementById('audioProgressText');
  var resultEl = document.getElementById('audioResult');
  progressEl.style.display = 'block';
  resultEl.style.display = 'none';
  progressText.textContent = 'Submitting request...';
  progressEl.querySelector('.mini-spin').style.display = '';

  try {
    var r = await fetch('/api/toolbar/audio-knowledge', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ item_type: _audioSelectedType, selected_parents: selectedParents, language: language }),
    });
    var d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Request failed');
    var jobId = d.job_id;
    progressText.textContent = 'Searching knowledge base...';

    var poll = setInterval(async function() {
      try {
        var sr = await fetch('/api/toolbar/audio-knowledge/' + jobId);
        var sj = await sr.json();
        if (sj.status === 'searching') {
          progressText.textContent = 'Searching knowledge base...';
        } else if (sj.status === 'searching_web') {
          progressText.textContent = 'Found ' + (sj.items_found || '?') + ' items. Searching web for latest updates...';
        } else if (sj.status === 'generating_script') {
          progressText.textContent = 'Generating narration script (RAG + web)...';
        } else if (sj.status === 'generating_audio') {
          progressText.textContent = 'Narration ready (' + (sj.narration_length || '?') + ' chars). Generating audio...';
        } else if (sj.status === 'done') {
          clearInterval(poll);
          progressEl.querySelector('.mini-spin').style.display = 'none';
          if (sj.error) {
            progressText.textContent = 'Failed: ' + sj.error;
            document.getElementById('btnGenerateAudio').disabled = false;
          } else {
            progressText.textContent = 'Audio generated!';
            resultEl.style.display = 'block';
            resultEl.innerHTML = '<audio controls style="width:100%;margin-bottom:8px" src="' + escHtml(sj.output_url) + '"></audio>' +
              '<div style="font-size:0.78em;color:#8b8fa4">' +
              '<a href="' + escHtml(sj.output_url) + '" download style="color:#60a5fa;text-decoration:none">Download MP3</a>' +
              (sj.narration_preview ? ' | Preview: ' + escHtml(sj.narration_preview.substring(0, 200)) + '...' : '') +
              '</div>';
            addSystemMessage('Audio from Knowledge', 'Audio generated from ' + (sj.items_found || '?') + ' knowledge items (' + (_audioTypeLabels[_audioSelectedType] || _audioSelectedType) + '). Listen above or download the MP3.');
          }
        }
      } catch (pe) { /* polling error, retry */ }
    }, 2000);
  } catch (e) {
    progressText.textContent = 'Error: ' + e.message;
    document.getElementById('btnGenerateAudio').disabled = false;
  }
}

function modalSelectAll(listId) {
  document.querySelectorAll('#' + listId + ' input[type="checkbox"]').forEach(function(cb) { cb.checked = true; });
}
function modalSelectNone(listId) {
  document.querySelectorAll('#' + listId + ' input[type="checkbox"]').forEach(function(cb) { cb.checked = false; });
}
function _initDateRange(fromId, toId, defaultDays) {
  const today = new Date();
  const past = new Date(today);
  past.setDate(past.getDate() - defaultDays);
  const toEl = document.getElementById(toId);
  const fromEl = document.getElementById(fromId);
  if (toEl && !toEl.value) toEl.value = today.toISOString().slice(0, 10);
  if (fromEl && !fromEl.value) fromEl.value = past.toISOString().slice(0, 10);
}
function _getSelectedMembers(listId) {
  const checks = document.querySelectorAll('#' + listId + ' input[type="checkbox"]:checked');
  return Array.from(checks).map(function(cb) { return cb.value; });
}
function _dateRangeToHours(fromId, toId) {
  const from = document.getElementById(fromId).value;
  const to = document.getElementById(toId).value;
  if (!from || !to) return 48;
  const ms = new Date(to + 'T23:59:59').getTime() - new Date(from + 'T00:00:00').getTime();
  return Math.max(1, Math.ceil(ms / 3600000));
}
function _dateRangeLabel(fromId, toId) {
  const from = document.getElementById(fromId).value || '?';
  const to = document.getElementById(toId).value || '?';
  return from + ' to ' + to;
}

function openCommitSummaryModal() {
  _initDateRange('commitDateFrom', 'commitDateTo', 2);
  document.getElementById('commitSummaryModal').classList.add('open');
}
function closeCommitSummaryModal() {
  document.getElementById('commitSummaryModal').classList.remove('open');
}
async function startCommitSummary() {
  const members = _getSelectedMembers('commitMemberList');
  if (members.length === 0) { showToast('Select at least one team member'); return; }
  const fromDate = document.getElementById('commitDateFrom').value || '';
  const toDate = document.getElementById('commitDateTo').value || '';
  const range = _dateRangeLabel('commitDateFrom', 'commitDateTo');
  closeCommitSummaryModal();
  await newChat();
  showToast('Fetching commits for ' + members.length + ' member(s) — scanning repos…');
  try {
    const r = await fetch('/api/toolbar/commit-summary', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ since_date: fromDate, until_date: toDate, authors: members }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Request failed');
    const report = d.result || '';
    if (!report || report.includes('No commits found')) {
      addSystemMessage('Commit Summary (' + range + ')', report || 'No commits found.');
      showToast('No commits found for selected members in this date range');
      return;
    }
    addCollapsibleSystemMessage('Commit Summary (' + range + ')', report, 12);
    conversationHistory.push({role: 'assistant', content: '[Git Commits ' + range + ']\n' + report});
    showToast('Generating commit analysis…');
    if (!isStreaming) {
      queryInput.value = 'IMPORTANT: Use ONLY the latest commit data block above (the one marked [Git Commits ' + range + ']). Ignore any older commit data in the conversation. Summarize the commits for ' + members.join(', ') + ' (' + range + '): group by person and repository, highlight key changes, areas of focus, and notable patterns. Do NOT invent job titles or roles for anyone.';
      sendMessage();
    }
  } catch (e) {
    showToast('Commit fetch failed: ' + e.message);
  }
}

function openTeamActivityModal() {
  _initDateRange('activityDateFrom', 'activityDateTo', 7);
  document.getElementById('teamActivityModal').classList.add('open');
}
function closeTeamActivityModal() {
  document.getElementById('teamActivityModal').classList.remove('open');
}
async function startTeamActivity() {
  const members = _getSelectedMembers('activityMemberList');
  if (members.length === 0) { showToast('Select at least one team member'); return; }
  const fromDate = document.getElementById('activityDateFrom').value || '';
  const toDate = document.getElementById('activityDateTo').value || '';
  const range = _dateRangeLabel('activityDateFrom', 'activityDateTo');
  closeTeamActivityModal();
  await newChat();
  showToast('Fetching activity data for ' + members.length + ' member(s)…');
  let commitReport = '';
  try {
    const r = await fetch('/api/toolbar/commit-summary', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ since_date: fromDate, until_date: toDate, authors: members }),
    });
    const d = await r.json();
    if (r.ok) commitReport = d.result || '';
  } catch (e) { /* commit fetch is optional */ }
  if (commitReport) {
    addCollapsibleSystemMessage('Team Commits (' + range + ')', commitReport, 12);
    conversationHistory.push({role: 'assistant', content: '[Git Commits ' + range + ']\n' + commitReport});
  }
  showToast('Generating team activity report…');
  if (!isStreaming) {
    let prompt = 'IMPORTANT: Use ONLY the latest commit data block above. Ignore any older data in the conversation. Show comprehensive team activity for ' + members.join(', ') + ' from ' + range + '. ';
    if (commitReport) {
      prompt += 'Git commit data is shown above — summarize ALL commits, not just the preview. ';
    }
    prompt += 'Also search for their Jira ticket updates, wiki page changes, and any other tracked activity. Group everything by person with sections for commits, Jira, and wiki. Do NOT invent job titles or roles for anyone.';
    queryInput.value = prompt;
    sendMessage();
  }
}

(function() {
  document.addEventListener('keydown', function(ev) {
    if (ev.key === 'Escape') {
      document.querySelectorAll('.modal-overlay.open').forEach(function(m) { m.classList.remove('open'); });
    }
  });
})();

function formatSessionTime(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return iso; }
}

function renderSessionList(sessions) {
  const el = document.getElementById('sessionList');
  if (!el) return;
  el.innerHTML = '';
  for (const s of sessions) {
    const div = document.createElement('div');
    div.className = 'session-item' + (s.id === currentSessionId ? ' active' : '');
    div.dataset.sessionId = s.id;
    div.onclick = function() { selectSession(s.id); };
    const titleEl = document.createElement('div');
    titleEl.className = 'session-title';
    const isLearning = s.session_type === 'ai_learning' || s.session_type === 'english_learning' || s.session_type === 'casual_english';
    const icon = s.session_type === 'ai_learning' ? '\u{1F393} ' : s.session_type === 'english_learning' ? '\u{1F4BB} ' : s.session_type === 'casual_english' ? '\u{1F30D} ' : '';
    titleEl.textContent = icon + (s.title || 'Chat');
    if (isLearning) titleEl.style.fontWeight = '600';
    const timeEl = document.createElement('div');
    timeEl.className = 'session-time';
    timeEl.textContent = formatSessionTime(s.updated_at || s.created_at);
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'session-del';
    del.title = 'Delete';
    del.innerHTML = '&times;';
    del.onclick = function(ev) { ev.stopPropagation(); deleteSessionById(s.id); };
    div.appendChild(titleEl);
    div.appendChild(timeEl);
    div.appendChild(del);
    el.appendChild(div);
  }
}

async function refreshSessionList() {
  try {
    const listR = await fetch('/api/sessions');
    const listD = await listR.json();
    renderSessionList(listD.sessions || []);
  } catch (e) { console.error(e); }
}

async function loadSession(id) {
  if (!id) return;
  try {
    const r = await fetch('/api/sessions/' + encodeURIComponent(id));
    if (!r.ok) return;
    const s = await r.json();
    currentSessionId = s.id;
    conversationHistory = [];
    chatEl.innerHTML = '';
    const msgs = s.messages || [];
    for (const m of msgs) {
      if (m.role !== 'user' && m.role !== 'assistant') continue;
      const c = m.content || '';
      if (m.role === 'user') {
        addMessage('user', c, null);
        conversationHistory.push({ role: 'user', content: c });
      } else {
        addMessage('assistant', c, null);
        conversationHistory.push({ role: 'assistant', content: c });
      }
    }
    await refreshSessionList();
  } catch (e) { console.error(e); }
}

async function selectSession(id) {
  await loadSession(id);
  closeSidebarMobile();
}

async function newChat() {
  try {
    const r = await fetch('/api/sessions', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({}) });
    if (!r.ok) return;
    const s = await r.json();
    currentSessionId = s.id;
    conversationHistory = [];
    chatEl.innerHTML = '';
    removeImage();
    await refreshSessionList();
    closeSidebarMobile();
  } catch (e) { console.error(e); }
}

async function deleteSessionById(id) {
  try {
    const r = await fetch('/api/sessions/' + encodeURIComponent(id), { method: 'DELETE' });
    if (!r.ok) return;
    let listR = await fetch('/api/sessions');
    let listD = await listR.json();
    let sessions = listD.sessions || [];
    if (id === currentSessionId) {
      if (sessions[0]) {
        await loadSession(sessions[0].id);
      } else {
        const cr = await fetch('/api/sessions', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({}) });
        if (cr.ok) {
          const ns = await cr.json();
          currentSessionId = ns.id;
          conversationHistory = [];
          chatEl.innerHTML = '';
          listR = await fetch('/api/sessions');
          listD = await listR.json();
          sessions = listD.sessions || [];
        }
      }
    }
    renderSessionList(sessions);
  } catch (e) { console.error(e); }
}

async function persistExchange(userText, assistantText) {
  if (!currentSessionId) return;
  try {
    const pr = await fetch('/api/sessions/' + encodeURIComponent(currentSessionId) + '/messages', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ user_message: userText, assistant_message: assistantText || '' }),
    });
    if (!pr.ok) return;
    await refreshSessionList();
  } catch (e) { console.error(e); }
}

async function initSessions() {
  applySidebarClass();
  try {
    let r = await fetch('/api/sessions');
    let data = await r.json();
    let sessions = data.sessions || [];
    if (sessions.length === 0) {
      const cr = await fetch('/api/sessions', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({}) });
      if (!cr.ok) throw new Error('Could not create session');
      r = await fetch('/api/sessions');
      data = await r.json();
      sessions = data.sessions || [];
    }
    renderSessionList(sessions);
    if (sessions[0]) await loadSession(sessions[0].id);
  } catch (e) {
    console.error(e);
    currentSessionId = null;
  }
}

queryInput.addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 200) + 'px';
});
queryInput.addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function renderMarkdown(text) {
  var codeBlocks = [];
  text = text.replace(/```(\w*)\n([\s\S]*?)```/g, function(_, lang, code) {
    var ph = '\x00CB' + codeBlocks.length + '\x00';
    codeBlocks.push('<pre style="background:#0d1017;padding:12px;border-radius:6px;overflow-x:auto;margin:8px 0;border:1px solid #2a2d3a"><code>' + escHtml(code.trim()) + '</code></pre>');
    return ph;
  });
  text = text.replace(/`([^`]+)`/g, '<code style="background:#2a2d3a;padding:1px 5px;border-radius:3px;font-size:0.9em">$1</code>');
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, function(m, label, url) {
    if (/^(https?:|mailto:|\/)/i.test(url)) return '<a href="' + url.replace(/"/g,'&quot;') + '" target="_blank">' + label + '</a>';
    return label;
  });
  text = text.replace(/^### (.+)$/gm, '<h4 style="margin:8px 0 4px;color:#c4c8f0">$1</h4>');
  text = text.replace(/^## (.+)$/gm, '<h3 style="margin:10px 0 4px;color:#c4c8f0">$1</h3>');
  text = text.replace(/^# (.+)$/gm, '<h2 style="margin:12px 0 6px;color:#c4c8f0">$1</h2>');
  text = text.replace(/^- (.+)$/gm, '&bull; $1');
  text = text.replace(/^\d+\. (.+)$/gm, function(m) { return m; });
  text = text.replace(/\n/g, '<br>');
  for (var i = 0; i < codeBlocks.length; i++) {
    text = text.replace('\x00CB' + i + '\x00', codeBlocks[i]);
  }
  return text;
}

function addMessage(role, content, imageDataUrl) {
  const div = document.createElement('div');
  div.className = 'msg msg-' + role;
  if (role === 'user') {
    div.textContent = content;
    if (imageDataUrl) {
      const img = document.createElement('img');
      img.src = imageDataUrl;
      img.className = 'msg-user-img';
      div.appendChild(img);
    }
  } else {
    div.innerHTML = renderMarkdown(content);
    const actions = document.createElement('div');
    actions.className = 'msg-actions';
    const noteBtn = document.createElement('button');
    noteBtn.className = 'note-btn';
    noteBtn.title = 'Save to Notes';
    noteBtn.innerHTML = '&#128278;';
    noteBtn.onclick = function() { saveToNotes(content); };
    actions.appendChild(noteBtn);
    div.appendChild(actions);
  }
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
  return div;
}

function addThinking(toolName, args) {
  const div = document.createElement('div');
  div.className = 'thinking';
  const argsStr = Object.entries(args || {}).map(([k,v]) => k+'='+JSON.stringify(v)).join(', ');
  div.innerHTML = '<div class="spinner"></div> Calling <span class="tool-badge">' +
    escHtml(toolName) + '</span>' + (argsStr ? ' <span style="color:#666">(' + escHtml(argsStr.substring(0,120)) + ')</span>' : '');
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
  return div;
}

function addSources(sources, parentEl) {
  if (!sources || sources.length === 0) return;
  const unique = [];
  const seen = new Set();
  for (const s of sources) {
    const key = s.source + '|' + s.title;
    if (!seen.has(key)) { seen.add(key); unique.push(s); }
  }
  if (unique.length === 0) return;
  const details = document.createElement('div');
  details.className = 'sources';
  details.innerHTML = '<details><summary>Sources (' + unique.length + ')</summary>' +
    unique.map(s => '<div class="src-item">[' + escHtml(s.source) + '] ' + escHtml(s.title) + '</div>').join('') +
    '</details>';
  parentEl.insertAdjacentElement('afterend', details);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function handleImage(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(e) {
    const dataUrl = e.target.result;
    document.getElementById('imgThumb').src = dataUrl;
    document.getElementById('imgPreview').style.display = 'inline-block';
    document.getElementById('imgBtn').classList.add('has-img');
    const raw = dataUrl.split(',')[1];
    const img = new Image();
    img.onload = function() {
      if (img.width <= 1024 && img.height <= 1024) {
        currentImageB64 = raw;
        return;
      }
      const scale = Math.min(1024/img.width, 1024/img.height);
      const canvas = document.createElement('canvas');
      canvas.width = img.width * scale;
      canvas.height = img.height * scale;
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
      currentImageB64 = canvas.toDataURL('image/jpeg', 0.85).split(',')[1];
    };
    img.src = dataUrl;
  };
  reader.readAsDataURL(file);
}

function removeImage() {
  currentImageB64 = null;
  document.getElementById('imgPreview').style.display = 'none';
  document.getElementById('imgBtn').classList.remove('has-img');
  document.getElementById('imgInput').value = '';
}

async function sendMessage() {
  const query = queryInput.value.trim();
  if (!query || isStreaming) return;
  isStreaming = true;
  sendBtn.disabled = true;
  lastOutgoingUserText = query;

  const imageDataUrl = currentImageB64 ? document.getElementById('imgThumb').src : null;
  addMessage('user', query, imageDataUrl);
  conversationHistory.push({role: 'user', content: query});
  queryInput.value = '';
  queryInput.style.height = 'auto';

  const body = {query, history: conversationHistory.slice(0, -1), session_id: currentSessionId};
  if (currentImageB64) body.image = currentImageB64;
  removeImage();

  let thinkingEls = [];
  let assistantDiv = null;
  let fullContent = '';

  try {
    const resp = await fetch('/api/agent', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') continue;
        let event;
        try { event = JSON.parse(payload); } catch { continue; }

        if (event.type === 'model') {
          // show which model is being used
        } else if (event.type === 'thinking') {
          thinkingEls.push(addThinking(event.tool, event.args));
        } else if (event.type === 'tool_result') {
          // keep thinking indicators visible
        } else if (event.type === 'token') {
          if (!assistantDiv) {
            thinkingEls.forEach(el => el.remove());
            thinkingEls = [];
            assistantDiv = document.createElement('div');
            assistantDiv.className = 'msg msg-assistant';
            chatEl.appendChild(assistantDiv);
          }
          fullContent += event.content;
          assistantDiv.innerHTML = renderMarkdown(fullContent);
          chatEl.scrollTop = chatEl.scrollHeight;
        } else if (event.type === 'answer_done') {
          if (!assistantDiv) {
            thinkingEls.forEach(el => el.remove());
            assistantDiv = addMessage('assistant', fullContent || '(no response)');
          } else {
            const actions = document.createElement('div');
            actions.className = 'msg-actions';
            const noteBtn = document.createElement('button');
            noteBtn.className = 'note-btn';
            noteBtn.title = 'Save to Notes';
            noteBtn.innerHTML = '&#128278;';
            const fc = fullContent;
            noteBtn.onclick = function() { saveToNotes(fc); };
            actions.appendChild(noteBtn);
            const contBtn = document.createElement('button');
            contBtn.className = 'note-btn';
            contBtn.title = 'Continue generating';
            contBtn.innerHTML = '&#9654; Continue';
            contBtn.style.fontSize = '12px';
            contBtn.style.marginLeft = '6px';
            contBtn.onclick = function() {
              contBtn.remove();
              var lastChunk = fullContent.slice(-300).replace(/\n/g, ' ');
              queryInput.value = 'Continue from where you stopped. Your last output ended with: "...' + lastChunk + '". Pick up exactly from there and complete the rest. Do NOT repeat what you already said.';
              sendBtn.click();
            };
            actions.appendChild(contBtn);
            assistantDiv.appendChild(actions);
          }
          addSources(event.sources, assistantDiv);
          conversationHistory.push({role: 'assistant', content: fullContent || ''});
          await persistExchange(lastOutgoingUserText, fullContent || '');
        } else if (event.type === 'answer') {
          thinkingEls.forEach(el => el.remove());
          assistantDiv = addMessage('assistant', event.content || '(no response)');
          addSources(event.sources, assistantDiv);
          conversationHistory.push({role: 'assistant', content: event.content || ''});
          await persistExchange(lastOutgoingUserText, event.content || '');
        } else if (event.type === 'error') {
          thinkingEls.forEach(el => el.remove());
          addMessage('assistant', 'Error: ' + (event.message || 'Unknown error'));
        }
      }
    }
  } catch (err) {
    thinkingEls.forEach(el => el.remove());
    addMessage('assistant', 'Connection error: ' + err.message);
  }

  isStreaming = false;
  sendBtn.disabled = false;
  queryInput.focus();
}

async function switchModel(model) {
  try {
    await fetch('/api/switch-model', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({model}),
    });
    checkHealth();
  } catch {}
}

async function openGlobalSettings() {
  document.getElementById('globalSettingsModal').style.display = 'flex';
  document.getElementById('dsTestResult').style.display = 'none';
  try {
    const r = await fetch('/api/settings');
    const d = await r.json();
    document.getElementById('settAudioAi').value = d.audio_lang_ai || 'zh';
    document.getElementById('settAudioWorld').value = d.audio_lang_world || 'zh';
    document.getElementById('settAudioChina').value = d.audio_lang_china || 'zh';
    document.getElementById('settAudioKnowledge').value = d.audio_lang_knowledge || 'zh';
    var masked = d.deepseek_api_key_masked || '';
    var el = document.getElementById('settDeepseekKey');
    el.value = '';
    el.placeholder = masked ? masked : 'sk-...';
    var st = document.getElementById('dsKeyStatus');
    if (masked) { st.textContent = 'Configured'; st.style.background = '#064e3b'; st.style.color = '#10b981'; }
    else { st.textContent = 'Not set'; st.style.background = '#1e293b'; st.style.color = '#8b8fa4'; }
  } catch {}
}
function closeGlobalSettings() { document.getElementById('globalSettingsModal').style.display = 'none'; }
async function saveGlobalSettings() {
  const body = {
    audio_lang_ai: document.getElementById('settAudioAi').value,
    audio_lang_world: document.getElementById('settAudioWorld').value,
    audio_lang_china: document.getElementById('settAudioChina').value,
    audio_lang_knowledge: document.getElementById('settAudioKnowledge').value,
  };
  try {
    await fetch('/api/settings', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
    showToast('Settings saved');
    closeGlobalSettings();
  } catch {}
}
function toggleDsKeyVisibility() {
  var el = document.getElementById('settDeepseekKey');
  el.type = el.type === 'password' ? 'text' : 'password';
}
async function saveDsKey() {
  var key = document.getElementById('settDeepseekKey').value.trim();
  if (!key) { showToast('Please enter an API key'); return; }
  try {
    const r = await fetch('/api/settings/deepseek-key', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({api_key: key}) });
    const d = await r.json();
    if (d.ok) {
      var st = document.getElementById('dsKeyStatus');
      st.textContent = 'Configured'; st.style.background = '#064e3b'; st.style.color = '#10b981';
      document.getElementById('settDeepseekKey').value = '';
      document.getElementById('settDeepseekKey').placeholder = d.masked;
      showToast('API key saved');
    }
  } catch(e) { showToast('Failed to save: ' + e.message); }
}
async function testDsKey() {
  var btn = document.getElementById('btnTestDs');
  var res = document.getElementById('dsTestResult');
  var keyInput = document.getElementById('settDeepseekKey').value.trim();
  btn.disabled = true; btn.textContent = 'Testing...';
  res.style.display = 'block'; res.style.color = '#60a5fa'; res.innerHTML = '&#9203; Connecting to DeepSeek API...';
  try {
    var body = {};
    if (keyInput) body.api_key = keyInput;
    const r = await fetch('/api/deepseek/test', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
    const d = await r.json();
    if (d.ok) {
      res.style.color = '#10b981';
      res.innerHTML = '&#9989; <b>Connection successful!</b><br>Model: ' + d.model +
        '<br>Reply: <em>' + (d.reply||'').substring(0,80) + '</em>' +
        '<br><span style="font-size:0.72em;color:#8b8fa4">Tokens: ' + (d.usage.total_tokens||'?') + '</span>';
    } else {
      res.style.color = '#f87171';
      res.innerHTML = '&#10060; <b>Failed:</b> ' + (d.error||'Unknown error');
    }
  } catch(e) {
    res.style.color = '#f87171';
    res.innerHTML = '&#10060; <b>Error:</b> ' + e.message;
  }
  btn.disabled = false; btn.textContent = '\u26A1 Test';
}
async function clearDsKey() {
  try {
    await fetch('/api/settings/deepseek-key', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({api_key: ''}) });
    var st = document.getElementById('dsKeyStatus');
    st.textContent = 'Not set'; st.style.background = '#1e293b'; st.style.color = '#8b8fa4';
    document.getElementById('settDeepseekKey').value = '';
    document.getElementById('settDeepseekKey').placeholder = 'sk-...';
    document.getElementById('dsTestResult').style.display = 'none';
    showToast('API key cleared');
  } catch {}
}

async function checkHealth() {
  try {
    const resp = await fetch('/api/health');
    const data = await resp.json();
    const modelResp = await fetch('/api/switch-model');
    const modelData = await modelResp.json();
    const sel = document.getElementById('modelSelect');
    if (sel) {
      const cur = modelData.model || '';
      let found = false;
      for (const opt of sel.options) { if (opt.value === cur) { found = true; break; } }
      if (!found && cur) {
        const opt = document.createElement('option');
        opt.value = cur; opt.textContent = cur;
        sel.appendChild(opt);
      }
      sel.value = cur;
    }
    if (data.ollama && data.qdrant) {
      const fastInfo = data.fast_model ? ' (text: ' + data.fast_model + ')' : '';
      statusEl.textContent = (modelData.model || '?') + fastInfo + ' | ' + (data.qdrant_points || 0) + ' chunks';
      statusEl.className = 'status status-ok';
    } else {
      const issues = [];
      if (!data.ollama) issues.push('Ollama offline');
      if (!data.qdrant) issues.push('Qdrant error');
      statusEl.textContent = issues.join(', ');
      statusEl.className = 'status status-err';
    }
  } catch {
    statusEl.textContent = 'Agent offline';
    statusEl.className = 'status status-err';
  }
}
// --- Learning Sessions ---
let _learningOpenLock = null;
async function _openLearning(type, buildWelcome) {
  if (_learningOpenLock) return;
  _learningOpenLock = type;
  try {
    const freshStart = (type === 'english_learning' || type === 'casual_english');
    const [sessR, ctxR] = await Promise.all([
      fetch('/api/toolbar/learning-session', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({type})}),
      fetch('/api/toolbar/learning-context?type=' + type)
    ]);
    if (!sessR.ok) throw new Error('Session API returned ' + sessR.status);
    if (!ctxR.ok) throw new Error('Context API returned ' + ctxR.status);
    const sess = await sessR.json();
    const ctx = await ctxR.json();
    if (sess.id) {
      if (freshStart) {
        await fetch('/api/sessions/' + encodeURIComponent(sess.id) + '/clear', {method:'POST'});
        currentSessionId = sess.id;
        conversationHistory = [];
        chatEl.innerHTML = '';
        await refreshSessionList();
      } else {
        await loadSession(sess.id);
        await refreshSessionList();
      }
    }
    if (freshStart || (sess.messages && sess.messages.length === 0)) {
      const welcomeMsg = buildWelcome(ctx);
      if (welcomeMsg) {
        addMessage('assistant', welcomeMsg, null);
        conversationHistory.push({role:'assistant', content: welcomeMsg});
        await persistExchange('', welcomeMsg);
      }
    }
  } catch(e) { console.error(e); showToast('Failed to open learning session'); }
  finally { _learningOpenLock = null; }
}

async function openAILearning() {
  await _openLearning('ai_learning', function(ctx) {
    if (!ctx.topics || ctx.topics.length === 0) return null;
    let msg = '## AI Learning Roadmap\n\nWelcome! Here are the topics you can learn. Click any topic or type a question to start a deep-dive lesson.\n\n';
    let lastTrack = '', lastLevel = '';
    for (const t of ctx.topics) {
      if (t.track !== lastTrack) { msg += '\n### ' + escHtml(t.track) + '\n'; lastTrack = t.track; lastLevel = ''; }
      if (t.level !== lastLevel) { msg += '\n**' + escHtml(t.level) + '**\n'; lastLevel = t.level; }
      msg += '- ' + escHtml(t.topic) + '\n';
    }
    msg += '\n---\n\nType a topic name to start learning, or ask any question about RAG, LLM, or HuggingFace!';
    return msg;
  });
}

async function openEnglishLearning() {
  await _openLearning('english_learning', function(ctx) {
    const titles = ctx.news_titles || [];
    let msg = '## Tech English Learning\n\nPick a topic and I will analyze the article for you — highlighting key phrases, expressions, and how to discuss it in English.\n\n';
    if (titles.length > 0) {
      msg += '### Recent AI news:\n\n';
      for (let i = 0; i < Math.min(titles.length, 20); i++) {
        msg += (i+1) + '. ' + escHtml(titles[i]) + '\n';
      }
      msg += '\n---\n\nType a number to pick a topic, or paste any text you want me to help you express in English!';
    } else {
      msg += 'No AI news topics available right now. You can still paste any text and I will help you express it in English!\n';
    }
    return msg;
  });
}

async function openCasualEnglish() {
  await _openLearning('casual_english', function(ctx) {
    const items = ctx.news_items || [];
    let msg = '## Casual English Learning\n\nPick a topic and I will analyze the article for you — teaching everyday phrases, idioms, and how native speakers would discuss it.\n\n';
    if (items.length > 0) {
      msg += '### Recent world news:\n\n';
      let lastCat = '';
      for (let i = 0; i < Math.min(items.length, 20); i++) {
        const it = items[i];
        if (it.category !== lastCat) { msg += '\n**' + escHtml(it.category) + '**\n'; lastCat = it.category; }
        msg += (i+1) + '. ' + escHtml(it.title) + '\n';
      }
      msg += '\n---\n\nType a number to pick a topic, or write anything you want to practice expressing in English!';
    } else {
      msg += 'No world news topics available right now. You can still practice by writing anything in English and I will help you improve!\n';
    }
    return msg;
  });
}

async function openAWSCert() {
  await _openLearning('aws_cert', function(ctx) {
    const domains = ctx.domains || [];
    const progress = ctx.progress || {};
    const domainWeights = {'1':'20%','2':'24%','3':'28%','4':'14%','5':'14%'};
    const domainNames = {
      '1':'Fundamentals of AI and ML',
      '2':'Fundamentals of Generative AI',
      '3':'Applications of Foundation Models',
      '4':'Guidelines for Responsible AI',
      '5':'Security, Compliance & Governance'
    };

    let msg = '## AWS Certified AI Practitioner (AIF-C01)\n\n';
    msg += '**Exam:** 65 questions | 90 min | Passing: 700/1000\n\n';

    // Progress summary
    const pd = progress.domains || {};
    let hasProgress = false;
    for (const dn of ['1','2','3','4','5']) {
      const dd = pd[dn] || {};
      if ((dd.topics_taught||[]).length > 0 || (dd.topics_quizzed||[]).length > 0) { hasProgress = true; break; }
    }
    if (hasProgress) {
      msg += '### Your Progress\n\n';
      for (const dn of ['1','2','3','4','5']) {
        const dd = pd[dn] || {};
        const pct = dd.completion_pct || 0;
        const taught = (dd.topics_taught||[]).length;
        const quizzed = (dd.topics_quizzed||[]).length;
        const bar = '\u2588'.repeat(Math.floor(pct/10)) + '\u2591'.repeat(10 - Math.floor(pct/10));
        msg += 'D' + dn + ' (' + domainWeights[dn] + ') ' + bar + ' ' + pct + '% | ' + taught + ' taught, ' + quizzed + ' quizzed\n';
      }
      msg += '\n**Overall Readiness: ' + (progress.overall_readiness||0) + '%**\n\n';
    }

    msg += '### Exam Domains\n\n';
    let lastDomain = '';
    for (const d of domains) {
      if (d.domain !== lastDomain) {
        msg += '\n**' + escHtml(d.domain) + '**\n';
        lastDomain = d.domain;
      }
      if (d.task) msg += '  ' + escHtml(d.task) + '\n';
      msg += '  - ' + escHtml(d.topic) + '\n';
    }

    msg += '\n---\n\n';
    msg += '**Commands:**\n';
    msg += '- `teach me Domain 1` — Start a lesson on any domain\n';
    msg += '- `teach me Amazon Bedrock` — Learn a specific topic\n';
    msg += '- `quiz me on Domain 2` — Take a practice quiz\n';
    msg += '- `progress` — View your study progress\n';
    msg += '- Or just ask any question about the AIF-C01 exam!\n';
    return msg;
  });
}

function toggleNotesPanel() {
  document.getElementById('notesPanel').classList.toggle('open');
  if (document.getElementById('notesPanel').classList.contains('open')) loadNotes();
}

async function loadNotes() {
  const body = document.getElementById('notesBody');
  const tag = document.getElementById('notesFilter').value;
  body.innerHTML = '<div style="text-align:center;color:#666;padding:20px">Loading...</div>';
  try {
    const url = '/api/notes' + (tag ? '?tag=' + encodeURIComponent(tag) : '');
    const r = await fetch(url);
    const notes = await r.json();
    if (!notes.length) {
      body.innerHTML = '<div style="text-align:center;color:#666;padding:40px">No notes yet.<br>Click the 📎 button on any assistant message to save it.</div>';
      return;
    }
    body.innerHTML = '';
    for (const n of notes) {
      const card = document.createElement('div');
      card.className = 'note-card';
      const dateStr = (n.created_at || '').substring(0, 10);
      const tagsHtml = (n.tags || []).map(t => '<span class="note-tag">' + escHtml(t) + '</span>').join('');

      const header = document.createElement('div');
      header.className = 'note-header';
      header.innerHTML = '<span class="note-arrow">&#9654;</span>'
        + '<span class="note-title">' + escHtml(n.title || n.content.substring(0, 80)) + '</span>'
        + '<span class="note-date">' + escHtml(dateStr) + '</span>';
      header.addEventListener('click', function() { card.classList.toggle('open'); });

      const noteBody = document.createElement('div');
      noteBody.className = 'note-body';
      noteBody.innerHTML = '<div class="note-content">' + renderMarkdown(n.content) + '</div>'
        + (tagsHtml ? '<div class="note-tags">' + tagsHtml + '</div>' : '')
        + '<div class="note-actions">'
        + '<button class="note-action-btn edit-btn">&#9998; Edit</button>'
        + '<button class="note-action-btn danger del-btn">&#128465; Delete</button>'
        + '</div>';

      noteBody.querySelector('.del-btn').addEventListener('click', function(e) {
        e.stopPropagation();
        deleteNote(n.id);
      });
      noteBody.querySelector('.edit-btn').addEventListener('click', function(e) {
        e.stopPropagation();
        startEditNote(n.id, n.content, noteBody);
      });

      card.appendChild(header);
      card.appendChild(noteBody);
      body.appendChild(card);
    }
  } catch(e) { body.innerHTML = '<div style="color:#ef4444;padding:20px">Error loading notes</div>'; }
}

function startEditNote(noteId, content, noteBody) {
  const contentDiv = noteBody.querySelector('.note-content');
  const actionsDiv = noteBody.querySelector('.note-actions');
  contentDiv.style.display = 'none';
  if (actionsDiv) actionsDiv.style.display = 'none';

  const editArea = document.createElement('textarea');
  editArea.className = 'note-edit-area';
  editArea.value = content;

  const editActions = document.createElement('div');
  editActions.className = 'note-edit-actions';
  editActions.innerHTML = '<button class="save-btn">Save</button><button class="cancel-btn">Cancel</button>';

  noteBody.appendChild(editArea);
  noteBody.appendChild(editActions);
  editArea.focus();

  editActions.querySelector('.cancel-btn').addEventListener('click', function() {
    editArea.remove();
    editActions.remove();
    contentDiv.style.display = '';
    if (actionsDiv) actionsDiv.style.display = '';
  });
  editActions.querySelector('.save-btn').addEventListener('click', async function() {
    const newContent = editArea.value.trim();
    if (!newContent) { showToast('Content cannot be empty'); return; }
    try {
      const r = await fetch('/api/notes/' + encodeURIComponent(noteId), {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ content: newContent }),
      });
      if (r.ok) {
        showToast('Note updated!');
        loadNotes();
      } else { showToast('Failed to update note'); }
    } catch(e) { showToast('Error updating note'); }
  });
}

async function saveToNotes(content) {
  const sessionType = currentSessionId === '00000000-0000-0000-0000-000000000001' ? 'ai_learning'
    : currentSessionId === '00000000-0000-0000-0000-000000000002' ? 'tech_english'
    : currentSessionId === '00000000-0000-0000-0000-000000000003' ? 'casual_english'
    : currentSessionId === '00000000-0000-0000-0000-000000000004' ? 'aws_cert' : 'general';
  const tags = [sessionType];
  try {
    const r = await fetch('/api/notes', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ content, tags, session_id: currentSessionId, session_type: sessionType }),
    });
    if (r.ok) {
      showToast('Saved to notes!');
    } else {
      showToast('Failed to save note');
    }
  } catch(e) { showToast('Error saving note'); }
}

async function deleteNote(id) {
  if (!confirm('Delete this note?')) return;
  try {
    await fetch('/api/notes/' + encodeURIComponent(id), { method: 'DELETE' });
    loadNotes();
  } catch(e) { showToast('Error deleting note'); }
}

// --- Stock Analysis ---
function openStockModal() {
  document.getElementById('stockAnalysisModal').classList.add('open');
}
function closeStockModal() {
  document.getElementById('stockAnalysisModal').classList.remove('open');
}
function showStockTab(tab) {
  var local = document.getElementById('stockResult');
  var ds = document.getElementById('stockResultDs');
  var btnL = document.getElementById('stockTabLocal');
  var btnD = document.getElementById('stockTabDs');
  if (tab === 'deepseek') {
    local.style.display = 'none'; ds.style.display = 'block';
    btnL.style.background = '#1e293b'; btnL.style.color = '#64748b';
    btnD.style.background = '#3b82f6'; btnD.style.color = 'white';
  } else {
    local.style.display = 'block'; ds.style.display = 'none';
    btnL.style.background = '#3b82f6'; btnL.style.color = 'white';
    btnD.style.background = '#1e293b'; btnD.style.color = '#64748b';
  }
}
async function runStockAnalysis() {
  const sym = document.getElementById('stockSymbolInput').value.trim();
  if (!sym) { showToast('请输入股票代码'); return; }
  const st = document.getElementById('stockStatus');
  const res = document.getElementById('stockResult');
  const resDs = document.getElementById('stockResultDs');
  const tabs = document.getElementById('stockResultTabs');
  const useDs = document.getElementById('stockUseDeepseek').checked;
  st.textContent = '正在分析...（需要1-3分钟）';
  res.innerHTML = '<p style="color:#60a5fa">⏳ 正在获取数据并生成AI预测报告，请稍候...</p>';
  resDs.innerHTML = '';
  tabs.style.display = useDs ? 'block' : 'none';
  resDs.style.display = 'none'; res.style.display = 'block';
  showStockTab('local');
  document.getElementById('btnStockAnalyze').disabled = true;
  try {
    const r = await fetch('/api/stock/analyze', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({symbol: sym, mode: 'full'})});
    const d = await r.json();
    if (d.error) { res.innerHTML = '<p style="color:#f87171">'+d.error+'</p>'; }
    else { res.innerHTML = _renderStockMd(d); }
    st.textContent = useDs ? 'DeepSeek 分析中...' : '';
  } catch(e) { res.innerHTML = '<p style="color:#f87171">请求失败: '+e.message+'</p>'; st.textContent = ''; }
  document.getElementById('btnStockAnalyze').disabled = false;
  if (useDs) {
    resDs.innerHTML = '<p style="color:#60a5fa">⏳ DeepSeek 分析中...</p>';
    try {
      const r2 = await fetch('/api/stock/analyze/deepseek', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({symbol: sym})});
      const d2 = await r2.json();
      if (d2.error) {
        resDs.innerHTML = '<p style="color:#f87171">DeepSeek: '+d2.error+'</p>';
      } else {
        var h = '';
        if (d2.reasoning) {
          h += '<details style="margin-bottom:12px"><summary style="font-size:0.85em;color:#60a5fa;cursor:pointer">&#129504; 推理过程 (Chain of Thought)</summary>';
          h += '<div style="font-size:0.8em;color:#94a3b8;white-space:pre-wrap;margin-top:6px;max-height:400px;overflow-y:auto;padding:8px;background:#0a0e1a;border-radius:6px">' + d2.reasoning.replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</div></details>';
        }
        h += '<div style="white-space:pre-wrap;line-height:1.7">' + _simpleMarkdown(d2.report || '') + '</div>';
        if (d2.usage && d2.usage.total_tokens) {
          h += '<div style="font-size:0.72em;color:#64748b;text-align:right;margin-top:8px">Model: ' + (d2.model||'') + ' | Tokens: ' + d2.usage.total_tokens + '</div>';
        }
        resDs.innerHTML = h;
      }
      st.textContent = '';
    } catch(e2) {
      resDs.innerHTML = '<p style="color:#f87171">DeepSeek 请求失败: '+e2.message+'</p>';
      st.textContent = '';
    }
  }
}
async function runStockTech() { await _runStockPartial('technical'); }
async function runStockFund() { await _runStockPartial('fundamental'); }
async function runStockSent() { await _runStockPartial('sentiment'); }
async function runStockXGB() { await _runStockPartial('xgboost'); }
async function runStockFF() { await _runStockPartial('fund_flow'); }
async function _runStockPartial(mode) {
  const sym = document.getElementById('stockSymbolInput').value.trim();
  if (!sym) { showToast('请输入股票代码'); return; }
  const st = document.getElementById('stockStatus');
  const res = document.getElementById('stockResult');
  st.textContent = '分析中...';
  res.innerHTML = '<p style="color:#60a5fa">⏳ 正在分析...</p>';
  try {
    const r = await fetch('/api/stock/analyze', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({symbol: sym, mode: mode})});
    const d = await r.json();
    if (d.error) { res.innerHTML = '<p style="color:#f87171">'+d.error+'</p>'; }
    else { res.innerHTML = _renderStockMd(d); }
    st.textContent = '';
  } catch(e) { res.innerHTML = '<p style="color:#f87171">请求失败: '+e.message+'</p>'; st.textContent = ''; }
}
function _renderStockMd(d) {
  let md = d.report || d.technical_report || d.fundamental_report || d.sentiment_report || '';
  if (d.fund_flow_report) md += '\n\n---\n\n' + d.fund_flow_report;
  if (d.xgb_report) md += '\n\n---\n\n' + d.xgb_report;
  if (d.prediction_report) md += '\n\n---\n\n' + d.prediction_report;
  return '<div style="white-space:pre-wrap;line-height:1.7">' + _simpleMarkdown(md) + '</div>';
}
function _simpleMarkdown(text) {
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/^# (.+)$/gm,'<h2 style="color:#60a5fa;margin:16px 0 8px">$1</h2>')
    .replace(/^## (.+)$/gm,'<h3 style="color:#818cf8;margin:12px 0 6px">$1</h3>')
    .replace(/^### (.+)$/gm,'<h4 style="color:#a5b4fc;margin:8px 0 4px">$1</h4>')
    .replace(/^> (.+)$/gm,'<blockquote style="border-left:3px solid #3a3d5a;padding:4px 12px;margin:8px 0;color:#a0a4c0">$1</blockquote>')
    .replace(/\*\*(.+?)\*\*/g,'<strong style="color:#e2e8f0">$1</strong>')
    .replace(/\|(.+)\|/g, function(m){
      const cells = m.split('|').filter(c=>c.trim());
      if (cells.every(c=>/^[\s\-:]+$/.test(c))) return '';
      const tds = cells.map(c=>'<td style="padding:4px 8px;border-bottom:1px solid #2a2d3e">'+c.trim()+'</td>').join('');
      return '<tr>'+tds+'</tr>';
    })
    .replace(/(<tr>.*<\/tr>\s*){2,}/g, function(m){ return '<table style="width:100%;border-collapse:collapse;margin:8px 0">'+m+'</table>'; })
    .replace(/^---$/gm,'<hr style="border:none;border-top:1px solid #2a2d3e;margin:12px 0">')
    .replace(/^\*(.+)\*$/gm,'<em style="color:#8b8fa4">$1</em>');
}
// --- Watchlist ---
function openWatchlistModal() {
  document.getElementById('watchlistModal').classList.add('open');
  loadWatchlist();
}
function closeWatchlistModal() {
  document.getElementById('watchlistModal').classList.remove('open');
}
async function loadWatchlist() {
  try {
    const r = await fetch('/api/stock/watchlist');
    const d = await r.json();
    const tb = document.getElementById('watchlistBody');
    if (!d.stocks || d.stocks.length === 0) { tb.innerHTML = '<tr><td colspan="6" style="padding:20px;text-align:center;color:#6b7280">自选股为空，添加股票开始</td></tr>'; return; }
    tb.innerHTML = d.stocks.map(s => {
      const chg = s.change_pct != null ? s.change_pct : '';
      const chgColor = chg > 0 ? '#ef4444' : chg < 0 ? '#22c55e' : '#c4c8f0';
      const priceStr = s.latest_price != null ? '¥'+s.latest_price : '-';
      const chgStr = chg !== '' ? (chg>0?'+':'')+chg.toFixed(2)+'%' : '-';
      return '<tr style="border-bottom:1px solid #1e2030">' +
        '<td style="padding:6px 8px"><a href="#" onclick="document.getElementById(\'stockSymbolInput\').value=\''+s.symbol+'\';openStockModal();closeWatchlistModal();return false" style="color:#60a5fa;text-decoration:none">'+s.symbol+'</a></td>' +
        '<td style="padding:6px 8px">'+s.name+'</td>' +
        '<td style="padding:6px 8px;text-align:right;color:'+chgColor+'">'+priceStr+'</td>' +
        '<td style="padding:6px 8px;text-align:right;color:'+chgColor+'">'+chgStr+'</td>' +
        '<td style="padding:6px 8px;color:#8b8fa4">'+(s.sector||'')+'</td>' +
        '<td style="padding:6px 8px;text-align:center"><button onclick="removeFromWatchlist(\''+s.symbol+'\')" style="background:none;border:none;color:#f87171;cursor:pointer;font-size:0.9em" title="删除">✕</button></td>' +
        '</tr>';
    }).join('');
  } catch(e) { showToast('加载自选股失败'); }
}
async function addToWatchlist() {
  const sym = document.getElementById('watchlistAddSymbol').value.trim();
  const name = document.getElementById('watchlistAddName').value.trim();
  const sector = document.getElementById('watchlistAddSector').value.trim();
  if (!sym) { showToast('请输入代码'); return; }
  try {
    const r = await fetch('/api/stock/watchlist', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({symbol:sym,name:name,sector:sector})});
    const d = await r.json();
    if (d.error) showToast(d.error); else { showToast('已添加 '+sym); loadWatchlist(); }
    document.getElementById('watchlistAddSymbol').value = '';
    document.getElementById('watchlistAddName').value = '';
    document.getElementById('watchlistAddSector').value = '';
  } catch(e) { showToast('添加失败'); }
}
async function removeFromWatchlist(sym) {
  try {
    await fetch('/api/stock/watchlist/'+sym, {method:'DELETE'});
    loadWatchlist();
  } catch(e) { showToast('删除失败'); }
}
async function refreshWatchlist() {
  const st = document.getElementById('watchlistStatus');
  st.textContent = '刷新中...';
  try {
    await fetch('/api/stock/watchlist/refresh', {method:'POST'});
    await loadWatchlist();
    st.textContent = '已刷新';
    setTimeout(()=>{st.textContent='';}, 3000);
  } catch(e) { st.textContent = '刷新失败'; }
}

// --- AI Scanner ---
let _scanPollTimer = null;
function openScannerModal() {
  document.getElementById('scannerModal').classList.add('open');
  pollScanStatus();
}
function closeScannerModal() {
  document.getElementById('scannerModal').classList.remove('open');
  if (_scanPollTimer) { clearInterval(_scanPollTimer); _scanPollTimer = null; }
}
async function startScan() {
  const st = document.getElementById('scanStatus');
  st.textContent = '启动中...';
  document.getElementById('btnScanStart').disabled = true;
  document.getElementById('btnScanStop').disabled = false;
  document.getElementById('scanProgress').style.display = 'block';
  var useDs = document.getElementById('scanUseDeepseek').checked;
  document.getElementById('scanResult').innerHTML = '<p style="color:#60a5fa">⏳ 正在扫描全市场...' + (useDs ? ' (DeepSeek enabled)' : '') + '</p>';
  try {
    const r = await fetch('/api/stock/scan/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({use_deepseek: useDs})});
    const d = await r.json();
    if (d.error) { st.textContent = d.error; document.getElementById('btnScanStart').disabled = false; return; }
    st.textContent = '扫描进行中';
    if (!_scanPollTimer) _scanPollTimer = setInterval(pollScanStatus, 4000);
  } catch(e) { st.textContent = '启动失败'; document.getElementById('btnScanStart').disabled = false; }
}
async function stopScan() {
  try { await fetch('/api/stock/scan/stop', {method:'POST'}); } catch(e) {}
  document.getElementById('scanStatus').textContent = '正在停止...';
}
async function pollScanStatus() {
  try {
    const r = await fetch('/api/stock/scan/status');
    const d = await r.json();
    const st = document.getElementById('scanStatus');
    const bar = document.getElementById('scanProgressBar');
    const txt = document.getElementById('scanProgressText');
    const phase = document.getElementById('scanPhase');
    const prog = document.getElementById('scanProgress');

    if (!d.status || d.status === '') {
      return;
    }

    prog.style.display = 'block';
    const total = d.layer1_count || d.total_stocks || 100;
    const done = d.analyzed_count || 0;

    if (d.status === 'layer1') {
      bar.style.width = '5%'; txt.textContent = ''; phase.textContent = 'Layer 1: 全市场快速筛选...';
    } else if (d.status === 'layer2_in_progress') {
      const pct = Math.min(90, 10 + (done / total) * 75);
      bar.style.width = pct + '%'; txt.textContent = done + '/' + total;
      phase.textContent = 'Layer 2: 详细分析中 (' + done + '/' + total + ')';
    } else if (d.status === 'layer3') {
      var l3mode = d.layer3_mode === 'deepseek+local' ? 'Layer 3: &#128171; DeepSeek + 本地 LLM 判断...' : 'Layer 3: LLM综合评分...';
      bar.style.width = '90%'; txt.textContent = ''; phase.textContent = l3mode;
    } else if (d.status === 'comprehensive') {
      bar.style.width = '93%'; txt.textContent = ''; phase.textContent = '综合分析: ' + (d.comprehensive_current || '运行中...');
    } else if (d.status === 'deepseek') {
      bar.style.width = '97%'; txt.textContent = ''; phase.textContent = '&#128171; DeepSeek 补充报告: ' + (d.deepseek_current || '运行中...');
    } else if (d.status === 'done') {
      bar.style.width = '100%'; txt.textContent = '完成'; phase.textContent = '';
      st.textContent = '扫描完成';
      document.getElementById('btnScanStart').disabled = false;
      document.getElementById('btnScanStop').disabled = true;
      if (_scanPollTimer) { clearInterval(_scanPollTimer); _scanPollTimer = null; }
      renderScanResult(d.top_picks || []);
    } else if (d.status === 'stopped') {
      bar.style.width = bar.style.width; phase.textContent = '已暂停 (可重新启动继续)';
      st.textContent = '已暂停';
      document.getElementById('btnScanStart').disabled = false;
      document.getElementById('btnScanStop').disabled = true;
      if (_scanPollTimer) { clearInterval(_scanPollTimer); _scanPollTimer = null; }
    } else if (d.status === 'error') {
      phase.textContent = '错误: ' + (d.error || '未知');
      st.textContent = '扫描失败';
      document.getElementById('btnScanStart').disabled = false;
      document.getElementById('btnScanStop').disabled = true;
      if (_scanPollTimer) { clearInterval(_scanPollTimer); _scanPollTimer = null; }
    }

    if (d.running) {
      document.getElementById('btnScanStart').disabled = true;
      document.getElementById('btnScanStop').disabled = false;
    }

    if (d.status === 'layer2_in_progress' && d.layer2_results && d.layer2_results.length > 0) {
      renderPartialResults(d.layer2_results);
    }
  } catch(e) {}
}
function renderScanResult(picks) {
  const el = document.getElementById('scanResult');
  if (!picks || picks.length === 0) {
    el.innerHTML = '<div style="text-align:center;padding:24px">' +
      '<p style="color:#fbbf24;font-size:1.1em;font-weight:600">本次扫描：暂无推荐</p>' +
      '<p style="color:#8b8fa4;font-size:0.85em;margin-top:8px">经过三层筛选，没有找到估值合理且值得买入的股票。</p>' +
      '<p style="color:#6b7280;font-size:0.8em">这是正常的 — "不推荐" 本身就是最好的建议。</p></div>';
    return;
  }
  let h = '<div style="margin-bottom:12px"><h3 style="color:#fbbf24;margin:0 0 8px">✅ 推荐买入: ' + picks.length + ' 只</h3></div>';
  picks.forEach((p, i) => {
    const chgColor = (p.change_pct||0) > 0 ? '#ef4444' : (p.change_pct||0) < 0 ? '#22c55e' : '#c4c8f0';
    h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;padding:12px;margin-bottom:8px">';
    h += '<div style="display:flex;justify-content:space-between;align-items:center">';
    h += '<div><span style="color:#fbbf24;font-weight:700;font-size:1.1em">#' + (i+1) + '</span> ';
    h += '<span style="color:#60a5fa;font-weight:600">' + p.name + '</span> ';
    h += '<span style="color:#8b8fa4">(' + p.symbol + ')</span></div>';
    h += '<div style="display:flex;align-items:center;gap:8px">';
    h += '<button onclick="addScanPickToWatchlist(\'' + p.symbol + '\',\'' + (p.name||'').replace(/'/g,"\\'") + '\')" style="background:#1e3a5f;border:1px solid #3b82f6;color:#60a5fa;border-radius:6px;padding:3px 10px;cursor:pointer;font-size:0.8em" title="加入自选股">⭐ 自选</button>';
    h += '<span style="color:#fbbf24;font-size:1.1em;font-weight:700">' + (p.final_score||0).toFixed(1) + '</span><span style="color:#8b8fa4;font-size:0.8em">/100</span>';
    h += '</div></div>';
    h += '<div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:8px;font-size:0.85em">';
    h += '<span>¥' + (p.price||'-') + '</span>';
    h += '<span style="color:' + chgColor + '">' + ((p.change_pct||0)>0?'+':'') + (p.change_pct||0).toFixed(2) + '%</span>';
    h += '<span>PE: ' + (p.pe||'-') + '</span>';
    if (p.fund_score != null) h += '<span>基本面: ' + p.fund_score + '</span>';
    h += '<span>技术: ' + (p.tech_score||'-') + '</span>';
    h += '<span>情绪: ' + (p.sentiment_score||'-') + '</span>';
    if (p.is_hot) h += '<span style="color:#f59e0b">🔥 热门</span>';
    h += '</div>';
    if (p.buy_low && p.buy_high) h += '<div style="margin-top:6px;color:#38bdf8;font-size:0.83em">📊 建议买入区间: ¥' + p.buy_low + ' ~ ¥' + p.buy_high + '</div>';
    var judgeTag = p.judged_by === 'deepseek' ? '<span style="color:#3b82f6;font-size:0.75em;margin-left:8px">&#128300; DeepSeek判断</span>' : '<span style="color:#8b8fa4;font-size:0.75em;margin-left:8px">&#129302; 本地LLM判断</span>';
    if (p.reasoning) h += '<div style="margin-top:4px;color:#a3e635;font-size:0.85em">💡 ' + p.reasoning + judgeTag + '</div>';
    if (p.risk) h += '<div style="margin-top:2px;color:#f87171;font-size:0.8em">⚠️ ' + p.risk + '</div>';
    if (p.strategy) h += '<div style="margin-top:2px;color:#38bdf8;font-size:0.82em">📋 ' + p.strategy + '</div>';
    if (p.comprehensive) h += _renderComprehensive(p.comprehensive);
    if (p.deepseek) h += _renderDeepseekResult(p.deepseek, i);
    h += '</div>';
  });
  el.innerHTML = h;
}
function _renderDeepseekResult(ds, idx) {
  if (ds.error) {
    return '<div style="margin-top:8px;padding:8px 12px;background:#1c1113;border:1px solid #7f1d1d;border-radius:6px;font-size:0.8em;color:#f87171">DeepSeek: ' + ds.error + '</div>';
  }
  var isJudgment = ds.judgment === true;
  var dsTitle = isJudgment ? '&#128300; DeepSeek Layer 3 判断' : '&#128171; DeepSeek 深度分析';
  var h = '<div style="margin-top:10px;padding:10px 12px;background:#0c1220;border:1px solid #1e3a5f;border-radius:8px">';
  h += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">';
  h += '<span style="font-size:0.85em;color:#3b82f6;font-weight:600">' + dsTitle + '</span>';
  if (ds.model) h += '<span style="font-size:0.7em;color:#64748b">' + ds.model + '</span>';
  h += '</div>';
  if (ds.reasoning) {
    var rid = 'dsReasoning' + idx;
    h += '<details style="margin-bottom:8px"><summary style="font-size:0.78em;color:#60a5fa;cursor:pointer">&#129504; 推理过程 (Chain of Thought)</summary>';
    h += '<div id="' + rid + '" style="font-size:0.78em;color:#94a3b8;white-space:pre-wrap;margin-top:4px;max-height:300px;overflow-y:auto;padding:6px;background:#0a0e1a;border-radius:4px">' + ds.reasoning.replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</div></details>';
  }
  if (ds.report) {
    h += '<div style="font-size:0.85em;color:#e0e0e0;white-space:pre-wrap;line-height:1.6">' + _simpleMarkdown(ds.report) + '</div>';
  }
  if (ds.usage && ds.usage.total_tokens) {
    h += '<div style="font-size:0.7em;color:#64748b;margin-top:6px;text-align:right">Tokens: ' + ds.usage.total_tokens + '</div>';
  }
  h += '</div>';
  return h;
}
function _renderComprehensive(c) {
  var star = c.star_rating || 0;
  var starStr = '';
  for (var s = 0; s < 5; s++) starStr += s < star ? '&#11088;' : '&#9734;';
  var starColor = star >= 4 ? '#fbbf24' : star >= 3 ? '#60a5fa' : star >= 2 ? '#8b8fa4' : '#f87171';
  var h = '<div style="margin-top:10px;padding:10px 12px;background:#111827;border:1px solid #374151;border-radius:8px">';
  h += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">';
  h += '<span style="font-size:0.85em;color:#8b8fa4;font-weight:600">综合分析报告</span>';
  h += '<span style="font-size:1.1em;color:' + starColor + '">' + starStr + ' <span style="font-size:0.75em">(' + (c.support_count||0) + '/' + (c.total_dims||0) + ' 维度支持)</span></span>';
  h += '</div>';
  h += '<div style="font-size:0.88em;color:' + starColor + ';font-weight:700;margin-bottom:8px">' + (c.conclusion||'') + '</div>';

  var dims = c.dimensions || {};
  h += '<div style="display:flex;flex-wrap:wrap;gap:6px">';

  if (dims.technical) {
    var t = dims.technical;
    var tc = t.supports_buy ? '#10b981' : '#f87171';
    var icon = t.supports_buy ? '&#9989;' : '&#10060;';
    h += '<div style="flex:1;min-width:200px;background:#0f1117;border:1px solid #2a2d3e;border-radius:6px;padding:8px">';
    h += '<div style="font-size:0.78em;color:#8b8fa4;margin-bottom:4px">' + icon + ' 技术面</div>';
    h += '<div style="font-size:0.85em;color:' + tc + ';font-weight:600">' + (t.overall||'') + '</div>';
    h += '<div style="font-size:0.78em;color:#8b8fa4">RSI: ' + (t.rsi||'?') + ' | 看涨: ' + (t.bullish||0) + ' 看跌: ' + (t.bearish||0) + '</div>';
    if (t.support && t.support.length) h += '<div style="font-size:0.75em;color:#8b8fa4">支撑: ¥' + t.support.join('/¥') + '</div>';
    if (t.resistance && t.resistance.length) h += '<div style="font-size:0.75em;color:#8b8fa4">阻力: ¥' + t.resistance.join('/¥') + '</div>';
    if (t.signals && t.signals.length) h += '<div style="font-size:0.72em;color:#10b981;margin-top:2px">' + t.signals.join(', ') + '</div>';
    if (t.warnings && t.warnings.length) h += '<div style="font-size:0.72em;color:#f87171;margin-top:1px">' + t.warnings.join(', ') + '</div>';
    h += '</div>';
  }

  if (dims.ml_direction) {
    var m = dims.ml_direction;
    var mc = m.supports_buy ? '#10b981' : (m.direction === '跌' ? '#f87171' : '#8b8fa4');
    var micon = m.supports_buy ? '&#9989;' : '&#10060;';
    h += '<div style="flex:1;min-width:140px;background:#0f1117;border:1px solid #2a2d3e;border-radius:6px;padding:8px">';
    h += '<div style="font-size:0.78em;color:#8b8fa4;margin-bottom:4px">' + micon + ' ML方向预测</div>';
    h += '<div style="font-size:0.95em;color:' + mc + ';font-weight:700">' + (m.direction||'?') + '</div>';
    h += '<div style="font-size:0.78em;color:#8b8fa4">置信度: ' + (m.confidence||0) + '%</div>';
    h += '</div>';
  }

  if (dims.price_prediction) {
    var pp = dims.price_prediction;
    var pc = pp.supports_buy ? '#10b981' : '#8b8fa4';
    var picon = pp.supports_buy ? '&#9989;' : '&#10060;';
    h += '<div style="flex:1;min-width:170px;background:#0f1117;border:1px solid #2a2d3e;border-radius:6px;padding:8px">';
    h += '<div style="font-size:0.78em;color:#8b8fa4;margin-bottom:4px">' + picon + ' 明日价格预测</div>';
    h += '<div style="font-size:0.85em;color:' + pc + ';font-weight:600">' + (pp.change_pct > 0 ? '+' : '') + (pp.change_pct||0).toFixed(1) + '%</div>';
    if (pp.pred_close) h += '<div style="font-size:0.78em;color:#8b8fa4">收盘: ¥' + pp.pred_close.toFixed(2) + '</div>';
    if (pp.pred_high && pp.pred_low) h += '<div style="font-size:0.75em;color:#8b8fa4">区间: ¥' + pp.pred_low.toFixed(2) + ' ~ ¥' + pp.pred_high.toFixed(2) + '</div>';
    h += '</div>';
  }

  if (dims.fund_flow) {
    var ff = dims.fund_flow;
    var phase = ff.smart_money_phase || '无信号';
    var phaseColors = {'布局期':'#10b981','拉升期':'#fbbf24','出货期':'#f87171','观察期':'#60a5fa','无信号':'#8b8fa4'};
    var phaseIcons = {'布局期':'&#128176;','拉升期':'&#128200;','出货期':'&#9888;','观察期':'&#128065;','无信号':'&#8722;'};
    var pc = phaseColors[phase] || '#8b8fa4';
    var ficon = ff.supports_buy ? '&#9989;' : '&#10060;';
    h += '<div style="flex:1;min-width:180px;background:#0f1117;border:1px solid #2a2d3e;border-radius:6px;padding:8px">';
    h += '<div style="font-size:0.78em;color:#8b8fa4;margin-bottom:4px">' + ficon + ' 资金流向</div>';
    h += '<div style="font-size:0.95em;color:' + pc + ';font-weight:700">' + (phaseIcons[phase]||'') + ' ' + phase + '</div>';
    if (ff.accumulation_score != null) h += '<div style="font-size:0.78em;color:' + pc + '">布局得分: ' + ff.accumulation_score + '/100</div>';
    if (ff.detail) h += '<div style="font-size:0.75em;color:#a3e635;margin-top:2px">' + ff.detail + '</div>';
    h += '<div style="font-size:0.75em;color:#8b8fa4;margin-top:3px">3日净流入: ' + (ff.main_net_3d||'?') + '</div>';
    if (ff.main_net_10d != null) h += '<div style="font-size:0.72em;color:#8b8fa4">10日净流入: ' + ff.main_net_10d + '</div>';
    h += '</div>';
  }

  h += '</div>';

  var details = c.verdict_details || [];
  if (details.length > 0) {
    h += '<div style="margin-top:6px;font-size:0.76em;color:#8b8fa4">判据: ' + details.join(' | ') + '</div>';
  }
  h += '</div>';
  return h;
}
async function addScanPickToWatchlist(sym, name) {
  try {
    const r = await fetch('/api/stock/watchlist', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({symbol:sym, name:name})});
    const d = await r.json();
    if (d.error) showToast(d.error); else showToast('已加入自选: ' + sym + ' ' + name);
  } catch(e) { showToast('加入自选失败'); }
}
function renderPartialResults(results) {
  const el = document.getElementById('scanResult');
  const sorted = results.slice().sort((a,b) => (b.score_l2||0) - (a.score_l2||0)).slice(0,10);
  let h = '<div style="margin-bottom:8px"><span style="color:#8b8fa4;font-size:0.82em">实时候选 (Layer 2 进行中, 按得分排序)</span></div>';
  sorted.forEach(s => {
    const chgColor = (s.change_pct||0) > 0 ? '#ef4444' : (s.change_pct||0) < 0 ? '#22c55e' : '#c4c8f0';
    h += '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #1e2130;font-size:0.85em">';
    h += '<span style="color:#60a5fa">' + s.name + ' (' + s.symbol + ')</span>';
    h += '<span>L2: ' + (s.score_l2||0).toFixed(1) + '  <span style="color:'+chgColor+'">' + ((s.change_pct||0)>0?'+':'') + (s.change_pct||0).toFixed(2) + '%</span></span>';
    h += '</div>';
  });
  el.innerHTML = h;
}
async function loadScanHistory() {
  const el = document.getElementById('scanResult');
  el.innerHTML = '<p style="color:#60a5fa">加载历史记录...</p>';
  try {
    const r = await fetch('/api/stock/scan/history');
    const d = await r.json();
    if (!d.history || d.history.length === 0) { el.innerHTML = '<p style="color:#6b7280">暂无历史记录</p>'; return; }
    let h = '<h3 style="color:#fbbf24;margin:0 0 12px">📋 历史推荐记录</h3>';
    d.history.slice().reverse().forEach(entry => {
      h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:6px;padding:10px;margin-bottom:6px">';
      h += '<div style="color:#60a5fa;font-weight:600;margin-bottom:6px">' + entry.date + '</div>';
      entry.picks.forEach(p => {
        let ret = '';
        if (p.return_1d != null) ret += ' 1D:' + (p.return_1d>0?'+':'') + p.return_1d + '%';
        if (p.return_3d != null) ret += ' 3D:' + (p.return_3d>0?'+':'') + p.return_3d + '%';
        if (p.return_7d != null) ret += ' 7D:' + (p.return_7d>0?'+':'') + p.return_7d + '%';
        h += '<div style="display:flex;justify-content:space-between;font-size:0.85em;padding:2px 0">';
        h += '<span>' + p.name + ' (' + p.symbol + ') 得分:' + (p.score||0).toFixed(1) + '</span>';
        h += '<span style="color:#8b8fa4">' + (ret || '暂无收益数据') + '</span>';
        h += '</div>';
      });
      h += '</div>';
    });
    el.innerHTML = h;
  } catch(e) { el.innerHTML = '<p style="color:#f87171">加载失败</p>'; }
}

// --- Price Prediction Training ---
let _trainPollTimer = null;
function openPriceTrainModal() {
  document.getElementById('priceTrainModal').classList.add('open');
  pollTrainStatus();
}
function closePriceTrainModal() {
  document.getElementById('priceTrainModal').classList.remove('open');
  if (_trainPollTimer) { clearInterval(_trainPollTimer); _trainPollTimer = null; }
}
async function startDailyTraining() {
  const st = document.getElementById('trainStatus');
  st.textContent = '启动中...';
  document.getElementById('btnTrainStart').disabled = true;
  try {
    const r = await fetch('/api/stock/train/daily', {method:'POST'});
    const d = await r.json();
    if (!d.ok) { st.textContent = d.error || '启动失败'; document.getElementById('btnTrainStart').disabled = false; return; }
    st.textContent = '训练已启动';
    if (!_trainPollTimer) _trainPollTimer = setInterval(pollTrainStatus, 3000);
  } catch(e) { st.textContent = '请求失败'; document.getElementById('btnTrainStart').disabled = false; }
}
async function pollTrainStatus() {
  try {
    const r = await fetch('/api/stock/train/status');
    const d = await r.json();
    const st = document.getElementById('trainStatus');
    const prog = document.getElementById('trainProgress');
    const bar = document.getElementById('trainProgressBar');
    const txt = document.getElementById('trainProgressText');
    const phase = document.getElementById('trainPhase');
    const btn = document.getElementById('btnTrainStart');
    if (d.status === 'idle') {
      st.textContent = '就绪';
      prog.style.display = 'none';
      btn.disabled = false;
      return;
    }
    if (d.status === 'running') {
      prog.style.display = 'block';
      const pct = d.total > 0 ? Math.round(d.completed / d.total * 100) : 0;
      bar.style.width = pct + '%';
      txt.textContent = pct + '%';
      phase.textContent = d.current || '';
      st.textContent = d.completed + '/' + d.total;
      btn.disabled = true;
      if (!_trainPollTimer) _trainPollTimer = setInterval(pollTrainStatus, 3000);
    }
    if (d.status === 'done') {
      if (_trainPollTimer) { clearInterval(_trainPollTimer); _trainPollTimer = null; }
      prog.style.display = 'none';
      btn.disabled = false;
      st.textContent = '训练完成 (' + (d.results || []).length + ' 只股票)';
      renderFullTrainReport(d.verifications || [], d.results || [], d.sentiment || null, d.black_swan || null, d.aggregate_stats || null);
    }
  } catch(e) {}
}
function renderFullTrainReport(verifications, results, sentiment, blackSwan, aggregateStats) {
  const el = document.getElementById('trainResult');
  let h = '';

  // === Section 0: Market Sentiment + Black Swan ===
  if (sentiment || blackSwan) {
    h += '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">';
    if (sentiment) {
      const fg = sentiment.fear_greed || {};
      const vix = sentiment.vix || {};
      const mood = sentiment.market_mood || {};
      const fgVal = fg.value;
      const fgColor = fgVal <= 25 ? '#ef4444' : fgVal <= 45 ? '#fbbf24' : fgVal <= 55 ? '#8b8fa4' : fgVal <= 75 ? '#10b981' : '#3b82f6';
      h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;padding:12px 16px;flex:1;min-width:220px">';
      h += '<div style="font-size:0.8em;color:#8b8fa4;margin-bottom:6px">&#128200; 市场情绪</div>';
      if (fgVal != null) {
        h += '<div style="display:flex;align-items:baseline;gap:8px"><span style="font-size:1.8em;font-weight:700;color:' + fgColor + '">' + fgVal + '</span>';
        h += '<span style="font-size:0.85em;color:#8b8fa4">' + (fg.label||'') + '</span></div>';
        h += '<div style="height:6px;background:#1a1d2e;border-radius:3px;margin:8px 0;position:relative">';
        h += '<div style="height:100%;width:' + fgVal + '%;background:linear-gradient(90deg,#ef4444,#fbbf24,#10b981);border-radius:3px"></div></div>';
      }
      if (vix.value != null) {
        const vixColor = vix.value >= 30 ? '#ef4444' : vix.value >= 20 ? '#fbbf24' : '#10b981';
        h += '<div style="font-size:0.82em;margin-top:4px">VIX: <span style="color:' + vixColor + ';font-weight:600">' + vix.value + '</span>';
        if (vix.change_pct != null) h += ' <span style="color:#8b8fa4">(' + (vix.change_pct > 0 ? '+' : '') + vix.change_pct + '%)</span>';
        h += '</div>';
      }
      if (mood.recommendation) h += '<div style="font-size:0.78em;color:#fbbf24;margin-top:6px">' + mood.recommendation + '</div>';
      h += '</div>';
    }
    if (blackSwan && blackSwan.alerts && blackSwan.alerts.length > 0) {
      const rs = blackSwan.risk_summary || {};
      const lvlColor = {'critical':'#ef4444','high':'#f97316','elevated':'#fbbf24','low':'#8b8fa4','normal':'#10b981'}[rs.overall_level] || '#8b8fa4';
      h += '<div style="background:#0f1117;border:1px solid ' + lvlColor + ';border-radius:8px;padding:12px 16px;flex:1;min-width:280px">';
      h += '<div style="font-size:0.8em;color:#8b8fa4;margin-bottom:6px">&#9888;&#65039; 黑天鹅检测</div>';
      h += '<div style="font-size:1.1em;font-weight:700;color:' + lvlColor + ';margin-bottom:4px">' + (rs.overall_level||'').toUpperCase() + '</div>';
      h += '<div style="font-size:0.78em;color:#fbbf24;margin-bottom:8px">' + (rs.recommendation||'') + '</div>';
      blackSwan.alerts.forEach(a => {
        const sevColor = a.severity === 'high' ? '#ef4444' : a.severity === 'medium' ? '#fbbf24' : '#8b8fa4';
        h += '<div style="margin-bottom:4px;font-size:0.8em">';
        h += '<span style="color:' + sevColor + ';font-weight:600">[' + a.severity.toUpperCase() + ']</span> ';
        h += '<span style="color:#e0e0e0">' + a.label + '</span> ';
        h += '<span style="color:#8b8fa4">(' + a.match_count + ' 条新闻)</span>';
        h += '<div style="color:#8b8fa4;font-size:0.9em;margin-left:12px">影响: ' + a.affected_industries.join(', ') + '</div>';
        h += '</div>';
      });
      h += '</div>';
    }
    h += '</div>';
  }

  // === Section 1: Verification (predicted vs actual) ===
  const filled = verifications.filter(v => v.actual_close != null);
  if (filled.length > 0) {
    h += '<h3 style="color:#60a5fa;margin:0 0 10px">&#128269; 昨日预测验证</h3>';
    h += '<table style="width:100%;border-collapse:collapse;font-size:0.82em;margin-bottom:16px">';
    h += '<tr style="border-bottom:1px solid #2a2d3e;color:#8b8fa4">';
    h += '<th style="text-align:left;padding:6px">股票</th><th>预测收盘</th><th>实际收盘</th><th>误差</th>';
    h += '<th>预测最高</th><th>实际最高</th><th>预测最低</th><th>实际最低</th><th>方向</th></tr>';
    filled.forEach(v => {
      const dirIcon = v.direction_correct === true ? '&#9989;' : v.direction_correct === false ? '&#10060;' : '&#8212;';
      const errColor = v.error_pct_close != null ? (v.error_pct_close <= 2 ? '#10b981' : v.error_pct_close <= 5 ? '#fbbf24' : '#ef4444') : '#8b8fa4';
      h += '<tr style="border-bottom:1px solid #1a1d2e">';
      h += '<td style="padding:5px;font-weight:600">' + (v.name||v.symbol) + '<br><span style="color:#8b8fa4;font-size:0.85em">' + (v.target_date||'') + '</span></td>';
      h += '<td style="text-align:center;padding:5px">' + (v.predicted_close ? '&yen;'+v.predicted_close.toFixed(2) : '-') + '</td>';
      h += '<td style="text-align:center;padding:5px;font-weight:600">' + (v.actual_close ? '&yen;'+v.actual_close.toFixed(2) : '-') + '</td>';
      h += '<td style="text-align:center;padding:5px;color:' + errColor + ';font-weight:600">' + (v.error_pct_close != null ? v.error_pct_close.toFixed(2)+'%' : '-') + '</td>';
      h += '<td style="text-align:center;padding:5px;color:#ef4444">' + (v.predicted_high ? '&yen;'+v.predicted_high.toFixed(2) : '-') + '</td>';
      h += '<td style="text-align:center;padding:5px">' + (v.actual_high ? '&yen;'+v.actual_high.toFixed(2) : '-') + '</td>';
      h += '<td style="text-align:center;padding:5px;color:#10b981">' + (v.predicted_low ? '&yen;'+v.predicted_low.toFixed(2) : '-') + '</td>';
      h += '<td style="text-align:center;padding:5px">' + (v.actual_low ? '&yen;'+v.actual_low.toFixed(2) : '-') + '</td>';
      h += '<td style="text-align:center;padding:5px">' + dirIcon + '</td>';
      h += '</tr>';
    });
    h += '</table>';
  } else if (verifications.length > 0) {
    h += '<div style="color:#fbbf24;margin-bottom:12px;font-size:0.85em">&#9888; 首次运行，暂无历史预测可验证。下次运行时将自动回填实际价格。</div>';
  }

  // === Section 1.5: Aggregate Verification Stats ===
  if (aggregateStats && aggregateStats.total_verified > 0) {
    const as = aggregateStats;
    const dirAcc = as.direction_accuracy != null ? (as.direction_accuracy * 100).toFixed(1) : '-';
    const dirColor = as.direction_accuracy >= 0.6 ? '#10b981' : as.direction_accuracy >= 0.45 ? '#fbbf24' : '#ef4444';
    const mapeColor = as.avg_mape != null ? (as.avg_mape <= 2 ? '#10b981' : as.avg_mape <= 5 ? '#fbbf24' : '#ef4444') : '#8b8fa4';
    h += '<h3 style="color:#a78bfa;margin:12px 0 10px">&#128202; 历史验证统计</h3>';
    h += '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px">';

    h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;padding:12px 16px;flex:1;min-width:140px;text-align:center">';
    h += '<div style="font-size:0.75em;color:#8b8fa4;margin-bottom:4px">验证次数</div>';
    h += '<div style="font-size:1.6em;font-weight:700;color:#60a5fa">' + as.total_verified + '</div>';
    h += '<div style="font-size:0.7em;color:#8b8fa4">待验证: ' + as.total_pending + '</div>';
    h += '</div>';

    h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;padding:12px 16px;flex:1;min-width:140px;text-align:center">';
    h += '<div style="font-size:0.75em;color:#8b8fa4;margin-bottom:4px">方向预测成功率</div>';
    h += '<div style="font-size:1.6em;font-weight:700;color:' + dirColor + '">' + dirAcc + '%</div>';
    h += '<div style="font-size:0.7em;color:#8b8fa4">' + as.direction_correct + ' / ' + as.direction_total + ' 次</div>';
    h += '</div>';

    h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;padding:12px 16px;flex:1;min-width:140px;text-align:center">';
    h += '<div style="font-size:0.75em;color:#8b8fa4;margin-bottom:4px">平均误差 (MAPE)</div>';
    h += '<div style="font-size:1.6em;font-weight:700;color:' + mapeColor + '">' + (as.avg_mape != null ? as.avg_mape + '%' : '-') + '</div>';
    h += '<div style="font-size:0.7em;color:#8b8fa4">MAE: ' + (as.avg_mae != null ? '&yen;' + as.avg_mae : '-') + '</div>';
    h += '</div>';

    h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;padding:12px 16px;flex:1;min-width:140px;text-align:center">';
    h += '<div style="font-size:0.75em;color:#8b8fa4;margin-bottom:4px">覆盖股票</div>';
    h += '<div style="font-size:1.6em;font-weight:700;color:#a78bfa">' + as.symbol_count + '</div>';
    h += '<div style="font-size:0.7em;color:#8b8fa4">总预测: ' + as.total_predictions + ' 条</div>';
    h += '</div>';

    h += '</div>';

    const l7 = as.last_7 || {};
    const l30 = as.last_30 || {};
    if (l7.count > 0 || l30.count > 0) {
      h += '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px">';
      if (l7.count > 0) {
        const d7 = l7.direction_accuracy != null ? (l7.direction_accuracy * 100).toFixed(1) : '-';
        const d7c = l7.direction_accuracy >= 0.6 ? '#10b981' : l7.direction_accuracy >= 0.45 ? '#fbbf24' : '#ef4444';
        h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;padding:10px 14px;flex:1;min-width:200px">';
        h += '<div style="font-size:0.78em;color:#8b8fa4;margin-bottom:6px">近 7 日 (' + l7.count + ' 条)</div>';
        h += '<div style="display:flex;gap:16px;align-items:baseline">';
        h += '<span style="font-size:0.82em">方向: <b style="color:' + d7c + '">' + d7 + '%</b></span>';
        h += '<span style="font-size:0.82em">MAPE: <b>' + (l7.avg_mape != null ? l7.avg_mape + '%' : '-') + '</b></span>';
        h += '<span style="font-size:0.82em">正确: ' + l7.direction_correct + '/' + l7.direction_total + '</span>';
        h += '</div></div>';
      }
      if (l30.count > 0) {
        const d30 = l30.direction_accuracy != null ? (l30.direction_accuracy * 100).toFixed(1) : '-';
        const d30c = l30.direction_accuracy >= 0.6 ? '#10b981' : l30.direction_accuracy >= 0.45 ? '#fbbf24' : '#ef4444';
        h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;padding:10px 14px;flex:1;min-width:200px">';
        h += '<div style="font-size:0.78em;color:#8b8fa4;margin-bottom:6px">近 30 日 (' + l30.count + ' 条)</div>';
        h += '<div style="display:flex;gap:16px;align-items:baseline">';
        h += '<span style="font-size:0.82em">方向: <b style="color:' + d30c + '">' + d30 + '%</b></span>';
        h += '<span style="font-size:0.82em">MAPE: <b>' + (l30.avg_mape != null ? l30.avg_mape + '%' : '-') + '</b></span>';
        h += '<span style="font-size:0.82em">正确: ' + l30.direction_correct + '/' + l30.direction_total + '</span>';
        h += '</div></div>';
      }
      h += '</div>';
    }

    if (as.per_symbol && as.per_symbol.length > 0) {
      h += '<details style="margin-bottom:16px"><summary style="cursor:pointer;color:#a78bfa;font-size:0.85em;font-weight:600">&#128200; 各股票验证明细</summary>';
      h += '<table style="width:100%;border-collapse:collapse;font-size:0.8em;margin-top:8px">';
      h += '<tr style="border-bottom:1px solid #2a2d3e;color:#8b8fa4"><th style="text-align:left;padding:5px">股票</th><th>验证次数</th><th>方向成功率</th><th>平均MAPE</th></tr>';
      as.per_symbol.forEach(ps => {
        const psColor = ps.direction_accuracy >= 0.6 ? '#10b981' : ps.direction_accuracy >= 0.45 ? '#fbbf24' : '#ef4444';
        h += '<tr style="border-bottom:1px solid #1a1d2e">';
        h += '<td style="padding:5px;font-weight:600">' + ps.symbol + '</td>';
        h += '<td style="text-align:center;padding:5px">' + ps.verified + '</td>';
        h += '<td style="text-align:center;padding:5px;color:' + psColor + ';font-weight:600">' + (ps.direction_accuracy * 100).toFixed(1) + '%</td>';
        h += '<td style="text-align:center;padding:5px">' + (ps.avg_mape != null ? ps.avg_mape + '%' : '-') + '</td>';
        h += '</tr>';
      });
      h += '</table></details>';
    }
  }

  // === Section 2: Model Health ===
  const healthResults = results.filter(r => r.health && r.health.grade !== 'N/A');
  if (healthResults.length > 0) {
    h += '<h3 style="color:#fbbf24;margin:12px 0 10px">&#129657; 模型健康度</h3>';
    h += '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px">';
    healthResults.forEach(r => {
      const hl = r.health;
      const trendIcon = hl.trend === 'improving' ? '&#9650;' : hl.trend === 'degrading' ? '&#9660;' : '&#9644;';
      const trendColor = hl.trend === 'improving' ? '#10b981' : hl.trend === 'degrading' ? '#ef4444' : '#8b8fa4';
      h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:6px;padding:8px 12px;min-width:180px">';
      h += '<div style="font-weight:600;font-size:0.85em">' + (r.name||r.symbol) + '</div>';
      h += '<div style="display:flex;align-items:center;gap:8px;margin-top:4px">';
      h += '<span style="font-size:1.4em;font-weight:700;color:' + (hl.color||'#8b8fa4') + '">' + hl.grade + '</span>';
      h += '<span style="font-size:0.78em;color:#8b8fa4">' + hl.message + '</span>';
      h += '<span style="font-size:0.78em;color:' + trendColor + '">' + trendIcon + '</span>';
      h += '</div>';
      h += '<div style="font-size:0.75em;color:#8b8fa4;margin-top:2px">MAPE: ' + (hl.recent_mape||'-') + '% | 样本: ' + (hl.sample_size||0) + '</div>';
      h += '</div>';
    });
    h += '</div>';
  }

  // === Section 3: New Predictions ===
  const valid = results.filter(r => !r.error);
  if (valid.length > 0) {
    h += '<h3 style="color:#10b981;margin:12px 0 10px">&#127919; 明日价格预测</h3>';
    h += '<table style="width:100%;border-collapse:collapse;font-size:0.84em">';
    h += '<tr style="border-bottom:1px solid #2a2d3e;color:#8b8fa4"><th style="text-align:left;padding:6px">股票</th><th>当前价</th><th>预测收盘</th><th>预测最高</th><th>预测最低</th><th>涨跌幅</th><th>健康</th></tr>';
    results.forEach(r => {
      if (r.error) {
        h += '<tr style="border-bottom:1px solid #1a1d2e"><td style="padding:6px">' + r.symbol + '</td><td colspan="6" style="color:#f87171;padding:6px">' + r.error + '</td></tr>';
        return;
      }
      const p = r.predictions || {};
      const c = r.change_pct || {};
      const chgVal = c.close || 0;
      const chgColor = chgVal > 0 ? '#ef4444' : chgVal < 0 ? '#10b981' : '#8b8fa4';
      const chgSign = chgVal > 0 ? '+' : '';
      const hl = r.health || {};
      h += '<tr style="border-bottom:1px solid #1a1d2e">';
      h += '<td style="padding:6px;font-weight:600">' + (r.name || r.symbol) + '<br><span style="color:#8b8fa4;font-weight:400;font-size:0.85em">' + r.symbol + '</span></td>';
      h += '<td style="text-align:center;padding:6px;color:#8b8fa4">' + (r.current_close ? '&yen;'+r.current_close.toFixed(2) : '-') + '</td>';
      h += '<td style="text-align:center;padding:6px;color:#fbbf24;font-weight:600">&yen;' + (p.close||0).toFixed(2) + '</td>';
      h += '<td style="text-align:center;padding:6px;color:#ef4444">&yen;' + (p.high||0).toFixed(2) + '</td>';
      h += '<td style="text-align:center;padding:6px;color:#10b981">&yen;' + (p.low||0).toFixed(2) + '</td>';
      h += '<td style="text-align:center;padding:6px;color:' + chgColor + ';font-weight:600">' + chgSign + chgVal.toFixed(2) + '%</td>';
      h += '<td style="text-align:center;padding:6px"><span style="color:' + (hl.color||'#8b8fa4') + ';font-weight:700">' + (hl.grade||'-') + '</span></td>';
      h += '</tr>';
    });
    h += '</table>';
  }

  // === Section 4: Errors ===
  const errors = results.filter(r => r.error);
  if (errors.length > 0) {
    h += '<div style="margin-top:12px;font-size:0.8em;color:#f87171">';
    h += '<b>训练失败:</b> ';
    h += errors.map(r => r.symbol + '(' + r.error + ')').join(', ');
    h += '</div>';
  }

  el.innerHTML = h || '<p style="color:#6b7280">暂无结果</p>';
}

// --- National Team ETF Monitor ---
function openNationalTeamModal() {
  document.getElementById('nationalTeamModal').classList.add('open');
}
function closeNationalTeamModal() {
  document.getElementById('nationalTeamModal').classList.remove('open');
}
async function fetchNationalTeam() {
  const st = document.getElementById('ntStatus');
  const el = document.getElementById('ntResult');
  st.textContent = '获取数据中... (含历史回填约30-60秒)';
  el.innerHTML = '<p style="color:#60a5fa">&#9203; 正在从上交所/深交所获取ETF份额数据 + 回填历史数据...</p>';
  document.getElementById('btnNTFetch').disabled = true;
  try {
    const r = await fetch('/api/stock/national-team');
    const d = await r.json();
    if (d.error) { el.innerHTML = '<p style="color:#f87171">'+d.error+'</p>'; st.textContent = ''; document.getElementById('btnNTFetch').disabled = false; return; }
    renderNationalTeam(d);
    st.textContent = '';
  } catch(e) { el.innerHTML = '<p style="color:#f87171">请求失败: '+e.message+'</p>'; st.textContent = ''; }
  document.getElementById('btnNTFetch').disabled = false;
}
function renderNationalTeam(d) {
  const el = document.getElementById('ntResult');
  const snap = d.snapshot || {};
  const trend = d.trend || {};
  const ps = d.period_stats || {};
  const etfs = snap.etf_snapshot || [];
  const sigs = snap.signals || {};
  let h = '';

  var sigColor = '#8b8fa4';
  var sigLabel = sigs.broad_total_change || '无数据';
  if (sigLabel.indexOf('大幅增持') >= 0) sigColor = '#ef4444';
  else if (sigLabel.indexOf('温和增持') >= 0) sigColor = '#f97316';
  else if (sigLabel.indexOf('大幅减持') >= 0) sigColor = '#10b981';
  else if (sigLabel.indexOf('温和减持') >= 0) sigColor = '#3b82f6';

  h += '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">';
  h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;padding:12px 16px;flex:1;min-width:180px">';
  h += '<div style="font-size:0.78em;color:#8b8fa4">宽基ETF总份额</div>';
  h += '<div style="font-size:1.6em;font-weight:700;color:#60a5fa">' + (snap.total_broad_shares_yi||0).toFixed(1) + '<span style="font-size:0.5em;color:#8b8fa4"> 亿份</span></div>';
  h += '</div>';
  h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;padding:12px 16px;flex:1;min-width:180px">';
  h += '<div style="font-size:0.78em;color:#8b8fa4">行业ETF总份额</div>';
  h += '<div style="font-size:1.6em;font-weight:700;color:#a78bfa">' + (snap.total_sector_shares_yi||0).toFixed(1) + '<span style="font-size:0.5em;color:#8b8fa4"> 亿份</span></div>';
  h += '</div>';
  h += '<div style="background:#0f1117;border:1px solid ' + sigColor + ';border-radius:8px;padding:12px 16px;flex:1;min-width:180px">';
  h += '<div style="font-size:0.78em;color:#8b8fa4">国家队动向</div>';
  h += '<div style="font-size:1.3em;font-weight:700;color:' + sigColor + '">' + sigLabel + '</div>';
  if (trend.total_change_pct != null) {
    var tc = trend.total_change_pct;
    h += '<div style="font-size:0.78em;color:#8b8fa4;margin-top:2px">近期变化: <span style="color:' + (tc > 0 ? '#ef4444' : tc < 0 ? '#10b981' : '#8b8fa4') + '">' + (tc > 0 ? '+' : '') + tc + '%</span></div>';
    h += '<div style="font-size:0.78em;color:#8b8fa4">趋势: ' + (trend.trend||'') + ' (数据点: ' + (trend.data_points||0) + ')</div>';
  }
  h += '</div>';
  h += '</div>';

  var periods = (ps.periods || []);
  if (periods.length > 0) {
    h += '<div style="margin-bottom:16px">';
    h += '<div style="font-size:0.85em;font-weight:600;color:#e0e0e0;margin-bottom:8px">&#128200; 历史区间变化</div>';
    h += '<table style="width:100%;border-collapse:collapse;font-size:0.82em;background:#0f1117;border-radius:8px;border:1px solid #2a2d3e">';
    h += '<tr style="border-bottom:1px solid #2a2d3e;color:#8b8fa4">';
    h += '<th style="text-align:left;padding:8px 10px">区间</th>';
    h += '<th style="text-align:center;padding:8px 10px">参考日期</th>';
    h += '<th style="text-align:right;padding:8px 10px">宽基变化</th>';
    h += '<th style="text-align:right;padding:8px 10px">宽基份额</th>';
    h += '<th style="text-align:right;padding:8px 10px">行业变化</th>';
    h += '<th style="text-align:right;padding:8px 10px">行业份额</th>';
    h += '</tr>';
    periods.forEach(function(p) {
      var bPct = p.broad_change_pct;
      var sPct = p.sector_change_pct;
      var bStr = bPct != null ? ((bPct > 0 ? '+' : '') + bPct.toFixed(2) + '%') : 'N/A';
      var sStr = sPct != null ? ((sPct > 0 ? '+' : '') + sPct.toFixed(2) + '%') : 'N/A';
      var bColor = bPct != null ? (bPct > 0 ? '#ef4444' : bPct < 0 ? '#10b981' : '#8b8fa4') : '#8b8fa4';
      var sColor = sPct != null ? (sPct > 0 ? '#ef4444' : sPct < 0 ? '#10b981' : '#8b8fa4') : '#8b8fa4';
      var bRange = (p.broad_from != null && p.broad_to != null) ? (p.broad_from.toFixed(1) + ' \u2192 ' + p.broad_to.toFixed(1)) : '-';
      var sRange = (p.sector_from != null && p.sector_to != null) ? (p.sector_from.toFixed(1) + ' \u2192 ' + p.sector_to.toFixed(1)) : '-';
      h += '<tr style="border-bottom:1px solid #1a1d2e">';
      h += '<td style="padding:8px 10px;font-weight:700;color:#e0e0e0">' + p.label + '</td>';
      h += '<td style="padding:8px 10px;text-align:center;color:#8b8fa4;font-size:0.9em">' + (p.ref_date || '-') + '</td>';
      h += '<td style="padding:8px 10px;text-align:right;font-weight:700;color:' + bColor + '">' + bStr + '</td>';
      h += '<td style="padding:8px 10px;text-align:right;color:#8b8fa4;font-size:0.88em">' + bRange + '</td>';
      h += '<td style="padding:8px 10px;text-align:right;font-weight:700;color:' + sColor + '">' + sStr + '</td>';
      h += '<td style="padding:8px 10px;text-align:right;color:#8b8fa4;font-size:0.88em">' + sRange + '</td>';
      h += '</tr>';
    });
    h += '</table>';
    h += '</div>';
  }

  var fs = d.fund_signals || {};
  if (fs.market_flow) {
    h += '<div style="margin-bottom:16px">';
    h += '<div style="font-size:0.85em;font-weight:600;color:#e0e0e0;margin-bottom:8px">&#128176; 资金信号</div>';
    var mf = fs.market_flow;
    var mfColor = mf.latest_net_yi > 0 ? '#ef4444' : mf.latest_net_yi < 0 ? '#10b981' : '#8b8fa4';
    var mfIcon = mf.latest_net_yi > 0 ? '&#9650;' : mf.latest_net_yi < 0 ? '&#9660;' : '&#9644;';
    h += '<div style="background:#0f1117;border:1px solid #2a2d3e;border-radius:8px;padding:12px 16px;max-width:400px">';
    h += '<div style="font-size:0.78em;color:#8b8fa4;margin-bottom:4px">全市场主力资金 <span style="color:#6b7280;font-size:0.9em" title="主力=超大单(>100万)+大单(20-100万), 代表机构/大户资金行为。此为A股全市场数据，不只是上方16只ETF。">(超大单+大单 · 全A股)</span></div>';
    h += '<div style="font-size:1.2em;font-weight:700;color:' + mfColor + '">' + mfIcon + ' ' + mf.signal + '</div>';
    h += '<div style="font-size:0.78em;color:#8b8fa4;margin-top:4px">今日净流入: <span style="color:' + mfColor + ';font-weight:600">' + (mf.latest_net_yi > 0 ? '+' : '') + mf.latest_net_yi + ' 亿</span></div>';
    h += '<div style="font-size:0.78em;color:#8b8fa4">5日均净流入: ' + (mf.avg_5d_net_yi > 0 ? '+' : '') + mf.avg_5d_net_yi + ' 亿</div>';
    if (mf.consecutive_inflow > 0) h += '<div style="font-size:0.78em;color:#ef4444">连续流入 ' + mf.consecutive_inflow + ' 日</div>';
    if (mf.consecutive_outflow > 0) h += '<div style="font-size:0.78em;color:#10b981">连续流出 ' + mf.consecutive_outflow + ' 日</div>';
    h += '</div>';
    h += '<div style="font-size:0.7em;color:#6b7280;margin-top:6px;line-height:1.4">';
    h += '\u2139\ufe0f <b>\u4e3b\u529b</b> = \u8d85\u5927\u5355(>100\u4e07) + \u5927\u5355(20-100\u4e07)\uff0c\u4ee3\u8868\u673a\u6784/\u5927\u6237\u8d44\u91d1\u884c\u4e3a\u3002'
    h += '<br>\u2139\ufe0f <b>\u8303\u56f4\u533a\u522b:</b> \u4e0a\u65b9\u201cETF\u4efd\u989d\u53d8\u52a8\u201d\u53cd\u6620\u7684\u662f<u>16\u53ea\u6838\u5fc3ETF</u>\u7684\u88ab\u52a8\u8d44\u91d1\uff0c\u4e0b\u65b9\u201c\u5168\u5e02\u573a\u4e3b\u529b\u8d44\u91d1\u201d\u662f<u>\u6240\u6709A\u80a1</u>\u7684\u4e3b\u52a8\u8d44\u91d1\u3002\u4e24\u8005\u53ef\u80fd\u77db\u76fe(\u5982\u5927\u76d8\u6d41\u51fa\u4f46\u56fd\u5bb6\u961f\u5355\u72ec\u589e\u6301ETF)\uff0c\u8fd9\u6b63\u662f\u62a4\u76d8\u7684\u5178\u578b\u4fe1\u53f7\u3002'
    h += '<br>\u2139\ufe0f \u673a\u6784\u6301\u4ed3\u4e3a\u5b63\u62a5\u6570\u636e\uff0c\u6709\u6ede\u540e\u6027\u3002';
    h += '</div>';
    h += '</div>';
  }

  if (sigs.anomalies && sigs.anomalies.length > 0) {
    h += '<div style="background:#1a0a0a;border:1px solid #ef4444;border-radius:8px;padding:10px 14px;margin-bottom:14px">';
    h += '<div style="color:#ef4444;font-weight:600;font-size:0.85em;margin-bottom:6px">&#9888; 异常变动</div>';
    sigs.anomalies.forEach(function(a) {
      var dir = a.direction === '增持' ? '&#9650;' : '&#9660;';
      var dc = a.direction === '增持' ? '#ef4444' : '#10b981';
      h += '<div style="font-size:0.82em;color:#e0e0e0;margin-bottom:3px">' + dir + ' <b style="color:' + dc + '">' + a.name + '</b> (' + a.code + '): ';
      h += a.prev_yi.toFixed(1) + ' &rarr; ' + a.curr_yi.toFixed(1) + ' 亿份 ';
      h += '<span style="color:' + dc + ';font-weight:600">(' + (a.change_pct > 0 ? '+' : '') + a.change_pct.toFixed(1) + '%)</span></div>';
    });
    h += '</div>';
  }

  // ── 综合研判 ──
  var _fs = d.fund_signals || {};
  var _mf = _fs.market_flow || {};
  var _etfSig = sigs.broad_total_change || '';
  var _tc = trend.total_change_pct;
  var _mfNet = _mf.latest_net_yi || 0;
  var _mfConsecIn = _mf.consecutive_inflow || 0;
  var _mfConsecOut = _mf.consecutive_outflow || 0;

  var _etfUp = _etfSig.indexOf('增持') >= 0;
  var _etfDown = _etfSig.indexOf('减持') >= 0;
  var _mfIn = _mfNet > 0;
  var _mfOut = _mfNet < 0;

  var _verdicts = [];
  if (_etfUp && _mfOut) {
    _verdicts.push({icon: '\ud83d\udee1\ufe0f', text: 'ETF\u4efd\u989d\u589e\u52a0\u4f46\u5168\u5e02\u573a\u4e3b\u529b\u8d44\u91d1\u6d41\u51fa \u2014 \u56fd\u5bb6\u961f\u9006\u5e02\u62a4\u76d8\u6982\u7387\u8f83\u9ad8', color: '#ef4444'});
  } else if (_etfUp && _mfIn) {
    _verdicts.push({icon: '\ud83d\ude80', text: 'ETF\u4efd\u989d\u4e0e\u5168\u5e02\u573a\u4e3b\u529b\u540c\u65f6\u6d41\u5165 \u2014 \u5e02\u573a\u6574\u4f53\u770b\u591a\uff0c\u8d44\u91d1\u5171\u632f', color: '#f59e0b'});
  } else if (_etfDown && _mfIn) {
    _verdicts.push({icon: '\u26a0\ufe0f', text: 'ETF\u4efd\u989d\u51cf\u5c11\u4f46\u5e02\u573a\u4e3b\u529b\u6d41\u5165 \u2014 \u8d44\u91d1\u7ed5\u8fc7ETF\u6e20\u9053\u5165\u573a\uff0c\u56fd\u5bb6\u961f\u53ef\u80fd\u51cf\u4ed3', color: '#3b82f6'});
  } else if (_etfDown && _mfOut) {
    _verdicts.push({icon: '\u2744\ufe0f', text: 'ETF\u4efd\u989d\u4e0e\u5168\u5e02\u573a\u4e3b\u529b\u540c\u65f6\u6d41\u51fa \u2014 \u5e02\u573a\u5168\u9762\u8c28\u614e', color: '#10b981'});
  }
  if (_tc != null && _tc > 5) {
    _verdicts.push({icon: '\ud83d\udcc8', text: 'ETF\u4efd\u989d\u8fd1\u671f\u7d2f\u8ba1\u589e\u957f' + _tc + '%\uff0c\u589e\u6301\u529b\u5ea6\u663e\u8457', color: '#ef4444'});
  } else if (_tc != null && _tc < -3) {
    _verdicts.push({icon: '\ud83d\udcc9', text: 'ETF\u4efd\u989d\u8fd1\u671f\u7d2f\u8ba1\u4e0b\u964d' + Math.abs(_tc) + '%\uff0c\u51cf\u6301\u8d8b\u52bf\u660e\u663e', color: '#10b981'});
  }
  if (_mfConsecIn >= 3) {
    _verdicts.push({icon: '\ud83d\udd25', text: '\u5168\u5e02\u573a\u4e3b\u529b\u8fde\u7eed' + _mfConsecIn + '\u65e5\u6d41\u5165\uff0c\u77ed\u671f\u505a\u591a\u60c5\u7eea\u5f3a\u70c8', color: '#f97316'});
  } else if (_mfConsecOut >= 3) {
    _verdicts.push({icon: '\ud83d\udca8', text: '\u5168\u5e02\u573a\u4e3b\u529b\u8fde\u7eed' + _mfConsecOut + '\u65e5\u6d41\u51fa\uff0c\u77ed\u671f\u505a\u7a7a\u538b\u529b\u8f83\u5927', color: '#10b981'});
  }
  var _p1w = null, _p1m = null, _p3m = null;
  (ps.periods || []).forEach(function(p) {
    if (p.label === '1\u5468') _p1w = p.broad_change_pct;
    if (p.label === '1\u6708') _p1m = p.broad_change_pct;
    if (p.label === '3\u6708') _p3m = p.broad_change_pct;
  });
  if (_p3m != null && _p1w != null) {
    if (_p3m > 3 && _p1w > 0) {
      _verdicts.push({icon: '\ud83c\udfaf', text: '3\u6708\u7d2f\u8ba1+' + _p3m.toFixed(1) + '%\u4e14\u8fd1\u5468\u4ecd\u5728\u589e\u6301 \u2014 \u957f\u7ebf\u5e03\u5c40\u6301\u7eed\u4e2d', color: '#f59e0b'});
    } else if (_p3m < -3 && _p1w < 0) {
      _verdicts.push({icon: '\u23f3', text: '3\u6708\u7d2f\u8ba1' + _p3m.toFixed(1) + '%\u4e14\u8fd1\u5468\u7ee7\u7eed\u51cf\u6301 \u2014 \u957f\u671f\u6301\u7eed\u64a4\u9000', color: '#10b981'});
    }
  }

  if (_verdicts.length > 0) {
    h += '<div style="margin-bottom:16px;background:linear-gradient(135deg,#0f1117 0%,#1a1530 100%);border:1px solid #6366f1;border-radius:10px;padding:14px 18px">';
    h += '<div style="font-size:0.88em;font-weight:700;color:#a78bfa;margin-bottom:10px">\ud83e\udde0 \u7efc\u5408\u7814\u5224</div>';
    _verdicts.forEach(function(v) {
      h += '<div style="font-size:0.84em;color:' + v.color + ';margin-bottom:6px;line-height:1.5">' + v.icon + ' ' + v.text + '</div>';
    });
    h += '</div>';
  }

  var broad = etfs.filter(function(e) { return e.type === '宽基'; });
  var sector = etfs.filter(function(e) { return e.type === '行业'; });
  var perEtf = (ps.per_etf_periods || []);
  var perEtfMap = {};
  perEtf.forEach(function(pe) { perEtfMap[pe.code] = pe; });

  h += '<h3 style="color:#60a5fa;margin:8px 0 6px">&#127970; 宽基ETF (' + broad.length + '只)</h3>';
  h += _ntTable(broad, perEtfMap);

  h += '<h3 style="color:#a78bfa;margin:12px 0 6px">&#127981; 行业ETF (' + sector.length + '只)</h3>';
  h += _ntTable(sector, perEtfMap);

  var bf = d.backfill || {};
  var bfMsg = bf.message ? (' | ' + bf.message + ' (总计 ' + (bf.total_history||0) + ' 个数据点)') : '';
  h += '<div style="margin-top:12px;font-size:0.72em;color:#6b7280">数据来源: 上交所/深交所 ETF份额公告 | 更新时间: ' + (snap.date||'') + bfMsg + '</div>';
  el.innerHTML = h;
}
function _ntTable(etfs, perEtfMap) {
  perEtfMap = perEtfMap || {};
  var hasPeriods = Object.keys(perEtfMap).length > 0;
  var h = '<table style="width:100%;border-collapse:collapse;font-size:0.82em">';
  h += '<tr style="border-bottom:1px solid #2a2d3e;color:#8b8fa4">';
  h += '<th style="text-align:left;padding:5px">名称</th><th style="padding:5px">代码</th><th style="padding:5px">跟踪指数</th><th style="text-align:right;padding:5px">份额(亿份)</th><th style="text-align:right;padding:5px">变化</th>';
  if (hasPeriods) h += '<th style="text-align:right;padding:5px;color:#f59e0b">1周</th><th style="text-align:right;padding:5px;color:#f59e0b">1月</th><th style="text-align:right;padding:5px;color:#f59e0b">3月</th>';
  h += '</tr>';
  etfs.forEach(function(e) {
    var yi = e.shares_yi;
    var chg = e.change_pct;
    var chgStr = '-';
    var chgColor = '#8b8fa4';
    if (chg != null) {
      chgStr = (chg > 0 ? '+' : '') + chg.toFixed(1) + '%';
      chgColor = chg > 0 ? '#ef4444' : chg < 0 ? '#10b981' : '#8b8fa4';
    }
    h += '<tr style="border-bottom:1px solid #1a1d2e">';
    h += '<td style="padding:5px;font-weight:600">' + e.name + '</td>';
    h += '<td style="padding:5px;text-align:center;color:#8b8fa4">' + e.code + '</td>';
    h += '<td style="padding:5px;text-align:center;color:#8b8fa4;font-size:0.9em">' + (e.index||'') + '</td>';
    h += '<td style="padding:5px;text-align:right;font-weight:600">' + (yi != null ? yi.toFixed(1) : 'N/A') + '</td>';
    h += '<td style="padding:5px;text-align:right;color:' + chgColor + ';font-weight:600">' + chgStr + '</td>';
    if (hasPeriods) {
      var pe = perEtfMap[e.code] || {};
      ['1w','1m','3m'].forEach(function(k) {
        var v = pe[k];
        var vs = v != null ? ((v > 0 ? '+' : '') + v.toFixed(1) + '%') : '-';
        var vc = v != null ? (v > 0 ? '#ef4444' : v < 0 ? '#10b981' : '#8b8fa4') : '#8b8fa4';
        h += '<td style="padding:5px;text-align:right;color:' + vc + ';font-size:0.88em">' + vs + '</td>';
      });
    }
    h += '</tr>';
  });
  h += '</table>';
  return h;
}

initSessions();
checkHealth();
setInterval(checkHealth, 30000);
</script>
</body>
</html>"""


@app.route("/")
def index():
    resp = make_response(render_template_string(AGENT_HTML))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ===================================================================
# MAIN
# ===================================================================

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18889
    print(f"Starting Jarvis on http://127.0.0.1:{port}", flush=True)
    print(f"Model: {OLLAMA_MODEL} via {OLLAMA_HOST}", flush=True)
    print("Preloading embedding model and Qdrant data...", flush=True)
    _get_embed_model()
    _get_qdrant()
    print("Ready! Open your browser.", flush=True)
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
