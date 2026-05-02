---
tags:
  - implementation
  - learning
  - deep-dive
  - notes
category: learning
status: current
last-updated: 2026-05-02
---

# Deep Dive Sessions & Notes System

> **Category**: LEARNING | **Sources**: `scripts/rag/routes/toolbar.py`, `scripts/rag/agent.py`, `scripts/rag/prompts.py`, `scripts/rag/router.py`

## Overview

**Deep dive** lets a user start a **new chat session** from a Learning Guide URL, optional `raw/*.md` path, and title: the toolbar API fetches or reads content, truncates it for the LLM context, seeds the session with an initial user message, and stores metadata (`source_url`, `title`, `raw_file`, `fetch_error`). **My Notes** is a separate JSON-backed CRUD API for short notes with optional `tags`, `session_id`, and `session_type`, persisted next to reports.

### Deep Dive vs Explain This

These are **distinct features** despite sharing a similar goal (learning about a topic):

| Aspect | Deep Dive | Explain This |
|--------|-----------|-------------|
| **Trigger** | Click button on Learning Guide article | Manual topic entry via toolbar modal |
| **Creates new session?** | Yes — dedicated `deep_dive` session with UUID | No — sends message in current session |
| **Content source** | Fetches original article URL or reads `raw/*.md` | Relies on RAG knowledge base + LLM |
| **System prompt** | `SYSTEM_PROMPT_DEEP_DIVE` (tutor mode) | Current session's system prompt |
| **Depth options** | Always deep (comprehensive tutor) | User chooses: "quick overview" or "deep dive" |
| **Web search** | No — uses fetched article content | Optional checkbox |
| **Session persistence** | Full session with `deep_dive_meta` on disk | Just a message in the conversation |
| **UI location** | Green button inside rendered Learning Guide | Toolbar → Usage Tools → "Explain This" |

## Architecture & Design

### Workflow Diagram

```text
┌──────────────────────────────────────────────────────────────────┐
│                     DAILY FETCH PIPELINE                         │
│  run-all-sources.py → raw/*.md articles → generate_learning_guide│
│  → learning-guide.md (difficulty-rated reading list)             │
└─────────────────────────┬────────────────────────────────────────┘
                          │ rendered in Daily Fetch modal
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                     FRONTEND (index.html)                        │
│  1. Detects filename = "learning-guide*"                         │
│  2. Injects "📖 Deep Dive" button per article entry              │
│  3. Button extracts: title, source URL, raw file path            │
│  4. onClick → startDeepDive(title, sourceUrl, rawFile)           │
└─────────────────────────┬────────────────────────────────────────┘
                          │ POST /api/toolbar/deep-dive
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                BACKEND — api_toolbar_deep_dive                   │
│  (scripts/rag/routes/toolbar.py:195–256)                         │
│                                                                  │
│  1. Validate: source_url or title required                       │
│  2. If source_url → _fetch_source_url_content (httpx + proxy)    │
│     └─ HTML detected? → _html_to_text (strip scripts/styles/nav)│
│  3. If raw_file & no fetched content → _read_raw_file_content    │
│     └─ Scans last 7 days: REPORTS_ROOT/{date}/{raw_file}         │
│  4. Truncate content to 8,000 chars                              │
│  5. Build teaching_context (topic + source URL + content)         │
│  6. Create session_data:                                         │
│     - id: random UUID                                            │
│     - session_type: "deep_dive"                                  │
│     - deep_dive_meta: {source_url, title, raw_file, fetch_error} │
│     - messages: [initial user prompt]                             │
│  7. _save_session_file → return {session_id, title}              │
└─────────────────────────┬────────────────────────────────────────┘
                          │ client loads session, auto-sends
                          │ "Please teach me about this topic."
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                   CHAT — POST /api/agent                         │
│                                                                  │
│  1. route_session(session_id) loads session file                 │
│     └─ session_type == "deep_dive" detected                      │
│  2. Returns: is_deep_dive=True, SYSTEM_PROMPT_DEEP_DIVE          │
│  3. Intent: LEARNING_DEEP_DIVE                                   │
│  4. LLM receives tutor prompt + article content + user question  │
│  5. Ongoing Q&A in the dedicated session                         │
└──────────────────────────────────────────────────────────────────┘
```

### System Context

Deep dives are **not** fixed UUID sessions: `api_toolbar_deep_dive` creates a new `session_id` (random UUID) and sets `session_type: deep_dive`. Subsequent `/api/agent` calls load that session; `route_session()` in `router.py` detects the type and applies `SYSTEM_PROMPT_DEEP_DIVE`.

### Data Flow

1. **Create session** — `api_toolbar_deep_dive` validates `source_url` or `title` (`toolbar.py:201–202`).
2. **Fetch** — If `source_url`, `_fetch_source_url_content` uses `httpx` with `BRIEFING_PROXY`, detects HTML vs plain, strips tags via `_html_to_text` (`agent.py:173–199`).
3. **Raw fallback** — If `raw_file` and no fetched content, `_read_raw_file_content` scans last 7 days under `REPORTS_ROOT/{date}/{raw_file}` (`agent.py:222–233`).
4. **Context build** — `teaching_context` includes topic, source URL, truncated body (max 8000 chars) (`toolbar.py:223–230`).
5. **Initial message** — User-role prompt asks for a comprehensive explanation (`toolbar.py:232–235`).
6. **Persistence** — `session_data` with `deep_dive_meta`; `_save_session_file` (`toolbar.py:237–256`).
7. **Routing** — `route_session` detects `session_type == "deep_dive"` and returns `SYSTEM_PROMPT_DEEP_DIVE` (`router.py:35–83`).
8. **Intent** — Mapped to `Intent.LEARNING_DEEP_DIVE` via `session_type_to_intent()` (`intent.py:246`).

### Key Design Decisions

- **httpx + HTML stripping** rather than a headless browser — simpler ops; JS-heavy sites may return incomplete text (`agent.py:173–199`).
- **8k truncation** — Balances source fidelity with `num_ctx` limits (`toolbar.py:227–229`).
- **Notes file in REPORTS_ROOT** — Keeps user data with other Jarvis artifacts (`NOTES_FILE` in config).
- **Session linking** — Notes accept `session_id` / `session_type` for client-side association; no server-side FK enforcement.

## Implementation Details

### Core Components

| Piece | File | Lines | Role |
|-------|------|-------|------|
| `api_toolbar_deep_dive` | `routes/toolbar.py` | 194–256 | POST handler: fetch, truncate, create session. |
| `_fetch_source_url_content` | `agent.py` | 173–199 | httpx GET with proxy, `_html_to_text` for HTML. |
| `_html_to_text` | `agent.py` | 202–219 | Regex strip scripts/styles/nav/footer/header, unescape, tag removal. |
| `_read_raw_file_content` | `agent.py` | 222–233 | Resolves `raw_file` under recent 7 days of report dates. |
| `SYSTEM_PROMPT_DEEP_DIVE` | `prompts.py` | 275–289 | Tutor behavior prompt for briefing-derived topics. |
| `route_session` | `router.py` | 35–83 | Detects `deep_dive` session type, returns prompt. |
| `Intent.LEARNING_DEEP_DIVE` | `intent.py` | 50, 246 | Intent enum and session-type mapping. |
| `startDeepDive` | `index.html` | 1543–1565 | Frontend JS: calls API, loads session, sends first message. |
| Learning Guide button injection | `index.html` | 1515–1534 | Injects "Deep Dive" buttons when rendering `learning-guide*` files. |
| `_load_notes` / `_save_notes` | `agent.py` | 1279–1296 | JSON list persistence. |
| `api_notes_*` | `agent.py` | 1302–1366 | REST-style notes CRUD. |

### Frontend Flow

1. **Button injection**: When the file preview detects a filename starting with `learning-guide`, it regex-matches each numbered article entry and injects a green "Deep Dive" button (`index.html:1515–1534`).
2. **Metadata extraction**: The button's `onclick` passes the article **title**, **source URL** (from `Source:` line), and **raw file path** (from `File:` line).
3. **Session creation**: `startDeepDive()` POSTs to `/api/toolbar/deep-dive`, then calls `refreshSessionList()` and `loadSession(data.session_id)` to switch to the new session (`index.html:1543–1565`).
4. **Auto-send**: After loading, it sets `queryInput.value = 'Please teach me about this topic.'` and calls `sendMessage()` to trigger the first LLM response.

### API Surface

- `POST /api/toolbar/deep-dive` — JSON: `source_url`, `title`, `raw_file`; returns `session_id`, `title`.
- `GET /api/notes?tag=` — list, sorted by `created_at` desc.
- `POST /api/notes` — body: `content`, optional `title`, `tags`, `session_id`, `session_type`.
- `PUT /api/notes/<note_id>` — `content` required.
- `DELETE /api/notes/<note_id>`.
- `POST /api/agent` — ongoing deep-dive chat with returned `session_id`.

### Configuration

- `NOTES_FILE` — `os.path.join(REPORTS_ROOT, ".learning-notes.json")` (`scripts/config.py:38`).
- `REPORTS_ROOT` — env `JARVIS_REPORTS_ROOT` or default `C:/reports/ai`.
- Proxy: `BRIEFING_PROXY` for URL fetch (`agent.py:180`).
- Session directory: `CHAT_SESSIONS_DIR` (`scripts/config.py:37`).

### Error Handling & Edge Cases

- Fetch errors stored in `deep_dive_meta.fetch_error` while still allowing title-only sessions (`toolbar.py:205–208`).
- If no content and no title → 400 (`toolbar.py:215–216`).
- Session save failure → 500 (`toolbar.py:253–254`).
- Notes: missing note on update/delete → 404; empty content → 400.

## Improvement Ideas

### Short-term

- **Playwright or readability** — For SPAs/paywalled content, optional headless fetch behind a flag (current code is httpx-only).
- Increase truncation selectively when `run_agent` selects higher `num_ctx`.

### Medium-term

- **Export notes to Markdown** — Batch export from `.learning-notes.json`.
- **Note ↔ session linking** — Server validate `session_id` exists; show deep-dive title in note list API.

### Long-term

- **Collaborative notes** — Multi-user tags or shared collections.
- **Flashcards / review reminders** — Derive cards from note content or deep-dive transcripts with spaced repetition.

## References

- `scripts/rag/routes/toolbar.py` — `api_toolbar_deep_dive` (194–256).
- `scripts/rag/agent.py` — `_fetch_source_url_content` (173–199), `_html_to_text` (202–219), `_read_raw_file_content` (222–233), notes CRUD (1279–1366).
- `scripts/rag/prompts.py` — `SYSTEM_PROMPT_DEEP_DIVE` (275–289).
- `scripts/rag/router.py` — `route_session` deep_dive detection (35–83).
- `scripts/rag/intent.py` — `Intent.LEARNING_DEEP_DIVE` (50, 246).
- `scripts/rag/templates/index.html` — Learning Guide button injection (1515–1534), `startDeepDive` (1543–1565), `startExplainThis` (1229–1259).
- `scripts/config.py` — `NOTES_FILE` (38), `CHAT_SESSIONS_DIR` (37), `REPORTS_ROOT`.
- `scripts/tools/generate_learning_guide.py` — Generates the difficulty-rated reading list that triggers deep dives.
