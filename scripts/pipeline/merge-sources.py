"""
Merge per-source JSON files into a single briefing-data.json.

Reads all per-source JSON files from the output directory, maps them
into the schema expected by briefing-template.py, and writes:
  - briefing-data.json  (for the PDF template)
  - timing-log.json     (per-step timing from each source)

Usage: python merge-sources.py <output-dir>
"""
import json
import os
import sys
import time

SOURCE_META = {
    "arxiv-ml":         {"display": "Arxiv Machine Learning",       "category": "Deep Tech & Papers"},
    "arxiv":            {"display": "Arxiv AI",                     "category": "Deep Tech & Papers"},
    "openai-blog":      {"display": "OpenAI Developer Blog",        "category": "AI Lab Blogs"},
    "anthropic":        {"display": "Anthropic Engineering",         "category": "AI Lab Blogs"},
    "deepmind":         {"display": "Google DeepMind Blog",          "category": "AI Lab Blogs"},
    "techcrunch":       {"display": "TechCrunch AI",                "category": "Industry News"},
    "rundown":          {"display": "The Rundown AI",               "category": "Industry News"},
    "github-trending":  {"display": "GitHub Trending",              "category": "Developer Tools"},
    "mit-review":       {"display": "MIT Technology Review",        "category": "Industry News"},
}

GITHUB_SOURCE = "github-trending"


def load_source_json(output_dir: str, source_name: str) -> dict | None:
    path = os.path.join(output_dir, f"{source_name}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_per_source_data(all_data: dict) -> list:
    """Build the per_source_data array for briefing-template.py."""
    per_source = []
    for source_name, meta in SOURCE_META.items():
        if source_name == GITHUB_SOURCE:
            continue
        data = all_data.get(source_name)
        if not data or not data.get("items"):
            continue
        items = []
        for item in data["items"]:
            items.append({
                "title": item.get("title", ""),
                "date": item.get("date"),
                "summary": item.get("summary"),
                "points": item.get("points", []),
                "url": item.get("url", ""),
                "commentary": "",
                "prediction": "",
            })
        per_source.append({
            "name": meta["display"],
            "category": meta["category"],
            "items": items,
        })
    return per_source


def build_tools_data(all_data: dict) -> list:
    """Build the tools_data table for GitHub Trending."""
    data = all_data.get(GITHUB_SOURCE)
    if not data or not data.get("items"):
        return []
    rows = []
    for item in data["items"]:
        rows.append([
            item.get("title", ""),
            item.get("today_stars") or item.get("stars", ""),
            (item.get("summary") or "")[:100],
            item.get("language", ""),
        ])
    return rows


def build_timing_log(all_data: dict) -> list:
    """Extract per-source timing from _timing fields."""
    entries = []
    for source_name in SOURCE_META:
        data = all_data.get(source_name)
        if data and data.get("_timing"):
            entries.append(data["_timing"])
    return entries


def main():
    if len(sys.argv) < 2:
        print("Usage: python merge-sources.py <output-dir>")
        sys.exit(1)

    output_dir = sys.argv[1]
    t0 = time.monotonic()

    all_data = {}
    sources_used = []
    sources_unavailable = []

    for source_name, meta in SOURCE_META.items():
        data = load_source_json(output_dir, source_name)
        if data and data.get("items"):
            all_data[source_name] = data
            sources_used.append(meta["display"])
        else:
            sources_unavailable.append(meta["display"])

    briefing_data = {
        "sources_used": sources_used,
        "sources_unavailable": sources_unavailable,
        "week_in_review": None,
        "per_source_data": build_per_source_data(all_data),
        "tools_data": build_tools_data(all_data),
        "company_moves": [],
        "community_buzz": [],
        "cross_cutting_analysis": "",
        "big_picture_forecast": "",
        "personal_relevance": {
            "direct": [],
            "watch": [],
            "learn": [],
        },
        "skill_radar": [],
    }

    briefing_path = os.path.join(output_dir, "briefing-data.json")
    with open(briefing_path, "w", encoding="utf-8") as f:
        json.dump(briefing_data, f, ensure_ascii=False, indent=2)

    timing_entries = build_timing_log(all_data)
    timing_path = os.path.join(output_dir, "timing-log.json")
    existing_timing = {}
    if os.path.exists(timing_path):
        with open(timing_path, "r", encoding="utf-8") as f:
            existing_timing = json.load(f)

    existing_timing["sources_detail"] = timing_entries
    existing_timing["merge_seconds"] = round(time.monotonic() - t0, 2)

    with open(timing_path, "w", encoding="utf-8") as f:
        json.dump(existing_timing, f, ensure_ascii=False, indent=2)

    print(f"Merged {len(sources_used)} sources -> {briefing_path}")
    if sources_unavailable:
        print(f"Unavailable: {', '.join(sources_unavailable)}")
    print(f"Timing log updated: {timing_path}")


if __name__ == "__main__":
    main()
