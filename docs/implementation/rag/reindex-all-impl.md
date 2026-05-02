# Implementation Guide: reindex_all.py

## Overview

`reindex_all.py` is the incremental re-index orchestrator for the Jarvis RAG stack. It lives at `scripts/rag/reindex_all.py` (about 459 lines). The script coordinates daily briefings, codebase, and Confluence (team and per-user) indexers so they share one embedding model and one Qdrant client, then persists a manifest and on-disk snapshot. Only sources that are stale or forced are re-run, which keeps routine runs fast.

## Technologies

- **Indexer modules (imports):** `index_briefing`, `index_codebase`, `index_confluence`, `index_confluence_user`, `project_graph`
- **Standard library:** `argparse`, `hashlib`, `json`, `os`, `re`, `sys`, `datetime` (`date`, `datetime`, `timedelta`, `timezone`), typing helpers
- **Third-party (via indexers):** `qdrant_client` (client creation and snapshot load in `create_shared_client`)

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────────┐
│  ENTRY                                                                  │
│  python reindex_all.py  [--force | --force-briefings | --force-codebase │
│                           | --force-confluence]                          │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  MANIFEST CHECK + SHARED RUNTIME                                         │
│  load_manifest() ← MANIFEST_PATH / .index-manifest.json (defaults if new) │
│  create_shared_model() + create_shared_client() ← load .rag-store.json   │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  run_briefings (main order #1) — staleness: folder mtime vs manifest    │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  run_codebase (#2) — staleness: MD5 fingerprint path/size/mtime vs manif. │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  run_project_graph (#3) — project_graph.build_graph + save (always runs) │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  run_confluence_team (#4) — 24h TTL unless --force-confluence / --force  │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  run_confluence_user_default (#5) — 7-day TTL per user entry            │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PERSIST                                                                 │
│  index_briefing._save_snapshot(client) → .rag-store.json                  │
│  manifest["last_run"] + save_manifest() → .index-manifest.json          │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
                    print_summary()  →  exit 0 vs 2 (any summary["errors"])

  (Orchestrator does not run a separate vector “cleanup” pass; skips are staleness-driven.)
```

The orchestrator follows a linear pipeline:

1. Parse CLI flags to determine which sources are forced.
2. `load_manifest()` → read prior state (or defaults).
3. `create_shared_model()` and `create_shared_client()` → one `SentenceTransformer` and one in-memory Qdrant client restored from the shared snapshot when present.
4. Run `run_briefings`, `run_codebase`, `run_project_graph`, `run_confluence_team`, and `run_confluence_user_default` in sequence; manifest updates are written by each indexer slice as it runs.
5. `index_briefing._save_snapshot(client)` writes the unified vector store to disk.
6. `save_manifest()` and `print_summary()` finalize the run.

Confluence team indexing generates a fresh report under `C:/reports/ai/<today>` via `index_confluence.run_confluence_report`, then parses and indexes pages. User Confluence uses `DEFAULT_CONFLUENCE_USER` (configurable constant in this file).

## Manifest System

State is stored in JSON at **`C:/reports/ai/.index-manifest.json`** (constant `MANIFEST_PATH` in the script—not `.rag-manifest.json`).

Top-level keys include:

- `last_run` — ISO timestamp of the last successful orchestrator completion
- `briefings` — map of `YYYY-MM-DD` → `{ indexed_at, file_count }`
- `codebase` — map of normalized project path → `{ indexed_at, content_hash, chunk_count }`
- `confluence_team` — `{ indexed_at, page_count }`
- `confluence_users` — map of display name → `{ indexed_at, page_count }`

`load_manifest()` returns a default empty structure if the file is missing or unreadable. `save_manifest()` ensures the parent directory exists and writes pretty-printed JSON.

## How staleness is decided

1. **Briefings:** For each date folder under the reports root, `briefing_needs_index` compares the folder’s filesystem mtime (UTC) to `indexed_at` in the manifest. New folders or newer mtimes trigger a reindex.
2. **Codebase:** `codebase_content_hash` builds an MD5 fingerprint from relative path, size, and mtime of each tracked file (skipping dirs from `index_codebase.SKIP_DIRS`). `codebase_project_needs_index` compares that hash to `content_hash` in the manifest.
3. **Confluence team:** `confluence_team_needs_index` treats the index as stale if `indexed_at` is missing, invalid, or older than **24 hours**.
4. **Confluence user:** `confluence_user_needs_index` uses a **7-day** staleness window per user entry.

When `--force` is set, all of the above checks short-circuit to “needs index.” Per-source `--force-*` flags only force that slice’s check path.

## Key functions

| Function | Role |
|----------|------|
| `load_manifest` / `save_manifest` | Read/write the JSON manifest |
| `_utc_now_iso`, `_parse_manifest_time`, `_folder_mtime_utc` | Time handling for comparisons |
| `create_shared_model` | Delegates to `index_briefing._get_model()` |
| `create_shared_client` | Builds in-memory Qdrant collection, loads snapshot via `index_briefing` helpers |
| `codebase_content_hash`, `norm_codebase_key` | Fingerprint and key normalization for codebase entries |
| `list_briefing_date_folders` | Enumerate `YYYY-MM-DD` briefing directories |
| `briefing_needs_index` | Briefing folder vs manifest |
| `codebase_project_needs_index` | Hash vs manifest |
| `confluence_team_needs_index` / `confluence_user_needs_index` | Time-based staleness |
| `run_briefings` / `run_codebase` / `run_confluence_team` / `run_confluence_user_default` | Execute the corresponding indexer and update manifest + summary |
| `print_summary` | Prints indexed, skipped, and error lines |

## CLI usage

```text
python reindex_all.py                    # Incremental: only stale sources
python reindex_all.py --force            # Force all sources
python reindex_all.py --force-briefings  # Force briefings only (others incremental)
python reindex_all.py --force-codebase   # Force codebase only
python reindex_all.py --force-confluence # Force team + default user Confluence
```

There are no separate `--briefings` / `--codebase` “run only this source” flags: narrowing is done by forcing one slice while others remain incremental, or by editing the script’s main flow if a single-source run is required.

## Design decisions

- **Single model and client:** Avoids loading multiple copies of the transformer and keeps one Qdrant collection consistent with a single snapshot write at the end.
- **Manifest separate from vectors:** The manifest tracks *when* and *what fingerprint* was indexed; the vector data lives in the shared RAG snapshot (`index_briefing` snapshot path), so orchestration state stays small and human-readable.
- **Fast codebase fingerprint:** Hashing path/size/mtime instead of full file bytes balances accuracy and speed for large trees.
- **Different TTLs for team vs user Confluence:** Team content is refreshed daily; personal pages use a longer window to reduce API load.
- **Exit code:** Returns `2` if any errors were recorded in the summary, otherwise `0`, so automation can detect partial failures.
