---
tags:
  - learning
  - frontend
  - vite
  - typescript
  - tailwind
category: learning
status: current
last-updated: 2026-09-15
---

# Chapter 3: Vite, TypeScript, Tailwind, shadcn

> The toolchain around React: how TypeScript files become a folder Python can serve, and how the UI is styled.
> Previous: [Ch. 2](ch2-react-state-routing.md). Next: [Ch. 4 — apiJson in detail](ch4-apijson-sse-jobs.md).

---

## Why not send `.tsx` to the browser?

Browsers do not run TypeScript. They run **JavaScript** (and CSS). **Vite** is the tool that:

| Mode | Command | What you get |
|------|---------|----------------|
| **Dev** | `cd web && npm run dev` | Server on **:5173**, instant refresh (HMR) when you save a file. `/api` is proxied to :18889. |
| **Production** | `cd web && npm run build` | Writes **`web/dist/`**: `index.html` + hashed `/assets/*.js` + CSS + fonts. |

Python (`agent.py`) only knows how to serve **`web/dist`**. It never runs Vite. After you change UI code you must **rebuild** (or use `npm run dev`) and **hard-refresh** the browser so it does not keep an old hashed JS file.

`package.json` scripts:

```json
"dev": "vite",
"build": "tsc -b && vite build",
"test": "vitest run"
```

`tsc -b` type-checks before bundling. If TypeScript fails, there is no new `dist`.

How to start both processes: [implementation/web/run-and-serve.md](../../implementation/web/run-and-serve.md).

---

## `npm` and `node_modules`

- **Node.js** runs Vite.
- **`npm install`** (once) reads `web/package.json` and fills `web/node_modules/`.
- You do not commit `node_modules`. You do commit `package-lock.json`.

Alias **`@`** → `web/src` (`vite.config.ts`). Imports look like:

```ts
import { apiJson } from "@/lib/api";
import { Button } from "@/components/ui/button";
```

instead of `../../../lib/api`.

---

## TypeScript — types on data you already have

**TypeScript** is JavaScript plus types that are **erased** at compile time. They catch mistakes in the editor (`tsc`), they do not run in the browser.

Useful bits in Jarvis:

**Object shapes**

```ts
type SessionMeta = {
  id: string;
  title: string;
  message_count: number;
};
```

**Generics on `apiJson`** (full story in Chapter 4):

```ts
const data = await apiJson<{ sessions: SessionMeta[] }>("/api/sessions");
data.sessions  // TypeScript knows this is SessionMeta[]
```

`<T>` means “the JSON will look like this”. If Python actually returns `{ items: [] }`, TypeScript will not save you at runtime — you still write the type to match the real JSON.

**`unknown` vs `any`**

SSE events are `Record<string, unknown> & { type?: string }`. You **narrow** before use:

```ts
if (event.type === "token" && typeof event.content === "string") {
  assistant += event.content;
}
```

That is why Chat does not crash if a field is missing.

---

## Tailwind — CSS as class names

**Tailwind** maps class strings to CSS. You rarely write a new `.css` file for a button.

```tsx
<div className="bg-background text-foreground flex h-svh">
```

| Class | Idea |
|-------|------|
| `flex` | `display: flex` |
| `h-svh` | height = small viewport |
| `bg-background` | uses CSS variable `--background` (theme) |
| `text-sm` | small font |

Tokens live in `web/src/index.css`. **Day / Night / Reading** swap those variables:

| Theme | DOM | Feel |
|-------|-----|------|
| Day | `:root` | default light |
| Night | `html.dark` | dark tokens |
| Reading | `html[data-theme=reading]` | warm paper, **whole app** |

`web/src/lib/theme.ts` — `applyTheme` sets `classList` + `data-theme` + `localStorage['jarvis-theme']`. `main.tsx` calls it **before** React paints so the first frame is not the wrong theme.

---

## shadcn/ui — copy-paste components, not an npm UI framework

**shadcn** is a pattern: run `npx shadcn@latest add button` and you **get a file** under `web/src/components/ui/button.tsx`. You own that file. It is built on **Radix** (accessibility) + Tailwind.

Use those primitives (`Button`, `Card`, `Input`, `Accordion`, …). Do not invent a second button style.

Stock **tables** use **AG Grid** (`ag-grid-react`), not shadcn Table — only on Stock routes, which is why they are lazy-loaded.

---

## Tests (frontend)

```bash
cd web
npm test
```

**Vitest** runs `web/src/**/*.test.ts`. Helpers like `parseSseChunk` and `pollJob` are tested **without** starting Python. That is the right layer: pure functions in `lib/`.

---

## Check yourself

1. After editing `ChatPage.tsx`, why can :18889 still show the old UI?
2. Does `apiJson<{ stocks: Stock[] }>` guarantee Python returned stocks?
3. Where do you add a sidebar item?

Answers: (1) Need `npm run build` + hard-refresh, or use Vite :5173. (2) No — only compile-time. (3) `lib/nav.ts` (+ route in `App.tsx` if new page).

---

Next: [Chapter 4 — apiJson, SSE, and job polling](ch4-apijson-sse-jobs.md) (the detailed helpers chapter).
