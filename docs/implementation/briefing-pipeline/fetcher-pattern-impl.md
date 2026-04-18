# Implementation Guide: Fetcher Scripts (fetch-*.py)

## Overview

The Jarvis briefing pipeline uses sixteen fetcher scripts organized into two subdirectories under `scripts/fetchers/`. Each script collects structured news or research items from a single source, optionally drills into article pages for full text or abstracts, and writes a per-source JSON file consumed later by merge and output stages.

**AI and technology fetchers** (`scripts/fetchers/ai/`, 10 scripts — 9 used by `run-all-sources.py`): `fetch-arxiv.py`, `fetch-arxiv-ml.py`, `fetch-openai-blog.py`, `fetch-anthropic.py`, `fetch-deepmind.py`, `fetch-techcrunch.py`, `fetch-rundown.py`, `fetch-github-trending.py`, `fetch-mit-review.py`, `fetch-hf-papers.py` (manual only)

**World news fetchers** (`scripts/fetchers/news/`, 6 scripts — all used by `run-world-news.py`): `fetch-china-news.py` (Sina + People's Daily, priority 0), `fetch-bbc-news.py`, `fetch-reuters.py`, `fetch-ap-news.py`, `fetch-dw-news.py`, `fetch-guardian.py`

All fetchers share one universal asynchronous pattern: launch a headless browser (or equivalent extraction path), extract listings, drill down where configured, normalize fields, and persist JSON with timing metadata.

## Technologies

| Technology | Role |
|------------|------|
| **Playwright** (`async_playwright`) | Headless Chromium for DOM scraping and navigation |
| **asyncio** | Concurrent async execution inside each script |
| **json** | Serialized output for downstream merge |
| **raw_saver** | Optional persistence of full drill-down text when `SAVE_RAW=1` |

## The Universal Pattern

Every fetcher follows the same structural blueprint.

1. **Constants** — `SOURCE_NAME`, `SOURCE_URL`, `MAX_ITEMS`, `DRILL_DOWN_COUNT`, `OUTPUT_DIR` (and any source-specific selectors or endpoints).
2. **`async fetch()`**
   - Launch headless Chromium; optionally route traffic through a proxy when `BRIEFING_PROXY` is set.
   - Navigate to the source URL (or fetch RSS where applicable).
   - Extract headlines: titles, URLs, dates, and authors as the source allows.
   - Drill down into the top `DRILL_DOWN_COUNT` items to load full content or abstracts.
   - Build the `items` list; each item includes `title`, `url`, `date`, `summary`, `points`, and `authors`.
   - Record monotonic timing for each logical step.
3. **`async safe_fetch()`** — Wraps `fetch()` in `try`/`except`, ensures an output JSON file is still written on failure (typically with error context and empty or partial `items`).
4. **Output file** — `{source_name}.json` with top-level keys `source`, `items`, and `_timing`.

Helper patterns such as `_step(name)` wrap blocks with `time.monotonic()` to append `{ "step": "...", "seconds": ... }` entries into `_timing.steps`.

## Drill-Down Mechanism

- Only the first `DRILL_DOWN_COUNT` items (after listing extraction and any local sorting) receive full page loads.
- For each such item, the script navigates to the article URL and extracts body text, abstract, or RSS `description` enrichment depending on the site.
- When `SAVE_RAW=1`, `raw_saver.save_raw_content()` may persist the full extracted text as markdown under the configured output tree for later indexing.

Listing-only items beyond the drill-down limit still appear in `items` with summaries derived from listing pages or snippets where available.

## Timing System

- Elapsed time uses `time.monotonic()` to avoid clock skew.
- Each major phase (navigation, headline extraction, each drill-down iteration, cleanup) is recorded via a shared `_step` pattern into `_timing.steps`.
- `_timing.total_seconds` aggregates the full run from start of `fetch()` through completion.
- `_timing` also carries `source` (or equivalent) for merge-stage diagnostics.

## Output Format

```json
{
  "source": "arxiv",
  "items": [
    {
      "title": "Paper Title",
      "url": "https://...",
      "date": "2026-04-08",
      "summary": "Abstract text...",
      "points": [],
      "authors": "Author1, Author2"
    }
  ],
  "_timing": {
    "source": "arxiv",
    "steps": [
      {"step": "navigate", "seconds": 2.1},
      {"step": "extract_headlines", "seconds": 1.3},
      {"step": "drill_down_1", "seconds": 3.5}
    ],
    "total_seconds": 8.2
  }
}
```

- **`source`** — Stable identifier matching the merge configuration.
- **`items`** — Ordered collection; field population varies slightly by source.
- **`points`** — Often empty for paper sources; may hold bullet extractions for blogs.
- **`_timing`** — Diagnostic only; not required for PDF or audio generation but useful for pipeline tuning.

## Source Variations

| Source group | Notable behavior |
|--------------|------------------|
| **ArXiv** (`fetch-arxiv.py`, `fetch-arxiv-ml.py`) | Parses listing structure (e.g., `dt`/`dd` pairs), follows `/abs/` links for abstracts |
| **HF Papers** (`fetch-hf-papers.py`) | Scrolls for lazy-loaded content; may sort or prioritize by engagement (e.g., upvotes) |
| **BBC, Reuters, DW, Guardian** | RSS feed parsing for listings plus Playwright drill-down into article HTML |
| **AP News** (`fetch-ap-news.py`) | Playwright-only listing and article extraction (no RSS dependency) |
| **GitHub Trending** (`fetch-github-trending.py`) | Repo name, stars, language, and description from trending page structure |
| **Blogs / corp news** (OpenAI, Anthropic, DeepMind, TechCrunch, MIT Review, Rundown) | Site-specific selectors and pagination; same drill-down and timing envelope |

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `BRIEFING_PROXY` | Optional HTTP(S) proxy URL passed to the browser context |
| `SAVE_RAW` | When set to `1`, enables `raw_saver` markdown dumps for drilled articles |

Additional script-specific variables may exist; consult each `fetch-*.py` for defaults and paths.

## Error Handling

- **`safe_fetch()`** catches exceptions from `fetch()`, logs or embeds error information, and still writes `{source}.json` so orchestration can proceed and surface failures per source.
- Partial results are preferred over silent omission: successfully scraped items should appear even if later drill-downs fail.
- Playwright timeouts and navigation errors are typically mapped to skipped items or shortened summaries rather than crashing the entire process.
- Exit codes from subprocess invocation allow `run-all-sources.py` to distinguish success, partial failure, and total failure per fetcher.
