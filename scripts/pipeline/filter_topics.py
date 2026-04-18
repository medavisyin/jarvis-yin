"""
Topic Deduplication Filter — filters briefing items based on topic freshness.

Reads merged briefing-data.json, classifies each item against the topic index,
and outputs a filtered version with stale items removed (aggressive mode) or
shortened (conservative mode).

Usage:
  python filter-topics.py <briefing-data.json> <output-filtered.json> [--mode aggressive|conservative]

Default mode: aggressive (skip stale items entirely)

After filtering, the topic index at C:/reports/ai/topic-index.json is updated
with today's items.
"""
import json
import os
import sys
from datetime import date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from topic_index import TopicIndex  # noqa: E402


def filter_briefing(data: dict, mode: str = "aggressive",
                    today: str = None) -> dict:
    """
    Filter briefing data based on topic freshness.

    Returns a new dict with:
    - per_source_data: filtered items with classification tags
    - skipped_stale: list of items that were removed
    - filter_summary: stats about what was kept/skipped
    """
    today = today or date.today().isoformat()
    idx = TopicIndex()

    filtered_sources = []
    skipped_stale = []
    stats = {"new": 0, "updated": 0, "stale_skipped": 0, "total_input": 0}

    for source in data.get("per_source_data", []):
        filtered_items = []
        for item in source.get("items", []):
            stats["total_input"] += 1
            title = item.get("title", "")
            summary = item.get("summary", "") or ""

            result = idx.classify(title, summary, today)
            topic_id = result["topic_id"]
            classification = result["classification"]

            if classification == "new":
                stats["new"] += 1
                item["_dedup_tag"] = result["tag"]
                item["_topic_id"] = topic_id
                filtered_items.append(item)
                idx.update_topic(topic_id, title, today,
                                 _extract_delta(item), source["name"])

            elif classification == "updated":
                stats["updated"] += 1
                item["_dedup_tag"] = result["tag"]
                item["_topic_id"] = topic_id
                filtered_items.append(item)
                idx.update_topic(topic_id, title, today,
                                 _extract_delta(item), source["name"])

            else:  # stale
                if mode == "aggressive":
                    stats["stale_skipped"] += 1
                    skipped_stale.append({
                        "title": title,
                        "source": source["name"],
                        "tag": result["tag"],
                        "topic_id": topic_id,
                        "mention_count": result["mention_count"],
                    })
                    idx.update_topic(topic_id, title, today,
                                     "No significant new information",
                                     source["name"])
                else:
                    stats["updated"] += 1
                    item["_dedup_tag"] = result["tag"]
                    item["_topic_id"] = topic_id
                    item["_shortened"] = True
                    filtered_items.append(item)
                    idx.update_topic(topic_id, title, today,
                                     "No significant new information",
                                     source["name"])

        if filtered_items:
            filtered_source = dict(source)
            filtered_source["items"] = filtered_items
            filtered_sources.append(filtered_source)

    idx.save()

    result_data = dict(data)
    result_data["per_source_data"] = filtered_sources
    result_data["skipped_stale"] = skipped_stale
    result_data["filter_summary"] = {
        "mode": mode,
        "date": today,
        "total_input": stats["total_input"],
        "kept_new": stats["new"],
        "kept_updated": stats["updated"],
        "skipped_stale": stats["stale_skipped"],
        "total_kept": stats["new"] + stats["updated"],
    }

    return result_data


def _extract_delta(item: dict) -> str:
    """Extract a brief delta description from an item for the topic index."""
    summary = item.get("summary", "") or ""
    if len(summary) > 200:
        summary = summary[:200] + "..."
    return summary


def main():
    if len(sys.argv) < 3:
        print("Usage: python filter-topics.py <input.json> <output.json> [--mode aggressive|conservative]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    mode = "aggressive"
    if "--mode" in sys.argv:
        mode_idx = sys.argv.index("--mode")
        if mode_idx + 1 < len(sys.argv):
            mode = sys.argv[mode_idx + 1]

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = filter_briefing(data, mode=mode)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    summary = result["filter_summary"]
    print(f"Filter complete ({summary['mode']} mode):")
    print(f"  Input:   {summary['total_input']} items")
    print(f"  Kept:    {summary['total_kept']} ({summary['kept_new']} new, {summary['kept_updated']} updated)")
    print(f"  Skipped: {summary['skipped_stale']} stale items")

    if result.get("skipped_stale"):
        print(f"\n  Skipped items:")
        for s in result["skipped_stale"]:
            print(f"    - [{s['source']}] {s['title']} ({s['tag']})")


if __name__ == "__main__":
    main()
