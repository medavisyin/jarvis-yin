"""CLI for RAG evaluation and dataset management.

Usage:
    python eval_cli.py export [--no-vectors] [--output PATH]
    python eval_cli.py stats
    python eval_cli.py view [--source SOURCE] [--type TYPE] [--limit N] [--query TEXT]
    python eval_cli.py eval [--k 5] [--output PATH]
    python eval_cli.py seed
"""
import argparse
import io
import json
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)
sys.path.insert(0, os.path.join(_THIS_DIR, ".."))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from config import REPORTS_ROOT, SNAPSHOT_PATH


def cmd_export(args):
    """Export RAG store as a HF Dataset."""
    from dataset_adapter import load_snapshot_as_dataset

    include_vectors = not args.no_vectors
    ds = load_snapshot_as_dataset(SNAPSHOT_PATH, include_vectors=include_vectors)
    out = args.output or os.path.join(REPORTS_ROOT, "rag-dataset-export")
    ds.save_to_disk(out)
    print(f"Exported {len(ds)} chunks to: {out}")
    print(f"Columns: {ds.column_names}")
    if not args.no_vectors:
        print("  (includes vectors — use --no-vectors for smaller export)")


def cmd_stats(args):
    """Show statistics about the RAG store."""
    from dataset_adapter import load_snapshot_as_dataset

    ds = load_snapshot_as_dataset(SNAPSHOT_PATH, include_vectors=False)
    print(f"{'='*50}")
    print(f"  RAG Store Statistics")
    print(f"{'='*50}")
    print(f"  Total chunks: {len(ds)}")

    print(f"\n  By source:")
    sources = {}
    for row in ds:
        src = row.get("source", "") or "unknown"
        sources[src] = sources.get(src, 0) + 1
    for src, count in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"    {src}: {count}")

    print(f"\n  By item_type:")
    types = {}
    for row in ds:
        t = row.get("item_type", "") or "unknown"
        types[t] = types.get(t, 0) + 1
    for t, count in sorted(types.items(), key=lambda x: -x[1]):
        print(f"    {t}: {count}")

    dates = [row.get("date", "") for row in ds if row.get("date")]
    if dates:
        print(f"\n  Date range: {min(dates)} to {max(dates)}")

    print(f"{'='*50}")


def cmd_view(args):
    """Browse and inspect RAG store content interactively."""
    from dataset_adapter import load_snapshot_as_dataset

    ds = load_snapshot_as_dataset(SNAPSHOT_PATH, include_vectors=False)

    if args.source:
        ds = ds.filter(lambda x: x.get("source", "") == args.source)
    if args.type:
        ds = ds.filter(lambda x: x.get("item_type", "") == args.type)
    if args.query:
        query_lower = args.query.lower()
        ds = ds.filter(
            lambda x: query_lower in (x.get("text", "") or "").lower()
            or query_lower in (x.get("title", "") or "").lower()
        )

    limit = args.limit or 20
    total = len(ds)
    print(f"\nShowing {min(limit, total)} of {total} chunks")
    print(f"{'-'*70}")

    for i, row in enumerate(ds):
        if i >= limit:
            break
        title = row.get("title", "untitled")[:60]
        source = row.get("source", "?")
        item_type = row.get("item_type", "?")
        date = row.get("date", "")
        text_preview = (row.get("text", "") or "")[:120].replace("\n", " ")

        print(f"\n  [{i+1}] {title}")
        print(f"      source={source}  type={item_type}  date={date}")
        print(f"      {text_preview}...")

    print(f"\n{'-'*70}")
    if total > limit:
        print(f"  ({total - limit} more chunks not shown -- use --limit to see more)")

    if args.csv:
        df = ds.to_pandas()
        df.to_csv(args.csv, index=False)
        print(f"\n  CSV exported to: {args.csv}")


def cmd_eval(args):
    """Run evaluation against the RAG pipeline."""
    from datasets import Dataset
    from eval_runner import run_evaluation
    from rag_engine import get_qdrant, vector_search

    get_qdrant()

    eval_path = os.path.join(REPORTS_ROOT, "eval-dataset")
    if not os.path.exists(eval_path):
        print("No eval dataset found. Run 'seed' first:")
        print("  python eval_cli.py seed")
        sys.exit(1)

    eval_ds = Dataset.load_from_disk(eval_path)
    print(f"Running evaluation on {len(eval_ds)} queries (k={args.k})...\n")

    def search_fn(query, top_k=5):
        return vector_search(query, top_k=top_k)

    report = run_evaluation(eval_ds, search_fn, k=args.k)

    print(f"{'='*50}")
    print(f"  RAG Evaluation Results")
    print(f"{'='*50}")
    print(f"  Queries evaluated: {report.num_queries}")
    print(f"  Precision@{args.k}:     {report.metrics[f'precision@{args.k}']:.3f}")
    print(f"  Recall@{args.k}:        {report.metrics[f'recall@{args.k}']:.3f}")
    print(f"  MRR:              {report.metrics['mrr']:.3f}")
    print(f"{'='*50}")

    print(f"\n  Per-query breakdown:")
    for pq in report.per_query:
        status = "+" if pq["recall"] > 0 else "-"
        print(f"    [{status}] [{pq['category']}] {pq['query'][:50]}")
        print(f"        P={pq['precision']:.2f}  R={pq['recall']:.2f}  MRR={pq['mrr']:.2f}")

    if args.output:
        report.save(args.output)
        print(f"\n  Full report saved to: {args.output}")


def cmd_seed(args):
    """Run seed script to bootstrap eval dataset."""
    import seed_eval_data
    seed_eval_data.main()


def main():
    parser = argparse.ArgumentParser(
        description="RAG Evaluation & Data Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python eval_cli.py stats                       # Show store statistics
  python eval_cli.py view --source briefing      # Browse briefing chunks
  python eval_cli.py view --query "vector"       # Search chunks by text
  python eval_cli.py view --type wiki_page --csv out.csv  # Export to CSV
  python eval_cli.py export --no-vectors         # Export as HF Dataset
  python eval_cli.py seed                        # Bootstrap eval queries
  python eval_cli.py eval --k 5                  # Run evaluation
        """,
    )
    sub = parser.add_subparsers(dest="command")

    p_export = sub.add_parser("export", help="Export RAG store as HF Dataset")
    p_export.add_argument("--no-vectors", action="store_true",
                          help="Exclude embedding vectors (smaller export)")
    p_export.add_argument("--output", type=str, help="Output directory path")

    sub.add_parser("stats", help="Show RAG store statistics")

    p_view = sub.add_parser("view", help="Browse and inspect RAG store content")
    p_view.add_argument("--source", type=str,
                        help="Filter by source (briefing, codebase, confluence)")
    p_view.add_argument("--type", type=str,
                        help="Filter by item_type (news, readme, wiki_page, etc.)")
    p_view.add_argument("--query", type=str,
                        help="Search text in title and content")
    p_view.add_argument("--limit", type=int, default=20,
                        help="Max results to display (default: 20)")
    p_view.add_argument("--csv", type=str,
                        help="Export filtered results to CSV file")

    p_eval = sub.add_parser("eval", help="Run retrieval evaluation")
    p_eval.add_argument("--k", type=int, default=5,
                        help="Top-k cutoff for metrics (default: 5)")
    p_eval.add_argument("--output", type=str,
                        help="Save full JSON report to path")

    sub.add_parser("seed", help="Bootstrap eval dataset from seed queries")

    args = parser.parse_args()
    commands = {
        "export": cmd_export,
        "stats": cmd_stats,
        "view": cmd_view,
        "eval": cmd_eval,
        "seed": cmd_seed,
    }
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
