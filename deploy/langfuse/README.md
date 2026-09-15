# Self-hosted Langfuse for Jarvis

Jarvis does not start Langfuse. Run this stack separately, then put the UI keys
into the Jarvis `.env`.

## Prerequisites

- Docker Desktop (Windows)
- 4+ CPU / 8+ GB RAM recommended for the Langfuse stack alone

## Start

```bat
cd deploy\langfuse
git clone --depth 1 https://github.com/langfuse/langfuse.git
cd langfuse
```

Edit `docker-compose.yml` secrets marked `# CHANGEME` (NEXTAUTH_SECRET, SALT, ENCRYPTION_KEY, passwords). Then:

```bat
docker compose up -d
```

Wait until the `langfuse-web` container logs `Ready` (~2–3 minutes). Open http://localhost:3000 and create the first user (becomes admin). Create a project, copy **Public key** and **Secret key**.

## Point Jarvis at it

In `c:\jarvis\.env` (never commit):

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=http://localhost:3000
```

Copy `.env.example` from the repo root if you do not already have a `.env`. Restart Jarvis (`bin\jarvis-restart.bat`). `bin\jarvis-start.bat` does **not** start Langfuse.

## Stop

```bat
cd deploy\langfuse\langfuse
docker compose down
```

Use `docker compose down -v` only if you intend to wipe all traces.
