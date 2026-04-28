"""
Incremental RAG re-index orchestrator — runs briefing, codebase, and Confluence
indexers with a single Qdrant client and embedding model, tracks state in a manifest.

Usage:
  python reindex_all.py
  python reindex_all.py --force
  python reindex_all.py --force-briefings
  python reindex_all.py --force-codebase
  python reindex_all.py --force-confluence
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# Windows console UTF-8
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

_RAG_DIR = os.path.dirname(os.path.abspath(__file__))
if _RAG_DIR not in sys.path:
    sys.path.insert(0, _RAG_DIR)
sys.path.insert(0, os.path.join(_RAG_DIR, ".."))

import index_briefing as ib  # noqa: E402
import index_codebase as ic  # noqa: E402
import index_confluence as iconf  # noqa: E402
import index_confluence_user as icu  # noqa: E402
from config import MANIFEST_PATH  # noqa: E402

DEFAULT_CONFLUENCE_USER = "Rong Yin"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _parse_manifest_time(iso_str: str) -> datetime:
    s = (iso_str or "").strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _folder_mtime_utc(path: str) -> datetime:
    return datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)


def load_manifest() -> Dict[str, Any]:
    if not os.path.isfile(MANIFEST_PATH):
        return {
            "last_run": "",
            "briefings": {},
            "codebase": {},
            "confluence_team": {},
            "confluence_users": {},
        }
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  Warning: could not read manifest ({e}), starting fresh")
        data = {}
    data.setdefault("last_run", "")
    data.setdefault("briefings", {})
    data.setdefault("codebase", {})
    data.setdefault("confluence_team", {})
    data.setdefault("confluence_users", {})
    return data


def save_manifest(manifest: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"  Wrote manifest: {MANIFEST_PATH}")


def create_shared_model():
    return ib._get_model()


def create_shared_client():
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name=ib.COLLECTION,
        vectors_config=VectorParams(size=ib.VECTOR_SIZE, distance=Distance.COSINE),
    )
    if os.path.exists(ib.SNAPSHOT_PATH):
        ib._load_snapshot(client)
    return client


def count_briefing_files(date_folder: str) -> int:
    n = 0
    for _root, _dirs, files in os.walk(date_folder):
        n += len(files)
    return n


def codebase_content_hash(project_path: str) -> str:
    """Fast fingerprint: md5 over (relative path, size, mtime) for each file."""
    h = hashlib.md5()
    if not os.path.isdir(project_path):
        return ""
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in ic.SKIP_DIRS]
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                st = os.stat(fpath)
                rel = os.path.relpath(fpath, project_path).replace("\\", "/")
                line = f"{rel}\0{st.st_size}\0{st.st_mtime}\n"
                h.update(line.encode("utf-8", errors="replace"))
            except OSError:
                continue
    return h.hexdigest()


def norm_codebase_key(path: str) -> str:
    return os.path.normcase(os.path.normpath(path)).replace("\\", "/")


def list_briefing_date_folders() -> List[str]:
    root = ib.REPORTS_ROOT
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root)):
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", name):
            continue
        p = os.path.join(root, name)
        if os.path.isdir(p):
            out.append(p)
    return out


def briefing_needs_index(
    folder_path: str,
    manifest: Dict[str, Any],
    force: bool,
) -> Tuple[bool, str]:
    folder_date = os.path.basename(folder_path)
    if force:
        return True, "forced"
    entry = manifest.get("briefings", {}).get(folder_date)
    if not entry:
        return True, "not in manifest"
    indexed_at = entry.get("indexed_at", "")
    try:
        idx_dt = _parse_manifest_time(indexed_at)
    except Exception:
        return True, "invalid manifest time"
    folder_dt = _folder_mtime_utc(folder_path)
    if folder_dt > idx_dt:
        return True, "folder newer than indexed_at"
    return False, "up to date"


def codebase_project_needs_index(
    proj_path: str,
    manifest: Dict[str, Any],
    force: bool,
) -> Tuple[bool, str, str]:
    key = norm_codebase_key(proj_path)
    current = codebase_content_hash(proj_path)
    if force:
        return True, "forced", current
    if not current and not os.path.isdir(proj_path):
        return False, "path missing", current
    entry = manifest.get("codebase", {}).get(key)
    if not entry:
        return True, "not in manifest", current
    prev = entry.get("content_hash", "")
    if prev != current:
        return True, "content hash changed", current
    return False, "up to date", current


def confluence_team_needs_index(manifest: Dict[str, Any], force: bool) -> Tuple[bool, str]:
    if force:
        return True, "forced"
    entry = manifest.get("confluence_team") or {}
    indexed_at = entry.get("indexed_at", "")
    if not indexed_at:
        return True, "not in manifest"
    try:
        idx_dt = _parse_manifest_time(indexed_at)
    except Exception:
        return True, "invalid manifest time"
    if datetime.now(timezone.utc) - idx_dt > timedelta(hours=24):
        return True, "older than 24h"
    return False, "up to date"


def confluence_user_needs_index(
    display_name: str,
    manifest: Dict[str, Any],
    force: bool,
) -> Tuple[bool, str]:
    if force:
        return True, "forced"
    users = manifest.get("confluence_users") or {}
    entry = users.get(display_name) or {}
    indexed_at = entry.get("indexed_at", "")
    if not indexed_at:
        return True, "not in manifest"
    try:
        idx_dt = _parse_manifest_time(indexed_at)
    except Exception:
        return True, "invalid manifest time"
    if datetime.now(timezone.utc) - idx_dt > timedelta(days=7):
        return True, "older than 7 days"
    return False, "up to date"


def run_briefings(
    client,
    model,
    manifest: Dict[str, Any],
    force: bool,
    summary: Dict[str, List[str]],
) -> None:
    folders = list_briefing_date_folders()
    for folder_path in folders:
        folder_date = os.path.basename(folder_path)
        need, reason = briefing_needs_index(folder_path, manifest, force)
        if not need:
            summary["skipped"].append(f"briefing {folder_date} ({reason})")
            continue
        try:
            chunks = ib.index_date_folder(folder_path, client, model)
            fc = count_briefing_files(folder_path)
            manifest.setdefault("briefings", {})[folder_date] = {
                "indexed_at": _utc_now_iso(),
                "file_count": fc,
            }
            summary["indexed"].append(
                f"briefing {folder_date} ({chunks} chunks, {fc} files, {reason})"
            )
        except Exception as e:
            summary["errors"].append(f"briefing {folder_date}: {e}")


def run_codebase(
    client,
    model,
    manifest: Dict[str, Any],
    force: bool,
    summary: Dict[str, List[str]],
) -> None:
    projects = ic.load_project_dirs()
    seen_hashes: set[str] = set()
    for proj in projects:
        name = proj["name"]
        path = proj["path"]
        key = norm_codebase_key(path)
        need, reason, chash = codebase_project_needs_index(path, manifest, force)
        if not need:
            summary["skipped"].append(f"codebase {name} ({reason})")
            continue
        if not os.path.isdir(path):
            summary["skipped"].append(f"codebase {name} (path not found: {path})")
            continue
        try:
            chunk_count, _deduped = ic.index_project(name, path, model, client, seen_hashes)
            manifest.setdefault("codebase", {})[key] = {
                "indexed_at": _utc_now_iso(),
                "content_hash": chash,
                "chunk_count": chunk_count,
            }
            summary["indexed"].append(
                f"codebase {name} ({chunk_count} chunks, {reason})"
            )
        except Exception as e:
            summary["errors"].append(f"codebase {name}: {e}")


def run_confluence_team(
    client,
    model,
    manifest: Dict[str, Any],
    force: bool,
    summary: Dict[str, List[str]],
) -> None:
    need, reason = confluence_team_needs_index(manifest, force)
    if not need:
        summary["skipped"].append(f"confluence team ({reason})")
        return
    try:
        report_dir = os.path.join(ib.REPORTS_ROOT, date.today().isoformat())
        report_path = iconf.run_confluence_report(report_dir)
        if not report_path or not os.path.exists(report_path):
            summary["errors"].append("confluence team: no report file")
            return
        pages = iconf.parse_confluence_pages(report_path)
        page_count = len(pages)
        if not pages:
            summary["errors"].append("confluence team: no pages parsed")
            return
        chunks = iconf.index_confluence_pages(pages, client, model)
        manifest["confluence_team"] = {
            "indexed_at": _utc_now_iso(),
            "page_count": page_count,
        }
        summary["indexed"].append(
            f"confluence team ({chunks} chunks, {page_count} pages, {reason})"
        )
    except Exception as e:
        summary["errors"].append(f"confluence team: {e}")


def run_confluence_user_default(
    client,
    model,
    manifest: Dict[str, Any],
    force: bool,
    summary: Dict[str, List[str]],
    display_name: str,
) -> None:
    need, reason = confluence_user_needs_index(display_name, manifest, force)
    if not need:
        summary["skipped"].append(f"confluence user '{display_name}' ({reason})")
        return
    try:
        pages = icu.fetch_user_pages(display_name, limit=200)
        page_count = len(pages)
        if not pages:
            summary["errors"].append(
                f"confluence user '{display_name}': no pages fetched"
            )
            return
        chunks = icu.index_pages(pages, client, model)
        manifest.setdefault("confluence_users", {})[display_name] = {
            "indexed_at": _utc_now_iso(),
            "page_count": page_count,
        }
        summary["indexed"].append(
            f"confluence user '{display_name}' ({chunks} chunks, {page_count} pages, {reason})"
        )
    except Exception as e:
        summary["errors"].append(f"confluence user '{display_name}': {e}")


def print_summary(summary: Dict[str, List[str]]) -> None:
    print("\n" + "=" * 60)
    print("Re-index summary")
    print("=" * 60)
    for label, key in (
        ("Indexed", "indexed"),
        ("Skipped", "skipped"),
        ("Errors", "errors"),
    ):
        items = summary.get(key, [])
        print(f"\n{label} ({len(items)}):")
        if not items:
            print("  (none)")
        else:
            for line in items:
                print(f"  - {line}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Incremental RAG re-index orchestrator")
    parser.add_argument("--force", action="store_true", help="Force re-index all sources")
    parser.add_argument(
        "--force-briefings",
        action="store_true",
        help="Force re-index daily briefings only",
    )
    parser.add_argument(
        "--force-codebase",
        action="store_true",
        help="Force re-index codebase only",
    )
    parser.add_argument(
        "--force-confluence",
        action="store_true",
        help="Force re-index Confluence (team + user)",
    )
    args = parser.parse_args()

    force_all = args.force
    force_briefings = force_all or args.force_briefings
    force_codebase = force_all or args.force_codebase
    force_confluence = force_all or args.force_confluence

    manifest = load_manifest()
    summary: Dict[str, List[str]] = {
        "indexed": [],
        "skipped": [],
        "errors": [],
    }

    print("Re-index orchestrator — loading shared model and Qdrant client...")
    try:
        model = create_shared_model()
        client = create_shared_client()
    except Exception as e:
        print(f"Fatal: could not initialize model/client: {e}")
        return 1

    print("\n--- Briefings ---")
    try:
        run_briefings(client, model, manifest, force_briefings, summary)
    except Exception as e:
        summary["errors"].append(f"briefings (fatal wrap): {e}")

    print("\n--- Codebase ---")
    try:
        run_codebase(client, model, manifest, force_codebase, summary)
    except Exception as e:
        summary["errors"].append(f"codebase (fatal wrap): {e}")

    print("\n--- Confluence (team) ---")
    try:
        run_confluence_team(client, model, manifest, force_confluence, summary)
    except Exception as e:
        summary["errors"].append(f"confluence team (fatal wrap): {e}")

    print("\n--- Confluence (user) ---")
    try:
        run_confluence_user_default(
            client, model, manifest, force_confluence, summary, DEFAULT_CONFLUENCE_USER
        )
    except Exception as e:
        summary["errors"].append(f"confluence user (fatal wrap): {e}")

    print("\n--- Saving snapshot ---")
    try:
        ib._save_snapshot(client)
    except Exception as e:
        summary["errors"].append(f"snapshot save: {e}")

    manifest["last_run"] = _utc_now_iso()
    try:
        save_manifest(manifest)
    except Exception as e:
        summary["errors"].append(f"manifest save: {e}")

    print_summary(summary)
    return 0 if not summary["errors"] else 2


if __name__ == "__main__":
    sys.exit(main())
