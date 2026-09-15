"""TDD: Intensive Reading Explain speak (Edge TTS)."""

from __future__ import annotations

import os
import subprocess
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

from intensive_reading.speak import (  # noqa: E402
    MAX_SPEAK_CHARS,
    edge_rate_for,
    normalize_speak_rate,
    prepend_silence_mp3,
    speak_text_for_tts,
    validate_speak_text,
)
from routes.intensive_reading import intensive_reading_bp  # noqa: E402


def test_normalize_speak_rate_defaults_to_slow():
    assert normalize_speak_rate("slow") == "slow"
    assert normalize_speak_rate("MEDIUM") == "medium"
    assert normalize_speak_rate("fast") == "fast"
    assert normalize_speak_rate(None) == "slow"
    assert normalize_speak_rate("quick") == "slow"


def test_edge_rate_for_matches_design():
    assert edge_rate_for("slow") == "-25%"
    assert edge_rate_for("medium") == "-10%"
    assert edge_rate_for("fast") == "+0%"


def test_speak_text_for_tts_keeps_word_when_silence_pad_available():
    assert speak_text_for_tts("congressman", pad_silence=True) == "congressman"


def test_speak_text_for_tts_adds_leading_pause_without_ffmpeg():
    assert speak_text_for_tts("congressman", pad_silence=False) == ". congressman"


def test_prepend_silence_mp3_uses_half_second_ffmpeg_pad(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_which(_name: str) -> str:
        return "/usr/bin/ffmpeg"

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        Path(cmd[-1]).write_bytes(b"PADDED")
        return subprocess.CompletedProcess(cmd, 0)

    from intensive_reading import speak as speak_mod

    monkeypatch.setattr(speak_mod.shutil, "which", fake_which)
    monkeypatch.setattr(speak_mod.subprocess, "run", fake_run)

    out = prepend_silence_mp3(b"WORDMP3")
    assert out == b"PADDED"
    joined = " ".join(" ".join(c) for c in calls)
    assert "anullsrc" in joined
    assert "0.50" in joined


def test_validate_speak_text_rejects_blank_and_too_long():
    with pytest.raises(ValueError):
        validate_speak_text("  ")
    with pytest.raises(ValueError):
        validate_speak_text("x" * (MAX_SPEAK_CHARS + 1))
    assert validate_speak_text("  hello  ") == "hello"


@pytest.fixture()
def client():
    app = Flask(__name__)
    app.register_blueprint(intensive_reading_bp)
    app.config["TESTING"] = True
    yield app.test_client()


def test_speak_rejects_empty_text(client):
    r = client.post("/api/intensive-reading/speak", json={"text": "  ", "rate": "slow"})
    assert r.status_code == 400
    assert "text" in (r.get_json().get("error") or "").lower()


def test_speak_rejects_too_long_text(client):
    r = client.post(
        "/api/intensive-reading/speak",
        json={"text": "x" * (MAX_SPEAK_CHARS + 1), "rate": "slow"},
    )
    assert r.status_code == 400
    assert "too long" in (r.get_json().get("error") or "").lower()


def test_speak_returns_mp3_with_mocked_tts(client):
    with (
        patch("routes.intensive_reading.can_pad_silence", return_value=True),
        patch("routes.intensive_reading.prepend_silence_mp3", side_effect=lambda audio: audio),
        patch(
            "routes.intensive_reading.synthesize_speech",
            return_value=b"ID3fake",
        ) as synth,
    ):
        r = client.post(
            "/api/intensive-reading/speak",
            json={"text": "a bitter pill", "rate": "slow"},
        )
    assert r.status_code == 200
    assert (r.headers.get("content-type") or "").startswith("audio/mpeg")
    assert r.data == b"ID3fake"
    assert synth.call_args.kwargs["rate"] == "-25%"
    assert synth.call_args.kwargs["text"] == "a bitter pill"


def test_speak_pads_silence_when_ffmpeg_available(client):
    with (
        patch("routes.intensive_reading.can_pad_silence", return_value=True),
        patch("routes.intensive_reading.synthesize_speech", return_value=b"RAW") as synth,
        patch("routes.intensive_reading.prepend_silence_mp3", return_value=b"PADDED") as pad,
    ):
        r = client.post(
            "/api/intensive-reading/speak",
            json={"text": "congressman", "rate": "slow"},
        )
    assert r.status_code == 200
    assert r.data == b"PADDED"
    assert synth.call_args.kwargs["text"] == "congressman"
    pad.assert_called_once_with(b"RAW")


def test_speak_prefixes_pause_when_ffmpeg_missing(client):
    with (
        patch("routes.intensive_reading.can_pad_silence", return_value=False),
        patch("routes.intensive_reading.synthesize_speech", return_value=b"ID3fake") as synth,
        patch("routes.intensive_reading.prepend_silence_mp3") as pad,
    ):
        r = client.post(
            "/api/intensive-reading/speak",
            json={"text": "congressman", "rate": "slow"},
        )
    assert r.status_code == 200
    assert synth.call_args.kwargs["text"] == ". congressman"
    pad.assert_not_called()


def test_speak_timeout_returns_504(client):
    with patch("routes.intensive_reading.synthesize_speech", side_effect=TimeoutError):
        r = client.post(
            "/api/intensive-reading/speak",
            json={"text": "a bitter pill", "rate": "slow"},
        )
    assert r.status_code == 504
    err = (r.get_json().get("error") or "").lower()
    assert "timeout" in err or "timed out" in err


def test_speak_failure_hides_exception_text(client):
    with patch(
        "routes.intensive_reading.synthesize_speech",
        side_effect=RuntimeError("edge-internal-secret"),
    ):
        r = client.post(
            "/api/intensive-reading/speak",
            json={"text": "a bitter pill", "rate": "slow"},
        )
    assert r.status_code == 502
    body = r.get_json().get("error") or ""
    assert "edge-internal-secret" not in body
    assert "TTS failed" in body
