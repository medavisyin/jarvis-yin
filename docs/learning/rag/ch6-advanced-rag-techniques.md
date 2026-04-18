# Chapter 6: Advanced RAG Techniques — Deep Dive

> A teaching guide to the techniques that separate basic RAG from production-quality systems.
> Each technique is explained with intuition, math where helpful, and real examples.

> **Implementation Status (April 2026):** All techniques described in this chapter are now implemented in Jarvis:
> - Hybrid Search (BM25 + Vector with RRF) — `bm25_index.py`, `search_ui.py`, `agent.py`
> - Cross-Encoder Re-Ranking — `reranker.py`, `search_ui.py`
> - Chunk Overlap — All 5 indexers
> - Query Rewriting — `agent.py` (`_rewrite_query`)
> - Feedback Collection & Weighted Ranking — `feedback_store.py`, both servers
> - Pipeline Visibility & Human-in-the-Loop Scoring — Search UI

---

## Why "Naive RAG" Isn't Enough

Naive RAG has three fundamental problems:

### Problem 1: The Vocabulary Mismatch

```
User asks:    "FHIR-R4 Patient resource validation"
Best chunk:   "The HL7 FHIR R4 standard defines Patient as a core resource..."
Vector score: 0.72 ✓ (found it!)

User asks:    "FHIR-R4"
Best chunk:   "The HL7 FHIR R4 standard defines Patient as a core resource..."
Vector score: 0.41 ✗ (too low! The embedding doesn't know "FHIR-R4" is an exact match)
```

**Why:** Vector search understands *meaning* but not *exact mentions*. Short acronyms get diluted in the 384-dimensional space.

**Solution:** Hybrid search (BM25 + vector).

### Problem 2: The Ranking Problem

```
Query: "How does P4M handle authentication?"

Vector results (cosine order):
  #1: "P4M uses Spring Boot for its backend services..." (score: 0.74) ← mentions P4M but not auth
  #2: "Authentication in P4M Next uses JWT tokens..." (score: 0.71)    ← THIS is the answer
  #3: "The admin app has a login page component..." (score: 0.69)      ← related but different app
```

**Why:** Bi-encoders (like MiniLM) encode query and document **independently**. They can't see the interaction between query terms and document terms.

**Solution:** Cross-encoder re-ranking.

### Problem 3: The Boundary Problem

```
Original document:
  "...The PACS connector handles DICOM routing.
   It uses configurable rules to forward studies | ← CHUNK BOUNDARY
   based on modality, station name, and AE title.
   Each rule specifies a destination..."

Chunk 1: "...The PACS connector handles DICOM routing. It uses configurable rules to forward studies"
Chunk 2: "based on modality, station name, and AE title. Each rule specifies a destination..."

Query: "What rules does the PACS connector use for DICOM routing?"
→ Neither chunk contains the full answer!
```

**Why:** Fixed-boundary chunking splits concepts arbitrarily.

**Solution:** Chunk overlap + semantic chunking.

---

## Technique 1: Hybrid Search (BM25 + Vector Fusion)

### What Is BM25?

BM25 (Best Matching 25) is the algorithm behind traditional search engines (Elasticsearch, Lucene). It scores documents by **how many query terms appear** and **how rare those terms are**.

```
BM25 Score Formula (simplified):

score(q, d) = Σ  IDF(term) × TF(term, d) × (k₁ + 1)
              ─────────────────────────────────────────
              TF(term, d) + k₁ × (1 - b + b × |d|/avgdl)

Where:
  IDF(term) = log((N - n + 0.5) / (n + 0.5))    ← Rare terms score higher
  TF(term, d) = frequency of term in document     ← More mentions = higher score
  k₁ = 1.2 (term frequency saturation)
  b = 0.75 (document length normalization)
  N = total documents, n = documents containing term
```

**Intuition:** BM25 rewards documents that contain the exact query words, especially rare words. "FHIR-R4" is rare, so any document containing it gets a high BM25 score.

### Why Combine BM25 + Vector?

| Query Type | BM25 | Vector | Winner |
|-----------|:----:|:------:|:------:|
| Exact keyword: "FHIR-R4" | **Strong** | Weak | BM25 |
| Semantic: "healthcare data exchange" | Weak | **Strong** | Vector |
| Mixed: "FHIR patient validation" | Medium | Medium | **Both** |

Neither alone is best. Together they cover both exact matches and semantic similarity.

### Reciprocal Rank Fusion (RRF)

The standard way to merge two ranked lists:

```
RRF_score(doc) = Σ  1 / (k + rank_in_list_i)
                 i

Where k = 60 (standard constant that prevents high-ranked items from dominating)
```

**Example:**
```
Vector results:  Doc_A (rank 1), Doc_B (rank 2), Doc_C (rank 3)
BM25 results:    Doc_B (rank 1), Doc_D (rank 2), Doc_A (rank 3)

RRF scores:
  Doc_A: 1/(60+1) + 1/(60+3) = 0.0164 + 0.0159 = 0.0323
  Doc_B: 1/(60+2) + 1/(60+1) = 0.0161 + 0.0164 = 0.0325  ← Winner!
  Doc_C: 1/(60+3) + 0         = 0.0159
  Doc_D: 0         + 1/(60+2) = 0.0161
```

Doc_B wins because it ranks well in **both** lists. This is more robust than simple score averaging because BM25 and cosine scores are on different scales.

---

## Technique 2: Cross-Encoder Re-Ranking

### Bi-Encoder vs Cross-Encoder

```
BI-ENCODER (what Jarvis uses now):
  Query:    "DICOM routing" ──→ [Encoder] ──→ vector_q
  Document: "PACS forwards..." ──→ [Encoder] ──→ vector_d
  Score = cosine(vector_q, vector_d)

  ✓ Fast: encode once, compare many
  ✗ Can't see query-document interaction

CROSS-ENCODER (re-ranker):
  [Query + Document] ──→ [Encoder] ──→ relevance_score

  ✗ Slow: must process each pair
  ✓ Sees the full interaction between query and document terms
```

### Why Cross-Encoders Are More Accurate

A bi-encoder must compress all meaning of "DICOM routing configuration" into 384 numbers **without knowing what document it will be compared to**. It has to represent everything about the query in advance.

A cross-encoder sees the query AND document together. It can notice:
- "routing" in the query matches "forwarding rules" in the document
- "configuration" in the query matches "configurable" in the document
- The document is specifically about DICOM, not general networking

This **attention across query and document** is why cross-encoders are 10-30% more accurate.

### The Two-Stage Pipeline

```
Stage 1: Bi-encoder retrieval (fast, approximate)
  18,500 chunks → cosine search → Top 20 candidates
  Time: ~35ms

Stage 2: Cross-encoder re-ranking (slow, precise)
  20 candidates → score each (query, doc) pair → Top 5 final
  Time: ~1 second (50ms × 20 pairs)

Total: ~1 second for much better results
```

### The Model: `ms-marco-MiniLM-L-6-v2`

| Property | Value |
|----------|-------|
| Architecture | 6-layer MiniLM (same family as the bi-encoder) |
| Training data | MS MARCO passage ranking (8.8M query-passage pairs) |
| Output | Single relevance score per (query, passage) pair |
| Speed | ~50ms per pair on CPU |
| Size | ~80 MB |

---

## Technique 3: Semantic Chunking

### The Problem with Fixed-Size Chunks

Current approach: split at paragraph boundaries, cap at 500 chars. This is **content-agnostic** — it doesn't know where concepts begin and end.

### Semantic Chunking: Let the Embedding Model Decide

```
Idea: Embed each sentence. When the embedding suddenly changes direction,
      that's a topic boundary → split there.

Sentence embeddings:
  S1: "FHIR defines resources."           → [0.12, 0.45, ...]  ─┐
  S2: "Patient is a core resource."        → [0.14, 0.43, ...]  ─┤ Similar → same chunk
  S3: "Resources have standard fields."    → [0.11, 0.47, ...]  ─┘
  S4: "The deployment uses Docker."        → [-0.33, 0.12, ...] ← BIG CHANGE → new chunk!
  S5: "Containers run on AWS ECS."         → [-0.31, 0.14, ...] ─┐ Similar → same chunk
  S6: "ECS tasks are defined in JSON."     → [-0.29, 0.16, ...] ─┘
```

### How It Works

1. Split document into sentences
2. Embed each sentence
3. Compute cosine similarity between consecutive sentences
4. Where similarity drops below a threshold → chunk boundary
5. Group sentences between boundaries into chunks

```python
from sentence_transformers import SentenceTransformer
import numpy as np

def semantic_chunk(text, model, threshold=0.5):
    sentences = text.split(". ")
    embeddings = model.encode(sentences)

    chunks = []
    current_chunk = [sentences[0]]

    for i in range(1, len(sentences)):
        sim = np.dot(embeddings[i-1], embeddings[i]) / (
            np.linalg.norm(embeddings[i-1]) * np.linalg.norm(embeddings[i])
        )
        if sim < threshold:
            chunks.append(". ".join(current_chunk))
            current_chunk = [sentences[i]]
        else:
            current_chunk.append(sentences[i])

    if current_chunk:
        chunks.append(". ".join(current_chunk))
    return chunks
```

### Trade-offs

| Approach | Speed | Quality | Complexity |
|----------|:-----:|:-------:|:----------:|
| Fixed-size (current) | Fast | Low | Simple |
| Paragraph-based (current) | Fast | Medium | Simple |
| Fixed + overlap | Fast | Medium-High | Simple |
| Semantic chunking | Slow (needs embedding) | High | Medium |
| Recursive (LangChain-style) | Medium | Medium-High | Medium |

**Recommendation:** Start with overlap (cheap win), then consider semantic chunking for high-value content like books and project docs.

---

## Technique 4: Query Rewriting & Expansion

### Types of Query Transformation

| Technique | Input | Output | When to Use |
|-----------|-------|--------|-------------|
| **Rewriting** | "that thing Jan mentioned" | "Jan Loeffler recent Confluence update" | Vague queries |
| **Expansion** | "FHIR validation" | "FHIR validation" + "HL7 resource conformance" | Technical queries |
| **Decomposition** | "Compare P4M and Admin App auth" | ["P4M auth", "Admin App auth"] | Complex queries |
| **HyDE** | "How does P4M auth work?" | (LLM generates hypothetical answer, embed that) | Any query |

### HyDE: Hypothetical Document Embeddings

A clever trick: instead of embedding the question, ask the LLM to **generate a hypothetical answer**, then embed that answer and search for similar real documents.

```
Query: "How does P4M handle authentication?"

Step 1: LLM generates hypothetical answer:
  "P4M uses Spring Security with JWT tokens. Users authenticate via
   the login endpoint which validates credentials against the database
   and returns a signed JWT token for subsequent API calls."

Step 2: Embed the hypothetical answer (not the question!)

Step 3: Search for real chunks similar to this hypothetical answer
  → Finds actual P4M auth documentation (much better match than
    embedding the short question)
```

**Why it works:** The hypothetical answer is in the same "language" as the actual documents. It's like searching with a document instead of a question.

---

## Technique 5: Parent-Child Chunk Linking

### The Problem

When you find a relevant chunk, you often want the surrounding context:

```
Search finds: "JWT tokens are validated using the public key..."
But you need: The full authentication flow (3 paragraphs before and after)
```

### The Solution: Hierarchical Chunks

```
Parent chunk (2000 chars):
  "Chapter 3: Authentication
   P4M uses Spring Security... JWT tokens... public key validation...
   Session management... token refresh... logout flow..."

Child chunks (500 chars each):
  Child 1: "P4M uses Spring Security with JWT..."
  Child 2: "JWT tokens are validated using the public key..."  ← Search finds this
  Child 3: "Session management handles token refresh..."

When child 2 is found → return parent chunk as context
```

**Implementation:** Store both parent and child chunks. Search on children (more specific), return parents (more context).

---

## Technique 6: Retrieval Evaluation Metrics

### How to Measure If Your RAG Is Good

| Metric | What It Measures | Formula |
|--------|-----------------|---------|
| **Recall@K** | Does the relevant doc appear in top K? | relevant_in_top_k / total_relevant |
| **MRR** | How high does the relevant doc rank? | 1/rank_of_first_relevant |
| **NDCG** | Are highly relevant docs ranked higher? | DCG / ideal_DCG |
| **Faithfulness** | Does the LLM answer match the context? | (claims_in_context / total_claims) |
| **Answer Relevance** | Does the answer address the question? | semantic_sim(question, answer) |

### Example Evaluation

```
Test query: "How does P4M handle DICOM routing?"
Known relevant chunk: chunk_id = "abc123"

System returns: [chunk_456, chunk_789, chunk_abc123, chunk_def, chunk_ghi]
                 rank 1     rank 2     rank 3         rank 4    rank 5

Recall@5 = 1/1 = 1.0  (found it in top 5 ✓)
Recall@1 = 0/1 = 0.0  (not in top 1 ✗)
MRR = 1/3 = 0.33      (found at rank 3)

After re-ranking: [chunk_abc123, chunk_456, chunk_789, chunk_def, chunk_ghi]
MRR = 1/1 = 1.0       (now at rank 1! ✓)
```

### Building a Test Set

You need 20-50 test queries with known relevant chunks:

```json
[
  {
    "query": "How does P4M handle DICOM routing?",
    "relevant_chunk_ids": ["abc123", "def456"],
    "category": "technical"
  },
  {
    "query": "What did Jan work on last sprint?",
    "relevant_chunk_ids": ["wiki_789"],
    "category": "team"
  }
]
```

Run this test set before and after each upgrade to measure improvement.

---

## Summary: The Advanced RAG Toolkit

```
┌─────────────────────────────────────────────────────────────────┐
│                    ADVANCED RAG PIPELINE                        │
│                                                                 │
│  Query ──→ Rewrite ──→ Hybrid Search ──→ Re-Rank ──→ Generate  │
│    │         │            │      │          │            │      │
│    │     LLM-based    Vector   BM25    Cross-encoder   LLM     │
│    │     expansion    (dense)  (sparse) (precise)    (answer)  │
│    │                     │      │          │                    │
│    │                     └──RRF─┘     Top 20→5                 │
│    │                                                            │
│    └── Evaluate ──→ [Good?] → proceed                          │
│                     [Bad?]  → rewrite & retry                  │
│                                                                 │
│  Indexing: Semantic chunks with overlap + parent-child linking  │
└─────────────────────────────────────────────────────────────────┘
```

Each technique addresses a specific weakness. Together they transform a basic search into a production-quality retrieval system.

---

*Next: [Chapter 7 — Machine Learning for Information Retrieval](ch7-ml-for-retrieval.md)*
