"""
Memory retrieval for injection into the LLM context.

Two trigger points:
- load_session_context(): Called at session start to prime with relevant memories.
- query_memories_for_context(): Called mid-conversation on ambiguous/low-confidence queries.
"""

import logging
from typing import Optional

from .store import MemoryEntry, MemoryType, search_memories, get_all_memories
from .patterns import find_similar_patterns

logger = logging.getLogger(__name__)

MAX_MEMORY_CONTEXT_CHARS = 1500


def load_session_context(session_id: str = "",
                         recent_query: str = "") -> str:
    """Build a memory context block for session start.

    Retrieves the most relevant memories and formats them as a context
    string to prepend to the system prompt or inject as context.
    """
    if not recent_query:
        all_facts = get_all_memories(memory_type=MemoryType.FACT.value)
        corrections = get_all_memories(memory_type=MemoryType.CORRECTION.value)
        combined = sorted(
            all_facts + corrections,
            key=lambda m: m.timestamp,
            reverse=True,
        )[:5]
    else:
        combined = search_memories(
            query=recent_query,
            top_k=5,
            min_score=0.3,
        )

    if not combined:
        return ""

    return _format_memory_block(combined)


def query_memories_for_context(query: str, include_patterns: bool = True) -> str:
    """Retrieve relevant memories for a specific query.

    Called by the pipeline when RAG confidence is LOW/MEDIUM to augment
    context with past knowledge.
    """
    memories = search_memories(query=query, top_k=5, min_score=0.35)

    pattern_text = ""
    if include_patterns:
        patterns = find_similar_patterns(query, top_k=2, min_score=0.5)
        if patterns:
            pattern_lines = []
            for p in patterns:
                tools_str = ", ".join(p["tools"])
                pattern_lines.append(
                    f"- Previously for similar query, tools [{tools_str}] were used successfully"
                )
            pattern_text = "\n".join(pattern_lines)

    memory_text = _format_memory_block(memories) if memories else ""

    parts = []
    if memory_text:
        parts.append(memory_text)
    if pattern_text:
        parts.append(f"[Past successful patterns]\n{pattern_text}")

    combined = "\n\n".join(parts)
    return combined[:MAX_MEMORY_CONTEXT_CHARS] if combined else ""


def get_tool_suggestions_from_memory(query: str) -> list[str]:
    """Get tool suggestions based on past patterns.

    Used by the pipeline/agent_loop to augment the suggested_tools list.
    """
    patterns = find_similar_patterns(query, top_k=3, min_score=0.5)
    tools: list[str] = []
    seen: set[str] = set()
    for p in patterns:
        for t in p.get("tools", []):
            if t not in seen:
                tools.append(t)
                seen.add(t)
    return tools


def _format_memory_block(memories: list[MemoryEntry]) -> str:
    """Format memory entries into a compact context block."""
    if not memories:
        return ""

    lines = ["[Conversation Memory]"]
    for mem in memories:
        type_label = mem.memory_type.upper()
        lines.append(f"- [{type_label}] {mem.text}")

    return "\n".join(lines)
