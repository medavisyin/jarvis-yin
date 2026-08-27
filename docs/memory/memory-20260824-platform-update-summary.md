# Memory: Medavis Platform Update Summary

**Generated**: 2026-08-24 ~10:30 UTC+8
**Last updated**: 2026-08-24 ~13:10 UTC+8
**Project**: c:\jarvis
**Focus**: New Medavis toolbar feature — task-based master-only platform update summaries (Radiology first)

---

## Goal & Scope (required)

Add a new Medavis toolbar action so the user can read Radiology Platform updates by **task**, without opening git. Radiology is two repos that usually change together. Only work already merged to **master** is listed. Time range is selectable. Existing Commit Summary stays as-is.

---

## Key Decisions (required)

1. **Task grouping = JIRA issue key**: Same key on backend + frontend = one summary item.
2. **Per-task shape**: JIRA key + title + 1–2 English sentences of what shipped (FE+BE together) + merge date + authors + JIRA/Bitbucket links. No commit list.
3. **Language**: English blurbs (same as Wiki Fetch).
4. **UI**: New Medavis toolbar button (Platform Updates). Keep existing Commit Summary unchanged.
5. **Git update**: `git fetch --all --prune` only — do not pull, checkout, or mutate local working trees.
6. **Branch filter**: `origin/master` only (merged-to-master tasks).
7. **Approach A**: git log on origin/master is ground truth; group by JIRA key; JIRA title if ATLASSIAN_* works; Ollama blurb; async job like Wiki Fetch.
8. **Rejected: Bitbucket-PR-as-task**: FE/BE would split into separate items.
9. **Rejected: Upgrade existing Commit Summary**: User wants a new button, not a replacement.
10. **Rejected: Chinese blurbs**: User chose English.
11. **Rejected: Show commit lists under tasks**: User chose summary-only.
12. **Rejected: git pull / update local master**: Fetch-only.
13. **Safety cap**: At most 80 most-recent tasks get an Ollama blurb; missing API dates default to last 7 days; report body capped at 80k chars.
14. **Empty POST without dates is dangerous**: scans full master (observed 2331 tasks). Restart Jarvis to load the 7-day default and stop any in-flight unbounded job.

---

## Confirmed Assumptions (required)

- Platform picker exists; v1 lists **Radiology Platform** only. More platforms later.
- Date range = from/to pickers (same pattern as Wiki Fetch / Commit Summary).
- All authors — no team-member people picker (this is a platform view, not a person view).
- Commits / merges on master **without** a JIRA key are omitted (not an "unticketed" bucket).
- JIRA title from JIRA API when possible; else first merge/commit subject.
- 1–2 sentence blurbs via existing Ollama summarizer style (English, what shipped).
- Default production branch name is `master` (not `main`).
- Frontend repo is not in `REPO_CONFIG`; this feature uses an explicit platform→repos map.
- Different JIRA keys for FE vs BE (e.g. TPC-4852 vs TPC-4863) stay two rows — expected.

---

## Constraints & Non-Goals (include when relevant)

- Do not change existing Commit Summary, Team Activity, or Jira Daily.
- Do not `git pull` or reset local branches.
- Do not list per-commit details.
- Other platforms (P4M, etc.) are out of v1 except leaving a picker that can grow.

---

## Key Discoveries (required)

- Medavis toolbar already has Wiki Fetch, Jira Daily, Commit Summary, Team Activity, Projects (`scripts/rag/templates/index.html`).
- Existing Commit Summary is **commit-level**, `git log --all`, all `REPO_CONFIG` repos, optional author filter.
- `REPO_CONFIG` includes `d:/projects/teleradiology-cloud-backend` but **not** `d:/projects/teleradiology-cloud-frontend`.
- Radiology JIRA keys in the wild are `TPC-*` (not `TEL-*`). Regex `\b([A-Z][A-Z0-9]+-\d+)\b` matches them.
- Both radiology repos exist locally; a local git-log smoke for 2026-08-01..2026-08-24 produced 32 master-merged tasks.
- Live agent at `:18889` already served the new button and accepted `POST /api/toolbar/platform-updates` (`job_id`, `status: started`). An empty-body POST started summarizing 2331 tasks — stop by restarting Jarvis.
- Jira browse URLs resolved to `https://medavis.atlassian.net/browse/TPC-…`; Bitbucket to `https://git.medavis.local/projects/TPF/repos/…`.

---

## Current State (required)

- **Working**: Platform Updates UI + API + grouping/summarize pipeline; 11 tests passed; py_compile ok
- **Pending**: Jarvis restart to load date-default + 80-task cap and kill the unbounded job; browser click-through after restart; code review
- **Blocked**: none

---

## Next Steps (required)

1. [ ] Restart Jarvis (stop 2331-task job; load 7-day default + 80-task cap)
2. [ ] User re-runs Platform Updates for Radiology with an explicit date range
3. [x] Trigger `requesting-code-review` — user confirmed
4. [x] Update this memory file

---

## Notes for Next Session (include when relevant)

- Radiology repos: `D:\projects\teleradiology-cloud-backend`, `D:\projects\teleradiology-cloud-frontend`
- Grouping key: JIRA issue key shared across FE+BE on `origin/master`
- Restart Jarvis before trusting live behavior of date defaults / MAX_TASKS
- Do not POST `{}` without dates on an old process — it scans all of master

---

## References (required)

- `scripts/rag/platform_updates.py` — catalog, git log, grouping, Ollama blurb, MAX_TASKS
- `scripts/rag/routes/toolbar.py` — `/api/toolbar/platform-updates` job
- `scripts/rag/templates/index.html` — Platform Updates button + modal + poll JS
- `tests/test_platform_updates.py` — 11 tests
- `docs/implementation/medavis/platform-updates-impl.md` — implementation notes

---

**Confirmed at**: 2026-08-24 ~13:10 UTC+8
