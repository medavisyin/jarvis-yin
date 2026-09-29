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
_ROUTES_DIR = os.path.dirname(os.path.abspath(__file__))
_RAG_DIR = os.path.dirname(_ROUTES_DIR)
_SCRIPTS_DIR = os.path.dirname(_RAG_DIR)
_PIPELINE_DIR = os.path.join(_SCRIPTS_DIR, "pipeline")
for _p in (_SCRIPTS_DIR, _RAG_DIR, _PIPELINE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from web_api import Blueprint, jsonify, request

from finance_sources import (
    AUDIO_FILES,
    CATEGORIES,
    categories_with_items,
    finance_report_items,
    load_catalog,
    resolve_enabled,
)
from world_sources import (
    CATEGORIES as WORLD_CATEGORIES,
    load_catalog as load_world_catalog,
    resolve_enabled as resolve_world_enabled,
    world_history_missing_steps,
)
from briefing_translate import (
    briefing_ready_for_zh_audio,
    pick_item_text,
    translate_briefing_data,
)
from config import JIRA_REPORT_SCRIPT, KNOWLEDGE_ROOT, REPORTS_ROOT
from topic_index import TOPIC_DEDUP_TIMEOUT_SECONDS, format_filter_subprocess_error
from daily_fetch_schedule import (
    NEWS_ONLY_STEPS,
    _run_scheduled_daily_fetch as _schedule_tick,
    _start_daily_fetch_scheduler as _start_scheduler_impl,
    make_start_job,
    poll_due_job,
    scheduler_status,
)
from tools import tool_commit_summary
from routes.ai_news import (
    _generate_segmented_narrations,
    _load_ai_kb,
    _tts_segments_to_mp3,
    tts_voice_from_settings,
)

daily_fetch_bp = Blueprint("daily_fetch", __name__)
_log = logging.getLogger(__name__)

JIRA_SCRIPT = JIRA_REPORT_SCRIPT


_AGENT_MODULE_CANDIDATES = ("__main__", "agent", "rag.agent")

_AUDIO_STEP_LANG_KEYS = {
    "ai_audio": "audio_lang_ai",
    "finance_audio": "audio_lang_finance",
}

_AUDIO_MP3_NAMES = {
    "ai_audio": "ai-briefing.mp3",
    "finance_audio": "finance-markets.mp3",
    "fn_audio:markets": "finance-markets.mp3",
    "fn_audio:china-policy": "finance-china-policy.mp3",
    "fn_audio:us-political": "finance-us-political.mp3",
    "fn_audio:crypto": "finance-crypto.mp3",
    "fn_audio:gold": "finance-gold.mp3",
    "fn_audio:oil": "finance-oil.mp3",
}


def _resolve_agent_from(modules):
    """Prefer the running Flask app (__main__) over a stale ``import agent`` copy."""
    for name in _AGENT_MODULE_CANDIDATES:
        m = modules.get(name)
        if m is not None and hasattr(m, "_load_session_file"):
            return m
    return modules.get("__main__")


def _pick_global_settings(live_modules, disk_settings: dict | None = None) -> dict:
    """Live Global Settings win; disk is fallback when the app module is missing."""
    m = _resolve_agent_from(live_modules)
    gs = getattr(m, "_GLOBAL_SETTINGS", None) if m is not None else None
    if gs and isinstance(gs, dict) and any(str(k).startswith("audio_lang") for k in gs):
        return gs
    return dict(disk_settings or {})


def _resolve_agent():
    """Lazy handle to loaded agent or __main__ (session helpers, KB, Ollama globals)."""
    m = _resolve_agent_from(sys.modules)
    if m is not None:
        return m
    return sys.modules["__main__"]


def _get_global_settings() -> dict:
    """Get global settings reliably — live __main__ first, then disk."""
    settings_file = os.path.join(_RAG_DIR, ".global_settings.json")
    disk: dict = {}
    if os.path.isfile(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                disk = json.loads(f.read())
        except Exception as e:
            _log.error("Failed to read settings file %s: %s", settings_file, e)
    gs = _pick_global_settings(sys.modules, disk)
    if not gs:
        _log.warning("_GLOBAL_SETTINGS not found in-memory or on disk")
    return gs


def _write_audio_lang_sidecar(output_dir: str, step: str, lang: str) -> None:
    mp3 = _AUDIO_MP3_NAMES.get(step)
    if not mp3:
        return
    lang = (lang or "").strip().lower()
    if lang not in ("zh", "en"):
        return
    path = os.path.join(output_dir, os.path.splitext(mp3)[0] + ".lang")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(lang)
    except OSError as e:
        _log.warning("Failed to write audio lang sidecar %s: %s", path, e)
        return


def _audio_already_done(output_dir: str, step: str, expected_lang: str) -> bool:
    """True only when MP3 exists and sidecar language matches current Global."""
    mp3 = _AUDIO_MP3_NAMES.get(step)
    if not mp3:
        return False
    if not os.path.isfile(os.path.join(output_dir, mp3)):
        return False
    path = os.path.join(output_dir, os.path.splitext(mp3)[0] + ".lang")
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            recorded = f.read().strip().lower()
    except OSError:
        return False
    return recorded == (expected_lang or "").strip().lower()


def _should_skip_audio_step(only_steps, output_dir: str, step: str, expected_lang: str) -> bool:
    """Full runs skip when sidecar matches; Recreate/Continue (`only_steps`) never skip."""
    if only_steps:
        return False
    return _audio_already_done(output_dir, step, expected_lang)


def _mp3_was_replaced(path: str, before_mtime: float | None) -> bool:
    """True when TTS actually wrote a non-empty MP3 (not a no-op return)."""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) <= 0:
            return False
        if before_mtime is None:
            return True
        return os.path.getmtime(path) > before_mtime
    except OSError:
        return False


_AUDIO_EXCLUDE_SOURCES = {"Arxiv AI", "Arxiv Machine Learning"}


def _get_recent_ai_titles(reports_root: str, today_str: str, lookback_days: int = 3) -> set[str]:
    """Collect AI news titles from past N days for cross-day deduplication."""
    titles: set[str] = set()
    try:
        today_dt = datetime.strptime(today_str, "%Y-%m-%d")
    except ValueError:
        return titles
    for d in range(1, lookback_days + 1):
        past_date = (today_dt - timedelta(days=d)).strftime("%Y-%m-%d")
        for fname in ("briefing-data-filtered.json", "briefing-data.json"):
            fpath = os.path.join(reports_root, past_date, fname)
            if os.path.isfile(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for src_block in (data.get("per_source_data") or []):
                        for it in src_block.get("items", []):
                            t = (it.get("title") or "").strip().lower()
                            if t:
                                titles.add(t)
                except Exception:
                    pass
                break
    return titles


def _resolve_audio_lang(step: str, gs: dict, lang_overrides: dict | None) -> str:
    """Resolve narration language for a daily-fetch audio step."""
    if lang_overrides:
        if step in lang_overrides and lang_overrides[step] in ("zh", "en"):
            return lang_overrides[step]
        if step.startswith("fn_audio:") and lang_overrides.get("finance_audio") in ("zh", "en"):
            return lang_overrides["finance_audio"]
    if step.startswith("fn_audio:"):
        setting_key = "audio_lang_finance"
    else:
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


def _finance_news_json_path(date_dir: str) -> str | None:
    """Prefer finance-news data; fall back to legacy world-news paths."""
    pipeline = os.path.join(_SCRIPTS_DIR, "pipeline")
    if pipeline not in sys.path:
        sys.path.insert(0, pipeline)
    from finance_news_paths import finance_news_json_for_date_dir

    return finance_news_json_for_date_dir(date_dir)


def _check_finance_translated(output_dir: str) -> bool:
    fn_path = _finance_news_json_path(output_dir)
    if not fn_path:
        return False
    try:
        with open(fn_path, "r", encoding="utf-8") as f:
            return json.load(f).get("translated", False)
    except Exception:
        return False


def _world_news_json_path(date_dir: str) -> str | None:
    path = os.path.join(date_dir, "world-news", "world-news-data.json")
    return path if os.path.isfile(path) else None


def _check_world_translated(output_dir: str) -> bool:
    wn_path = _world_news_json_path(output_dir)
    if not wn_path:
        return False
    try:
        with open(wn_path, "r", encoding="utf-8") as f:
            return json.load(f).get("translated", False)
    except Exception:
        return False


def _count_world_news_items(date_dir: str) -> int:
    wn_path = _world_news_json_path(date_dir)
    if not wn_path:
        return 0
    try:
        with open(wn_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return int(data.get("total_items") or 0) or sum(
            len(c.get("items") or []) for c in (data.get("categories") or [])
        )
    except Exception:
        return 0


def _count_briefing_items(date_dir: str) -> int:
    """Count AI briefing items on disk (filtered file preferred)."""
    for fname in ("briefing-data-filtered.json", "briefing-data.json"):
        fp = os.path.join(date_dir, fname)
        if not os.path.isfile(fp):
            continue
        try:
            with open(fp, "r", encoding="utf-8") as f:
                bd = json.load(f)
            count = sum(len(src.get("items") or []) for src in (bd.get("per_source_data") or []))
            if count:
                return count
        except Exception:
            pass
    return 0


def _resolve_briefing_data_file(output_dir: str) -> str | None:
    """Pick the briefing JSON with content (prefer filtered when non-empty)."""
    for fname in ("briefing-data-filtered.json", "briefing-data.json"):
        fp = os.path.join(output_dir, fname)
        if not os.path.isfile(fp):
            continue
        try:
            with open(fp, "r", encoding="utf-8") as f:
                bd = json.load(f)
            if sum(len(src.get("items") or []) for src in (bd.get("per_source_data") or [])) > 0:
                return fp
        except Exception:
            pass
    return None


def _count_finance_news_items(date_dir: str) -> dict[str, int]:
    """Return region counts from finance-news-data.json (legacy world-news OK)."""
    counts = {"total": 0, "us": 0, "apac": 0, "china": 0, "global": 0}
    fn_file = _finance_news_json_path(date_dir)
    if not fn_file:
        return counts
    try:
        with open(fn_file, "r", encoding="utf-8") as f:
            wd = json.load(f)
        for c in wd.get("categories") or []:
            for it in c.get("items") or []:
                counts["total"] += 1
                region = (it.get("region") or "global").lower()
                if region not in counts:
                    region = "global"
                counts[region] += 1
    except Exception:
        pass
    return counts


def _index_briefing_warn(output_dir: str, steps: list, scripts_dir: str) -> None:
    """Re-index the date folder (includes finance_news). Failures are warnings only."""
    import subprocess as sp
    index_script = os.path.join(scripts_dir, "rag", "index_briefing.py")
    if not os.path.isfile(index_script):
        steps.append({"step": "finance_news_index", "exit_code": -1,
                      "output": "index_briefing.py not found"})
        return
    try:
        r = sp.run(
            [sys.executable, index_script, output_dir],
            capture_output=True, text=False, timeout=180, cwd=scripts_dir,
        )
        stdout = r.stdout.decode("utf-8", errors="replace") if r.stdout else ""
        err = r.stderr.decode("utf-8", errors="replace") if r.stderr else ""
        out = (stdout or err or "indexed")[-400:]
        if r.returncode != 0:
            steps.append({"step": "finance_news_index", "exit_code": r.returncode,
                          "output": f"Warning: indexing failed: {out}"})
        else:
            steps.append({"step": "finance_news_index", "exit_code": 0, "output": out})
    except Exception as e:
        steps.append({"step": "finance_news_index", "exit_code": 1,
                      "output": f"Warning: indexing failed: {e}"[:300]})


def _run_daily_fetch(
    job_id: str,
    *,
    only_steps: list | None = None,
    target_date: str | None = None,
    lang_overrides: dict | None = None,
    finance_sources: list | None = None,
    world_sources: list | None = None,
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
            "fetch_sources": lambda: _count_briefing_items(output_dir) > 0,
            "topic_dedup": lambda: os.path.isfile(os.path.join(output_dir, "briefing-data-filtered.json")),
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
            "finance_news_translate": lambda: _check_finance_translated(output_dir),
            "world_news_translate": lambda: _check_world_translated(output_dir),
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
            job["step"] = "Running AI + finance news fetchers..."
            try:
                run_all = os.path.join(scripts_dir, "pipeline", "run-all-sources.py")
                cmd = ["python", run_all, "--output-dir", output_dir]
                proxy_url = os.environ.get("BRIEFING_PROXY", "")
                if proxy_url:
                    cmd.extend(["--proxy", proxy_url])
                r = sp.run(
                    cmd,
                    capture_output=True, text=False, timeout=2400, cwd=scripts_dir
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
                        capture_output=True, text=False,
                        timeout=TOPIC_DEDUP_TIMEOUT_SECONDS, cwd=scripts_dir
                    )
                    stdout2 = r2.stdout.decode("utf-8", errors="replace") if r2.stdout else ""
                    stderr2 = r2.stderr.decode("utf-8", errors="replace") if r2.stderr else ""
                    out = stdout2[-300:]
                    if r2.returncode != 0:
                        out = format_filter_subprocess_error(
                            RuntimeError(f"exit {r2.returncode}"),
                            stderr2 or stdout2,
                        )
                    steps.append({"step": "topic_dedup", "exit_code": r2.returncode, "output": out})
            except Exception as e:
                err = ""
                raw_err = getattr(e, "stderr", None)
                if raw_err:
                    err = raw_err.decode("utf-8", errors="replace") if isinstance(raw_err, (bytes, bytearray)) else str(raw_err)
                steps.append({"step": "topic_dedup", "exit_code": 1,
                              "output": format_filter_subprocess_error(e, err)})

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
                from wiki_summary import attach_ai_summaries, format_wiki_report

                if all_user_pages_detail:
                    job["step"] = "Generating AI summaries for wiki pages..."
                    agent = _resolve_agent()
                    attach_ai_summaries(
                        all_user_pages_detail,
                        host=getattr(agent, "OLLAMA_HOST", None) or getattr(agent, "OLLAMA_HOST", None),
                        model=getattr(agent, "OLLAMA_MODEL_FAST", None)
                        or getattr(agent, "OLLAMA_MODEL_FAST", None),
                    )

                wiki_details_json = os.path.join(output_dir, f"wiki-details-{today}.json")
                if all_user_pages_detail:
                    with open(wiki_details_json, "w", encoding="utf-8") as wdj:
                        json.dump(all_user_pages_detail, wdj, ensure_ascii=False, indent=2)

                wiki_report_path = os.path.join(output_dir, f"wiki-fetch-{today}.md")
                with open(wiki_report_path, "w", encoding="utf-8") as wf:
                    wf.write(
                        format_wiki_report(
                            _WIKI_USERS,
                            yesterday,
                            today,
                            total_wiki_pages,
                            total_wiki_chunks,
                            wiki_results,
                            all_user_pages_detail,
                        )
                    )
                steps.append({"step": "wiki_fetch", "exit_code": 0,
                              "output": f"{total_wiki_pages} wiki pages ({total_wiki_chunks} chunks) from {len(_WIKI_USERS)} users"})
            except Exception as e:
                steps.append({"step": "wiki_fetch", "exit_code": 1, "output": str(e)[:300]})

        job["step"] = "Building daily summary..."
        ai_key_points = ""
        finance_key_points = ""
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

            fn_file = _finance_news_json_path(output_dir)
            if fn_file:
                import json as _json
                with open(fn_file, "r", encoding="utf-8") as wf:
                    wdata = _json.load(wf)
                fn_items = []
                cats = wdata.get("categories") or []
                if isinstance(cats, list):
                    for cat_block in cats:
                        cat_name = cat_block.get("label") or cat_block.get("category", "")
                        for it in (cat_block.get("items") or [])[:3]:
                            title = it.get("title_zh") or it.get("title", "")
                            region = it.get("region", "")
                            if title:
                                tag = f"{cat_name}/{region}" if region else cat_name
                                fn_items.append(f"- [{tag}] {title}")
                finance_key_points = "\n".join(fn_items[:15]) if fn_items else "No finance news items"
        except Exception:
            pass

        summary_parts = []
        summary_parts.append(f"=== Daily Fetch Summary ({today}) ===\n")

        summary_parts.append("## AI News Key Points")
        summary_parts.append(ai_key_points or "No data")
        summary_parts.append("")

        summary_parts.append("## Finance News Key Points")
        summary_parts.append(finance_key_points or "No data")
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
                        try:
                            r_dedup = sp.run(
                                ["python", filter_script, input_json, filtered_json, "--mode", "aggressive"],
                                capture_output=True, text=False,
                                timeout=TOPIC_DEDUP_TIMEOUT_SECONDS, cwd=scripts_dir
                            )
                            stdout_d = r_dedup.stdout.decode("utf-8", errors="replace") if r_dedup.stdout else ""
                            stderr_d = r_dedup.stderr.decode("utf-8", errors="replace") if r_dedup.stderr else ""
                            out_d = stdout_d[-300:]
                            if r_dedup.returncode != 0:
                                out_d = format_filter_subprocess_error(
                                    RuntimeError(f"exit {r_dedup.returncode}"),
                                    stderr_d or stdout_d,
                                )
                            steps.append({"step": "topic_dedup", "exit_code": r_dedup.returncode, "output": out_d})
                        except Exception as e:
                            err = ""
                            raw_err = getattr(e, "stderr", None)
                            if raw_err:
                                err = raw_err.decode("utf-8", errors="replace") if isinstance(raw_err, (bytes, bytearray)) else str(raw_err)
                            steps.append({"step": "topic_dedup", "exit_code": 1,
                                          "output": format_filter_subprocess_error(e, err)})
            except Exception as e:
                steps.append({"step": "refetch_ai", "exit_code": 1, "output": str(e)[:300]})

        gs = _get_global_settings()
        lang_overrides = job.get("lang_overrides") or {}

        if _should_run("ai_audio") or _should_run("ai_news_translate"):
            ai_lang = _resolve_audio_lang("ai_audio", gs, lang_overrides)
            data_file = _resolve_briefing_data_file(output_dir)
            bdata = None
            if data_file:
                try:
                    with open(data_file, "r", encoding="utf-8") as df:
                        bdata = json.load(df)
                except Exception:
                    bdata = None
            did_translate = False
            if ai_lang == "zh" and bdata is not None and not briefing_ready_for_zh_audio(bdata):
                job["step"] = "Translating AI briefing to Chinese..."
                try:
                    bdata = translate_briefing_data(bdata)
                    with open(data_file, "w", encoding="utf-8") as df:
                        json.dump(bdata, df, ensure_ascii=False, indent=2)
                    did_translate = True
                    steps.append({"step": "ai_news_translate", "exit_code": 0,
                                  "output": "AI briefing titles/summaries translated"})
                except Exception as e:
                    steps.append({"step": "ai_news_translate", "exit_code": 1, "output": str(e)[:300]})

            if not _should_run("ai_audio"):
                pass
            elif (
                _should_skip_audio_step(only_steps, output_dir, "ai_audio", ai_lang)
                and not did_translate
                and (ai_lang != "zh" or briefing_ready_for_zh_audio(bdata))
            ):
                steps.append({"step": "ai_audio", "exit_code": 0,
                              "output": f"Skipped — already completed for {today} ({ai_lang})"})
            else:
                job["step"] = f"Generating AI briefing audio ({ai_lang})..."
                try:
                    if data_file and bdata is not None:
                        prefer_zh = ai_lang == "zh"
                        recent_titles = _get_recent_ai_titles(REPORTS_ROOT, today)
                        ai_segments: list[dict] = []
                        seen_titles: set[str] = set()
                        for src_block in (bdata.get("per_source_data") or []):
                            src_name = src_block.get("source_name") or src_block.get("name") or ""
                            if src_name in _AUDIO_EXCLUDE_SOURCES:
                                continue
                            items_text_parts = []
                            for it in src_block.get("items", [])[:5]:
                                title, summary_text = pick_item_text(it, prefer_zh=prefer_zh)
                                if not title:
                                    continue
                                title_key = (it.get("title") or title).strip().lower()
                                if title_key in recent_titles or title_key in seen_titles:
                                    continue
                                seen_titles.add(title_key)
                                points = it.get("points") or []
                                parts = [title]
                                if summary_text:
                                    parts.append(summary_text)
                                elif points:
                                    parts.append(" | ".join(str(p) for p in points[:5]))
                                items_text_parts.append("\n".join(parts))
                            if items_text_parts:
                                ai_segments.append({
                                    "name": src_name or "AI News",
                                    "content": "\n\n".join(items_text_parts),
                                })
                        if ai_segments:
                            job["step"] = f"Generating AI narration ({len(ai_segments)} segments, {ai_lang})..."
                            narrations_ai = _generate_segmented_narrations(ai_segments, "ai", lang=ai_lang)
                            if narrations_ai:
                                total_chars = sum(len(n) for n in narrations_ai)
                                ai_mp3 = os.path.join(output_dir, "ai-briefing.mp3")
                                before_mtime = os.path.getmtime(ai_mp3) if os.path.isfile(ai_mp3) else None
                                _tts_segments_to_mp3(
                                    narrations_ai,
                                    ai_mp3,
                                    voice=tts_voice_from_settings(ai_lang, gs),
                                    engine=(gs or {}).get("audio_engine") or "edge",
                                    lang=ai_lang,
                                    style=(gs or {}).get("audio_mimo_style") or "平静",
                                    key=(gs or {}).get("mimo_api_key") or "",
                                )
                                if not _mp3_was_replaced(ai_mp3, before_mtime):
                                    steps.append({"step": "ai_audio", "exit_code": 1,
                                                  "output": "TTS produced no audio file"})
                                else:
                                    _write_audio_lang_sidecar(output_dir, "ai_audio", ai_lang)
                                    steps.append({"step": "ai_audio", "exit_code": 0,
                                                  "output": f"Generated ai-briefing.mp3 ({len(ai_segments)} segments, {total_chars} chars, {len(recent_titles)} titles deduped, {ai_lang})"})
                            else:
                                steps.append({"step": "ai_audio", "exit_code": 1, "output": "All narration segments failed"})
                        else:
                            steps.append({"step": "ai_audio", "exit_code": -1, "output": "Insufficient briefing content"})
                    else:
                        steps.append({"step": "ai_audio", "exit_code": -1, "output": "No briefing data file found"})
                except Exception as e:
                    steps.append({"step": "ai_audio", "exit_code": 1, "output": str(e)[:300]})

        # --- Refetch Finance News sources (for Recreate with fresh data) ---
        if only_steps and "refetch_finance" in only_steps:
            job["step"] = "Re-fetching finance news sources..."
            try:
                fn_dir = os.path.join(output_dir, "finance-news")
                os.makedirs(fn_dir, exist_ok=True)
                fn_script = os.path.join(scripts_dir, "pipeline", "run-finance-news.py")
                r_fn_cmd = ["python", fn_script, "--output-dir", fn_dir, "--no-translate",
                     "--report-date", today]
                if finance_sources:
                    r_fn_cmd.extend(["--sources", ",".join(str(s) for s in finance_sources)])
                r_fn = sp.run(
                    r_fn_cmd,
                    capture_output=True, text=False, timeout=900, cwd=scripts_dir
                )
                stdout_fn = r_fn.stdout.decode("utf-8", errors="replace") if r_fn.stdout else ""
                steps.append({"step": "refetch_finance", "exit_code": r_fn.returncode, "output": stdout_fn[-500:]})
                _index_briefing_warn(output_dir, steps, scripts_dir)
            except Exception as e:
                steps.append({"step": "refetch_finance", "exit_code": 1, "output": str(e)[:300]})

        # --- Ensure finance-news-data.json exists (merge recovery) ---
        if _should_run("finance_news_merge"):
            fn_dir = os.path.join(output_dir, "finance-news")
            fn_merged_path = os.path.join(fn_dir, "finance-news-data.json")
            if os.path.isdir(fn_dir) and not os.path.isfile(fn_merged_path):
                source_jsons = [f for f in os.listdir(fn_dir)
                                if f.endswith(".json") and f != "finance-news-timing.json"]
                if source_jsons:
                    job["step"] = "Merging finance news sources..."
                    try:
                        merge_script = os.path.join(_SCRIPTS_DIR, "pipeline", "run-finance-news.py")
                        fn_merge_cmd = [sys.executable, merge_script,
                                        "--output-dir", fn_dir, "--no-fetch", "--no-translate",
                                        "--report-date", today]
                        proc = sp.run(fn_merge_cmd, capture_output=True, text=True, timeout=120,
                                      cwd=os.path.dirname(merge_script))
                        steps.append({"step": "finance_news_merge", "exit_code": proc.returncode,
                                      "output": (proc.stdout or "")[-200:]})
                        if proc.returncode == 0:
                            _index_briefing_warn(output_dir, steps, scripts_dir)
                    except Exception as e:
                        steps.append({"step": "finance_news_merge", "exit_code": 1, "output": str(e)[:300]})
                else:
                    steps.append({"step": "finance_news_merge", "exit_code": -1,
                                  "output": "No per-source JSON files to merge"})
            elif os.path.isfile(fn_merged_path):
                steps.append({"step": "finance_news_merge", "exit_code": 0, "output": "Already merged"})
            else:
                steps.append({"step": "finance_news_merge", "exit_code": -1,
                              "output": "finance-news directory missing"})

        # --- Translate finance news to Chinese (separate step to avoid timeout) ---
        if _should_run("finance_news_translate") and not _already_done("finance_news_translate"):
            fn_dir = os.path.join(output_dir, "finance-news")
            fn_merged_path = os.path.join(fn_dir, "finance-news-data.json")
            if os.path.isfile(fn_merged_path):
                job["step"] = "Translating finance news to Chinese..."
                try:
                    with open(fn_merged_path, "r", encoding="utf-8") as f:
                        fn_data = json.load(f)
                    if not fn_data.get("translated"):
                        import importlib.util
                        _fn_spec = importlib.util.spec_from_file_location(
                            "run_finance_news",
                            os.path.join(scripts_dir, "pipeline", "run-finance-news.py"))
                        _fn_mod = importlib.util.module_from_spec(_fn_spec)
                        _fn_spec.loader.exec_module(_fn_mod)
                        fn_data = _fn_mod.translate_news_to_chinese(fn_data)
                        with open(fn_merged_path, "w", encoding="utf-8") as f:
                            json.dump(fn_data, f, ensure_ascii=False, indent=2)
                        steps.append({"step": "finance_news_translate", "exit_code": 0,
                                      "output": "Translation complete"})
                    else:
                        steps.append({"step": "finance_news_translate", "exit_code": 0,
                                      "output": "Already translated"})
                except Exception as e:
                    steps.append({"step": "finance_news_translate", "exit_code": 1,
                                  "output": str(e)[:300]})
            else:
                steps.append({"step": "finance_news_translate", "exit_code": -1,
                              "output": "No finance-news-data.json to translate"})

        if only_steps and "refetch_world" in only_steps:
            job["step"] = "Re-fetching world news sources..."
            try:
                wn_dir = os.path.join(output_dir, "world-news")
                os.makedirs(wn_dir, exist_ok=True)
                wn_script = os.path.join(scripts_dir, "pipeline", "run-world-news.py")
                r_wn_cmd = ["python", wn_script, "--output-dir", wn_dir, "--no-translate",
                            "--report-date", today]
                if world_sources:
                    r_wn_cmd.extend(["--sources", ",".join(str(s) for s in world_sources)])
                r_wn = sp.run(
                    r_wn_cmd,
                    capture_output=True, text=False, timeout=900, cwd=scripts_dir
                )
                stdout_wn = r_wn.stdout.decode("utf-8", errors="replace") if r_wn.stdout else ""
                steps.append({"step": "refetch_world", "exit_code": r_wn.returncode, "output": stdout_wn[-500:]})
            except Exception as e:
                steps.append({"step": "refetch_world", "exit_code": 1, "output": str(e)[:300]})

        if _should_run("world_news_merge"):
            wn_dir = os.path.join(output_dir, "world-news")
            wn_merged_path = os.path.join(wn_dir, "world-news-data.json")
            os.makedirs(wn_dir, exist_ok=True)
            if not os.path.isfile(wn_merged_path):
                job["step"] = "Fetching and merging world news..."
                try:
                    wn_script = os.path.join(scripts_dir, "pipeline", "run-world-news.py")
                    wn_cmd = [sys.executable, wn_script, "--output-dir", wn_dir,
                              "--no-translate", "--report-date", today]
                    if world_sources:
                        wn_cmd.extend(["--sources", ",".join(str(s) for s in world_sources)])
                    proc = sp.run(wn_cmd, capture_output=True, text=True, timeout=900,
                                  cwd=os.path.dirname(wn_script))
                    steps.append({"step": "world_news_merge", "exit_code": proc.returncode,
                                  "output": (proc.stdout or proc.stderr or "")[-300:]})
                except Exception as e:
                    steps.append({"step": "world_news_merge", "exit_code": 1, "output": str(e)[:300]})
            else:
                steps.append({"step": "world_news_merge", "exit_code": 0, "output": "Already merged"})

        if _should_run("world_news_translate") and not _already_done("world_news_translate"):
            wn_merged_path = os.path.join(output_dir, "world-news", "world-news-data.json")
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

        # --- Audio generation: single Finance News briefing ---
        def _pick_fn_text(it, prefer_zh):
            if prefer_zh:
                title = it.get("title_zh") or it.get("title", "")
                summary_text = it.get("summary_zh") or it.get("summary", "") or it.get("description", "")
            else:
                title = it.get("title", "")
                summary_text = it.get("summary", "") or it.get("description", "")
            return title, summary_text

        def _build_finance_audio_segments(categories, prefer_zh, items_per_segment=10):
            """Build narration segments from all finance items (chunked for LLM context)."""
            segs = []
            if not isinstance(categories, list):
                return segs
            for cat_block in categories:
                cat_name = cat_block.get("label") or cat_block.get("category", "") or "Finance"
                parts = []
                chunk_idx = 1
                for it in (cat_block.get("items") or []):
                    title, summary_text = _pick_fn_text(it, prefer_zh)
                    if not title:
                        continue
                    region = it.get("region") or ""
                    prefix = f"[{region}] " if region else ""
                    parts.append(f"{prefix}{title}\n{summary_text}")
                    if len(parts) >= items_per_segment:
                        label = cat_name if chunk_idx == 1 else f"{cat_name} ({chunk_idx})"
                        segs.append({"name": label, "content": "\n\n".join(parts)})
                        parts = []
                        chunk_idx += 1
                if parts:
                    label = cat_name if chunk_idx == 1 else f"{cat_name} ({chunk_idx})"
                    segs.append({"name": label, "content": "\n\n".join(parts)})
            return segs

        def _fn_audio_cats_requested():
            if not only_steps or "finance_audio" in only_steps:
                return list(AUDIO_FILES.keys())
            cats = []
            for s in only_steps or []:
                if isinstance(s, str) and s.startswith("fn_audio:"):
                    cats.append(s.split(":", 1)[1])
            return cats

        fn_cats = _fn_audio_cats_requested()
        if fn_cats:
            fn_lang = _resolve_audio_lang("finance_audio", gs, lang_overrides)
            try:
                fn_file = os.path.join(output_dir, "finance-news", "finance-news-data.json")
                if not os.path.exists(fn_file):
                    fn_file = _finance_news_json_path(output_dir) or ""
                if fn_file and os.path.exists(fn_file):
                    import json as _json
                    with open(fn_file, "r", encoding="utf-8") as wf:
                        fdata = _json.load(wf)
                    cat_blocks = {
                        (c.get("category") or ""): c
                        for c in (fdata.get("categories") or [])
                    }
                    prefer_zh = fn_lang == "zh"
                    generated = 0
                    for cat_id in fn_cats:
                        step_name = f"fn_audio:{cat_id}"
                        mp3_name = AUDIO_FILES.get(cat_id)
                        if not mp3_name:
                            continue
                        if _should_skip_audio_step(only_steps, output_dir, step_name, fn_lang):
                            steps.append({"step": step_name, "exit_code": 0,
                                          "output": f"Skipped — already completed for {today} ({fn_lang})"})
                            continue
                        block = cat_blocks.get(cat_id)
                        items = (block or {}).get("items") or []
                        if not items:
                            steps.append({"step": step_name, "exit_code": 0,
                                          "output": f"No items for {cat_id}; skipped audio"})
                            continue
                        job["step"] = f"Generating {cat_id} finance audio ({fn_lang})..."
                        segs = _build_finance_audio_segments([block], prefer_zh=prefer_zh)
                        if not segs:
                            steps.append({"step": step_name, "exit_code": -1,
                                          "output": f"No narration content for {cat_id}"})
                            continue
                        narrations_fn = _generate_segmented_narrations(segs, "finance", lang=fn_lang)
                        if not narrations_fn:
                            steps.append({"step": step_name, "exit_code": 1,
                                          "output": f"Finance narration failed ({cat_id})"})
                            continue
                        fn_mp3 = os.path.join(output_dir, mp3_name)
                        before_mtime = os.path.getmtime(fn_mp3) if os.path.isfile(fn_mp3) else None
                        _tts_segments_to_mp3(
                            narrations_fn,
                            fn_mp3,
                            voice=tts_voice_from_settings(fn_lang, gs),
                            engine=(gs or {}).get("audio_engine") or "edge",
                            lang=fn_lang,
                            style=(gs or {}).get("audio_mimo_style") or "平静",
                            key=(gs or {}).get("mimo_api_key") or "",
                        )
                        if not _mp3_was_replaced(fn_mp3, before_mtime):
                            steps.append({"step": step_name, "exit_code": 1,
                                          "output": f"TTS produced no audio file ({mp3_name})"})
                            continue
                        _write_audio_lang_sidecar(output_dir, step_name, fn_lang)
                        generated += 1
                        steps.append({"step": step_name, "exit_code": 0,
                                      "output": f"Generated {mp3_name} ({len(narrations_fn)} segments, {fn_lang})"})
                    if generated == 0 and not any(s["step"].startswith("fn_audio:") for s in steps):
                        steps.append({"step": "finance_audio", "exit_code": -1,
                                      "output": "No finance news content"})
                else:
                    steps.append({"step": "finance_audio", "exit_code": -1,
                                  "output": "No finance news data file found"})
            except Exception as e:
                steps.append({"step": "finance_audio", "exit_code": 1, "output": str(e)[:300]})

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


def _run_scheduled_daily_fetch():
    """Cron entry: skip if busy/done, else start NEWS_ONLY_STEPS via existing worker."""
    start_job = make_start_job(_daily_fetch_jobs, _run_daily_fetch)
    return _schedule_tick(
        _daily_fetch_jobs,
        reports_root=REPORTS_ROOT,
        start_job=start_job,
    )


def _start_daily_fetch_scheduler():
    """Bind the in-process sleep-loop job to this module's worker and start it."""
    return _start_scheduler_impl(job_func=_run_scheduled_daily_fetch)


@daily_fetch_bp.route("/api/toolbar/daily-fetch/scheduler", methods=["GET"])
def api_daily_fetch_scheduler():
    """Scheduler running flag, next fire, last tick, log path."""
    poll_due_job()
    return jsonify(scheduler_status())


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
    finance_sources = data.get("finance_sources") or []
    world_sources = data.get("world_sources") or []
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
            "finance_sources": finance_sources or None,
            "world_sources": world_sources or None,
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
    finance_by_source: dict[str, int] = {}
    finance_by_category: dict[str, int] = {}
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

    fn_counts = _count_finance_news_items(date_dir)
    fn_file = _finance_news_json_path(date_dir)
    if fn_file:
        try:
            with open(fn_file, "r", encoding="utf-8") as f:
                wd = json.load(f)
            for c in wd.get("categories") or []:
                cid = c.get("category") or ""
                n = len(c.get("items") or [])
                if cid:
                    finance_by_category[cid] = finance_by_category.get(cid, 0) + n
                for it in c.get("items") or []:
                    src_label = it.get("source") or "Finance"
                    finance_by_source[src_label] = finance_by_source.get(src_label, 0) + 1
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
    finance_audio_files = {
        cid: os.path.isfile(os.path.join(date_dir, fname))
        for cid, fname in AUDIO_FILES.items()
    }
    has_finance_audio = any(finance_audio_files.values())
    has_pdf = os.path.isfile(os.path.join(date_dir, "ai-briefing.pdf"))

    has_sources = os.path.isfile(os.path.join(date_dir, "briefing-data.json"))
    has_filtered = os.path.isfile(os.path.join(date_dir, "briefing-data-filtered.json"))
    has_commit = any(f.startswith("commit-report-") and f.endswith(".md") for f in os.listdir(date_dir)) if os.path.isdir(date_dir) else False
    has_jira = os.path.isfile(jira_file)
    has_wiki = any(f.startswith("wiki-fetch-") and f.endswith(".md") for f in os.listdir(date_dir)) if os.path.isdir(date_dir) else False
    has_fn_data = bool(fn_file)

    fn_dir = os.path.join(date_dir, "finance-news")
    has_fn_source_jsons = False
    if os.path.isdir(fn_dir) and not has_fn_data:
        has_fn_source_jsons = any(
            f.endswith(".json") and f != "finance-news-timing.json" and f != "finance-news-data.json"
            for f in os.listdir(fn_dir)
        )

    has_filtered_items = False
    filtered_file = os.path.join(date_dir, "briefing-data-filtered.json")
    if os.path.isfile(filtered_file):
        try:
            with open(filtered_file, "r", encoding="utf-8") as _ff:
                _fd = json.load(_ff)
            has_filtered_items = sum(
                len(src.get("items") or []) for src in (_fd.get("per_source_data") or [])
            ) > 0
        except Exception:
            pass

    has_briefing_items = ai_count > 0 or _count_briefing_items(date_dir) > 0
    has_fn_items = fn_counts.get("total", 0) > 0

    gs = _get_global_settings()
    missing_steps = []
    if not has_sources or not has_briefing_items:
        missing_steps.append("fetch_sources")
    if has_briefing_items and not has_filtered_items:
        missing_steps.append("topic_dedup")
    if not has_commit:
        missing_steps.append("commit_report")
    if not has_jira:
        missing_steps.append("jira_daily")
    if not has_wiki:
        missing_steps.append("wiki_fetch")
    if has_fn_source_jsons and not has_fn_data:
        missing_steps.append("finance_news_merge")
    if not has_fn_items and (has_fn_data or has_fn_source_jsons):
        missing_steps.append("refetch_finance")
    # Translate step only opens finance-news/finance-news-data.json — do not
    # demand it for legacy-only world-news days.
    finance_canonical = os.path.join(date_dir, "finance-news", "finance-news-data.json")
    if has_fn_items and os.path.isfile(finance_canonical):
        try:
            with open(finance_canonical, "r", encoding="utf-8") as _wf:
                _fn_check = json.load(_wf)
            if not _fn_check.get("translated"):
                missing_steps.append("finance_news_translate")
        except Exception:
            pass
    missing_steps.extend(world_history_missing_steps(date_dir, target_date))
    if has_briefing_items:
        _ai_lang = _resolve_audio_lang("ai_audio", gs, None)
        _ai_done = _audio_already_done(date_dir, "ai_audio", _ai_lang)
        if _ai_lang == "zh":
            _bfile = _resolve_briefing_data_file(date_dir)
            _bdata = None
            if _bfile:
                try:
                    with open(_bfile, "r", encoding="utf-8") as _bf:
                        _bdata = json.load(_bf)
                except Exception:
                    _bdata = None
            if not briefing_ready_for_zh_audio(_bdata):
                _ai_done = False
                missing_steps.append("ai_news_translate")
        if not _ai_done:
            missing_steps.append("ai_audio")
    if has_fn_data or has_fn_source_jsons:
        fn_lang = _resolve_audio_lang("finance_audio", gs, None)
        present_cats = set(AUDIO_FILES)
        if fn_file:
            try:
                with open(fn_file, "r", encoding="utf-8") as _mf:
                    present_cats = set(categories_with_items(json.load(_mf)))
            except Exception:
                present_cats = set(AUDIO_FILES)
        missing_fn = [
            f"fn_audio:{cid}"
            for cid in AUDIO_FILES
            if cid in present_cats and not _audio_already_done(date_dir, f"fn_audio:{cid}", fn_lang)
        ]
        if missing_fn:
            missing_steps.append("finance_audio")
            missing_steps.extend(missing_fn)
    date_dirs = sorted(
        [d for d in os.listdir(REPORTS_ROOT)
         if os.path.isdir(os.path.join(REPORTS_ROOT, d)) and d[:4].isdigit()],
        reverse=True,
    )[:30]

    audio_langs = {
        "audio_lang_ai": gs.get("audio_lang_ai", "zh"),
        "audio_lang_finance": gs.get("audio_lang_finance") or gs.get("audio_lang_world") or "zh",
    }

    return jsonify({
        "date": target_date,
        "files": files,
        "audio_langs": audio_langs,
        "stats": {
            "ai_items": ai_count,
            "ai_by_source": ai_by_source,
            "finance_news_items": fn_counts.get("total", 0),
            "world_news_items": _count_world_news_items(date_dir),
            "finance_by_region": {
                "us": fn_counts.get("us", 0),
                "apac": fn_counts.get("apac", 0),
                "china": fn_counts.get("china", 0),
                "global": fn_counts.get("global", 0),
            },
            "finance_by_source": finance_by_source,
            "finance_by_category": finance_by_category,
            "jira_tickets": jira_tickets,
            "confluence_pages": confluence_pages,
            "wiki_pages": wiki_pages,
        },
        "has_audio": has_audio,
        "has_finance_audio": has_finance_audio,
        "finance_audio_files": finance_audio_files,
        "finance_categories": CATEGORIES,
        "has_pdf": has_pdf,
        "missing_steps": missing_steps,
        "available_dates": date_dirs,
    })


@daily_fetch_bp.route("/api/toolbar/daily-fetch/finance-items/<date_str>", methods=["GET"])
def api_finance_day_items(date_str):
    """Per-category finance headlines + links for Daily Fetch Reports."""
    date_dir = os.path.join(REPORTS_ROOT, date_str)
    fn_file = _finance_news_json_path(date_dir)
    if not fn_file or not os.path.isfile(fn_file):
        return jsonify({"date": date_str, "categories": []})
    try:
        with open(fn_file, "r", encoding="utf-8") as f:
            merged = json.load(f)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"date": date_str, "categories": finance_report_items(merged)})


@daily_fetch_bp.route("/api/toolbar/finance-sources", methods=["GET", "POST"])
def api_finance_sources():
    """List catalog + enabled ids; POST saves finance_sources_enabled."""
    catalog = load_catalog()
    a = _resolve_agent()
    gs = getattr(a, "_GLOBAL_SETTINGS", None)
    if not isinstance(gs, dict):
        gs = _get_global_settings()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        enabled_map = data.get("enabled") or {}
        if not isinstance(enabled_map, dict):
            return jsonify({"error": "enabled must be an object"}), 400
        gs["finance_sources_enabled"] = {
            str(k): bool(v) for k, v in enabled_map.items()
        }
        if hasattr(a, "_save_settings"):
            a._save_settings(gs)
        elif hasattr(a, "_GLOBAL_SETTINGS"):
            a._GLOBAL_SETTINGS = gs
        return jsonify({"ok": True, "enabled": resolve_enabled(catalog, settings=gs)})
    return jsonify({
        "categories": CATEGORIES,
        "sources": catalog,
        "enabled": resolve_enabled(catalog, settings=gs),
    })


@daily_fetch_bp.route("/api/toolbar/world-sources", methods=["GET", "POST"])
def api_world_sources():
    """List geopolitics catalog + enabled ids; POST saves world_sources_enabled."""
    catalog = load_world_catalog()
    a = _resolve_agent()
    gs = getattr(a, "_GLOBAL_SETTINGS", None)
    if not isinstance(gs, dict):
        gs = _get_global_settings()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        enabled_map = data.get("enabled") or {}
        if not isinstance(enabled_map, dict):
            return jsonify({"error": "enabled must be an object"}), 400
        gs["world_sources_enabled"] = {
            str(k): bool(v) for k, v in enabled_map.items()
        }
        if hasattr(a, "_save_settings"):
            a._save_settings(gs)
        elif hasattr(a, "_GLOBAL_SETTINGS"):
            a._GLOBAL_SETTINGS = gs
        return jsonify({"ok": True, "enabled": resolve_world_enabled(catalog, settings=gs)})
    return jsonify({
        "categories": WORLD_CATEGORIES,
        "sources": catalog,
        "enabled": resolve_world_enabled(catalog, settings=gs),
    })


@daily_fetch_bp.route("/api/toolbar/finance-news-summary", methods=["POST"])
def api_finance_news_summary():
    """Chinese summary of finance news for a date range + categories."""
    from finance_sources import load_finance_items_from_reports

    data = request.get_json(silent=True) or {}
    today = datetime.now().strftime("%Y-%m-%d")
    start = (data.get("start") or "")[:10] or today
    end = (data.get("end") or "")[:10] or today
    if end < start:
        start, end = end, start
    raw_cats = data.get("categories") or []
    if not isinstance(raw_cats, list):
        raw_cats = []
    cats = [c for c in raw_cats if isinstance(c, str) and c.strip()]
    items = load_finance_items_from_reports(
        REPORTS_ROOT, start, end, cats or None
    )
    if not items:
        return jsonify({
            "ok": True,
            "summary": "该时间范围内没有匹配的金融新闻。请先运行 Daily Fetch。",
            "items": [],
            "start": start,
            "end": end,
            "categories": cats,
        })

    lines = []
    for it in items[:80]:
        title = it.get("title_zh") or it.get("title") or ""
        src = it.get("source") or ""
        cat = it.get("category") or ""
        url = it.get("url") or ""
        lines.append(f"- [{cat}] {src}: {title}" + (f" ({url})" if url else ""))
    prompt = (
        f"用简体中文总结 {start} 至 {end} 的金融新闻"
        f"（类别: {', '.join(cats) if cats else '全部'}）。"
        "按类别分点，每条1-2句，只根据下列条目，不要编造。\n\n" + "\n".join(lines)
    )
    summary = ""
    try:
        a = _resolve_agent()
        host = getattr(a, "OLLAMA_HOST", None) or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        model = getattr(a, "OLLAMA_MODEL_FAST", None) or os.environ.get("OLLAMA_MODEL_FAST", "qwen3:1.7b")
        import requests as _req
        resp = _req.post(
            f"{host}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是金融新闻编辑。只根据给定条目写中文摘要。"},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "think": False,
                "options": {"temperature": 0.2, "num_predict": 2500},
            },
            timeout=90,
        )
        resp.raise_for_status()
        summary = (resp.json().get("message") or {}).get("content") or ""
    except Exception as e:
        summary = "摘要生成失败: " + str(e)[:200]
    item_out = [
        {
            "title": it.get("title_zh") or it.get("title"),
            "url": it.get("url") or "",
            "source": it.get("source") or "",
            "category": it.get("category") or "",
            "date": it.get("date") or it.get("report_date") or "",
        }
        for it in items[:60]
    ]
    return jsonify({
        "ok": True,
        "summary": summary.strip(),
        "items": item_out,
        "start": start,
        "end": end,
        "categories": cats,
        "count": len(items),
    })


# ---------------------------------------------------------------------------
# Learning Sessions (special persistent sessions)
# ---------------------------------------------------------------------------


def _get_or_create_learning_session(session_type: str) -> dict:
    """Get or create a special persistent learning session."""
    from learning.constants import LEARNING_SESSION_IDS as _LEARNING_SESSION_IDS

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
    """Load recent finance/world news titles for casual English learning.
    Filters out non-English (CJK) articles since this channel focuses on English practice."""
    items = []
    try:
        _pipeline = os.path.normpath(os.path.join(_SCRIPTS_DIR, "pipeline"))
        if _pipeline not in sys.path:
            sys.path.insert(0, _pipeline)
        from finance_news_paths import finance_news_data_path
    except Exception:
        finance_news_data_path = None

    for d_offset in range(7):
        dt = (datetime.now() - timedelta(days=d_offset)).strftime("%Y-%m-%d")
        wn_path = finance_news_data_path(REPORTS_ROOT, dt) if finance_news_data_path else None
        if not wn_path:
            continue
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
            logging.warning("Failed to load finance/world news from %s: %s", wn_path, exc)
    return items


@daily_fetch_bp.route("/api/toolbar/learning-session", methods=["POST"])
def api_learning_session():
    """Get or create a special learning session."""
    body = request.get_json(silent=True) or {}
    from learning.constants import LEARNING_SESSION_IDS as _LEARNING_SESSION_IDS

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
