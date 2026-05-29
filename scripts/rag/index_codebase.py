"""
Codebase Indexer — indexes project source code and docs into the RAG vector store.

Walks configured project directories, extracts meaningful chunks from:
- README/docs (Markdown files)
- Java source files (class/interface signatures, method summaries, package info)
- Configuration files (pom.xml dependencies, application.yml, persistence.xml)

Stores in the same Qdrant collection as other RAG content, searchable together.

Project directories come from two sources in .rag-projects.json:
  - base_dirs: root folders auto-discovered (each immediate subdirectory = project)
  - explicit_projects: manually listed {name, path} entries

Content-hash deduplication: files with identical content across different projects
are indexed only once (first occurrence wins).

Usage:
  python index_codebase.py                   Index all configured projects
  python index_codebase.py <project-path>    Index a specific project directory

Dependencies: pip install qdrant-client sentence-transformers
"""
import hashlib
import json
import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import date
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import SNAPSHOT_PATH, PROJECT_DIRS_PATH

COLLECTION = "ai_briefings"
VECTOR_SIZE = 384

SKIP_DIRS = {
    "node_modules", ".git", "target", "build", ".idea", ".vscode",
    ".gradle", "__pycache__", ".mvn", "bin", ".settings",
}

JAVA_EXTENSIONS = {".java"}
DOC_EXTENSIONS = {".md", ".adoc", ".txt", ".rst"}
CONFIG_FILES = {
    "pom.xml", "build.gradle", "application.yml", "application.yaml",
    "application.properties", "persistence.xml", "docker-compose.yml",
    "Dockerfile", "README.md", "CHANGELOG.md",
}

MAX_CHUNK_CHARS = 600

def load_project_dirs() -> list[dict]:
    """Load project directories from .rag-projects.json.

    Config format:
      {
        "base_dirs": ["D:/projects", ...],
        "explicit_projects": [{"name": "Foo", "path": "D:/other/foo"}, ...]
      }

    base_dirs: each immediate subdirectory becomes a project (name = folder name).
    explicit_projects: manually specified projects with custom names.
    Returns empty list if config file is missing or invalid.
    """
    if not os.path.isfile(PROJECT_DIRS_PATH):
        print(f"  Config not found: {PROJECT_DIRS_PATH}")
        print(f"  Create it with base_dirs and/or explicit_projects to index projects.")
        return []

    try:
        with open(PROJECT_DIRS_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"  Error reading {PROJECT_DIRS_PATH}: {e}")
        return []

    projects: list[dict] = []
    seen_paths: set[str] = set()

    for base_dir in cfg.get("base_dirs", []):
        base_dir = os.path.normpath(base_dir)
        if not os.path.isdir(base_dir):
            print(f"  Base dir not found, skipping: {base_dir}")
            continue
        for entry in sorted(os.listdir(base_dir)):
            entry_path = os.path.join(base_dir, entry)
            if not os.path.isdir(entry_path):
                continue
            if entry.startswith("."):
                continue
            norm = os.path.normcase(os.path.normpath(entry_path))
            if norm in seen_paths:
                continue
            seen_paths.add(norm)
            projects.append({"name": entry, "path": entry_path})

    for proj in cfg.get("explicit_projects", []):
        name = proj.get("name", "")
        path = proj.get("path", "")
        if not name or not path:
            continue
        norm = os.path.normcase(os.path.normpath(path))
        if norm in seen_paths:
            continue
        seen_paths.add(norm)
        projects.append({"name": name, "path": os.path.normpath(path)})

    if not projects:
        print("  No projects resolved from config (check base_dirs and explicit_projects)")

    return projects


def _get_model():
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


def _get_client():
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    if os.path.exists(SNAPSHOT_PATH):
        _load_snapshot(client)
    return client


def _load_snapshot(client):
    from qdrant_client.models import PointStruct
    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    points = data.get("points", [])
    for i in range(0, len(points), 100):
        batch = [
            PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
            for p in points[i:i + 100]
        ]
        client.upsert(collection_name=COLLECTION, points=batch)
    print(f"  Loaded {len(points)} existing points from snapshot")


def _save_snapshot(client):
    all_points = []
    offset = None
    while True:
        result = client.scroll(
            collection_name=COLLECTION,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        points, next_offset = result
        for p in points:
            all_points.append({
                "id": p.id,
                "vector": p.vector if isinstance(p.vector, list) else list(p.vector),
                "payload": p.payload,
            })
        if next_offset is None:
            break
        offset = next_offset

    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    _tmp = f"{SNAPSHOT_PATH}.tmp-{os.getpid()}"
    with open(_tmp, "w", encoding="utf-8") as f:
        json.dump({"points": all_points, "count": len(all_points)}, f)
    os.replace(_tmp, SNAPSHOT_PATH)
    print(f"  Saved {len(all_points)} total points to snapshot")


def _chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS, overlap: int = 100) -> list[str]:
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    prev_tail = ""
    for para in paragraphs:
        if not current:
            current = (prev_tail + "\n\n" + para).strip() if prev_tail else para
            continue
        if len(current) + len(para) > max_chars:
            chunks.append(current.strip())
            prev_tail = current[-overlap:] if len(current) > overlap else current
            current = prev_tail + "\n\n" + para
        else:
            current = current + "\n\n" + para
    if current.strip():
        chunks.append(current.strip())
    return chunks if chunks else [text[:max_chars]]


def _content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()


# ===================================================================
# JAVA FILE PROCESSING
# ===================================================================

_AI_IMPORT_KEYWORDS = {
    "openai", "langchain", "spring.ai", "azure.ai", "com.theokanning",
    "anthropic", "cohere", "huggingface", "deeplearning4j",
    "tensorflow", "pytorch", "onnx", "opennlp", "weka",
    "ollama", "ai.djl", "smile.nlp",
}

_NOTABLE_IMPORT_PREFIXES = (
    "org.springframework.web", "org.springframework.security",
    "org.springframework.data", "org.springframework.kafka",
    "org.springframework.amqp", "org.springframework.cloud",
    "javax.ws.rs", "jakarta.ws.rs",
    "org.apache.http", "org.apache.kafka",
    "com.fasterxml.jackson", "io.swagger",
    "org.quartz", "org.camunda",
)

_REST_ANNOTATIONS = {
    "@RequestMapping", "@GetMapping", "@PostMapping", "@PutMapping",
    "@DeleteMapping", "@PatchMapping",
    "@GET", "@POST", "@PUT", "@DELETE", "@Path",
}


def _extract_java_summary(content: str, filepath: str) -> list[dict]:
    """Extract meaningful chunks from a Java source file with enriched metadata."""
    chunks = []
    lines = content.split("\n")

    package = ""
    imports: list[str] = []
    for line in lines:
        stripped = line.strip()
        m = re.match(r'package\s+([\w.]+)\s*;', stripped)
        if m:
            package = m.group(1)
        m2 = re.match(r'import\s+(?:static\s+)?([\w.*]+)\s*;', stripped)
        if m2:
            imports.append(m2.group(1))

    class_match = re.search(
        r'(/\*\*[\s\S]*?\*/\s*)?'
        r'((?:@\w+(?:\([^)]*\))?\s*)*)'
        r'(public\s+)?(?:abstract\s+)?(?:final\s+)?'
        r'(class|interface|enum|record)\s+'
        r'(\w+)(?:\s*<[^>]+>)?'
        r'(?:\s+extends\s+(\w+))?'
        r'(?:\s+implements\s+([\w,\s]+))?',
        content
    )

    if not class_match:
        return chunks

    javadoc = class_match.group(1) or ""
    class_annotations_raw = class_match.group(2) or ""
    kind = class_match.group(4)
    class_name = class_match.group(5)
    extends = class_match.group(6) or ""
    implements = class_match.group(7) or ""

    class_annotations = [a.strip() for a in re.findall(r'@\w+(?:\([^)]*\))?', class_annotations_raw)]

    javadoc_clean = re.sub(r'/\*\*|\*/|\*\s?', '', javadoc).strip()
    javadoc_clean = re.sub(r'@\w+.*', '', javadoc_clean).strip()

    notable_imports = []
    ai_imports = []
    for imp in imports:
        imp_lower = imp.lower()
        if any(kw in imp_lower for kw in _AI_IMPORT_KEYWORDS):
            ai_imports.append(imp)
        elif any(imp.startswith(prefix) for prefix in _NOTABLE_IMPORT_PREFIXES):
            notable_imports.append(imp)

    method_pattern = re.compile(
        r'(?:public|protected|private)\s+(?:static\s+)?(?:final\s+)?'
        r'(?:[\w<>\[\],\s]+)\s+(\w+)\s*\([^)]*\)',
    )
    methods = method_pattern.findall(content)
    methods = [m for m in methods if m != class_name and m not in ("toString", "hashCode", "equals")]

    summary_parts = [f"{kind} {class_name}"]
    if package:
        summary_parts.insert(0, f"package {package}")
    if class_annotations:
        summary_parts.append(f"annotations: {', '.join(class_annotations)}")
    if extends:
        summary_parts.append(f"extends {extends}")
    if implements:
        summary_parts.append(f"implements {implements.strip()}")
    if javadoc_clean:
        summary_parts.append(f"\n{javadoc_clean}")
    if ai_imports:
        summary_parts.append(f"\nAI/ML imports: {', '.join(ai_imports)}")
    if notable_imports:
        summary_parts.append(f"\nKey imports: {', '.join(notable_imports[:10])}")
    if methods:
        summary_parts.append(f"\nMethods: {', '.join(methods[:20])}")

    summary = "\n".join(summary_parts)
    rel_path = os.path.basename(filepath)

    item_type = "code_doc"
    if ai_imports:
        item_type = "ai_integration"

    chunks.append({
        "text": summary[:MAX_CHUNK_CHARS],
        "title": f"{class_name} ({kind})",
        "filename": rel_path,
        "item_type": item_type,
    })

    api_pattern = re.compile(
        r'(/\*\*[\s\S]*?\*/\s*)?'
        r'((?:@\w+(?:\([^)]*\))?\s*)+)?'
        r'(?:public)\s+(?:static\s+)?(?:final\s+)?'
        r'([\w<>\[\],\s]+)\s+(\w+)\s*\(([^)]*)\)',
    )
    for m in api_pattern.finditer(content):
        method_doc = m.group(1) or ""
        annotations = m.group(2) or ""
        return_type = m.group(3).strip()
        method_name = m.group(4)
        params = m.group(5).strip()

        if method_name in ("toString", "hashCode", "equals", class_name):
            continue

        annotation_list = re.findall(r'@\w+(?:\([^)]*\))?', annotations)
        has_rest = any(
            any(ra in a for ra in _REST_ANNOTATIONS)
            for a in annotation_list
        )
        has_doc = bool(method_doc.strip())
        if not has_rest and not has_doc:
            continue

        doc_clean = re.sub(r'/\*\*|\*/|\*\s?', '', method_doc).strip()
        doc_clean = re.sub(r'@\w+.*', '', doc_clean).strip()

        method_text = f"{class_name}.{method_name}({params}) -> {return_type}"
        if annotations.strip():
            method_text = annotations.strip() + "\n" + method_text
        if doc_clean:
            method_text += f"\n{doc_clean}"

        ep_item_type = "rest_endpoint" if has_rest else "code_doc"

        rest_path = ""
        if has_rest:
            path_match = re.search(r'(?:@\w+Mapping|@Path|@RequestMapping)\s*\(\s*["\']([^"\']+)', annotations)
            if path_match:
                rest_path = path_match.group(1)
            method_text = f"[REST {rest_path}] " + method_text if rest_path else method_text

        chunks.append({
            "text": method_text[:MAX_CHUNK_CHARS],
            "title": f"{class_name}.{method_name}()" + (f" [{rest_path}]" if rest_path else ""),
            "filename": rel_path,
            "item_type": ep_item_type,
        })

    return chunks


# ===================================================================
# DOC / CONFIG FILE PROCESSING
# ===================================================================

def _process_markdown(content: str, filepath: str) -> list[dict]:
    """Chunk a Markdown file into sections with feature-aware splitting."""
    filename = os.path.basename(filepath)
    fname_lower = filename.lower()
    title = filename
    m = re.match(r'^#\s+(.+)', content)
    if m:
        title = m.group(1).strip()

    is_readme = fname_lower in ("readme.md", "readme.txt", "readme.adoc")
    is_changelog = fname_lower in ("changelog.md", "changes.md", "release-notes.md")

    item_type = "code_doc"
    if is_readme:
        item_type = "project_readme"
    elif is_changelog:
        item_type = "project_changelog"

    sections = re.split(r'\n(?=#{1,3}\s)', content)
    chunks = []
    for section in sections:
        section = section.strip()
        if not section or len(section) < 30:
            continue
        section_title = title
        heading = re.match(r'^#{1,3}\s+(.+)', section)
        if heading:
            section_title = f"{title} > {heading.group(1).strip()}"

        for text_chunk in _chunk_text(section):
            chunks.append({
                "text": text_chunk,
                "title": section_title,
                "filename": filename,
                "item_type": item_type,
            })

    if not chunks:
        text_chunks = _chunk_text(content)
        chunks = [
            {"text": chunk, "title": f"{title} (part {i+1})", "filename": filename,
             "item_type": item_type}
            for i, chunk in enumerate(text_chunks)
        ]

    return chunks


_CONFIG_FEATURE_PATTERNS = {
    "database": (r"spring\.datasource|jdbc|hibernate|jpa\.properties|database\.url", "Database"),
    "ai_api": (r"openai|azure\.ai|anthropic|langchain|ollama|huggingface", "AI/ML API"),
    "messaging": (r"kafka|rabbitmq|amqp|jms|activemq", "Messaging"),
    "cache": (r"redis|ehcache|caffeine|hazelcast|cache\.type", "Caching"),
    "security": (r"security|oauth|jwt|keycloak|ldap|authentication", "Security"),
    "cloud": (r"aws|azure|gcp|s3|sqs|cloud\.config", "Cloud"),
    "monitoring": (r"actuator|prometheus|grafana|metrics|micrometer", "Monitoring"),
    "mail": (r"spring\.mail|smtp|email\.host", "Email"),
}


def _process_config(content: str, filepath: str) -> list[dict]:
    """Index a config file with feature detection from key-value patterns."""
    filename = os.path.basename(filepath)
    fname_lower = filename.lower()

    is_app_config = fname_lower in (
        "application.yml", "application.yaml", "application.properties",
        "application-dev.yml", "application-prod.yml", "bootstrap.yml",
    )

    detected_features = []
    if is_app_config:
        content_lower = content.lower()
        for _feat_key, (pattern, label) in _CONFIG_FEATURE_PATTERNS.items():
            if re.search(pattern, content_lower):
                detected_features.append(label)

    item_type = "config_analysis" if detected_features else "code_doc"

    config_text = content
    if detected_features:
        feature_header = f"Detected features: {', '.join(detected_features)}\n\n"
        config_text = feature_header + content

    if len(config_text) > MAX_CHUNK_CHARS * 2:
        config_text = config_text[:MAX_CHUNK_CHARS * 2]

    text_chunks = _chunk_text(config_text)
    title_base = filename
    if detected_features:
        title_base = f"{filename} [{', '.join(detected_features)}]"

    return [
        {"text": chunk, "title": f"{title_base} (part {i+1})", "filename": filename,
         "item_type": item_type}
        for i, chunk in enumerate(text_chunks)
    ]


def _parse_pom_xml(content: str, filepath: str, project_name: str) -> list[dict]:
    """Extract structured data from pom.xml: coordinates, dependencies, modules."""
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

        identity_parts = [
            f"Project: {project_name}",
            f"Maven coordinates: {group_id}:{artifact_id}:{version}",
            f"Packaging: {packaging}",
        ]
        if description:
            identity_parts.append(f"Description: {description}")

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

        _DEP_FEATURE_MAP = {
            "AI/ML": {"openai", "langchain", "spring-ai", "azure-ai", "anthropic", "ollama", "huggingface", "deeplearning4j", "tensorflow", "onnx"},
            "REST API": {"spring-boot-starter-web", "spring-webmvc", "jersey", "resteasy", "jaxrs"},
            "Database": {"spring-data-jpa", "hibernate", "mybatis", "spring-jdbc", "h2", "mysql-connector", "postgresql", "flyway", "liquibase"},
            "Messaging": {"spring-kafka", "spring-amqp", "spring-jms", "activemq", "rabbitmq"},
            "Security": {"spring-security", "keycloak", "oauth2", "jwt", "spring-boot-starter-security"},
            "Cloud": {"aws-sdk", "azure-sdk", "spring-cloud", "spring-boot-starter-cloud"},
            "Monitoring": {"spring-boot-starter-actuator", "micrometer", "prometheus", "slf4j"},
            "Testing": {"junit", "mockito", "spring-boot-starter-test", "testcontainers", "assertj"},
            "Caching": {"spring-boot-starter-cache", "ehcache", "caffeine", "redis", "hazelcast"},
        }

        deps_el = root.find(f"{ns}dependencies")
        if deps_el is not None:
            dep_lines = []
            detected_dep_features: dict[str, list[str]] = {}
            for dep in deps_el.findall(f"{ns}dependency"):
                g = dep.findtext(f"{ns}groupId") or ""
                a = dep.findtext(f"{ns}artifactId") or ""
                v = dep.findtext(f"{ns}version") or ""
                scope = dep.findtext(f"{ns}scope") or "compile"
                dep_lines.append(f"  {g}:{a}:{v} (scope: {scope})")
                dep_key = f"{g}:{a}".lower()
                for feature, keywords in _DEP_FEATURE_MAP.items():
                    if any(kw in dep_key for kw in keywords):
                        detected_dep_features.setdefault(feature, []).append(a)
            if dep_lines:
                dep_text = f"Project {project_name} dependencies:\n"
                if detected_dep_features:
                    feat_summary = "; ".join(
                        f"{feat}: {', '.join(arts[:3])}"
                        for feat, arts in sorted(detected_dep_features.items())
                    )
                    dep_text += f"Technology features: {feat_summary}\n\n"
                dep_text += "\n".join(dep_lines[:30])
                chunks.append({
                    "text": dep_text[:MAX_CHUNK_CHARS * 2],
                    "title": f"{project_name} (dependencies)",
                    "filename": filename,
                    "item_type": "project_dependency",
                })
            if detected_dep_features:
                tech_text = f"Project {project_name} technology stack:\n"
                for feat, arts in sorted(detected_dep_features.items()):
                    tech_text += f"  {feat}: {', '.join(arts)}\n"
                chunks.append({
                    "text": tech_text[:MAX_CHUNK_CHARS],
                    "title": f"{project_name} (technology stack)",
                    "filename": filename,
                    "item_type": "project_technology",
                })

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
        return _process_config(content, filepath)

    return chunks if chunks else _process_config(content, filepath)


def _generate_project_summary(
    project_name: str,
    project_path: str,
    all_chunks: list[dict],
) -> dict:
    """Generate a high-level project summary from indexed chunks."""
    java_classes = []
    identity_info = ""
    rest_endpoints: list[str] = []
    ai_classes: list[str] = []
    tech_stack = ""

    for c in all_chunks:
        title = c.get("title", "")
        item_type = c.get("item_type", "")
        if "(class)" in title or "(interface)" in title or "(enum)" in title:
            java_classes.append(title.split(" (")[0])
        if item_type == "project_identity" and not identity_info:
            identity_info = c["text"]
        if item_type == "rest_endpoint":
            rest_endpoints.append(title)
        if item_type == "ai_integration":
            ai_classes.append(title.split(" (")[0])
        if item_type == "project_technology" and not tech_stack:
            tech_stack = c["text"]

    type_counts: dict[str, int] = {}
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

    if rest_endpoints:
        parts.append(f"REST endpoints ({len(rest_endpoints)}): "
                      + ", ".join(rest_endpoints[:10]))

    if ai_classes:
        parts.append(f"AI/ML integrations: {', '.join(ai_classes)}")

    if tech_stack:
        parts.append(tech_stack)

    return {
        "text": "\n".join(parts)[:MAX_CHUNK_CHARS * 3],
        "title": f"{project_name} (project summary)",
        "filename": "PROJECT_SUMMARY",
        "item_type": "project_summary",
    }


# ===================================================================
# MAIN INDEXING LOGIC
# ===================================================================

def index_project(
    project_name: str,
    project_path: str,
    model,
    client,
    seen_hashes: set[str] | None = None,
) -> tuple[int, int]:
    """Walk a project directory and index relevant files.

    Returns (chunk_count, files_deduped).
    seen_hashes: shared set of content hashes for cross-project deduplication.
    If a file's content hash is already in the set, it is skipped.
    """
    from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue

    if seen_hashes is None:
        seen_hashes = set()

    try:
        delete_filter = Filter(must=[
            FieldCondition(key="source", match=MatchValue(value=f"project:{project_name}")),
        ])
        old_ids = []
        offset = None
        while True:
            result = client.scroll(
                collection_name=COLLECTION,
                scroll_filter=delete_filter,
                limit=500,
                offset=offset,
                with_payload=False,
            )
            points, next_offset = result
            old_ids.extend(p.id for p in points)
            if next_offset is None:
                break
            offset = next_offset
        if old_ids:
            client.delete(collection_name=COLLECTION, points_selector=old_ids)
            print(f"  Removed {len(old_ids)} old chunks for {project_name}")
    except Exception as e:
        print(f"  Warning: failed to remove old chunks for {project_name}: {e}")

    all_chunks = []
    files_processed = 0
    files_deduped = 0

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        rel_root = os.path.relpath(root, project_path).replace("\\", "/")

        for fname in files:
            fpath = os.path.join(root, fname)
            ext = os.path.splitext(fname)[1].lower()

            try:
                if ext in JAVA_EXTENSIONS:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    if len(content) < 50:
                        continue
                    ch = _content_hash(content)
                    if ch in seen_hashes:
                        files_deduped += 1
                        continue
                    seen_hashes.add(ch)
                    chunks = _extract_java_summary(content, fpath)
                    for c in chunks:
                        c["rel_path"] = f"{rel_root}/{fname}"
                    all_chunks.extend(chunks)
                    files_processed += 1

                elif ext in DOC_EXTENSIONS or fname in CONFIG_FILES:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    if len(content) < 20:
                        continue
                    ch = _content_hash(content)
                    if ch in seen_hashes:
                        files_deduped += 1
                        continue
                    seen_hashes.add(ch)
                    if ext in DOC_EXTENSIONS:
                        chunks = _process_markdown(content, fpath)
                    elif fname == "pom.xml":
                        chunks = _parse_pom_xml(content, fpath, project_name)
                    else:
                        chunks = _process_config(content, fpath)
                    for c in chunks:
                        c["rel_path"] = f"{rel_root}/{fname}"
                    all_chunks.extend(chunks)
                    files_processed += 1

            except Exception:
                continue

    if all_chunks:
        summary_chunk = _generate_project_summary(project_name, project_path, all_chunks)
        all_chunks.insert(0, summary_chunk)

    if not all_chunks:
        print(f"  No indexable content found in {project_name}")
        if files_deduped:
            print(f"  ({files_deduped} files skipped as duplicates)")
        return 0, files_deduped

    print(f"  Processed {files_processed} files -> {len(all_chunks)} chunks" +
          (f" ({files_deduped} deduped)" if files_deduped else ""))
    print(f"  Generating embeddings...", end=" ", flush=True)

    texts = [c["text"] for c in all_chunks]
    embeddings = model.encode(texts, show_progress_bar=False).tolist()
    print("done")

    today = date.today().isoformat()
    points = []
    for chunk, emb in zip(all_chunks, embeddings):
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=emb,
            payload={
                "date": today,
                "source": f"project:{project_name}",
                "title": chunk["title"],
                "item_type": chunk.get("item_type", "code_doc"),
                "difficulty": "intermediate",
                "url": "",
                "filename": chunk.get("rel_path", chunk.get("filename", "")),
                "parent_title": project_name,
                "tags": [],
                "text": chunk["text"],
            },
        ))

    for i in range(0, len(points), 100):
        client.upsert(collection_name=COLLECTION, points=points[i:i + 100])

    print(f"  Indexed {len(points)} chunks for {project_name}")
    return len(points), files_deduped


def main():
    projects = load_project_dirs()

    if len(sys.argv) > 1:
        custom_path = sys.argv[1]
        if os.path.isdir(custom_path):
            name = os.path.basename(os.path.normpath(custom_path))
            projects = [{"name": name, "path": custom_path}]
        else:
            print(f"Error: {custom_path} is not a directory")
            sys.exit(1)

    print("Codebase Indexer — indexing project source code and docs")
    print(f"Projects: {len(projects)}")
    print()

    model = _get_model()
    client = _get_client()
    total = 0
    seen_hashes: set[str] = set()

    for proj in projects:
        name = proj["name"]
        path = proj["path"]
        if not os.path.isdir(path):
            print(f"  SKIP {name}: {path} not found")
            continue
        print(f"Indexing {name} ({path})...")
        count, _deduped = index_project(name, path, model, client, seen_hashes)
        total += count
        print()

    if total > 0:
        print(f"Saving snapshot ({total} new chunks)...")
        _save_snapshot(client)

    print(f"\nDone! Indexed {total} chunks across {len(projects)} projects.")
    print(f"Deduplication: {len(seen_hashes)} unique file hashes tracked.")


if __name__ == "__main__":
    main()
