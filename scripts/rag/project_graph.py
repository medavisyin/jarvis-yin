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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import PROJECT_GRAPH_PATH
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
    """Find all pom.xml files in a project and parse them. Root pom.xml is always first."""
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
    poms.sort(key=lambda p: p["pom_path"].count("/"))
    return poms


def build_graph() -> dict:
    """Build the project knowledge graph."""
    projects = load_project_dirs()
    if not projects:
        print("No projects configured.")
        return {"projects": {}, "artifact_index": {}, "total_projects": 0}

    project_data = {}
    artifact_to_project: dict[str, str] = {}

    for proj in projects:
        name = proj["name"]
        path = proj["path"]
        if not os.path.isdir(path):
            continue
        poms = _scan_project_poms(path)
        if not poms:
            project_data[name] = {
                "path": path,
                "coordinates": "",
                "groupId": "",
                "artifactId": "",
                "version": "",
                "packaging": "",
                "description": "",
                "modules": [],
                "parent": None,
                "pom_count": 0,
                "all_dependencies": [],
                "internal_dependencies": [],
                "depended_by": [],
            }
            continue

        root_pom = poms[0]
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
            if pom["artifactId"] and pom["artifactId"] != root_pom["artifactId"]:
                artifact_to_project[pom["artifactId"]] = name
            for dep in pom["dependencies"]:
                dep_key = f"{dep['groupId']}:{dep['artifactId']}"
                existing_keys = [d["key"] for d in project_data[name]["all_dependencies"]]
                if dep_key not in existing_keys:
                    project_data[name]["all_dependencies"].append({
                        "key": dep_key,
                        "version": dep["version"],
                        "scope": dep["scope"],
                    })

    all_group_ids = {pd["groupId"] for pd in project_data.values() if pd.get("groupId")}
    for name, data in project_data.items():
        for dep in data["all_dependencies"]:
            parts = dep["key"].split(":")
            dep_group = parts[0] if parts else ""
            dep_artifact = parts[1] if len(parts) > 1 else ""
            if dep_group in all_group_ids or dep_artifact in artifact_to_project:
                target = artifact_to_project.get(dep_artifact, dep["key"])
                if target != name:
                    existing_targets = [d["target"] for d in data["internal_dependencies"]]
                    if target not in existing_targets:
                        data["internal_dependencies"].append({
                            "target": target,
                            "artifact": dep["key"],
                            "version": dep["version"],
                        })

    for name, data in project_data.items():
        for internal_dep in data["internal_dependencies"]:
            target_name = internal_dep["target"]
            if target_name in project_data and name not in project_data[target_name]["depended_by"]:
                project_data[target_name]["depended_by"].append(name)

    return {
        "projects": project_data,
        "artifact_index": artifact_to_project,
        "total_projects": len(project_data),
    }


def save_graph(graph: dict) -> None:
    os.makedirs(os.path.dirname(PROJECT_GRAPH_PATH), exist_ok=True)
    with open(PROJECT_GRAPH_PATH, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)
    print(f"  Saved project graph to {PROJECT_GRAPH_PATH}")
    print(f"  {graph.get('total_projects', 0)} projects mapped")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build project knowledge graph")
    parser.add_argument("--print", action="store_true", dest="print_graph",
                        help="Print graph summary")
    args = parser.parse_args()

    graph = build_graph()
    save_graph(graph)

    if args.print_graph:
        for name, data in sorted(graph.get("projects", {}).items()):
            deps = [d["target"] for d in data.get("internal_dependencies", [])]
            by = data.get("depended_by", [])
            coords = data.get("coordinates", "no pom")
            print(f"\n{name} ({coords})")
            if deps:
                print(f"  depends on: {', '.join(deps)}")
            if by:
                print(f"  depended by: {', '.join(by)}")


if __name__ == "__main__":
    main()
