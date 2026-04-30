# Enhanced Conversation Memory — Implementation Plan

**Status:** COMPLETED (2026-04-30) — The `scripts/rag/memory/` package (store, extractor, patterns, retriever), Qdrant `conversation_memory` collection with JSON snapshot, LLM extraction (immediate for corrections/preferences, batch for general facts), pattern learning (Q→A mappings, corrections, retrieval feedback), pipeline injection on LOW/MEDIUM retrieval confidence, and API routes GET/DELETE `/api/memory` plus POST `/api/memory/extract` are implemented and wired through `pipeline.py`, `agent_loop.py`, startup init, and `config`. Tasks 1–10 in this document describe the shipped design; Task 11 (updates to `docs/implementation/usage-tool/rag-agent-impl.md`) is optional documentation only.

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Build a persistent, searchable conversation memory system that extracts facts from conversations, learns from Q→A patterns, tracks corrections, and injects relevant memories at session start and on ambiguous queries.

**Architecture:** A `memory/` package under `scripts/rag/` with four modules: `store.py` (Qdrant collection CRUD + JSON persistence), `extractor.py` (LLM-based fact extraction — immediate for corrections, batch for general facts), `patterns.py` (Q→A pattern recording + similar-query matching), and `retriever.py` (memory retrieval at session start + on-demand). Single-user, single global memory store.

**Tech Stack:** Qdrant in-memory (separate `conversation_memory` collection), sentence-transformers `all-MiniLM-L6-v2` (shared with existing RAG), Ollama `qwen3:1.7b` for extraction, JSON file persistence at `C:/reports/ai/.conversation-memory.json`.

---

## Task 1: Memory Store (`memory/store.py`)

**Files:**
- Create: `scripts/rag/memory/__init__.py`
- Create: `scripts/rag/memory/store.py`

**Step 1: Create the memory package**

Create `scripts/rag/memory/__init__.py`:

```python
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

__all__ = [
    "MemoryEntry",
    "MemoryType",
    "init_memory_store",
    "add_memory",
    "search_memories",
    "delete_memory",
    "get_all_memories",
    "save_snapshot",
]
```

**Step 2: Implement the store module**

Create `scripts/rag/memory/store.py`:

```python
"""
Qdrant-backed conversation memory store.

Manages the `conversation_memory` collection: CRUD operations, vector search,
and JSON snapshot persistence (load on startup, save on every write).
"""

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

COLLECTION = "conversation_memory"
VECTOR_SIZE = 384

# Persistence path (alongside the RAG snapshot)
_MEMORY_SNAPSHOT_PATH: str = ""
_qdrant_client = None
_embed_model_fn = None  # Lazy reference to rag_engine.get_embed_model


class MemoryType(str, Enum):
    FACT = "fact"
    CORRECTION = "correction"
    PATTERN = "pattern"
    RETRIEVAL_BOOST = "retrieval_boost"


@dataclass
class MemoryEntry:
    id: str
    text: str
    memory_type: str  # MemoryType value
    timestamp: str
    session_id: str = ""
    confidence: float = 0.8
    metadata: dict = field(default_factory=dict)

    def to_payload(self) -> dict:
        return {
            "text": self.text,
            "memory_type": self.memory_type,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }

    @classmethod
    def from_payload(cls, point_id: str, payload: dict) -> "MemoryEntry":
        return cls(
            id=point_id,
            text=payload.get("text", ""),
            memory_type=payload.get("memory_type", MemoryType.FACT.value),
            timestamp=payload.get("timestamp", ""),
            session_id=payload.get("session_id", ""),
            confidence=payload.get("confidence", 0.8),
            metadata=payload.get("metadata", {}),
        )


def init_memory_store(snapshot_path: str, embed_model_fn=None):
    """Initialize the memory collection. Call once at startup.

    Args:
        snapshot_path: Path to JSON snapshot file for persistence.
        embed_model_fn: Callable that returns the SentenceTransformer model.
    """
    global _MEMORY_SNAPSHOT_PATH, _qdrant_client, _embed_model_fn

    _MEMORY_SNAPSHOT_PATH = snapshot_path
    _embed_model_fn = embed_model_fn

    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance, VectorParams, PointStruct,
        HnswConfigDiff, OptimizersConfigDiff,
    )

    _qdrant_client = QdrantClient(":memory:")
    _qdrant_client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
        optimizers_config=OptimizersConfigDiff(indexing_threshold=0),
    )

    # Load from snapshot if exists
    if os.path.exists(snapshot_path):
        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            points = data.get("points", [])
            batch_size = 200
            for i in range(0, len(points), batch_size):
                batch = [
                    PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
                    for p in points[i:i + batch_size]
                ]
                _qdrant_client.upsert(collection_name=COLLECTION, points=batch)
            logger.info("Memory store: loaded %d memories from snapshot", len(points))
        except Exception as e:
            logger.warning("Memory store: failed to load snapshot: %s", e)


def _get_embedding(text: str) -> list[float]:
    """Get embedding vector for text using the shared model."""
    if _embed_model_fn is None:
        from rag_engine import get_embed_model
        model = get_embed_model()
    else:
        model = _embed_model_fn()
    return model.encode(text, normalize_embeddings=True).tolist()


def add_memory(entry: MemoryEntry) -> str:
    """Add a memory entry to the collection. Returns the ID."""
    from qdrant_client.models import PointStruct

    if not entry.id:
        entry.id = str(uuid.uuid4())

    vector = _get_embedding(entry.text)
    point = PointStruct(id=entry.id, vector=vector, payload=entry.to_payload())
    _qdrant_client.upsert(collection_name=COLLECTION, points=[point])

    save_snapshot()
    logger.info("Memory added: [%s] %s", entry.memory_type, entry.text[:60])
    return entry.id


def search_memories(query: str, top_k: int = 5, min_score: float = 0.3,
                    memory_type: Optional[str] = None) -> list[MemoryEntry]:
    """Search memories by semantic similarity.

    Args:
        query: Search query text.
        top_k: Max results to return.
        min_score: Minimum cosine similarity threshold.
        memory_type: Optional filter by MemoryType value.

    Returns:
        List of MemoryEntry sorted by relevance.
    """
    if _qdrant_client is None:
        return []

    vector = _get_embedding(query)

    from qdrant_client.models import Filter, FieldCondition, MatchValue
    query_filter = None
    if memory_type:
        query_filter = Filter(must=[
            FieldCondition(key="memory_type", match=MatchValue(value=memory_type))
        ])

    results = _qdrant_client.search(
        collection_name=COLLECTION,
        query_vector=vector,
        query_filter=query_filter,
        limit=top_k,
        score_threshold=min_score,
    )

    return [
        MemoryEntry.from_payload(str(hit.id), hit.payload)
        for hit in results
    ]


def delete_memory(memory_id: str) -> bool:
    """Delete a memory entry by ID."""
    if _qdrant_client is None:
        return False
    try:
        from qdrant_client.models import PointIdsList
        _qdrant_client.delete(
            collection_name=COLLECTION,
            points_selector=PointIdsList(points=[memory_id]),
        )
        save_snapshot()
        return True
    except Exception as e:
        logger.warning("Failed to delete memory %s: %s", memory_id, e)
        return False


def get_all_memories(memory_type: Optional[str] = None) -> list[MemoryEntry]:
    """Get all stored memories, optionally filtered by type."""
    if _qdrant_client is None:
        return []

    from qdrant_client.models import Filter, FieldCondition, MatchValue
    query_filter = None
    if memory_type:
        query_filter = Filter(must=[
            FieldCondition(key="memory_type", match=MatchValue(value=memory_type))
        ])

    results = _qdrant_client.scroll(
        collection_name=COLLECTION,
        scroll_filter=query_filter,
        limit=1000,
    )
    points = results[0] if results else []
    return [
        MemoryEntry.from_payload(str(p.id), p.payload)
        for p in points
    ]


def save_snapshot():
    """Persist all memories to JSON snapshot file."""
    if not _MEMORY_SNAPSHOT_PATH or _qdrant_client is None:
        return

    results = _qdrant_client.scroll(
        collection_name=COLLECTION,
        limit=10000,
        with_vectors=True,
    )
    points = results[0] if results else []

    snapshot_data = {
        "collection": COLLECTION,
        "saved_at": datetime.now().isoformat(),
        "count": len(points),
        "points": [
            {
                "id": str(p.id),
                "vector": p.vector,
                "payload": p.payload,
            }
            for p in points
        ],
    }

    os.makedirs(os.path.dirname(_MEMORY_SNAPSHOT_PATH), exist_ok=True)
    with open(_MEMORY_SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, ensure_ascii=False, indent=1)
    logger.debug("Memory snapshot saved: %d entries", len(points))
```

**Step 3: Verify syntax**

Run: `python -c "import sys; sys.path.insert(0,'..'); exec(open('memory/store.py').read()); print('OK')"`
Working directory: `scripts/rag`
Expected: `OK` (no syntax errors)

---

## Task 2: Fact Extractor (`memory/extractor.py`)

**Files:**
- Create: `scripts/rag/memory/extractor.py`

**Step 1: Implement the extractor**

```python
"""
LLM-based fact extraction from conversations.

Two modes:
- extract_immediate(): Detects corrections/preferences in real-time (low latency).
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

    Called after each assistant response. Only triggers if the user message
    contains correction/preference signals.

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
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        text = resp.json().get("message", {}).get("content", "").strip()
        # Remove thinking tags if present
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

    Args:
        conversation: List of {"role": ..., "content": ...} messages.
        session_id: Session identifier.

    Returns:
        List of newly created MemoryEntry objects.
    """
    if len(conversation) < 4:
        return []

    # Build a condensed transcript
    transcript_lines = []
    for msg in conversation[-30:]:  # Last 30 messages max
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
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        raw = resp.json().get("message", {}).get("content", "").strip()
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        # Extract JSON from markdown code block if present
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
    for fact in facts[:10]:  # Cap at 10 facts per session
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
```

**Step 2: Verify syntax**

Run: `python -c "import sys; sys.path.insert(0,'..'); sys.path.insert(0,'.'); from memory.extractor import is_correction_or_preference; print('OK:', is_correction_or_preference('no, I mean git push'))"`
Expected: `OK: True`

---

## Task 3: Pattern Learning (`memory/patterns.py`)

**Files:**
- Create: `scripts/rag/memory/patterns.py`

**Step 1: Implement pattern recording and matching**

```python
"""
Q→A pattern recording and similar-query matching.

Records which tools were used (and how) for similar queries, so Jarvis can
suggest the same approach next time without re-classifying.
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

    Called after a tool call completes successfully. Stores the query-tool
    mapping so similar future queries can reuse the same approach.

    Args:
        query: The user's original query.
        tools_used: List of tool names that were called.
        tool_args: Optional dict of key arguments (for recall).
        session_id: Session identifier.
        success: Whether the tool call was successful.

    Returns:
        The stored MemoryEntry, or None if not worth recording.
    """
    if not tools_used or not success:
        return None

    # Build a concise pattern description
    tool_str = ", ".join(tools_used)
    text = f"Query pattern: \"{query[:100]}\" → used tools: [{tool_str}]"
    if tool_args:
        # Only include key arguments, not full payloads
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
    """Record an intent correction for future reference.

    Called when the user corrects Jarvis's misunderstanding.

    Args:
        original_intent: What Jarvis initially classified as.
        corrected_intent: What the user actually meant.
        query: The query that was misclassified.
        session_id: Session identifier.
    """
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

    Args:
        query: Current user query.
        top_k: Max patterns to return.
        min_score: Minimum similarity threshold (higher than general search).

    Returns:
        List of dicts with 'tools', 'tool_args', 'confidence' keys.
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
    """Record which retrieval sources were helpful (from user feedback).

    Called on thumbs-up feedback to boost future similar queries.
    """
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
```

**Step 2: Verify syntax**

Run: `python -c "import sys; sys.path.insert(0,'..'); sys.path.insert(0,'.'); from memory.patterns import find_similar_patterns; print('OK')"`
Expected: `OK`

---

## Task 4: Memory Retriever (`memory/retriever.py`)

**Files:**
- Create: `scripts/rag/memory/retriever.py`

**Step 1: Implement retrieval logic**

```python
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

    Args:
        session_id: Current session ID (for session-specific memories).
        recent_query: The first query of the session (for relevance).

    Returns:
        Formatted memory context string, or empty string if no relevant memories.
    """
    if not recent_query:
        # No query yet — return top facts by recency
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

    Args:
        query: The current user query.
        include_patterns: Whether to also search for similar Q→A patterns.

    Returns:
        Formatted memory context string.
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

    Returns:
        List of tool names suggested by past patterns.
    """
    patterns = find_similar_patterns(query, top_k=3, min_score=0.5)
    tools = []
    seen = set()
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
```

**Step 2: Verify syntax**

Run: `python -c "import sys; sys.path.insert(0,'..'); sys.path.insert(0,'.'); from memory.retriever import load_session_context; print('OK')"`
Expected: `OK`

---

## Task 5: Wire into Pipeline (`pipeline.py`)

**Files:**
- Modify: `scripts/rag/pipeline.py`

**Step 1: Add memory retrieval to the pipeline**

Add import at top of `pipeline.py`:

```python
from memory.retriever import query_memories_for_context, get_tool_suggestions_from_memory
```

Modify `handle_query()` — after the intent classification (Step 2) and before decomposition (Step 4), add memory augmentation:

```python
    # Step 2b: Augment with conversation memory on low/medium confidence
    memory_context = ""
    memory_tools: list[str] = []
    if intent_result.rag_confidence in (
        RetrievalConfidence.LOW.value, RetrievalConfidence.MEDIUM.value
    ):
        memory_context = query_memories_for_context(effective_query)
        memory_tools = get_tool_suggestions_from_memory(effective_query)
```

Add `memory_context` to the effective query if available:

```python
    # After building effective_query, prepend memory context
    if memory_context:
        effective_query = f"{memory_context}\n\n{effective_query}"
```

Add `memory_tools` to `all_suggested_tools` in `PipelineContext`:

Update the `all_suggested_tools` property in `PipelineContext`:

```python
    @property
    def all_suggested_tools(self) -> list[str]:
        """All tools suggested across decomposed sub-queries, intent, and memory."""
        tools = []
        if self.is_decomposed:
            tools = get_sub_query_tools(self.decomposition)
        else:
            tools = list(self.intent_result.suggested_tools)
        # Augment with memory-based tool suggestions
        tools.extend(t for t in self.memory_tools if t not in tools)
        return tools
```

Add `memory_tools: list[str] = field(default_factory=list)` to the `PipelineContext` dataclass.

---

## Task 6: Wire into Agent Loop (Pattern Recording)

**Files:**
- Modify: `scripts/rag/agent_loop.py`

**Step 1: Record patterns after successful tool calls**

After a tool call succeeds in `run_agent()`, record the pattern. Add at top:

```python
from memory.patterns import record_pattern as _record_pattern
```

In the tool execution section of `run_agent()`, after `_execute_tool` returns successfully, add:

```python
    # Record pattern for learning
    try:
        _record_pattern(
            query=user_query,
            tools_used=[tool_name],
            tool_args=tool_args,
            session_id="",
        )
    except Exception:
        pass  # Non-critical, don't break the flow
```

---

## Task 7: Wire Immediate Extraction in `api_agent()`

**Files:**
- Modify: `scripts/rag/agent.py` (minimal change)

**Step 1: Add immediate extraction after response**

In the `api_agent()` function's non-learning `generate()`, after the SSE stream completes, trigger immediate extraction in a background thread:

Add import:
```python
from memory.extractor import extract_immediate as _extract_immediate_memory
```

At the end of the `generate()` function for non-learning path, after yielding `[DONE]`:
```python
    # Fire-and-forget immediate memory extraction
    import threading
    def _bg_extract():
        try:
            # Get the last user/assistant messages from the accumulated stream
            _extract_immediate_memory(query, "", session_id)
        except Exception:
            pass
    threading.Thread(target=_bg_extract, daemon=True).start()
```

---

## Task 8: Memory API Routes

**Files:**
- Modify: `scripts/rag/agent.py` (add 3 routes, ~60 lines)

**Step 1: Add memory management routes**

```python
@app.route("/api/memory", methods=["GET"])
def api_memory_list():
    """List all stored memories, optionally filtered by type."""
    from memory.store import get_all_memories, MemoryType
    mem_type = request.args.get("type")
    memories = get_all_memories(memory_type=mem_type)
    return jsonify({
        "count": len(memories),
        "memories": [
            {
                "id": m.id,
                "text": m.text,
                "type": m.memory_type,
                "timestamp": m.timestamp,
                "confidence": m.confidence,
            }
            for m in memories
        ],
    })


@app.route("/api/memory/<memory_id>", methods=["DELETE"])
def api_memory_delete(memory_id):
    """Delete a specific memory by ID."""
    from memory.store import delete_memory
    success = delete_memory(memory_id)
    if success:
        return jsonify({"status": "deleted"})
    return jsonify({"error": "Memory not found"}), 404


@app.route("/api/memory/extract", methods=["POST"])
def api_memory_extract_batch():
    """Trigger batch fact extraction from a session's conversation history."""
    from memory.extractor import extract_batch
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "")
    conversation = data.get("conversation", [])
    if not conversation:
        # Try to load from session file
        session_data = _load_session_file(session_id) if session_id else None
        if session_data:
            conversation = session_data.get("messages", [])
    if not conversation:
        return jsonify({"error": "No conversation data"}), 400

    entries = extract_batch(conversation, session_id=session_id)
    return jsonify({
        "extracted": len(entries),
        "facts": [{"text": e.text, "confidence": e.confidence} for e in entries],
    })
```

---

## Task 9: Initialize Memory Store at Startup

**Files:**
- Modify: `scripts/rag/agent.py` (add ~5 lines at startup)
- Modify: `scripts/config.py` (add 1 path constant)

**Step 1: Add config path**

In `scripts/config.py`, add:
```python
MEMORY_SNAPSHOT_PATH = os.path.join(REPORTS_ROOT, ".conversation-memory.json")
```

**Step 2: Initialize at startup in `agent.py`**

Near the existing initialization code (where `agent_loop.init()` is called), add:

```python
from memory.store import init_memory_store
from config import MEMORY_SNAPSHOT_PATH
from rag_engine import get_embed_model

init_memory_store(
    snapshot_path=MEMORY_SNAPSHOT_PATH,
    embed_model_fn=get_embed_model,
)
```

---

## Task 10: Update `memory/__init__.py` with Full Exports

**Files:**
- Modify: `scripts/rag/memory/__init__.py`

Update to export all public APIs:

```python
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
```

---

## Task 11: Update Documentation

**Files:**
- Modify: `docs/implementation/usage-tool/rag-agent-impl.md`

Add a new section documenting the memory system:
- Module structure update (add `memory/` package)
- Architecture diagram update (add memory retrieval path)
- Data flow update (describe extraction + retrieval triggers)

---

## Summary of Changes

| Module | Lines | Purpose |
|--------|-------|---------|
| `memory/__init__.py` | ~35 | Package exports |
| `memory/store.py` | ~200 | Qdrant collection CRUD + JSON persistence |
| `memory/extractor.py` | ~160 | LLM fact extraction (immediate + batch) |
| `memory/patterns.py` | ~140 | Q→A pattern recording + matching |
| `memory/retriever.py` | ~110 | Memory retrieval (session + on-demand) |
| `pipeline.py` changes | ~15 | Memory augmentation on low confidence |
| `agent_loop.py` changes | ~10 | Pattern recording after tool calls |
| `agent.py` changes | ~80 | Routes + startup init + immediate extraction |
| `config.py` changes | ~1 | MEMORY_SNAPSHOT_PATH constant |

**Total new code:** ~750 lines across 4 new files + ~100 lines of modifications.
