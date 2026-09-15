"""TDD: magazine-only speaking tab (logic / cue / pressure)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
for _p in (_SCRIPTS, _RAG):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from web_api import Flask  # noqa: E402

from intensive_reading.analysis_cache import (  # noqa: E402
    load_chunk_analysis,
    save_chunk_analysis,
)
from intensive_reading.prompts import (  # noqa: E402
    allowed_kinds,
    speaking_system_prompt,
    speaking_user_message,
    tabs_for_book_type,
)
from routes.intensive_reading import intensive_reading_bp  # noqa: E402

INDEX = Path(__file__).resolve().parents[1] / "scripts" / "rag" / "templates" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _function_source(html: str, name: str) -> str:
    start = -1
    for prefix in (f"function {name}(", f"async function {name}("):
        start = html.find(prefix)
        if start != -1:
            break
    if start < 0:
        raise AssertionError(f"missing function {name}")
    nxt = html.find("\nfunction ", start + 1)
    nxt_async = html.find("\nasync function ", start + 1)
    ends = [i for i in (nxt, nxt_async) if i != -1]
    end = min(ends) if ends else start + 5000
    return html[start:end]


def test_speaking_tab_magazine_only_not_an_analyze_kind():
    mag_ids = [t["id"] for t in tabs_for_book_type("magazine")]
    novel_ids = [t["id"] for t in tabs_for_book_type("novel")]
    assert "speaking" in mag_ids
    assert mag_ids[-1] == "speaking"
    assert "speaking" not in novel_ids
    assert "speaking" not in allowed_kinds("magazine")
    assert "vocab" in allowed_kinds("magazine")


def test_speaking_prompts_cover_three_exercises():
    logic = speaking_system_prompt("logic")
    cue = speaking_system_prompt("cue")
    pressure = speaking_system_prompt("pressure")
    assert "core claim" in logic.lower() or "core assertion" in logic.lower() or "主张" in logic
    assert "Meaning and Sense" not in logic  # not the selection-explain prompt
    assert "passive" in cue.lower() or "Problem-Solution-Benefit" in cue
    assert "Yes, but" in pressure
    with pytest.raises((KeyError, ValueError)):
        speaking_system_prompt("nope")


def test_speaking_user_message_includes_passage_and_oral():
    msg = speaking_user_message(
        exercise="logic",
        passage="Growth slowed in Britain.",
        oral="The UK economy is weaker.",
    )
    assert "Growth slowed in Britain." in msg
    assert "The UK economy is weaker." in msg


def test_save_analysis_preserves_speaking_and_speaking_only_save(tmp_path):
    books = tmp_path / "books"
    bid = "magbook-aaa111"
    book_dir = books / bid
    book_dir.mkdir(parents=True)
    save_chunk_analysis(
        str(books),
        bid,
        0,
        {"vocab": {"text": "old tab", "status": "done"}},
        merge=False,
    )
    save_chunk_analysis(
        str(books),
        bid,
        0,
        {},
        merge=True,
        speaking={"oral": "my retell", "logic": "skeleton", "phase": "idle"},
    )
    doc = load_chunk_analysis(str(books), bid, 0)
    assert doc["tabs"]["vocab"]["text"] == "old tab"
    assert doc["speaking"]["oral"] == "my retell"
    assert doc["speaking"]["logic"] == "skeleton"
    save_chunk_analysis(
        str(books),
        bid,
        0,
        {"stance": {"text": "new", "status": "done"}},
        merge=True,
    )
    doc2 = load_chunk_analysis(str(books), bid, 0)
    assert doc2["tabs"]["stance"]["text"] == "new"
    assert doc2["speaking"]["oral"] == "my retell"


def test_merge_false_tabs_replace_keeps_speaking_when_omitted(tmp_path):
    books = tmp_path / "books"
    bid = "magbook-bbb222"
    (books / bid).mkdir(parents=True)
    save_chunk_analysis(
        str(books),
        bid,
        0,
        {"vocab": {"text": "v1", "status": "done"}},
        merge=False,
        speaking={"oral": "keep me", "logic": "L"},
    )
    save_chunk_analysis(
        str(books),
        bid,
        0,
        {"stance": {"text": "only stance", "status": "done"}},
        merge=False,
    )
    doc = load_chunk_analysis(str(books), bid, 0)
    assert "vocab" not in doc["tabs"]
    assert doc["tabs"]["stance"]["text"] == "only stance"
    assert doc["speaking"]["oral"] == "keep me"
    assert doc["speaking"]["logic"] == "L"


def test_speaking_user_message_pressure_step2_includes_reply():
    msg = speaking_user_message(
        exercise="pressure",
        passage="The bank cut rates.",
        oral="Rates will fall further.",
        pressure_step=2,
        pressure_attack="Yes, but the sample is tiny.",
        user_reply="The sample is the whole G7.",
    )
    assert "Yes, but the sample is tiny." in msg
    assert "The sample is the whole G7." in msg
    assert "step 2" in msg.lower()



@pytest.fixture()
def client():
    app = Flask(__name__)
    app.register_blueprint(intensive_reading_bp)
    app.config["TESTING"] = True
    yield app.test_client()


def _meta(book_type: str = "magazine") -> dict:
    return {"title": "The Economist", "book_type": book_type, "chunk_count": 1}


def test_speaking_api_rejects_novel(client):
    with patch("routes.intensive_reading._books_dir", return_value="X"):
        with patch("routes.intensive_reading.load_meta", return_value=_meta("novel")):
            with patch(
                "routes.intensive_reading.get_chunk",
                return_value={"text": "Hello.", "is_toc": False},
            ):
                r = client.post(
                    "/api/intensive-reading/speaking",
                    json={
                        "book_id": "magbook-aaa111",
                        "chunk_index": 0,
                        "exercise": "logic",
                        "oral_text": "hi",
                    },
                )
    assert r.status_code == 400
    assert "magazine" in (r.get_json().get("error") or "").lower()


def test_speaking_api_pressure_requires_oral(client):
    with patch("routes.intensive_reading._books_dir", return_value="X"):
        with patch("routes.intensive_reading.load_meta", return_value=_meta("magazine")):
            with patch(
                "routes.intensive_reading.get_chunk",
                return_value={"text": "Hello.", "is_toc": False},
            ):
                r = client.post(
                    "/api/intensive-reading/speaking",
                    json={
                        "book_id": "magbook-aaa111",
                        "chunk_index": 0,
                        "exercise": "pressure",
                        "oral_text": "  ",
                        "pressure_step": 1,
                    },
                )
    assert r.status_code == 400
    assert "oral" in (r.get_json().get("error") or "").lower()


def test_speaking_api_logic_streams_with_mocked_ollama(client):
    class _FakeResp:
        status_code = 200

        def iter_lines(self):
            yield json.dumps({"message": {"content": "Claim: x"}}).encode()
            yield json.dumps(
                {"message": {"content": ""}, "done": True, "done_reason": "stop"}
            ).encode()

    with patch("routes.intensive_reading._books_dir", return_value="X"):
        with patch("routes.intensive_reading.load_meta", return_value=_meta("magazine")):
            with patch(
                "routes.intensive_reading.get_chunk",
                return_value={"text": "Growth slowed.", "is_toc": False},
            ):
                with patch(
                    "routes.intensive_reading._ollama_settings",
                    return_value=("http://localhost:9", "m"),
                ):
                    with patch("requests.post", return_value=_FakeResp()):
                        r = client.post(
                            "/api/intensive-reading/speaking",
                            json={
                                "book_id": "magbook-aaa111",
                                "chunk_index": 0,
                                "exercise": "logic",
                                "oral_text": "",
                            },
                        )
    assert r.status_code == 200
    assert "Claim: x" in r.data.decode("utf-8")


def test_analyze_rejects_speaking_kind(client):
    with patch("routes.intensive_reading._books_dir", return_value="X"):
        with patch("routes.intensive_reading.load_meta", return_value=_meta("magazine")):
            with patch(
                "routes.intensive_reading.get_chunk",
                return_value={"text": "Hello.", "is_toc": False},
            ):
                r = client.post(
                    "/api/intensive-reading/analyze",
                    json={
                        "book_id": "magbook-aaa111",
                        "chunk_index": 0,
                        "analysis_kind": "speaking",
                    },
                )
    assert r.status_code == 400
    err = (r.get_json().get("error") or "").lower()
    assert "speaking" in err or "invalid" in err


def test_put_analysis_rejects_kind_speaking(client):
    with patch("routes.intensive_reading._books_dir", return_value="X"):
        with patch("routes.intensive_reading.load_meta", return_value=_meta("magazine")):
            r = client.put(
                "/api/intensive-reading/books/magbook-aaa111/chunks/0/analysis",
                json={"kind": "speaking", "slot": {"text": "nope", "status": "done"}},
            )
    assert r.status_code == 400
    assert "speaking" in (r.get_json().get("error") or "").lower()


def test_speaking_api_rejects_oral_too_long(client):
    with patch("routes.intensive_reading._books_dir", return_value="X"):
        with patch("routes.intensive_reading.load_meta", return_value=_meta("magazine")):
            with patch(
                "routes.intensive_reading.get_chunk",
                return_value={"text": "Hello.", "is_toc": False},
            ):
                r = client.post(
                    "/api/intensive-reading/speaking",
                    json={
                        "book_id": "magbook-aaa111",
                        "chunk_index": 0,
                        "exercise": "logic",
                        "oral_text": "x" * 8001,
                    },
                )
    assert r.status_code == 400
    assert "too long" in (r.get_json().get("error") or "").lower()


def test_index_html_speaking_pane_wired_for_magazine():
    html = _html()
    tabs = _function_source(html, "irTabsForType")
    assert "_IR_SPEAKING_TAB" in tabs
    show = _function_source(html, "irShowActiveAnalysis")
    assert "speaking" in show
    assert "function irRunSpeaking" in html or "async function irRunSpeaking" in html
    run = _function_source(html, "irRunSpeaking")
    assert "/api/intensive-reading/speaking" in run
    assert "pressure" in run
    assert "irSpeakLive" in run
    assert "irShowSpeakingPane" not in run
    persist = _function_source(html, "irPersistSpeaking")
    assert "speakingLoaded" in persist
    assert "speakingDirty" in persist
    select = _function_source(html, "irSelectTab")
    assert "await irPersistSpeaking" in select
    reset = _function_source(html, "irResetAnalyses")
    assert "speakingLoaded" in reset
    assert "liveSnapshot" in run
    assert "persistOk" in run
    assert "sp[liveTarget] = liveSnapshot" in run
    load = _function_source(html, "irLoadChunk")
    assert load.find("irPersistSpeaking") < load.find("irResetAnalyses")
    assert "chunkLoading" in load
    openb = _function_source(html, "irOpenBook")
    assert "bookId:" in openb
    assert "chunkIndex:" in openb
    assert "speaking:" in openb
    back = _function_source(html, "irBackToLibrary")
    assert "irPersistSpeaking" in back
    assert back.find("irPersistSpeaking") < back.find("bookId = null")
    show_src = _function_source(html, "irShowSpeakingPane")
    assert show_src.count("irPersistSpeaking") >= 2
    toc = _function_source(html, "irRenderArticlesPop")
    assert "await irLoadChunk" in toc
