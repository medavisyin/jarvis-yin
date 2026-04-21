---
tags:
  - plan
  - roadmap
  - active
category: plan
status: active
last-updated: 2026-04-18
---


# Jarvis Enhancement Plan — April 2026 and Beyond

> **Purpose:** A living roadmap of enhancements, new features, and infrastructure improvements for the Jarvis project. Organized by priority tier and domain. Each item includes rationale, complexity estimate, and dependency notes.

**Last updated:** 2026-04-18

---

## Status overview

| Area | Current maturity | Next frontier |
|------|-----------------|---------------|
| **RAG** | Advanced (hybrid search, reranking, 6 indexers, feedback) | Embedding fine-tuning, corrective RAG, adaptive retrieval |
| **Daily Fetch** | Complete pipeline with segmented audio, wiki fetch, continue recovery | Auto-scheduling, email digest, multi-language podcast |
| **Stock** | Full stack (TA, fundamental, sentiment, XGBoost, scanner, prediction) | Portfolio tracking, backtesting engine, real-time alerts |
| **Infrastructure** | Single-machine, no tests, no CI | Testing, Docker, CI/CD, monitoring |
| **UI/UX** | Functional monolithic template | Component extraction, mobile-responsive, dark/light themes |

---

## Tier 0 — Bug Fixes & Code Health (Do First)

### 0.1 Fix Silent Error Swallowing

**Problem:** Many `except Exception: pass` patterns make failures invisible. Failed RAG/commits/Jira auto-context in `run_agent`'s `ThreadPoolExecutor` block is swallowed — user gets no context and no warning. Corrupt `predictions_log.json` shows empty history. Daily summary JSON parse errors leave sections saying "No data" while files exist.

**Locations:**
- `agent.py` `run_agent` parallel block (~L879): `future.result()` failures → `pass`
- `agent.py` `tool_commit_summary`: failed `git fetch` → `pass`
- `agent.py` `_rewrite_query`: Ollama failure → silent fallback
- `agent.py` daily summary JSON load (~L3439): parse error → empty sections
- `agent.py` stats/Jira/wiki parsing (~L3754+): failures → zero counts
- `stock/prediction_tracker.py` `_load_log`: corrupt file → empty list

**Fix:**
- Replace `pass` with `logging.warning(...)` in all silent handlers
- In `run_agent`: collect failed context sources and inject a small system note: *"Note: Jira context unavailable (timeout)"*
- In Daily Fetch history API: return a `warnings` list so the UI can show a subtle banner

**Complexity:** Low (half day)
**Dependencies:** None

---

### 0.2 Fix Timeout Mismatch

**Problem:** `ThreadPoolExecutor` futures in `run_agent` timeout at **60s**, but `tool_jira_report` subprocess has **120s** timeout. Heavy RAG search can also exceed 60s. The outer timeout silently cancels work-in-progress.

**Fix:** Set outer future timeout to `max(TOOL_TIMEOUT_SECONDS, 60) + 15` buffer, or make it configurable. Log when a future is cancelled due to timeout.

**Complexity:** Low (1 hour)
**Dependencies:** None

---

### 0.3 Fix Broken Audio Players After Fresh Run

**Problem:** `runDailyFetchFromModal` always renders 3 `<audio>` tags (AI/World/China) without checking whether files exist — unlike `loadDailyFetchHistory` which gates on `has_*` flags. Result: broken 404 players when a step was skipped.

**Fix:** After the run completes, call `loadDailyFetchHistory(dateStr)` to render the correct audio section (same as the history view) instead of hardcoding `<audio>` tags.

**Complexity:** Low (1 hour)
**Dependencies:** None

---

### 0.4 Add Real Web Search Tool

**Problem:** "Explain This" tells the LLM to "search the web" but there's no `web_search` tool in `TOOL_SCHEMAS`. When auto-RAG fills context, `use_tools` is set to `false` and tools are disabled entirely.

**Fix:**
- Add `tool_web_search` using DuckDuckGo Instant Answer API (no API key needed) or `duckduckgo-search` package
- Register in `TOOL_SCHEMAS` alongside existing tools
- Keep `web_search` available even when RAG context is injected (only suppress RAG tools to avoid duplication, not web search)

**Complexity:** Low-Medium (half day)
**Dependencies:** `pip install duckduckgo-search`

---

### 0.5 Fix Stock Print Pollution

**Problem:** All stock modules use `print()` instead of `logging`. Noisy in server mode, invisible in structured log pipelines.

**Fix:** Replace `print(...)` with `logging.info(...)` / `logging.warning(...)` across: `scanner.py`, `llm_reasoning.py`, `features.py`, `fetch_market_data.py`, `watchlist.py`, `hot_sectors.py`, `fundamental_analysis.py`, `report_technical.py`, `sentiment.py`, `technical_analysis.py`. Keep `print` only inside `if __name__ == "__main__"` CLI blocks.

**Complexity:** Low (2 hours)
**Dependencies:** None

---

### 0.6 Clean Up Dead Code & Unused Flags

**Problem:**
- JS function `toolbarCommitFetch24` targets `#btnCommitFetch` which doesn't exist in the HTML (dead code)
- `has_pdf` is computed in `api_daily_fetch_history` but never used in `missing_steps` or UI — PDF failures are invisible
- Fear & Greed index in `market_sentiment.py` docs say "CNN" but code uses `alternative.me` (crypto proxy)

**Fix:**
- Remove `toolbarCommitFetch24` or add the corresponding toolbar button
- Add `has_pdf` to UI display and optionally to `missing_steps`
- Correct the doc comment in `market_sentiment.py` to say "alternative.me (crypto-derived)" instead of "CNN"

**Complexity:** Low (1 hour)
**Dependencies:** None

---

## Tier 1 — High Impact, Achievable Now

### 1.1 Automated Test Suite

**Problem:** Zero test coverage. Every change risks silent regressions across the ~8,000-line `agent.py`, stock pipeline, and RAG indexers.

**Plan:**
- Add `pytest` configuration and `tests/` directory structure
- Start with **integration tests** for critical paths:
  - Daily Fetch pipeline: mock fetch → verify merge → verify audio generation call
  - History endpoint: given known report files → verify correct stats/missing_steps
  - Stock features: given known OHLCV → verify feature matrix shape and column names
  - XGBoost: given synthetic features → verify walk-forward produces predictions
- Add **unit tests** for pure functions:
  - `_pick_wn_text`, `_build_audio_segments`, `merge_news`, `_tokenize` (BM25)
  - Feature engineering helpers, scoring functions
- Target: 60%+ coverage on stock and RAG modules

**Complexity:** Medium (2-3 days for framework + first 30 tests)
**Dependencies:** None
**Know-how:** [testing-python-apps.md](../learning/python-web/testing-python-apps.md)

---

### 1.2 Daily Fetch Auto-Scheduling

**Problem:** Daily Fetch requires manual "Run Today's Fetch" clicks. Users forget or are busy.

**Plan:**
- Add an **APScheduler** cron job to `agent.py` that triggers `_run_daily_fetch` at a configurable time (default: 08:00 local)
- Configurable via Global Settings: enable/disable, time, timezone
- Store schedule config in `_GLOBAL_SETTINGS`
- Add a "Last auto-run" indicator in the Daily Fetch modal
- On failure, retry once after 30 minutes; log results to a `daily-fetch-log.json`

**Complexity:** Low-Medium (1-2 days)
**Dependencies:** `pip install apscheduler`

---

### 1.3 World News Translation Recovery

**Problem:** The Chinese translation step in `run-world-news.py` sometimes fails (Ollama timeout), leaving source JSONs without a merged `world-news-data.json`. The `world_news_merge` recovery step merges without translation, losing Chinese titles/summaries.

**Plan:**
- Add a `world_news_translate` recovery step that:
  1. Loads existing `world-news-data.json` (merged but untranslated)
  2. Identifies items missing `title_zh`/`summary_zh`
  3. Translates only missing items via Ollama (batch of 10)
  4. Re-saves the merged file
- Add to `missing_steps` when merged data exists but >50% of items lack `title_zh`
- Timeout per batch: 60s with retry

**Complexity:** Low (half day)
**Dependencies:** Existing Ollama infrastructure

---

### 1.4 Email / Notification Digest

**Problem:** Daily Fetch results are only visible in the Jarvis UI. Users want a morning summary without opening the browser.

**Plan:**
- After Daily Fetch completes, generate a concise HTML email:
  - Key stats (AI items, world news, Chinese news counts)
  - Top 5 headlines per category
  - Audio file links (if accessible via local network)
  - Missing steps warnings
- Send via SMTP (configurable in Global Settings: SMTP server, recipient)
- Optional: Windows notification via `win10toast` or `plyer`

**Complexity:** Medium (1-2 days)
**Dependencies:** `smtplib` (stdlib) or `win10toast`

---

## Tier 2 — Strategic Improvements

### 2.1 Embedding Fine-Tuning Pipeline

**Problem:** Generic `all-MiniLM-L6-v2` embeddings work well but aren't optimized for Jarvis's domain (AI news, medical software, Chinese stock analysis).

**Plan:**
- **Phase 1: Training data generation** (from `plan-ml-integration.md` pending tasks)
  - Mine positive pairs from: user queries → clicked/used RAG chunks
  - Mine hard negatives from: retrieved-but-not-used chunks
  - Target: 5,000+ training pairs
- **Phase 2: Fine-tune**
  - Use `sentence-transformers` training API with `MultipleNegativesRankingLoss`
  - Train on domain-specific pairs while preserving general capability
  - Evaluate: MRR@5 and Recall@10 on held-out queries
- **Phase 3: Deploy**
  - Replace `all-MiniLM-L6-v2` with fine-tuned model
  - Re-index all content with new embeddings
  - A/B compare retrieval quality

**Complexity:** High (1-2 weeks)
**Dependencies:** Feedback data collection (partially implemented), GPU helpful but CPU trainable
**Know-how:** See [sentence-transformers.md](../learning/huggingface/sentence-transformers.md)

---

### 2.2 Stock Backtesting Engine

**Problem:** XGBoost predictions exist but there's no way to evaluate *"if I had followed these predictions for the last 6 months, what would my returns be?"*

**Plan:**
- New `scripts/stock/backtester.py`:
  - Walk-forward simulation: for each historical prediction, simulate buy/sell based on confidence threshold
  - Track: total return, max drawdown, Sharpe ratio, win rate per class
  - Compare: model vs buy-and-hold vs random
- UI integration: "Backtest" button per stock → chart showing equity curve
- Store results in `C:/reports/stock/backtests/{symbol}/`

**Complexity:** Medium-High (3-5 days)
**Dependencies:** `prediction_tracker.py` data, matplotlib or plotly for charts

---

### 2.3 Real-Time Stock Alerts

**Problem:** Predictions and signals are only visible when the user opens the Stock panel. No proactive notifications.

**Plan:**
- Background monitoring thread checking watchlist stocks at configurable intervals (default: every 30 minutes during market hours 9:30-15:00 CST)
- Alert triggers:
  - Price crosses predicted support/resistance
  - RSI enters overbought/oversold zone
  - Black swan detector fires on new news
  - Volume spike > 3x average
- Delivery: chat system message + optional desktop notification
- Configurable: per-stock alert rules, quiet hours

**Complexity:** Medium (2-3 days)
**Dependencies:** Market hours awareness, `fetch_market_data.py`

---

### 2.4 Multi-User Support

**Problem:** Jarvis is single-user. No authentication, no session isolation, no per-user settings.

**Plan:**
- **Phase 1: Session isolation**
  - Add a simple auth layer (username/password or SSO token)
  - Per-user session storage, settings, and note collections
  - Per-user RAG boosting (each user's queries weighted toward their own content)
- **Phase 2: Team features**
  - Shared knowledge base with personal annotations
  - Team Daily Fetch with individual notification preferences
  - Admin panel for user management

**Complexity:** High (1-2 weeks)
**Dependencies:** Architectural decision on auth method

---

## Tier 3 — Infrastructure & DevOps

### 3.1 Docker Containerization

**Problem:** Setup requires manual Python env, Ollama installation, and path configuration. Hard to reproduce or deploy to another machine.

**Plan:**
- `docker-compose.yml` with services:
  - `jarvis-agent`: Flask app + all scripts
  - `ollama`: Ollama server with pre-pulled models
  - `qdrant` (optional): External Qdrant instead of in-memory
- Volumes for `C:/reports/ai/` and RAG snapshot
- Environment variable configuration
- Health checks for Ollama and agent readiness

**Complexity:** Medium (2-3 days)
**Dependencies:** Docker Desktop on Windows, Ollama Docker image

---

### 3.2 CI/CD Pipeline

**Problem:** No automated quality gates. Changes go directly from editor to production.

**Plan:**
- GitHub Actions workflow:
  - **On PR:** lint (ruff/flake8), type check (mypy basic), run pytest suite
  - **On merge to main:** deploy notification, optional auto-restart of agent
- Pre-commit hooks: formatting (black), import sorting (isort), lint
- Badge in README showing test status

**Complexity:** Low-Medium (1-2 days, after tests exist)
**Dependencies:** Test suite (Tier 1.1), GitHub repository

---

### 3.3 Monitoring & Observability

**Problem:** No visibility into system health, performance, or error rates beyond terminal logs.

**Plan:**
- Structured logging with `structlog` or JSON formatter
- Key metrics: requests/sec, LLM latency (p50/p95), TTS duration, RAG search time
- Simple dashboard: `/api/health` endpoint with uptime, Ollama status, Qdrant collection stats, disk usage
- Optional: Prometheus metrics exporter → Grafana

**Complexity:** Medium (2-3 days)
**Dependencies:** None for basic; Prometheus/Grafana for advanced

---

## Tier 4 — New Feature Ideas

### 4.1 Meeting Summary Agent

**Problem:** Team meetings generate notes in Confluence/Teams but aren't indexed or actionable.

**Plan:**
- New indexer `index_meeting_notes.py` that processes:
  - Pasted meeting transcripts
  - Confluence meeting pages (filtered by template)
  - Uploaded audio (via Whisper or Azure Speech → text → index)
- Auto-extract: action items, decisions, participants, follow-ups
- Daily Fetch integration: "Yesterday's meetings" section with action item summary
- Tool: `tool_meeting_search` for RAG queries about past decisions

**Complexity:** High (1-2 weeks)
**Dependencies:** Whisper for audio (optional), Confluence meeting template

---

### 4.2 Code Review Assistant

**Problem:** Code review requires manual context-gathering. Jarvis has Git commit data but doesn't actively assist in reviews.

**Plan:**
- New toolbar action: "Review PR" — takes a PR URL or branch diff
- Pipeline:
  1. Fetch diff (via `git diff` or GitHub API)
  2. For each changed file: RAG search for related codebase context
  3. LLM analyzes: potential bugs, style issues, security concerns, missing tests
  4. Output: structured review with file-by-file comments
- Integration with GitHub PR comments (via `gh` CLI)

**Complexity:** Medium-High (3-5 days)
**Dependencies:** Git access, optional GitHub API token

---

### 4.3 Knowledge Graph Visualization

**Problem:** RAG search returns flat lists. Users can't see relationships between topics, people, and projects.

**Plan:**
- Build a lightweight knowledge graph from RAG payloads:
  - Nodes: people (authors), projects (sources), topics (extracted keywords)
  - Edges: "authored", "mentioned_in", "related_to" (cosine similarity > threshold)
- UI: interactive D3.js force-directed graph in a new modal
- Click a node → filter RAG search to that entity
- Auto-update on reindex

**Complexity:** High (1-2 weeks)
**Dependencies:** D3.js (frontend), entity extraction from chunks

---

### 4.4 Jarvis Mobile Companion

**Problem:** Jarvis UI is desktop-only. Audio podcasts are great for commuting but require accessing the desktop first.

**Plan:**
- **Phase 1: Mobile-responsive UI**
  - Refactor the monolithic HTML template for responsive layout
  - Touch-friendly controls for audio player, Daily Fetch modal
  - Service worker for offline audio playback
- **Phase 2: Progressive Web App (PWA)**
  - Manifest + service worker → installable on phone
  - Push notifications for Daily Fetch completion
  - Audio streaming endpoint for direct podcast access

**Complexity:** Medium-High (1 week for Phase 1)
**Dependencies:** Frontend refactoring

---

### 4.5 Personal Learning Tracker

**Problem:** Learning modes (AI Learning, Tech English, Casual English, AWS AIF-C01) generate content but don't track progress or spaced repetition. *(Partial progress: AWS AIF-C01 mode already has per-domain progress tracking via `.aws-cert-progress.json` — see `learning-features-impl.md` §12.)*

**Plan:**
- Track topics studied, time spent, and quiz scores
- Spaced repetition system (SRS): surface topics for review at optimal intervals
- Progress dashboard: topics mastered, streak, areas needing review
- Weekly learning report in Daily Fetch
- Exportable flashcards (Anki-compatible format)

**Complexity:** Medium (3-5 days)
**Dependencies:** Learning mode infrastructure (exists)

---

## Tier 5 — New Feature Ideas (April 2026 additions)

### 5.1 Smart Daily Digest Chat

**Problem:** Daily Fetch results are shown as static report files and system messages. Users can't interactively explore the content — e.g., "tell me more about headline #3" or "what does this mean for our Jira backlog?"

**Plan:**
- After Daily Fetch completes, auto-inject a structured summary into the chat session (not just a system message)
- Include: top 5 AI headlines, top 5 world news, Jira ticket summary, commit highlights, wiki changes
- The injected context enables immediate follow-up questions with full RAG support
- Optional: auto-start a "Daily Briefing" chat session with the summary pre-loaded

**Complexity:** Medium (1-2 days)
**Dependencies:** Daily Fetch pipeline, session management

---

### 5.2 Cross-Feature Intelligence

**Problem:** Features are siloed — black swan detection doesn't alert stock watchlist, AI News KB doesn't feed into Learning, commit summaries don't link to Jira tickets.

**Plan:**
- **Black Swan → Stock Alert:** When `black_swan_detector` fires on Daily Fetch news, auto-check watchlist stocks against `affected_industries` and inject a warning into the Stock modal
- **AI News KB → Learning:** When new topics appear in the AI News KB, suggest matching AI Learning lessons via a "Suggested topics" section
- **Commit Summary → Jira:** Parse branch names and commit messages for ticket IDs (e.g., `PROJ-123`) and auto-link them in the commit summary output

**Complexity:** Medium (2-3 days for all three connections)
**Dependencies:** Existing feature infrastructure

---

### 5.3 Interactive Two-Voice Podcast

**Problem:** Current audio narration is a single-voice monologue. Longer podcasts (10-15 min) can feel monotonous.

**Plan:**
- Generate a **two-voice conversation** script: host asks questions, analyst provides insights
- Use two different Edge TTS voices (e.g., `zh-CN-YunxiNeural` as host, `zh-CN-XiaoxiaoNeural` as analyst; `en-US-AndrewNeural` / `en-US-JennyNeural` for English)
- LLM generates a dialogue-format script instead of a monologue
- TTS generates segments per speaker, then merge with `ffmpeg`
- Configurable in Global Settings: monologue vs. dialogue mode

**Complexity:** Medium (2-3 days)
**Dependencies:** Existing segmented audio pipeline, Edge TTS

---

### 5.4 RAG Quality Dashboard

**Problem:** No visibility into RAG retrieval quality. Hard to know if embeddings are working well, which topics have coverage gaps, or which chunks are stale.

**Plan:**
- New modal accessible from toolbar (Data Analysis category)
- Metrics: retrieval hit rate, average similarity scores, query distribution by topic
- Stale content alerts: chunks not retrieved in 30+ days
- Most/least queried topics visualization
- Feedback correlation: chunks with positive/negative feedback scores
- Data source: `feedback_store.py` events + query logs

**Complexity:** Medium-High (3-5 days)
**Dependencies:** Feedback data, query logging (needs implementation)

---

### 5.5 Stock Portfolio Simulator

**Problem:** Watchlist tracks prices but doesn't support virtual trading or P&L tracking. No way to evaluate "what if I followed the model's recommendations?"

**Plan:**
- Add virtual buy/sell entries per watchlist stock (price, quantity, date)
- Track: unrealized P&L, realized P&L, total portfolio value
- Overlay XGBoost predictions to compare model vs. actual user decisions
- Portfolio summary card in the Stock modal
- Store in `C:/reports/stock/portfolio.json`

**Complexity:** Medium (2-3 days)
**Dependencies:** Watchlist infrastructure

---

### 5.6 Keyboard Shortcuts

**Problem:** Power users must click through toolbar menus. No keyboard-driven workflow.

**Plan:**
- `Ctrl+K` → Quick toolbar command palette (fuzzy search across all toolbar actions)
- `Ctrl+D` → Open Daily Fetch modal
- `Ctrl+S` → Open Stock modal
- `Ctrl+/` → Focus chat input
- `Escape` → Close any open modal
- Display shortcut hints on toolbar button tooltips

**Complexity:** Low (half day)
**Dependencies:** None

---

### 5.7 Daily Fetch Comparison View

**Problem:** No way to see trends across days — what's new in today's news vs. yesterday? Are Jira tickets being resolved or piling up?

**Plan:**
- Side-by-side or diff view of two Daily Fetch dates
- Highlight: new topics, resolved Jira tickets, commit velocity change
- Show trend arrows for item counts (AI news up/down, world news up/down)
- Accessible from the Daily Fetch modal's date navigator

**Complexity:** Medium (2-3 days)
**Dependencies:** Daily Fetch history data

---

## Priority matrix

```
                        Impact
                  Low ◄─────────► High
           ┌───────────┬──────────────────┐
  Instant  │ 0.6 Dead  │ 0.1 Silent errs  │
  (hours)  │    code   │ 0.2 Timeouts     │
           │ 0.5 Print │ 0.3 Audio fix    │
           │    logs   │ 5.6 Shortcuts    │
           ├───────────┼──────────────────┤
  Quick    │ 3.2 CI    │ 0.4 Web search   │
  (days)   │ 1.3 WN    │ 1.1 Tests        │
           │  recovery │ 1.2 Schedule     │
           │           │ 5.1 Digest Chat  │
           │           │ 5.2 Cross-Intel  │
           ├───────────┼──────────────────┤
  Slow     │ 3.3 Mon   │ 2.1 Finetune     │
  (weeks)  │ 4.5 SRS   │ 2.2 Backtest     │
           │           │ 5.3 Two-Voice    │
           │           │ 5.4 RAG Dash     │
           │           │ 4.1 Meetings     │
           └───────────┴──────────────────┘
```

## Suggested execution order

1. **Tier 0 (0.1–0.6)** → Fix bugs and code health first (1 day total)
2. **1.1 Tests** → Foundation for everything else
3. **1.2 Auto-scheduling** → Immediate daily value
4. **5.1 Smart Digest Chat** → Multiplies value of Daily Fetch
5. **5.2 Cross-Feature Intelligence** → Connects existing features
6. **1.3 Translation recovery** → Quick fix for existing pain
7. **1.4 Email digest** → User-requested enhancement
8. **5.3 Two-Voice Podcast** → Engaging audio experience
9. **3.1 Docker** → Reproducibility before scaling
10. **2.2 Backtesting** → Validates stock prediction value
11. **5.4 RAG Quality Dashboard** → Visibility into retrieval quality
12. **2.1 Embedding fine-tuning** → RAG quality leap
13. **Tier 4 + remaining Tier 5** → Based on user demand

---

## Appendix: Technology candidates

| Enhancement | New tech needed | Existing alternative |
|-------------|----------------|---------------------|
| Web search tool | `duckduckgo-search` | None (model hallucination) |
| Auto-scheduling | APScheduler | Windows Task Scheduler (external) |
| Email digest | smtplib (stdlib) | — |
| Two-voice podcast | None (Edge TTS multi-voice) | Single-voice monologue |
| Backtesting | matplotlib/plotly | Console-only reports |
| Docker | Docker Desktop | Manual setup docs |
| CI/CD | GitHub Actions | Manual testing |
| Meeting transcription | OpenAI Whisper | Manual paste |
| Knowledge graph | D3.js | Flat search results |
| Mobile | PWA / service workers | Desktop browser only |
| Monitoring | structlog + Prometheus | Print-to-console logging |
| Keyboard shortcuts | None (vanilla JS) | Mouse-only toolbar |
| RAG dashboard | Chart.js or lightweight charting | No visibility |
| Portfolio simulator | None (JSON storage) | Watchlist view-only |
