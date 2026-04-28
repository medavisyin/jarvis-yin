# Full Project Intelligence Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Enhance the RAG system so the agent chat can answer deep code-level AND architecture-level questions about all indexed projects — including cross-project relationships, dependency graphs, and impact analysis.

**Architecture:** Three-layer approach: (1) Enrich the indexing pipeline to capture structured project metadata (Maven dependencies, project summaries, relationship data), (2) Build a pre-computed project knowledge graph as a JSON artifact, (3) Enhance the agent with multi-hop retrieval, project-aware system prompt, and a "Projects" tool for graph queries. The qwen3:8b model is available as a UI option for complex project questions.

**Tech Stack:** Python, Flask, Qdrant (in-memory), sentence-transformers (all-MiniLM-L6-v2), Ollama (qwen3:8b for project mode), existing `.rag-store.json` snapshot system.

---

## Task 1: Enhanced Maven Dependency Extraction

**Files:**
- Modify: `scripts/rag/index_codebase.py`

**What:** Parse `pom.xml` files to extract structured dependency and module information instead of raw text chunking. Create relationship-aware chunks like "P4M depends on core-framework:2.1.0".

**Step 1: Add `_parse_pom_xml` function**

Add after `_process_config` function (~line 335):

```python
import xml.etree.ElementTree as ET

def _parse_pom_xml(content: str, filepath: str, project_name: str) -> list[dict]:
    """Extract structured data from pom.xml: groupId, artifactId, dependencies, modules."""
    filename = os.path.basename(filepath)
    chunks = []
    try:
        root = ET.fromstring(content)
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        group_id = (root.findtext(f"{ns}groupId") or
                    root.findtext(f"{ns}parent/{ns}groupId") or "unknown")
        artifact_id = root.findtext(f"{ns}artifactId") or "unknown"
        version = (root.findtext(f"{ns}version") or
                   root.findtext(f"{ns}parent/{ns}version") or "")
        packaging = root.findtext(f"{ns}packaging") or "jar"
        description = root.findtext(f"{ns}description") or ""

        # Project identity chunk
        identity_parts = [
            f"Project: {project_name}",
            f"Maven coordinates: {group_id}:{artifact_id}:{version}",
            f"Packaging: {packaging}",
        ]
        if description:
            identity_parts.append(f"Description: {description}")

        # Modules (for multi-module projects)
        modules_el = root.find(f"{ns}modules")
        if modules_el is not None:
            mods = [m.text for m in modules_el.findall(f"{ns}module") if m.text]
            if mods:
                identity_parts.append(f"Modules: {', '.join(mods)}")

        chunks.append({
            "text": "\n".join(identity_parts),
            "title": f"{project_name} (Maven identity)",
            "filename": filename,
            "item_type": "project_identity",
        })

        # Dependencies chunk
        deps_el = root.find(f"{ns}dependencies")
        if deps_el is not None:
            dep_lines = []
            for dep in deps_el.findall(f"{ns}dependency"):
                g = dep.findtext(f"{ns}groupId") or ""
                a = dep.findtext(f"{ns}artifactId") or ""
                v = dep.findtext(f"{ns}version") or ""
                scope = dep.findtext(f"{ns}scope") or "compile"
                dep_lines.append(f"  {g}:{a}:{v} (scope: {scope})")
            if dep_lines:
                dep_text = (
                    f"Project {project_name} dependencies:\n"
                    + "\n".join(dep_lines[:30])
                )
                chunks.append({
                    "text": dep_text[:MAX_CHUNK_CHARS * 2],
                    "title": f"{project_name} (dependencies)",
                    "filename": filename,
                    "item_type": "project_dependency",
                })

        # Dependency management (for parent POMs)
        dep_mgmt = root.find(f"{ns}dependencyManagement/{ns}dependencies")
        if dep_mgmt is not None:
            managed = []
            for dep in dep_mgmt.findall(f"{ns}dependency"):
                g = dep.findtext(f"{ns}groupId") or ""
                a = dep.findtext(f"{ns}artifactId") or ""
                v = dep.findtext(f"{ns}version") or ""
                managed.append(f"  {g}:{a}:{v}")
            if managed:
                mgmt_text = (
                    f"Project {project_name} managed dependencies (BOM):\n"
                    + "\n".join(managed[:30])
                )
                chunks.append({
                    "text": mgmt_text[:MAX_CHUNK_CHARS * 2],
                    "title": f"{project_name} (dependency management)",
                    "filename": filename,
                    "item_type": "project_dependency",
                })
    except ET.ParseError:
        # Fall back to text chunking if XML is malformed
        return _process_config(content, filepath)

    return chunks if chunks else _process_config(content, filepath)
```

**Step 2: Route pom.xml through the new parser**

In `index_project`, modify the file processing block. Where it currently has:

```python
elif ext in DOC_EXTENSIONS or fname in CONFIG_FILES:
    ...
    if ext in DOC_EXTENSIONS:
        chunks = _process_markdown(content, fpath)
    else:
        chunks = _process_config(content, fpath)
```

Change to:

```python
elif ext in DOC_EXTENSIONS or fname in CONFIG_FILES:
    ...
    if ext in DOC_EXTENSIONS:
        chunks = _process_markdown(content, fpath)
    elif fname == "pom.xml":
        chunks = _parse_pom_xml(content, fpath, project_name)
    else:
        chunks = _process_config(content, fpath)
```

**Step 3: Update the payload to use `item_type` from chunk when available**

In the point creation loop, change:

```python
"item_type": "code_doc",
```

To:

```python
"item_type": chunk.get("item_type", "code_doc"),
```

**Verify:** Run `python scripts/rag/index_codebase.py D:/projects/p4m` and check output includes "Maven identity" and "dependencies" chunks.

---

## Task 2: Auto-Generated Project Summary Chunks

**Files:**
- Modify: `scripts/rag/index_codebase.py`

**What:** After scanning all files in a project, generate an automatic summary chunk that describes the project at a high level — tech stack, main classes, directory structure, number of files.

**Step 1: Add `_generate_project_summary` function**

```python
def _generate_project_summary(
    project_name: str,
    project_path: str,
    all_chunks: list[dict],
) -> dict:
    """Generate a high-level project summary from indexed chunks."""
    java_classes = []
    doc_files = []
    config_files_found = []
    identity_info = ""
    dep_info = ""

    for c in all_chunks:
        title = c.get("title", "")
        item_type = c.get("item_type", "")
        if "(class)" in title or "(interface)" in title or "(enum)" in title:
            java_classes.append(title.split(" (")[0])
        elif item_type == "project_identity":
            identity_info = c["text"]
        elif item_type == "project_dependency":
            if not dep_info:
                dep_info = c["text"]

    # Count by file type
    type_counts = {}
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in JAVA_EXTENSIONS or ext in DOC_EXTENSIONS or f in CONFIG_FILES:
                type_counts[ext or f] = type_counts.get(ext or f, 0) + 1

    parts = [f"Project: {project_name}"]
    if identity_info:
        parts.append(identity_info)
    parts.append(f"Location: {project_path}")

    if type_counts:
        type_summary = ", ".join(f"{v} {k}" for k, v in sorted(
            type_counts.items(), key=lambda x: -x[1]
        )[:10])
        parts.append(f"File composition: {type_summary}")

    if java_classes:
        parts.append(f"Key classes ({len(java_classes)} total): "
                      + ", ".join(java_classes[:20]))

    return {
        "text": "\n".join(parts)[:MAX_CHUNK_CHARS * 3],
        "title": f"{project_name} (project summary)",
        "filename": "PROJECT_SUMMARY",
        "item_type": "project_summary",
    }
```

**Step 2: Call it in `index_project` before embedding**

After the file walk loop, before `if not all_chunks:`, add:

```python
    summary_chunk = _generate_project_summary(project_name, project_path, all_chunks)
    all_chunks.insert(0, summary_chunk)
```

**Verify:** After reindexing, search for "project summary" in the Library tab of search_ui.py.

---

## Task 3: Build Project Knowledge Graph

**Files:**
- Create: `scripts/rag/project_graph.py`
- Modify: `scripts/config.py` (add `PROJECT_GRAPH_PATH`)

**What:** Pre-compute a project knowledge graph (JSON file) that maps relationships between projects based on Maven dependencies, shared packages, and module structure.

**Step 1: Add config path**

In `scripts/config.py`:

```python
PROJECT_GRAPH_PATH = os.path.join(REPORTS_ROOT, ".project-graph.json")
```

**Step 2: Create `project_graph.py`**

```python
"""
Project Knowledge Graph builder.

Scans all configured projects, extracts Maven coordinates and dependencies,
builds a graph of inter-project relationships, and saves as JSON.

Usage:
  python project_graph.py           Build/update the graph
  python project_graph.py --print   Print the graph summary
"""
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import PROJECT_GRAPH_PATH, PROJECT_DIRS_PATH
from index_codebase import load_project_dirs, SKIP_DIRS


def _parse_pom_coordinates(pom_path: str) -> dict | None:
    """Parse a pom.xml and return project coordinates + dependencies."""
    try:
        tree = ET.parse(pom_path)
        root = tree.getroot()
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        group_id = (root.findtext(f"{ns}groupId") or
                    root.findtext(f"{ns}parent/{ns}groupId") or "")
        artifact_id = root.findtext(f"{ns}artifactId") or ""
        version = (root.findtext(f"{ns}version") or
                   root.findtext(f"{ns}parent/{ns}version") or "")
        packaging = root.findtext(f"{ns}packaging") or "jar"
        description = root.findtext(f"{ns}description") or ""

        parent = None
        parent_el = root.find(f"{ns}parent")
        if parent_el is not None:
            parent = {
                "groupId": parent_el.findtext(f"{ns}groupId") or "",
                "artifactId": parent_el.findtext(f"{ns}artifactId") or "",
                "version": parent_el.findtext(f"{ns}version") or "",
            }

        deps = []
        for dep in root.findall(f"{ns}dependencies/{ns}dependency"):
            deps.append({
                "groupId": dep.findtext(f"{ns}groupId") or "",
                "artifactId": dep.findtext(f"{ns}artifactId") or "",
                "version": dep.findtext(f"{ns}version") or "",
                "scope": dep.findtext(f"{ns}scope") or "compile",
            })

        modules = []
        modules_el = root.find(f"{ns}modules")
        if modules_el is not None:
            modules = [m.text for m in modules_el.findall(f"{ns}module") if m.text]

        return {
            "groupId": group_id,
            "artifactId": artifact_id,
            "version": version,
            "packaging": packaging,
            "description": description,
            "parent": parent,
            "dependencies": deps,
            "modules": modules,
        }
    except (ET.ParseError, FileNotFoundError, PermissionError):
        return None


def _scan_project_poms(project_path: str) -> list[dict]:
    """Find all pom.xml files in a project and parse them."""
    poms = []
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if "pom.xml" in files:
            pom_path = os.path.join(root, "pom.xml")
            coords = _parse_pom_coordinates(pom_path)
            if coords:
                rel = os.path.relpath(pom_path, project_path).replace("\\", "/")
                coords["pom_path"] = rel
                poms.append(coords)
    return poms


def build_graph() -> dict:
    """Build the project knowledge graph."""
    projects = load_project_dirs()
    if not projects:
        print("No projects configured.")
        return {}

    # Phase 1: Scan all projects
    project_data = {}
    artifact_to_project = {}  # artifactId -> project name

    for proj in projects:
        name = proj["name"]
        path = proj["path"]
        if not os.path.isdir(path):
            continue
        poms = _scan_project_poms(path)
        if poms:
            root_pom = poms[0]  # first pom.xml is usually the root
            project_data[name] = {
                "path": path,
                "coordinates": f"{root_pom['groupId']}:{root_pom['artifactId']}:{root_pom['version']}",
                "groupId": root_pom["groupId"],
                "artifactId": root_pom["artifactId"],
                "version": root_pom["version"],
                "packaging": root_pom["packaging"],
                "description": root_pom["description"],
                "modules": root_pom["modules"],
                "parent": root_pom["parent"],
                "pom_count": len(poms),
                "all_dependencies": [],
                "internal_dependencies": [],
                "depended_by": [],
            }
            artifact_to_project[root_pom["artifactId"]] = name
            for pom in poms:
                for dep in pom["dependencies"]:
                    dep_key = f"{dep['groupId']}:{dep['artifactId']}"
                    if dep_key not in [d["key"] for d in project_data[name]["all_dependencies"]]:
                        project_data[name]["all_dependencies"].append({
                            "key": dep_key,
                            "version": dep["version"],
                            "scope": dep["scope"],
                        })

    # Phase 2: Resolve internal dependencies
    all_group_ids = {pd["groupId"] for pd in project_data.values() if pd["groupId"]}
    for name, data in project_data.items():
        for dep in data["all_dependencies"]:
            dep_group = dep["key"].split(":")[0]
            dep_artifact = dep["key"].split(":")[1] if ":" in dep["key"] else ""
            if dep_group in all_group_ids or dep_artifact in artifact_to_project:
                target = artifact_to_project.get(dep_artifact, dep["key"])
                data["internal_dependencies"].append({
                    "target": target,
                    "artifact": dep["key"],
                    "version": dep["version"],
                })

    # Phase 3: Build reverse dependencies
    for name, data in project_data.items():
        for internal_dep in data["internal_dependencies"]:
            target_name = internal_dep["target"]
            if target_name in project_data:
                project_data[target_name]["depended_by"].append(name)

    graph = {
        "projects": project_data,
        "artifact_index": artifact_to_project,
        "total_projects": len(project_data),
    }
    return graph


def save_graph(graph: dict) -> None:
    os.makedirs(os.path.dirname(PROJECT_GRAPH_PATH), exist_ok=True)
    with open(PROJECT_GRAPH_PATH, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)
    print(f"Saved project graph to {PROJECT_GRAPH_PATH}")
    print(f"  {graph.get('total_projects', 0)} projects mapped")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build project knowledge graph")
    parser.add_argument("--print", action="store_true", help="Print graph summary")
    args = parser.parse_args()

    graph = build_graph()
    save_graph(graph)

    if args.print:
        for name, data in graph.get("projects", {}).items():
            deps = [d["target"] for d in data.get("internal_dependencies", [])]
            by = data.get("depended_by", [])
            print(f"\n{name} ({data['coordinates']})")
            if deps:
                print(f"  depends on: {', '.join(deps)}")
            if by:
                print(f"  depended by: {', '.join(by)}")


if __name__ == "__main__":
    main()
```

**Verify:** Run `python scripts/rag/project_graph.py --print` and confirm it finds Maven relationships.

---

## Task 4: Project Graph Query Tool for the Agent

**Files:**
- Modify: `scripts/rag/agent.py`

**What:** Add a `project_query` tool the agent can call to query the project knowledge graph. This enables multi-hop reasoning: user asks "what depends on Core Framework?" → agent calls tool → gets structured answer → formulates response.

**Step 1: Add graph loading function**

Near the top of agent.py (after imports), add:

```python
from config import PROJECT_GRAPH_PATH

def _load_project_graph() -> dict:
    if not os.path.isfile(PROJECT_GRAPH_PATH):
        return {}
    try:
        with open(PROJECT_GRAPH_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
```

**Step 2: Add the `project_query` tool function**

```python
def tool_project_query(query_type: str, project_name: str = "") -> str:
    """Query the project knowledge graph.

    query_type: one of "list", "info", "dependencies", "dependents", "impact", "relationships"
    project_name: project name (case-insensitive fuzzy match)
    """
    graph = _load_project_graph()
    if not graph or "projects" not in graph:
        return "Project graph not available. Run: python scripts/rag/project_graph.py"

    projects = graph["projects"]

    if query_type == "list":
        lines = [f"Indexed projects ({len(projects)}):"]
        for name, data in sorted(projects.items()):
            lines.append(f"  - {name}: {data.get('coordinates', 'unknown')}")
        return "\n".join(lines)

    # Fuzzy match project name
    matched = None
    if project_name:
        pn_lower = project_name.lower()
        for name in projects:
            if pn_lower in name.lower() or name.lower() in pn_lower:
                matched = name
                break
        if not matched:
            # Try artifact ID match
            for aid, pname in graph.get("artifact_index", {}).items():
                if pn_lower in aid.lower():
                    matched = pname
                    break
    if not matched and project_name:
        return f"Project '{project_name}' not found. Use query_type='list' to see all projects."

    if query_type == "info" and matched:
        data = projects[matched]
        lines = [
            f"Project: {matched}",
            f"Coordinates: {data.get('coordinates', '')}",
            f"Path: {data.get('path', '')}",
            f"Packaging: {data.get('packaging', '')}",
            f"Description: {data.get('description', 'N/A')}",
            f"Modules: {', '.join(data.get('modules', [])) or 'none'}",
        ]
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
```

**Step 3: Register the tool in the tools list**

Find the existing tool definitions (search for `TOOL_DEFINITIONS` or the list of tool dicts near the tool-calling section) and add:

```python
{
    "type": "function",
    "function": {
        "name": "project_query",
        "description": "Query the project knowledge graph for project info, dependencies, dependents, impact analysis, or cross-project relationships. Use this when the user asks about project structure, what depends on what, or impact of changes.",
        "parameters": {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "enum": ["list", "info", "dependencies", "dependents", "impact", "relationships"],
                    "description": "Type of query: list (all projects), info (project details), dependencies (what it uses), dependents (what uses it), impact (change impact analysis), relationships (full graph)"
                },
                "project_name": {
                    "type": "string",
                    "description": "Project name (fuzzy matched). Required for info/dependencies/dependents/impact."
                }
            },
            "required": ["query_type"]
        }
    }
}
```

**Step 4: Add tool execution handler**

In the tool-calling dispatch section, add:

```python
elif tool_name == "project_query":
    result = tool_project_query(
        query_type=tool_args.get("query_type", "list"),
        project_name=tool_args.get("project_name", ""),
    )
```

**Verify:** In the Jarvis chat, ask "List all projects" or "What depends on Core Framework?" and confirm the agent uses the tool.

---

## Task 5: Enhanced System Prompt for Project Context

**Files:**
- Modify: `scripts/rag/agent.py`

**What:** When the retrieved RAG context contains `code_doc` or `project_*` chunks, inject additional project-aware instructions into the system prompt so the LLM knows how to reason about projects.

**Step 1: Add project context detection**

In `_auto_rag_search` or in `run_agent` where `rag_context` is assembled, after building the context string, detect if project chunks are present:

```python
has_project_context = any(
    r.get("item_type", "").startswith("project_") or r.get("item_type") == "code_doc"
    for r in results
)
```

**Step 2: Add project system prompt addon**

```python
SYSTEM_PROMPT_PROJECT_ADDON = """
When answering about MEDAVIS projects:
- Use the project knowledge graph tool (project_query) for dependency and relationship questions.
- Cite specific classes, modules, or Maven coordinates when relevant.
- For impact analysis, always check both upstream dependencies and downstream dependents.
- If the user asks about architecture, synthesize from project summaries, README content, and dependency structure.
- For cross-project questions, query multiple projects and correlate the information.
"""
```

**Step 3: Inject when project context is detected**

In `run_agent`, when building the system message, if `has_project_context`:

```python
if has_project_context:
    sys_prompt += "\n" + SYSTEM_PROMPT_PROJECT_ADDON
```

**Verify:** Ask a project question and verify the agent's response references project structure.

---

## Task 6: Add qwen3:8b to Model Dropdown

**Files:**
- Modify: `scripts/rag/agent.py`

**What:** Add qwen3:8b as a selectable model in the UI dropdown for users who want more capable reasoning on complex project questions.

**Step 1: Add option to the model select dropdown**

Find the model `<select>` in AGENT_HTML (~line 6690) and add:

```html
<option value="qwen3:8b">qwen3:8b (deep)</option>
```

After `qwen3:1.7b (fast)` option.

**Verify:** Load the Jarvis page and confirm qwen3:8b appears in the dropdown.

---

## Task 7: Add "Projects" Button to Medavis Toolbar

**Files:**
- Modify: `scripts/rag/agent.py`

**What:** Add a "Projects" button under the Medavis toolbar category that sends a pre-built prompt to explore project knowledge.

**Step 1: Add button in toolbar HTML**

In the Medavis toolbar section (~line 6775), add after "Team Activity" button:

```html
<button type="button" class="toolbar-btn" onclick="toolbarProjects()" title="Explore project knowledge and relationships">&#128187; Projects</button>
```

**Step 2: Add JavaScript handler**

```javascript
function toolbarProjects() {
  const msg = "Show me an overview of all MEDAVIS projects — list them with their key purpose, " +
    "technologies, and inter-project dependencies. Highlight which projects depend on each other.";
  document.getElementById('userInput').value = msg;
  sendMessage();
}
```

**Verify:** Click "Projects" in the Medavis toolbar and confirm it sends the prompt and gets a meaningful response.

---

## Task 8: Integrate Graph Build into Reindex Pipeline

**Files:**
- Modify: `scripts/rag/search_ui.py`
- Modify: `scripts/rag/reindex_all.py`

**What:** After project reindexing completes, automatically rebuild the project knowledge graph.

**Step 1: Update `_run_reindex_projects` in search_ui.py**

After `_save_snap_code(client)`, add:

```python
try:
    from project_graph import build_graph, save_graph
    graph = build_graph()
    save_graph(graph)
except Exception as e:
    print(f"  Warning: failed to build project graph: {e}")
```

**Step 2: Update `reindex_all.py`**

After `run_codebase(...)`, add:

```python
print("\n--- Project Graph ---")
try:
    from project_graph import build_graph, save_graph
    graph = build_graph()
    save_graph(graph)
    summary["indexed"].append(f"project graph ({graph.get('total_projects', 0)} projects)")
except Exception as e:
    summary["errors"].append(f"project graph: {e}")
```

**Verify:** Run "Reindex Projects" from the UI and confirm the project graph is rebuilt automatically.

---

## Task 9: Multi-Hop Retrieval Enhancement

**Files:**
- Modify: `scripts/rag/agent.py`

**What:** When the agent detects a cross-project question (mentions multiple projects or asks about relationships), perform multiple RAG queries — one per project mentioned — and combine the results for richer context.

**Step 1: Add multi-hop detection in `_auto_rag_search`**

After the initial search, check if results span multiple projects:

```python
project_sources = set()
for r in results:
    src = r.get("source", "")
    if src.startswith("project:"):
        project_sources.add(src.replace("project:", ""))

if len(project_sources) >= 2:
    # Multi-project query — enrich with graph context
    graph = _load_project_graph()
    if graph and "projects" in graph:
        graph_lines = []
        for pname in project_sources:
            pdata = graph["projects"].get(pname)
            if pdata:
                internal = pdata.get("internal_dependencies", [])
                by = pdata.get("depended_by", [])
                if internal:
                    graph_lines.append(
                        f"{pname} depends on: {', '.join(d['target'] for d in internal)}"
                    )
                if by:
                    graph_lines.append(f"{pname} is used by: {', '.join(by)}")
        if graph_lines:
            rag_context += "\n\n--- Project Relationships ---\n" + "\n".join(graph_lines)
```

**Verify:** Ask "How do P4M and Core Framework relate?" and verify the response includes dependency information.

---

## Summary

| Task | What | Impact |
|------|------|--------|
| 1 | Maven dependency extraction | Structured dependency chunks in RAG |
| 2 | Auto project summaries | High-level project understanding |
| 3 | Project knowledge graph | Pre-computed relationship data |
| 4 | Project query tool | Agent can query graph on demand |
| 5 | Project-aware system prompt | Better reasoning about projects |
| 6 | qwen3:8b in dropdown | User can choose more capable model |
| 7 | Projects toolbar button | Quick access to project overview |
| 8 | Graph build in reindex | Automatic graph updates |
| 9 | Multi-hop retrieval | Cross-project context enrichment |

**Execution order matters:** Tasks 1-3 build the data layer. Tasks 4-5 enhance the agent. Tasks 6-7 are UI. Task 8 integrates the pipeline. Task 9 is the final intelligence layer.
