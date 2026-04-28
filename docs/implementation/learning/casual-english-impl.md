---
tags:
  - implementation
  - learning
  - casual-english
category: learning
status: current
last-updated: 2026-04-28
---

# Casual English Learning

> **Category**: LEARNING | **Source**: `scripts/rag/agent.py`

## Overview

Casual English Learning uses **world news** articles (English titles only) to teach everyday vocabulary, idioms, cultural context, and dialogues. It shares the same intent-resolution pipeline as Tech English but sources topics from `_load_recent_world_news_titles()` and `_fetch_article_content`’s world-news JSON branch, with `SYSTEM_PROMPT_CASUAL_ENGLISH` enforcing a six-section, 500+ word lesson.

## Architecture & Design

### System Context

Session UUID `...0003`. Classification uses `_classify_and_resolve_learning_input` with `channel_desc` “Casual English - learning everyday English through world news” and `_resolve_topic_by_name_in_list` against world news titles (`1606–1608`, `1610`, `1632–1647`).

```text
User message
    → _classify_and_resolve_learning_input (casual_english)
        → world news titles / LLM intent
    → _fetch_article_content(title, session_id)
        → world-news-data.json (per-day scan)
    → effective_query + SYSTEM_PROMPT_CASUAL_ENGLISH
    → run_agent (RAG + long context)
```

### Data Flow

1. `api_agent` selects `SYSTEM_PROMPT_CASUAL_ENGLISH` for `casual_english` (`2040–2042`).
2. `_classify_and_resolve_learning_input` loads `all_items = _load_recent_world_news_titles()` and title list for matching (`1606–1607`, `1610`).
3. On `select_topic`, `_fetch_article_content` walks up to 7 days of `world-news/world-news-data.json` or legacy `world-news-data.json`, matches title case-insensitively, and returns title, category, source, summary, body (cap 5000), points, commentary, analysis (`1904–1940`).
4. `effective_query` lists all six casual-English sections including detailed “What Happened?” requirements (`2221–2240`).
5. `more_topics` uses `_fetch_fresh_topics` with `[category] title` lines (`1666–1670`, `2251–2258`).
6. Off-topic path streams response without `rag_query_override` (`2267–2286`).

### Key Design Decisions

- **CJK filter** — `_has_cjk_chars` drops non–English-practice titles (`5375–5376`, `5397–5399`).
- **Category in topic lists** — Fresh topics show `[category] title` for quicker scanning (`1669–1670`).
- **Same intent machinery as Tech English** — One code path to maintain; only data sources differ (`1589–1629`).
- **Prompt focuses on informal register** — Idioms, fillers, dialogues, cultural cues (`1333–1388`).

## Implementation Details

### Core Components

| Piece | Role |
|--------|------|
| `SYSTEM_PROMPT_CASUAL_ENGLISH` | Six sections: news summary, casual vocab, patterns, native retelling, culture, dialogues (`1333–1388`). |
| `_load_recent_world_news_titles` | Aggregates ≤50 items from recent `world-news-data.json`; skips CJK titles (`5380–5402`). |
| `_resolve_topic_by_name_in_list` | Casual name matching with command-prefix strip (`1632–1647`). |
| `_fetch_article_content` (casual branch) | JSON article field assembly (`1904–1940`). |
| `_fetch_fresh_topics` | Casual branch formats numbered list with categories (`1666–1670`). |
| `api_agent` | Casual branch parallel to English (`2216–2286`). |
| `api_learning_context` | Returns `news_items` with title, category, summary snippet (`5441–5443`). |

### API Surface

- `POST /api/toolbar/learning-session` — `type: casual_english` (`5408–5412`).
- `GET /api/toolbar/learning-context?type=casual_english` (`5441–5443`).
- `POST /api/agent` — `session_id` `00000000-0000-0000-0000-000000000003`.

### Configuration

- World news paths: `REPORTS_ROOT/{date}/world-news/world-news-data.json` or `REPORTS_ROOT/{date}/world-news-data.json` (`1905–1910`, `5384–5388`).
- JSON shape: `categories[]` with `label`/`category` and `items` or `articles` (`1914–1916`).

### Error Handling & Edge Cases

- JSON read errors logged with `logging.warning` (`5400–5401`).
- No article match → fallback prompt using RAG + knowledge (`2242–2249`).
- Empty `topic_ctx` for more_topics → user-facing message to check back later (`2260–2263`).

## Code Walkthrough

- **Prompt** — `SYSTEM_PROMPT_CASUAL_ENGLISH` (`1333–1388`).
- **Title loading** — Loop `d_offset in range(7)`, nested categories and articles (`5384–5399`).
- **Article body** — Prefers `summary`, `body[:5000]`, bullet `points`, optional `commentary` / `analysis` (`1927–1939`).
- **Classification** — `is_tech` false → `_resolve_topic_by_name_in_list` and world-news titles (`1601`, `1610`).
- **Main teach prompt** — Section 1 explicitly requires depth and facts (`2225–2240`).
- **Non–eng/cas shared path** — For `ai_learning` and other sessions, `_resolve_topic_from_history` still applies; `_eng_cas_ids` excludes English/casual from that block (`2288–2292`).

## Improvement Ideas

### Short-term

- Deduplicate world news titles across dates when building the 50-item cap.
- Expose article `url` in the UI from `api_learning_context` for preview before study.

### Medium-term

- **Idiom flashcards** — Export idioms from model output to structured JSON for drill apps.
- **Difficulty levels** — Simpler vocabulary glossaries for A2/B1 vs C1 in prompt suffix.

### Long-term

- **Speech recognition** — User speaks a topic or practices dialogues; grade fluency externally.
- **Cultural comparison** — User locale in request body to contrast norms in prompt.

## References

- `scripts/rag/agent.py` — `SYSTEM_PROMPT_CASUAL_ENGLISH`, `_load_recent_world_news_titles`, `_fetch_article_content` (casual), `_fetch_fresh_topics`, `api_agent` casual branch, `api_learning_context` (`1333–1388`, `1904–1940`, `2216–2286`, `5380–5443`).
