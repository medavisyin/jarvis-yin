# Memory: FastAPI Swagger /docs

**Generated**: 2026-09-15
**Last updated**: 2026-09-15
**Project**: c:\jarvis
**Focus**: Enable FastAPI Swagger so `/api` routes can be listed and tried in the browser

---

## Goal & Scope (required)

User wanted to see and test all FastAPI APIs in the browser. Swagger `/docs` was previously disabled. Enabled `/docs` + `/openapi.json`; left `/redoc` off. SPA catch-all must not steal those URLs.

---

## Key Decisions (required)

1. **Enable `/docs` (Swagger) only, not `/redoc`**: User chose option B, then approved the approach.
2. **Keep Flask-shaped routes as-is**: Do not add Pydantic models just for richer Swagger forms. Try it out still works; paste JSON when the form is empty.
3. **SPA reserved paths**: `spa_static.py` returns JSON 404 for `docs`, `docs/*`, `redoc`, `redoc/*`, `openapi.json` so React `index.html` does not mask the explorer.
5. **Review follow-ups applied**: LAN sentence on `/docs`; SPA test asserts `/redoc` JSON 404; architecture + run-and-serve reserved-path rows; Vite `:5173/docs` is not Swagger.

---

## Confirmed Assumptions (required)

- Local single-user app; no auth on `/api` or `/docs`.
- Request bodies in Swagger are often empty because handlers use `request.get_json()`, not Pydantic.
- Do not Try it out on long scanners / daily-fetch (those start real jobs).
- Chat SSE will not stream in Swagger.

---

## Constraints & Non-Goals

- `/redoc` stays disabled.
- No OpenAPI client generation; React still uses `apiJson` / `apiSsePost` / `apiUpload`.

---

## Key Discoveries (required)

- `Flask` in `web_api.py` had `docs_url`, `redoc_url`, and `openapi_url` all `None`, so `/docs` was 404.
- With the SPA mounted, `GET /docs` previously returned React `index.html` (catch-all), not a 404.
- Swagger needs `/openapi.json` as well as `/docs`; enabling only the UI URL is not enough.
- Live check after Agent restart: Swagger UI title `Jarvis Agent`, OpenAPI listed ~140 paths; Try it out on `GET /api/health` returned 200 with real health JSON.

---

## Runtime Evidence

- RED: `test_swagger_docs_are_enabled` asserted 200, got 404; `test_spa_does_not_steal_docs_or_openapi` got SPA HTML instead of swagger.
- GREEN: `python -m pytest tests/test_web_api.py tests/test_agent_spa.py -q` → 23 passed.
- Browser: `http://127.0.0.1:18889/docs` — 151 opblocks; `/api/health` Execute → 200 `{"ollama": true, ...}`.

---

## Current State (required)

- **Working**: `/docs` and `/openapi.json` on the restarted Agent (`:18889`). Review findings Important-1 (docs sentence) and Minor-1/2/3 applied.
- **Pending**: follow-up code review of those doc/test fixes (handoff gate).
- **Blocked**: none.

---

## Next Steps (required)

1. [ ] Code review of `/docs` enablement (user requested `requesting-code-review`)
2. [ ] Commit only if the user asks

---

## Notes for Next Session

- Open **http://127.0.0.1:18889/docs**. If it shows the React app instead of Swagger, restart the Agent (`bin/jarvis-restart.bat /AGENT`).
- `apiJson` is unrelated to Swagger; it is the React `fetch` helper in `web/src/lib/api.ts`.

---

## References (required)

- `scripts/rag/web_api.py` — FastAPI `docs_url` / `openapi_url`
- `scripts/rag/spa_static.py` — SPA must not steal `/docs`
- `tests/test_web_api.py` — `test_swagger_docs_are_enabled`
- `tests/test_agent_spa.py` — `test_spa_does_not_steal_docs_or_openapi`
- `docs/implementation/web/python-bridge.md` — how React talks to Python + Swagger note

---

**Confirmed at**: 2026-09-15
