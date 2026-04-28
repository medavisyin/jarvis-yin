---
tags:
  - implementation
  - learning
  - deep-dive
  - notes
category: learning
status: current
last-updated: 2026-04-28
---

# Deep Dive Sessions & Notes System

> **Category**: LEARNING | **Source**: `scripts/rag/agent.py`, `scripts/config.py`

## Overview

**Deep dive** lets a user start a **new chat session** from a Learning Guide URL, optional `raw/*.md` path, and title: the toolbar API fetches or reads content, truncates it for the LLM context, seeds the session with an initial user message, and stores metadata (`source_url`, `title`, `raw_file`, `fetch_error`). **My Notes** is a separate JSON-backed CRUD API for short notes with optional `tags`, `session_id`, and `session_type`, persisted next to reports.

## Architecture & Design

### System Context

Deep dives are **not** fixed UUID sessions: `api_toolbar_deep_dive` creates a new `session_id` (random UUID) and sets `session_type: deep_dive`. Subsequent `/api/agent` calls load that session; if `session_type == "deep_dive"`, `SYSTEM_PROMPT_DEEP_DIVE` is applied (`2047–2050`).

```text
POST /api/toolbar/deep-dive { source_url?, title?, raw_file? }
  → _fetch_source_url_content OR _read_raw_file_content
  → truncate to 8000 chars
  → _save_session_file (messages: [initial user prompt], deep_dive_meta)
Client opens chat with returned session_id
  → POST /api/agent → run_agent(..., SYSTEM_PROMPT_DEEP_DIVE)

Notes (parallel): GET/POST /api/notes, PUT/DELETE /api/notes/:id
  → .learning-notes.json
```

### Data Flow

1. **Create session** — `api_toolbar_deep_dive` validates `source_url` or `title` (`2957–2964`).
2. **Fetch** — If `source_url`, `_fetch_source_url_content` uses `httpx` with `BRIEFING_PROXY`, detects HTML vs plain, strips tags via `_html_to_text` (`1737–1783`).
3. **Raw fallback** — If `raw_file` and no fetched content, `_read_raw_file_content` scans last 7 days under `REPORTS_ROOT/{date}/{raw_file}` (`1786–1797`).
4. **Context build** — `teaching_context` includes topic, source URL, truncated body (max 8000 chars) (`2985–2992`).
5. **Initial message** — User-role prompt asks for a comprehensive explanation (`2994–2997`).
6. **Persistence** — `session_data` with `deep_dive_meta`; `_save_session_file` (`2999–3016`).
7. **Agent** — `run_agent` receives history including the seeded message; system prompt is deep-dive tutor (`1449–1463`, `2047–2050`).

**Notes:** `api_notes_list` optional `tag` filter; create generates UUID, timestamps; update requires new content and refreshes title from first line (`2746–2809`).

### Key Design Decisions

- **httpx + HTML stripping** rather than a headless browser — simpler ops; JS-heavy sites may return incomplete text (`1737–1763`).
- **8k truncation** — Balances source fidelity with `num_ctx` limits (`2989–2991`).
- **Notes file in REPORTS_ROOT** — Keeps user data with other Jarvis artifacts (`NOTES_FILE` in config).
- **Session linking** — Notes accept `session_id` / `session_type` for client-side association; no server-side FK enforcement (`2767–2768`).

## Implementation Details

### Core Components

| Piece | Role |
|--------|------|
| `api_toolbar_deep_dive` | POST handler: fetch, truncate, create session (`2957–3018`). |
| `_fetch_source_url_content` | httpx GET, `_html_to_text` for HTML (`1737–1763`). |
| `_read_raw_file_content` | Resolves `raw_file` under recent report dates (`1786–1797`). |
| `_html_to_text` | Regex strip scripts/styles/nav/footer/header, unescape, tag removal (`1766–1783`). |
| `SYSTEM_PROMPT_DEEP_DIVE` | Tutor behavior for briefing-derived topics (`1449–1463`). |
| `api_agent` | Loads session file; applies deep dive prompt when `session_type == deep_dive` (`2047–2050`). |
| `_load_notes` / `_save_notes` | JSON list persistence (`2724–2743`). |
| `api_notes_list` / `api_notes_create` / `api_notes_update` / `api_notes_delete` | REST-style notes CRUD (`2746–2809`). |

### API Surface

- `POST /api/toolbar/deep-dive` — JSON: `source_url`, `title`, `raw_file`; returns `session_id`, `title` (`2957–3018`).
- `GET /api/notes?tag=` — list, sorted by `created_at` desc (`2746–2753`).
- `POST /api/notes` — body: `content`, optional `title`, `tags`, `session_id`, `session_type` (`2756–2775`).
- `PUT /api/notes/<note_id>` — `content` required (`2778–2797`).
- `DELETE /api/notes/<note_id>` (`2800–2809`).
- `POST /api/agent` — ongoing deep-dive chat with returned `session_id`.

### Configuration

- `NOTES_FILE` — `os.path.join(REPORTS_ROOT, ".learning-notes.json")` (`scripts/config.py` line 37).
- `REPORTS_ROOT` — env `JARVIS_REPORTS_ROOT` or default `C:/reports/ai`.
- Proxy: `BRIEFING_PROXY` for URL fetch (`1744`, `1749`).
- Session directory: `CHAT_SESSIONS_DIR` (`2980`, `3015`).

### Error Handling & Edge Cases

- Fetch errors stored in `deep_dive_meta.fetch_error` while still allowing title-only sessions (`2967–2977`, `3012`).
- If no content and no title → 400 (`2977–2978`).
- Session save failure → 500 (`3015–3016`).
- Notes: missing note on update/delete → 404 (`2790–2791`, `2805–2806`); empty content → 400 (`2759–2761`, `2781–2783`).

## Code Walkthrough

- **Deep dive route** — `api_toolbar_deep_dive` assembles `session_data` including `messages` and `deep_dive_meta` (`2957–3016`).
- **URL fetch** — Status check, content-type heuristic, HTML path vs raw text (`1751–1758`).
- **Agent hook** — `_load_session_file(session_id)` and `session_type` gate (`2047–2050`).
- **Notes list filter** — Case-insensitive tag membership (`2749–2751`).
- **Note shape** — `id`, `content`, `title` (default first 80 chars), `tags`, `session_id`, `session_type`, `created_at`; update adds `updated_at` (`2762–2770`, `2792–2794`).

## Improvement Ideas

### Short-term

- **Playwright or readabilty** — For SPAs/paywalled content, optional headless fetch behind a flag (current code is httpx-only).
- Increase truncation selectively when `run_agent` selects higher `num_ctx`.

### Medium-term

- **Export notes to Markdown** — Batch export from `.learning-notes.json`.
- **Note ↔ session linking** — Server validate `session_id` exists; show deep-dive title in note list API.

### Long-term

- **Collaborative notes** — Multi-user tags or shared collections.
- **Flashcards / review reminders** — Derive cards from note content or deep-dive transcripts with spaced repetition.

## References

- `scripts/rag/agent.py` — `SYSTEM_PROMPT_DEEP_DIVE`, `_fetch_source_url_content`, `_read_raw_file_content`, `_html_to_text`, `api_toolbar_deep_dive`, notes helpers and routes, `api_agent` deep-dive detection (`1449–1463`, `1737–1797`, `2724–2809`, `2957–3018`, `2047–2050`).
- `scripts/config.py` — `NOTES_FILE`, `REPORTS_ROOT`, `CHAT_SESSIONS_DIR`.
