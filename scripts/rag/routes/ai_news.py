"""AI News knowledge base API, audio-from-knowledge, report/audio file serving,
and narration + Edge-TTS helpers shared with Daily Fetch (implemented in agent.py).

Toolbar job storage lives in ``routes.toolbar``; this module does not use it.
``_web_search_references`` is resolved lazily from the loaded agent / __main__ module
to avoid circular imports when ``agent`` imports this blueprint.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import traceback
import uuid
from datetime import datetime
from typing import Any

import requests as req_mod
from flask import Blueprint, Response, jsonify, request, send_file

_ROUTES_DIR = os.path.dirname(os.path.abspath(__file__))
_RAG_PKG_DIR = os.path.dirname(_ROUTES_DIR)
_SCRIPTS_DIR = os.path.dirname(_RAG_PKG_DIR)
for _p in (_SCRIPTS_DIR, _RAG_PKG_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config import REPORTS_ROOT  # noqa: E402

from rag_engine import (  # noqa: E402
    get_qdrant as _get_qdrant,
    get_qdrant_points,
    sync_qdrant_points_from_snapshot as _sync_qdrant_points_from_snapshot,
)

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL_FAST = os.environ.get("RAG_AGENT_FAST_MODEL", "qwen3:1.7b")
OLLAMA_MODEL_NARRATION = os.environ.get("RAG_NARRATION_MODEL", "qwen3:1.7b")

ai_news_bp = Blueprint("ai_news", __name__)
_log = logging.getLogger(__name__)

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
            source_match = re.match(r"^(?:★\s*)?(.+?)\s*\(.+\)\s*$", line)
            if source_match:
                candidate = source_match.group(1).strip()
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
        "Open Source & Community", "Research & Papers", "Other",
    ]
    cat_str = ", ".join(categories_list)

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


@ai_news_bp.route("/api/toolbar/ai-news-kb", methods=["GET"])
def api_ai_news_kb_get():
    kb = _load_ai_kb()
    return jsonify({
        "items": kb["items"],
        "last_scanned": kb.get("last_scanned"),
        "total": len(kb["items"]),
    })


@ai_news_bp.route("/api/toolbar/ai-news-kb/scan", methods=["POST"])
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


def _resolved_web_search_references(query: str, num_results: int = 5) -> str:
    """Call ``agent._web_search_references`` after the app module has finished loading."""
    for name in ("__main__", "agent", "rag.agent"):
        m = sys.modules.get(name)
        if m is not None and hasattr(m, "_web_search_references"):
            return m._web_search_references(query, num_results)
    _log.warning("agent module missing _web_search_references")
    return ""


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
        for entry in get_qdrant_points():
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
            web_refs = _resolved_web_search_references(search_query + " latest news update", 5)
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

        dialogue_format = (
            "\n\n【对话格式规则——严格遵守】：\n"
            "1. 每句话必须以 [主播] 或 [嘉宾] 开头\n"
            "2. [主播] 负责引导话题、提出问题、串联过渡\n"
            "3. [嘉宾] 负责深入分析、解释技术细节、给出见解\n"
            "4. 对话自然流畅，不要堆砌比喻或口头禅\n"
            "5. 全部用中文，只有专有名词保留英文\n"
            "6. 不要用markdown格式\n"
        ) if language != "en" else (
            "\n\n[DIALOGUE FORMAT RULES — STRICT]:\n"
            "1. Every line MUST start with [Host] or [Guest]\n"
            "2. [Host] drives the conversation, asks questions, makes transitions\n"
            "3. [Guest] provides deep analysis, explains technical details\n"
            "4. Keep dialogue natural — don't force analogies or catchphrases\n"
            "5. No markdown formatting\n"
        )

        user_msg = f"""{lang_instruction} Write a LONG, comprehensive educational podcast DIALOGUE between two people (~10 minutes of spoken content, approximately 8000-12000 characters). Cover ALL the content below in depth. The host asks questions and guides the conversation, the guest explains and analyzes. Make it feel like a real podcast conversation — natural, insightful, and engaging. Output ONLY the dialogue text.{dialogue_format}

Knowledge base content:
{rag_block}{web_instruction}"""

        system_prompt_ka = (
            "You are writing an educational podcast dialogue between:\n"
            "- [Host]: A curious journalist who asks sharp questions and guides the conversation.\n"
            "- [Guest]: A knowledgeable expert who explains concepts clearly and provides insights.\n"
            "Write natural, engaging dialogue. Every line must start with [Host] or [Guest]. "
            "Aim for ~10 minutes of spoken content. No markdown."
        ) if language == "en" else (
            "你在写一档教育播客的双人对话脚本，两个角色：\n"
            "- [主播]：好奇心强的记者，善于提问和引导话题方向。\n"
            "- [嘉宾]：资深专家，善于把复杂内容讲清楚，有独到见解。\n"
            "对话自然流畅，不要堆砌比喻和口头禅。每句必须以[主播]或[嘉宾]开头。\n"
            "目标：约10分钟口播内容。不要markdown格式。"
        )

        resp = req_mod.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL_FAST,
                "messages": [
                    {"role": "system", "content": system_prompt_ka},
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

        import edge_tts
        import shutil
        import tempfile

        today_str = datetime.now().strftime("%Y-%m-%d")
        out_dir = os.path.join(REPORTS_ROOT, today_str)
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%H%M%S")
        out_filename = f"knowledge-audio-{ts}.mp3"
        out_path = os.path.join(out_dir, out_filename)

        async def _do_tts():
            is_en = language == "en"
            lang_key = "en" if is_en else "zh"
            ka_voices = _DIALOGUE_VOICES.get(lang_key, _DIALOGUE_VOICES["zh"])

            turns = _parse_dialogue_turns(narration)
            part_paths = []

            async def _save_ka_chunk(chunk_text, chunk_path, chunk_voice):
                fallbacks = [chunk_voice] + [v for v in _TTS_VOICE_FALLBACKS if v != chunk_voice]
                for v in fallbacks:
                    try:
                        comm = edge_tts.Communicate(chunk_text, v, rate="-5%", pitch="+0Hz")
                        await comm.save(chunk_path)
                        return
                    except Exception:
                        await asyncio.sleep(1)
                comm = edge_tts.Communicate(chunk_text, voice, rate="-5%", pitch="+0Hz")
                await comm.save(chunk_path)

            for turn_idx, (role, text) in enumerate(turns):
                turn_voice = ka_voices["host"] if role == "host" else ka_voices["guest"]
                text = _enhance_narration_rhythm(text)

                chunks = []
                remaining = text
                while remaining:
                    if len(remaining) <= 2000:
                        chunks.append(remaining)
                        break
                    split_at = remaining.rfind("。", 0, 2000)
                    if split_at < 0:
                        split_at = remaining.rfind(".", 0, 2000)
                    if split_at < 0:
                        split_at = 2000
                    else:
                        split_at += 1
                    chunks.append(remaining[:split_at])
                    remaining = remaining[split_at:].strip()

                for ci, chunk in enumerate(chunks):
                    part = os.path.join(out_dir, f"_ka_t{turn_idx}_c{ci}.mp3")
                    await _save_ka_chunk(chunk, part, turn_voice)
                    part_paths.append(part)

            if not part_paths:
                return
            if len(part_paths) == 1:
                os.replace(part_paths[0], out_path)
            else:
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
                    with open(out_path, "wb") as outf:
                        for p in part_paths:
                            with open(p, "rb") as pf:
                                outf.write(pf.read())
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


@ai_news_bp.route("/api/toolbar/audio-knowledge", methods=["POST"])
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


@ai_news_bp.route("/api/toolbar/ai-news-kb/article-audio", methods=["POST"])
def api_article_audio():
    """Generate a deep-dive audio for a single AI News KB article."""
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "Missing title"}), 400
    summary = data.get("summary", "")
    url = data.get("url", "")
    source = data.get("source", "")
    language = data.get("language", "en")
    job_id = str(uuid.uuid4())[:8]
    _audio_jobs[job_id] = {"status": "queued", "created": datetime.now().isoformat()}
    threading.Thread(
        target=_generate_article_audio,
        args=(job_id, title, summary, url, source, language),
        daemon=True,
    ).start()
    return jsonify({"job_id": job_id})


def _generate_article_audio(job_id: str, title: str, summary: str,
                            url: str, source: str, language: str):
    """Background worker: deep-dive audio for a single article.

    Generates a bilingual audio: Chinese deep-dive first, then English
    deep-dive with vocabulary explanations, concatenated into one MP3.
    """
    try:
        _audio_jobs[job_id]["status"] = "searching"

        rag_text = ""
        _get_qdrant()
        _sync_qdrant_points_from_snapshot()
        title_lower = title.lower()
        for entry in get_qdrant_points():
            pl = entry.get("payload") or {}
            pt = (pl.get("title") or "").lower()
            if title_lower in pt or pt in title_lower:
                chunk = (pl.get("text") or "").strip()
                if chunk:
                    rag_text += chunk + "\n\n"
        rag_text = rag_text[:12000]

        content_block = f"# {title}\n"
        if source:
            content_block += f"Source: {source}\n"
        if url:
            content_block += f"URL: {url}\n"
        if summary:
            content_block += f"\nSummary:\n{summary}\n"
        if rag_text:
            content_block += f"\nDetailed content from knowledge base:\n{rag_text}\n"

        _audio_jobs[job_id]["content_chars"] = len(content_block)
        _audio_jobs[job_id]["has_rag"] = bool(rag_text)

        import tempfile
        import shutil
        import subprocess as _sp

        today_str = datetime.now().strftime("%Y-%m-%d")
        out_dir = os.path.join(REPORTS_ROOT, today_str)
        os.makedirs(out_dir, exist_ok=True)
        title_hash = hashlib.md5(title.encode()).hexdigest()[:10]
        tmp_dir = tempfile.mkdtemp()
        part_files = []

        try:
            # --- Part 1: Chinese deep-dive → separate MP3 ---
            _audio_jobs[job_id]["status"] = "generating_script_zh"
            zh_system = (
                "你在写一档AI科技播客的深度解读对话，两个角色：\n"
                "- [主播]：好奇心强的科技记者，善于提问。\n"
                "- [嘉宾]：资深AI专家，讲解清晰有见解。\n"
                "每句必须以[主播]或[嘉宾]开头。不要用markdown。\n"
                "全部用中文写作，只有专有名词保留英文。\n"
                "尽可能详细地覆盖文章的所有要点。"
            )
            zh_user = (
                f"写一段关于这篇文章的深度解读播客对话（约2000-3000字）。"
                f"详细解释它是什么、为什么重要、技术细节和更广泛的影响。"
                f"覆盖文章中的所有关键信息点。"
                f"用你的知识补充摘要之外的内容。\n\n{content_block}"
            )
            narration_zh = _ollama_narration_call(zh_system, zh_user,
                                                  max_tokens=6144, timeout=420)
            if narration_zh and len(narration_zh) > 50:
                _audio_jobs[job_id]["status"] = "tts_zh"
                zh_path = os.path.join(tmp_dir, "part_0_zh.mp3")
                _tts_to_mp3(_clean_narration_for_tts(narration_zh), zh_path,
                            voice=_DIALOGUE_VOICES["zh"]["host"])
                if os.path.isfile(zh_path) and os.path.getsize(zh_path) > 0:
                    part_files.append(zh_path)
                _log.info("Article audio ZH done: %d chars → %s",
                          len(narration_zh), "OK" if part_files else "empty")

            # --- Part 2: English deep-dive with vocabulary → separate MP3 ---
            _audio_jobs[job_id]["status"] = "generating_script_en"
            en_system = (
                "You are writing a deep-dive podcast dialogue about a SINGLE tech article.\n"
                "Two speakers:\n"
                "- [Host]: Curious tech journalist, asks sharp questions.\n"
                "- [Guest]: Expert who explains clearly and provides insights.\n"
                "Every line starts with [Host] or [Guest]. No markdown.\n\n"
                "VOCABULARY TEACHING (listener is Chinese at CET-6 level):\n"
                "When using an advanced word, explain it with a dash:\n"
                "[Guest] This is a paradigm shift — a fundamental change in approach — for the industry.\n"
                "Include at least 5 such explanations spread across the dialogue.\n"
                "Cover ALL key points from the article thoroughly."
            )
            en_user = (
                f"Write a deep-dive podcast dialogue about this article "
                f"(approximately 1500-2500 words). Cover ALL key points: "
                f"what it is, why it matters, the technical details, "
                f"and broader implications. Be thorough — do not skip any "
                f"important information from the article.\n\n"
                f"{content_block}"
            )
            narration_en = _ollama_narration_call(en_system, en_user,
                                                  max_tokens=6144, timeout=420)
            if narration_en and len(narration_en) > 50:
                narration_en = _enrich_vocabulary(narration_en)
                _audio_jobs[job_id]["status"] = "tts_en"
                en_path = os.path.join(tmp_dir, "part_1_en.mp3")
                _tts_to_mp3(_clean_narration_for_tts(narration_en), en_path,
                            voice=_DIALOGUE_VOICES["en"]["host"])
                if os.path.isfile(en_path) and os.path.getsize(en_path) > 0:
                    part_files.append(en_path)
                _log.info("Article audio EN done: %d chars → %s",
                          len(narration_en), "OK" if len(part_files) > (1 if narration_zh else 0) else "empty")

            if not part_files:
                _audio_jobs[job_id]["status"] = "done"
                _audio_jobs[job_id]["error"] = "LLM/TTS produced no usable audio for either language."
                return

            # --- Concat all parts into final MP3 ---
            _audio_jobs[job_id]["status"] = "concatenating"
            out_filename = f"article-audio-{title_hash}.mp3"
            out_path = os.path.join(out_dir, out_filename)

            if len(part_files) == 1:
                shutil.copy2(part_files[0], out_path)
            else:
                concat_list = os.path.join(tmp_dir, "concat.txt")
                with open(concat_list, "w") as cl:
                    for pf in part_files:
                        cl.write(f"file '{pf}'\n")
                _sp.run(
                    ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                     "-i", concat_list, "-c", "copy", out_path],
                    capture_output=True, timeout=60,
                )

            total_chars = len(narration_zh or "") + len(narration_en or "")
            _audio_jobs[job_id]["status"] = "done"
            _audio_jobs[job_id]["output_path"] = out_path
            _audio_jobs[job_id]["output_url"] = f"/api/toolbar/audio-file/{today_str}/{out_filename}"
            _audio_jobs[job_id]["narration_preview"] = (
                _clean_narration_for_tts(narration_zh or narration_en or "")[:300]
            )
            _log.info("Article audio done: %s (%d chars, %d parts)", out_filename, total_chars, len(part_files))

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    except Exception as e:
        _audio_jobs[job_id]["status"] = "done"
        _audio_jobs[job_id]["error"] = str(e)
        _log.exception("Article audio failed for '%s'", title)


@ai_news_bp.route("/api/toolbar/ai-news-kb/article-audios", methods=["GET"])
def api_article_audios():
    """Return a map of title -> audio URL for all existing article audios."""
    audios: dict[str, str] = {}
    if os.path.isdir(REPORTS_ROOT):
        for date_dir in sorted(os.listdir(REPORTS_ROOT), reverse=True):
            date_path = os.path.join(REPORTS_ROOT, date_dir)
            if not os.path.isdir(date_path) or len(date_dir) != 10:
                continue
            for fname in os.listdir(date_path):
                if fname.startswith("article-audio-") and fname.endswith(".mp3"):
                    title_hash = fname.replace("article-audio-", "").replace(".mp3", "")
                    if title_hash not in audios:
                        audios[title_hash] = f"/api/toolbar/audio-file/{date_dir}/{fname}"
    kb = _load_ai_kb()
    title_map: dict[str, str] = {}
    for it in kb.get("items", []):
        t = it.get("title", "").strip()
        if t:
            h = hashlib.md5(t.encode()).hexdigest()[:10]
            if h in audios:
                title_map[t] = audios[h]
    return jsonify({"audios": title_map})


@ai_news_bp.route("/api/toolbar/audio-knowledge/history", methods=["GET"])
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


@ai_news_bp.route("/api/toolbar/audio-knowledge/items", methods=["GET"])
def api_audio_knowledge_items():
    """List available documents grouped by parent_title for a given item_type."""
    item_type = request.args.get("type", "")
    if not item_type:
        return jsonify({"error": "Missing 'type' parameter"}), 400

    _get_qdrant()
    _sync_qdrant_points_from_snapshot()

    groups: dict[str, dict] = {}
    for entry in get_qdrant_points():
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


@ai_news_bp.route("/api/toolbar/audio-knowledge/<job_id>", methods=["GET"])
def api_audio_knowledge_status(job_id):
    job = _audio_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@ai_news_bp.route("/api/toolbar/audio-file/<date_str>/<filename>")
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


@ai_news_bp.route("/api/toolbar/report-content/<date_str>/<filename>")
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
# Narration + TTS (Daily Fetch pipeline in agent.py)
# ---------------------------------------------------------------------------
def _ollama_narration_call(system_prompt: str, user_prompt: str, max_tokens: int = 8192, timeout: int = 600) -> str:
    """Low-level Ollama call for narration generation using the fast narration model."""
    resp = req_mod.post(
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
    """Use Ollama to generate a Chinese podcast dialogue from briefing content.

    Legacy single-call path — kept for backward compatibility when called directly.
    Daily Fetch audio now uses _generate_segmented_narrations instead.
    Outputs dual-host dialogue with [主播]/[嘉宾] markers.
    """
    dialogue_rules = (
        "\n\n【对话格式】：每句以[主播]或[嘉宾]开头。主播引导话题提问，嘉宾深入分析。"
        "对话自然流畅，不要堆砌比喻或口头禅。不要用markdown。"
    )
    if content_type == "world":
        system_prompt = (
            "你在写一档世界新闻播客的双人对话脚本。\n"
            "[主播]：资深新闻主播，引导话题、提问。\n"
            "[嘉宾]：国际时事分析师，深入解读。\n"
            "全部用中文，只有人名和专有名词保留英文。不要用markdown。"
        )
        user_prompt = (
            "写一段世界新闻播客对话（约5-8分钟口播，约4000-6000字）。"
            "涵盖以下所有新闻要点，提供背景分析和影响解读。"
            f"{dialogue_rules}\n\n{content}"
        )
    else:
        system_prompt = (
            "你在写一档AI科技播客的双人对话脚本。\n"
            "[主播]：好奇心强的科技记者，善于提问。\n"
            "[嘉宾]：资深AI专家，讲解清晰有见解。\n"
            "全部用中文，专有名词保留英文。不要用markdown。"
        )
        user_prompt = (
            "写一段AI科技播客对话（约8-12分钟口播，约6000-10000字）。"
            "深入讲解以下所有内容，解释概念、分析趋势、讨论影响。"
            f"{dialogue_rules}\n\n{content}"
        )
    return _ollama_narration_call(system_prompt, user_prompt, max_tokens=32768, timeout=1800)


def _generate_segmented_narrations(
    segments: list[dict],
    content_type: str = "ai",
    lang: str = "zh",
) -> list[str]:
    """Generate narrations per source/category segment as dual-host dialogue.

    *segments* is a list of dicts:
        {"name": "<source or category name>", "content": "<items text>"}
    *lang* is "zh" for Chinese narration or "en" for English.

    Returns a list of dialogue narration strings (one per segment, in order).
    Each line is prefixed with [主播] or [嘉宾] (or [Host]/[Guest] for English).
    The first segment gets an intro, the last gets an outro.
    """
    total = len(segments)
    narrations: list[str] = []
    use_en = lang == "en"

    _ENGLISH_LEARNING = (
        "\n\n[VOCABULARY TEACHING — MANDATORY]:\n"
        "The listener is Chinese (CET-6 level). You MUST explain 4-6 difficult English words/phrases in the dialogue.\n"
        "Use this exact pattern — say the word, then explain it with a dash:\n\n"
        "EXAMPLE (follow this pattern exactly):\n"
        '[Host] They decided to pivot — meaning to completely change direction — toward enterprise customers.\n'
        '[Guest] The ramifications — the consequences and knock-on effects — could be enormous for the whole industry.\n'
        '[Host] It really moves the needle — an idiom meaning it makes a significant difference — for smaller companies.\n'
        '[Guest] They plan to roll out — to gradually release and make available — the feature next month.\n'
        '[Host] The situation is unprecedented — meaning it has never happened before — in the history of AI.\n'
        '[Guest] They are doubling down — investing even more heavily — on their safety research.\n\n'
        "RULES:\n"
        "- Pick advanced words: idioms, phrasal verbs, formal vocabulary (NOT basic words like 'important' or 'big')\n"
        "- Spread the explanations throughout the dialogue, not at the end\n"
        "- Each explanation is short: just a few words after the dash\n"
        "- This is REQUIRED. A dialogue without vocabulary explanations is WRONG.\n"
    )

    _DIALOGUE_FORMAT_ZH = (
        "\n\n【对话格式规则——严格遵守】：\n"
        "1. 每一句话必须以 [主播] 或 [嘉宾] 开头，标明说话人\n"
        "2. 主播负责引导话题、提出问题、串联过渡\n"
        "3. 嘉宾负责深入分析、解释技术细节、给出见解\n"
        "4. 对话要自然流畅，像两个人真的在聊天\n"
        "5. 不要每句都太长，保持对话节奏感\n"
        "6. 不要生硬地加比喻或口头禅，自然表达即可\n"
        "7. 全部用中文，只有专有名词保留英文\n"
        "8. 不要用markdown格式\n"
        "9. 禁止在对话内容中提及角色身份（如\u201c我是主播\u201d\u201c今天请到嘉宾\u201d\u201c主持人\u201d\u201c分析师\u201d等），直接讨论话题内容\n"
        "10. 不要自我介绍或介绍对方，不要说\u201c欢迎来到XX节目\u201d之类的套话，直接进入话题\n"
        "\n示例格式：\n"
        "[主播] 今天我们来聊一个很有意思的话题。\n"
        "[嘉宾] 对，这个话题最近确实很火。\n"
        "[主播] 那你能给我们讲讲具体是怎么回事吗？\n"
        "[嘉宾] 简单说就是……\n"
    )

    _DIALOGUE_FORMAT_EN = (
        "\n\n[DIALOGUE FORMAT RULES — STRICT]:\n"
        "1. Every line MUST start with [Host] or [Guest] to indicate the speaker\n"
        "2. Host drives the conversation: asks questions, transitions between topics\n"
        "3. Guest provides analysis, explains technical details, shares insights\n"
        "4. Keep the dialogue natural and conversational\n"
        "5. Vary sentence lengths for good rhythm\n"
        "6. Don't force analogies or catchphrases — speak naturally\n"
        "7. No markdown formatting\n"
        "8. NEVER mention speaker roles in dialogue content (no 'I'm your host', 'our guest today', 'presenter', 'analyst', etc.) — just discuss the topic directly\n"
        "9. No self-introductions or show introductions ('welcome to the show' etc.) — jump straight into the topic\n"
        "\nExample format:\n"
        "[Host] Let's talk about something really interesting today.\n"
        "[Guest] Yeah, this has been a hot topic recently.\n"
        "[Host] Can you break it down for us?\n"
        "[Guest] Sure, basically what happened is...\n"
    )

    for idx, seg in enumerate(segments):
        is_first = idx == 0
        is_last = idx == total - 1
        seg_name = seg["name"]
        seg_content = seg["content"]
        min_chars = max(800, len(seg_content))
        max_chars = max(1500, len(seg_content) * 2)

        review_zh = ""
        review_en = ""
        if is_last and total > 1:
            prev_names = [s["name"] for s in segments[:idx]]
            review_zh = (
                f"\n在结束前，主播和嘉宾一起用几句话快速回顾今天所有板块的核心要点"
                f"（{', '.join(prev_names)}以及当前板块）。"
            )
            review_en = (
                f"\nBefore signing off, Host and Guest briefly recap key takeaways "
                f"from all segments ({', '.join(prev_names)} and this one)."
            )

        if content_type == "world":
            if use_en:
                system_prompt = (
                    "You are writing a world news podcast dialogue between two people:\n"
                    "- [Host]: A sharp news anchor who asks good questions and drives the conversation.\n"
                    "- [Guest]: An experienced analyst who provides depth, context, and clear explanations.\n"
                    "Write natural, professional dialogue. No markdown. Every line must start with [Host] or [Guest].\n\n"
                    "MANDATORY VOCABULARY TEACHING (the listener is a Chinese English learner at CET-6 level):\n"
                    "When using an advanced word, IMMEDIATELY explain it with a dash, like:\n"
                    "[Guest] The situation is unprecedented — meaning it has never happened before — in modern history.\n"
                    "[Host] The ramifications — the far-reaching consequences — are enormous.\n"
                    "You MUST include at least 4 such vocabulary explanations spread across the dialogue."
                )
                intro = "Host opens with a brief welcome and introduces today's topic. " if is_first else ""
                outro = f"Host thanks the guest and wraps up.{review_en} " if is_last else ""
                user_prompt = (
                    f"Write a podcast dialogue about '{seg_name}' "
                    f"(approximately {min_chars}-{max_chars} words). "
                    f"{intro}Cover background, impact, and implications. "
                    f"{outro}"
                    f"{_ENGLISH_LEARNING}"
                    f"{_DIALOGUE_FORMAT_EN}\n\n{seg_content}"
                )
            else:
                system_prompt = (
                    "你在写一档世界新闻播客的双人对话脚本，两个角色：\n"
                    "- [主播]：资深新闻主播，负责引导话题、提出关键问题、串联板块。\n"
                    "- [嘉宾]：国际时事分析师，负责深入解读、提供背景和洞察。\n"
                    "对话要自然专业，不要堆砌比喻和口头禅。不要用markdown。每句必须以[主播]或[嘉宾]开头。\n"
                    "重要：全部用中文写作，不要附加英文段落。只有人名和专有名词保留英文。"
                )
                intro = "主播先简短开场欢迎听众，引入今天话题。" if is_first else ""
                outro = f"主播做简短收尾，感谢嘉宾和听众。{review_zh}" if is_last else ""
                user_prompt = (
                    f"写一段关于「{seg_name}」的世界新闻播客对话"
                    f"（约{min_chars}-{max_chars}字）。"
                    f"{intro}提供背景分析和影响解读。{outro}"
                    f"{_DIALOGUE_FORMAT_ZH}\n\n"
                    f"以下是素材（请用中文重新组织讲解）：\n\n{seg_content}"
                )
        else:
            _content_depth_en = (
                "\n\nCRITICAL CONTENT RULES:\n"
                "- You MUST discuss each news item listed below by name. Cover what it is, why it matters, and its implications.\n"
                "- If only headlines are provided without detailed summaries, use your knowledge to explain the topic substantively.\n"
                "- Every news item must get meaningful discussion — do NOT skip items or replace them with generic commentary.\n"
                "- NO filler content: no generic AI philosophy, no vague predictions unrelated to the items, no padding.\n"
                "- Stay focused on the specific news items provided. Each item should get at least 2-3 exchanges.\n"
            )
            _content_depth_zh = (
                "\n\n【内容规则——最高优先级】：\n"
                "- 你必须逐条讨论下面列出的每条新闻，包括它是什么、为什么重要、有什么影响。\n"
                "- 如果素材只提供了标题没有详细摘要，请根据你的知识对该话题进行实质性讨论和解读。\n"
                "- 每条新闻都必须得到有意义的讨论——不要跳过，不要用笼统的评论代替。\n"
                "- 禁止填充内容：不要泛泛而谈AI哲学、不要说与新闻条目无关的空泛预测、不要凑字数。\n"
                "- 紧扣提供的具体新闻条目，每条至少有2-3轮对话讨论。\n"
            )

            if use_en:
                system_prompt = (
                    "You are writing an AI tech podcast dialogue between two people:\n"
                    "- [Host]: A curious tech journalist who asks sharp questions.\n"
                    "- [Guest]: An AI expert who explains things clearly and insightfully.\n"
                    "Write natural, engaging dialogue. No markdown. Every line must start with [Host] or [Guest].\n"
                    "FORBIDDEN: Never mention speaker roles in dialogue ('I'm your host', 'our guest', 'presenter', 'analyst'). No self-introductions. Jump directly into topic discussion.\n\n"
                    "MANDATORY VOCABULARY TEACHING (the listener is a Chinese English learner at CET-6 level):\n"
                    "When using an advanced word, IMMEDIATELY explain it with a dash, like:\n"
                    "[Guest] This is a paradigm shift — a fundamental change in approach — for the industry.\n"
                    "[Host] They plan to roll out — gradually release — the new features next month.\n"
                    "You MUST include at least 4 such vocabulary explanations spread across the dialogue."
                )
                intro = "Open by jumping straight into the topic (no self-introductions). " if is_first else ""
                outro = f"Wrap up the segment briefly.{review_en} " if is_last else ""
                user_prompt = (
                    f"Write a podcast dialogue about '{seg_name}' "
                    f"(approximately {min_chars}-{max_chars} words). "
                    f"{intro}Discuss each news item below in depth — explain what it is, why it matters, and its impact. "
                    f"{outro}"
                    f"{_content_depth_en}"
                    f"{_ENGLISH_LEARNING}"
                    f"{_DIALOGUE_FORMAT_EN}\n\n"
                    f"NEWS ITEMS TO DISCUSS:\n\n{seg_content}"
                )
            else:
                system_prompt = (
                    "你在写一档AI科技播客的双人对话脚本，两个角色：\n"
                    "- [主播]：好奇心强的科技记者，善于提出好问题，引导话题方向。\n"
                    "- [嘉宾]：资深AI专家，善于把复杂技术讲清楚，有独到见解。\n"
                    "对话要自然流畅，不要堆砌比喻和口头禅。不要用markdown。每句必须以[主播]或[嘉宾]开头。\n"
                    "重要：全部用中文写作，不要附加英文原文。只有专有名词保留英文。\n"
                    "禁止：不要在对话中提及\u201c主播\u201d\u201c嘉宾\u201d\u201c主持人\u201d\u201c分析师\u201d等角色身份词，不要自我介绍或介绍对方，直接讨论内容。"
                )
                intro = "用一句话引出今天要聊的话题（不要自我介绍）。" if is_first else ""
                outro = f"简短收尾总结。{review_zh}" if is_last else ""
                user_prompt = (
                    f"写一段关于「{seg_name}」的AI科技播客对话"
                    f"（约{min_chars}-{max_chars}字）。"
                    f"{intro}逐条深入讨论下面的每条新闻——解释它是什么、为什么重要、有什么影响。{outro}"
                    f"{_content_depth_zh}"
                    f"{_DIALOGUE_FORMAT_ZH}\n\n"
                    f"以下是要讨论的新闻条目（请用中文重新组织讲解）：\n\n{seg_content}"
                )

        _log.info("Generating dialogue segment %d/%d: %s (%d chars input)",
                  idx + 1, total, seg_name, len(seg_content))
        try:
            narration = _ollama_narration_call(system_prompt, user_prompt, max_tokens=4096, timeout=300)
            if narration and len(narration) > 50:
                narrations.append(narration)
                _log.info("Segment %d/%d done: %d chars dialogue", idx + 1, total, len(narration))
            else:
                _log.warning("Segment %d/%d returned too short dialogue (%d chars), skipping",
                             idx + 1, total, len(narration) if narration else 0)
        except Exception as e:
            _log.warning("Segment %d/%d failed: %s", idx + 1, total, str(e)[:200])

    return narrations


def _enrich_vocabulary(dialogue: str) -> str:
    """Post-process English dialogue to insert vocabulary explanations.

    The generation model may not consistently inline vocab teaching,
    so this second pass rewrites the dialogue with annotations added.
    """
    system = (
        "You are an editor. Rewrite the podcast dialogue below, keeping it EXACTLY the same "
        "but inserting 5-8 vocabulary explanations using em-dashes.\n\n"
        "PATTERN — insert an explanation immediately after a difficult word:\n"
        '[Guest] This is a paradigm shift — a fundamental change in approach — for the industry.\n'
        '[Host] They plan to roll out — gradually release — the new features soon.\n'
        '[Guest] The ramifications — the far-reaching consequences — could be huge.\n'
        '[Host] It is unprecedented — never happened before — in AI history.\n'
        '[Guest] They are doubling down — investing even more heavily — on safety.\n'
        '[Host] The move could galvanize — energize and motivate — the open-source community.\n\n'
        "RULES:\n"
        "- Pick words above CET-6 level: idioms, phrasal verbs, formal vocabulary\n"
        "- Each explained word must be DIFFERENT — never repeat the same word/phrase\n"
        "- Spread explanations evenly: put some at the start, middle, and end\n"
        "- Keep each explanation very short (3-8 words between dashes)\n"
        "- Do NOT change the meaning, structure, or [Host]/[Guest] tags\n"
        "- Do NOT add new dialogue turns or remove existing ones\n"
        "- Output ONLY the rewritten dialogue, nothing else"
    )
    user = f"Rewrite this dialogue by adding 5-8 vocabulary explanations (each word explained must be different):\n\n{dialogue}"
    try:
        resp = req_mod.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL_FAST,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "think": False,
                "options": {"temperature": 0.5, "num_predict": 6000},
            },
            timeout=120,
        )
        resp.raise_for_status()
        enriched = resp.json().get("message", {}).get("content", "").strip()
        enriched = re.sub(r"</?think>", "", enriched).strip()
        if enriched and len(enriched) > len(dialogue) * 0.7:
            return enriched
        _log.warning("Vocabulary enrichment returned too short (%d vs %d), using original",
                     len(enriched) if enriched else 0, len(dialogue))
    except Exception as e:
        _log.warning("Vocabulary enrichment failed: %s", str(e)[:200])
    return dialogue


_TTS_VOICE_FALLBACKS = ["zh-CN-YunxiNeural", "zh-CN-YunjianNeural", "zh-CN-XiaoxiaoNeural"]

_DIALOGUE_VOICES = {
    "zh": {"host": "zh-CN-YunxiNeural", "guest": "zh-CN-XiaoxiaoNeural"},
    "en": {"host": "en-US-AndrewNeural", "guest": "en-US-JennyNeural"},
}
_HOST_TAGS = {"[主播]", "[Host]"}
_GUEST_TAGS = {"[嘉宾]", "[Guest]"}


def _parse_dialogue_turns(text: str) -> list[tuple[str, str]]:
    """Parse dialogue text into (role, content) tuples.

    Recognizes lines starting with [主播]/[Host] or [嘉宾]/[Guest].
    If no dialogue markers are found, treats the entire text as a single host turn
    (graceful fallback for non-dialogue output from LLM).

    Returns list of ("host", text) or ("guest", text).
    """
    turns: list[tuple[str, str]] = []
    current_role = "host"
    current_lines: list[str] = []

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            if current_lines:
                current_lines.append("")
            continue

        detected_role = None
        clean_line = stripped
        for tag in _HOST_TAGS:
            if stripped.startswith(tag):
                detected_role = "host"
                clean_line = stripped[len(tag):].strip()
                break
        if detected_role is None:
            for tag in _GUEST_TAGS:
                if stripped.startswith(tag):
                    detected_role = "guest"
                    clean_line = stripped[len(tag):].strip()
                    break

        if detected_role is not None and detected_role != current_role and current_lines:
            combined = "\n".join(current_lines).strip()
            if combined:
                turns.append((current_role, combined))
            current_lines = []
            current_role = detected_role

        if detected_role is not None:
            current_role = detected_role
            if clean_line:
                current_lines.append(clean_line)
        else:
            current_lines.append(stripped)

    if current_lines:
        combined = "\n".join(current_lines).strip()
        if combined:
            turns.append((current_role, combined))

    if not turns:
        return [("host", text.strip())]

    return turns


def _clean_narration_for_tts(text: str) -> str:
    """Strip markdown formatting, sound-effect annotations, and role mentions that break TTS."""
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
    text = re.sub(r"(?:我是|这里是|欢迎来到|欢迎收听|欢迎收看)(?:主播|主持人|嘉宾|分析师|记者|专家)[^，。！？\n]*[，。！？]?", "", text)
    text = re.sub(r"(?:今天(?:我们)?(?:请到|邀请到?|有幸邀请)了?(?:我们的)?)(?:嘉宾|专家|分析师)[^，。！？\n]*[，。！？]?", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _enhance_narration_rhythm(text: str) -> str:
    """Enhance narration text with natural breathing pauses for TTS.

    Since edge-tts v7+ removed custom SSML support, we use text-level techniques:
    - Insert ellipsis-like pause markers between paragraphs (natural TTS pause)
    - Add commas before key transitional phrases to create micro-pauses
    - Ensure sentences aren't too long (TTS handles shorter sentences better)

    This produces more natural-sounding speech by giving TTS natural break points.
    """
    paragraphs = text.split("\n\n")
    enhanced = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        sentences = re.split(r"(?<=[。！？])", para)
        processed = []
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if len(sent) > 120:
                sub_parts = re.split(r"(?<=[，；、,;])", sent)
                if len(sub_parts) > 1:
                    mid = len(sub_parts) // 2
                    first_half = "".join(sub_parts[:mid])
                    second_half = "".join(sub_parts[mid:])
                    processed.append(first_half)
                    processed.append(second_half)
                else:
                    processed.append(sent)
            else:
                processed.append(sent)
        enhanced.append("".join(processed))

    return "\n\n".join(enhanced)


def _tts_segments_to_mp3(narrations: list[str], out_path: str, voice: str = "zh-CN-YunxiNeural"):
    """Convert a list of dialogue narration segments to a single combined MP3.

    Parses [主播]/[嘉宾] (or [Host]/[Guest]) markers and renders each turn
    with a different voice for natural dual-host podcast effect.
    """
    import edge_tts
    import shutil
    import tempfile

    out_dir = os.path.dirname(out_path)
    is_en = "en-" in voice
    lang_key = "en" if is_en else "zh"
    voices = _DIALOGUE_VOICES.get(lang_key, _DIALOGUE_VOICES["zh"])
    all_part_paths: list[str] = []

    async def _save_chunk(chunk_text, chunk_path, chunk_voice):
        fallbacks = [chunk_voice] + [v for v in _TTS_VOICE_FALLBACKS if v != chunk_voice]
        for v in fallbacks:
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

    def _generate_silence(duration_ms: int, silence_path: str):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return False
        try:
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi", "-i",
                 f"anullsrc=r=24000:cl=mono", "-t", f"{duration_ms / 1000:.2f}",
                 "-c:a", "libmp3lame", "-b:a", "48k", silence_path],
                check=True, capture_output=True, timeout=10,
            )
            return True
        except Exception:
            return False

    async def _do_tts():
        part_counter = 0
        for seg_idx, narration in enumerate(narrations):
            narration = _clean_narration_for_tts(narration)

            if seg_idx > 0:
                silence_part = os.path.join(out_dir, f"_df_p{part_counter}_silence.mp3")
                if _generate_silence(800, silence_part):
                    all_part_paths.append(silence_part)
                    part_counter += 1

            turns = _parse_dialogue_turns(narration)
            for turn_idx, (role, text) in enumerate(turns):
                turn_voice = voices["host"] if role == "host" else voices["guest"]
                text = _enhance_narration_rhythm(text)

                chunks: list[str] = []
                remaining = text
                while remaining:
                    if len(remaining) <= 2000:
                        chunks.append(remaining)
                        break
                    split_at = remaining.rfind("。", 0, 2000)
                    if split_at < 0:
                        split_at = remaining.rfind(".", 0, 2000)
                    if split_at < 0:
                        split_at = 2000
                    else:
                        split_at += 1
                    chunks.append(remaining[:split_at])
                    remaining = remaining[split_at:].strip()

                for ci, chunk in enumerate(chunks):
                    part = os.path.join(out_dir, f"_df_p{part_counter}.mp3")
                    await _save_chunk(chunk, part, turn_voice)
                    all_part_paths.append(part)
                    part_counter += 1

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
            with open(out_path, "wb") as outf:
                for p in all_part_paths:
                    with open(p, "rb") as pf:
                        outf.write(pf.read())

        for p in all_part_paths:
            try:
                os.remove(p)
            except OSError:
                pass
        _log.info("Dialogue TTS done (%d segments, %d parts merged, dual-voice)",
                  len(narrations), len(all_part_paths))

    asyncio.run(_do_tts())


def _tts_to_mp3(narration: str, out_path: str, voice: str = "zh-CN-YunxiNeural"):
    """Convert dialogue narration to MP3 with dual-voice rendering.

    Parses [主播]/[嘉宾] markers and uses different voices per role.
    Falls back to single-voice if no dialogue markers are found.
    """
    import edge_tts
    import shutil
    import tempfile

    narration = _clean_narration_for_tts(narration)
    is_en = "en-" in voice
    lang_key = "en" if is_en else "zh"
    voices = _DIALOGUE_VOICES.get(lang_key, _DIALOGUE_VOICES["zh"])

    out_dir = os.path.dirname(out_path)

    async def _save_chunk(chunk_text, chunk_path, chunk_voice):
        fallbacks = [chunk_voice] + [v for v in _TTS_VOICE_FALLBACKS if v != chunk_voice]
        for v in fallbacks:
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
        turns = _parse_dialogue_turns(narration)
        part_paths = []
        for turn_idx, (role, text) in enumerate(turns):
            turn_voice = voices["host"] if role == "host" else voices["guest"]
            text = _enhance_narration_rhythm(text)

            chunks: list[str] = []
            remaining = text
            while remaining:
                if len(remaining) <= 2000:
                    chunks.append(remaining)
                    break
                split_at = remaining.rfind("。", 0, 2000)
                if split_at < 0:
                    split_at = remaining.rfind(".", 0, 2000)
                if split_at < 0:
                    split_at = 2000
                else:
                    split_at += 1
                chunks.append(remaining[:split_at])
                remaining = remaining[split_at:].strip()

            for ci, chunk in enumerate(chunks):
                part = os.path.join(out_dir, f"_df_tts_t{turn_idx}_c{ci}.mp3")
                await _save_chunk(chunk, part, turn_voice)
                part_paths.append(part)

        if not part_paths:
            return
        if len(part_paths) == 1:
            os.replace(part_paths[0], out_path)
            _log.info("TTS done (1 part, dual-voice)")
            return

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
            with open(out_path, "wb") as outf:
                for p in part_paths:
                    with open(p, "rb") as pf:
                        outf.write(pf.read())
        for p in part_paths:
            try:
                os.remove(p)
            except OSError:
                pass
        _log.info("TTS done (%d parts merged, dual-voice, %d turns)", len(part_paths), len(turns))

    asyncio.run(_do_tts())
