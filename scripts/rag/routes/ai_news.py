"""AI News knowledge base API, audio-from-knowledge, report/audio file serving,
and narration + Edge-TTS helpers shared with Daily Fetch (implemented in agent.py).

Toolbar job storage lives in ``routes.toolbar``; this module does not use it.
``_web_search_references`` is resolved lazily from the loaded agent / __main__ module
to avoid circular imports when ``agent`` imports this blueprint.
"""

from __future__ import annotations

import asyncio
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


@ai_news_bp.route("/api/toolbar/ai-news-kb/summary", methods=["POST"])
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

        memory_techniques = (
            "\n\n【记忆强化写作规则——必须遵守】：\n"
            "1. 在节目开头用1-2句话预告今天要讲的几个核心话题\n"
            "2. 每个新话题先用一个日常类比或小故事引入（\"这就好比……\"）\n"
            "3. 关键概念和数字在上下文中至少出现两次，第二次用不同措辞\n"
            "4. 每讲完一个话题，用一句口语化短句收尾（\"所以记住……\"）\n"
            "5. 全篇讲完后，用3-4句话回顾串联所有话题的核心收获\n"
            "6. 多用口语停顿词（嗯、对吧、你想想看、有意思的是、说白了）\n"
            "7. 长句解释后跟一个短句总结，节奏有变化\n"
        ) if language != "en" else (
            "\n\n[MEMORY-FRIENDLY WRITING RULES — MUST FOLLOW]:\n"
            "1. Open with a 1-2 sentence preview of today's key topics\n"
            "2. Introduce each new concept with a relatable analogy or mini-story\n"
            "3. Mention key terms and numbers at least twice, rephrasing the second time\n"
            "4. After each topic, add a one-liner recap (\"So the takeaway here is...\")\n"
            "5. End with a 3-4 sentence review connecting all topics discussed\n"
            "6. Use conversational fillers (\"right?\", \"think about it\", \"here's the thing\")\n"
            "7. Alternate long explanatory sentences with short punchy summaries for rhythm\n"
        )

        user_msg = f"""{lang_instruction} Write a LONG, comprehensive educational podcast narration (~10 minutes of spoken content, approximately 8000-12000 characters). Cover ALL the content below in depth. Explain concepts using everyday analogies, provide context, discuss implications, and connect ideas across topics. Make it feel like a real educational podcast — engaging, memorable, and easy to recall after listening. Output ONLY the narration text.{memory_techniques}

Knowledge base content:
{rag_block}{web_instruction}"""

        system_prompt_ka = (
            "You are an educational podcast narrator who makes complex topics stick in listeners' minds. "
            "Your secret: you use vivid analogies, rhetorical questions, strategic repetition, and clear structure "
            "(preview → explain with story → recap) so listeners remember 80% even after one listen. "
            "Speak naturally with varied rhythm — mix short punchy lines with longer explanations. "
            "Aim for ~10 minutes of spoken content. No markdown, no formatting — pure narration text."
        ) if language == "en" else (
            "你是一位教育播客主播，擅长让复杂内容变得好记好懂。"
            "你的秘诀是：用生动的比喻、反问、战略性重复、和清晰结构（预告→故事引入→讲解→一句话收）"
            "让听众听一遍就能记住80%的内容。"
            "语气自然，节奏有变化——长句解释后用短句收，偶尔加口语停顿词。"
            "目标：约10分钟口播内容。不要markdown格式，只输出纯文本旁白。"
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
            enhanced_narration = _enhance_narration_rhythm(narration)
            chunks = []
            chunk_size = 2000
            text = enhanced_narration
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

            async def _save_ka_chunk(chunk_text, chunk_path):
                comm = edge_tts.Communicate(chunk_text, voice, rate="-5%", pitch="+0Hz")
                await comm.save(chunk_path)

            if len(chunks) == 1:
                await _save_ka_chunk(chunks[0], out_path)
            else:
                part_paths = []
                for i, chunk in enumerate(chunks):
                    part = os.path.join(out_dir, f"_ka_part_{i}.mp3")
                    await _save_ka_chunk(chunk, part)
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
    """Use Ollama to generate a Chinese podcast narration from briefing content.

    Legacy single-call path — kept for backward compatibility when called directly.
    Daily Fetch audio now uses _generate_segmented_narrations instead.
    """
    memory_rules = (
        "\n\n【记忆强化规则】：开头预告要点，每个话题用类比引入，关键词重复两次，"
        "每段结尾一句话总结，最后回顾串联。多用口语词（嗯、对吧、说白了）。"
    )
    if content_type == "world":
        system_prompt = (
            "你是一位专业的国际新闻播报员，善于让新闻变得好记。"
            "用流畅自然的中文播报，善用比喻和反问让听众留下印象。"
            "语气正式但不生硬，节奏有变化。不要用markdown格式，只输出纯文本旁白。"
        )
        user_prompt = (
            "用中文写一段世界新闻播客旁白（约5-8分钟口播内容，约4000-6000字）。"
            "涵盖以下所有新闻要点，提供背景分析和影响解读。技术术语和人名保留英文。"
            f"只输出旁白文本。{memory_rules}\n\n"
            f"{content}"
        )
    else:
        system_prompt = (
            "你是一位AI科技播客主播，擅长把复杂技术讲得好记好懂。"
            "风格像跟朋友聊天——轻松有干货，善用比喻和故事。"
            "不要用markdown格式，只输出纯文本旁白。"
        )
        user_prompt = (
            "用中文写一段AI科技播客旁白（约8-12分钟口播内容，约6000-10000字）。"
            "深入讲解以下所有内容，每个概念先用日常比喻引入再展开。"
            f"技术术语保留英文。只输出旁白文本。{memory_rules}\n\n"
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
    Narrations use memory-friendly techniques: preview, analogy, repetition, review.
    """
    total = len(segments)
    narrations: list[str] = []
    use_en = lang == "en"

    _MEMORY_TECHNIQUES_ZH = (
        "\n\n【记忆强化写作技巧——必须使用】：\n"
        "1. 每个板块开头用一句话预告本段核心要点（\"这一段我们聊三件事……\"）\n"
        "2. 对抽象概念必须用日常比喻或小故事开场（比如：\"这就好比你去超市……\"）\n"
        "3. 关键数据或名词在段内至少重复两次，第二次换一种说法\n"
        "4. 段落结尾用一句话口语化复述核心收获（\"所以简单来说……\"）\n"
        "5. 多用口语化停顿词和语气词（嗯、对吧、你想想看、说白了、有意思的是）\n"
        "6. 语句长短交错——长句解释后跟一个短句总结\n"
    )

    _MEMORY_TECHNIQUES_EN = (
        "\n\n[MEMORY-FRIENDLY WRITING TECHNIQUES — MUST USE]:\n"
        "1. Preview: Start each section with a one-sentence roadmap (\"Three things to cover here...\")\n"
        "2. Analogy: For every abstract concept, open with a relatable comparison or mini-story\n"
        "3. Repetition: Mention key numbers/terms at least twice, rephrasing the second time\n"
        "4. Recap: End each section with a plain-language one-liner (\"So the takeaway is...\")\n"
        "5. Conversational fillers: Use natural pauses (\"right?\", \"think about it\", \"here's the thing\")\n"
        "6. Rhythm: Alternate long explanatory sentences with short punchy summaries\n"
    )

    for idx, seg in enumerate(segments):
        is_first = idx == 0
        is_last = idx == total - 1
        seg_name = seg["name"]
        seg_content = seg["content"]
        min_chars = max(400, len(seg_content) // 3)
        max_chars = max(800, len(seg_content) // 2)

        review_instruction_zh = ""
        review_instruction_en = ""
        if is_last and total > 1:
            prev_names = [s["name"] for s in segments[:idx]]
            review_instruction_zh = (
                f"\n在结束前，用2-3句话快速回顾今天所有板块的核心要点"
                f"（{', '.join(prev_names)}以及当前板块），帮助听众串联记忆。"
            )
            review_instruction_en = (
                f"\nBefore signing off, spend 2-3 sentences recapping the key takeaways "
                f"from all segments ({', '.join(prev_names)} and this one) to reinforce memory."
            )

        if content_type == "world":
            if use_en:
                system_prompt = (
                    "You are a professional international news anchor who makes complex stories memorable. "
                    "Write in fluent, natural conversational English for a podcast. "
                    "Use analogies, mini-stories, and rhetorical questions to help listeners remember key facts. "
                    "Vary your pacing — mix short impactful statements with longer explanations. "
                    "No markdown, plain text only."
                )
                intro_line = "Start with a brief, curiosity-sparking opening question or surprising fact for this world news podcast. " if is_first else ""
                outro_line = f"End with a brief sign-off thanking listeners.{review_instruction_en} " if is_last else ""
                user_prompt = (
                    f"Write an English podcast narration about the '{seg_name}' section "
                    f"(approximately {min_chars}-{max_chars} words). "
                    f"{intro_line}Provide background analysis and impact interpretation. "
                    f"{outro_line}Output narration text only."
                    f"{_MEMORY_TECHNIQUES_EN}\n\n{seg_content}"
                )
            else:
                system_prompt = (
                    "你是一位专业的国际新闻播报员，善于让复杂新闻变得好记、好理解。"
                    "语气正式但不生硬，像在跟一个朋友讲今天世界上发生了什么。"
                    "善用比喻、反问、小故事让听众留下印象。语句节奏有变化，长短交错。"
                    "不要用markdown格式，只输出纯文本旁白。"
                    "重要规则：全部用中文写作，不要翻译或复述原文英文内容，不要附加英文段落。"
                    "只有人名和专有名词保留英文。"
                )
                intro_line = "以一个引发好奇心的问题或惊人事实开头，然后进入以下板块内容。" if is_first else ""
                outro_line = f"在板块结束后加上简短的结束语，感谢收听。{review_instruction_zh}" if is_last else ""
                user_prompt = (
                    f"用中文写一段关于「{seg_name}」板块的世界新闻播客旁白"
                    f"（约{min_chars}-{max_chars}字）。"
                    f"{intro_line}"
                    "提供背景分析和影响解读。只有人名和专有名词保留英文，其余全部用中文表达。"
                    f"{outro_line}"
                    "只输出中文旁白文本。"
                    f"{_MEMORY_TECHNIQUES_ZH}\n\n"
                    f"以下是素材（请用中文重新组织讲解，不要直接翻译或附加原文）：\n\n"
                    f"{seg_content}"
                )
        else:
            if use_en:
                system_prompt = (
                    "You are an AI technology podcast host who makes technical content stick in listeners' minds. "
                    "Write in engaging, conversational English — like explaining cool tech to a smart friend over coffee. "
                    "Use vivid analogies (\"think of it like...\"), rhetorical questions, and mini-stories. "
                    "Vary sentence rhythm. No markdown, plain text only."
                )
                intro_line = "Start with a thought-provoking question or surprising stat to hook the listener. " if is_first else ""
                outro_line = f"End with a brief sign-off.{review_instruction_en} " if is_last else ""
                user_prompt = (
                    f"Write an English podcast narration about the '{seg_name}' section "
                    f"(approximately {min_chars}-{max_chars} words). "
                    f"{intro_line}Explain concepts, analyze trends, discuss impact. "
                    f"{outro_line}Output narration text only."
                    f"{_MEMORY_TECHNIQUES_EN}\n\n{seg_content}"
                )
            else:
                system_prompt = (
                    "你是一位AI科技播客主播，擅长把复杂技术讲得有趣、好记。"
                    "风格像跟一个聪明的朋友喝咖啡聊天——轻松但有干货。"
                    "善用日常比喻（\"就好比……\"）、反问（\"你有没有想过……\"）、小故事让人印象深刻。"
                    "语句节奏有变化，长句解释后用短句收。"
                    "不要用markdown格式，只输出纯文本旁白。"
                    "重要规则：全部用中文写作，不要翻译或复述原文英文内容，不要附加英文段落。"
                    "只有专有名词（如公司名、模型名、技术名词）保留英文。"
                )
                intro_line = "以一个引发好奇的问题或有趣的比喻开头，然后进入本段内容。" if is_first else ""
                outro_line = f"在板块结束后加上简短的结束语，感谢收听。{review_instruction_zh}" if is_last else ""
                user_prompt = (
                    f"用中文写一段关于「{seg_name}」板块的AI科技播客旁白"
                    f"（约{min_chars}-{max_chars}字）。"
                    f"{intro_line}"
                    "深入讲解内容，解释概念、分析趋势、讨论影响。"
                    "只有专有名词保留英文，其余全部用中文表达，不要重复或附加英文原文。"
                    f"{outro_line}"
                    "只输出中文旁白文本。"
                    f"{_MEMORY_TECHNIQUES_ZH}\n\n"
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
    """Convert a list of narration segments to a single combined MP3.

    Uses rhythm-enhanced text processing and inter-segment silence for natural pacing.
    """
    import edge_tts
    import shutil
    import tempfile

    out_dir = os.path.dirname(out_path)
    voices_to_try = [voice] + [v for v in _TTS_VOICE_FALLBACKS if v != voice]
    all_part_paths: list[str] = []

    async def _save_chunk(chunk_text, chunk_path, rate="-5%", pitch="+0Hz"):
        for v in voices_to_try:
            for attempt in range(2):
                try:
                    comm = edge_tts.Communicate(chunk_text, v, rate=rate, pitch=pitch)
                    await comm.save(chunk_path)
                    return v
                except Exception:
                    if attempt < 1:
                        await asyncio.sleep(2)
            _log.warning("Voice %s failed for chunk, trying next fallback", v)
        raise RuntimeError(f"All TTS voices failed for chunk ({len(chunk_text)} chars)")

    def _generate_silence(duration_ms: int, silence_path: str):
        """Generate a short silence MP3 using ffmpeg for natural inter-segment pauses."""
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
        chunk_size = 2000
        for seg_idx, narration in enumerate(narrations):
            narration = _clean_narration_for_tts(narration)
            narration = _enhance_narration_rhythm(narration)

            if seg_idx > 0:
                silence_part = os.path.join(out_dir, f"_df_seg{seg_idx}_silence.mp3")
                if _generate_silence(800, silence_part):
                    all_part_paths.append(silence_part)

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
            with open(out_path, "wb") as outf:
                for p in all_part_paths:
                    with open(p, "rb") as pf:
                        outf.write(pf.read())

        for p in all_part_paths:
            try:
                os.remove(p)
            except OSError:
                pass
        _log.info("Segmented TTS done (%d segments, %d chunks merged, rhythm-enhanced)",
                  len(narrations), len(all_part_paths))

    asyncio.run(_do_tts())


def _tts_to_mp3(narration: str, out_path: str, voice: str = "zh-CN-YunxiNeural"):
    """Convert narration text to MP3 via Edge-TTS with rhythm enhancement, chunking, and voice fallback."""
    import edge_tts
    import shutil
    import tempfile

    narration = _clean_narration_for_tts(narration)
    narration = _enhance_narration_rhythm(narration)

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
            with open(out_path, "wb") as outf:
                for p in part_paths:
                    with open(p, "rb") as pf:
                        outf.write(pf.read())
        for p in part_paths:
            try:
                os.remove(p)
            except OSError:
                pass
        _log.info("TTS done (%d chunks merged, rhythm-enhanced, voice=%s)", len(chunks), used_voice)

    asyncio.run(_do_tts())
