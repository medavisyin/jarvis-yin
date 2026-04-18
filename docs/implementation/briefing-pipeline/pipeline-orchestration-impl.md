# Implementation Guide: Pipeline Orchestration

## Overview

The pipeline orchestrator coordinates end-to-end briefing ingestion in multiple phases: preflight connectivity checks, parallel AI news fetching, source merging, RAG indexing, and world news fetching (including Chinese political/financial news and Ollama translation).

| Script | Role |
|--------|------|
| `scripts/pipeline/preflight-check.py` | Parallel URL reachability checks before heavy scraping |
| `scripts/pipeline/run-all-sources.py` | Main orchestrator: subprocess fetchers, merge, RAG index, world news |
| `scripts/pipeline/merge-sources.py` | Combines `{source}.json` files and deduplicates by title similarity |
| `scripts/pipeline/run-world-news.py` | World news orchestrator: 6 fetchers + merge + Chinese translation |

See also: [World News Pipeline](./world-news-impl.md) for detailed docs on `run-world-news.py`, `fetch-china-news.py`, translation, and merge logic.

## Technologies

| Technology | Usage |
|------------|--------|
| **asyncio** | Concurrent preflight checks and coordination patterns |
| **subprocess** | Parallel execution of independent `fetch-*.py` processes |
| **Playwright** | Headless navigation for preflight URL verification |
| **json** | Reading per-source outputs and writing merged briefing data |
| **time** | Wall-clock or monotonic tracking for pipeline reporting |

## Pipeline Flow

```
run-all-sources.py (main orchestrator)
  │
  ├── Phase 0: preflight-check.py (check URLs reachable)
  │
  ├── Phase 1: Parallel Fetch (AI fetchers, currently 3 active)
  │   └── Active: fetch-anthropic, fetch-rundown, fetch-github-trending
  │   └── Disabled: fetch-arxiv-ml, fetch-arxiv, fetch-openai-blog,
  │                  fetch-deepmind, fetch-techcrunch, fetch-mit-review
  │
  ├── Phase 2: merge-sources.py → briefing-data.json
  │
  ├── Phase 2.5: generate_learning_guide.py (if raw articles exist)
  │
  ├── Phase 3: RAG Indexing (index_briefing.py)
  │
  ├── Phase 3.5: Confluence Indexing (index_confluence.py)
  │
  └── Phase 5: World News Fetch (180s timeout)
      └── run-world-news.py --output-dir <world-news/>
          ├── 6 parallel fetchers (5 international + 1 China)
          ├── Merge by category with deduplication
          └── Ollama translation (English → Chinese)
```

Preflight is optional in manual workflows but recommended for diagnosing proxies, DNS, and site blocks before launching browser-backed jobs.

## Script Details

### preflight-check.py

- Loads the configured source URLs (aligned with fetcher `SOURCE_URL` values).
- Opens each URL in headless Chromium via Playwright, with parallel checks across sources.
- Prints or logs which endpoints are reachable, slow, or failing.
- Surfaces TLS, HTTP status, and timeout issues without running the full fetch workload.

### run-all-sources.py

- Creates a temporary output directory (conventionally `_briefing_tmp` under the working tree) for per-source JSON.
- Spawns every `fetch-*.py` script as a subprocess with appropriate working directory and environment.
- Waits for all child processes, records per-script duration and exit codes.
- Invokes `merge-sources.py` to produce consolidated `briefing-data.json`.
- May invoke `filter_topics.py` after merge to apply topic freshness and tagging before downstream generators consume the file.

### merge-sources.py

- Enumerates `*.json` outputs in the temp directory from completed fetchers.
- Parses each file’s `items` array and concatenates into one ordered list (often with source metadata preserved on items).
- Applies deduplication using title similarity to reduce near-duplicate headlines across outlets.
- Writes `briefing-data.json`, the canonical input for `briefing-template.py`, `generate-audio.py`, and `generate-video.py`.
- Emits a timing log summarizing per-source `_timing` data and merge duration.

## Error Handling

- **Preflight** — Failed checks do not automatically abort `run-all-sources.py`; they inform the operator. Individual fetchers still enforce their own `safe_fetch` guarantees.
- **Subprocess fetchers** — Non-zero exit codes are collected; merge may run with partial inputs if some JSON files exist.
- **Missing JSON** — Merge skips or warns on absent files; empty `items` arrays are valid.
- **Merge deduplication** — Collisions are resolved deterministically (e.g., first-seen wins or highest-similarity merge) per implementation in `merge-sources.py`.

## Configuration

- **Paths** — Temp directory name and final `briefing-data.json` location are defined in `run-all-sources.py` and `merge-sources.py` (or via environment variables if present in those scripts).
- **Environment inheritance** — Child fetchers inherit `BRIEFING_PROXY`, `SAVE_RAW`, and any locale or font-related variables needed for consistent scraping.
- **Fetcher set** — The orchestrator references scripts via relative paths (`fetchers/ai/fetch-*.py` and `fetchers/news/fetch-*.py`). The list must stay in sync with the actual files in those directories.

## Output Files

| Artifact | Producer | Consumer |
|----------|----------|----------|
| `{source}.json` | Each `fetch-*.py` | `merge-sources.py` |
| `briefing-data.json` | `merge-sources.py` | Output generators, `filter_topics.py`, RAG indexing |
| `world-news/{source}.json` | World news fetchers | `merge_news()` in `run-world-news.py` |
| `world-news/world-news-data.json` | `run-world-news.py` | World audio generation, UI display, black swan detector |
| `world-news/world-news-timing.json` | `run-world-news.py` | Operators, CI logs |
| Timing / log output | `run-all-sources.py`, `merge-sources.py` | Operators, CI logs |

After merge (and optional `filter_topics.py`), the pipeline hands off to output generation scripts. The world news phase runs independently and produces its own merged output used for audio generation and stock-related analysis.

See [World News Pipeline](./world-news-impl.md) for full details on the 6-source world news pipeline, Chinese news fetching, and Ollama translation.
