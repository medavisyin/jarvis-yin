"""
Tool function implementations for the Jarvis RAG agent.

Each function corresponds to one of the tools defined in schemas.py.
These are registered into the tool registry at startup by agent.py.
"""

import os
import subprocess
from datetime import datetime, timedelta
from typing import Any


def _get_dependencies():
    """Lazy import of shared dependencies to avoid circular imports."""
    from rag_engine import vector_search, load_project_graph
    return vector_search, load_project_graph


# Injected by agent.py at startup
_REPORTS_ROOT = ""
_JIRA_SCRIPT = ""
_TOOL_TIMEOUT = 120
_REPO_CONFIG = []

AUTHOR_ALIASES = {
    "rong yin": ["rong yin", "rong.yin"],
    "raymond shen": ["raymond shen"],
    "belen liu": ["belen liu", "belen.liu"],
    "eason li": ["eason li", "eason.li"],
    "johnny yang": ["johnny yang", "johnny.yang"],
    "charlotte jiang": ["charlotte jiang", "charlotte.jiang"],
    "christoph scheben": ["christoph scheben", "christoph.scheben"],
    "tobias troesch": ["tobias troesch", "tobias.troesch", "tobias.trösch"],
    "jan loeffler": ["jan loeffler", "jan.loeffler", "jan löffler"],
}


def init(*, reports_root: str, jira_script: str, tool_timeout: int,
         repo_config: list[dict]):
    """Called by agent.py at startup to inject configuration."""
    global _REPORTS_ROOT, _JIRA_SCRIPT, _TOOL_TIMEOUT, _REPO_CONFIG
    _REPORTS_ROOT = reports_root
    _JIRA_SCRIPT = jira_script
    _TOOL_TIMEOUT = tool_timeout
    _REPO_CONFIG = repo_config


def _author_matches(git_author: str, filter_names: list[str]) -> bool:
    """Check if a git author name matches any filter names (case-insensitive, alias-aware)."""
    if not filter_names:
        return True
    git_lower = git_author.strip().lower()
    for name in filter_names:
        name_lower = name.strip().lower()
        if git_lower == name_lower:
            return True
        aliases = AUTHOR_ALIASES.get(name_lower, [])
        if git_lower in aliases:
            return True
    return False


def tool_rag_search(query: str, top_k: int = 3, min_score: float = 0.3) -> str:
    """Semantic search across the full RAG store."""
    vector_search, _ = _get_dependencies()
    results = vector_search(query, top_k=min(top_k, 5), min_score=min_score)
    if not results:
        return "No relevant results found in the knowledge base."
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. [{r['source']}] {r['title']} ({r['date']}, score={r['score']})\n"
            f"   {r['text'][:300]}"
        )
    return "\n\n".join(lines)


def tool_briefing_search(query: str, date_from: str = "", date_to: str = "",
                         source: str = "") -> str:
    """Date-filtered search across AI briefings."""
    from qdrant_client.models import FieldCondition, MatchValue, Range
    vector_search, _ = _get_dependencies()
    conditions = []
    if date_from:
        conditions.append(FieldCondition(key="date", range=Range(gte=date_from)))
    if date_to:
        conditions.append(FieldCondition(key="date", range=Range(lte=date_to)))
    if source:
        conditions.append(FieldCondition(key="source", match=MatchValue(value=source)))
    results = vector_search(query, top_k=3, min_score=0.25, conditions=conditions or None)
    if not results:
        return "No briefing results found for the given filters."
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. [{r['date']}] {r['title']} (source={r['source']}, score={r['score']})\n"
            f"   {r['text'][:300]}"
        )
    return "\n\n".join(lines)


def tool_confluence_search(query: str, space: str = "") -> str:
    """Search indexed Confluence wiki pages."""
    from qdrant_client.models import FieldCondition, MatchValue
    vector_search, _ = _get_dependencies()
    conditions = [FieldCondition(key="item_type", match=MatchValue(value="wiki_page"))]
    if space:
        conditions.append(FieldCondition(key="space", match=MatchValue(value=space)))
    results = vector_search(query, top_k=3, min_score=0.25, conditions=conditions)
    if not results:
        return "No Confluence wiki pages found matching the query."
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. {r['title']} ({r['date']}, score={r['score']})\n"
            f"   {r['text'][:300]}"
        )
    return "\n\n".join(lines)


def tool_jira_report(report_dir: str = "") -> str:
    """Run the Jira/Confluence daily report and return the summary."""
    if not report_dir:
        report_dir = os.path.join(_REPORTS_ROOT, datetime.now().strftime("%Y-%m-%d"))
    if not os.path.isfile(_JIRA_SCRIPT):
        return f"Error: Jira report script not found at {_JIRA_SCRIPT}"
    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", _JIRA_SCRIPT,
             "-ReportDir", report_dir],
            capture_output=True, text=True, timeout=_TOOL_TIMEOUT,
        )
        output = result.stdout.strip()
        if result.returncode != 0 and result.stderr:
            output += f"\n[stderr]: {result.stderr[:300]}"
        return output[:2000] if output else "Jira report completed but produced no output."
    except subprocess.TimeoutExpired:
        return "Error: Jira report timed out."
    except Exception as e:
        return f"Error running Jira report: {e}"


def tool_commit_summary(hours: int = 24, authors: list[str] | None = None,
                        since_date: str = "", until_date: str = "") -> str:
    """Fetch remotes for key repos and scan all repos for recent commits."""
    if since_date:
        since_str = since_date + "T00:00:00"
    else:
        since = datetime.now() - timedelta(hours=hours)
        since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
    until_str = (until_date + "T23:59:59") if until_date else ""
    all_commits: list[str] = []
    fetched = 0
    scanned = 0

    repos = list(_REPO_CONFIG)
    known_paths = {os.path.normpath(r["path"]).lower() for r in repos}
    projects_root = "d:/projects"
    if os.path.isdir(projects_root):
        for entry in os.listdir(projects_root):
            full = os.path.join(projects_root, entry)
            if os.path.isdir(os.path.join(full, ".git")):
                norm = os.path.normpath(full).lower()
                if norm not in known_paths:
                    repos.append({"name": entry, "path": full})
                    known_paths.add(norm)

    configured_paths = {os.path.normpath(r["path"]).lower() for r in _REPO_CONFIG}
    for repo in repos:
        repo_path = repo["path"]
        if not os.path.isdir(repo_path):
            continue
        if os.path.normpath(repo_path).lower() in configured_paths:
            try:
                subprocess.run(
                    ["git", "-C", repo_path, "fetch", "--all", "--prune"],
                    capture_output=True, text=True, timeout=30,
                )
                fetched += 1
            except Exception:
                pass

        try:
            git_cmd = ["git", "-C", repo_path, "log", "--all",
                       f"--since={since_str}", "--format=%h|%an|%s|%ci"]
            if until_str:
                git_cmd.insert(5, f"--until={until_str}")
            result = subprocess.run(
                git_cmd,
                capture_output=True, text=True, timeout=30,
            )
            scanned += 1
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                seen = set()
                for line in lines:
                    parts = line.split("|", 3)
                    if len(parts) >= 4 and parts[0] not in seen:
                        if not _author_matches(parts[1], authors or []):
                            continue
                        seen.add(parts[0])
                        all_commits.append(
                            f"[{repo['name']}] {parts[0]} by {parts[1]}: {parts[2]} ({parts[3]})"
                        )
        except Exception:
            continue

    author_info = f" for {', '.join(authors)}" if authors else ""
    if since_date and until_date:
        period = f" ({since_date} to {until_date})"
    elif since_date:
        period = f" (since {since_date})"
    else:
        period = f" in the last {hours} hours"
    info = f"Scanned {scanned} repos ({fetched} fetched from remotes).\n"
    if not all_commits:
        return info + f"No commits found{author_info}{period}."
    return info + f"Found {len(all_commits)} commits{author_info}{period}:\n\n" + "\n".join(all_commits[:200])


def tool_analyze_image(image_description_request: str) -> str:
    """Placeholder — vision analysis is handled inline by the agent loop."""
    return (
        "Image analysis is performed directly by the model when the user "
        "uploads an image. The image is already in the conversation context."
    )


def tool_project_query(query_type: str = "list", project_name: str = "") -> str:
    """Query the project knowledge graph for info, dependencies, impact analysis."""
    _, load_project_graph = _get_dependencies()
    graph = load_project_graph()
    if not graph or "projects" not in graph:
        return "Project graph not available. Run: python scripts/rag/project_graph.py"

    projects = graph["projects"]

    if query_type == "list":
        lines = [f"Indexed projects ({len(projects)}):"]
        for name, data in sorted(projects.items()):
            coords = data.get("coordinates", "no pom")
            desc = data.get("description", "")
            line = f"  - {name}: {coords}"
            if desc:
                line += f" — {desc[:80]}"
            lines.append(line)
        return "\n".join(lines)

    matched = None
    if project_name:
        pn_lower = project_name.lower()
        for name in projects:
            if pn_lower in name.lower() or name.lower() in pn_lower:
                matched = name
                break
        if not matched:
            for aid, pname in graph.get("artifact_index", {}).items():
                if pn_lower in aid.lower():
                    matched = pname
                    break
    if not matched and project_name:
        return f"Project '{project_name}' not found. Use query_type='list' to see all projects."

    if query_type == "info" and matched:
        data = projects[matched]
        internal = data.get("internal_dependencies", [])
        by = data.get("depended_by", [])
        lines = [
            f"Project: {matched}",
            f"Coordinates: {data.get('coordinates', '')}",
            f"Path: {data.get('path', '')}",
            f"Packaging: {data.get('packaging', '')}",
            f"Description: {data.get('description', 'N/A')}",
            f"Modules: {', '.join(data.get('modules', [])) or 'none'}",
            f"POM files: {data.get('pom_count', 0)}",
        ]
        if internal:
            lines.append(f"Depends on: {', '.join(d['target'] for d in internal)}")
        if by:
            lines.append(f"Depended by: {', '.join(by)}")
        return "\n".join(lines)

    if query_type == "dependencies" and matched:
        data = projects[matched]
        internal = data.get("internal_dependencies", [])
        if not internal:
            return f"{matched} has no internal (cross-project) dependencies."
        lines = [f"{matched} depends on:"]
        for dep in internal:
            lines.append(f"  - {dep['target']} ({dep['artifact']})")
        return "\n".join(lines)

    if query_type == "dependents" and matched:
        data = projects[matched]
        by = data.get("depended_by", [])
        if not by:
            return f"No other projects depend on {matched}."
        return f"Projects that depend on {matched}: {', '.join(by)}"

    if query_type == "impact" and matched:
        data = projects[matched]
        by = data.get("depended_by", [])
        deps = [d["target"] for d in data.get("internal_dependencies", [])]
        lines = [f"Impact analysis for {matched}:"]
        lines.append(f"  Changes to {matched} could affect: {', '.join(by) if by else 'no other projects'}")
        lines.append(f"  {matched} depends on: {', '.join(deps) if deps else 'no internal projects'}")
        if by:
            lines.append(f"  CAUTION: {len(by)} downstream project(s) may need testing.")
        return "\n".join(lines)

    if query_type == "relationships":
        lines = ["Project dependency relationships:"]
        for name, data in sorted(projects.items()):
            internal = data.get("internal_dependencies", [])
            by = data.get("depended_by", [])
            if internal or by:
                lines.append(f"\n  {name}:")
                if internal:
                    lines.append(f"    uses: {', '.join(d['target'] for d in internal)}")
                if by:
                    lines.append(f"    used by: {', '.join(by)}")
        return "\n".join(lines)

    return "Invalid query_type. Use: list, info, dependencies, dependents, impact, relationships"


def get_all_tool_functions() -> dict[str, Any]:
    """Return a dict mapping tool names to their implementation functions."""
    return {
        "rag_search": tool_rag_search,
        "briefing_search": tool_briefing_search,
        "confluence_search": tool_confluence_search,
        "jira_report": tool_jira_report,
        "commit_summary": tool_commit_summary,
        "analyze_image": tool_analyze_image,
        "project_query": tool_project_query,
    }
