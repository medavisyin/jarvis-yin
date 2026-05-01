"""Bootstrap evaluation dataset by matching seed queries against the live RAG store.

Runs each seed query through vector search and picks top-3 results as
'relevant_ids' candidates. Human review is still needed to confirm/adjust.
"""
import json
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)
sys.path.insert(0, os.path.join(_THIS_DIR, ".."))

from config import REPORTS_ROOT
from eval_dataset import create_eval_dataset, add_eval_example, EvalExample

SEED_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "eval", "eval-seed.json"
)
EVAL_SAVE_PATH = os.path.join(REPORTS_ROOT, "eval-dataset")


def main():
    from rag_engine import get_embed_model, get_qdrant, vector_search

    get_qdrant()

    with open(SEED_PATH, "r", encoding="utf-8") as f:
        seeds = json.load(f)

    ds = create_eval_dataset()
    for seed in seeds:
        results = vector_search(seed["query"], top_k=3)
        candidate_ids = [r["id"] for r in results] if results else []

        if seed["relevant_ids"]:
            ids = seed["relevant_ids"]
        else:
            ids = candidate_ids

        ds = add_eval_example(
            ds,
            EvalExample(
                query=seed["query"],
                relevant_ids=ids,
                answer=seed.get("answer", ""),
                category=seed.get("category", ""),
                difficulty=seed.get("difficulty", "medium"),
                notes=seed.get("notes", ""),
            ),
        )
        print(f"  [{seed['category']}] {seed['query']}")
        print(f"    -> candidates: {candidate_ids[:3]}")

    ds.save_to_disk(EVAL_SAVE_PATH)
    print(f"\nEval dataset saved to: {EVAL_SAVE_PATH}")
    print(f"Total examples: {len(ds)}")
    print("\nREVIEW: Check relevant_ids are correct before running evaluation.")


if __name__ == "__main__":
    main()
