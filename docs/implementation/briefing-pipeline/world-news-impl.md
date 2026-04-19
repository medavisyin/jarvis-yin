# Implementation Guide: World News Pipeline

## Overview

The world news pipeline fetches international and Chinese political/financial news from 6 sources, merges them by category, translates English content to Chinese via Ollama, and produces `world-news-data.json` for audio narration and UI display.

| Script | Role |
|--------|------|
| `scripts/pipeline/run-world-news.py` | Orchestrator: parallel fetch, merge, Ollama translation |
| `scripts/fetchers/news/fetch-bbc-news.py` | BBC World News (RSS + Playwright drill-down) |
| `scripts/fetchers/news/fetch-reuters.py` | Reuters (RSS + Playwright scraping fallback) |
| `scripts/fetchers/news/fetch-ap-news.py` | AP News (Playwright scraping) |
| `scripts/fetchers/news/fetch-dw-news.py` | Deutsche Welle (RSS + Playwright drill-down) |
| `scripts/fetchers/news/fetch-guardian.py` | The Guardian (RSS + Playwright drill-down) |
| `scripts/fetchers/news/fetch-china-news.py` | 中国新闻: 新浪 + 人民日报 + 财联社 + 头条 + 微博 (5 sources) |

## Technologies

| Technology | Usage |
|------------|-------|
| **asyncio** | Parallel subprocess execution for all 6 fetchers |
| **feedparser** | RSS parsing (BBC, DW, Guardian, People's Daily) |
| **requests** | HTTP API calls (Sina, CLS, Toutiao, Weibo, Ollama translation) |
| **Playwright** | Headless browser drill-down for article content |
| **Ollama** | Batch translation via `/api/chat` endpoint |
| **re** | Parsing numbered translation output |

## Pipeline Flow

```
run-all-sources.py
  └── Phase 5: World News Fetch
        │
        ▼
run-world-news.py --output-dir <world-news-dir> [--proxy <url>]
  ├── Parallel Fetch (6 scripts)
  │   ├── fetch-bbc-news.py      → bbc-news.json
  │   ├── fetch-reuters.py       → reuters.json
  │   ├── fetch-ap-news.py       → ap-news.json
  │   ├── fetch-dw-news.py       → dw-news.json
  │   ├── fetch-guardian.py      → guardian.json
  │   └── fetch-china-news.py    → china-news.json    (5 CN sources)
  │
  ├── Merge (merge_news)
  │   ├── Read all {source}.json files
  │   ├── Deduplicate by first-80-chars of title (lowered)
  │   ├── Sort by source priority (china-news=0 → highest)
  │   ├── Group into 4 categories + "other"
  │   └── Preserve title_zh/summary_zh from Chinese sources
  │
  ├── Translate to Chinese (translate_news_to_chinese)
  │   ├── Collect all title/summary texts
  │   ├── Batch translate via Ollama (10 texts/batch)
  │   └── Store as title_zh/summary_zh on each item
  │
  └── Output
      ├── world-news-data.json   (merged + translated)
      └── world-news-timing.json (per-source timing)
```

## Chinese News Fetcher (`fetch-china-news.py`)

### Data Sources (5 sources, all mainland-reachable)

| Source | API/Feed | Content | Typical Items |
|--------|----------|---------|:------------:|
| **新浪滚动新闻** (Sina) | `feed.mix.sina.com.cn/api/roll/get` | Finance (LID 2509) + Politics (LID 2510) | ~45 |
| **人民日报** (People's Daily) | RSS (`people.com.cn/rss/`) | Politics + Finance feeds | ~20 |
| **财联社快讯** (CLS Telegraph) | `cls.cn/nodeapi/updateTelegraphList` | Real-time market flash news | ~15 |
| **今日头条热榜** (Toutiao) | `toutiao.com/hot-event/hot-board/` | Trending hot topics | ~15 |
| **微博热搜** (Weibo) | `weibo.com/ajax/side/hotSearch` | Social trending topics | ~15 |

### Cross-Day Deduplication (2026-04-19)

A major issue was that rolling/trending APIs return "latest N" items regardless of date, causing heavy overlap between consecutive daily fetches. The fix:

1. On each run, load yesterday's `china-news.json` titles
2. Skip any article whose title (first 50 chars) matches yesterday's data
3. Sort results: today's articles first, then by source diversity

This typically removes 20-40 stale articles per run.

### Category Mapping

The fetcher maps raw categories to standard world-news categories:

```python
CATEGORY_MAP = {
    "politics": "politics",     # → "Politics & World Affairs"
    "finance": "economics",     # → "Economics & Business"
    "economy": "economics",
    "policy": "politics",
    "technology": "technology",  # → "Technology"
}
```

Political keyword detection overrides category for Sina items containing: 政策, 国务院, 总书记, 外交, 军事, 制裁.

Toutiao/Weibo items are auto-categorized by keyword matching (经济/股/基金 → economics, 科技/AI/芯片 → technology).

### Output Format

Each item includes pre-filled `title_zh`/`summary_zh` (since content is already Chinese):

```json
{
  "title": "光大期货0416热点追踪：干旱与减产预期共振",
  "title_zh": "光大期货0416热点追踪：干旱与减产预期共振",
  "url": "https://...",
  "date": "2026-04-16 09:30",
  "summary": "...",
  "summary_zh": "...",
  "category": "economics",
  "points": [],
  "_source_tag": "sina"
}
```

Valid `_source_tag` values: `sina`, `people`, `cls`, `toutiao`, `weibo`.

## Merge Logic (`merge_news`)

### Source Priority

Sources are sorted by priority during deduplication (lower = higher priority):

| Source | Priority | Display Name |
|--------|:--------:|-------------|
| `china-news` | 0 | 中国新闻 (新浪/人民日报/财联社/头条/微博) |
| `bbc-news` | 1 | BBC World News |
| `reuters` | 2 | Reuters |
| `ap-news` | 3 | AP News |
| `dw-news` | 4 | Deutsche Welle |
| `guardian` | 5 | The Guardian |

### Category Buckets

| Category Key | Display Label | Typical Sources |
|-------------|---------------|-----------------|
| `politics` | Politics & World Affairs | China (politics), BBC, DW, Guardian |
| `economics` | Economics & Business | China (finance), BBC, Reuters |
| `technology` | Technology | BBC, Guardian |
| `science` | Science & Environment | BBC, DW, Guardian |

### Field Preservation

The `_build_merged_item()` helper preserves optional `title_zh`/`summary_zh` fields from source items that already have them (e.g., Chinese sources). This is critical for:
- Avoiding redundant re-translation of already-Chinese text
- Providing native-quality Chinese titles for audio narration

## Translation (`translate_news_to_chinese`)

### How It Works

1. Collects all `title` and `summary` texts from merged items
2. Sends them to Ollama in batches of 10 via `/api/chat`
3. Parses numbered output lines (e.g., `1. 中文翻译`)
4. Stores translations as `title_zh` and `summary_zh` on each item

### Configuration

| Setting | Default | Source |
|---------|---------|--------|
| Model | `qwen3:1.7b` | `OLLAMA_MODEL_FAST` env var |
| Host | `http://localhost:11434` | `OLLAMA_HOST` env var |
| Batch size | 10 texts | Hardcoded |
| Temperature | 0.1 | Low for consistent translations |
| Max tokens | 2000 per batch | `num_predict` |
| `think` | `false` | Prevents reasoning preamble |

### Translation Prompt

```
System: 你是专业翻译。只输出翻译结果，不要解释。

User: 将以下{N}条新闻标题/摘要翻译成简体中文。
      严格按编号输出，每行格式: 编号. 中文翻译
      不要添加任何解释。

      1. Social media leaders called to Downing Street
      2. Bank boss tells BBC he won't rush interest rate rises
      ...
```

### Skip Translation

Pass `--no-translate` to skip the translation step entirely.

## Audio Generation Integration

The agent's `_run_daily_fetch` function generates **two separate audio files** from world news data:

### World News Audio (`world-news.mp3`)
- Contains only **international** items (BBC, Reuters, AP, DW, Guardian)
- China-sourced items are filtered out via `_CHINA_SOURCE_TAG`
- Language controlled by `audio_lang_world` setting

### Chinese News Audio (`china-news.mp3`)
- Contains only **China-sourced** items (Sina, People's Daily, CLS, Toutiao, Weibo)
- Up to 6 items per category (vs 4 for world news)
- Language controlled by `audio_lang_china` setting
- Cross-day dedup ensures minimal repeat content between consecutive days

### Generation Flow

1. Read `world-news-data.json`
2. `_build_audio_segments()` filters items by source and builds per-category segments
3. Prefer `title_zh`/`summary_zh` when audio language is Chinese
4. Send segments to `_generate_segmented_narrations(segments, "world", lang=...)`
5. Convert narration text to MP3 via Edge-TTS

### Audio Language Settings

| Setting | Audio File | Default |
|---------|-----------|---------|
| `audio_lang_world` | `world-news.mp3` (international) | `"zh"` |
| `audio_lang_china` | `china-news.mp3` (Chinese) | `"zh"` |

## Output Schema

### `world-news-data.json`

```json
{
  "sources_used": ["BBC World News", "中国新闻 (新浪/人民日报/财联社/头条/微博)", ...],
  "sources_unavailable": ["AP News"],
  "total_items": 70,
  "translated": true,
  "categories": [
    {
      "category": "politics",
      "label": "Politics & World Affairs",
      "items": [
        {
          "title": "Original English title",
          "title_zh": "中文翻译标题",
          "url": "https://...",
          "date": "2026-04-16",
          "summary": "Original summary...",
          "summary_zh": "中文翻译摘要...",
          "points": [],
          "source": "BBC World News"
        }
      ]
    }
  ]
}
```

## Error Handling

- **Fetcher timeout**: Each script has 120s timeout. `fetch-china-news.py` takes ~30s (5 API sources with 12s timeout each).
- **Translation failure**: If an Ollama batch fails, items keep their original `title`/`summary` without `_zh` variants.
- **Missing sources**: The merge function handles missing JSON files gracefully; absent sources appear in `sources_unavailable`.
- **Pipeline timeout**: `run-all-sources.py` gives the world news phase a 180s timeout.

## Configuration

| Setting | Value | Location |
|---------|-------|----------|
| Fetcher list | `FETCH_SCRIPTS` | `run-world-news.py` line 27 |
| Source metadata | `SOURCE_META` | `run-world-news.py` line 36 |
| Category order | `CATEGORY_ORDER` | `run-world-news.py` line 45 |
| Per-script timeout | 120s | `PER_SCRIPT_TIMEOUT` |
| Sina API channels | LID 2509 (finance, 25 items), 2510 (politics, 20 items) | `fetch-china-news.py` |
| China source count | 5 (Sina, People, CLS, Toutiao, Weibo) | `fetch-china-news.py` |
| Cross-day dedup | Loads yesterday's titles, skips matches | `fetch-china-news.py` |
