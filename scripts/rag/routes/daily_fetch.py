"""Daily fetch pipeline and learning-session API — Flask blueprint (extracted from agent.py)."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import uuid as _uuid
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request

_ROUTES_DIR = os.path.dirname(os.path.abspath(__file__))
_RAG_DIR = os.path.dirname(_ROUTES_DIR)
_SCRIPTS_DIR = os.path.dirname(_RAG_DIR)
for _p in (_SCRIPTS_DIR, _RAG_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config import JIRA_REPORT_SCRIPT, KNOWLEDGE_ROOT, REPORTS_ROOT
from tools import tool_commit_summary
from learning.constants import LEARNING_SESSION_IDS as _LEARNING_SESSION_IDS
from routes.ai_news import _generate_segmented_narrations, _load_ai_kb, _tts_segments_to_mp3

daily_fetch_bp = Blueprint("daily_fetch", __name__)
_log = logging.getLogger(__name__)

JIRA_SCRIPT = JIRA_REPORT_SCRIPT


def _resolve_agent():
    """Lazy handle to loaded agent or __main__ (session helpers, KB, Ollama globals)."""
    for name in ("agent", "rag.agent", "__main__"):
        m = sys.modules.get(name)
        if m is not None and hasattr(m, "_load_session_file"):
            return m
    return sys.modules["__main__"]


def _get_global_settings() -> dict:
    """Get global settings reliably — tries in-memory first, falls back to disk."""
    gs = getattr(_resolve_agent(), "_GLOBAL_SETTINGS", None)
    if gs and isinstance(gs, dict) and any(k.startswith("audio_lang") for k in gs):
        return gs
    _log.warning("_GLOBAL_SETTINGS not found in-memory (got %r), reading from disk", type(gs))
    settings_file = os.path.join(_RAG_DIR, ".global_settings.json")
    if os.path.isfile(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                return json.loads(f.read())
        except Exception as e:
            _log.error("Failed to read settings file %s: %s", settings_file, e)
    return {}


_AUDIO_STEP_LANG_KEYS = {
    "ai_audio": "audio_lang_ai",
    "world_audio": "audio_lang_world",
    "china_audio": "audio_lang_china",
    "wiki_audio": "audio_lang_wiki",
}


def _resolve_audio_lang(step: str, gs: dict, lang_overrides: dict | None) -> str:
    """Resolve narration language for a daily-fetch audio step."""
    if lang_overrides and step in lang_overrides:
        lang = lang_overrides[step]
        if lang in ("zh", "en"):
            return lang
    setting_key = _AUDIO_STEP_LANG_KEYS.get(step, "audio_lang_ai")
    return gs.get(setting_key, "zh")


# ---------------------------------------------------------------------------
# AI Learning — ingest daily AI news into learning knowledge base
# ---------------------------------------------------------------------------


_AI_NEWS_CATEGORIES: dict[str, list[str]] = {
    "LLM Releases & Model Updates": [
        "gpt", "claude", "gemini", "llama", "mistral", "qwen", "phi",
        "model release", "new model", "benchmark", "parameter", "weights",
        "open-source model", "deepseek", "command r", "cohere",
    ],
    "AI Agents & Coding Tools": [
        "agent", "copilot", "cursor", "code", "coding", "claude code",
        "devin", "aider", "windsurf", "mcp", "tool calling", "function call",
        "auto mode", "managed agent", "sdk",
    ],
    "RAG, Search & Information Retrieval": [
        "rag", "retrieval", "search", "embedding", "vector", "rerank",
        "knowledge base", "semantic search", "hybrid search",
    ],
    "AI Safety, Ethics & Regulation": [
        "safety", "regulation", "policy", "bias", "alignment", "guardrail",
        "responsible", "hallucination", "jailbreak", "red team",
        "eu ai act", "governance",
    ],
    "AI Infrastructure & Deployment": [
        "inference", "serving", "deploy", "gpu", "tpu", "cloud",
        "quantiz", "vllm", "tensorrt", "onnx", "optimization",
        "latency", "throughput", "cost",
    ],
    "AI Products & Applications": [
        "product", "launch", "feature", "api", "app", "platform",
        "enterprise", "startup", "funding", "acquisition", "partnership",
        "openai", "anthropic", "google", "meta", "microsoft",
    ],
    "Research & Papers": [
        "paper", "research", "arxiv", "study", "finding", "breakthrough",
        "technique", "method", "architecture", "training",
        "fine-tun", "finetun", "pre-train", "pretrain",
    ],
}


def _categorize_ai_news(title: str, summary: str) -> str:
    text = (title + " " + summary).lower()
    scores = {}
    for cat, keywords in _AI_NEWS_CATEGORIES.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[cat] = score
    return max(scores, key=scores.get) if scores else "AI Products & Applications"


def _ingest_ai_news_to_learning(output_dir: str, date_str: str) -> int:
    """Extract AI news items from daily briefing and append to learning notes.

    Adds new items to ``ai_learning/08-ai-news-digest.md`` with deduplication
    based on title hash and categorization by AI topic.  Returns item count.
    """
    import json as _json
    import hashlib

    data_file = os.path.join(output_dir, "briefing-data-filtered.json")
    if not os.path.isfile(data_file):
        data_file = os.path.join(output_dir, "briefing-data.json")
    if not os.path.isfile(data_file):
        return 0

    with open(data_file, "r", encoding="utf-8") as f:
        bdata = _json.load(f)

    items: list[dict] = []
    for src_block in bdata.get("per_source_data", []):
        src_name = src_block.get("source_name") or src_block.get("name", "")
        for it in src_block.get("items", []):
            title = (it.get("title") or "").strip()
            summary = (it.get("summary") or it.get("description") or "").strip()
            url = (it.get("url") or it.get("link") or "").strip()
            if title:
                items.append({
                    "title": title,
                    "summary": summary[:500],
                    "source": src_name,
                    "url": url,
                    "category": _categorize_ai_news(title, summary),
                })

    if not items:
        return 0

    notes_dir = os.path.join(KNOWLEDGE_ROOT, "notes", "ai_learning")
    os.makedirs(notes_dir, exist_ok=True)
    digest_path = os.path.join(notes_dir, "08-ai-news-digest.md")

    existing_hashes: set[str] = set()
    existing_content = ""
    if os.path.isfile(digest_path):
        with open(digest_path, "r", encoding="utf-8") as f:
            existing_content = f.read()
        for line in existing_content.split("\n"):
            if line.startswith("### "):
                title_text = line.replace("### ", "").strip()
                h = hashlib.md5(title_text.lower().encode()).hexdigest()
                existing_hashes.add(h)

    new_items: list[dict] = []
    for it in items:
        h = hashlib.md5(it["title"].lower().encode()).hexdigest()
        if h in existing_hashes:
            continue
        existing_hashes.add(h)
        new_items.append(it)

    if not new_items:
        return 0

    from collections import defaultdict
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for it in new_items:
        by_cat[it["category"]].append(it)

    new_sections: list[str] = [f"\n## {date_str}\n"]
    for cat_name in _AI_NEWS_CATEGORIES:
        cat_items = by_cat.get(cat_name, [])
        if not cat_items:
            continue
        new_sections.append(f"\n**{cat_name}**\n")
        for it in cat_items:
            entry = f"### {it['title']}\n"
            entry += f"**Source:** {it['source']} | **Date:** {date_str}"
            if it["url"]:
                entry += f" | [Link]({it['url']})"
            entry += "\n\n"
            if it["summary"]:
                clean = it["summary"].replace("\n", " ").strip()
                entry += f"{clean}\n"
            new_sections.append(entry)

    if not existing_content:
        existing_content = (
            "# Domain 8: AI Industry & Recent Developments\n\n"
            "Auto-populated from daily AI briefings. Each entry represents a "
            "notable development in AI/ML, categorized by topic to supplement "
            "the structured learning notes.\n\n---\n"
        )

    existing_content += "\n".join(new_sections) + "\n"

    with open(digest_path, "w", encoding="utf-8") as f:
        f.write(existing_content)

    return len(new_items)


# ---------------------------------------------------------------------------
# Daily Fetch (full briefing pipeline + commit + jira)
# ---------------------------------------------------------------------------

_daily_fetch_jobs: dict[str, dict] = {}


def _check_wn_translated(output_dir: str) -> bool:
    wn_path = os.path.join(output_dir, "world-news", "world-news-data.json")
    if not os.path.isfile(wn_path):
        return False
    try:
        with open(wn_path, "r", encoding="utf-8") as f:
            return json.load(f).get("translated", False)
    except Exception:
        return False


def _run_daily_fetch(
    job_id: str,
    *,
    only_steps: list | None = None,
    target_date: str | None = None,
    lang_overrides: dict | None = None,
):
    """Background worker: run full briefing pipeline, then commit report + Jira daily.

    If *only_steps* is provided (non-empty list), only those pipeline steps are
    executed — used by the "Continue" button to finish an incomplete run.
    *lang_overrides* maps audio step names (e.g. ``ai_audio``) to ``zh`` or ``en``.
    """
    import subprocess as sp
    job = _daily_fetch_jobs[job_id]
    job["lang_overrides"] = lang_overrides or {}
    today = target_date or datetime.now().strftime("%Y-%m-%d")
    output_dir = os.path.join(REPORTS_ROOT, today)
    _should_run = lambda step_name: not only_steps or step_name in only_steps  # noqa: E731
    os.makedirs(output_dir, exist_ok=True)
    scripts_dir = _SCRIPTS_DIR
    steps = []

    def _already_done(step_name: str) -> bool:
        """Check whether a step's output files already exist for today.
        Returns True (and appends a 'skipped' entry to *steps*) when the step
        can safely be skipped because its artefacts are already on disk.
        Only applies to full runs (not partial/only_steps runs where the user
        explicitly requested a step).
        """
        if only_steps:
            return False
        checks = {
            "fetch_sources": lambda: os.path.isfile(os.path.join(output_dir, "briefing-data.json")),
            "topic_dedup": lambda: os.path.isfile(os.path.join(output_dir, "briefing-data-filtered.json")),
            "ai_audio": lambda: os.path.isfile(os.path.join(output_dir, "ai-briefing.mp3")),
            "world_audio": lambda: os.path.isfile(os.path.join(output_dir, "world-news.mp3")),
            "china_audio": lambda: os.path.isfile(os.path.join(output_dir, "china-news.mp3")),
            "wiki_audio": lambda: os.path.isfile(os.path.join(output_dir, "wiki-report.mp3")),
            "commit_report": lambda: any(
                f.startswith("commit-report-") and f.endswith(".md")
                for f in os.listdir(output_dir)
            ) if os.path.isdir(output_dir) else False,
            "jira_daily": lambda: os.path.isfile(
                os.path.join(output_dir, f"atlassian-daily-report-{today.replace('-', '')}.md")
            ),
            "wiki_fetch": lambda: any(
                f.startswith("wiki-fetch-") and f.endswith(".md")
                for f in os.listdir(output_dir)
            ) if os.path.isdir(output_dir) else False,
            "world_news_translate": lambda: _check_wn_translated(output_dir),
        }
        check_fn = checks.get(step_name)
        if check_fn and check_fn():
            steps.append({"step": step_name, "exit_code": 0,
                          "output": f"Skipped — already completed for {today}"})
            return True
        return False

    try:
        job["status"] = "fetching"
        if _should_run("fetch_sources") and not _already_done("fetch_sources"):
            job["step"] = "Running AI + world news fetchers..."
            try:
                run_all = os.path.join(scripts_dir, "pipeline", "run-all-sources.py")
                cmd = ["python", run_all, "--output-dir", output_dir]
                proxy_url = os.environ.get("BRIEFING_PROXY", "")
                if proxy_url:
                    cmd.extend(["--proxy", proxy_url])
                r = sp.run(
                    cmd,
                    capture_output=True, text=False, timeout=600, cwd=scripts_dir
                )
                stdout = r.stdout.decode("utf-8", errors="replace") if r.stdout else ""
                steps.append({"step": "fetch_sources", "exit_code": r.returncode, "output": stdout[-500:]})
            except Exception as e:
                steps.append({"step": "fetch_sources", "exit_code": 1, "output": str(e)[:300]})

        if _should_run("topic_dedup") and not _already_done("topic_dedup"):
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

        if _should_run("ai_learning_knowledge"):
            job["step"] = "Extracting AI news into learning knowledge..."
            try:
                _ingest_ai_news_to_learning(output_dir, today)
                steps.append({"step": "ai_learning_knowledge", "exit_code": 0,
                              "output": "AI learning knowledge updated"})
            except Exception as e:
                steps.append({"step": "ai_learning_knowledge", "exit_code": 1,
                              "output": str(e)[:300]})

        commit_text = ""
        if _should_run("commit_report") and not _already_done("commit_report"):
            job["step"] = "Running commit report (24h)..."
            try:
                commit_script = os.path.join(scripts_dir, "tools", "commit-report.ps1")
                if os.path.exists(commit_script):
                    rc = sp.run(
                        ["powershell", "-ExecutionPolicy", "Bypass", "-File", commit_script,
                         "-Hours", "24", "-OutputDir", REPORTS_ROOT],
                        capture_output=True, text=False, timeout=600, cwd=scripts_dir
                    )
                    raw_out = rc.stdout.decode("utf-8", errors="replace") if rc.stdout else ""
                    if "---DATA_START---" in raw_out:
                        commit_text = raw_out.split("---DATA_START---")[1].split("---DATA_END---")[0].strip()
                    else:
                        commit_text = raw_out[-2000:]
                    steps.append({"step": "commit_report", "exit_code": rc.returncode,
                                  "output": raw_out[:raw_out.find("---DATA_START---")][-500:] if "---DATA_START---" in raw_out else raw_out[-500:]})
                else:
                    commit_text = tool_commit_summary(hours=24)
                    steps.append({"step": "commit_report", "exit_code": 0, "output": commit_text[:500]})
            except Exception as e:
                steps.append({"step": "commit_report", "exit_code": 1, "output": str(e)[:200]})

        jira_text = ""
        if _should_run("jira_daily") and not _already_done("jira_daily"):
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
        all_user_pages_detail = {}
        if _should_run("wiki_fetch") and not _already_done("wiki_fetch"):
            job["step"] = "Running Wiki Fetch for all team members..."
            _WIKI_USERS = [
                "Rong Yin", "Raymond Shen", "Charlotte Jiang",
                "Christoph Scheben", "Tobias Troesch",
                "Belen Liu", "Eason Li", "Johnny Yang",
                "Bin Si", "Deniz Erginos", "Djilija Vranic",
                "Dominik Kowalski", "Eatin Yang", "Ehsan Esmaili",
                "Emrys MacInally", "Erik Zweier", "Holger Pflüger",
                "Jan Loeffler", "Martin Leim", "Mathias Stümpert",
                "Michael Mauer", "Patrick Höhle", "Quan Cheng",
                "Samer Abdalla", "Steffen Eitelmann", "Tamino Fischer",
                "Thomas Freier", "Thomas Simon",
            ]
            try:
                script = os.path.join(_RAG_DIR, "index_confluence_user.py")
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
                                      cwd=_RAG_DIR)
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
                    change_summary = page_detail.get("change_summary", "").strip()
                    version_number = page_detail.get("version_number", 1)
                    if not raw_summary and not change_summary:
                        return ""

                    is_update = version_number > 1 and change_summary
                    context_parts = [f"Page title: {title}"]
                    if headings:
                        context_parts.append(f"Sections: {', '.join(headings[:8])}")

                    if is_update:
                        context_parts.append(f"Changes in this update:\n{change_summary}")
                        system_prompt = (
                            "You are a concise technical writer. Given a Confluence wiki page's "
                            "change diff, write a 1-2 sentence summary of what was actually "
                            "changed or updated. Focus on what was added, modified, or removed. "
                            "Be specific and factual. Output only the summary, no labels or prefixes."
                        )
                    else:
                        context_parts.append(f"Content excerpt:\n{raw_summary}")
                        system_prompt = (
                            "You are a concise technical writer. Given a new Confluence wiki page's content, "
                            "write a 1-2 sentence summary of what this page covers. "
                            "Be specific and factual. Output only the summary, no labels or prefixes."
                        )

                    context = "\n".join(context_parts)
                    try:
                        import requests as _req

                        agent = _resolve_agent()
                        ohost = getattr(agent, "OLLAMA_HOST", os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
                        omodel_fast = getattr(
                            agent, "OLLAMA_MODEL_FAST", os.environ.get("OLLAMA_MODEL_FAST", "qwen3:1.7b"),
                        )

                        resp = _req.post(
                            f"{ohost}/api/chat",
                            json={
                                "model": omodel_fast,
                                "messages": [
                                    {"role": "system", "content": system_prompt},
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

                wiki_details_json = os.path.join(output_dir, f"wiki-details-{today}.json")
                if all_user_pages_detail:
                    with open(wiki_details_json, "w", encoding="utf-8") as wdj:
                        json.dump(all_user_pages_detail, wdj, ensure_ascii=False, indent=2)

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
                                version_number = pg.get("version_number", 1)
                                is_new = version_number <= 1

                                if url:
                                    wf.write(f"- **[{title}]({url})**")
                                else:
                                    wf.write(f"- **{title}**")
                                if space:
                                    wf.write(f" — *{space}*")
                                if modified:
                                    wf.write(f" (modified: {modified})")
                                if is_new:
                                    wf.write(" \U0001f195")
                                wf.write("\n")
                                if ai_summary:
                                    label = "Summary" if is_new else "Changes"
                                    wf.write(f"  > **{label}:** {ai_summary}\n")
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
                        src_name = src_block.get("source_name") or src_block.get("name") or ""
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

        summary_parts.append("## Git Commits (Last 24h)")
        summary_parts.append(commit_text[:4000] if commit_text else "No commits found")
        summary_parts.append("")

        summary_parts.append("## Jira Daily Report")
        summary_parts.append(jira_text[:4000] if jira_text else "No Jira report available")

        job["daily_summary"] = "\n".join(summary_parts)

        # --- Refetch AI sources (for Recreate with fresh data) ---
        if _should_run("refetch_ai"):
            job["step"] = "Re-fetching AI sources..."
            try:
                run_all = os.path.join(scripts_dir, "pipeline", "run-all-sources.py")
                r_ai = sp.run(
                    ["python", run_all, "--output-dir", output_dir],
                    capture_output=True, text=False, timeout=600, cwd=scripts_dir
                )
                stdout_ai = r_ai.stdout.decode("utf-8", errors="replace") if r_ai.stdout else ""
                steps.append({"step": "refetch_ai", "exit_code": r_ai.returncode, "output": stdout_ai[-500:]})
                if r_ai.returncode == 0:
                    filter_script = os.path.join(scripts_dir, "pipeline", "filter_topics.py")
                    input_json = os.path.join(output_dir, "briefing-data.json")
                    filtered_json = os.path.join(output_dir, "briefing-data-filtered.json")
                    if os.path.exists(input_json):
                        job["step"] = "Running topic deduplication on fresh data..."
                        sp.run(
                            ["python", filter_script, input_json, filtered_json, "--mode", "aggressive"],
                            capture_output=True, text=False, timeout=60, cwd=scripts_dir
                        )
            except Exception as e:
                steps.append({"step": "refetch_ai", "exit_code": 1, "output": str(e)[:300]})

        # --- Audio generation: AI Briefing (segmented per-source) ---
        if _should_run("ai_audio") and not _already_done("ai_audio"):
            job["step"] = "Generating AI briefing audio (segmented)..."
            try:
                data_file = os.path.join(output_dir, "briefing-data.json")
                if not os.path.exists(data_file):
                    data_file = os.path.join(output_dir, "briefing-data-filtered.json")
                if os.path.exists(data_file):
                    import json as _json
                    with open(data_file, "r", encoding="utf-8") as df:
                        bdata = _json.load(df)
                    ai_segments: list[dict] = []
                    for src_block in (bdata.get("per_source_data") or []):
                        src_name = src_block.get("source_name") or src_block.get("name") or ""
                        items_text_parts = []
                        for it in src_block.get("items", [])[:3]:
                            title = it.get("title", "")
                            summary_text = it.get("summary") or it.get("description") or ""
                            url = it.get("url") or ""
                            points = it.get("points") or []
                            if not title:
                                continue
                            parts = [title]
                            if summary_text:
                                parts.append(summary_text)
                            else:
                                if points:
                                    parts.append(" | ".join(str(p) for p in points[:5]))
                                if url:
                                    parts.append(f"Source: {url}")
                            items_text_parts.append("\n".join(parts))
                        if items_text_parts:
                            ai_segments.append({
                                "name": src_name or "AI News",
                                "content": "\n\n".join(items_text_parts),
                            })
                    if ai_segments:
                        gs = _get_global_settings()
                        ai_lang = _resolve_audio_lang("ai_audio", gs, job.get("lang_overrides"))
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

        # --- Refetch World News sources (for Recreate with fresh data) ---
        if _should_run("refetch_world"):
            job["step"] = "Re-fetching world news sources..."
            try:
                wn_dir = os.path.join(output_dir, "world-news")
                os.makedirs(wn_dir, exist_ok=True)
                wn_script = os.path.join(scripts_dir, "pipeline", "run-world-news.py")
                r_wn = sp.run(
                    ["python", wn_script, "--output-dir", wn_dir, "--no-translate"],
                    capture_output=True, text=False, timeout=900, cwd=scripts_dir
                )
                stdout_wn = r_wn.stdout.decode("utf-8", errors="replace") if r_wn.stdout else ""
                steps.append({"step": "refetch_world", "exit_code": r_wn.returncode, "output": stdout_wn[-500:]})
            except Exception as e:
                steps.append({"step": "refetch_world", "exit_code": 1, "output": str(e)[:300]})

        # --- Translate world news to Chinese (separate step to avoid timeout) ---
        if _should_run("world_news_translate") and not _already_done("world_news_translate"):
            wn_dir = os.path.join(output_dir, "world-news")
            wn_merged_path = os.path.join(wn_dir, "world-news-data.json")
            if os.path.isfile(wn_merged_path):
                job["step"] = "Translating world news to Chinese..."
                try:
                    with open(wn_merged_path, "r", encoding="utf-8") as f:
                        wn_data = json.load(f)
                    if not wn_data.get("translated"):
                        import importlib.util
                        _wn_spec = importlib.util.spec_from_file_location(
                            "run_world_news",
                            os.path.join(scripts_dir, "pipeline", "run-world-news.py"))
                        _wn_mod = importlib.util.module_from_spec(_wn_spec)
                        _wn_spec.loader.exec_module(_wn_mod)
                        wn_data = _wn_mod.translate_news_to_chinese(wn_data)
                        with open(wn_merged_path, "w", encoding="utf-8") as f:
                            json.dump(wn_data, f, ensure_ascii=False, indent=2)
                        steps.append({"step": "world_news_translate", "exit_code": 0,
                                      "output": "Translation complete"})
                    else:
                        steps.append({"step": "world_news_translate", "exit_code": 0,
                                      "output": "Already translated"})
                except Exception as e:
                    steps.append({"step": "world_news_translate", "exit_code": 1,
                                  "output": str(e)[:300]})
            else:
                steps.append({"step": "world_news_translate", "exit_code": -1,
                              "output": "No world-news-data.json to translate"})

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
                        merge_script = os.path.join(_SCRIPTS_DIR, "pipeline", "run-world-news.py")
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

        if _should_run("world_audio") and not _already_done("world_audio"):
            job["step"] = "Generating world news audio..."
            try:
                wn_file = os.path.join(output_dir, "world-news", "world-news-data.json")
                if os.path.exists(wn_file):
                    import json as _json
                    with open(wn_file, "r", encoding="utf-8") as wf:
                        wdata = _json.load(wf)
                    categories = wdata.get("categories") or []

                    gs = _get_global_settings()
                    wn_lang = _resolve_audio_lang("world_audio", gs, job.get("lang_overrides"))
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

        if _should_run("china_audio") and not _already_done("china_audio"):
            job["step"] = "Generating Chinese news audio..."
            try:
                wn_file = os.path.join(output_dir, "world-news", "world-news-data.json")
                if os.path.exists(wn_file):
                    import json as _json
                    with open(wn_file, "r", encoding="utf-8") as wf:
                        wdata = _json.load(wf)
                    categories = wdata.get("categories") or []

                    gs = _get_global_settings()
                    cn_lang = _resolve_audio_lang("china_audio", gs, job.get("lang_overrides"))
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

        # --- Audio generation: Wiki Fetch Report (purpose, changes, author per page) ---
        if _should_run("wiki_audio") and not _already_done("wiki_audio"):
            job["step"] = "Generating Wiki Fetch Report audio..."
            try:
                wiki_details_file = None
                for fn in os.listdir(output_dir):
                    if fn.startswith("wiki-details-") and fn.endswith(".json"):
                        wiki_details_file = os.path.join(output_dir, fn)
                        break

                wiki_page_details: dict[str, list[dict]] = {}
                if wiki_details_file and os.path.isfile(wiki_details_file):
                    with open(wiki_details_file, "r", encoding="utf-8") as wdf:
                        wiki_page_details = json.load(wdf)
                elif all_user_pages_detail:
                    wiki_page_details = all_user_pages_detail

                if wiki_page_details:
                    wiki_segments: list[dict] = []
                    for user, pages in wiki_page_details.items():
                        if not pages:
                            continue
                        page_texts: list[str] = []
                        for pg in pages:
                            title = pg.get("title", "Untitled")
                            space = pg.get("space", "")
                            version = pg.get("version_number", 1)
                            ai_summary = pg.get("ai_summary", "")
                            raw_summary = pg.get("summary", "").strip()
                            headings = pg.get("headings", [])

                            parts = [f"Page: {title}"]
                            if space:
                                parts.append(f"Space: {space}")
                            parts.append(f"Author: {user}")
                            if version <= 1:
                                parts.append("This is a newly created page.")
                            else:
                                parts.append(f"This page was updated (version {version}).")
                            if ai_summary:
                                parts.append(f"Summary: {ai_summary}")
                            elif raw_summary:
                                parts.append(f"Content: {raw_summary[:300]}")
                            if headings:
                                parts.append(f"Sections: {', '.join(headings[:6])}")
                            page_texts.append("\n".join(parts))

                        if page_texts:
                            wiki_segments.append({
                                "name": f"{user}'s Wiki Updates",
                                "content": "\n\n".join(page_texts),
                            })

                    if wiki_segments:
                        gs = _get_global_settings()
                        wiki_lang = _resolve_audio_lang("wiki_audio", gs, job.get("lang_overrides"))
                        wiki_voice = "en-US-AndrewNeural" if wiki_lang == "en" else "zh-CN-YunxiNeural"
                        job["step"] = f"Generating Wiki narration ({len(wiki_segments)} segments, lang={wiki_lang})..."
                        narrations_wiki = _generate_segmented_narrations(
                            wiki_segments, "wiki", lang=wiki_lang,
                        )
                        if narrations_wiki:
                            total_chars = sum(len(n) for n in narrations_wiki)
                            wiki_mp3 = os.path.join(output_dir, "wiki-report.mp3")
                            _tts_segments_to_mp3(narrations_wiki, wiki_mp3, voice=wiki_voice)
                            steps.append({"step": "wiki_audio", "exit_code": 0,
                                          "output": f"Generated wiki-report.mp3 ({len(narrations_wiki)} segments, {total_chars} chars)"})
                        else:
                            steps.append({"step": "wiki_audio", "exit_code": 1,
                                          "output": "Wiki narration generation failed"})
                    else:
                        steps.append({"step": "wiki_audio", "exit_code": -1,
                                      "output": "No wiki pages with content to narrate"})
                else:
                    steps.append({"step": "wiki_audio", "exit_code": -1,
                                  "output": "No wiki details data found"})
            except Exception as e:
                steps.append({"step": "wiki_audio", "exit_code": 1, "output": str(e)[:300]})

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


@daily_fetch_bp.route("/api/toolbar/daily-fetch", methods=["POST"])
def api_daily_fetch():
    """Start the daily fetch pipeline as a background job."""
    job_id = str(_uuid.uuid4())[:8]
    _daily_fetch_jobs[job_id] = {"status": "starting", "step": "Initializing...", "steps": [], "files": []}
    t = threading.Thread(target=_run_daily_fetch, args=(job_id,), daemon=True)
    t.start()
    return jsonify({"job_id": job_id})


@daily_fetch_bp.route("/api/toolbar/daily-fetch/continue", methods=["POST"])
def api_daily_fetch_continue():
    """Continue a partially-completed daily fetch — runs only the missing steps."""
    data = request.get_json(silent=True) or {}
    only_steps = data.get("steps") or []
    target_date = data.get("date") or datetime.now().strftime("%Y-%m-%d")
    lang_overrides = data.get("lang_overrides") or {}
    job_id = str(_uuid.uuid4())[:8]
    _daily_fetch_jobs[job_id] = {
        "status": "starting",
        "step": "Continuing...",
        "steps": [],
        "files": [],
        "lang_overrides": lang_overrides,
    }
    t = threading.Thread(
        target=_run_daily_fetch,
        args=(job_id,),
        kwargs={
            "only_steps": only_steps,
            "target_date": target_date,
            "lang_overrides": lang_overrides,
        },
        daemon=True,
    )
    t.start()
    return jsonify({"job_id": job_id, "running_steps": only_steps})


@daily_fetch_bp.route("/api/toolbar/daily-fetch/<job_id>", methods=["GET"])
def api_daily_fetch_status(job_id):
    """Poll daily fetch job status."""
    job = _daily_fetch_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@daily_fetch_bp.route("/api/toolbar/daily-fetch/history", methods=["GET"])
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
    ai_by_source: dict[str, int] = {}
    wn_count = 0
    wn_by_source: dict[str, int] = {}
    cn_count = 0
    cn_by_source: dict[str, int] = {}
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
                src_name = src.get("source_name") or src.get("name") or "Unknown"
                item_count = len(src.get("items") or [])
                ai_count += item_count
                ai_by_source[src_name] = ai_by_source.get(src_name, 0) + item_count
        except Exception:
            pass

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
                        src_label = it.get("source", "")
                        if _CHINA_TAG in src_label:
                            cn_count += 1
                            cn_by_source[src_label] = cn_by_source.get(src_label, 0) + 1
                        else:
                            wn_count += 1
                            wn_by_source[src_label] = wn_by_source.get(src_label, 0) + 1
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
    has_wiki_audio = os.path.isfile(os.path.join(date_dir, "wiki-report.mp3"))
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
    if has_wn_data:
        try:
            with open(wn_file, "r", encoding="utf-8") as _wf:
                _wn_check = json.load(_wf)
            if not _wn_check.get("translated"):
                missing_steps.append("world_news_translate")
        except Exception:
            pass
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
    has_wiki_details = any(f.startswith("wiki-details-") and f.endswith(".json")
                          for f in os.listdir(date_dir)) if os.path.isdir(date_dir) else False
    if not has_wiki_audio and (has_wiki_details or has_wiki):
        if has_wiki and not has_wiki_details:
            missing_steps.append("wiki_fetch")
        missing_steps.append("wiki_audio")

    date_dirs = sorted(
        [d for d in os.listdir(REPORTS_ROOT)
         if os.path.isdir(os.path.join(REPORTS_ROOT, d)) and d[:4].isdigit()],
        reverse=True,
    )[:30]

    gs = _get_global_settings()
    audio_langs = {
        "audio_lang_ai": gs.get("audio_lang_ai", "zh"),
        "audio_lang_world": gs.get("audio_lang_world", "zh"),
        "audio_lang_china": gs.get("audio_lang_china", "zh"),
        "audio_lang_wiki": gs.get("audio_lang_wiki", "en"),
    }

    return jsonify({
        "date": target_date,
        "files": files,
        "audio_langs": audio_langs,
        "stats": {
            "ai_items": ai_count,
            "ai_by_source": ai_by_source,
            "world_news_items": wn_count,
            "world_by_source": wn_by_source,
            "china_news_items": cn_count,
            "china_by_source": cn_by_source,
            "jira_tickets": jira_tickets,
            "confluence_pages": confluence_pages,
            "wiki_pages": wiki_pages,
        },
        "has_audio": has_audio,
        "has_wn_audio": has_wn_audio,
        "has_cn_audio": has_cn_audio,
        "has_wiki_audio": has_wiki_audio,
        "has_pdf": has_pdf,
        "missing_steps": missing_steps,
        "available_dates": date_dirs,
    })


# ---------------------------------------------------------------------------
# Learning Sessions (special persistent sessions)
# ---------------------------------------------------------------------------


def _get_or_create_learning_session(session_type: str) -> dict:
    """Get or create a special persistent learning session."""
    a = _resolve_agent()
    sid = _LEARNING_SESSION_IDS.get(session_type)
    if not sid:
        return {}
    data = a._load_session_file(sid)
    if data:
        return data
    a._ensure_chat_sessions_dir()
    now = a._now_iso()
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
    a._save_session_file(data)
    return data


def _load_ai_learning_roadmap() -> str:
    """Load the AI learning roadmap (new domain/category structure)."""
    roadmap_path = os.path.normpath(
        os.path.join(_RAG_DIR, "..", "..", "docs", "ai-learning-roadmap.md")
    )
    try:
        with open(roadmap_path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        legacy = os.path.normpath(
            os.path.join(_RAG_DIR, "..", "..", "docs",
                         "learning", "rag", "ch8-learning-roadmap.md")
        )
        try:
            with open(legacy, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""


def _load_aws_cert_roadmap() -> str:
    """Load the AWS AIF-C01 certification roadmap."""
    roadmap_path = os.path.normpath(
        os.path.join(_RAG_DIR, "..", "..", "docs", "aws-cert-learning-roadmap.md")
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
    progress["last_activity"] = _resolve_agent()._now_iso()
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
                "date": _resolve_agent()._now_iso(),
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
                    for src_block in data.get("per_source_data", []):
                        for item in src_block.get("items", []):
                            t = item.get("title", "").strip()
                            if t and len(titles) < 50:
                                titles.append(t)
                    if not titles:
                        for section in data.get("sections", []):
                            for item in section.get("items", []):
                                t = item.get("title", "").strip()
                                if t and len(titles) < 50:
                                    titles.append(t)
                except Exception:
                    pass
    return titles


def _has_cjk_chars(text: str) -> bool:
    """Check if text contains CJK (Chinese/Japanese/Korean) characters."""
    return any(0x4e00 <= ord(ch) <= 0x9fff or 0x3400 <= ord(ch) <= 0x4dbf for ch in text)


def _load_recent_world_news_titles() -> list[dict]:
    """Load recent world news titles for casual English learning.
    Filters out non-English (CJK) articles since this channel focuses on English practice."""
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
                        if t and len(items) < 50 and not _has_cjk_chars(t):
                            items.append({"title": t, "category": cat_name,
                                          "summary": article.get("summary", "")[:200]})
            except Exception as exc:
                logging.warning("Failed to load world news from %s: %s", wn_path, exc)
    return items


@daily_fetch_bp.route("/api/toolbar/learning-session", methods=["POST"])
def api_learning_session():
    """Get or create a special learning session."""
    body = request.get_json(silent=True) or {}
    session_type = body.get("type", "ai_learning")
    if session_type not in _LEARNING_SESSION_IDS:
        return jsonify({"error": "Invalid learning type"}), 400
    data = _get_or_create_learning_session(session_type)
    return jsonify(data)


@daily_fetch_bp.route("/api/toolbar/learning-context", methods=["GET"])
def api_learning_context():
    """Get learning context: roadmap topics for AI, news titles for English."""
    ltype = request.args.get("type", "ai_learning")
    if ltype == "ai_learning":
        roadmap = _load_ai_learning_roadmap()
        domains = []
        current_domain = ""
        current_category = ""
        for line in roadmap.split("\n"):
            if line.startswith("## Domain"):
                current_domain = line.replace("## ", "").strip()
                current_category = ""
            elif line.startswith("### Category:"):
                current_category = line.replace("### Category:", "").strip()
            elif line.startswith("### "):
                current_category = line.replace("### ", "").strip()
            elif line.startswith("- **") and current_domain:
                topic_name = line.split("**")[1] if "**" in line else line[4:]
                topic_text = topic_name.strip(":").strip()
                desc = ""
                if ":" in line.split("**", 2)[-1]:
                    desc = line.split("**", 2)[-1].split(":", 1)[-1].strip()
                domains.append({
                    "domain": current_domain,
                    "category": current_category,
                    "topic": topic_text,
                    "description": desc,
                })
        return jsonify({"type": "ai_learning", "domains": domains})
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
        current_category = ""
        for line in roadmap.split("\n"):
            if line.startswith("## Domain") or line.startswith("## Exam Strategy"):
                current_domain = line.replace("## ", "").strip()
                current_category = ""
            elif line.startswith("### Category:"):
                current_category = line.replace("### Category:", "").strip()
            elif line.startswith("### "):
                current_category = line.replace("### ", "").strip()
            elif line.startswith("- **") and current_domain:
                topic_name = line.split("**")[1] if "**" in line else line[4:]
                topic_text = topic_name.strip(":").strip()
                desc = ""
                if ":" in line.split("**", 2)[-1]:
                    desc = line.split("**", 2)[-1].split(":", 1)[-1].strip()
                domains.append({
                    "domain": current_domain,
                    "category": current_category,
                    "topic": topic_text,
                    "description": desc,
                })
        progress = _load_aws_cert_progress()
        return jsonify({
            "type": "aws_cert",
            "domains": domains,
            "progress": progress,
        })
    return jsonify({"error": "Unknown type"}), 400
