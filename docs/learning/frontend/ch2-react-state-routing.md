---
tags:
  - learning
  - frontend
  - react
  - router
category: learning
status: current
last-updated: 2026-09-15
---

# Chapter 2: React — components, state, routing

> How the UI is *structured* after the HTML shell loads. You do not write `document.getElementById` by hand for each widget.
> Previous: [Ch. 1](ch1-browser-http-json.md). Next: [Ch. 3 — Vite / TypeScript / Tailwind](ch3-vite-typescript-ui.md).

---

## What React is

**React** is a library: you describe the screen as **functions that return HTML-like markup (JSX)**. When **state** changes, React **re-runs** those functions and updates the DOM.

Without React you would do:

```javascript
button.addEventListener("click", () => {
  list.innerHTML += "<li>new</li>";
});
```

That gets unmanageable. React’s rule: **data in state → UI is a function of that data**.

Jarvis uses **React 19** (`web/package.json`). Entry:

1. `web/index.html` has `<div id="root">`.
2. `web/src/main.tsx` calls `createRoot(...).render(<App />)`.
3. `App.tsx` sets up the router; `AppShell` draws the sidebar; a **page** fills the main area.

---

## JSX is HTML in JavaScript

```tsx
<p className="text-sm">{health || "…"}</p>
```

| JSX | Meaning |
|-----|---------|
| `<p>` | Create a paragraph (React element, not a string) |
| `className` | HTML `class` (because `class` is a JS keyword) |
| `{health \|\| "…"}` | JavaScript inside curly braces — show the variable |

A **component** is a function whose name is Capitalized and that returns JSX:

```tsx
export function ChatPage() {
  return <div>…</div>;
}
```

You use it like a tag: `<ChatPage />`.

**Props** are arguments:

```tsx
<Button size="sm" variant="outline" onClick={load}>Refresh</Button>
```

`Button` is not a browser built-in — it is `web/src/components/ui/button.tsx` (shadcn). `onClick={load}` passes a function; React calls it on click.

---

## State: `useState`

`useState` is a React **hook** (a function that starts with `use` and only works inside components).

```tsx
const [sessions, setSessions] = useState<SessionMeta[]>([]);
```

| Piece | Meaning |
|-------|---------|
| `sessions` | Current value (starts as `[]`) |
| `setSessions` | Call this to change it — React will **re-render** the component |
| `<SessionMeta[]>` | TypeScript: array of session objects |

You **never** assign `sessions = ...`. Always `setSessions(newArray)`.

Chat example (`web/src/pages/ChatPage.tsx`):

- `draft` — text in the box.
- `messages` — bubbles on screen.
- `streaming` — true while SSE is open (disables Send).
- `error` — red banner string.

When a token arrives, Chat does `setMessages(...)` with a longer assistant string. React redraws that bubble.

---

## Effects: `useEffect`

**Rendering** must be pure (no network). Side effects (HTTP, timers) go in `useEffect`:

```tsx
useEffect(() => {
  apiJson<{ ollama?: boolean; model?: string }>("/api/health")
    .then((h) => setHealth(`${h.model || "?"} · ollama ${h.ollama ? "up" : "down"}`))
    .catch(() => setHealth("health unavailable"));
}, []);
```

This is `AppShell` (`web/src/layouts/AppShell.tsx`).

| Piece | Meaning |
|-------|---------|
| Function body | Runs **after** paint |
| `[]` | Dependency list. Empty = run **once** on mount (open the app) |
| `.then` / `.catch` | Promises from `apiJson` (Chapter 4) |

If you put `[sessionId]` as the list, the effect re-runs whenever `sessionId` changes (load that session’s messages).

---

## Events and async handlers

Buttons call async functions:

```tsx
async function loadWatchlist() {
  const data = await apiJson<{ stocks?: Stock[] }>("/api/stock/watchlist");
  setStocks(data.stocks || []);
}
```

```tsx
<Button onClick={() => void loadWatchlist()}>Refresh</Button>
```

`void` tells TypeScript “I am firing a Promise on purpose”. Errors should be `try/catch` and `setError(...)`.

Do **not** call `apiJson` directly in the JSX like `{apiJson("/api/health")}` — that would fire every render. Put it in an event handler or `useEffect`.

---

## Lists need a `key`

```tsx
{sessions.map((s) => (
  <button key={s.id} onClick={() => openSession(s.id)}>{s.title}</button>
))}
```

`key` must be stable (id, not array index) so React can match items when the list updates.

---

## Routing: many URLs, one HTML file

**React Router** reads `window.location.pathname` and chooses a component.

`web/src/App.tsx` (simplified):

```tsx
<BrowserRouter>
  <Routes>
    <Route element={<AppShell />}>
      <Route path="/" element={<ChatPage />} />
      <Route path="/news" element={<NewsLayout />}>
        <Route index element={<Navigate to="daily" replace />} />
        <Route path=":tab" element={<NewsToolPage />} />
      </Route>
      <Route path="stock/*" element={<Suspense><StockRoutes /></Suspense>} />
      <Route path="/reading" element={<ReadingPage />} />
      <Route path="/settings" element={<SettingsPage />} />
    </Route>
  </Routes>
</BrowserRouter>
```

| Idea | In Jarvis |
|------|-----------|
| **Layout route** | `AppShell` wraps children; it renders `<Outlet />` where the page goes |
| **Index redirect** | `/news` → `/news/daily` |
| **Param** | `:tab` is `daily`, `ai-kb`, … |
| **`stock/*`** | Nested stock URLs live in `StockRoutes.tsx` |
| **`lazy()` + `Suspense`** | Stock (AG Grid) is a **separate JS chunk**. Chat users do not download the grid until they open Stock |

Sidebar labels are data in `web/src/lib/nav.ts` (`NAV`), not hard-coded `<a>` tags in the shell. Changing a menu item = edit the constant + add a `<Route>` if it is a new page.

**Client route vs API route**

| URL | Who |
|-----|-----|
| `/stock/watch` | React Router (Python still returns `index.html`) |
| `/api/stock/watchlist` | Python JSON |

If you invent `/reports` in React but forget the `<Route>`, you get a blank outlet. If you invent `/api/reports` only in React, Python returns 404 JSON.

---

## Layers in `web/src` (where to put code)

| Folder | Put here |
|--------|----------|
| `pages/` | One screen (ChatPage, SettingsPage) |
| `features/` | A panel on a screen (DailyFetchPanel, WatchlistGrid) |
| `layouts/` | Shell: sidebar, outlet |
| `components/ui/` | Reusable Button, Card, Input (shadcn) — **no** `fetch` |
| `lib/` | Helpers: `api.ts`, `nav.ts`, `theme.ts` — **no** JSX (or very little) |

Rule of thumb: **UI kit never talks to Python**. Pages and feature panels call `apiJson`.

---

## Mental model of one click

```
User clicks "Refresh" on Watchlist
  → onClick handler (StockPage)
  → await apiJson("/api/stock/watchlist")     // Ch. 4
  → setStocks(...)
  → React re-renders the grid
```

No jQuery, no `innerHTML`, no WebSocket.

---

## Check yourself

1. What happens if you write `sessions.push(newItem)` instead of `setSessions`?
2. Why is Stock `lazy()`?
3. Why does `/stock/watch` work after a hard refresh even though there is no `watch.html`?

Answers: (1) React does not see the mutation — UI stale. (2) Smaller Chat bundle. (3) Python SPA fallback always serves `index.html`; Router reads the path.

---

Next: [Chapter 3 — Vite, TypeScript, Tailwind, shadcn](ch3-vite-typescript-ui.md).
