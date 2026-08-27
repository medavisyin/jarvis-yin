# Memory: Wiki Fetch Readable Per-Page Summaries

**Generated**: 2026-08-22 ~16:20 UTC+8
**Last updated**: 2026-08-22 ~16:45 UTC+8
**Project**: c:\jarvis
**Focus**: Keep Wiki Fetch ingest; replace raw diffs with 1–2 sentence English summaries

---

## Goal & Scope (required)

Wiki Fetch already fetches Confluence pages for selected people/dates and indexes chunks into RAG. The chat report is unreadable: truncated `difflib` Added/Removed lines, heading dumps, and leaked blog-macro HTML. Replace that human-facing summary only.

---

## Key Decisions (required)

1. **Summary-only change**: Team-member picker, date range, and RAG chunk/index pipeline stay as-is.
2. **Per-page shape**: Title + Confluence link + space + modified date + 🆕 for new pages; 1–2 English sentences on what changed and why it matters.
3. **Shared summarizer**: Toolbar Wiki Fetch and Daily Fetch use the same summary function/prompt so the two paths do not diverge.
4. **Rejected: full Wiki Fetch redo**: Selection UI and ingest are not in scope.
5. **Rejected: Chinese summaries**: User chose English.
6. **Rejected: per-person bullets or theme digest**: User chose per-page.
7. **On Ollama failure**: Do not paste raw diffs; omit the blurb. Still index the page into RAG.
8. **Approach B**: Shared `wiki_summary.py`; clean macro/layout noise; if cleaned diff is too thin, use content excerpt; LLM writes 1–2 English sentences (what + why it matters).
9. **Rejected A**: Wire existing Daily Fetch summarizer as-is (garbage-in still possible).
10. **Rejected C**: Change `_compute_change_summary` in the fetch script.
11. **No page cap**: one Ollama call per page, same as Daily Fetch today.
12. **Architecture approved**: new module; toolbar + Daily Fetch call sites; `index_confluence_user.py` and picker unchanged.

---

## Confirmed Assumptions (required)

- The pasted Jan Loeffler block is toolbar `_build_wiki_report` output (raw `change_summary` truncated to 300 chars), not Daily Fetch AI summaries.
- Daily Fetch already has `_wiki_ai_summary` (Ollama, `qwen3:1.7b`) but toolbar Wiki Fetch does not call it.
- Drop raw Added/Removed dumps and leaked HTML from the report.
- Drop the `Sections:` line as TOC noise unless a later design step argues to keep it.
- Improving Daily Fetch's prompt is in scope (same “what + why it matters” quality).

---

## Constraints & Non-Goals (include when relevant)

- Do not change `/api/toolbar/wiki-fetch` user/date inputs.
- Do not change `index_confluence_user.py` RAG chunking/indexing behavior for this task (summary text in the report only).
- Reuse existing Ollama host/model settings.

---

## Key Discoveries (required)

- `scripts/rag/routes/toolbar.py` `_build_wiki_report` dumps `change_summary[:300]` + first 5 headings.
- `scripts/rag/index_confluence_user.py` `_compute_change_summary` uses `difflib.unified_diff`; Confluence blog macros leak (`false center https://...`).
- `scripts/rag/routes/daily_fetch.py` `_wiki_ai_summary` already asks for 1–2 sentences of *what changed*, not *why it matters*, and is nested inside the daily-fetch step (not shared with toolbar).
- Example noise: `Security & Compliance` → `> 1`; `Tech-Update Juli 2026` → blog layout attributes.

---

## Current State (required)

- **Working**: Shared summaries; 🆕 pages with junk macros still get a topic summary from title/space/headings
- **Pending**: User re-runs Wiki Fetch after Jarvis restart
- **Blocked**: none

---

## Next Steps (required)

1. [x] Trigger `brainstorming` — design B approved; execute directly
2. [x] RED: `tests/test_wiki_summary.py` (`ModuleNotFoundError: wiki_summary`)
3. [x] GREEN: `python -m pytest tests/test_wiki_summary.py -v` → **10 passed**; `py_compile` on module + toolbar + daily_fetch
4. [ ] User: run Wiki Fetch for Jan Loeffler and confirm no raw diffs / Sections / leaked HTML
5. [ ] Optional: `requesting-code-review`

---

## Notes for Next Session (include when relevant)

- Loaded this session: `memory-20260821-daily-fetch-audio-global-lang.md` (unrelated audio-lang work).
- User-facing copy in Jarvis UI can stay English for this report.

---

## References (required)

- `scripts/rag/routes/toolbar.py` — `_build_wiki_report`, `POST /api/toolbar/wiki-fetch`
- `scripts/rag/routes/daily_fetch.py` — `_wiki_ai_summary`, wiki report write
- `scripts/rag/index_confluence_user.py` — `_compute_change_summary`, `REPORT_JSON`
- `scripts/rag/templates/index.html` — Wiki Fetch modal + result render
- `docs/implementation/rag/index-confluence-impl.md` — change_summary vs AI summary

---

**Confirmed at**: 2026-08-22 ~16:20 UTC+8
