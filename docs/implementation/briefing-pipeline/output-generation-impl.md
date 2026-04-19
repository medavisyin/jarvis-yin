# Implementation Guide: Output Generation

## Overview

After `briefing-data.json` is produced (and optionally filtered for topic freshness), three scripts materialize human-consumable deliverables: a typeset PDF, a Chinese TTS podcast, and a slideshow video synchronized with narration.

| Script | Deliverable |
|--------|-------------|
| `scripts/output/briefing-template.py` | `ai-briefing.pdf` |
| `scripts/output/generate-audio.py` | `ai-briefing.mp3` |
| `scripts/output/generate-video.py` | `ai-briefing.mp4` |

## Technologies

| Library / module | Script | Role |
|------------------|--------|------|
| **ReportLab** | `briefing-template.py` | PDF layout, paragraphs, tables of contents, pagination |
| **edge-tts** | `generate-audio.py` | Microsoft Edge neural TTS (Chinese voice) |
| **moviepy** | `generate-video.py` | Clip sequencing, audio muxing, timeline composition |
| **Pillow (PIL)** | `generate-video.py` | Raster slide images from structured slide data |
| **asyncio** | `generate-audio.py` | Concurrent segment synthesis where applicable |
| **json** | All three | Load briefing or narration/slide payloads |

## briefing-template.py

### Architecture

- Loads `briefing-data.json` (or a path passed via CLI / convention).
- Builds a document model: cover or title page, table of contents, and repeating sections per item or category.
- Flows long summaries with wrapping; uses styles for headings, body text, and metadata lines.
- Registers a Chinese-capable font so mixed or fully Chinese content renders without tofu glyphs.

### Input / output

- **Input:** Merged briefing JSON with `items` (title, summary, date, url, optional tags).
- **Output:** `ai-briefing.pdf` placed under the date-organized output folder used by the Jarvis briefing layout.

### Configuration

- Page size, margins, and style sheets are defined in code or small constants at the top of the script.
- Font paths or embedded font names must match the environment (system fonts vs bundled TTF).

## generate-audio.py (standalone / legacy)

### Architecture

- Reads a narration JSON containing Chinese text segmented by section or slide (structure aligns with the briefing outline).
- Calls `edge-tts` with a Chinese neural voice such as `zh-CN-XiaoxiaoNeural`.
- Writes MP3 bytes sequentially or in parallel async tasks, then concatenates or encodes a single track.

> **Note:** The Daily Fetch pipeline in `agent.py` does **not** use this script. It has its own segmented audio generation built in (see below). This script remains for manual/standalone use.

### Input / output

- **Input:** Narration JSON (Chinese strings per section).
- **Output:** `ai-briefing.mp3` in the same dated folder convention as the PDF.

### Voice settings

- Voice name, rate, pitch, and volume are configurable via constants or CLI flags where implemented.
- Default voice targets natural Mandarin delivery suitable for daily briefing playback.

## Daily Fetch Audio (in agent.py — segmented approach)

### Architecture

The Daily Fetch pipeline generates audio using a **segmented per-source/category** approach for significantly faster generation:

1. **Content splitting:** Briefing data is split by source (AI Brief) or category (World News). Each source/category becomes one narration segment.
2. **Narration generation:** Each segment is sent to the fast narration model (`qwen3:1.7b` via `OLLAMA_MODEL_NARRATION`) with `num_predict: 8192` and 600s timeout. The first segment includes an intro, the last includes an outro.
3. **TTS conversion:** Each narration is cleaned (markdown/sound-effect annotations removed), chunked at 2000-char sentence boundaries, and converted to MP3 via Edge-TTS (`zh-CN-YunxiNeural`, with fallback to `zh-CN-YunjianNeural` and `zh-CN-XiaoxiaoNeural`).
4. **Concatenation:** All segment MP3 parts are merged via `ffmpeg -f concat -c copy` (or binary concatenation if ffmpeg is unavailable).

### Why segmented?

| Aspect | Old (single-call) | New (segmented) |
|--------|-------------------|-----------------|
| Model | `qwen3.5:4b` (4B params) | `qwen3:1.7b` (1.7B params) |
| LLM calls | 1 large call | N calls (one per source/category) |
| `num_predict` | 32768 | 8192 per segment |
| Timeout | 1800s | 600s per segment |
| Total audio | ~8-15 min | ~15 min (sum of segments) |
| Speed | Slow (large model, huge token budget) | Much faster (~4x smaller model, smaller calls) |

### Key functions

- `_ollama_narration_call(system_prompt, user_prompt, max_tokens, timeout)` — Low-level Ollama call using `OLLAMA_MODEL_NARRATION`
- `_generate_segmented_narrations(segments, content_type, lang)` — Iterates source/category segments, generates narration per segment. The `lang` parameter (`"zh"` or `"en"`) controls prompt language and narration style.
- `_tts_segments_to_mp3(narrations, out_path, voice)` — Edge-TTS all narrations, chunk and merge into final MP3
- `_generate_briefing_narration(content, content_type)` — Legacy single-call function, still available for backward compatibility

### Language-aware audio generation

Audio language is controlled per type via Global Settings (`_GLOBAL_SETTINGS` dict, accessible through `GET/POST /api/settings`):

| Setting Key | Audio Type | Output File | Default |
|-------------|-----------|-------------|---------|
| `audio_lang_ai` | AI Briefing | `ai-briefing.mp3` | `"zh"` |
| `audio_lang_world` | World News (international) | `world-news.mp3` | `"zh"` |
| `audio_lang_china` | 中国新闻 (Chinese political/financial) | `china-news.mp3` | `"zh"` |
| `audio_lang_knowledge` | Knowledge | `knowledge-audio.mp3` | `"zh"` |

World news audio is split into two separate files:
- **`world-news.mp3`**: International news only (BBC, Reuters, AP, DW, Guardian)
- **`china-news.mp3`**: Chinese news only (Sina, People's Daily, CLS, Toutiao, Weibo) — up to 6 items per category, cross-day dedup

When generating audio, the pipeline prefers translated `title_zh`/`summary_zh` fields if the language is `"zh"`. For `"en"`, it uses the original English `title`/`summary`.

TTS voice selection is dynamic:

| Language | Voice |
|----------|-------|
| Chinese (`"zh"`) | `zh-CN-YunxiNeural` |
| English (`"en"`) | `en-US-AndrewNeural` |

See [Global Settings](../rag/global-settings-impl.md) for the full settings UI implementation.

### Configuration

- `OLLAMA_MODEL_NARRATION` defaults to `qwen3:1.7b`, overridable via `RAG_NARRATION_MODEL` env var
- TTS voice: selected dynamically based on language (see above), with automatic fallback for Chinese
- TTS rate: `-5%`, pitch: `+0Hz`

## generate-video.py

### Architecture

- Reads a slides JSON: each slide has a title and bullet points (and optionally timing hints).
- Uses Pillow to render fixed-resolution images (background, typography, bullet layout).
- Uses moviepy to import each image as a clip, set durations, and attach the TTS audio track.
- Exports a single H.264-friendly MP4.

### Input / output

- **Input:** Slides JSON plus `ai-briefing.mp3` (or inline generation if the script chains TTS).
- **Output:** `ai-briefing.mp4` alongside PDF and MP3.

### Font / visual settings

- PIL font selection should mirror PDF choices for brand consistency when possible.
- Resolution (e.g., 1920×1080) and frame rate are defined once for predictable file size and upload compatibility.

## Input and Output Formats (Summary)

| Script | Primary input | Primary output |
|--------|---------------|----------------|
| `briefing-template.py` | `briefing-data.json` | `ai-briefing.pdf` |
| `generate-audio.py` | Narration JSON (Chinese) | `ai-briefing.mp3` |
| `generate-video.py` | Slides JSON + audio | `ai-briefing.mp4` |

Field-level schemas for narration and slides JSON follow the conventions established by the briefing merge and any helper that emits those files from `briefing-data.json`.

## Configuration Checklist

- Ensure `briefing-data.json` path matches between merge/filter stages and `briefing-template.py`.
- Install ReportLab, edge-tts, moviepy, and Pillow in the same Python environment used for cron or manual runs.
- For Chinese PDF output, verify font files are readable on the host OS.
- For video, confirm ffmpeg dependencies required by moviepy are on `PATH`.
