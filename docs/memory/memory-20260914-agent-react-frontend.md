# Memory: Agent React Frontend Split

**Generated**: 2026-09-14
**Last updated**: 2026-09-15 (Frontend suite `docs/implementation/web/`)
**Project**: c:\jarvis
**Focus**: Split agent :18889 into Python API + React/Vite/shadcn UI; SPA is live

---

## Goal & Scope (required)

Replace the agent page at `http://127.0.0.1:18889/` with React + Vite + TypeScript + shadcn/ui while keeping the Python FastAPI backend and existing `/api` + SSE. Full *feature* parity with a visual restyle (not a pixel clone). Search UI `:18888` stays Flask.

---

## Key Decisions (required)

1. **Full feature parity**: Chat/SSE, sessions, settings, stock, daily fetch/AI news, intensive reading, toolbar — all must survive.
2. **shadcn restyle**: New layout/theme (sidebar, cards, dark-friendly); not a pixel clone of `templates/index.html`.
3. **Same URL 18889**: FastAPI serves `web/dist`; Vite `/api` proxy only for HMR during coding.
4. **Approach A (monorepo two trees)**: `web/` frontend-only, `scripts/` backend-only.
5. **TypeScript**. Plan: `docs/plans/2026-09-14-agent-react-frontend.md`. Stay on `main`; do not commit unless asked.
6. **Medavis** is first-level nav after Reading (`/medavis/*`). News Toolbar removed; tools are News children.
7. **Accordion sidebar**: News/Stock/Medavis groups; Chat/Reading/Settings leaves. Nested routes. Accordion can collapse; route change still auto-opens the matching group.
8. **Stock Scanners**: first button **Left-Right-ATH** is `/api/stock/unified_scan` (left + right + ATH in one run). **AI scan** is a different API (`/api/stock/scan`). Do not treat them as the same.
9. **Theme**: Day / Night / Reading. Reading is a global warm-paper preset (`html[data-theme=reading]`), not Reading-page-only. Key `jarvis-theme`.
10. **Cleanup**: delete unused Vite scaffold (`App.css`, `src/assets/*`, unused `public/icons.svg`). Do not delete `templates/index.html`; `agent.py` only loads it when `web/dist` is missing.
11. **Docs hub**: frontend suite is **`docs/implementation/web/`** (architecture, React integration, run-and-serve, python-bridge). `docs/implementation/rag/agent-spa-impl.md` is the page→`/api` catalog only. Make Frontend unmissable in `docs/README.md` and `docs/implementation/README.md`.

---

## Confirmed Assumptions (required)

- Backend stays Python. No new APIs unless a screen cannot be rebuilt from existing ones.
- SSE protocol unchanged (`data: {json}\n\n`, `[DONE]`).
- Hard-refresh after `npm run build`. Do not start daily fetch / scan / train during UI verification.
- Analysis cache keys: `kind__level__lang` (e.g. `vocab__university__zh`). GET/PUT `/api/intensive-reading/books/{id}/chunks/{n}/analysis`.

---

## Constraints & Non-Goals

- Out: Search UI React, Telegram, Langfuse Docker, uv, deleting stock scanner backends, deleting legacy HTML file.
- Do not mix unrelated dirty `topic_index.py` / daily-fetch dedup hunks.

---

## Key Discoveries (required)

- Unified scanner ≠ AI scan. Unified orchestrates left + right + ATH; AI scan is the left-side LLM funnel only.
- SPA fallback already serves `/fonts/*` from `web/dist` via `spa_static` direct-file path.
- `themeClass("reading")` is `"light"` (no `.dark`); paper colors live on `html[data-theme=reading]`.
- PowerShell: `; if ($LASTEXITCODE -eq 0)` not `&&`.

---

## Runtime Evidence

- Accordion + Card + AG Grid verified earlier this session.
- Reading cache helpers: vitest `readingCache.test.ts`.
- Theme `parseTheme` tests added for reading.

---

## Open Risks

- Plan Task 10 remainder: `jarvis-start.bat` npm build; optional delete of `templates/index.html`.
- AI News still capped at 80 items vs old 500.
- AGENT process must be restarted to pick up `agent.py` lazy HTML load.

---

## Current State (required)

- **Working**: SPA on 18889; accordion nav; Stock AG Grid; Reading cache + passage paper; Day/Night/Reading themes; Left-Right-ATH label.
- **Pending**: jarvis-start.bat Task 10; optional code review / commit.
- **Blocked**: None.

---

## Next Steps (required)

1. [x] Accordion NAV + nested routes
2. [x] Card wrappers + Stock DataGrid
3. [x] Reading passage + analysis persist + explain
4. [x] Left-Right-ATH rename; Reading theme; dead-asset cleanup; SPA docs
5. [ ] Optional: code review / commit (only if asked)

---

## Notes for Next Session

- Do not re-litigate folder split or 18889 URL.
- First code for backend tests: `spa_static.py` + pytest; do not import full `agent.py`.
- Unrelated dirty files — do not mix: `scripts/pipeline/topic_index.py`, topic-dedup hunks in `daily_fetch.py`.

---

## References (required)

- `docs/implementation/web/request-flow.md` — React → Python request sequences
- `docs/implementation/rag/agent-spa-impl.md` — page → `/api` catalog
- `docs/plans/2026-09-14-agent-react-frontend.md`
- `web/src/lib/nav.ts`, `theme.ts`, `readingCache.ts`
- `web/src/pages/StockPage.tsx` — scanner labels
- `scripts/rag/spa_static.py`
- `scripts/rag/templates/index.html` — old UI fallback/reference

---

**Confirmed at**: 2026-09-14 Left-Right-ATH + Reading theme + docs hub, execute directly
