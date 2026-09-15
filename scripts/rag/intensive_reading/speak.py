"""Edge TTS helpers for Intensive Reading selection speak."""

from __future__ import annotations

import shutil
import subprocess

MAX_SPEAK_CHARS = 2000
LEADING_PAUSE_MS = 500

_EDGE_RATES = {
    "slow": "-25%",
    "medium": "-10%",
    "fast": "+0%",
}


def normalize_speak_rate(rate: str | None) -> str:
    r = (rate or "").strip().lower()
    return r if r in _EDGE_RATES else "slow"


def edge_rate_for(rate: str | None) -> str:
    return _EDGE_RATES[normalize_speak_rate(rate)]


def validate_speak_text(text: str | None) -> str:
    t = (text or "").strip()
    if not t:
        raise ValueError("text is required")
    if len(t) > MAX_SPEAK_CHARS:
        raise ValueError(f"text too long (max {MAX_SPEAK_CHARS})")
    return t


def can_pad_silence() -> bool:
    return bool(shutil.which("ffmpeg"))


def speak_text_for_tts(text: str, *, pad_silence: bool) -> str:
    return text if pad_silence else f". {text}"


def prepend_silence_mp3(audio: bytes, duration_ms: int = LEADING_PAUSE_MS) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if not audio or not ffmpeg:
        return audio
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        word = os.path.join(td, "word.mp3")
        out = os.path.join(td, "out.mp3")
        with open(word, "wb") as f:
            f.write(audio)
        try:
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "lavfi",
                    "-t",
                    f"{duration_ms / 1000:.2f}",
                    "-i",
                    "anullsrc=r=24000:cl=mono",
                    "-i",
                    word,
                    "-filter_complex",
                    "[0:a][1:a]concat=n=2:v=0:a=1",
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    "48k",
                    out,
                ],
                check=True,
                capture_output=True,
                timeout=15,
            )
            with open(out, "rb") as f:
                padded = f.read()
            return padded or audio
        except Exception:
            return audio


def synthesize_speech(text: str, voice: str, rate: str, timeout: float = 20) -> bytes:
    import asyncio

    import edge_tts

    async def _run() -> bytes:
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch="+0Hz")
        chunks: list[bytes] = []
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        return b"".join(chunks)

    return asyncio.run(asyncio.wait_for(_run(), timeout=timeout))
