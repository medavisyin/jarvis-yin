# Chapter 5: HuggingFace Datasets Library

> How Jarvis uses the `datasets` library for RAG evaluation and data management.

## Does This Change the User Experience?

**No — this is a developer tool, not a user-facing feature.**

When you search in the Jarvis UI, the query still flows through:
`embed → vector search → BM25 hybrid → rerank → display`

The `datasets` integration helps **you as the developer** answer:
- "Is my search actually returning good results?"
- "Did my latest change make search better or worse?"
- "Which types of queries work well? Which don't?"

**Users benefit indirectly**: when you measure quality, you can improve it systematically instead of guessing.

## What is `datasets`?

The HuggingFace `datasets` library provides:
- **Arrow-backed storage** — fast, memory-efficient columnar data
- **Lazy operations** — filter/map/select without loading everything into RAM
- **Save/load** — persist datasets to disk and reload instantly
- **Pandas integration** — `ds.to_pandas()` for analysis
- **Streaming** — handle datasets larger than memory

## Why Jarvis Uses It

Jarvis stores all RAG chunks in `.rag-store.json` — a flat JSON file with vectors and payloads.
The `datasets` library gives us structured access to this data:

1. **Evaluation** — measure retrieval quality over time
2. **Inspection** — browse, filter, search chunks without loading vectors
3. **Export** — convert to CSV, pandas, or Arrow for analysis
4. **Versioning** — save snapshots of the eval dataset at different points

## Key Concepts

### Dataset = Table of Rows

```python
from datasets import Dataset

ds = Dataset.from_dict({
    "query": ["What is RAG?", "How does BM25 work?"],
    "answer": ["It combines search with LLM", "Sparse keyword scoring"],
})

# Access like a list
print(ds[0])  # {"query": "What is RAG?", "answer": "..."}

# Filter
rag_only = ds.filter(lambda x: "RAG" in x["query"])

# To pandas
df = ds.to_pandas()
```

### Features = Schema

```python
from datasets import Features, Value, Sequence

EVAL_FEATURES = Features({
    "query": Value("string"),
    "relevant_ids": Sequence(Value("string")),  # list of strings
    "answer": Value("string"),
    "category": Value("string"),
})
```

### Save/Load

```python
ds.save_to_disk("path/to/dataset")
loaded = Dataset.load_from_disk("path/to/dataset")
```

## Jarvis Integration

### Dataset Adapter Pattern

The adapter converts between Jarvis's custom JSON format and HF Dataset:

```python
from dataset_adapter import load_snapshot_as_dataset

# Load RAG store as browseable dataset
ds = load_snapshot_as_dataset("C:/reports/ai/.rag-store.json", include_vectors=False)

# How many chunks?
print(len(ds))  # e.g. 3500

# What sources?
sources = ds.unique("source")  # ["briefing", "codebase", "confluence"]

# Filter to just briefings
briefings = ds.filter(lambda x: x["source"] == "briefing")

# Search by text
vector_chunks = ds.filter(lambda x: "vector" in x["text"].lower())

# Export to CSV for Excel analysis
ds.to_csv("rag-export.csv")
```

### Evaluation Dataset

Stores **ground truth** for testing retrieval quality:

```python
from eval_dataset import create_eval_dataset, add_eval_example, EvalExample

ds = create_eval_dataset()
ds = add_eval_example(ds, EvalExample(
    query="What is RAG?",
    relevant_ids=["chunk-abc-001", "chunk-abc-002"],
    answer="Retrieval-Augmented Generation...",
    category="concept",
))
ds.save_to_disk("path/to/eval-dataset")
```

### Metrics

Standard information retrieval metrics:

| Metric | What it measures | Example |
|--------|-----------------|---------|
| Precision@5 | Of top-5 results, how many are relevant? | 3/5 = 0.6 |
| Recall@5 | Of all relevant docs, how many appear in top-5? | 3/4 = 0.75 |
| MRR | Where does the first relevant result appear? | 1st position → 1.0, 2nd → 0.5 |

### Running Evaluation

```bash
# 1. Bootstrap eval dataset from seed queries
python eval_cli.py seed

# 2. Run evaluation
python eval_cli.py eval --k 5

# Output:
# ==================================================
#   RAG Evaluation Results
# ==================================================
#   Queries evaluated: 8
#   Precision@5:     0.650
#   Recall@5:        0.825
#   MRR:             0.875
# ==================================================
```

## How This Connects to Learning

| Previous Chapter | This Chapter | Next Steps |
|-----------------|--------------|------------|
| Ch3: Model Selection | Ch4: Datasets | Fine-tuning (plan-ml-integration) |
| Chose `all-MiniLM-L6-v2` | Measure how well it retrieves | Use eval data to improve model |

## CLI Quick Reference

```bash
python eval_cli.py stats            # Store statistics
python eval_cli.py view             # Browse chunks
python eval_cli.py view --source X  # Filter by source
python eval_cli.py view --query X   # Search text
python eval_cli.py view --csv out   # Export filtered to CSV
python eval_cli.py export           # Export as HF Dataset
python eval_cli.py seed             # Bootstrap eval data
python eval_cli.py eval             # Run evaluation
```

## Key Takeaways

1. `datasets` is not just for ML training — it's a powerful data management tool
2. The adapter pattern lets you use HF Dataset operations on any JSON data
3. Evaluation is essential: without metrics, you can't know if changes help or hurt
4. The eval dataset grows over time as you add more ground-truth examples
5. MRR and Recall@k are the most important metrics for RAG (you want relevant docs ranked high)

## Further Reading

- [HuggingFace Datasets Documentation](https://huggingface.co/docs/datasets/)
- [Information Retrieval Metrics](https://en.wikipedia.org/wiki/Evaluation_measures_(information_retrieval))
- Jarvis implementation: `scripts/rag/eval_cli.py`, `scripts/rag/dataset_adapter.py`
