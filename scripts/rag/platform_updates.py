"""Platform Updates: master-only JIRA-task summaries across a platform's repos."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections import OrderedDict
from datetime import date, timedelta
from typing import Any, Callable, Mapping
from urllib.parse import quote

HttpGet = Callable[..., Any]
HttpPost = Callable[..., Any]
ProgressFn = Callable[[str], None]

JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
_NOT_JIRA_PROJECTS = frozenset(
    {
        "UTF",
        "SHA",
        "ISO",
        "MD",
        "CRC",
        "AES",
        "RFC",
        "CVE",
        "HTTP",
        "HTML",
        "CSS",
        "XML",
        "JSON",
        "BASE",
        "PEP",
        "IEEE",
    }
)
_THINK_RE = re.compile(r"</?think>", re.IGNORECASE)
_SCM_RE = re.compile(r"scm/([^/]+)/([^/.]+)", re.IGNORECASE)

PLATFORM_CATALOG: dict[str, dict[str, Any]] = {
    "radiology": {
        "label": "Radiology Platform",
        "repos": [
            {
                "name": "Teleradiology Cloud Backend",
                "path": "d:/projects/teleradiology-cloud-backend",
            },
            {
                "name": "Teleradiology Cloud Frontend",
                "path": "d:/projects/teleradiology-cloud-frontend",
            },
        ],
    },
}

MAX_TASKS = 80
DEFAULT_LOOKBACK_DAYS = 7
REPORT_CHAR_LIMIT = 80_000


def _truncation_note(limit: int) -> str:
    return f"\n\n---\nReport truncated to {limit:,} characters.\n"


class UnknownPlatformError(ValueError):
    """Raised when platform_id is not in PLATFORM_CATALOG."""


def require_platform(platform_id: str) -> dict[str, Any]:
    spec = PLATFORM_CATALOG.get(platform_id)
    if not spec:
        known = ", ".join(PLATFORM_CATALOG)
        raise UnknownPlatformError(
            f"Unknown platform '{platform_id}'. Known: {known or '(none)'}."
        )
    return spec


def resolve_date_range(date_from: str, date_to: str) -> tuple[str, str]:
    today = date.today()
    to_s = (date_to or "").strip() or today.isoformat()
    from_s = (date_from or "").strip() or (
        today - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    ).isoformat()
    return from_s, to_s


def clip_report(report: str, limit: int = REPORT_CHAR_LIMIT) -> str:
    text = report or ""
    if len(text) <= limit:
        return text
    note = _truncation_note(limit)
    if len(note) >= limit:
        return note[:limit]
    keep = limit - len(note)
    return text[:keep] + note


_BLURB_SYSTEM = (
    "You are a concise technical writer. Given commits merged to master for one "
    "JIRA ticket that may span backend and frontend, write 1-2 English sentences "
    "covering what shipped and why it matters to a teammate catching up. "
    "Do not list commit hashes. Output only the summary, no labels or prefixes."
)

_GIT_TIMEOUT = 45


def extract_jira_keys(text: str) -> list[str]:
    """Return unique JIRA keys in first-seen order."""
    seen: set[str] = set()
    keys: list[str] = []
    for key in JIRA_KEY_RE.findall(text or ""):
        project = key.split("-", 1)[0]
        if project in _NOT_JIRA_PROJECTS:
            continue
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def fallback_title(subject: str, key: str) -> str:
    text = (subject or "").strip()
    text = re.sub(rf"^{re.escape(key)}\s*[:\-–—]?\s*", "", text, count=1)
    text = re.sub(
        r"^(feat|fix|chore|docs|refactor|test|style)(\([^)]+\))?:\s*",
        "",
        text,
        flags=re.I,
    )
    return text.strip() or key


def bitbucket_commit_url(remote_url: str, commit_hash: str) -> str:
    if not remote_url or not commit_hash:
        return ""
    match = _SCM_RE.search(remote_url.replace("\\", "/"))
    if not match:
        return ""
    project = match.group(1).upper()
    slug = match.group(2)
    return (
        f"https://git.medavis.local/projects/{project}/repos/{slug}/commits/{commit_hash}"
    )


def jira_browse_url(key: str) -> str:
    site = (os.environ.get("ATLASSIAN_SITE") or "").strip().rstrip("/")
    if not site or not key:
        return ""
    if site.startswith("http://") or site.startswith("https://"):
        base = site
    else:
        base = f"https://{site}"
    return f"{base}/browse/{key}"


def _date_prefix(value: str) -> str:
    text = (value or "").strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return ""


def _later_date(current: str | None, candidate: str) -> str:
    cand = _date_prefix(candidate)
    cur = _date_prefix(current or "")
    if not cur:
        return cand or (candidate or "")[:10]
    if cand and cand > cur:
        return cand
    return cur


def group_commits_by_ticket(
    commits: list[dict[str, Any]],
) -> OrderedDict[str, dict[str, Any]]:
    """Drop unkeyed commits; merge FE+BE rows that share a JIRA key."""
    grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for commit in commits:
        blob = f"{commit.get('subject') or ''}\n{commit.get('body') or ''}"
        keys = extract_jira_keys(blob)
        if not keys:
            continue
        key = keys[0]
        task = grouped.get(key)
        if task is None:
            task = {
                "key": key,
                "commits": [],
                "authors": [],
                "repos": [],
                "subjects": [],
            }
            grouped[key] = task
        task["commits"].append(commit)
        author = (commit.get("author") or "").strip()
        if author and author not in task["authors"]:
            task["authors"].append(author)
        repo = (commit.get("repo_name") or "").strip()
        if repo and repo not in task["repos"]:
            task["repos"].append(repo)
        subject = (commit.get("subject") or "").strip()
        if subject:
            task["subjects"].append(subject)
        task["merge_date"] = _later_date(task.get("merge_date"), commit.get("date") or "")
    return grouped


def format_platform_report(
    platform_label: str,
    date_from: str,
    date_to: str,
    tasks: list[dict[str, Any]],
    warnings: list[str] | None = None,
) -> str:
    warnings = warnings or []
    lines: list[str] = [
        f"# {platform_label} Updates ({date_from or '...'} to {date_to or '...'})",
        "",
    ]
    if warnings:
        for warn in warnings:
            lines.append(f"- ⚠️ {warn}")
        lines.append("")
    if not tasks:
        lines.append("No master-merged JIRA tasks in this date range.")
        return "\n".join(lines) + "\n"

    lines.append(f"**{len(tasks)} task(s)** merged to master.\n")
    for task in tasks:
        key = task.get("key") or ""
        title = task.get("title") or key
        heading = f"### {key} — {title}" if title and title != key else f"### {key}"
        lines.append(heading)
        meta_bits = []
        if task.get("merge_date"):
            meta_bits.append(str(task["merge_date"]))
        if task.get("authors"):
            meta_bits.append(", ".join(task["authors"]))
        if task.get("repos"):
            meta_bits.append(" + ".join(task["repos"]))
        if meta_bits:
            lines.append(" · ".join(meta_bits))
        link_bits = []
        jira_url = task.get("jira_url") or ""
        if jira_url:
            link_bits.append(f"[Jira]({jira_url})")
        for repo_name, url in task.get("commit_links") or []:
            if url:
                link_bits.append(f"[{repo_name}]({url})")
        if link_bits:
            lines.append(" · ".join(link_bits))
        blurb = (task.get("blurb") or "").strip()
        if blurb:
            lines.append("")
            lines.append(f"> {blurb}")
        lines.append("")
    return "\n".join(lines)


def fetch_jira_title(key: str, http_get: HttpGet | None = None) -> str:
    site = (os.environ.get("ATLASSIAN_SITE") or "").strip()
    email = (os.environ.get("ATLASSIAN_EMAIL") or "").strip()
    token = (os.environ.get("ATLASSIAN_API_TOKEN") or "").strip()
    if not (site and email and token and key):
        return ""
    host = site if site.startswith("http") else f"https://{site}"
    url = f"{host}/rest/api/3/issue/{quote(key)}?fields=summary"
    getter = http_get
    if getter is None:
        import requests

        getter = requests.get
    try:
        resp = getter(
            url,
            auth=(email, token),
            headers={"Accept": "application/json"},
            timeout=20,
        )
        resp.raise_for_status()
        fields = (resp.json() or {}).get("fields") or {}
        return str(fields.get("summary") or "").strip()
    except Exception:
        return ""


def _default_ollama() -> tuple[str, str]:
    host = os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
    model = os.environ.get("OLLAMA_MODEL_FAST") or "qwen3:1.7b"
    for name in ("__main__", "agent", "rag.agent"):
        mod = sys.modules.get(name)
        if mod is None:
            continue
        host = getattr(mod, "OLLAMA_HOST", None) or host
        model = getattr(mod, "OLLAMA_MODEL_FAST", None) or model
    return host, model


def summarize_ticket(
    task: Mapping[str, Any],
    host: str | None = None,
    model: str | None = None,
    http_post: HttpPost | None = None,
) -> str:
    subjects = task.get("subjects") or []
    repos = task.get("repos") or []
    key = task.get("key") or ""
    title = task.get("title") or ""
    if not subjects and not title:
        return ""
    user_lines = [
        f"JIRA: {key} {title}".strip(),
        f"Repos: {', '.join(repos)}" if repos else "",
        "Commit subjects:",
        *[f"- {s}" for s in subjects[:12]],
    ]
    context = "\n".join(line for line in user_lines if line)
    default_host, default_model = _default_ollama()
    ollama_host = (host or default_host).rstrip("/")
    ollama_model = model or default_model
    payload = {
        "model": ollama_model,
        "messages": [
            {"role": "system", "content": _BLURB_SYSTEM},
            {"role": "user", "content": context},
        ],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.3, "num_predict": 200},
    }
    poster = http_post
    if poster is None:
        import requests

        poster = requests.post
    try:
        resp = poster(f"{ollama_host}/api/chat", json=payload, timeout=30)
        resp.raise_for_status()
        result = (resp.json().get("message") or {}).get("content") or ""
        return _THINK_RE.sub("", result).strip()
    except Exception:
        return ""


def _run_git(args: list[str], cwd: str, timeout: int = _GIT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def _remote_url(repo_path: str) -> str:
    try:
        proc = _run_git(["git", "config", "--get", "remote.origin.url"], repo_path, timeout=10)
        if proc.returncode == 0:
            return (proc.stdout or "").strip()
    except Exception:
        pass
    return ""


def _fetch_repo(repo_path: str) -> str:
    """Return empty string on success, or a warning."""
    try:
        proc = _run_git(["git", "fetch", "--all", "--prune"], repo_path, timeout=60)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "fetch failed").strip().splitlines()
            detail = err[-1] if err else "fetch failed"
            return f"git fetch failed ({detail})"
    except subprocess.TimeoutExpired:
        return "git fetch timed out"
    except Exception as exc:
        return f"git fetch failed ({exc})"
    return ""


def _master_ref(repo_path: str) -> str:
    try:
        proc = _run_git(
            ["git", "rev-parse", "--verify", "origin/master"], repo_path, timeout=10
        )
        if proc.returncode == 0:
            return "origin/master"
    except Exception:
        pass
    return ""


def _parse_log(stdout: str, repo_name: str, remote_url: str) -> list[dict[str, Any]]:
    commits: list[dict[str, Any]] = []
    raw = (stdout or "").strip("\x1e").strip()
    if not raw:
        return commits
    for block in raw.split("\x1e"):
        parts = block.strip().split("\x1f")
        if len(parts) < 4:
            continue
        commits.append(
            {
                "hash": parts[0].strip(),
                "author": parts[1].strip(),
                "date": parts[2].strip(),
                "subject": parts[3].strip(),
                "body": parts[4].strip() if len(parts) > 4 else "",
                "repo_name": repo_name,
                "remote_url": remote_url,
            }
        )
    return commits


def collect_master_commits(
    repo_name: str,
    repo_path: str,
    date_from: str,
    date_to: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    if not os.path.isdir(repo_path):
        return [], [f"{repo_name}: repo folder not found ({repo_path})"]
    fetch_warn = _fetch_repo(repo_path)
    ref = _master_ref(repo_path)
    if not ref:
        if fetch_warn:
            warnings.append(f"{repo_name}: {fetch_warn}")
        warnings.append(f"{repo_name}: no origin/master ref")
        return [], warnings
    if fetch_warn:
        warnings.append(f"{repo_name}: {fetch_warn} (using local origin/master)")
    date_from, date_to = resolve_date_range(date_from, date_to)
    since = f"{date_from} 00:00:00"
    until = f"{date_to} 23:59:59"
    cmd = [
        "git",
        "log",
        ref,
        "--pretty=format:%H%x1f%an%x1f%ad%x1f%s%x1f%b%x1e",
        "--date=iso",
    ]
    cmd.append(f"--since={since}")
    cmd.append(f"--until={until}")
    try:
        proc = _run_git(cmd, repo_path, timeout=60)
    except Exception as exc:
        warnings.append(f"{repo_name}: git log failed ({exc})")
        return [], warnings
    if proc.returncode != 0:
        err = (proc.stderr or "git log failed").strip().splitlines()
        warnings.append(f"{repo_name}: git log failed ({err[-1] if err else 'error'})")
        return [], warnings
    remote = _remote_url(repo_path)
    return _parse_log(proc.stdout, repo_name, remote), warnings


def _task_commit_links(task: dict[str, Any]) -> list[tuple[str, str]]:
    newest_by_repo: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for commit in task.get("commits") or []:
        repo = commit.get("repo_name") or ""
        if repo not in newest_by_repo:
            newest_by_repo[repo] = commit
            continue
        if (commit.get("date") or "") > (newest_by_repo[repo].get("date") or ""):
            newest_by_repo[repo] = commit
    links: list[tuple[str, str]] = []
    for repo, commit in newest_by_repo.items():
        url = bitbucket_commit_url(commit.get("remote_url") or "", commit.get("hash") or "")
        if url:
            links.append((repo, url))
    return links


def build_platform_report(
    platform_id: str,
    date_from: str,
    date_to: str,
    progress: ProgressFn | None = None,
    http_get: HttpGet | None = None,
    http_post: HttpPost | None = None,
    host: str | None = None,
    model: str | None = None,
) -> str:
    spec = require_platform(platform_id)
    date_from, date_to = resolve_date_range(date_from, date_to)

    label = spec["label"]
    all_commits: list[dict[str, Any]] = []
    warnings: list[str] = []
    repos = spec.get("repos") or []
    for idx, repo in enumerate(repos):
        name = repo["name"]
        path = repo["path"]
        if progress:
            progress(f"Updating {name} ({idx + 1}/{len(repos)})...")
        commits, repo_warnings = collect_master_commits(name, path, date_from, date_to)
        warnings.extend(repo_warnings)
        all_commits.extend(commits)

    grouped = group_commits_by_ticket(all_commits)
    tasks: list[dict[str, Any]] = []
    for _key, task in grouped.items():
        key = task["key"]
        first_subject = (task["subjects"][0] if task.get("subjects") else "") or key
        task["title"] = fallback_title(first_subject, key)
        task["jira_url"] = jira_browse_url(key)
        task["commit_links"] = _task_commit_links(task)
        tasks.append(task)

    tasks.sort(key=lambda item: item.get("merge_date") or "", reverse=True)
    total_found = len(tasks)
    if total_found > MAX_TASKS:
        warnings.append(
            f"Showing the {MAX_TASKS} most recent of {total_found} master-merged tasks."
        )
        tasks = tasks[:MAX_TASKS]
    for idx, task in enumerate(tasks):
        key = task.get("key") or ""
        if progress:
            progress(f"Summarizing {key} ({idx + 1}/{len(tasks)})...")
        jira_title = fetch_jira_title(key, http_get=http_get)
        if jira_title:
            task["title"] = jira_title
        task["blurb"] = summarize_ticket(task, host=host, model=model, http_post=http_post)
    if progress:
        progress(f"{len(tasks)} task(s)")
    return format_platform_report(label, date_from, date_to, tasks, warnings)
