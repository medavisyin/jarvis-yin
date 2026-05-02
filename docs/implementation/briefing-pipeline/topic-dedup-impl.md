# Implementation Guide: Topic Deduplication System

## Overview

The topic system prevents briefing fatigue by tracking stories across days, classifying each mention as new, updated, or stale, and filtering redundant items before PDF and media generation. It also supports optional archival of full raw article text for deeper RAG indexing.

| Script | Responsibility |
|--------|----------------|
| `scripts/pipeline/topic_index.py` | Persistent `TopicIndex` with fuzzy matching and classification |
| `scripts/pipeline/filter_topics.py` | Applies `TopicIndex` to merged briefing items and tags survivors |
| `scripts/raw_saver.py` | Saves full drill-down markdown when `SAVE_RAW=1` |

## Architecture & Design

```text
┌──────────────────────────────────────────────────────────────────┐
│  INPUT: briefing-data.json (merged per_source_data[].items[])     │
└─────────────────────────────┬────────────────────────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    filter_topics.filter_briefing()                │
│  TopicIndex.load → for each item: classify(title, summary, date) │
└─────────────────────────────┬────────────────────────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│               TopicIndex (scripts/pipeline/topic_index.py)        │
│  match_topic: normalize → SequenceMatcher + keyword overlap       │
│     vs canonical_title / aliases vs SIMILARITY_THRESHOLD          │
│  classify:                                                          │
│    · no match → "new" + _topic_hash                                 │
│    · gap > 3 days → "updated" [RETURNING]                         │
│    · _has_new_info(title+summary keywords) → "updated"            │
│    · else → "stale"                                                │
└─────────────────────────────┬────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐       ┌─────────────────────────────┐
│  keep new / updated     │       │  aggressive: skip stale       │
│  _dedup_tag, _topic_id  │       │  (append skipped_stale list) │
│  update_topic() in-mem │       └─────────────────────────────┘
└────────────┬────────────┘
             │ idx.save()
             ▼
┌──────────────────────────────────────────────────────────────────┐
│  OUTPUT: filtered JSON (+ topic-index.json persisted)           │
│  → PDF / TTS / video / indexing stages                            │
└──────────────────────────────────────────────────────────────────┘
```

## Technologies

| Module | Role |
|--------|------|
| **difflib.SequenceMatcher** | Fuzzy similarity between titles and canonical topic strings |
| **hashlib** | Stable topic identifiers derived from normalized strings |
| **json** | Serialize and load `topic-index.json` |
| **re** | Tokenization, keyword extraction, normalization |
| **datetime** | Freshness windows, gap detection, staleness thresholds |

## TopicIndex Architecture

The `TopicIndex` class maintains a durable JSON store of every topic the pipeline has observed.

### Topic record shape

- **`canonical_title`** — Normalized primary headline for the topic cluster.
- **`aliases`** — Alternate titles matched to the same topic.
- **`first_seen` / `last_seen`** — ISO or normalized dates for lifecycle analytics.
- **`mention_count`** — Number of times the story appeared across runs.
- **`summary_evolution`** — Historical summaries or keywords showing how coverage changed.
- **`sources`** — Originating outlets or fetcher `source` identifiers.

### Key methods

| Method | Behavior |
|--------|----------|
| `match_topic(title)` | Fuzzy and keyword overlap against known topics; returns best match above threshold |
| `classify(title, summary, date)` | Returns `"new"`, `"updated"`, or `"stale"` |
| `update_topic(...)` | Records a new mention, merges aliases, appends summary evolution, updates sources |
| `_has_new_info(...)` | Compares keyword sets between the incoming mention and all prior mentions |
| `get_stale_topics(days)` | Topics with no recent mentions beyond `days` |
| `stats()` | Aggregate counts for debugging and dashboards |

### Self-test

Running `topic_index.py` with `--test` executes a built-in suite that exercises matching, classification edge cases, and persistence round-trips.

## Classification Algorithm

| Label | Conditions (conceptual) |
|-------|-------------------------|
| **`new`** | No fuzzy/keyword match to an existing topic |
| **`updated`** | Matched topic **and** (`_has_new_info` indicates keyword novelty above ~30% **or** the topic reappears after a gap of at least three days) |
| **`stale`** | Matched topic, insufficient novelty, and seen recently |

The exact thresholds live in `topic_index.py` as constants; tune them when outlets repeat identical phrasing across days.

## Fuzzy Matching

- Candidate titles are normalized (case folding, punctuation stripping, whitespace collapse) before `SequenceMatcher` ratios are computed.
- Keyword bags extracted via `re` supplement fuzzy scores so that minor rewordings still map to the same cluster.
- Hash-based IDs tie persisted records to in-memory structures across process restarts.

## Filter Pipeline (`filter_topics.py`)

1. Read merged `briefing-data.json`.
2. For each item, call `TopicIndex.classify(title, summary, date)`.
3. Drop items classified as `"stale"` so the briefing highlights only fresh angles.
4. Tag retained items with human-readable freshness labels, for example:
   - `[NEW]`
   - `[UPDATED — day N]`
   - `[RETURNING after N days]`
5. Write filtered JSON for downstream PDF/TTS/video scripts and optional indexing.

## Raw Saver (`raw_saver.py`)

- Imported by `fetch-*.py` modules during drill-down.
- When environment variable `SAVE_RAW=1`, saves the full extracted article body as markdown.
- **Output path pattern:** `{output_dir}/raw/{source}-{index}-{slug}.md`
- **Frontmatter** includes at least: title, source URL, date, and difficulty (when inferred or defaulted).
- `scripts/rag/index_briefing.py` uses `_extract_raw_files()` to ingest these markdown files for richer retrieval than summaries alone.

## Data Formats

| File | Contents |
|------|----------|
| `topic-index.json` | Serialized topics, aliases, counters, evolution history |
| Filtered briefing JSON | Same schema as merge output plus freshness tags in titles or metadata |
| `raw/*.md` | Full-text markdown with YAML or markdown frontmatter |

## CLI Usage

| Command | Purpose |
|---------|---------|
| `python topic_index.py --test` | Run TopicIndex self-tests |
| `python filter_topics.py` (with args as defined in script) | Apply classification to `briefing-data.json` and emit filtered output |

Consult each script’s `argparse` or `if __name__` block for exact flags, default paths, and output filenames.
