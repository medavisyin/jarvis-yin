# Agent React Frontend Split Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Replace the agent page at `http://127.0.0.1:18889/` with a React + Vite + TypeScript + shadcn/ui app that talks to the existing Python FastAPI `/api` (including SSE), with full *feature* parity and a modern restyle (not a pixel clone).

**Architecture:** Same git repo, two trees. `web/` is frontend-only (no Python). `scripts/` is backend-only (no React). FastAPI serves `web/dist` at `/` with SPA fallback; `/api/*` stays Python. Until cutover, if `web/dist/index.html` is missing, keep serving `scripts/rag/templates/index.html`. Vite `npm run dev` proxies `/api` to 18889 for HMR. Search UI `:18888` is unchanged.

**Tech Stack:** Python FastAPI (`scripts/rag/web_api.py` + `agent.py`), Vite, React 19, TypeScript, Tailwind CSS, shadcn/ui, React Router. Existing SSE: `POST /api/agent` with `text/event-stream`, lines `data: {json}\n\n`, terminator `data: [DONE]\n\n`.

**Approved decisions (do not re-litigate):**
- Full feature parity (chat/SSE, sessions, settings, stock, daily fetch / AI news, intensive reading, toolbar)
- Visual restyle with shadcn (sidebar, cards, dark-friendly) — not a pixel clone
- Same user URL: `http://127.0.0.1:18889/`
- Approach A: monorepo `web/` + `scripts/` (rejected: two git repos; rejected: UI under `scripts/rag/web/`)
- TypeScript
- No new backend endpoints unless a screen cannot be rebuilt from existing APIs
- Search UI, Telegram, Langfuse Docker, Python business-logic rewrite are out of scope
- `tests/` remains gitignored; still write tests there for local pytest
- Do not mix unrelated dirty files (`scripts/pipeline/topic_index.py` topic-dedup hunks) into this work

---

### Task 1: Failing test — serve `web/dist` when present, keep `/api` JSON

**Files:**
- Create: `tests/test_agent_spa.py`
- Modify later: `scripts/rag/agent.py` (do not implement until the test fails)

Do **not** import `agent.py` (loads MiniLM). Test a small helper that will live in `scripts/rag/spa_static.py`.

**Step 1: Write the failing test**

```python
"""FastAPI serves Vite build at / without stealing /api."""
from __future__ import annotations

import os
import sys

import pytest

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)


def test_spa_helper_importable():
    import spa_static  # noqa: F401


@pytest.fixture
def dist_dir(tmp_path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><html><body>SPA</body></html>", encoding="utf-8")
    (assets / "app.js").write_text("console.log(1)", encoding="utf-8")
    return dist


def test_root_serves_dist_index(dist_dir):
    from fastapi.testclient import TestClient
    from spa_static import mount_spa
    from web_api import Flask, jsonify

    app = Flask("test")

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    mount_spa(app, str(dist_dir))
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code == 200
    assert "SPA" in r.text
    assert "text/html" in r.headers["content-type"]
    api = c.get("/api/health")
    assert api.status_code == 200
    assert api.json() == {"status": "ok"}


def test_client_route_falls_back_to_index(dist_dir):
    from fastapi.testclient import TestClient
    from spa_static import mount_spa
    from web_api import Flask

    app = Flask("test")
    mount_spa(app, str(dist_dir))
    r = TestClient(app).get("/stock")
    assert r.status_code == 200
    assert "SPA" in r.text


def test_missing_dist_returns_none_index_path(tmp_path):
    from spa_static import resolve_index_html

    assert resolve_index_html(str(tmp_path / "nope")) is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_spa.py -v`

Expected: FAIL `ModuleNotFoundError: No module named 'spa_static'`

**Step 3: Write minimal implementation**

Create `scripts/rag/spa_static.py`:

```python
"""Serve a Vite `dist/` folder from the FastAPI Flask-compat app."""
from __future__ import annotations

import os
from typing import Any

from fastapi.staticfiles import StaticFiles
from web_api import FileResponse  # use starlette FileResponse via web_api if exported

# If FileResponse is not re-exported, import from fastapi.responses
from fastapi.responses import FileResponse


def resolve_index_html(dist_dir: str) -> str | None:
    path = os.path.join(dist_dir, "index.html")
    return path if os.path.isfile(path) else None


def mount_spa(app: Any, dist_dir: str) -> None:
    index = resolve_index_html(dist_dir)
    if not index:
        return
    assets = os.path.join(dist_dir, "assets")
    if os.path.isdir(assets):
        app.mount("/assets", StaticFiles(directory=assets), name="spa-assets")

    @app.route("/")
    def spa_root():
        return FileResponse(index, media_type="text/html")

    @app.route("/<path:full_path>")
    def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            return {"error": "Not found"}, 404
        direct = os.path.join(dist_dir, full_path)
        if os.path.isfile(direct):
            return FileResponse(direct)
        return FileResponse(index, media_type="text/html")
```

**Caveat:** `app.mount` and `@app.route("/<path:full_path>")` can collide with existing API routes depending on registration order. APIs must be registered **before** `mount_spa`. Static `/assets` mount must not hide APIs (they are under `/api`). If the catch-all 404s a real file-less API because it was registered first, register the catch-all **last** in `agent.py`.

If `web_api.Flask.route` catch-all steals `/api/health` in the unit test, fix `spa_fallback` to not be registered for paths that FastAPI already matched — Starlette matches more specific routes first if APIs are added first. In the unit test, `/api/health` is registered before `mount_spa`.

**Step 4: Run tests**

Run: `pytest tests/test_agent_spa.py -v`

Expected: PASS

If `/api/health` becomes 404, change catch-all to skip any path starting with `api` **and** register catch-all only after all blueprints in agent.py (Task 4).

---

### Task 2: Wire `agent.py` to prefer `web/dist`, fallback to old HTML

**Files:**
- Modify: `scripts/rag/agent.py` (the `GET /` handler near the `AGENT_HTML` load / `@app.route("/")`)
- Modify: import `JARVIS_ROOT` from `config` (already imported from `config` — add `JARVIS_ROOT` to that import)

**Step 1: Extend tests**

Add to `tests/test_agent_spa.py`:

```python
def test_fallback_when_no_dist(tmp_path):
    from spa_static import resolve_index_html, mount_spa
    from web_api import Flask, make_response
    from fastapi.testclient import TestClient

    app = Flask("test")

    @app.route("/")
    def old():
        return make_response("<html>legacy</html>")

    mount_spa(app, str(tmp_path / "missing"))
    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert "legacy" in r.text
```

Note: if `mount_spa` no-ops when dist missing, the legacy route remains. If `mount_spa` also registers `/`, it must not override when dist is missing.

**Step 2: Run — expect FAIL** until `mount_spa` no-ops on missing dist (already specified).

**Step 3: Change `agent.py`**

After all `register_blueprint(...)` calls, before or replacing the current `GET /`:

```python
from spa_static import mount_spa, resolve_index_html
from config import JARVIS_ROOT  # add to existing config import

_WEB_DIST = os.path.join(JARVIS_ROOT, "web", "dist")

# Keep loading AGENT_HTML for fallback
# ... existing AGENT_HTML read ...

if resolve_index_html(_WEB_DIST):
    mount_spa(app, _WEB_DIST)
else:
    @app.route("/")
    def index():
        resp = make_response(render_template_string(AGENT_HTML))
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
```

**Do not** register both `GET /` handlers if `mount_spa` already adds `/`.

**Step 4:** `pytest tests/test_agent_spa.py tests/test_web_api.py -v` — all pass.

---

### Task 3: Scaffold `web/` (Vite + React + TS)

**Files:**
- Create: `web/` (entire Vite app)
- Modify: `.gitignore` — add `web/node_modules/` (root already ignores `dist/`)

**Step 1:** From repo root (PowerShell):

```bat
cd /d c:\jarvis
npm create vite@latest web -- --template react-ts
cd web
npm install
```

**Step 2:** Tailwind + shadcn (follow current shadcn Vite docs; typical):

```bat
npm install -D tailwindcss @tailwindcss/vite
npm install react-router-dom
npx shadcn@latest init
```

Use style **new-york**, base color **zinc**, CSS variables, React Router. Add components as slices need them (`sidebar`, `button`, `card`, `input`, `scroll-area`, `separator`, `sonner` or `toast`).

**Step 3:** `web/vite.config.ts` proxy:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:18889", changeOrigin: true },
    },
  },
});
```

**Step 4:** Verify:

```bat
cd web
npm run build
```

Expected: `web/dist/index.html` and `web/dist/assets/*` exist.

**Step 5:** `dir web\dist` then hit `GET /` on a running agent **after Task 2** — should return the Vite HTML (`<div id="root">`), not the old chat page. If the agent was started before the build, restart it (HTML is chosen at import/startup if using `if resolve_index_html` at module load). **Prefer resolving dist at request time** so a rebuild does not require re-importing Python:

```python
def index():
    idx = resolve_index_html(_WEB_DIST)
    if idx:
        return FileResponse(idx, media_type="text/html")
    # legacy...
```

Call `mount_spa` for `/assets` at startup if `web/dist/assets` exists; document restart after first scaffold build.

---

### Task 4: App shell (shadcn sidebar + routes)

**Files:**
- Create: `web/src/layouts/AppShell.tsx`
- Create: `web/src/pages/ChatPage.tsx` (placeholder until Task 5)
- Create: `web/src/pages/NewsPage.tsx` (placeholder)
- Create: `web/src/pages/StockPage.tsx` (placeholder)
- Create: `web/src/pages/ReadingPage.tsx` (placeholder)
- Create: `web/src/pages/SettingsPage.tsx` (placeholder)
- Modify: `web/src/App.tsx`, `web/src/main.tsx`

**Step 1:** Routes: `/` chat, `/news`, `/stock`, `/reading`, `/settings`. Sidebar labels: Chat, News, Stock, Reading, Settings.

**Step 2:** `npm run build` succeeds. Placeholder pages render a title.

**Step 3:** Restart agent, open `http://127.0.0.1:18889/` and `http://127.0.0.1:18889/stock` — React shell, not old HTML. Sidebar navigation works (SPA fallback).

---

### Task 5: API client + SSE parser (TDD in frontend)

**Files:**
- Create: `web/src/lib/sse.ts`
- Create: `web/src/lib/api.ts`
- Create: `web/src/lib/sse.test.ts` (vitest)

**Step 1:** Add vitest if missing: `npm install -D vitest`.

**Step 2:** Failing test for SSE line parser:

```ts
import { describe, it, expect } from "vitest";
import { parseSseChunk } from "./sse";

describe("parseSseChunk", () => {
  it("yields JSON events and ignores [DONE]", () => {
    const { events, rest } = parseSseChunk(
      'data: {"type":"token","content":"Hi"}\n\ndata: [DONE]\n\npartial'
    );
    expect(events).toEqual([{ type: "token", content: "Hi" }]);
    expect(rest).toBe("partial");
  });
});
```

**Step 3:** `npx vitest run src/lib/sse.test.ts` — FAIL until implemented.

**Step 4:** Implement `parseSseChunk` matching the current UI:

- Split on `\n`
- Lines starting with `data: `
- Payload `[DONE]` skipped
- Other payloads `JSON.parse`; skip malformed

Event types used by chat today: `query_rewrite`, `model`, `thinking`, `tool_result`, `token`, `answer_done`, `answer`, `error` (see `scripts/rag/templates/index.html` around the `/api/agent` reader).

**Step 5:** `api.ts` helpers: `apiJson(path, init)`, `apiSsePost(path, body, onEvent)` using **relative** `/api/...` (works on 18889 and Vite proxy).

---

### Task 6: Chat + sessions + settings (first usable 18889)

**Files:**
- Modify: `web/src/pages/ChatPage.tsx`
- Create: `web/src/features/chat/*` as needed
- Modify: `web/src/pages/SettingsPage.tsx`

**Behavior to port from `templates/index.html` (not the look):**
- `GET/POST /api/sessions`, `GET/DELETE /api/sessions/<id>`, messages, clear
- `POST /api/agent` JSON `{ query, history, session_id, image? }` — stream tokens into markdown
- `GET/POST /api/settings`, model switch `GET/POST /api/switch-model`
- `GET /api/health` in the header (ollama/model)
- Image attach (base64) as today

**Verify:**
1. `npx vitest run`
2. `npm run build`
3. Agent running: send a short chat at 18889; SSE tokens appear; refresh keeps session list.

Keep old HTML **unavailable** once dist exists (by design). If you need the old UI during this slice, temporarily rename `web/dist` — do not add a dual-UI toggle unless blocked.

---

### Task 7: News / daily fetch / toolbar jobs

**Files:** `web/src/pages/NewsPage.tsx`, `web/src/features/news/*`

Port fetch + poll loops from `index.html` for:
- `/api/toolbar/daily-fetch` POST + `GET .../<job_id>`
- history, finance items, continue
- AI news KB, audio-knowledge, audio-file URLs as `<audio src="/api/toolbar/audio-file/...">`
- wiki-fetch, commit-summary, jira-report, platform-updates, reindex (toolbar actions can live in News or a Shell menu)

**Verify:** Open `/news` on 18889; history loads; one POST job shows polling status (can use an already-running backend; do not start a full daily fetch in CI).

---

### Task 8: Stock

**Files:** `web/src/pages/StockPage.tsx`, `web/src/features/stock/*`

Port watchlist, scanners (unified / long-term / quality-value / midday / right-side), prefetch, PDF export/download (`/api/stock/pdf-file/...`), DeepSeek analyze. APIs already on `scripts/rag/routes/stock.py`.

**Verify:** `/stock` loads watchlist (`GET /api/stock/watchlist`) without 500s when backend is up.

---

### Task 9: Intensive reading

**Files:** `web/src/pages/ReadingPage.tsx`, `web/src/features/reading/*`

Port: book list, upload (`multipart` `file` + `book_type`), chunk nav, analyze SSE, selection explain SSE, speaking, progress POST. Same `/api/intensive-reading/*` as `routes/intensive_reading.py`.

**Verify:** `/reading` lists books; upload 400s cleanly without file (Missing file).

---

### Task 10: Cutover + docs + start script

**Status (2026-09-14):** SPA is the live UI. Docs for frontend + API map live in `docs/implementation/rag/agent-spa-impl.md`. `agent.py` no longer reads `templates/index.html` at import when `web/dist` exists (file kept as fallback). Still open: `bin/jarvis-start.bat` auto `npm run build`; deleting the legacy HTML file.

**Files:**
- Modify: `scripts/rag/agent.py` — remove `AGENT_HTML` fallback once dist is required
- Modify: `bin/jarvis-start.bat` — after Python check, `npm run build --prefix "%SCRIPT_DIR%..\web"` (or skip if `web\dist\index.html` exists)
- Modify: `docs/getting-started.md` — Agent is React at 18889; `cd web && npm install && npm run build`; Search UI still Flask
- Modify: `docs/implementation/rag/agent-impl.md` — Flask/HTML → FastAPI + Vite SPA
- Modify: `docs/implementation/tech-stack-overview.md` — React/Vite/shadcn row
- Delete or stop reading: `scripts/rag/templates/index.html` only after the React app covers Tasks 6–9

**Verify:** Cold `jarvis-start.bat` (or documented manual build + `python agent.py`) opens 18889 on the React shell. Search UI 18888 still Flask.

---

## Verification Summary

- [ ] `pytest tests/test_agent_spa.py tests/test_web_api.py` pass
- [ ] `cd web && npm run build` produces `web/dist/index.html`
- [ ] `http://127.0.0.1:18889/` is the React app (sidebar)
- [ ] Chat SSE works (`token` / `[DONE]`)
- [ ] Sessions, settings, news, stock, reading features work against existing `/api`
- [ ] Search UI `http://127.0.0.1:18888/` unchanged
- [ ] No Python code inside `web/`; no React inside `scripts/`

## Out of scope (reminders)

- Search UI FastAPI/React
- uv / Docker / AWS
- Un-ignoring `tests/`
- Langfuse compose
- Changing SSE event names
