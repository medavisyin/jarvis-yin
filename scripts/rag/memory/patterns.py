"""
Q→A pattern recording and similar-query matching.

Records which tools were used for similar queries so Jarvis can suggest
the same approach next time without full re-classification.
"""

import logging
from datetime import datetime
from typing import Optional

from .store import MemoryEntry, MemoryType, add_memory, search_memories

logger = logging.getLogger(__name__)


def record_pattern(query: str, tools_used: list[str],
                   tool_args: dict | None = None,
                   session_id: str = "",
                   success: bool = True) -> Optional[MemoryEntry]:
    """Record a successful Q→tool pattern for future reference.

    Called after a tool call completes successfully.
    """
    if not tools_used or not success:
        return None

    tool_str = ", ".join(tools_used)
    text = f"Query pattern: \"{query[:100]}\" → used tools: [{tool_str}]"
    if tool_args:
        key_args = {k: v for k, v in list(tool_args.items())[:3]
                    if isinstance(v, (str, int, float, bool))}
        if key_args:
            text += f" with args: {key_args}"

    entry = MemoryEntry(
        id="",
        text=text,
        memory_type=MemoryType.PATTERN.value,
        timestamp=datetime.now().isoformat(),
        session_id=session_id,
        confidence=0.7,
        metadata={
            "query": query[:200],
            "tools": tools_used,
            "tool_args": tool_args or {},
            "success": success,
        },
    )
    add_memory(entry)
    return entry


def record_correction(original_intent: str, corrected_intent: str,
                      query: str, session_id: str = "") -> Optional[MemoryEntry]:
    """Record an intent correction for future reference."""
    text = (
        f"Intent correction: \"{query[:80]}\" was misclassified as "
        f"'{original_intent}' but user meant '{corrected_intent}'"
    )

    entry = MemoryEntry(
        id="",
        text=text,
        memory_type=MemoryType.CORRECTION.value,
        timestamp=datetime.now().isoformat(),
        session_id=session_id,
        confidence=0.9,
        metadata={
            "query": query[:200],
            "original_intent": original_intent,
            "corrected_intent": corrected_intent,
        },
    )
    add_memory(entry)
    return entry


def find_similar_patterns(query: str, top_k: int = 3,
                          min_score: float = 0.5) -> list[dict]:
    """Find similar past query patterns.

    Returns tool suggestions based on past successful patterns.
    """
    memories = search_memories(
        query=query,
        top_k=top_k,
        min_score=min_score,
        memory_type=MemoryType.PATTERN.value,
    )

    suggestions = []
    for mem in memories:
        meta = mem.metadata
        if meta.get("tools"):
            suggestions.append({
                "tools": meta["tools"],
                "tool_args": meta.get("tool_args", {}),
                "confidence": mem.confidence,
                "source_query": meta.get("query", ""),
            })

    return suggestions


def record_retrieval_feedback(query: str, helpful_sources: list[str],
                              session_id: str = "") -> Optional[MemoryEntry]:
    """Record which retrieval sources were helpful (from user feedback)."""
    if not helpful_sources:
        return None

    sources_str = ", ".join(helpful_sources[:5])
    text = f"Retrieval boost: for \"{query[:80]}\" these sources were helpful: [{sources_str}]"

    entry = MemoryEntry(
        id="",
        text=text,
        memory_type=MemoryType.RETRIEVAL_BOOST.value,
        timestamp=datetime.now().isoformat(),
        session_id=session_id,
        confidence=0.75,
        metadata={
            "query": query[:200],
            "helpful_sources": helpful_sources,
        },
    )
    add_memory(entry)
    return entry
