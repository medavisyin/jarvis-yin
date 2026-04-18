"""
AI Briefing Audio Generator — Chinese narration podcast.

Reads a JSON data file (same format as briefing-template.py) and generates
a natural-sounding Chinese podcast narration using Edge-TTS.

Usage:
  1. Agent writes briefing data JSON + narration script JSON
  2. Run: python generate-audio.py narration.json
  3. Output: C:/reports/ai/YYYY-MM-DD/ai-briefing.mp3

The narration JSON has a single key "narration" with the full Chinese text.
The agent generates conversational Chinese text from the briefing data.

Long narrations are split into chunks for Edge-TTS and concatenated.
Uses ffmpeg if available; falls back to binary MP3 concatenation otherwise.

Optional JSON keys:
  "voice": override Edge voice (default zh-CN-YunxiNeural)
  "rate": e.g. "-5%" (default "-5%")
  "pitch": e.g. "+0Hz" (default "+0Hz")

Dependencies: pip install edge-tts  |  optional: ffmpeg on PATH for cleaner joins
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import REPORTS_ROOT

DATE_FOLDER = date.today().strftime("%Y-%m-%d")
OUTPUT_DIR = os.path.join(REPORTS_ROOT, DATE_FOLDER)
DEFAULT_OUTPUT_FILENAME = "ai-briefing.mp3"

VOICE = "zh-CN-YunxiNeural"
RATE = "-5%"
PITCH = "+0Hz"

# Edge-TTS is more reliable under this size per request
CHUNK_MAX_CHARS = 2000


def _chunk_narration(text: str, max_len: int = CHUNK_MAX_CHARS) -> List[str]:
    text = text.strip()
    if len(text) <= max_len:
        return [text]
    parts: List[str] = []
    current: List[str] = []
    current_len = 0
    for para in text.split("\n\n"):
        plen = len(para) + (2 if current else 0)
        if current_len + plen > max_len and current:
            parts.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += plen
    if current:
        parts.append("\n\n".join(current))
    return parts


async def _tts_save_chunk(text: str, path: str, voice: str, rate: str, pitch: str):
    import edge_tts

    for attempt in range(3):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            await communicate.save(path)
            return
        except Exception as e:
            if attempt < 2:
                print(f"  TTS attempt {attempt+1} failed ({e}), retrying...")
                import asyncio
                await asyncio.sleep(2)
            else:
                raise


def _concat_mp3(part_paths: List[str], out_path: str) -> None:
    """Concatenate MP3 files. Tries ffmpeg first; falls back to binary cat."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as list_file:
            for p in part_paths:
                safe = os.path.abspath(p).replace("\\", "/")
                list_file.write(f"file '{safe}'\n")
            list_path = list_file.name
        try:
            subprocess.run(
                [ffmpeg, "-y", "-f", "concat", "-safe", "0",
                 "-i", list_path, "-c", "copy", out_path],
                check=True, capture_output=True, text=True,
            )
            return
        finally:
            try:
                os.unlink(list_path)
            except OSError:
                pass

    # MP3 frames are independently decodable; binary concatenation works.
    with open(out_path, "wb") as out:
        for p in part_paths:
            with open(p, "rb") as chunk:
                out.write(chunk.read())


async def generate_audio(text: str, voice: str, rate: str, pitch: str,
                         output_filename: str = DEFAULT_OUTPUT_FILENAME):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    chunks = _chunk_narration(text)
    if len(chunks) == 1:
        await _tts_save_chunk(chunks[0], output_path, voice, rate, pitch)
        print(f"Audio saved to: {output_path}")
        return

    part_paths = []
    for i, chunk in enumerate(chunks):
        part = os.path.join(OUTPUT_DIR, f"_tts_part_{i}.mp3")
        await _tts_save_chunk(chunk, part, voice, rate, pitch)
        part_paths.append(part)

    try:
        _concat_mp3(part_paths, output_path)
    finally:
        for p in part_paths:
            try:
                os.remove(p)
            except OSError:
                pass
    print(f"Audio saved to: {output_path} ({len(chunks)} chunks merged)")


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate-audio.py <narration.json>")
        print('The narration JSON must have a "narration" key with the full text.')
        sys.exit(1)

    data_path = sys.argv[1]
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    narration_text = data.get("narration", "")
    if not narration_text:
        print("Error: narration text is empty")
        sys.exit(1)

    voice = data.get("voice", VOICE)
    rate = data.get("rate", RATE)
    pitch = data.get("pitch", PITCH)
    output_filename = data.get("output_filename", DEFAULT_OUTPUT_FILENAME)

    asyncio.run(generate_audio(narration_text, voice, rate, pitch, output_filename))


if __name__ == "__main__":
    main()
