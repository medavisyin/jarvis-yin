"""MiMo TTS tests stay off the network."""
from __future__ import annotations

import os
import sys

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_RAG = os.path.join(_SCRIPTS, "rag")
_STOCK = os.path.join(_SCRIPTS, "stock")
if _STOCK in sys.path:
    sys.path.remove(_STOCK)
for _p in (_SCRIPTS, _RAG):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)
sys.modules.pop("config", None)

import agent  # noqa: E402
import mimo_chat  # noqa: E402
import routes.ai_news as ai_news  # noqa: E402
from routes.ai_news import _tts_segments_to_mp3  # noqa: E402
from web_api import Flask  # noqa: E402
from routes.intensive_reading import intensive_reading_bp  # noqa: E402


def test_tts_route_speak_and_sing(monkeypatch, tmp_path):
    original = dict(agent._GLOBAL_SETTINGS)
    seen = {}

    def fake_wav(_client, text, *, lang="zh"):
        seen["text"] = text
        seen["lang"] = lang
        return b"wav"

    monkeypatch.setattr(agent, "_save_settings", lambda _settings: None)
    monkeypatch.setattr(mimo_chat, "make_client", lambda _key: object())
    monkeypatch.setattr(mimo_chat, "synthesize_wav", fake_wav)
    try:
        agent._GLOBAL_SETTINGS["mimo_api_key"] = "sk-1234567890abcd"
        client = agent.app.test_client()
        speak = client.post("/api/mimo/tts/test", json={"mode": "speak"})
        assert speak.status_code == 200
        assert (speak.headers.get("content-type") or "").startswith("audio/wav")
        assert speak.data == b"wav"
        assert seen["text"] == mimo_chat.SPEAK_SAMPLE
        sing = client.post("/api/mimo/tts/test", json={"mode": "sing"})
        assert sing.data == b"wav"
        assert seen["text"] == mimo_chat.SING_SAMPLE
        other = client.post("/api/mimo/tts/test", json={"mode": "other"})
        assert other.status_code == 400
    finally:
        agent._GLOBAL_SETTINGS.clear()
        agent._GLOBAL_SETTINGS.update(original)


def test_segments_use_mimo_style_prefix(monkeypatch, tmp_path):
    seen = {}

    def fake_wav(_client, text, *, lang="zh"):
        seen["text"] = text
        return b"wav"

    monkeypatch.setattr(mimo_chat, "make_client", lambda _key: object())
    monkeypatch.setattr(mimo_chat, "synthesize_wav", fake_wav)
    monkeypatch.setattr(mimo_chat, "wav_to_mp3", lambda _wav: b"ID3mimo")
    out = tmp_path / "out.mp3"
    _tts_segments_to_mp3(
        ["今天天气不错。"],
        str(out),
        engine="mimo",
        lang="zh",
        style="平静",
        key="sk-1234567890abcd",
    )
    assert seen["text"].startswith("(平静)")
    assert out.read_bytes() == b"ID3mimo"


def test_segments_edge_still_constructs_edge(monkeypatch, tmp_path):
    created = {}

    class FakeComm:
        def __init__(self, text, voice, rate, pitch):
            created["voice"] = voice

        async def save(self, path):
            with open(path, "wb") as handle:
                handle.write(b"ID3edge")

    import edge_tts
    monkeypatch.setattr(edge_tts, "Communicate", FakeComm)
    out = tmp_path / "edge.mp3"
    _tts_segments_to_mp3(["hello"], str(out), voice="zh-CN-XiaoxiaoNeural", engine="edge")
    assert created["voice"] == "zh-CN-XiaoxiaoNeural"
    assert out.read_bytes().startswith(b"ID3")


def test_speak_uses_mimo_then_pads(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(intensive_reading_bp)
    client = app.test_client()
    order = []

    def fake_wav(_client, text, *, lang="zh"):
        order.append(("wav", text, lang))
        return b"wav"

    def fake_mp3(_wav):
        order.append("mp3")
        return b"ID3mimo"

    def fake_pad(audio):
        order.append(("pad", audio))
        return b"PADDED"

    monkeypatch.setattr("routes.intensive_reading._global_settings", lambda: {
        "audio_engine": "mimo",
        "audio_mimo_style": "平静",
        "mimo_api_key": "sk-1234567890abcd",
    })
    monkeypatch.setattr("routes.intensive_reading.can_pad_silence", lambda: True)
    monkeypatch.setattr("routes.intensive_reading.prepend_silence_mp3", fake_pad)
    monkeypatch.setattr("routes.intensive_reading.synthesize_speech", lambda **_k: (_ for _ in ()).throw(AssertionError("edge")))
    monkeypatch.setattr(mimo_chat, "make_client", lambda _key: object())
    monkeypatch.setattr(mimo_chat, "synthesize_wav", fake_wav)
    monkeypatch.setattr(mimo_chat, "wav_to_mp3", fake_mp3)
    response = client.post("/api/intensive-reading/speak", json={"text": "congressman", "rate": "slow"})
    assert response.status_code == 200
    assert (response.headers.get("content-type") or "").startswith("audio/mpeg")
    assert response.data == b"PADDED"
    assert order[0][0] == "wav"
    assert order[0][1].startswith("(平静)")
    assert order[0][2] == "en"
    assert order[1] == "mp3"
    assert order[2] == ("pad", b"ID3mimo")


def _stub_knowledge_pipeline(monkeypatch, tmp_path, narration="[主播] 你好。"):
    monkeypatch.setattr(ai_news, "REPORTS_ROOT", str(tmp_path))
    monkeypatch.setattr(ai_news, "_get_qdrant", lambda: None)
    monkeypatch.setattr(ai_news, "_sync_qdrant_points_from_snapshot", lambda: None)
    monkeypatch.setattr(ai_news, "get_qdrant_points", lambda: [{
        "payload": {
            "item_type": "book_chapter",
            "parent_title": "Book",
            "title": "Chapter",
            "text": "Some text about MiMo.",
            "date": "2026-09-29",
            "source": "test",
        }
    }])
    monkeypatch.setattr(ai_news, "_resolved_web_search_references", lambda *_a, **_k: "")
    monkeypatch.setattr(ai_news, "_audio_prefs", lambda: {
        "audio_engine": "mimo",
        "audio_mimo_style": "平静",
        "mimo_api_key": "sk-1234567890abcd",
    })

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": narration}}

    monkeypatch.setattr(ai_news.req_mod, "post", lambda *_a, **_k: _Resp())


def test_knowledge_audio_mimo_skips_edge(monkeypatch, tmp_path):
    seen = {}

    def fake_wav(_client, text, *, lang="zh"):
        seen["text"] = text
        return b"wav"

    def forbid_edge(*_a, **_k):
        raise AssertionError("edge")

    import edge_tts
    monkeypatch.setattr(edge_tts, "Communicate", forbid_edge)
    monkeypatch.setattr(mimo_chat, "make_client", lambda _key: object())
    monkeypatch.setattr(mimo_chat, "synthesize_wav", fake_wav)
    monkeypatch.setattr(mimo_chat, "wav_to_mp3", lambda _wav: b"ID3mimo")
    _stub_knowledge_pipeline(monkeypatch, tmp_path)
    ai_news._audio_jobs["ka-mimo"] = {"status": "queued"}
    try:
        ai_news._generate_knowledge_audio("ka-mimo", "book_chapter", ["Book"], "zh")
        job = ai_news._audio_jobs["ka-mimo"]
        assert job.get("error") in (None, "")
        assert seen["text"].startswith("(平静)")
        assert job["output_path"].endswith(".mp3")
    finally:
        ai_news._audio_jobs.pop("ka-mimo", None)


def test_knowledge_audio_mimo_failure_hides_key(monkeypatch, tmp_path):
    secret = "sk-1234567890abcd"

    def boom(_client, _text, *, lang="zh"):
        raise RuntimeError(f"Bearer {secret}")

    monkeypatch.setattr(mimo_chat, "make_client", lambda _key: object())
    monkeypatch.setattr(mimo_chat, "synthesize_wav", boom)
    _stub_knowledge_pipeline(monkeypatch, tmp_path)
    ai_news._audio_jobs["ka-fail"] = {"status": "queued"}
    try:
        ai_news._generate_knowledge_audio("ka-fail", "book_chapter", ["Book"], "zh")
        error = ai_news._audio_jobs["ka-fail"].get("error") or ""
        assert secret not in error
        assert error == "MiMo request failed"
    finally:
        ai_news._audio_jobs.pop("ka-fail", None)


def test_segments_mimo_failure_hides_key(monkeypatch, tmp_path):
    secret = "sk-1234567890abcd"

    def boom(_client, _text, *, lang="zh"):
        raise RuntimeError(f"Bearer {secret}")

    monkeypatch.setattr(mimo_chat, "make_client", lambda _key: object())
    monkeypatch.setattr(mimo_chat, "synthesize_wav", boom)
    out = tmp_path / "leak.mp3"
    try:
        _tts_segments_to_mp3(
            ["今天天气不错。"],
            str(out),
            engine="mimo",
            lang="zh",
            style="平静",
            key=secret,
        )
    except Exception as exc:
        message = str(exc)[:300]
        assert secret not in message
        assert message == "MiMo request failed"
        return
    raise AssertionError("MiMo TTS failure did not raise")
