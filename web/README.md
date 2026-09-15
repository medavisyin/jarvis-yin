# Jarvis agent UI (`web/`)

React + Vite + TypeScript + shadcn/ui for **`http://127.0.0.1:18889/`**. Python owns `/api/*`. Search UI `:18888` is a separate Flask app.

## Scripts

```bash
cd web
npm install
npm run dev      # Vite :5173, proxies /api → 18889
npm test
npm run build    # writes dist/; FastAPI serves this
```

After `npm run build`, hard-refresh the agent page. Design, routes, and API map: [docs/implementation/rag/agent-spa-impl.md](../docs/implementation/rag/agent-spa-impl.md).
