"""Toolbar API — Flask blueprint (background jobs, chunk stats, quick tools)."""

import glob
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta
from typing import Any, Iterator

from flask import Blueprint, Response, jsonify, request

_ROUTES_DIR = os.path.dirname(os.path.abspath(__file__))
_RAG_PKG_DIR = os.path.dirname(_ROUTES_DIR)
_SCRIPTS_DIR = os.path.dirname(_RAG_PKG_DIR)
for _p in (_SCRIPTS_DIR, _RAG_PKG_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config import REPORTS_ROOT

from rag_engine import COLLECTION, get_embed_model as _get_embed_model, get_qdrant as _get_qdrant

from tools import tool_commit_summary, tool_jira_report

toolbar_bp = Blueprint("toolbar", __name__)

_toolbar_jobs: dict[str, dict[str, Any]] = {}
_toolbar_jobs_lock = threading.Lock()
_chunk_analysis_cache: dict[str, Any] | None = None
_chunk_analysis_cache_time: float = 0.0
_chunk_analysis_cache_lock = threading.Lock()
CHUNK_ANALYSIS_CACHE_TTL = 60


def _agent():
    """Resolve loaded agent module (script as __main__, package import as agent/rag.agent)."""
    import sys

    for name in ("agent", "rag.agent", "__main__"):
        m = sys.modules.get(name)
        if m is not None and hasattr(m, "_now_iso"):
            return m
    return sys.modules["__main__"]


def _rag_scripts_dir() -> str:
    return _RAG_PKG_DIR


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


@toolbar_bp.route("/api/toolbar/reindex", methods=["POST"])
def api_toolbar_reindex():
    ag = _agent()
    job_id = str(uuid.uuid4())
    started = ag._now_iso()
    with _toolbar_jobs_lock:
        _toolbar_jobs[job_id] = {
            "status": "running",
            "started": started,
            "result": "",
            "kind": "index_new",
        }
    threading.Thread(target=_run_index_new_briefings, args=(job_id,), daemon=True).start()
    return jsonify({"job_id": job_id, "status": "started"})


@toolbar_bp.route("/api/toolbar/reindex/<job_id>", methods=["GET"])
@toolbar_bp.route("/api/toolbar/wiki-fetch/<job_id>", methods=["GET"])
def api_toolbar_job_status(job_id: str):
    with _toolbar_jobs_lock:
        job = _toolbar_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404
    return jsonify({"job_id": job_id, **job})


@toolbar_bp.route("/api/toolbar/chunk-analysis", methods=["GET"])
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


@toolbar_bp.route("/api/toolbar/deep-dive", methods=["POST"])
def api_toolbar_deep_dive():
    """Create a deep-dive learning session from a Learning Guide source URL."""
    ag = _agent()
    data = request.get_json(silent=True) or {}
    source_url = (data.get("source_url") or "").strip()
    title = (data.get("title") or "").strip()
    if not source_url and not title:
        return jsonify({"error": "source_url or title required"}), 400

    fetched_content = ""
    fetch_error = ""
    if source_url:
        fetched_content, fetch_error = ag._fetch_source_url_content(source_url)

    raw_file = (data.get("raw_file") or "").strip()
    raw_content = ""
    if raw_file and not fetched_content:
        raw_content = ag._read_raw_file_content(raw_file)

    content = fetched_content or raw_content
    if not content and not title:
        return jsonify({"error": "Could not fetch content and no title provided"}), 400

    ag._ensure_chat_sessions_dir()
    sid = str(uuid.uuid4())
    now = ag._now_iso()
    session_title = f"Deep Dive \u2014 {title}" if title else f"Deep Dive \u2014 {source_url[:60]}"

    teaching_context = f"Topic: {title}\n" if title else ""
    if source_url:
        teaching_context += f"Source: {source_url}\n"
    if content:
        max_content = 8000
        if len(content) > max_content:
            content = content[:max_content] + "\n\n[Content truncated for context window]"
        teaching_context += f"\n---\nSource content:\n{content}"

    initial_prompt = (
        f"I want to learn about this topic from my daily AI briefing. "
        f"Please provide a comprehensive explanation.\n\n{teaching_context}"
    )

    session_data = {
        "id": sid,
        "title": session_title,
        "created_at": now,
        "updated_at": now,
        "messages": [
            {"role": "user", "content": initial_prompt},
        ],
        "session_type": "deep_dive",
        "deep_dive_meta": {
            "source_url": source_url,
            "title": title,
            "raw_file": raw_file,
            "fetch_error": fetch_error,
        },
    }
    if not ag._save_session_file(session_data):
        return jsonify({"error": "Failed to create session"}), 500

    return jsonify({"session_id": sid, "title": session_title})


@toolbar_bp.route("/api/toolbar/wiki-fetch", methods=["POST"])
def api_toolbar_wiki_fetch():
    ag = _agent()
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
    started = ag._now_iso()
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
                script = os.path.join(_RAG_PKG_DIR, "index_confluence_user.py")
                cmd = [sys.executable, script, user]
                if d_from:
                    cmd.extend(["--date-from", d_from])
                if d_to:
                    cmd.extend(["--date-to", d_to])
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=600,
                    cwd=_RAG_PKG_DIR,
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


@toolbar_bp.route("/api/toolbar/commit-summary", methods=["POST"])
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


@toolbar_bp.route("/api/toolbar/jira-report", methods=["POST"])
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
    """Payloads from qdrant_points snapshot cache, or live Qdrant scroll if cache empty."""
    from rag_engine import (
        get_qdrant,
        get_qdrant_points,
        sync_qdrant_points_from_snapshot as _sync_qdrant_points_from_snapshot,
    )

    get_qdrant()
    _sync_qdrant_points_from_snapshot()
    _points = get_qdrant_points()
    if _points:
        for entry in _points:
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


@toolbar_bp.route("/api/toolbar/trend-analysis", methods=["POST"])
def api_toolbar_trend_analysis():
    ag = _agent()
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

    ollama_host = ag.OLLAMA_HOST
    ollama_model_fast = ag.OLLAMA_MODEL_FAST

    def _stream_one_category(req_mod, cat_key, block_text):
        """Analyze one category via chat API with thinking disabled for speed."""
        label = cat_labels.get(cat_key, cat_key)
        user_msg = (
            f"Based on the following {label} data from the last {days} days "
            f"({start_s} to {end_s}), provide **predictions for the next 1-2 weeks**.\n\n"
            f"FORMAT REQUIREMENTS (strict):\n"
            f"Write each prediction as a separate block using this template:\n\n"
            f"### Prediction N: <title>\n\n"
            f"**Trend**: <one sentence describing what will happen>\n\n"
            f"**Supporting Evidence**:\n"
            f"- <data point 1>\n"
            f"- <data point 2>\n\n"
            f"**Confidence**: High / Medium / Low\n\n"
            f"**Team Impact**: <how this affects our team>\n\n"
            f"---\n\n"
            f"Provide 3-5 predictions. Separate each with a blank line and `---`.\n"
            f"Think deeply about patterns, trajectories, and implications.\n\n"
            f"DATA:\n{block_text[:6000]}"
        )
        try:
            resp = req_mod.post(
                f"{ollama_host}/api/chat",
                json={
                    "model": ollama_model_fast,
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
