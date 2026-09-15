---
tags:
  - learning
  - frontend
  - http
  - json
category: learning
status: current
last-updated: 2026-09-15
---

# Chapter 1: The browser, HTTP, and JSON

> This chapter is the vocabulary for everything later: what a page is, what a request is, and why Jarvis’s UI talks to Python with **JSON over HTTP**.
> Next: [Ch. 2 — React](ch2-react-state-routing.md).

---

## Two programs, one screen

When you open **http://127.0.0.1:18889/** you are running **two** programs:

| Program | Language | Job |
|---------|----------|-----|
| **Browser** (Chrome / Edge) | Loads HTML, runs JavaScript | Draw the UI, send HTTP requests |
| **Python** (`agent.py`) | FastAPI | Serve the HTML/JS files **and** answer `/api/*` |

The browser does **not** import Python modules. It can only talk to Python by sending an **HTTP request** (a URL + method + optional body) and reading the **HTTP response**.

That is the whole “frontend talks to backend” idea.

---

## What the browser loads first

A classic website is many `.html` files. Jarvis’s Agent UI is a **single-page app (SPA)**:

1. Browser asks `GET /` (or `GET /stock/watch` — same idea).
2. Python’s `spa_static.py` returns **`web/dist/index.html`**.
3. That HTML is tiny: a `<div id="root">` and a `<script>` that loads the bundled JavaScript.
4. The JavaScript (**React**) paints Chat, News, Stock, … inside `#root`.
5. Clicking sidebar links **does not** download a new HTML file. React Router swaps the page in memory. Python is only contacted again when the page needs **data**.

```
GET /stock/watch     →  index.html  (shell)
GET /assets/*.js     →  React code
GET /api/stock/watchlist  →  JSON from Python  (data)
```

If you only remember one split: **navigation = React**. **Data = `/api`**.

---

## HTTP in one minute

An HTTP request has:

| Part | Example | Meaning |
|------|---------|---------|
| **Method** | `GET`, `POST`, `PUT`, `DELETE` | Verb. GET = read. POST = create/start/send. DELETE = remove. |
| **URL / path** | `/api/stock/watchlist` | Which Python function should run |
| **Headers** | `Content-Type: application/json` | How to parse the body |
| **Body** | `{"query":"hello"}` | Payload (GET usually has none) |

The response has:

| Part | Example |
|------|---------|
| **Status** | `200` OK, `400` bad request, `404` missing, `500` server crash |
| **Body** | JSON text, or a stream of SSE lines |

Python in Jarvis returns JSON for almost every `/api` call, except chat/reading which return a **stream** (Chapter 4).

---

## JSON is just text with a shape

**JSON** (JavaScript Object Notation) is a text format both languages understand.

```json
{ "stocks": [ { "symbol": "600519" } ], "error": null }
```

- JavaScript: `JSON.parse(text)` → object; `JSON.stringify(obj)` → text.
- Python: `json.loads` / `json.dumps`, or Flask-shaped `request.get_json()` / `jsonify(...)`.

The UI and Python agree on **field names** (`stocks`, `job_id`, `status`, `query`). There is no shared class file. If Python returns `{ "error": "Empty query" }`, the UI reads `.error`.

---

## `fetch` — the browser’s HTTP function

Modern browsers include **`fetch`**. It returns a **Promise** (an async result). Jarvis wraps it; you still need the idea:

```javascript
const resp = await fetch("/api/health");
const data = await resp.json();   // parse JSON body
if (!resp.ok) {
  throw new Error(data.error || "HTTP " + resp.status);
}
```

| Piece | Meaning |
|-------|---------|
| `"/api/health"` | **Relative URL**. Same host as the page (`127.0.0.1:18889` in production). |
| `await` | Pause this function until the network round-trip finishes (the UI thread is not frozen; other React work can run). |
| `resp.ok` | Status 200–299. `404` and `500` are **not** ok; `fetch` does **not** throw on HTTP errors by itself — you must check. |
| `resp.json()` | Parse the body as JSON. If the body is empty or not JSON, it throws (Jarvis’s wrapper catches that). |

**GET** (read):

```javascript
await fetch("/api/sessions");
```

**POST** (send JSON):

```javascript
await fetch("/api/settings", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ audio_lang_knowledge: "zh" }),
});
```

`Content-Type: application/json` tells Python: parse the body with `request.get_json()`, not as a form.

Jarvis never uses **axios**. `fetch` is built in. The wrappers `apiJson` / `apiSsePost` / `apiUpload` live in `web/src/lib/api.ts` (Chapter 4).

---

## Same origin (why there is no CORS in production)

A page loaded from `http://127.0.0.1:18889` may call `http://127.0.0.1:18889/api/...` freely. Same **scheme + host + port** = **same origin**.

If the JavaScript were on port **5173** and Python on **18889**, the browser would block the call unless Python sent CORS headers **or** a **proxy** made `/api` look like it still lives on 5173.

Jarvis does the second thing in development:

- Vite (`web/vite.config.ts`) proxies `/api` → `http://127.0.0.1:18889`.
- React still writes `fetch("/api/health")` — the path never changes.

You do **not** put `http://127.0.0.1:18889` in frontend code. Relative `/api/...` works in both modes.

---

## GET vs POST vs long work

| Kind of work | HTTP | Why |
|--------------|------|-----|
| Read a list (watchlist, sessions, health) | **GET** | Safe to refresh; no body |
| Save settings, send a chat, start a scan | **POST** | Has a body or triggers work |
| Delete a note / stock | **DELETE** | Matches REST habit |
| Chat tokens appearing one by one | **POST** + **SSE stream** | One long response, many small events |
| Daily fetch / scanner (minutes) | **POST start** then **GET status** in a loop | HTTP would time out if one request ran for 10 minutes |

Chapter 4 names these **Pattern A / B / C**. Chapter 5 maps them to screens.

---

## What Python is allowed to return

For JSON APIs Jarvis usually sends:

```json
{ "ok": true, "...": "payload" }
```

or on failure:

```json
{ "error": "human readable message" }
```

plus a non-2xx status. The UI shows `error` in a banner. That contract is why `apiJson` does `throw new Error(err.error || "HTTP " + status)`.

---

## Check yourself

1. Why does `GET /news/daily` return HTML, but `GET /api/health` return JSON?
2. Why does `fetch` need `resp.ok` checked even when the network “succeeded”?
3. Why is the path `"/api/sessions"` and not `"http://127.0.0.1:18889/api/sessions"`?

Answers: (1) SPA fallback vs API routes. (2) HTTP 404 is still a completed request. (3) Same-origin relative URLs; Vite proxy in dev.

---

Next: [Chapter 2 — React: components, state, routing](ch2-react-state-routing.md).
