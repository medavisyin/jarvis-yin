# Implementation Guide: index_custom.py

## Overview

This script indexes personal knowledge files (Markdown and PDF) from a dedicated knowledge tree into the shared RAG vector store. It lives at `scripts/rag/index_custom.py` (approximately 451 lines). Content is labeled with subfolder-based `source` values (e.g. `knowledge/books`, `knowledge/notes`) and folder-derived types so it can be searched alongside briefings, code, and wiki chunks.

## Technologies

| Component | Role |
|-----------|------|
| **sentence-transformers** | Same `all-MiniLM-L6-v2` model and offline configuration as sibling indexers. |
| **qdrant-client** | In-memory Qdrant, cosine distance, shared `ai_briefings` collection and JSON snapshot. |
| **pypdf** | `PdfReader` for text extraction from PDFs. |
| **PyYAML** (optional) | Preferred path for parsing YAML frontmatter in Markdown; a minimal fallback parser runs if `yaml` is not importable. |

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────────┐
│  ENTRY POINTS                                                           │
│  • CLI: index_custom.main() → add │ scan │ list │ remove               │
│  • search_ui.py: POST /api/refresh-knowledge → daemon thread →          │
│    _run_refresh_knowledge → index_custom.index_file per .md/.markdown/.txt/.pdf │
│      under KNOWLEDGE_ROOT                                               │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LOAD / MUTATE SNAPSHOT                                                  │
│  _get_client() loads .rag-store.json into in-memory Qdrant               │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PER FILE                                                               │
│  .md → _parse_frontmatter → body → _chunk_by_sections (+ _chunk_text)    │
│  .pdf → PdfReader pages → text → section chunking (_extract_pdf_sections)│
│  _infer_item_type / _infer_source from path under KNOWLEDGE_ROOT          │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  OUTPUT                                                                 │
│  MiniLM embed → deterministic UUID upserts → _save_snapshot              │
└─────────────────────────────────────────────────────────────────────────┘
```

1. **CLI dispatch** — Subcommands route to add, scan, list, or remove flows.
2. **Snapshot** — Load existing `.rag-store.json`, mutate collection, save full snapshot (consistent with other scripts).
3. **Markdown path** — Read file → optional frontmatter split → body chunked by headings then paragraphs → metadata merged from frontmatter and path inference.
4. **PDF path** — Extract full text per page → infer type from path → section-aware chunking similar to Markdown bodies.
5. **Indexing** — Embed chunks, assign deterministic IDs, upsert, persist.

## Key Functions

- **`_chunk_text()`** — Paragraph-based splitting with a maximum character length (default 500).
- **`_chunk_by_sections()`** — Splits Markdown (or PDF text) on heading boundaries using `\n(?=#{1,3}\s)`; oversized sections are further split with `_chunk_text`.
- **`_parse_frontmatter()`** — If the file starts with `---`, parses YAML between delimiters and returns `(meta_dict, body)`. Falls back to simple line parsing when PyYAML is unavailable.
- **`_infer_item_type()`** — Maps the first path segment under `KNOWLEDGE_ROOT` to an `item_type` via `FOLDER_TYPE_MAP` (`books` → `book_chapter`, `projects` → `project_doc`, `notes` → `personal_note`, `tasks` → `task`); unknown locations default to `personal_note`.
- **`_infer_source()`** — Derives a descriptive `source` label from the subfolder path: `knowledge/books`, `knowledge/notes`, `knowledge/projects`, `knowledge/tasks`, or `knowledge` for files directly under the root. Replaces the former generic `custom` label.
- **`_extract_pdf_sections()`** — Concatenates page text, builds chunks with `_chunk_by_sections`, derives per-chunk titles from headings or “Chapter N” patterns when present.
- **`_extract_markdown()`** — Combines frontmatter fields (title, tags, difficulty, etc.) with inferred type and default difficulty per type.

Remove/list flows filter or display points by payload patterns (e.g. title or source) as implemented in the script.

## CLI Commands

| Command | Purpose |
|---------|---------|
| `python index_custom.py add <file-or-folder>` | Index one file or all eligible files under a folder. |
| `python index_custom.py scan` | Index everything under the configured `knowledge/` root. |
| `python index_custom.py list` | Show summaries of indexed custom content. |
| `python index_custom.py remove <pattern>` | Remove indexed points matching a title (or pattern) as defined in the script. |

## Frontmatter Format

Markdown files may start with YAML between `---` lines, for example:

```yaml
---
title: My Custom Title
tags: [architecture, medavis]
difficulty: intermediate
category: internal-notes
---
```

The implementation copies `title`, `tags`, `difficulty`, and `url` from frontmatter into each chunk’s metadata; optional keys like `category` are parsed but are not added to the payload unless the script is extended to pass them through. If PyYAML is not installed, a lightweight parser still extracts simple `key: value` lines and basic list syntax.

**Organization by folder** — Under `C:/reports/ai/knowledge/`, subfolders such as `books/`, `projects/`, `notes/`, and `tasks/` drive `item_type` via `FOLDER_TYPE_MAP` and default difficulty presets (`DEFAULT_DIFFICULTY`).

## Configuration

| Constant | Purpose |
|----------|---------|
| `KNOWLEDGE_ROOT` | `C:/reports/ai/knowledge` — root for `scan` and relative type inference. |
| `SNAPSHOT_PATH` | `C:/reports/ai/.rag-store.json` |
| `COLLECTION` / `VECTOR_SIZE` | Same as other RAG indexers (`ai_briefings`, 384). |

## Design Decisions

- **Heading-first chunking** — `_chunk_by_sections` keeps sections aligned with Markdown structure (and PDF text that mirrors headings) for better semantic retrieval than blind paragraph cuts alone.
- **Folder-based types** — Encourages a predictable layout; `item_type` and default difficulty stay consistent without manual tagging in every file.
- **Optional PyYAML** — Keeps installs minimal when users only need simple frontmatter; full YAML when available.
- **Unified collection** — Knowledge notes live in the same store as briefings and code so a single query interface can rank across all sources (filtering by `source` or `item_type` in application code).
- **Subfolder-based source labels** — Source is `knowledge/<subfolder>` (e.g. `knowledge/books`, `knowledge/notes`) rather than a generic `custom`, making the Chunk Analysis "By Source" chart meaningful and distinguishing book content from personal notes at a glance.
