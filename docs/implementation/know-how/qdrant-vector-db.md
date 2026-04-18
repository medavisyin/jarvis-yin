# Know-How: Qdrant Vector Database

A beginner-friendly overview of **vector databases**, **Qdrant**, and how **Jarvis** stores and searches embeddings.

## What is a vector database?

A **vector database** is optimized for **nearest-neighbor search** in high-dimensional space.

- Instead of classic SQL filters like `WHERE column = 'value'`, you often ask: **“Which stored vectors are closest to this query vector?”**
- Common uses: **semantic search**, **recommendations**, **image similarity**, RAG retrieval.

```text
Query vector  ----compare---->  [stored vector 1]
                    |           [stored vector 2]
                    |           [stored vector 3]
                    v           ...
                "Top K nearest"
```

## What is Qdrant?

**Qdrant** is an **open-source** vector database, implemented in **Rust**, designed for:

- Fast similarity search
- **Payloads** (metadata attached to each vector)
- **Filtering** (e.g. only search items where `source == "arxiv"`)
- Configurable **distance metrics** (cosine, dot product, Euclidean, etc.)

You can run Qdrant as a **server** or use **embedded / in-memory** clients depending on your integration.

Official site and docs:

- [Qdrant documentation](https://qdrant.tech/documentation/)
- [Qdrant Python client](https://github.com/qdrant/qdrant-client)

## How Jarvis uses Qdrant

- **Mode:** **In-memory** — no separate Qdrant server process required for the default Jarvis setup.
- **Client:** Created with `QdrantClient(":memory:")`.
- **Collection:** A single collection named **`ai_briefings`**, using **cosine** distance and **384** dimensions (matching the embedding model).
- **Each point:** A **vector** (384 floats) plus a **payload** with fields such as **title**, **text**, **date**, **source**, **item_type**, and related metadata.
- **Persistence (snapshot pattern):** A JSON snapshot at **`C:/reports/ai/.rag-store.json`**
  - **On startup:** Load all points from JSON into the in-memory collection.
  - **After indexing:** Save all points back to JSON.
  - **Why:** Avoids **Windows file-locking** friction that can appear with Qdrant’s native on-disk storage in some local setups, while keeping deployment simple.

## Key operations

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

client = QdrantClient(":memory:")
client.create_collection(
    "ai_briefings",
    VectorParams(size=384, distance=Distance.COSINE),
)

client.upsert(
    "ai_briefings",
    [
        PointStruct(
            id="uuid",
            vector=[0.0] * 384,
            payload={"title": "..."},
        )
    ],
)

results = client.search(
    "ai_briefings",
    query_vector=[0.0] * 384,
    limit=5,
)

results = client.search(
    "ai_briefings",
    query_vector=[0.0] * 384,
    limit=5,
    query_filter=Filter(
        must=[FieldCondition(key="source", match=MatchValue(value="arxiv"))]
    ),
)

points, next_offset = client.scroll(
    "ai_briefings",
    limit=500,
    with_payload=True,
    with_vectors=True,
)
```

Replace `[0.0] * 384` with a real embedding from Sentence Transformers in production code.

## The snapshot pattern (JSON load/save)

```text
┌─────────────────┐     load      ┌──────────────────┐
│ .rag-store.json │ ─────────────>│ Qdrant :memory:  │
└─────────────────┘               └──────────────────┘
        ^                                  │
        │              save                │
        └──────────────────────────────────┘
```

- **Pros:** Simple deployment, predictable backup (one file), fewer moving parts on Windows.
- **Cons:** Full dataset must be **loaded into RAM**; save/load cost grows with collection size.

## Performance characteristics (Jarvis-oriented)

Order-of-magnitude figures for the current Jarvis dataset (your machine may vary):

- **~18,500 vectors** load from JSON in **under ~2 seconds**.
- **Search** across the full in-memory set on the order of **~35ms** (plus embedding time for the query).

Memory: rough **~150MB** for the current dataset (vectors + payloads + overhead)—treat this as an estimate, not a guarantee.

## Why in-memory + JSON instead of a Qdrant server?

- **Simpler deployment:** No Docker, no extra service to manage.
- **Fewer Windows file-lock surprises** compared to some native on-disk paths in local dev.
- **Fast enough** for Jarvis’s current scale.
- **Trade-off:** The **entire** vector set must fit in **RAM**; very large corpora may need a different architecture.

## When to upgrade to server mode

Consider a **dedicated Qdrant server** (or another production-grade vector DB) when:

- Your vector count or dimensionality makes **RAM** usage uncomfortable on one machine.
- You need **concurrent** writers, **high availability**, or **horizontal scaling**.
- You want **native** Qdrant persistence features without custom JSON snapshots.
- Multiple apps must share one vector store over the network.

## Installation

```bash
pip install qdrant-client
```

## Further reading

- [Qdrant documentation](https://qdrant.tech/documentation/)
- [Qdrant filtering](https://qdrant.tech/documentation/concepts/filtering/)
- [Python client Quickstart](https://qdrant.tech/documentation/quick-start/)
