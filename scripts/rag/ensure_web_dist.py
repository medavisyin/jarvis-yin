"""Ensure `web/dist` matches current frontend sources (used by jarvis-start.bat)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

SKIP_DIRS = {".git", "dist", "node_modules"}


def dist_index_path(web_root: str) -> str:
    return os.path.join(web_root, "dist", "index.html")


def needs_web_rebuild(web_root: str) -> bool:
    index = dist_index_path(web_root)
    if not os.path.isfile(index):
        return True
    dist_mtime = os.path.getmtime(index)
    for dirpath, dirnames, filenames in os.walk(web_root):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                if os.path.getmtime(path) > dist_mtime:
                    return True
            except OSError:
                continue
    return False


def _run_npm(web_root: str, *args: str) -> int:
    npm = shutil.which("npm")
    if not npm:
        print("WARNING: npm not on PATH; skip frontend build. Install Node.js or run: cd web && npm run build", flush=True)
        return 1
    cmd = [npm, *args]
    print(f"  {' '.join(cmd)}  (in {web_root})", flush=True)
    completed = subprocess.run(cmd, cwd=web_root, shell=(os.name == "nt"))
    return completed.returncode


def ensure_web_dist(web_root: str) -> int:
    web_root = os.path.abspath(web_root)
    if not os.path.isdir(web_root):
        print(f"WARNING: {web_root} missing; skip frontend build", flush=True)
        return 0
    if not needs_web_rebuild(web_root):
        print("web/dist is current; skip npm run build", flush=True)
        return 0
    print("Frontend sources newer than web/dist (or dist missing); building…", flush=True)
    if not os.path.isdir(os.path.join(web_root, "node_modules")):
        if _run_npm(web_root, "install") != 0:
            return 1
    return _run_npm(web_root, "run", "build")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        web_root = argv[0]
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        web_root = os.path.normpath(os.path.join(here, "..", "..", "web"))
    return ensure_web_dist(web_root)


if __name__ == "__main__":
    raise SystemExit(main())
