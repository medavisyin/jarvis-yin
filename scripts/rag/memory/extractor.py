"""
LLM-based fact extraction from conversations.

Two modes:
- extract_immediate(): Detects corrections/preferences in real-time.
- extract_batch(): Processes a full conversation post-session for general facts.
"""

import json
import logging
import re
from datetime import datetime
from typing import Optional

import requests

from .store import MemoryEntry, MemoryType, add_memory

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL_FAST = "qwen3:1.7b"

_CORRECTION_SIGNALS = [
    r"\bno[,.]?\s+(?:i\s+mean|that'?s?\s+not|not\s+what)",
    r"\bactually[,.]?\s+(?:i\s+meant|it'?s|what\s+i)",
    r"\bi\s+(?:prefer|want|need|like)\b",
    r"\bdon'?t\s+(?:call|use|do|show)\b",
    r"\bnot\s+(?:that|this|what)\b.*\bbut\b",
    r"\bremember\s+(?:that|this|:)",
    r"\bfrom\s+now\s+on\b",
]
_CORRECTION_RE = re.compile("|".join(_CORRECTION_SIGNALS), re.IGNORECASE)


def is_correction_or_preference(user_msg: str) -> bool:
    """Quick heuristic: does this message contain a correction or preference signal?"""
    return bool(_CORRECTION_RE.search(user_msg))


def extract_immediate(user_msg: str, assistant_msg: str,
                      session_id: str = "") -> Optional[MemoryEntry]:
    """Extract an immediate memory (correction/preference) from the current turn.

    Only triggers if the user message contains correction/preference signals.
    Returns the stored MemoryEntry or None if nothing worth remembering.
    """
    if not is_correction_or_preference(user_msg):
        return None

    prompt = (
        "Extract the key correction or preference from this exchange. "
        "Output a single short factual sentence (max 30 words) that captures "
        "what should be remembered for future conversations. "
        "If there is no meaningful correction or preference, output exactly: NONE\n\n"
        f"User: {user_msg}\n"
        f"Assistant: {assistant_msg[:300]}\n\n"
        "Extracted memory:"
    )

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL_FAST,
                "messages": [
                    {"role": "system", "content": "You extract factual memories from conversations. Be concise."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "think": False,
                "options": {"num_predict": 80, "temperature": 0.2},
            },
            timeout=60,
        )
        if resp.status_code != 200:
            return None
        text = resp.json().get("message", {}).get("content", "").strip()
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if not text or text.upper() == "NONE" or len(text) < 5:
            return None
    except Exception as e:
        logger.warning("Immediate extraction failed: %s", e)
        return None

    entry = MemoryEntry(
        id="",
        text=text,
        memory_type=MemoryType.CORRECTION.value,
        timestamp=datetime.now().isoformat(),
        session_id=session_id,
        confidence=0.85,
        metadata={"source_user_msg": user_msg[:200]},
    )
    add_memory(entry)
    return entry


def extract_batch(conversation: list[dict], session_id: str = "") -> list[MemoryEntry]:
    """Extract factual knowledge from a full conversation.

    Called post-session. Identifies reusable facts, not ephemeral exchanges.
    """
    if len(conversation) < 4:
        return []

    transcript_lines = []
    for msg in conversation[-30:]:
        role = msg.get("role", "?").upper()
        content = (msg.get("content", "") or "")[:300]
        if content.strip():
            transcript_lines.append(f"{role}: {content}")
    transcript = "\n".join(transcript_lines)

    prompt = (
        "Extract important FACTUAL information from this conversation that would be "
        "useful to remember in future conversations. Focus on:\n"
        "- Facts about the user (role, projects, team, preferences)\n"
        "- Technical decisions made\n"
        "- Specific knowledge that was clarified or corrected\n"
        "- Recurring patterns or needs\n\n"
        "Output a JSON array of objects with 'text' (the fact) and 'confidence' (0.0-1.0).\n"
        "Only include truly reusable facts, not session-specific chatter.\n"
        "If nothing worth remembering, output: []\n\n"
        f"Conversation:\n{transcript}\n\n"
        "Facts JSON:"
    )

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL_FAST,
                "messages": [
                    {"role": "system", "content": "You extract factual knowledge from conversations. Output valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "think": False,
                "options": {"num_predict": 500, "temperature": 0.3, "num_ctx": 8192},
            },
            timeout=90,
        )
        if resp.status_code != 200:
            return []
        raw = resp.json().get("message", {}).get("content", "").strip()
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if json_match:
            raw = json_match.group(1).strip()
        facts = json.loads(raw)
        if not isinstance(facts, list):
            return []
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Batch extraction failed: %s", e)
        return []

    entries = []
    for fact in facts[:10]:
        text = fact.get("text", "").strip()
        confidence = float(fact.get("confidence", 0.7))
        if not text or len(text) < 10 or confidence < 0.5:
            continue

        entry = MemoryEntry(
            id="",
            text=text,
            memory_type=MemoryType.FACT.value,
            timestamp=datetime.now().isoformat(),
            session_id=session_id,
            confidence=confidence,
            metadata={},
        )
        add_memory(entry)
        entries.append(entry)

    logger.info("Batch extraction: stored %d facts from session %s", len(entries), session_id[:8])
    return entries
