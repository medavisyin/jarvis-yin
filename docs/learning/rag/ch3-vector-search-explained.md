# Chapter 3: Vector Search & Embeddings — How Semantic Search Actually Works

> This chapter explains the math and intuition behind vector search,
> why it's different from traditional keyword search, and how Jarvis uses it.

---

## Traditional Search vs. Semantic Search

### Keyword Search (BM25 / Elasticsearch / SQL LIKE)

Matches **exact words**:

```
Query: "DICOM routing configuration"
  ✓ Matches: "The DICOM routing configuration is set in..."
  ✗ Misses:  "Study forwarding rules are defined in the PACS connector"
  ✗ Misses:  "How images are automatically sent between modalities"
```

**Problem:** The last two documents are about the same topic but use different words. Keyword search can't find them.

### Semantic Search (Vector / Embedding-based)

Matches **meaning**:

```
Query: "DICOM routing configuration"
  ✓ Matches: "The DICOM routing configuration is set in..."         (score: 0.92)
  ✓ Matches: "Study forwarding rules are defined in the PACS connector" (score: 0.78)
  ✓ Matches: "How images are automatically sent between modalities"     (score: 0.71)
  ✗ Misses:  "JavaScript React component styling"                       (score: 0.12)
```

**How:** A neural network learned that "DICOM routing", "study forwarding", and "image sending between modalities" are semantically related.

---

## How Embeddings Work (Intuition)

### Step 1: Text → Numbers

A neural network (SentenceTransformer) reads your text and outputs a fixed-size array of numbers:

```
"DICOM routing" → [0.12, -0.45, 0.78, 0.03, ..., 0.33]
                    ↑      ↑      ↑      ↑          ↑
                   dim 1  dim 2  dim 3  dim 4  ...  dim 384
```

Each dimension captures some aspect of meaning. No single dimension means "medical" or "routing" — meaning is distributed across all 384 dimensions.

### Step 2: Similar Meanings → Nearby Vectors

The model was trained on millions of text pairs so that:
- Texts with similar meaning → vectors pointing in similar directions
- Texts with different meaning → vectors pointing in different directions

```
"DICOM routing"          ──→  ↗  (direction A)
"study forwarding rules" ──→  ↗  (almost same direction!)
"banana smoothie recipe" ──→  ↙  (completely different direction)
```

### Step 3: Search = Find Nearest Neighbors

At query time, embed the question and find the stored vectors closest to it:

```
Query vector:  ↗  (direction A)

Stored vectors:
  Chunk 1: ↗  (angle: 5°)   → cosine similarity: 0.996  ← very close!
  Chunk 2: ↗  (angle: 15°)  → cosine similarity: 0.966  ← close
  Chunk 3: →  (angle: 45°)  → cosine similarity: 0.707  ← somewhat related
  Chunk 4: ↓  (angle: 90°)  → cosine similarity: 0.000  ← unrelated
  Chunk 5: ↙  (angle: 150°) → cosine similarity: -0.866 ← opposite meaning
```

---

## The Math (Simplified)

### Cosine Similarity Formula

```
                    A · B           a₁b₁ + a₂b₂ + ... + a₃₈₄b₃₈₄
cos(θ) = ─────────────────── = ──────────────────────────────────────
              ‖A‖ × ‖B‖        √(a₁² + a₂² + ...) × √(b₁² + b₂² + ...)
```

- **Numerator (dot product):** How much the vectors "agree" in each dimension
- **Denominator (magnitudes):** Normalizes for vector length so only direction matters
- **Result:** -1 (opposite) to +1 (identical)

### Why Cosine and Not Euclidean Distance?

Cosine measures **direction**, not magnitude. Two documents about the same topic but different lengths should still match:

```
Short: "FHIR API"           → vector magnitude: 0.8
Long:  "FHIR API enables... (500 words)" → vector magnitude: 1.2

Cosine similarity: 0.95 (same direction = same topic ✓)
Euclidean distance: 0.4  (different magnitude = seems different ✗)
```

---

## The Embedding Model: all-MiniLM-L6-v2

### What Is It?

| Property | Value |
|----------|-------|
| Full name | `sentence-transformers/all-MiniLM-L6-v2` |
| Architecture | 6-layer MiniLM (distilled from BERT) |
| Output dimensions | 384 |
| Max input tokens | 256 tokens (~200 words) |
| Training data | 1B+ sentence pairs from NLI, STS, and paraphrase datasets |
| Size | ~80 MB |
| Speed | ~24ms per query on CPU |

### Why This Model?

It's the **best trade-off** between quality and speed for a CPU-only setup:

| Model | Dimensions | Quality (STS) | Speed (CPU) | Size |
|-------|:----------:|:-------------:|:-----------:|:----:|
| all-MiniLM-L6-v2 | 384 | 82.0 | 24ms | 80MB |
| all-mpnet-base-v2 | 768 | 83.4 | 65ms | 420MB |
| e5-large-v2 | 1024 | 85.2 | 180ms | 1.3GB |
| text-embedding-3-small (OpenAI) | 1536 | 86.1 | ~100ms* | API |

*\* API latency, not local compute*

MiniLM-L6-v2 is ~3x faster than mpnet and only 1.4 points lower in quality. For 18,500 chunks on CPU, this matters.

### Limitations

1. **256 token limit** — Text longer than ~200 words gets truncated. This is why chunking to 500 characters is important.
2. **English-centric** — Trained primarily on English. Chinese/German queries work but with lower accuracy.
3. **General-purpose** — Not fine-tuned for medical/technical domains. "FHIR" and "HL7" might not be as well-represented as "machine learning".
4. **No cross-lingual** — A Chinese query won't match an English document well (unlike multilingual models like `paraphrase-multilingual-MiniLM-L12-v2`).

---

## Qdrant: The Vector Database

### Why Qdrant?

| Feature | Qdrant | FAISS | ChromaDB | Pinecone |
|---------|:------:|:-----:|:--------:|:--------:|
| In-memory mode | Yes | Yes | Yes | No (cloud) |
| No server needed | Yes | Yes | Yes | No |
| Payload filtering | Yes | No | Yes | Yes |
| Python client | Yes | Yes | Yes | Yes |
| HNSW index | Yes | Yes | Yes | Yes |
| Production-ready | Yes | Partial | Partial | Yes |
| Free | Yes | Yes | Yes | No |

Qdrant was chosen because it supports **in-memory mode** (no Docker/server), has excellent **payload filtering** (search within specific dates/sources), and has a clean Python API.

### How HNSW Works (The Index)

Without an index, finding nearest neighbors requires comparing the query against **every** stored vector (brute force). With 18,500 vectors at 384 dimensions, that's 7.1 million float comparisons per query.

**HNSW (Hierarchical Navigable Small World)** builds a graph where similar vectors are connected:

```
Layer 2 (sparse):    A ─── D ─── G
                     │           │
Layer 1 (medium):    A ── B ── D ── F ── G
                     │    │    │    │    │
Layer 0 (dense):     A─B─C─D─E─F─G─H─I─J─K
```

Search starts at the top layer (few nodes, big jumps) and descends to the bottom layer (all nodes, precise). This reduces search from O(n) to O(log n).

**In Jarvis:** `agent.py` configures HNSW with `m=16` (connections per node) and `ef_construct=100` (build-time search width). `search_ui.py` uses Qdrant defaults.

### Payload Filtering

Qdrant can filter results by metadata **before** or **during** vector search:

```python
# "Find chunks about DICOM from the last week, only from wiki pages"
conditions = [
    FieldCondition(key="date", range=Range(gte="2026-04-03")),
    FieldCondition(key="item_type", match=MatchValue(value="wiki_page")),
]
```

This is much more efficient than searching all 18,500 vectors and then filtering.

---

## The Chunking Problem

### Why Chunk Size Matters

```
Too small (50 chars):
  "FHIR resources are"  ← Not enough context, embedding is vague

Too large (5000 chars):
  "Chapter 1: FHIR... (entire chapter)" ← Embedding averages out all topics,
                                            matches everything weakly

Sweet spot (300-500 chars):
  "FHIR resources are the fundamental unit of interoperability.
   Each resource represents a clinical or administrative concept
   like Patient, Observation, or MedicationRequest."
  ← Focused enough for a good embedding, long enough for context
```

### Jarvis's Chunking Strategies

| Content Type | Strategy | Max Size | Overlap |
|-------------|----------|:--------:|:-------:|
| Raw articles (MD) | Paragraph accumulation | 500 chars | 100 chars |
| PDF sections | Regex split on `\d+\.` | 1500 chars | 100 chars |
| Learning guides | Single blob | 2000 chars | 100 chars |
| Java code | Class/method structure | ~1000 chars | 100 chars |
| Wiki pages | Paragraph accumulation | 500 chars | 100 chars |
| Custom (PDF) | Page-based | ~2000 chars | 100 chars |

### How chunk overlap works in Jarvis

Jarvis **implements** a **100-character overlap** between consecutive chunks in all indexers. Each new chunk starts by repeating the last 100 characters of the previous chunk before adding fresh text. That **preserves context at boundaries** so a sentence or definition is less often split across chunks with no shared wording, and **reduces “mid-thought” cuts** where neither chunk alone would embed the full idea.

```
With 100-char overlap (Jarvis behavior):
  Chunk 1: "...FHIR resources are the fundamental unit of interoperability. Each resource"
  Chunk 2: "the fundamental unit of interoperability. Each resource represents a clinical..."
  ← Both chunks carry the bridging phrase; semantic search is more likely to surface the right passage.

Without overlap (hypothetical):
  Chunk 1: "...FHIR resources are the fundamental unit of"
  Chunk 2: "interoperability. Each resource represents..."
  ← The same idea straddles the cut; each chunk’s embedding is weaker for queries about the full phrase.
```

---

## Practical Examples from Jarvis

### Example 1: Search UI Query

```
User types: "How does P4M handle HL7 messages?"

1. Embed: model.encode("How does P4M handle HL7 messages?") → [0.12, -0.45, ...]

2. Qdrant search: Find top 10 vectors with cosine > 0.5
   Result 1: "P4M Next PACS connector processes HL7 ADT messages..." (score: 0.84)
   Result 2: "The HL7 interface in P4M receives patient demographics..." (score: 0.79)
   Result 3: "Message routing configuration for inbound HL7v2..." (score: 0.72)

3. Return results with scores to the user
```

### Example 2: Agent Auto-RAG

```
User types: "What did Jan work on last week?"

1. Detect entity: "Jan" → "Jan Loeffler" (team name alias)

2. Batch encode: ["What did Jan work on last week?", "Jan Loeffler"]

3. Multi-query search:
   a) General search with query embedding (top 5, score > 0.25)
   b) Author-filtered search: author="Jan Loeffler" with query embedding (top 5)
   c) Name search: embed "Jan Loeffler" with author filter (top 3)
   d) Wiki-type search: item_type="wiki_page" with query embedding (top 3)

4. Deduplicate by title, take top 5

5. Inject into LLM prompt:
   "Context from knowledge base:
    • [wiki_page] Jan Loeffler's Sprint 42 Update: Worked on DICOM viewer...
    • [wiki_page] Team Standup 2026-04-07: Jan presented the new routing...
    ..."

6. LLM generates answer grounded in these results
```

---

## Key Takeaways

| Concept | What It Means | Jarvis Implementation |
|---------|--------------|----------------------|
| Embedding | Text → 384 numbers representing meaning | `all-MiniLM-L6-v2` |
| Cosine similarity | Measures directional similarity (0-1) | Qdrant's distance metric |
| Vector database | Finds nearest neighbors fast | Qdrant in-memory |
| HNSW index | Graph-based approximate nearest neighbor | Qdrant's default index |
| Chunking | Breaking documents into embeddable pieces | Paragraph-based, 500 chars |
| Payload filtering | Narrow search by metadata | Date, source, type, author |

---

*Next: [Chapter 4 — RAG Framework Comparison](ch4-framework-comparison.md) — How does Jarvis compare to LangChain, LlamaIndex, and Haystack?*
