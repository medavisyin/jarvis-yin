# Implementation Guide: index_briefing.py

## Overview

This script indexes daily AI briefing content into a vector store shared with other Jarvis RAG indexers. It lives at `scripts/rag/index_briefing.py` (approximately 299 lines). Each run loads the existing persisted store, adds or updates points for one day or for a full backfill, then writes the complete snapshot back to disk.

## Technologies

| Component | Role |
|-----------|------|
| **sentence-transformers** (`SentenceTransformer`, model `all-MiniLM-L6-v2`) | Converts text to 384-dimensional dense vectors. |
| **qdrant-client** (`QdrantClient`) | In-memory vector database; vectors compared with cosine distance. |
| **pypdf** (`PdfReader`) | Extracts text from briefing PDFs. |
| **Standard library** | `json`, `os`, `re`, `sys`, `uuid` for I/O, parsing, IDs, and CLI. |

## Architecture

1. **Client bootstrap** — Creates a Qdrant in-memory client and the `ai_briefings` collection (384-dim, cosine). If `C:/reports/ai/.rag-store.json` exists, existing points are loaded into memory so new briefings merge with prior data.
2. **Per-date ingestion** — For each date folder under `C:/reports/ai/` (e.g. `2026-04-08/`), the script gathers items from three sources (PDF sections, raw Markdown, learning guide).
3. **Chunking** — All textual content is split into chunks bounded by paragraph boundaries with a maximum size (500 characters).
4. **Embedding** — Chunks are encoded with `SentenceTransformer` in offline mode (`HF_HUB_OFFLINE=1` and related env flags) to avoid unintended Hub downloads.
5. **Upsert** — Points use deterministic UUIDs and are upserted in batches of 100.
6. **Persistence** — The full collection is scrolled and written to `.rag-store.json` as the canonical snapshot.

## Key Functions

- **`_get_model()`** — Configures offline Hugging Face behavior and returns the shared embedding model.
- **`_get_client()` / `_load_snapshot()` / `_save_snapshot()`** — Manage Qdrant lifecycle and JSON snapshot I/O.
- **`_extract_pdf_items()`** — Reads `ai-briefing.pdf`, splits on numbered sections using the pattern `\n(?=\d+\.\s)`, and derives a title per section.
- **`_extract_raw_files()`** — Reads all `.md` files under `raw/`, parses frontmatter (title, source URL, difficulty), and chunks each file.
- **`_extract_learning_guide()`** — Treats `learning-guide.md` as a single logical item (with internal chunking as needed).
- **`_chunk_text()`** — Splits on double newlines (`\n\n`) while respecting a 500-character maximum per chunk.
- **Main indexing path** — Embeds chunks, builds `PointStruct` entries with `uuid.uuid5` over a stable key (`date`, title, chunk index), upserts in batches, then saves the snapshot.

## Data Flow

```
Date folder (2026-04-08/)
├── ai-briefing.pdf  ──→ _extract_pdf_items()  ──→ sections by number
├── raw/*.md         ──→ _extract_raw_files()   ──→ chunks by paragraph
└── learning-guide.md ──→ _extract_learning_guide() ──→ single item
                              │
                              ▼
                     _chunk_text() (500 chars)
                              │
                              ▼
                     SentenceTransformer.encode()
                              │
                              ▼
                     Qdrant upsert (batch 100)
                              │
                              ▼
                     _save_snapshot() → .rag-store.json
```

## Configuration

| Constant | Purpose |
|----------|---------|
| `SNAPSHOT_PATH` | `C:/reports/ai/.rag-store.json` — persisted vector store. |
| `COLLECTION` | `ai_briefings` — shared collection name with other indexers. |
| `VECTOR_SIZE` | `384` — must match the embedding model output. |
| `REPORTS_ROOT` | `C:/reports/ai` — root for date folders and backfill discovery. |

Offline embedding behavior is enforced inside `_get_model()` via environment variables.

## Usage

```text
python index_briefing.py C:/reports/ai/2026-04-08    # Index single day
python index_briefing.py --backfill                   # Index all existing briefings
```

Single-day mode expects a folder layout consistent with the daily report structure (PDF, optional `raw/`, optional `learning-guide.md`).

## Design Decisions

- **Deterministic UUIDs** — `uuid5` from a stable string (date, title, chunk index) prevents duplicate points when re-indexing the same content.
- **Offline mode** — Forces local-only model use so runs do not trigger unexpected downloads in locked-down environments.
- **Paragraph-boundary chunking** — Keeps related sentences together better than fixed character windows alone.
- **Rich metadata** — Payloads carry `date`, `source`, `title`, `item_type`, `difficulty`, `url`, and `filename` (and related fields) so retrieval and filtering stay interpretable.
- **In-memory Qdrant + JSON snapshot** — Avoids Windows file-locking issues with on-disk Qdrant while still providing durable storage between runs.
