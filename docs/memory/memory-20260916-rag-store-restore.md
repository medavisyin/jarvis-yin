# Memory: RAG Store Dropped to 256 Chunks

**Generated**: 2026-09-16 ~11:30
**Last updated**: 2026-09-16 ~11:30
**Project**: c:\jarvis
**Focus**: Search UI `:18888` showed 256 chunks; restore from Sep 1 snapshot + backfill

---

## Goal & Scope (required)

User opened `http://127.0.0.1:18888/` and saw **256 chunks** instead of ~10k from months of briefings. Confirm whether data was gone, then restore.

In scope:
- Diagnose why the live snapshot shrank
- Restore vectors without wiping source briefings/books
- Bring Search UI and Agent back onto the restored store

Out of scope (not done this session):
- Fix `_merge_snapshot` so a failed `json.load` cannot overwrite the whole store
- Delete leftover `.rag-store.json.tmp-*` files

---

## Key Decisions (required)

1. **Loaded** `memory-20260915-national-team-etf-flow.md` at session start (unrelated topic).
2. **Restore path A**: copy `.rag-store.json.tmp-11224` (complete **7784** chunks, 2026-09-01) over the live store, then re-index `2026-09-01`…`2026-09-16` date folders and local books onto the same Qdrant client, one save. Rejected full 105-folder backfill as slower.
3. **Do not call** `intensive_reading.ingest._merge_snapshot` during restore — that function is what can wipe the store.
4. **Keep backups**: current 256-file and the 7784 tmp, both copied aside before overwrite.

---

## Confirmed Assumptions (required)

- Banner `Indexed chunks: N` is `get_stats()` reading `.rag-store.json` `count`, not a UI cap.
- Original briefing folders under `C:/reports/ai/YYYY-MM-DD` and `docs/books/` were never deleted.
- User chose restore-from-tmp + backfill, not “fix bug only”.

---

## Constraints & Non-Goals (include when relevant)

- Do not `git rm` `docs/books/` without `--cached`.
- Do not treat Search UI library count as source of truth while two processes listen on 18888 (Windows allowed duplicate LISTEN; stale process served 7784).

---

## Key Discoveries (required)

- Live `C:/reports/ai/.rag-store.json` was overwritten **2026-09-16 08:04:59** to 2.67MB / **256** points: 108 Economist (uploaded 2026-09-15 16:00) + today’s briefing. Format was `index_briefing._save_snapshot` (`points`+`count`, no `saved_at`).
- **Wipe mechanism**: `scripts/rag/intensive_reading/ingest.py` `_merge_snapshot` does `json.load`; on any exception it sets `data = {"points": []}` and **replaces the entire snapshot** with only the new book points. Search/agent use `snapshot_io.load_snapshot_dict` (keeps first JSON); this merge path does not.
- Likely sequence: 2026-09-15 16:00 Economist index wiped store to 108; 2026-09-16 08:00 daily fetch `index_briefing.py` loaded that tiny store, added today, saved 256. `_index_briefing_warn` timeout is 180s — loading a huge store can also fail this subprocess.
- Recoverable complete snapshot: `C:/reports/ai/.rag-store.json.tmp-11224` ends with `"count": 7784}` (2026-09-01 08:03). Many other `.tmp-*` files are **truncated** (no closing `count`).
- After restore: **10134** unique UUID points, all 384-d vectors. Source date folders still **105** (`2026-04-07` … `2026-09-16`).
- Stale Search UI can keep serving old in-memory Qdrant while disk `count` already shows 10134. Kill duplicate `:18888` LISTEN PIDs.

---

## Runtime Evidence (include when relevant)

- 256 composition: `intensive_reading` 108 (TheEconomist.2026.09.12), rest 2026-09-16 briefing/finance.
- Restore log: loaded 7784 → indexed 13 date folders → upserted 1383 book chunks → **Saved 10134 points**, 101.75MB.
- Verified `GET /` `Indexed chunks: 10134`; `/api/library` `docs=1240 chunks=10134`; `/api/explorer-stats` `total=10134`.
- Agent log: `Loaded 10134 points from snapshot`.

---

## Open Risks (include when relevant)

- `_merge_snapshot` wipe bug is still in production. Re-index a book if `json.load` fails (extra JSON / truncated file) will shrink the store again.
- Leftover `.rag-store.json.tmp-*` (80–300MB) can confuse future recovery; only tmp-11224 / bak-20260901-7784 were validated complete.
- Daily fetch still runs `index_briefing.py` with 180s timeout; a large load+save may be killed mid-write.

---

## Current State (required)

- **Working**: Live store **10134** chunks; Search UI `:18888` and Agent `:18889` reloaded that snapshot.
- **Pending**: Harden `_merge_snapshot` (abort on load failure, never empty-and-replace); optional code review / commit of that fix.
- **Blocked**: none.

---

## Next Steps (required)

1. [ ] Fix `_merge_snapshot` to use `load_snapshot_dict` and **refuse to write** if the existing file cannot be parsed (no empty fallback).
2. [ ] Raise or remove the 180s timeout on `daily_fetch._index_briefing_warn`.
3. [ ] User hard-refresh `http://127.0.0.1:18888/` if the tab still shows 256.

---

## Notes for Next Session (include when relevant)

- Backups: `C:/reports/ai/.rag-store.json.bak-20260916-256chunks`, `C:/reports/ai/.rag-store.json.bak-20260901-7784`.
- Related: `memory-20260814-intensive-reading-rag-index.md` (stock `config` clash on index, not this wipe).

---

## References (required)

- `C:/reports/ai/.rag-store.json` — live Qdrant JSON snapshot
- `scripts/rag/intensive_reading/ingest.py` — `_merge_snapshot` wipe-on-load-failure
- `scripts/rag/index_briefing.py` — `_save_snapshot` / daily folder index
- `scripts/rag/routes/daily_fetch.py` — `_index_briefing_warn` (timeout=180)
- `scripts/rag/search_ui.py` — stats banner + in-memory client
- `scripts/rag/snapshot_io.py` — tolerant load used by Search/Agent, not by merge

---

**Confirmed at**: 2026-09-16
