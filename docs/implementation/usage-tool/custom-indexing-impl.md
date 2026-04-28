---
tags:
  - implementation
  - usage-tool
  - custom-indexing
category: usage-tool
status: current
last-updated: 2026-04-28
---

# Custom File Indexing (`index_custom.py`)

> **Category**: USAGE TOOL | **Source**: `scripts/rag/index_custom.py`

## Overview

`index_custom.py` indexes personal Markdown, plain text, and PDF files into the shared `ai_briefings` Qdrant collection. It infers `item_type` and `source` from paths under `KNOWLEDGE_ROOT`, supports YAML front matter on Markdown, chunks by headings/paragraphs, embeds with MiniLM-L6-v2, and persists via the same JSON snapshot format as other indexers.

## Architecture & Design

### System Context

Custom content lives under `KNOWLEDGE_ROOT` (`scripts/config.py`: `.../reports/ai/knowledge`). The Search UI’s “Refresh Knowledge Docs” button calls `index_file` for each supported file via `_run_refresh_knowledge` in `search_ui.py`. CLI users can `add`, `scan`, `list`, or `remove` without starting the Flask app.

```
CLI / Search UI  →  index_file  →  extract (PDF / MD)  →  chunk  →  embed  →  upsert  →  _save_snapshot
```

### Data Flow

1. **add / scan**: `_get_client()` loads snapshot; `_get_model()` loads encoder; for each file, `index_file` chooses extractor by extension.
2. **Markdown**: Read UTF-8 → `_parse_frontmatter` → `_chunk_by_sections` on body → per-chunk metadata (title from `# ` or front matter, tags, difficulty).
3. **PDF**: `pypdf.PdfReader` → concatenate page text → `_chunk_by_sections` → synthetic titles from headings or “(part n)”.
4. **Upsert**: UUID5 ids from `custom:{filename}:{i}`; batched `client.upsert`.
5. **Persist**: `_save_snapshot` scrolls all points to `SNAPSHOT_PATH`.

### Key Design Decisions

- **Folder-based typing**: Top-level folder under `KNOWLEDGE_ROOT` maps via `FOLDER_TYPE_MAP` (`books` → `book_chapter`, etc.); unknown → `personal_note`.
- **Deterministic IDs**: Stable re-index behavior for same file/chunk index.
- **Front matter**: Prefers `pyyaml` when available; falls back to simple line parsing.

## Implementation Details

### Core Components

| Symbol | Role |
|--------|------|
| `_chunk_text` | Paragraph merge with `max_chars` / `overlap` |
| `_chunk_by_sections` | Split on markdown headings `#{1,3}` then sub-chunk |
| `_parse_frontmatter` | `---` ... `---` YAML or heuristic |
| `_infer_item_type`, `_infer_source` | From relative path under `KNOWLEDGE_ROOT` |
| `_extract_pdf_sections`, `_extract_markdown` | Produce list of `{text, metadata}` dicts |
| `index_file` | Encode batch, build `PointStruct`s, upsert |
| `cmd_add`, `cmd_scan`, `cmd_list`, `cmd_remove` | CLI entrypoints |
| `_save_snapshot`, `_load_snapshot` | JSON persistence compatible with briefing indexer |

### API Surface

**CLI**:

| Command | Behavior |
|---------|----------|
| `python index_custom.py add <file-or-folder>` | Index one file or walk directory for `.md`, `.markdown`, `.txt`, `.pdf` |
| `python index_custom.py scan` | `cmd_add(KNOWLEDGE_ROOT)` |
| `python index_custom.py list` | Summarize snapshot points where `source` starts with `knowledge` or equals `custom` |
| `python index_custom.py remove <pattern>` | Drop chunks matching substring in `parent_title`+`title` (case-insensitive) |

`index_file(filepath, client, model)` is also imported by `search_ui.py` for knowledge refresh.

### Configuration

- `KNOWLEDGE_ROOT`, `SNAPSHOT_PATH` from `scripts/config.py`.
- Offline HF env vars set in `_get_model`: `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`.
- `COLLECTION = "ai_briefings"`, `VECTOR_SIZE = 384`.

### Error Handling & Edge Cases

- Unsupported extension: skip with message, return 0 chunks.
- Missing `pypdf`: PDF returns empty list, warning printed.
- Empty PDF text: warning, no items.
- `cmd_remove`: no-op message if pattern matches nothing.

## Code Walkthrough

- **Module doc + constants**: ```1:56:scripts/rag/index_custom.py``` — `FOLDER_TYPE_MAP`, `DEFAULT_DIFFICULTY`.
- **Model/client/snapshot**: ```58:122:scripts/rag/index_custom.py```
- **Chunking + front matter**: ```125:187:scripts/rag/index_custom.py```
- **Path inference + PDF/MD extract**: ```190:300:scripts/rag/index_custom.py```
- **index_file**: ```303:337:scripts/rag/index_custom.py```
- **CLI**: ```340:468:scripts/rag/index_custom.py```

## Improvement Ideas

### Short-term

- Include `.rst` or `.adoc` if needed with same pipeline as markdown.
- Expose chunk `max_chars` / `overlap` as CLI flags.

### Medium-term

- **Web URL indexing**: Fetch HTML → readability extract → same chunk pipeline.
- **Auto-categorization**: LLM or rules to set `item_type` when file is not under mapped folders.

### Long-term

- **Bulk import**: Watch folder with debounced reindex (filesystem watcher).
- **Deduplication**: Hash content to skip unchanged files without full re-embed.

## References

- `scripts/rag/index_custom.py`
- `scripts/rag/search_ui.py` — `_run_refresh_knowledge`
- `scripts/config.py` — `KNOWLEDGE_ROOT`, `SNAPSHOT_PATH`
