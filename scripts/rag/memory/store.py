"""
Qdrant-backed conversation memory store.

Manages the `conversation_memory` collection: CRUD operations, vector search,
and JSON snapshot persistence (load on startup, save on every write).
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

COLLECTION = "conversation_memory"
VECTOR_SIZE = 384

_MEMORY_SNAPSHOT_PATH: str = ""
_qdrant_client = None
_embed_model_fn = None


class MemoryType(str, Enum):
    FACT = "fact"
    CORRECTION = "correction"
    PATTERN = "pattern"
    RETRIEVAL_BOOST = "retrieval_boost"


@dataclass
class MemoryEntry:
    id: str
    text: str
    memory_type: str
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
    """Initialize the memory collection. Call once at startup."""
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
    """Search memories by semantic similarity."""
    if _qdrant_client is None:
        return []

    vector = _get_embedding(query)

    from qdrant_client.models import Filter, FieldCondition, MatchValue
    query_filter = None
    if memory_type:
        query_filter = Filter(must=[
            FieldCondition(key="memory_type", match=MatchValue(value=memory_type))
        ])

    response = _qdrant_client.query_points(
        collection_name=COLLECTION,
        query=vector,
        query_filter=query_filter,
        limit=top_k,
        score_threshold=min_score,
        with_payload=True,
    )

    return [
        MemoryEntry.from_payload(str(hit.id), hit.payload)
        for hit in response.points
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
