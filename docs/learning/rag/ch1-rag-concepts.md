# Chapter 1: RAG Concepts — What It Is and How Jarvis Uses It

> This chapter teaches the fundamental concepts behind Retrieval-Augmented Generation,
> then maps each concept to how Jarvis implements it.

---

## What Problem Does RAG Solve?

Large Language Models (LLMs) like GPT, Qwen, or Llama are trained on public internet data up to a cutoff date. They have two critical limitations:

1. **Knowledge cutoff** — They don't know about events after their training date
2. **Hallucination** — When they don't know something, they confidently make things up

RAG solves both problems by **giving the LLM your own data as context** before it answers.

```
WITHOUT RAG:
  User: "What did our team discuss in last week's Confluence page?"
  LLM:  "I don't have access to your Confluence." (or worse, makes something up)

WITH RAG:
  User: "What did our team discuss in last week's Confluence page?"
  System: [searches your indexed Confluence pages, finds the relevant one]
  LLM:  "Based on the page from April 3rd, your team discussed..." (grounded answer)
```

---

## The RAG Pipeline (3 Stages)

Every RAG system has three stages:

### Stage 1: Indexing (Offline — done ahead of time)

Convert your documents into a searchable format:

```
Documents (PDF, MD, code, wiki)
    │
    ▼
Chunking ─── Break into small pieces (300-500 chars each)
    │
    ▼
Embedding ── Convert each chunk into a 384-dimensional number array
    │         (using a neural network called SentenceTransformer)
    ▼
Storage ──── Store vectors + metadata in a vector database (Qdrant)
```

**In Jarvis:** This is done by the 6 indexer scripts (`index_briefing.py`, `index_codebase.py`, etc.). They run offline and save everything to `.rag-store.json`.

### Stage 2: Retrieval (Online — at query time)

Find the most relevant chunks for the user's question:

```
User Question: "How does P4M handle DICOM routing?"
    │
    ▼
Embed the question ── Same neural network, same 384 dimensions
    │
    ▼
Vector Search ─────── Find chunks whose vectors are closest
    │                  (cosine similarity)
    ▼
Top 5 Results ─────── The most semantically similar chunks
```

**In Jarvis:** `search_ui.py` does pure vector search. `agent.py` does "auto-RAG" — it automatically searches before every chat message.

### Stage 3: Generation (Online — LLM answers with context)

Feed the retrieved chunks to the LLM as context:

```
System Prompt: "You are Jarvis, an AI assistant. Use the following context..."
Context:       [5 relevant chunks from the vector search]
User Question: "How does P4M handle DICOM routing?"
    │
    ▼
LLM generates answer grounded in your actual documents
```

**In Jarvis:** `agent.py` sends the auto-RAG results + user question to Ollama (local LLM). The Search UI (`search_ui.py`) skips this stage entirely — it just shows you the raw search results.

---

## Key Concepts Explained

### What Is an Embedding?

An embedding is a **list of numbers** (a vector) that represents the *meaning* of text. Similar meanings produce similar numbers.

```
"machine learning"     → [0.12, -0.45, 0.78, ..., 0.33]   (384 numbers)
"artificial intelligence" → [0.11, -0.43, 0.76, ..., 0.31]   (very similar!)
"banana smoothie"      → [-0.67, 0.22, -0.11, ..., 0.89]   (very different)
```

The model `all-MiniLM-L6-v2` was trained on millions of text pairs to learn that "machine learning" and "artificial intelligence" should have similar vectors, while "banana smoothie" should be far away.

**In Jarvis:** Every chunk gets embedded once during indexing. Every query gets embedded at search time. Then we compare.

### What Is Cosine Similarity?

It measures the angle between two vectors. Score ranges from -1 to 1:
- **1.0** = identical meaning
- **0.7+** = very relevant
- **0.5** = somewhat related
- **0.0** = unrelated

```
cos("DICOM routing in P4M", "P4M PACS connector forwards studies") = 0.82  ← relevant!
cos("DICOM routing in P4M", "JavaScript React component")          = 0.15  ← not relevant
```

**In Jarvis:** The default `min_score` threshold is 0.5 in the Search UI and 0.25 in the agent (lower because auto-RAG casts a wider net).

### What Is Chunking?

Documents are too long to embed as a whole (embeddings work best on 100-500 character pieces). Chunking splits them:

```
Original document (5000 chars):
  "Chapter 1: Introduction to FHIR...
   Section 1.1: Resources...
   Section 1.2: REST API..."

After chunking (500 chars each):
  Chunk 0: "Chapter 1: Introduction to FHIR. FHIR (Fast Healthcare..."
  Chunk 1: "Section 1.1: Resources. A Resource is the fundamental..."
  Chunk 2: "Section 1.2: REST API. FHIR uses standard HTTP..."
```

**In Jarvis:** `_chunk_text()` splits on paragraph boundaries (`\n\n`) with a 500-character cap. PDF sections are split on numbered headings. Java code is split by class/method structure.

### What Is a Vector Database?

A specialized database optimized for finding "nearest neighbors" in high-dimensional space. Instead of SQL `WHERE` clauses, you ask: "find me the 5 vectors closest to this query vector."

**In Jarvis:** Qdrant runs **in-memory** (no separate server needed). On startup, it loads all 18,500+ vectors from `.rag-store.json`. Search takes ~35ms across all vectors.

---

## How Jarvis's Two Servers Use RAG Differently

### Search UI (Port 18888) — "Show me what you found"

```
User types query
    → Embed query
    → Qdrant vector search (with optional filters)
    → Return raw results with scores
    → User reads the chunks directly
```

This is **retrieval only**. No LLM, no generation. Fast and transparent — you see exactly what the system found and can judge relevance yourself.

### Agent (Port 18889) — "Answer my question using what you found"

```
User types query
    → [Auto] Embed query + entity names
    → [Auto] Qdrant vector search (multiple filtered queries)
    → [Auto] Check if git/Jira tools needed (keyword matching)
    → Inject top 5 results as context into LLM prompt
    → Stream LLM response token by token (SSE)
    → If LLM calls a tool → execute → loop back
    → Final answer with source citations
```

This is **full RAG** — retrieval + generation. Slower (LLM inference takes 15-30s on CPU) but gives you a synthesized answer.

---

## The Indexing Lifecycle

```
                    ┌──────────────────┐
                    │  Source Content   │
                    │  (PDF, MD, Java,  │
                    │   Wiki, Custom)   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Indexer Script   │
                    │  (one per source) │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         Extract        Chunk Text     Parse Metadata
         Content        (500 chars)    (date, source,
         from file                      type, author)
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼─────────┐
                    │  SentenceTransformer │
                    │  all-MiniLM-L6-v2    │
                    │  text → 384-dim vector│
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Qdrant Upsert   │
                    │  (in-memory)     │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Save Snapshot   │
                    │  .rag-store.json │
                    └──────────────────┘
```

Each chunk becomes a **point** in Qdrant with:
- **Vector:** 384 floats (the embedding)
- **Payload:** title, text, date, source, item_type, filename, url, difficulty, etc.

---

## Summary: RAG in One Sentence

> RAG = "Before asking the AI, search your own documents for relevant context, then give that context to the AI so it can answer based on facts instead of guessing."

Jarvis implements this with:
- **SentenceTransformer** for understanding meaning (embeddings)
- **Qdrant** for fast similarity search (vector database)
- **Ollama** for generating answers (local LLM)
- **Flask** for the web interface (two servers)
- **JSON snapshot** for persistence (no external database server needed)

---

*Next: [Chapter 2 — Architecture Assessment](ch2-architecture-assessment.md) — Where does Jarvis sit on the RAG maturity scale?*
