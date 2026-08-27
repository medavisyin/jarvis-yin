---
tags:
  - implementation
  - medavis
  - platform-updates
category: medavis
status: current
last-updated: 2026-08-24
---

# Platform Updates

> **Category**: MEDAVIS | **Source**: `scripts/rag/platform_updates.py`, `scripts/rag/routes/toolbar.py` (`/api/toolbar/platform-updates`), toolbar button in `scripts/rag/templates/index.html`

## Overview

**Platform Updates** is a Medavis toolbar action that answers “what landed on master for this platform?” without reading git log. v1 covers **Radiology Platform**: teleradiology-cloud-backend + teleradiology-cloud-frontend. Each run `git fetch --all --prune`s (no pull), reads `origin/master` in the selected date window, groups commits by **JIRA key** across both repos, and writes one English 1–2 sentence blurb per task plus Jira/Bitbucket links.

Existing **Commit Summary** is unchanged (commit-level, `--all` branches, author filter, all `REPO_CONFIG` repos).

## Architecture & Design

```text
Toolbar modal (platform + from/to)
        │
        ▼
POST /api/toolbar/platform-updates  →  background job
        │
        ├─ git fetch --all --prune   (each catalog repo)
        ├─ git log origin/master --since/--until
        ├─ extract JIRA keys, drop unkeyed commits
        ├─ group FE+BE by key
        ├─ Jira title (ATLASSIAN_* if set) else first subject
        └─ Ollama 1–2 sentence blurb (omit on failure)
        │
        ▼
GET /api/toolbar/platform-updates/<job_id>  →  markdown in chat
```

### Key Design Decisions

- **Git on origin/master is ground truth** for “already merged”, not Jira Done or Bitbucket PRs.
- **One row per JIRA key** so a typical FE+BE task is a single item.
- **Fetch only** — never pull, checkout, or mutate the working tree.
- **No author picker / no commit list** — this is a platform view, not a person view.
- **Catalog, not REPO_CONFIG** — frontend is not added to the global commit-summary repo list.

## Implementation Details

### Platform catalog

`PLATFORM_CATALOG["radiology"]`:

| Repo | Path |
|------|------|
| Teleradiology Cloud Backend | `d:/projects/teleradiology-cloud-backend` |
| Teleradiology Cloud Frontend | `d:/projects/teleradiology-cloud-frontend` |

Add another platform later by appending a catalog entry and a `<option>` in the modal.

### API

- `POST /api/toolbar/platform-updates` `{ platform, date_from, date_to }` → `{ job_id, status: "started" }`
  - Missing dates default to **today** and **7 days ago**.
- `GET /api/toolbar/platform-updates/<job_id>` → `{ status, result, progress }` (`running` / `done` / `error`)

Result text is capped at 80k characters. At most **80** most-recent JIRA tasks get an Ollama blurb; extra tasks are noted in a warning.

### Per-task output

JIRA key, title, 1–2 English sentences, last master date in range, authors, repos, Jira browse link, newest Bitbucket commit link per repo that touched the key.

Bitbucket URL parse matches commit-report: `scm/{project}/{slug}` → `https://git.medavis.local/projects/{PROJECT}/repos/{slug}/commits/{hash}`.

### Error handling

| Case | Behavior |
|------|----------|
| Missing repo folder | Warning line, skip repo |
| Fetch fail | Warning; still log local `origin/master` |
| No master ref | Warning, skip repo |
| No keyed tasks | Empty-state sentence, not an error |
| Jira title fail | Fallback: subject with key stripped |
| Ollama fail | Omit blurb, keep metadata + links |

## Tests

`tests/test_platform_updates.py` — key extraction, FE+BE grouping, drop unkeyed, title fallback, Bitbucket URL, markdown shape, empty state. No live git/Jira/Ollama.
