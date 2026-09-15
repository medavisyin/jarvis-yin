---
tags:
  - learning
  - frontend
  - fetch
  - sse
  - api
category: learning
status: current
last-updated: 2026-09-15
---

# Chapter 4: `apiJson`, SSE, and job polling

> This is the chapter that names every helper the UI uses to talk to Python. Read it slowly. The file is **`web/src/lib/api.ts`** (plus `sse.ts` and `jobs.ts`).
> Previous: [Ch. 3](ch3-vite-typescript-ui.md). Next: [Ch. 5 — screens](ch5-jarvis-pages-to-python.md). Sequence diagrams: [request-flow.md](../../implementation/web/request-flow.md).

---

## The one rule

Pages never call Python functions. They call **`apiJson`**, **`apiUpload`**, or **`apiSsePost`**. Those functions call **`fetch("/api/...")`**. Python answers.

There is no axios, no GraphQL, no WebSocket, no generated OpenAPI client.

```
Feature panel  →  apiJson / apiSsePost / apiUpload  →  fetch  →  FastAPI  →  JSON or SSE
```

---

## What `apiJson` is

**`apiJson` is a small typed wrapper around `fetch` for “send optional JSON, receive JSON, throw if HTTP failed.”**

It is not a framework. It is 14 lines. Full source (`web/src/lib/api.ts`):

```ts
export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const resp = await fetch(path, { ...init, headers });
  const data = (await resp.json().catch(() => ({}))) as T;
  if (!resp.ok) {
    const err = data as { error?: string };
    throw new Error(err.error || `HTTP ${resp.status}`);
  }
  return data;
}
```

Walk it **line by line**.

### Signature: `apiJson<T>(path, init?)`

| Part | Meaning |
|------|---------|
| `async function` | Returns a **Promise**. Callers use `await`. |
| `<T>` | **Generic.** You tell TypeScript the shape of the JSON. Example: `apiJson<{ sessions: SessionMeta[] }>("/api/sessions")` so `data.sessions` is typed. If you omit `<T>`, `T` is unknown-ish and you lose autocomplete. |
| `path` | Always a string starting with `/api/...`. Relative. Never `http://127.0.0.1:18889/...`. |
| `init?` | Optional standard `RequestInit`: `{ method: "POST", body: JSON.stringify({...}) }`. Same object `fetch` accepts. |
| `Promise<T>` | When the function finishes successfully, you get `T`. |

**GET (default method is GET):**

```ts
const h = await apiJson<{ ollama?: boolean; model?: string }>("/api/health");
```

**POST:**

```ts
await apiJson("/api/settings", {
  method: "POST",
  body: JSON.stringify({ audio_lang_knowledge: "zh" }),
});
```

You must **`JSON.stringify`** the body yourself. `apiJson` does not magically turn a JS object into JSON — it only sets the header when a body exists.

**DELETE:**

```ts
await apiJson(`/api/notes/${id}`, { method: "DELETE" });
```

### Headers: why `Content-Type` is automatic

```ts
const headers = new Headers(init?.headers);
if (init?.body && !headers.has("Content-Type")) {
  headers.set("Content-Type", "application/json");
}
```

- If you send a `body`, Python must know it is JSON. The helper sets `Content-Type: application/json` unless you already set it.
- If there is **no** body (typical GET), it does **not** set that header. That is correct.
- `new Headers(...)` copies any headers you passed in `init` so we do not wipe them.

### `fetch` then `resp.json()`

```ts
const resp = await fetch(path, { ...init, headers });
const data = (await resp.json().catch(() => ({}))) as T;
```

- `{ ...init, headers }` = your method/body **plus** the headers object we built (overrides `init.headers` with the merged one).
- `resp.json()` reads the **entire** body as JSON. This is why `apiJson` is wrong for **SSE** (a stream that never ends as one JSON document). Chat uses `apiSsePost` instead.
- `.catch(() => ({}))` — if the body is empty or not JSON, pretend it is `{}` so we can still inspect `resp.ok`.

### Errors: `fetch` does not throw on 404

```ts
if (!resp.ok) {
  const err = data as { error?: string };
  throw new Error(err.error || `HTTP ${resp.status}`);
}
return data;
```

Python’s habit: `return jsonify({"error": "Empty query"}), 400`.

The UI then:

```ts
try {
  await apiJson("/api/...");
} catch (e) {
  setError(e instanceof Error ? e.message : String(e));
}
```

You see **"Empty query"** in the banner, not a stack trace. If Python forgot `{ error }`, you see **"HTTP 400"**.

**`resp.ok`** is status 200–299. 401, 404, 500 all throw.

### What `apiJson` is **not**

| Not this | Why |
|----------|-----|
| A cache | Every call hits the network |
| A retry library | Failures bubble to the page |
| Auth | No `Authorization` header; local app |
| SSE | Body is one JSON document, not `data: ...` lines |
| File upload | Multipart must **not** force `Content-Type: application/json` → use `apiUpload` |

---

## `apiUpload` — the one exception for files

```ts
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const resp = await fetch(path, { method: "POST", body: form });
  ...
}
```

Used for **Reading book upload**:

```ts
const form = new FormData();
form.append("file", file);
await apiUpload("/api/intensive-reading/upload", form);
```

The browser sets `Content-Type: multipart/form-data; boundary=...` automatically when `body` is `FormData`. If we used `apiJson`, it would overwrite that with `application/json` and Python would not see the file.

Error handling is the same as `apiJson` (`error` field / `HTTP status`).

---

## `apiSsePost` — one POST, many events

**SSE (Server-Sent Events)** is a convention: the HTTP response stays open and the server writes lines:

```
data: {"type":"token","content":"Hel"}

data: {"type":"token","content":"lo"}

data: [DONE]

```

Each payload is prefixed with `data: ` and followed by a blank line (`\n\n`). Chat’s assistant bubble grows as tokens arrive. If we waited for one JSON blob, the user would stare at a spinner for the whole answer.

`apiSsePost` still uses **`fetch` + POST JSON** (not the browser `EventSource` API, because `EventSource` is GET-only and Jarvis needs a POST body with `query` / `history`).

```ts
export async function apiSsePost(
  path: string,
  body: unknown,
  onEvent: (event: SseEvent) => void,
): Promise<void> {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error((err as { error?: string }).error || `HTTP ${resp.status}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseChunk(buffer);
    buffer = parsed.rest;
    for (const event of parsed.events) {
      onEvent(event);
    }
  }
  // flush a last incomplete "data: ..." line if the stream ended without "\n"
  ...
}
```

| Step | What |
|------|------|
| POST JSON | Same as `apiJson` request side |
| `resp.body.getReader()` | **ReadableStream** of bytes, not `resp.json()` |
| `TextDecoder` | Bytes → string |
| `buffer` | TCP can split a line across two chunks. Keep leftovers in `rest`. |
| `parseSseChunk` | `web/src/lib/sse.ts` — explained next |
| `onEvent(event)` | Your callback (Chat appends tokens here) |
| Return `void` | Success = stream finished. Persistence of chat is a **second** `apiJson` call. |

If Python returns 400 JSON instead of a stream, the helper throws like `apiJson`.

### `parseSseChunk` (`web/src/lib/sse.ts`)

```ts
export function parseSseChunk(chunk: string): { events: SseEvent[]; rest: string } {
  const lines = chunk.split("\n");
  const rest = lines.pop() ?? "";
  const events: SseEvent[] = [];
  for (const line of lines) {
    if (!line.startsWith("data: ")) continue;
    const payload = line.slice(6).trim();
    if (payload === "[DONE]") continue;
    try {
      events.push(JSON.parse(payload) as SseEvent);
    } catch {
      continue;
    }
  }
  return { events, rest };
}
```

| Detail | Why |
|--------|-----|
| `lines.pop()` as `rest` | Last fragment may be incomplete (`data: {"ty`). Wait for more bytes. |
| Skip non-`data: ` lines | SSE also allows comments (`:`), event names, etc. Jarvis only uses `data:`. |
| Skip `[DONE]` | Python’s terminator. Not JSON. Chat treats “reader finished” as the end. |
| `JSON.parse` in try | A truncated payload is ignored until the next chunk completes it (via `rest`). |

`SseEvent` is `{ type?: string } & Record<string, unknown>`. Always check `event.type` and `typeof event.content === "string"` before using fields (ChatPage does this).

**Python side (chat):** `agent.py` `api_agent` yields `data: {json}\n\n` from `run_agent`, then `data: [DONE]\n\n`. MIME `text/event-stream`. Headers `Cache-Control: no-cache` and `X-Accel-Buffering: no` stop proxies (including Vite) from buffering the stream into one blob.

---

## `pollJob` — long work without a 10-minute HTTP request

Daily fetch and stock scans can run for minutes. One `fetch` would sit until a proxy timeout. Pattern:

1. **POST start** → `{ job_id }` or `{ status: "running" }` immediately.
2. Python runs a **background thread**.
3. **GET status** every few seconds until `status` is terminal.
4. Optionally **GET result**.

`web/src/lib/jobs.ts`:

```ts
export function isTerminalJobStatus(status: unknown): boolean {
  if (typeof status !== "string" || !status) return false;
  return ["done", "error", "stopped", "complete"].includes(status.toLowerCase());
}

export async function pollJob<T extends { status?: string }>(
  fetchStatus: () => Promise<T>,
  onTick: (job: T) => void,
  opts?: { intervalMs?: number; signal?: AbortSignal },
): Promise<T> {
  const intervalMs = opts?.intervalMs ?? 4000;
  for (;;) {
    if (opts?.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const job = await fetchStatus();
    onTick(job);
    if (isTerminalJobStatus(job.status)) return job;
    await wait(intervalMs);
  }
}
```

| Argument | Meaning |
|----------|---------|
| `fetchStatus` | **You** pass a function, usually `() => apiJson("/api/.../status")`. `pollJob` does not know the URL. |
| `onTick` | Called every poll — update a progress string in React. |
| `intervalMs` | Default **4000** (4 seconds). |
| `signal` | Optional `AbortSignal` to stop the loop when the user navigates away. |

Daily fetch:

```ts
const started = await apiJson<{ job_id: string }>("/api/toolbar/daily-fetch", { method: "POST" });
const done = await pollJob(
  () => apiJson<DailyJob>(`/api/toolbar/daily-fetch/${started.job_id}`),
  (st) => setProgress(st.step || "Working..."),
);
```

That is **`apiJson` twice**: once to start, many times inside `pollJob`.

---

## Which helper do I call?

```
Does the user need tokens on screen while Python thinks?
  YES → apiSsePost          (chat, reading analyze / explain / speaking)
  NO  → Is it a file upload?
          YES → apiUpload
          NO  → Does it take minutes?
                 YES → apiJson start + pollJob(+ result)
                 NO  → apiJson once
```

---

## Tiny examples you can copy

**Read**

```ts
const data = await apiJson<{ stocks?: Stock[] }>("/api/stock/watchlist");
```

**Write JSON**

```ts
await apiJson("/api/stock/watchlist", {
  method: "POST",
  body: JSON.stringify({ symbol: "600519" }),
});
```

**Stream**

```ts
await apiSsePost("/api/agent", { query, history, session_id: sid }, (event) => {
  if (event.type === "token" && typeof event.content === "string") {
    // append to React state
  }
});
```

---

## Check yourself

1. Why can `apiJson` not parse a chat response?
2. Why must upload skip `Content-Type: application/json`?
3. Who decides the poll URL — `pollJob` or the panel?
4. What does `<T>` on `apiJson` guarantee at **runtime**?

Answers: (1) Body is SSE lines, not one JSON value. (2) Multipart boundary. (3) The panel’s `fetchStatus` closure. (4) Nothing — only TypeScript.

---

Next: [Chapter 5 — Jarvis pages talking to Python](ch5-jarvis-pages-to-python.md).
