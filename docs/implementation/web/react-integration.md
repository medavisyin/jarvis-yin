---
tags:
  - implementation
  - frontend
  - react
category: frontend
status: current
last-updated: 2026-09-15
---

# Integrating React and UI components

Source of truth: **`web/`**. Alias `@` → `web/src` (`vite.config.ts`).

## Stack (pinned in `web/package.json`)

| Piece | Role |
|-------|------|
| React 19 + React DOM | UI |
| React Router 7 | Client routes under `AppShell` |
| Vite 6 | Dev server + production bundle |
| TypeScript | `tsc -b` in `npm run build` |
| Tailwind 4 + `@tailwindcss/vite` | Utility CSS; tokens in `src/index.css` |
| shadcn/ui (`components.json`, style radix-nova) | Copy-in components under `components/ui/` |
| lucide-react | Sidebar icons |
| AG Grid | Stock tables only (watchlist, scanners, weekly, national team, train) |
| Vitest | `web/src/**/*.test.ts` |

Search UI (`search_ui.py`) does **not** use this stack.

## How a screen is assembled

1. **Route** in `App.tsx` (or `StockRoutes.tsx` for `/stock/*`).
2. **Page** in `pages/` wraps content in `PageFrame` (title + muted background).
3. **Feature panel** in `features/<area>/` does `apiJson` / `apiSsePost` and renders Cards / grids.
4. **Primitives** from `components/ui/*`. Do not invent a second button/input system.

Example: News Daily fetch is `NewsPage` → `DailyFetchPanel` → `POST /api/toolbar/daily-fetch`.

Stock AG Grid is lazy: `App.tsx` uses `lazy(() => import("@/pages/StockRoutes"))` so Chat does not download the grid chunk.

Reading uses shadcn **Resizable** (`react-resizable-panels`) for the passage / analysis split. Width is stored in `jarvis-reading-prefs` as `splitPercent` (30–75). Focus mode still uses the overlay panel, not the drag handle.

## Adding a shadcn component

From `web/`:

```bash
npx shadcn@latest add <component>
```

That writes `src/components/ui/<component>.tsx` using aliases in `components.json`. Import it from `@/components/ui/...`. Keep styling on CSS variables (`--background`, `--card`, …) so Day / Night / Reading themes apply.

## Adding a sidebar item

- Leaf (like Reading): add a `NavLeaf` in `lib/nav.ts` and a `<Route>` in `App.tsx`.
- Group child (like a new News tool): add a row to `NEWS_TABS` / `STOCK_TABS` / `MEDAVIS_TABS`. The accordion children are mapped from those lists.

Do not hard-code extra `NavLink`s inside `AppShell` except through `NAV`.

## Themes

`lib/theme.ts` — `ThemeId`: `day` | `night` | `reading`. Stored as `localStorage['jarvis-theme']`.

| Theme | DOM |
|-------|-----|
| Day | `:root` tokens |
| Night | `html.dark` |
| Reading | `html[data-theme=reading]` warm paper tokens (whole app, not only `/reading`) |

`applyTheme` is called from `main.tsx` before the first paint of React. Settings page buttons call the same helper.

## Tests

```bash
cd web
npm test
```

Helpers that encode cache keys or tab lists belong in `lib/*.ts` with a `*.test.ts` beside them. Do not import `agent.py` from Vitest.

## Out of scope for this UI

- Pixel-clone of `templates/index.html`
- AG Grid on markdown reports or AI news lists
- Python inside `web/`
