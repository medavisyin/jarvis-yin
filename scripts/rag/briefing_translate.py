"""Translate AI briefing items to Chinese for Daily Fetch audio."""

from __future__ import annotations

import os
import re
from typing import Callable

import requests

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
SUMMARY_MAX = 400
BATCH_SIZE = 10
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_TRANSLATE_MODEL = os.environ.get("OLLAMA_MODEL_FAST", "qwen3:1.7b")

TranslateBatch = Callable[[list[str]], list[str]]


def needs_translation(text: str) -> bool:
    t = (text or "").strip()
    return bool(t) and not CJK_RE.search(t)


def pick_item_text(item: dict, prefer_zh: bool) -> tuple[str, str]:
    """Title/summary for narration: Chinese fields when prefer_zh."""
    if prefer_zh:
        title = item.get("title_zh") or item.get("title") or ""
        summary = (
            item.get("summary_zh")
            or item.get("summary")
            or item.get("description")
            or ""
        )
    else:
        title = item.get("title") or ""
        summary = item.get("summary") or item.get("description") or ""
    return title, summary


def briefing_ready_for_zh_audio(bdata: dict | None) -> bool:
    return bool(isinstance(bdata, dict) and bdata.get("translated"))


def _default_translate_batch(texts: list[str]) -> list[str]:
    """Ollama batch translate; same contract as finance news translation."""
    out = [""] * len(texts)
    total = len(texts)
    for batch_start in range(0, total, BATCH_SIZE):
        batch = texts[batch_start:batch_start + BATCH_SIZE]
        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(batch))
        prompt = (
            f"将以下{len(batch)}条新闻标题/摘要翻译成简体中文。"
            f"严格按编号输出，每行格式: 编号. 中文翻译\n"
            f"不要添加任何解释。\n\n{numbered}"
        )
        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": OLLAMA_TRANSLATE_MODEL,
                    "messages": [
                        {"role": "system", "content": "你是专业翻译。只输出翻译结果，不要解释。"},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0.1, "num_predict": 2000},
                },
                timeout=60,
            )
            resp.raise_for_status()
            raw = resp.json().get("message", {}).get("content", "")
            for line in raw.strip().split("\n"):
                line = line.strip()
                m = re.match(r"^(\d+)\.\s*(.+)", line)
                if m:
                    idx = int(m.group(1)) - 1
                    if 0 <= idx < len(batch):
                        out[batch_start + idx] = m.group(2).strip()
        except Exception:
            continue
    return out


def translate_briefing_data(
    bdata: dict,
    translate_batch: TranslateBatch | None = None,
) -> dict:
    """Fill title_zh/summary_zh on English briefing items. Sets translated=True."""
    translate_batch = translate_batch or _default_translate_batch
    texts: list[str] = []
    index_map: list[tuple[int, int, str]] = []
    sources = bdata.get("per_source_data") or []
    for si, src in enumerate(sources):
        for ii, item in enumerate(src.get("items") or []):
            title = item.get("title") or ""
            summary = (item.get("summary") or item.get("description") or "")
            if len(summary) > SUMMARY_MAX:
                summary = summary[:SUMMARY_MAX]
            if needs_translation(title) and not item.get("title_zh"):
                texts.append(title)
                index_map.append((si, ii, "title_zh"))
            if needs_translation(summary) and not item.get("summary_zh"):
                texts.append(summary)
                index_map.append((si, ii, "summary_zh"))

    if not texts:
        bdata["translated"] = True
        return bdata

    translated = translate_batch(texts)
    for i, (si, ii, field) in enumerate(index_map):
        if i < len(translated) and translated[i]:
            bdata["per_source_data"][si]["items"][ii][field] = translated[i]
    bdata["translated"] = True
    return bdata
