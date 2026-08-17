"""Intensive Reading API — upload books, read chunks, analyze with Ollama."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback

from flask import Blueprint, Response, jsonify, request

_ROUTES_DIR = os.path.dirname(os.path.abspath(__file__))
_RAG_DIR = os.path.dirname(_ROUTES_DIR)
_SCRIPTS_DIR = os.path.dirname(_RAG_DIR)
for _p in (_SCRIPTS_DIR, _RAG_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config import BOOKS_ROOT, JARVIS_ROOT

from intensive_reading.analysis_cache import load_chunk_analysis, save_chunk_analysis
from intensive_reading.chunking import next_readable_index, prev_readable_index
from intensive_reading.ingest import (
    BOOK_TYPE_MAGAZINE,
    BOOK_TYPE_NOVEL,
    InvalidBookId,
    books_root,
    get_chunk,
    index_chunks_to_rag,
    is_valid_book_id,
    list_books,
    load_chunks,
    load_meta,
    load_toc,
    reindex_book,
    save_book_files,
    delete_book,
    update_meta_fields,
)
from intensive_reading.progress import load_all_progress, load_progress, save_progress
from intensive_reading.prompts import (
    PASSAGE_WINDOW,
    KIND_VOCAB,
    SPEAKING_EXERCISES,
    allowed_kinds,
    analysis_user_message,
    selection_explain_system_prompt,
    selection_explain_user_message,
    speaking_system_prompt,
    speaking_user_message,
    slice_passage,
    system_prompt_for_kind,
    tabs_payload,
)

intensive_reading_bp = Blueprint("intensive_reading", __name__)

ALLOWED_EXT = {".pdf", ".epub"}
MAX_UPLOAD_MB = 80
# Shared with Flask MAX_CONTENT_LENGTH (set in agent.py)
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def _books_dir() -> str:
    # Prefer centralized config; fall back for older configs
    root = BOOKS_ROOT if BOOKS_ROOT else books_root(JARVIS_ROOT)
    return root


def _ollama_settings() -> tuple[str, str]:
    """Return (host, model) preferring agent globals when available."""
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("RAG_AGENT_MODEL", "qwen3.5:4b")
    try:
        import agent as agent_mod

        host = getattr(agent_mod, "OLLAMA_HOST", host)
        model = getattr(agent_mod, "OLLAMA_MODEL", model)
    except Exception:
        pass
    return host, model


def _require_book_id(book_id: str):
    if not is_valid_book_id(book_id):
        return jsonify({"error": "Invalid book_id"}), 400
    return None


def _sniff_format(path: str, ext: str) -> str | None:
    """Return normalized ext if magic looks ok, else None."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return None
    if ext == ".pdf":
        return ".pdf" if head.startswith(b"%PDF") else None
    if ext == ".epub":
        # EPUB is a ZIP (PK\x03\x04) with mimetype entry
        return ".epub" if head.startswith(b"PK") else None
    return None


@intensive_reading_bp.route("/api/intensive-reading/books", methods=["GET"])
def api_list_books():
    try:
        books = list_books(_books_dir())
        progress = load_all_progress()
        for b in books:
            bid = b.get("book_id")
            if bid and bid in progress:
                b["progress"] = progress[bid]
            else:
                b["progress"] = None
        return jsonify({"books": books})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@intensive_reading_bp.route("/api/intensive-reading/upload", methods=["POST"])
def api_upload():
    try:
        if "file" not in request.files:
            return jsonify({"error": "Missing file"}), 400
        f = request.files["file"]
        if not f or not f.filename:
            return jsonify({"error": "Empty filename"}), 400
        book_type = (request.form.get("book_type") or BOOK_TYPE_NOVEL).strip().lower()
        if book_type in ("ebook", "novel/ebook", "小说", "电子书"):
            book_type = BOOK_TYPE_NOVEL
        if book_type in ("杂志", "magazine"):
            book_type = BOOK_TYPE_MAGAZINE
        if book_type not in (BOOK_TYPE_NOVEL, BOOK_TYPE_MAGAZINE):
            return jsonify({"error": "book_type must be novel or magazine"}), 400

        original = f.filename
        ext = os.path.splitext(original)[1].lower()
        if ext not in ALLOWED_EXT:
            return jsonify({"error": f"Unsupported type {ext}; use PDF or EPUB"}), 400

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            f.save(tmp.name)
            tmp_path = tmp.name

        try:
            size = os.path.getsize(tmp_path)
            if size <= 0:
                return jsonify({"error": "Empty file"}), 400
            if size > MAX_UPLOAD_BYTES:
                return jsonify({"error": f"File too large (max {MAX_UPLOAD_MB} MB)"}), 400
            if _sniff_format(tmp_path, ext) is None:
                return jsonify({"error": f"File content does not look like a valid {ext}"}), 400

            try:
                meta = save_book_files(_books_dir(), tmp_path, book_type, original)
            except ValueError as ve:
                return jsonify({"error": str(ve)}), 400
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if meta.get("status") == "ready":
            chunks = load_chunks(_books_dir(), meta["book_id"])
            indexed, rag_err = index_chunks_to_rag(
                meta["book_id"], meta.get("title") or "", book_type, chunks
            )
            if indexed > 0 and not rag_err:
                meta = update_meta_fields(
                    _books_dir(),
                    meta["book_id"],
                    {"rag_status": "ok", "rag_chunks": indexed, "rag_error": ""},
                ) or meta
            else:
                meta = update_meta_fields(
                    _books_dir(),
                    meta["book_id"],
                    {
                        "rag_status": "failed",
                        "rag_chunks": 0,
                        "rag_error": rag_err or "index returned 0 points",
                    },
                ) or meta
                meta["warning"] = "Book saved but RAG indexing failed or skipped"

        if meta.get("status") == "error":
            return jsonify({"error": meta.get("error") or "Ingest failed", "meta": meta}), 400
        if meta.get("status") == "no_readable_content":
            return jsonify({
                "ok": False,
                "error": meta.get("error") or "No readable content",
                "book": meta,
            }), 400
        return jsonify({"ok": True, "book": meta})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@intensive_reading_bp.route("/api/intensive-reading/books/<book_id>", methods=["GET"])
def api_get_book(book_id: str):
    err = _require_book_id(book_id)
    if err:
        return err
    meta = load_meta(_books_dir(), book_id)
    if not meta:
        return jsonify({"error": "Book not found"}), 404
    prog = load_progress(book_id)
    meta["progress"] = prog
    meta["toc"] = load_toc(_books_dir(), book_id)
    return jsonify(meta)


@intensive_reading_bp.route("/api/intensive-reading/books/<book_id>", methods=["DELETE"])
def api_delete_book(book_id: str):
    """Remove local book files and this book's vectors from RAG."""
    err = _require_book_id(book_id)
    if err:
        return err
    try:
        result = delete_book(_books_dir(), book_id)
    except InvalidBookId:
        return jsonify({"error": "Invalid book_id"}), 400
    except FileNotFoundError:
        return jsonify({"error": "Book not found"}), 404
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    out = {"ok": True, "book": result}
    if result.get("rag_error"):
        out["warning"] = (
            "Book deleted locally; RAG cleanup failed: " + result["rag_error"]
        )
    return jsonify(out)


@intensive_reading_bp.route("/api/intensive-reading/books/<book_id>/toc", methods=["GET"])
def api_get_toc(book_id: str):
    err = _require_book_id(book_id)
    if err:
        return err
    meta = load_meta(_books_dir(), book_id)
    if not meta:
        return jsonify({"error": "Book not found"}), 404
    toc = load_toc(_books_dir(), book_id)
    return jsonify({"book_id": book_id, "toc": toc})


@intensive_reading_bp.route(
    "/api/intensive-reading/books/<book_id>/reindex",
    methods=["POST"],
)
def api_reindex_book(book_id: str):
    """Fix title/oversized chunks if needed, then (re)index into RAG."""
    err = _require_book_id(book_id)
    if err:
        return err
    try:
        meta = reindex_book(_books_dir(), book_id)
    except InvalidBookId:
        return jsonify({"error": "Invalid book_id"}), 400
    except FileNotFoundError:
        return jsonify({"error": "Book not found"}), 404
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    ok = meta.get("rag_status") == "ok"
    out = {"ok": ok, "book": meta}
    if not ok:
        out["error"] = meta.get("rag_error") or "RAG reindex failed"
    return jsonify(out), (200 if ok else 500)


@intensive_reading_bp.route(
    "/api/intensive-reading/books/<book_id>/chunks/<int:chunk_index>",
    methods=["GET"],
)
def api_get_chunk(book_id: str, chunk_index: int):
    err = _require_book_id(book_id)
    if err:
        return err
    meta = load_meta(_books_dir(), book_id)
    if not meta:
        return jsonify({"error": "Book not found"}), 404
    if meta.get("status") == "no_readable_content":
        return jsonify({"error": "No readable chunks in this book", "done": True}), 404
    chunks = load_chunks(_books_dir(), book_id)
    if not chunks:
        return jsonify({"error": "No chunks"}), 404

    skip_toc = request.args.get("skip_toc", "1") != "0"
    idx = chunk_index
    if skip_toc:
        nxt = next_readable_index(chunks, start=idx)
        if nxt is None:
            return jsonify({"error": "No more readable chunks", "done": True}), 404
        idx = nxt

    chunk = get_chunk(_books_dir(), book_id, idx)
    if not chunk:
        return jsonify({"error": "Chunk not found"}), 404

    nxt = next_readable_index(chunks, start=idx + 1)
    prv = prev_readable_index(chunks, before=idx)
    return jsonify(
        {
            "book_id": book_id,
            "title": meta.get("title"),
            "book_type": meta.get("book_type"),
            "chunk": chunk,
            "chunk_index": idx,
            "total": len(chunks),
            "next_index": nxt,
            "prev_index": prv,
            "has_next": nxt is not None,
            "has_prev": prv is not None,
        }
    )


@intensive_reading_bp.route(
    "/api/intensive-reading/books/<book_id>/chunks/<int:chunk_index>/analysis",
    methods=["GET"],
)
def api_get_chunk_analysis(book_id: str, chunk_index: int):
    err = _require_book_id(book_id)
    if err:
        return err
    if chunk_index < 0:
        return jsonify({"error": "Invalid chunk_index"}), 400
    meta = load_meta(_books_dir(), book_id)
    if not meta:
        return jsonify({"error": "Book not found"}), 404
    try:
        doc = load_chunk_analysis(_books_dir(), book_id, chunk_index)
    except InvalidBookId:
        return jsonify({"error": "Invalid book_id"}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(doc)


@intensive_reading_bp.route(
    "/api/intensive-reading/books/<book_id>/chunks/<int:chunk_index>/analysis",
    methods=["PUT"],
)
def api_put_chunk_analysis(book_id: str, chunk_index: int):
    err = _require_book_id(book_id)
    if err:
        return err
    if chunk_index < 0:
        return jsonify({"error": "Invalid chunk_index"}), 400
    meta = load_meta(_books_dir(), book_id)
    if not meta:
        return jsonify({"error": "Book not found"}), 404
    data = request.get_json(silent=True) or {}
    tabs = data.get("tabs")
    kind = (data.get("kind") or "").strip()
    slot = data.get("slot")
    speaking = data.get("speaking") if "speaking" in data else None
    if kind == "speaking":
        return jsonify({
            "error": "speaking is not an analysis tab; send it as the speaking field",
        }), 400
    if tabs is None and kind and isinstance(slot, dict):
        tabs = {kind: slot}
    if tabs is None:
        tabs = {}
    if not isinstance(tabs, dict):
        return jsonify({"error": "tabs object (or kind+slot) required"}), 400
    if "speaking" in tabs:
        return jsonify({
            "error": "speaking is not an analysis tab; send it as the speaking field",
        }), 400
    if not tabs and speaking is None:
        return jsonify({"error": "tabs object (or kind+slot) required"}), 400
    merge = data.get("merge", True)
    try:
        doc = save_chunk_analysis(
            _books_dir(),
            book_id,
            chunk_index,
            tabs,
            merge=bool(merge),
            speaking=speaking if isinstance(speaking, dict) else None,
        )
    except InvalidBookId:
        return jsonify({"error": "Invalid book_id"}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except OSError as e:
        traceback.print_exc()
        return jsonify({"error": f"Failed to save analysis: {e}"}), 500
    return jsonify({"ok": True, "analysis": doc})


@intensive_reading_bp.route("/api/intensive-reading/progress", methods=["POST"])
def api_save_progress():
    data = request.get_json(silent=True) or {}
    book_id = (data.get("book_id") or "").strip()
    if not book_id:
        return jsonify({"error": "book_id required"}), 400
    err = _require_book_id(book_id)
    if err:
        return err
    meta = load_meta(_books_dir(), book_id)
    if not meta:
        return jsonify({"error": "Book not found"}), 404
    chunk_index = int(data.get("chunk_index", 0))
    total = int(data.get("total") or meta.get("chunk_count") or 0)
    title = meta.get("title") or book_id
    mid = save_progress(book_id, title, chunk_index, total)
    if mid is None:
        return jsonify({"ok": False, "warning": "Failed to write conversation memory"}), 200
    return jsonify({"ok": True, "memory_id": mid, "chunk_index": chunk_index})


@intensive_reading_bp.route("/api/intensive-reading/tabs", methods=["GET"])
def api_analysis_tabs():
    book_type = (request.args.get("book_type") or "novel").strip().lower()
    if book_type not in ("novel", "magazine"):
        book_type = "novel"
    return jsonify(tabs_payload(book_type))


@intensive_reading_bp.route("/api/intensive-reading/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json(silent=True) or {}
    book_id = (data.get("book_id") or "").strip()
    chunk_index = data.get("chunk_index")
    if not book_id or chunk_index is None:
        return jsonify({"error": "book_id and chunk_index required"}), 400
    err = _require_book_id(book_id)
    if err:
        return err
    meta = load_meta(_books_dir(), book_id)
    if not meta:
        return jsonify({"error": "Book not found"}), 404
    chunk = get_chunk(_books_dir(), book_id, int(chunk_index))
    if not chunk:
        return jsonify({"error": "Chunk not found"}), 404
    if chunk.get("is_toc"):
        return jsonify({"error": "Cannot analyze TOC chunk"}), 400

    book_type = (meta.get("book_type") or "novel").strip().lower()
    if book_type not in ("novel", "magazine"):
        book_type = "novel"
    analysis_kind = (data.get("analysis_kind") or KIND_VOCAB).strip().lower()
    if analysis_kind not in allowed_kinds(book_type):
        return jsonify({
            "error": f"Invalid analysis_kind {analysis_kind!r} for book_type {book_type}",
            "allowed": sorted(allowed_kinds(book_type)),
        }), 400

    full_text = chunk.get("text") or ""
    try:
        offset = max(0, int(data.get("offset") or 0))
    except (TypeError, ValueError):
        offset = 0
    if offset > len(full_text):
        return jsonify({"error": "offset past end of passage"}), 400

    excerpt, next_offset, has_more = slice_passage(full_text, offset, PASSAGE_WINDOW)
    if not excerpt.strip():
        return jsonify({"error": "No more passage text to analyze"}), 400

    try:
        part = max(1, int(data.get("part") or 1))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid part"}), 400
    previous_analysis = (data.get("previous_analysis") or "")[:8000]
    system_prompt = system_prompt_for_kind(analysis_kind)

    host, model = _ollama_settings()
    user_msg = analysis_user_message(
        meta.get("title") or book_id,
        int(chunk_index),
        excerpt,
        part=part,
        has_more=has_more,
        previous_analysis=previous_analysis,
        analysis_kind=analysis_kind,
        book_type=book_type,
    )

    def generate():
        import requests as req_mod

        full = ""
        done_reason = ""
        try:
            resp = req_mod.post(
                f"{host}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    "stream": True,
                    # qwen3.5 defaults to thinking-only tokens; without this,
                    # message.content stays empty and the UI shows no analysis.
                    "think": False,
                    "options": {"num_predict": 2048, "temperature": 0.4},
                },
                stream=True,
                timeout=300,
            )
            if resp.status_code >= 400:
                err_msg = f"Ollama error HTTP {resp.status_code}"
                yield f"data: {json.dumps({'type': 'error', 'content': err_msg})}\n\n"
                return
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk_j = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = chunk_j.get("message") or {}
                token = msg.get("content") or ""
                if not token:
                    token = msg.get("thinking") or ""
                if token:
                    full += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                if chunk_j.get("done"):
                    done_reason = (
                        chunk_j.get("done_reason")
                        or chunk_j.get("stop_reason")
                        or ""
                    )
                    break
            if not full.strip():
                yield f"data: {json.dumps({'type': 'error', 'content': 'Ollama returned empty content. Check model and try again.'})}\n\n"
                return
            # Generation may also be cut by num_predict
            gen_truncated = str(done_reason).lower() in ("length", "max_tokens", "max")
            yield f"data: {json.dumps({'type': 'done', 'content': full, 'has_more': has_more, 'next_offset': next_offset, 'part': part, 'gen_truncated': gen_truncated, 'passage_len': len(full_text), 'offset': offset, 'analysis_kind': analysis_kind})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_MAX_SELECTION_CHARS = 2000
_MAX_SELECTION_CONTEXT_CHARS = 8000


@intensive_reading_bp.route("/api/intensive-reading/explain-selection", methods=["POST"])
def api_explain_selection():
    data = request.get_json(silent=True) or {}
    selected_text = (data.get("selected_text") or "").strip()
    if not selected_text:
        return jsonify({"error": "selected_text is required"}), 400
    if len(selected_text) > _MAX_SELECTION_CHARS:
        return jsonify({"error": f"selected_text too long (max {_MAX_SELECTION_CHARS})"}), 400

    context = (data.get("context") or "").strip()
    if len(context) > _MAX_SELECTION_CONTEXT_CHARS:
        context = context[:_MAX_SELECTION_CONTEXT_CHARS]
    title = (data.get("title") or "").strip()
    book_id = (data.get("book_id") or "").strip()
    if book_id:
        err = _require_book_id(book_id)
        if err:
            return err
        meta = load_meta(_books_dir(), book_id)
        if meta and not title:
            title = (meta.get("title") or book_id).strip()

    source = (data.get("source") or "passage")
    try:
        user_msg = selection_explain_user_message(
            selected_text=selected_text,
            context=context,
            title=title,
            source=source,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    system_prompt = selection_explain_system_prompt(source)
    host, model = _ollama_settings()

    def generate():
        import requests as req_mod

        full = ""
        try:
            resp = req_mod.post(
                f"{host}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    "stream": True,
                    "think": False,
                    "options": {"num_predict": 1024, "temperature": 0.4},
                },
                stream=True,
                timeout=180,
            )
            if resp.status_code >= 400:
                err_msg = f"Ollama error HTTP {resp.status_code}"
                yield f"data: {json.dumps({'type': 'error', 'content': err_msg})}\n\n"
                return
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk_j = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = chunk_j.get("message") or {}
                token = msg.get("content") or ""
                if not token:
                    token = msg.get("thinking") or ""
                if token:
                    full += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                if chunk_j.get("done"):
                    break
            if not full.strip():
                yield f"data: {json.dumps({'type': 'error', 'content': 'Ollama returned empty content. Check model and try again.'})}\n\n"
                return
            yield f"data: {json.dumps({'type': 'done', 'content': full})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_MAX_ORAL_CHARS = 8000


@intensive_reading_bp.route("/api/intensive-reading/speaking", methods=["POST"])
def api_speaking():
    data = request.get_json(silent=True) or {}
    book_id = (data.get("book_id") or "").strip()
    chunk_index = data.get("chunk_index")
    if not book_id or chunk_index is None:
        return jsonify({"error": "book_id and chunk_index required"}), 400
    err = _require_book_id(book_id)
    if err:
        return err
    meta = load_meta(_books_dir(), book_id)
    if not meta:
        return jsonify({"error": "Book not found"}), 404
    book_type = (meta.get("book_type") or "novel").strip().lower()
    if book_type != BOOK_TYPE_MAGAZINE:
        return jsonify({"error": "Speaking practice is only available for magazine books"}), 400
    chunk = get_chunk(_books_dir(), book_id, int(chunk_index))
    if not chunk:
        return jsonify({"error": "Chunk not found"}), 404
    if chunk.get("is_toc"):
        return jsonify({"error": "Cannot run speaking practice on a TOC chunk"}), 400

    exercise = (data.get("exercise") or "").strip().lower()
    if exercise not in SPEAKING_EXERCISES:
        return jsonify({"error": f"exercise must be one of {list(SPEAKING_EXERCISES)}"}), 400

    oral_text = (data.get("oral_text") or "").strip()
    if len(oral_text) > _MAX_ORAL_CHARS:
        return jsonify({"error": f"oral_text is too long (max {_MAX_ORAL_CHARS} characters)"}), 400
    if exercise == "pressure" and not oral_text:
        return jsonify({"error": "oral_text is required for pressure practice"}), 400

    try:
        pressure_step = int(data.get("pressure_step") or 1)
    except (TypeError, ValueError):
        pressure_step = 1
    if pressure_step not in (1, 2):
        pressure_step = 1
    user_reply = (data.get("user_reply") or "").strip()
    if len(user_reply) > _MAX_ORAL_CHARS:
        return jsonify({"error": f"user_reply is too long (max {_MAX_ORAL_CHARS} characters)"}), 400
    pressure_attack = (data.get("pressure_attack") or "").strip()[:8000]
    if exercise == "pressure" and pressure_step == 2 and not user_reply:
        return jsonify({"error": "user_reply is required for pressure step 2"}), 400

    passage = (chunk.get("text") or "").strip()
    if not passage:
        return jsonify({"error": "Empty passage"}), 400
    if len(passage) > PASSAGE_WINDOW:
        passage = passage[:PASSAGE_WINDOW]

    try:
        user_msg = speaking_user_message(
            exercise=exercise,
            passage=passage,
            oral=oral_text,
            pressure_step=pressure_step,
            user_reply=user_reply,
            pressure_attack=pressure_attack,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    system_prompt = speaking_system_prompt(exercise)
    host, model = _ollama_settings()

    def generate():
        import requests as req_mod

        full = ""
        try:
            resp = req_mod.post(
                f"{host}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    "stream": True,
                    "think": False,
                    "options": {"num_predict": 1600, "temperature": 0.5},
                },
                stream=True,
                timeout=180,
            )
            if resp.status_code >= 400:
                err_msg = f"Ollama error HTTP {resp.status_code}"
                yield f"data: {json.dumps({'type': 'error', 'content': err_msg})}\n\n"
                return
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk_j = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = chunk_j.get("message") or {}
                token = msg.get("content") or ""
                if not token:
                    token = msg.get("thinking") or ""
                if token:
                    full += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                if chunk_j.get("done"):
                    break
            if not full.strip():
                yield f"data: {json.dumps({'type': 'error', 'content': 'Ollama returned empty content. Check model and try again.'})}\n\n"
                return
            yield f"data: {json.dumps({'type': 'done', 'content': full})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
