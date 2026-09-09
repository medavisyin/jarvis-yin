# Memory: Intensive Reading Progress Memory Error

**Generated**: 2026-09-02 16:10
**Last updated**: 2026-09-03 14:02
**Project**: c:\jarvis
**Focus**: Next/Back in Intensive Reading shows "Failed to write conversation memory"

---

## Goal & Scope (required)

When reading a book in Intensive Reading (web RAG UI), clicking Next or Back POSTs `/api/intensive-reading/progress`. If `save_progress()` returned `None`, the UI toasted "Failed to write conversation memory". User wanted this diagnosed and fixed so Next/Back saves progress without that error.

Out of scope unless required for the fix: analysis tabs, prompts, magazine vs novel reading UX.

---

## Key Decisions (required)

1. **Diagnose and fix, not hide**: Next/Back must actually persist progress; do not only suppress the toast.
2. **Reversed: Keep conversation-memory progress as the only store**: That path (embed + in-memory Qdrant + snapshot) failed in a long-lived agent process while reads still worked. Exceptions were swallowed, so the UI only showed a generic toast.
3. **Approach C approved and implemented**: `docs/books/{id}/meta.json` `progress` is source of truth. Conversation memory write is best-effort (logged, no toast).
4. **Rejected: Harden memory-only (Approach A)**: Toast would still appear whenever Qdrant/embed write fails.
5. **Rejected: Drop conversation memory entirely (Approach B)**: Keep best-effort memory so chat context can still see IR progress when that store works.
6. **Smallest change**: do not change unrelated Intensive Reading features.
7. **Skipped code review (2026-09-03)**: User declined `requesting-code-review` after the logical unit completed.

---

## Confirmed Assumptions (required)

- Surface is the web RAG Intensive Reading UI (`scripts/rag/templates/index.html`), not a separate Android-only flow.
- Toast only fires when POST `/api/intensive-reading/progress` returns `ok === false` (or HTTP error).
- Jarvis Agent must be restarted to pick up `progress.py` / route changes (HTML was not changed).

---

## Key Discoveries (required)

- Old `save_progress()` returned `None` on import failure of `memory.store` or on `add_memory()` exception (exceptions swallowed, no log).
- Progress facts use `MemoryType.FACT` with `kind=intensive_reading_progress`; they are excluded from RAG retrieval via `_EXCLUDED_FACT_KINDS` in `memory/retriever.py`.
- Live repro (agent PID started 2026-08-31 13:22): POST `/api/intensive-reading/progress` returned the warning in ~20ms; GET `/api/memory` listed 12 IR progress facts, newest timestamp 2026-08-31 11:00 (before that process started). No new point appeared after the failed POST → failure at or before upsert (embedding or Qdrant write), not merely snapshot.
- Isolated `save_progress`/`add_memory` in a new Python process succeeded; restarted agent also wrote `ok: true`. The Aug 31 process could read memory but not write. Inner exception was never logged; process was replaced before a traceback could be captured.
- Analysis cache already persists to local JSON; progress was the odd path requiring embeddings + Qdrant on every Next/Back.
- Related existing memory: `docs/memory/memory-20260728-intensive-reading.md` (original progress-in-conversation-memory decision).

---

## Runtime Evidence (include when relevant)

- POST live (old process): `{"ok":false,"warning":"Failed to write conversation memory"}` HTTP 200 TIME=0.020s
- GET `/api/memory` (old process): count=12, all `intensive_reading_progress` facts
- RED: `tests/test_intensive_reading_progress_routes.py::test_save_progress_persists_to_meta_when_memory_write_fails` failed `assert data.get("ok") is True` with `{'ok': False, 'warning': 'Failed to write conversation memory'}`
- GREEN: `python -m pytest tests/test_intensive_reading_progress_routes.py tests/test_intensive_reading_analysis_cache.py tests/test_intensive_reading_delete_book.py -q` → **28 passed**
- Live POST after fix + agent restart: `{"ok":true,"memory_id":"7a8f6798-...","chunk_index":2}` TIME=0.144s
- `docs/books/a-promised-land-83279aae/meta.json` progress: `{chunk_index: 2, total: 308, title: A Promised Land}`
- GET book returns the same `progress` for resume

---

## Current State (required)

- **Working**: Next/Back progress saves to `meta.json`; POST returns `ok: true` even when conversation memory write fails; no toast. Agent was restarted with this code.
- **Pending**: None for this bug.
- **Blocked**: None.

---

## Next Steps (required)

1. [x] Trigger `brainstorming` / `systematic-debugging`
2. [x] Reproduce / inspect conversation-memory write path
3. [x] User chose Approach C
4. [x] Implement with TDD (meta.json source of truth + best-effort memory)
5. [x] Verify Next/Back progress API without the toast; resume from GET book
6. [ ] Commit only if the user asks (not requested)

---

## Notes for Next Session (include when relevant)

- If the toast reappears, the running agent likely still has old code — restart Jarvis Agent.
- Conversation-memory write failures are now logged (`IR progress: conversation memory write failed`) and do not affect resume.
- Old books without `meta.json` progress still fall back to conversation-memory facts until the next Next/Back migrates them.

---

## References (required)

- `scripts/rag/routes/intensive_reading.py` -- `api_save_progress` always `ok: true` after meta write
- `scripts/rag/intensive_reading/progress.py` -- meta.json primary, memory best-effort
- `scripts/rag/intensive_reading/ingest.py` -- `update_meta_fields` / `load_meta`
- `scripts/rag/templates/index.html` -- toast only when `ok === false`; resume from `meta.progress.chunk_index`
- `scripts/rag/memory/store.py` -- Qdrant conversation memory store (optional path)
- `tests/test_intensive_reading_progress_routes.py` -- includes memory-failure save/resume test

---

**Confirmed at**: 2026-09-03 14:02
