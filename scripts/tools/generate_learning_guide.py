"""
Learning Guide Generator — creates a difficulty-rated reading list from raw content.

Reads all Markdown files in a raw/ directory and generates a learning-guide.md
that organizes them by difficulty with reading order suggestions.

Usage:
  python generate_learning_guide.py <raw-dir> <output-file>
  e.g.: python generate_learning_guide.py ./raw ./learning-guide.md
"""
import os
import re
import sys
from datetime import date
from typing import Dict, List, Tuple


DIFFICULTY_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}
DIFFICULTY_EMOJI = {"beginner": "B", "intermediate": "I", "advanced": "A"}
TIME_ESTIMATES = {"beginner": "~10 min read", "intermediate": "~20 min read", "advanced": "~30 min read"}


def _parse_raw_file(filepath: str) -> Dict:
    """Parse a raw Markdown file and extract metadata."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    title = ""
    source = ""
    file_date = ""
    difficulty = "intermediate"

    for line in content.split("\n"):
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.startswith("**Source:**"):
            source = line.replace("**Source:**", "").strip()
        elif line.startswith("**Date:**"):
            file_date = line.replace("**Date:**", "").strip()
        elif line.startswith("**Difficulty:**"):
            difficulty = line.replace("**Difficulty:**", "").strip().lower()

    body_lines = []
    in_body = False
    for line in content.split("\n"):
        if line.strip() == "---" and not in_body:
            in_body = True
            continue
        if in_body:
            body_lines.append(line)

    body_text = "\n".join(body_lines).strip()
    word_count = len(body_text.split())

    return {
        "filename": os.path.basename(filepath),
        "title": title,
        "source": source,
        "date": file_date,
        "difficulty": difficulty if difficulty in DIFFICULTY_ORDER else "intermediate",
        "word_count": word_count,
        "body_preview": body_text[:200] + "..." if len(body_text) > 200 else body_text,
    }


def _infer_prerequisites(difficulty: str, title: str) -> List[str]:
    """Infer prerequisite glossary terms based on title keywords."""
    prereqs = []
    title_lower = title.lower()

    keyword_prereqs = {
        "moe": ["MoE (Mixture-of-Experts)"],
        "mixture-of-experts": ["MoE (Mixture-of-Experts)"],
        "transformer": ["Transformer", "Attention"],
        "detr": ["DETR (Detection Transformer)", "Transformer"],
        "reinforcement learning": ["Reinforcement learning"],
        "gnn": ["GNN (Graph Neural Network)"],
        "graph neural": ["GNN (Graph Neural Network)"],
        "rlhf": ["RLHF / preference tuning"],
        "distillation": ["Distillation"],
        "lora": ["LoRA / adapter"],
        "rag": ["RAG (retrieval-augmented generation)"],
        "fine-tuning": ["Fine-tuning"],
        "sft": ["SFT (Supervised Fine-Tuning)"],
        "latent": ["Latent reasoning"],
        "agent": ["Agent", "Tool use / function calling"],
        "kolmogorov": ["Kolmogorov complexity"],
        "embedding": ["Embedding"],
        "quantization": ["Quantization"],
    }

    for keyword, terms in keyword_prereqs.items():
        if keyword in title_lower:
            prereqs.extend(terms)

    return list(dict.fromkeys(prereqs))


def generate_guide(raw_dir: str, output_path: str):
    """Generate learning-guide.md from raw content files."""
    if not os.path.isdir(raw_dir):
        print(f"Raw directory not found: {raw_dir}")
        return

    md_files = sorted(f for f in os.listdir(raw_dir) if f.endswith(".md"))
    if not md_files:
        print(f"No Markdown files found in {raw_dir}")
        return

    items = []
    for md_file in md_files:
        filepath = os.path.join(raw_dir, md_file)
        try:
            parsed = _parse_raw_file(filepath)
            items.append(parsed)
        except Exception as e:
            print(f"  Warning: could not parse {md_file}: {e}")

    items.sort(key=lambda x: DIFFICULTY_ORDER.get(x["difficulty"], 1))

    by_difficulty: Dict[str, List[Dict]] = {"beginner": [], "intermediate": [], "advanced": []}
    for item in items:
        by_difficulty.setdefault(item["difficulty"], []).append(item)

    today = date.today().isoformat()
    lines = [
        f"# Learning Guide -- {today}",
        "",
        "## How to Use This Guide",
        "",
        "Start with items marked [B] Beginner. Read the analyst notes in the PDF first,",
        "then come here for deeper understanding. Items marked [A] Advanced may require",
        "prerequisite concepts listed below each entry.",
        "",
        "Difficulty levels:",
        "- **[B] Beginner**: News articles, product announcements, GitHub tools",
        "- **[I] Intermediate**: Engineering blog posts with code, applied ML papers",
        "- **[A] Advanced**: Theoretical papers, math-heavy content, architecture papers",
        "",
        "---",
        "",
        "## Today's Reading List",
        "",
    ]

    item_num = 1
    for diff_level in ["beginner", "intermediate", "advanced"]:
        level_items = by_difficulty.get(diff_level, [])
        if not level_items:
            continue

        label = diff_level.capitalize()
        emoji = DIFFICULTY_EMOJI[diff_level]
        lines.append(f"### [{emoji}] {label}")
        lines.append("")

        for item in level_items:
            time_est = TIME_ESTIMATES.get(diff_level, "~15 min read")
            prereqs = _infer_prerequisites(diff_level, item["title"])

            lines.append(f"{item_num}. **{item['title']}**")
            lines.append(f"   - File: `raw/{item['filename']}`")
            lines.append(f"   - Time: {time_est} ({item['word_count']} words)")
            if item["source"]:
                lines.append(f"   - Source: {item['source']}")
            if prereqs and diff_level != "beginner":
                lines.append(f"   - Prerequisites: {', '.join(prereqs)}")
            lines.append("")
            item_num += 1

    lines.extend([
        "---",
        "",
        "## Suggested Reading Order",
        "",
    ])

    order_num = 1
    if by_difficulty.get("beginner"):
        first = by_difficulty["beginner"][0]
        lines.append(f"{order_num}. Start with: **{first['title']}** (easiest, builds context)")
        order_num += 1
    if by_difficulty.get("intermediate"):
        mid = by_difficulty["intermediate"][0]
        lines.append(f"{order_num}. Then: **{mid['title']}** (applies concepts to real systems)")
        order_num += 1
    if by_difficulty.get("advanced"):
        adv = by_difficulty["advanced"][0]
        lines.append(f"{order_num}. Deep dive: **{adv['title']}** (theoretical depth)")
        order_num += 1

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*Generated on {today} | {len(items)} articles available for deeper study*")
    lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Learning guide saved to: {output_path} ({len(items)} items)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python generate_learning_guide.py <raw-dir> <output-file>")
        sys.exit(1)
    generate_guide(sys.argv[1], sys.argv[2])
