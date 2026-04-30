"""Conversation memory package — persistent fact store with pattern learning."""

from .store import (
    MemoryEntry,
    MemoryType,
    init_memory_store,
    add_memory,
    search_memories,
    delete_memory,
    get_all_memories,
    save_snapshot,
)
from .extractor import extract_immediate, extract_batch, is_correction_or_preference
from .patterns import (
    record_pattern,
    record_correction,
    find_similar_patterns,
    record_retrieval_feedback,
)
from .retriever import (
    load_session_context,
    query_memories_for_context,
    get_tool_suggestions_from_memory,
)

__all__ = [
    "MemoryEntry", "MemoryType",
    "init_memory_store", "add_memory", "search_memories",
    "delete_memory", "get_all_memories", "save_snapshot",
    "extract_immediate", "extract_batch", "is_correction_or_preference",
    "record_pattern", "record_correction",
    "find_similar_patterns", "record_retrieval_feedback",
    "load_session_context", "query_memories_for_context",
    "get_tool_suggestions_from_memory",
]
