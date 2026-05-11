"""
Orchestrator: runs pre-flight check then all fetch scripts in parallel.

1. Runs preflight-check.py to test source reachability
2. Launches all 9 fetch-*.py scripts as parallel subprocesses
3. Waits for all to complete (per-script timeout: 180s)
4. Calls merge-sources.py to combine results + write timing log
5. Prints a summary of results and timing

Usage:
  python run-all-sources.py --output-dir <temp-dir>

If --output-dir is omitted, uses a temp folder under the current directory.

Dependencies: pip install playwright && playwright install chromium
"""
import argparse
import asyncio
import json
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))

FETCH_SCRIPTS = [
    "fetchers/ai/fetch-arxiv-ml.py",
    "fetchers/ai/fetch-arxiv.py",
    "fetchers/ai/fetch-openai-blog.py",
    "fetchers/ai/fetch-anthropic.py",
    "fetchers/ai/fetch-deepmind.py",
    "fetchers/ai/fetch-techcrunch.py",
    "fetchers/ai/fetch-rundown.py",
    "fetchers/ai/fetch-github-trending.py",
    "fetchers/ai/fetch-mit-review.py",
    "fetchers/ai/fetch-venturebeat.py",
    "fetchers/ai/fetch-theverge.py",
]

PER_SCRIPT_TIMEOUT = 180


async def run_script(script_name: str, output_dir: str) -> dict:
    """Run a single fetch script as a subprocess, return timing info."""
    script_path = os.path.join(SCRIPTS_ROOT, script_name)
    t0 = time.monotonic()
    result = {
        "script": script_name,
        "success": False,
        "seconds": 0,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
    }

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, script_path, output_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=PER_SCRIPT_TIMEOUT
        )
        result["exit_code"] = proc.returncode
        result["stdout"] = stdout.decode("utf-8", errors="replace").strip()
        result["stderr"] = stderr.decode("utf-8", errors="replace").strip()
        result["success"] = proc.returncode == 0
    except asyncio.TimeoutError:
        result["stderr"] = f"TIMEOUT after {PER_SCRIPT_TIMEOUT}s"
        try:
            proc.kill()
        except Exception:
            pass
    except Exception as exc:
        result["stderr"] = str(exc)[:300]
    finally:
        result["seconds"] = round(time.monotonic() - t0, 2)

    tag = "OK" if result["success"] else "FAIL"
    print(f"  [{tag}] {script_name:30s} {result['seconds']:6.1f}s")
    if result["stdout"]:
        print(f"         {result['stdout']}")
    if not result["success"] and result["stderr"]:
        print(f"         ERROR: {result['stderr'][:200]}")

    return result


async def run_preflight(output_dir: str) -> float:
    """Run the pre-flight check, return elapsed seconds."""
    script_path = os.path.join(SCRIPT_DIR, "preflight-check.py")
    t0 = time.monotonic()
    print("=== Phase 0: Pre-flight Check ===")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, script_path, output_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    elapsed = round(time.monotonic() - t0, 2)
    print(stdout.decode("utf-8", errors="replace"))
    if proc.returncode != 0:
        print(f"  Pre-flight stderr: {stderr.decode('utf-8', errors='replace')[:300]}")
    return elapsed


async def run_merge(output_dir: str) -> float:
    """Run the merge script, return elapsed seconds."""
    script_path = os.path.join(SCRIPT_DIR, "merge-sources.py")
    t0 = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        sys.executable, script_path, output_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    elapsed = round(time.monotonic() - t0, 2)
    out = stdout.decode("utf-8", errors="replace").strip()
    if out:
        print(f"  {out}")
    if proc.returncode != 0:
        print(f"  Merge stderr: {stderr.decode('utf-8', errors='replace')[:300]}")
    return elapsed


async def main():
    parser = argparse.ArgumentParser(description="Run all briefing source fetchers in parallel")
    parser.add_argument("--output-dir", default=None, help="Directory for per-source JSON output")
    parser.add_argument("--proxy", default=None, help="SOCKS5/HTTP proxy URL (e.g., socks5://localhost:10808)")
    parser.add_argument("--save-raw", action="store_true", default=True, help="Save raw drill-down content (default: enabled)")
    parser.add_argument("--no-save-raw", action="store_true", help="Disable raw content saving")
    args = parser.parse_args()

    if args.proxy:
        os.environ["BRIEFING_PROXY"] = args.proxy
        print(f"Proxy: {args.proxy}")

    if args.save_raw and not args.no_save_raw:
        os.environ["SAVE_RAW"] = "1"
        print("Raw content saving: enabled")

    output_dir = args.output_dir or os.path.join(os.getcwd(), "_briefing_tmp")
    os.makedirs(output_dir, exist_ok=True)

    grand_t0 = time.monotonic()

    preflight_seconds = await run_preflight(output_dir)

    print(f"\n=== Phase 1: Parallel Fetch ({len(FETCH_SCRIPTS)} sources) ===")
    tasks = [run_script(s, output_dir) for s in FETCH_SCRIPTS]
    results = await asyncio.gather(*tasks)

    succeeded = sum(1 for r in results if r["success"])
    failed = [r["script"] for r in results if not r["success"]]
    print(f"\n  {succeeded}/{len(results)} scripts succeeded")
    if failed:
        print(f"  Failed: {', '.join(failed)}")

    print("\n=== Phase 2: Merge ===")
    merge_seconds = await run_merge(output_dir)

    guide_seconds = 0
    raw_dir = os.path.join(output_dir, "raw")
    if os.path.isdir(raw_dir) and os.listdir(raw_dir):
        print("\n=== Phase 2.5: Learning Guide ===")
        guide_script = os.path.join(SCRIPTS_ROOT, "tools", "generate_learning_guide.py")
        guide_path = os.path.join(output_dir, "learning-guide.md")
        t = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            sys.executable, guide_script, raw_dir, guide_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        guide_seconds = round(time.monotonic() - t, 2)
        out = stdout.decode("utf-8", errors="replace").strip()
        if out:
            print(f"  {out}")
        raw_count = len([f for f in os.listdir(raw_dir) if f.endswith(".md")])
        print(f"  {raw_count} raw files saved, guide generated in {guide_seconds}s")

    index_seconds = 0
    index_script = os.path.join(SCRIPTS_ROOT, "rag", "index_briefing.py")
    if os.path.isfile(index_script):
        print("\n=== Phase 3: RAG Indexing ===")
        t = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            sys.executable, index_script, output_dir,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        index_seconds = round(time.monotonic() - t, 2)
        out = stdout.decode("utf-8", errors="replace").strip()
        if out:
            print(f"  {out}")
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            print(f"  Warning: RAG indexing failed (exit {proc.returncode})")
            if err:
                print(f"  {err[:200]}")
        else:
            print(f"  Indexed in {index_seconds}s")

    confluence_script = os.path.join(SCRIPTS_ROOT, "rag", "index_confluence.py")
    if os.path.isfile(confluence_script):
        print("\n=== Phase 3.5: Confluence Wiki Indexing ===")
        t = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            sys.executable, confluence_script,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        confluence_seconds = round(time.monotonic() - t, 2)
        out = stdout.decode("utf-8", errors="replace").strip()
        if out:
            print(f"  {out}")
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            print(f"  Warning: Confluence indexing failed (exit {proc.returncode})")
            if err:
                print(f"  {err[:200]}")
        else:
            print(f"  Confluence indexed in {confluence_seconds}s")

    world_news_script = os.path.join(SCRIPT_DIR, "run-world-news.py")
    if os.path.isfile(world_news_script):
        print("\n=== Phase 5: World News Fetch ===")
        t = time.monotonic()
        world_news_dir = os.path.join(output_dir, "world-news")
        os.makedirs(world_news_dir, exist_ok=True)
        cmd = [sys.executable, world_news_script, "--output-dir", world_news_dir]
        if args.proxy:
            cmd.extend(["--proxy", args.proxy])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            print(f"  Warning: World news fetch timed out after 180s")
            stdout, stderr = b"", b""
        world_news_seconds = round(time.monotonic() - t, 2)
        out = stdout.decode("utf-8", errors="replace").strip()
        if out:
            for line in out.split("\n"):
                print(f"  {line}")
        if proc.returncode and proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            print(f"  Warning: World news fetch failed (exit {proc.returncode})")
            if err:
                print(f"  {err[:200]}")
        else:
            print(f"  World news fetched in {world_news_seconds}s")

    grand_total = round(time.monotonic() - grand_t0, 2)

    timing_summary = {
        "date": time.strftime("%Y-%m-%d"),
        "preflight_seconds": preflight_seconds,
        "sources": [
            {"script": r["script"], "seconds": r["seconds"], "success": r["success"]}
            for r in results
        ],
        "merge_seconds": merge_seconds,
        "total_seconds": grand_total,
    }
    timing_path = os.path.join(output_dir, "timing-log.json")
    with open(timing_path, "w", encoding="utf-8") as f:
        json.dump(timing_summary, f, ensure_ascii=False, indent=2)

    print(f"\n=== Done in {grand_total}s ===")
    print(f"  Output dir: {output_dir}")
    print(f"  Timing log: {timing_path}")
    print(f"  Briefing data: {os.path.join(output_dir, 'briefing-data.json')}")


if __name__ == "__main__":
    asyncio.run(main())
