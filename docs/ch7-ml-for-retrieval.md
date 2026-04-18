# Chapter 7: Machine Learning for Information Retrieval

> A teaching guide to the ML concepts behind modern search systems.
> From classical IR to neural retrieval to learning-to-rank.

---

## The Evolution of Search

```
1990s           2000s           2010s           2020s           2025+
─────           ─────           ─────           ─────           ─────
TF-IDF     →   BM25       →   Word2Vec   →   BERT/Transformers → Fine-tuned
(term freq)    (probabilistic) (word vectors)  (contextual)       domain models
                                                                   + feedback loops
```

Each generation understood "relevance" at a deeper level:
- **TF-IDF:** A document is relevant if it contains the query words
- **BM25:** A document is relevant if it contains rare query words, adjusted for length
- **Word2Vec:** Words have meaning — "king" is to "queen" as "man" is to "woman"
- **BERT/Transformers:** Context matters — "bank" means different things in "river bank" vs "bank account"
- **Fine-tuned models:** Relevance is domain-specific — what matters in medical imaging is different from what matters in social media

---

## How Neural Embeddings Learn Meaning

### The Training Process

SentenceTransformers (like MiniLM) learn from **pairs of texts** with known relationships:

```
Training example 1:
  Text A: "A cat sits on a mat"
  Text B: "A feline rests on a rug"
  Label:  SIMILAR (score: 0.92)

Training example 2:
  Text A: "A cat sits on a mat"
  Text B: "The stock market crashed today"
  Label:  DISSIMILAR (score: 0.05)
```

The model adjusts its internal weights so that:
- Similar texts → vectors pointing in the same direction
- Dissimilar texts → vectors pointing in different directions

### Contrastive Learning (How It Actually Works)

```
                    ┌─────────────┐
  "A cat sits..." ──→│             │──→ vector_a ──┐
                    │  Transformer │               │
  "A feline..."  ──→│  (shared)    │──→ vector_b ──┤── cosine(a,b) = 0.95
                    └─────────────┘               │
                                                   │
                    Loss = max(0, margin - cos(a,b))│
                    If similar: push vectors closer │
                    If different: push apart        │
```

After seeing millions of pairs, the model learns general patterns:
- Synonyms map to similar vectors ("cat" ≈ "feline")
- Related concepts cluster together ("DICOM" near "medical imaging")
- Unrelated concepts are far apart ("DICOM" far from "banana")

### Why General Models Have Limits

The model was trained on **general English text** (Wikipedia, news, forums). It learned that:
- "doctor" ≈ "physician" ✓
- "machine learning" ≈ "AI" ✓

But it never saw your domain-specific data, so it doesn't know:
- "P4M" ≈ "PACS connector" (your product names)
- "FHIR-R4" ≈ "HL7 interoperability" (your standards)
- "Vaadin" ≈ "Java web UI" (your tech stack)

**This is why fine-tuning matters** — it teaches the model your domain's vocabulary.

---

## Fine-Tuning: Teaching the Model Your Domain

### What Changes During Fine-Tuning

```
BEFORE (general model):
  "P4M"  → [0.12, 0.03, -0.45, ...]   (generic, not meaningful)
  "PACS" → [0.33, -0.21, 0.67, ...]    (far from P4M)

AFTER (fine-tuned on your data):
  "P4M"  → [0.45, 0.78, -0.12, ...]    (now meaningful in your context)
  "PACS" → [0.43, 0.76, -0.14, ...]    (close to P4M!)
```

### The Three Loss Functions

| Loss | Training Data | How It Works | Best For |
|------|:------------:|-------------|----------|
| **CosineSimilarityLoss** | (text_a, text_b, score) | Push vectors to match the target similarity | When you have similarity scores |
| **TripletLoss** | (anchor, positive, negative) | Push anchor closer to positive, away from negative | When you have good/bad examples |
| **MultipleNegativesRankingLoss** | (query, positive) | Treat other batch items as negatives | When you only have positive pairs |

### Triplet Loss (Most Intuitive)

```
Anchor:   "How does P4M handle DICOM routing?"
Positive: "The PACS connector forwards studies based on routing rules..."  ← relevant
Negative: "JavaScript React component for the dashboard styling..."       ← irrelevant

Loss = max(0, distance(anchor, positive) - distance(anchor, negative) + margin)

If positive is closer than negative by at least `margin` → loss = 0 (good!)
If negative is closer → loss > 0 → adjust weights to fix this
```

### How Many Examples Do You Need?

| Dataset Size | Expected Improvement | Quality |
|:------------:|:-------------------:|:-------:|
| 50-100 pairs | 3-5% MRR improvement | Noticeable |
| 200-500 pairs | 10-15% MRR improvement | Significant |
| 1000-5000 pairs | 15-25% MRR improvement | Major |
| 10,000+ pairs | 20-30% MRR improvement | Near-optimal |

**Key insight:** You don't need millions of examples. 200-500 high-quality pairs from your domain can make a meaningful difference because you're **fine-tuning** (adjusting an already-trained model), not training from scratch.

### Avoiding Catastrophic Forgetting

When you fine-tune, the model might "forget" general knowledge while learning your domain:

```
Before: "machine learning" ≈ "AI"              (score: 0.89) ✓
After:  "machine learning" ≈ "AI"              (score: 0.52) ✗ ← forgot!
After:  "P4M" ≈ "PACS connector"              (score: 0.85) ✓ ← learned!
```

**Prevention strategies:**
1. **Low learning rate** (1e-5 to 2e-5) — small adjustments, not big rewrites
2. **Few epochs** (2-3) — stop before overfitting
3. **Mixed training data** — include some general pairs alongside domain pairs
4. **Evaluation on both** — test general AND domain queries

---

## Learning to Rank (LTR)

### Beyond Simple Similarity

Instead of just cosine similarity, train a model to predict relevance from **multiple features**:

```
Features for a (query, document) pair:
  f1: cosine similarity (vector search score)     = 0.72
  f2: BM25 score                                  = 12.4
  f3: document recency (days since creation)       = 3
  f4: chunk length (chars)                         = 450
  f5: source type (wiki=1, code=2, briefing=3)    = 1
  f6: historical click-through rate                = 0.35
  f7: query-title overlap (Jaccard)                = 0.40
  f8: feedback score (from user interactions)       = 0.70

LTR Model: f(f1, f2, ..., f8) → relevance_score
```

### Types of LTR

| Approach | How It Learns | Example |
|----------|--------------|---------|
| **Pointwise** | Predict absolute relevance score for each doc | Linear regression, neural net |
| **Pairwise** | Learn which of two docs is more relevant | RankNet, LambdaRank |
| **Listwise** | Optimize the entire ranking at once | LambdaMART, ListNet |

### A Simple LTR for Jarvis

```python
import numpy as np
from sklearn.linear_model import LogisticRegression

def train_ranker(training_data):
    """Train a simple LTR model from feedback data."""
    X = []  # feature vectors
    y = []  # labels (1=clicked, 0=not clicked)

    for example in training_data:
        features = [
            example["cosine_score"],
            example["bm25_score"],
            example["recency_days"],
            example["chunk_length"],
            example["feedback_score"],
        ]
        X.append(features)
        y.append(1 if example["clicked"] else 0)

    model = LogisticRegression()
    model.fit(np.array(X), np.array(y))
    return model

def predict_relevance(model, features):
    """Predict relevance probability for a (query, doc) pair."""
    return model.predict_proba([features])[0][1]
```

This is a simple starting point. Production systems use gradient-boosted trees (XGBoost, LightGBM) or neural rankers.

---

## Reinforcement Learning from Human Feedback (RLHF) for Retrieval

### The Concept

Instead of manually labeling training data, let the system learn from **user behavior**:

```
1. User searches → System returns results
2. User clicks result #3 (skipping #1 and #2)
3. System learns: #3 was more relevant than #1 and #2 for this query
4. Next time a similar query comes → #3-like results rank higher
```

### The Reward Signal

| User Action | Reward | Interpretation |
|------------|:------:|---------------|
| Click and read (>10s) | +1.0 | Relevant |
| Click and bounce (<3s) | +0.2 | Maybe relevant |
| Skip (shown but not clicked) | -0.3 | Probably not relevant |
| Reformulate query | -0.5 | Results were bad |
| Copy text | +1.5 | Very relevant |

### How It Improves the System

```
Week 1: Random ranking (no feedback yet)
  Query: "DICOM routing" → [Doc_A, Doc_B, Doc_C, Doc_D, Doc_E]
  User clicks: Doc_C

Week 2: Slightly better (learned from week 1)
  Query: "DICOM forwarding" → [Doc_C, Doc_A, Doc_B, Doc_D, Doc_E]
  User clicks: Doc_C (confirms) and Doc_D (new signal)

Week 4: Much better (accumulated feedback)
  Query: "study routing" → [Doc_C, Doc_D, Doc_A, Doc_B, Doc_E]
  User satisfied on first result!
```

### Implementation Levels

| Level | Complexity | What It Does |
|:-----:|:----------:|-------------|
| 1 | Low | Boost frequently-clicked chunks (simple counter) |
| 2 | Medium | Train a re-ranker on click data (logistic regression) |
| 3 | High | Fine-tune embeddings using click pairs as training data |
| 4 | Very High | Full RLHF with reward model and policy optimization |

**For Jarvis:** Start at Level 1 (feedback-weighted ranking), progress to Level 2 (trained re-ranker) after collecting enough data.

---

## Evaluation: How to Know If ML Is Helping

### Offline Evaluation (Before Deploying)

```python
def evaluate_retrieval(model, test_set):
    """Compute MRR and Recall@5 on a test set."""
    mrr_sum = 0
    recall_sum = 0

    for test in test_set:
        query = test["query"]
        relevant_ids = set(test["relevant_chunk_ids"])

        results = search(query, model, top_k=10)
        result_ids = [r["id"] for r in results]

        # MRR: reciprocal rank of first relevant result
        for rank, rid in enumerate(result_ids):
            if rid in relevant_ids:
                mrr_sum += 1.0 / (rank + 1)
                break

        # Recall@5: fraction of relevant docs in top 5
        top5_ids = set(result_ids[:5])
        recall_sum += len(top5_ids & relevant_ids) / len(relevant_ids)

    n = len(test_set)
    return {"MRR": mrr_sum / n, "Recall@5": recall_sum / n}
```

### Online Evaluation (After Deploying)

| Metric | How to Measure | Good Value |
|--------|---------------|:----------:|
| Click-through rate | clicks / impressions | > 40% |
| Mean reciprocal rank | 1/rank of first click | > 0.5 |
| Reformulation rate | queries followed by rephrased query | < 20% |
| Zero-result rate | queries with no results above threshold | < 5% |
| Time to first click | seconds from results shown to click | < 5s |

### A/B Testing

Run old and new systems side by side:

```
50% of queries → Old system (baseline)
50% of queries → New system (with ML improvements)

After 1 week, compare:
  Old: MRR = 0.45, CTR = 35%
  New: MRR = 0.62, CTR = 52%
  → New system is significantly better ✓
```

---

## The ML Maturity Ladder for Jarvis

```
Level 0 (Current):  Pre-trained embeddings, no learning
         ↓
Level 1:  Feedback collection + simple boosting
         ↓
Level 2:  Trained re-ranker (logistic regression on features)
         ↓
Level 3:  Fine-tuned embeddings (domain-adapted MiniLM)
         ↓
Level 4:  Continuous learning (feedback → retrain → deploy cycle)
         ↓
Level 5:  Full RLHF (reward model + policy optimization)
```

Each level builds on the previous. You can't skip to Level 5 without the data infrastructure from Level 1.

---

## Key Takeaways

1. **ML in search is about learning what "relevant" means for YOUR use case.** General models know general relevance. Fine-tuning teaches domain-specific relevance.

2. **You don't need big data.** 200-500 labeled pairs can improve retrieval by 10-15%. Start small, iterate.

3. **Feedback is the most valuable data.** Every user click is a training signal. Build the collection infrastructure first, then decide what to train.

4. **Simple ML often beats complex ML.** A logistic regression on 5 features (cosine score, BM25 score, recency, feedback score, chunk length) can outperform a complex neural ranker if you have limited data.

5. **Measure before and after.** Without evaluation metrics, you can't know if your ML is helping or hurting. Build a test set of 20-50 queries with known relevant documents.

---

*Back to: [Documentation Index](docs-index.md)*
