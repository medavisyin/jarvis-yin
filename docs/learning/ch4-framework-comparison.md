# Chapter 4: RAG Framework Comparison — Jarvis vs. The Ecosystem

> How does a hand-built RAG system compare to popular frameworks?
> What are the trade-offs of building from scratch vs. using a framework?

---

## The Major RAG Frameworks (2025-2026)

| Framework | Language | Stars | Philosophy | Best For |
|-----------|:--------:|:-----:|-----------|----------|
| **LangChain** | Python/JS | 100k+ | "Swiss army knife" — everything included | Prototyping, wide integrations |
| **LlamaIndex** | Python | 40k+ | "Data framework" — focus on indexing & retrieval | Complex data pipelines |
| **Haystack** | Python | 18k+ | "Production pipelines" — modular, typed | Enterprise deployments |
| **Jarvis** | Python | Custom | "Hand-built" — minimal dependencies, full control | Single-user, offline, specific needs |

---

## Feature Comparison

### Retrieval Capabilities

| Feature | LangChain | LlamaIndex | Haystack | **Jarvis** |
|---------|:---------:|:----------:|:--------:|:----------:|
| Dense vector search | Yes | Yes | Yes | **Yes** |
| BM25 keyword search | Yes | Yes | Yes | **Yes** (rank-bm25) |
| Hybrid search (vector+BM25) | Yes | Yes | Yes | **Yes** (RRF fusion) |
| Cross-encoder re-ranking | Yes | Yes | Yes | **Yes** (ms-marco-MiniLM) |
| Query rewriting | Yes | Yes | Yes | **Yes** (Ollama qwen3:1.7b) |
| Multi-query retrieval | Yes | Yes | Yes | **Partial** (entity-aware) |
| Metadata filtering | Yes | Yes | Yes | **Yes** |
| Knowledge graph retrieval | Yes | Yes | Plugin | No |
| Recursive retrieval | Yes | Yes | Yes | No |
| Parent-child chunk linking | Yes | Yes | Yes | No |

### Indexing & Data

| Feature | LangChain | LlamaIndex | Haystack | **Jarvis** |
|---------|:---------:|:----------:|:--------:|:----------:|
| PDF ingestion | Yes | Yes | Yes | **Yes** |
| Code ingestion | Plugin | Yes | Plugin | **Yes** (Java-specific) |
| Web scraping | Plugin | Yes | Plugin | **Yes** (15 custom scrapers) |
| Wiki/Confluence | Plugin | Plugin | Plugin | **Yes** (native) |
| Incremental indexing | Manual | Yes | Manual | **Yes** (manifest-based) |
| Chunk overlap | Yes | Yes | Yes | No |
| Semantic chunking | Yes | Yes | Yes | No |
| Custom metadata | Yes | Yes | Yes | **Yes** |

### Agent & LLM

| Feature | LangChain | LlamaIndex | Haystack | **Jarvis** |
|---------|:---------:|:----------:|:--------:|:----------:|
| Tool calling | Yes | Yes | Yes | **Yes** |
| Streaming (SSE) | Yes | Yes | Yes | **Yes** |
| Multi-model support | Yes | Yes | Yes | **Yes** (Ollama) |
| Session memory | Yes | Yes | Plugin | **Yes** |
| Auto-RAG injection | Manual | Yes | Manual | **Yes** (always-on) |
| Vision/multimodal | Yes | Yes | Yes | **Yes** |
| OpenAI/Anthropic API | Yes | Yes | Yes | No (local only) |
| Local LLM (Ollama) | Yes | Yes | Yes | **Yes** |

### Operations

| Feature | LangChain | LlamaIndex | Haystack | **Jarvis** |
|---------|:---------:|:----------:|:--------:|:----------:|
| Web UI included | No | No | No | **Yes** (2 UIs!) |
| No external DB needed | Partial | Partial | No | **Yes** |
| Works fully offline | Partial | Partial | No | **Yes** |
| Zero-config startup | No | No | No | **Yes** |
| Monitoring/tracing | LangSmith | Plugin | Plugin | No |
| Evaluation framework | LangSmith | Yes | Yes | No |

---

## Architecture Comparison

### LangChain Approach
```python
from langchain.chains import RetrievalQA
from langchain.vectorstores import Qdrant
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.llms import Ollama

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
vectorstore = Qdrant.from_documents(docs, embeddings)
retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
qa = RetrievalQA.from_chain_type(llm=Ollama(model="qwen3.5:4b"), retriever=retriever)
answer = qa.run("How does P4M handle DICOM?")
```

**Pros:** 5 lines of code, huge ecosystem, easy to swap components.
**Cons:** Heavy abstraction, hard to debug, dependency bloat (~200 packages), frequent breaking changes.

### LlamaIndex Approach
```python
from llama_index import VectorStoreIndex, SimpleDirectoryReader
from llama_index.vector_stores import QdrantVectorStore

documents = SimpleDirectoryReader("./data").load_data()
index = VectorStoreIndex.from_documents(documents)
query_engine = index.as_query_engine()
response = query_engine.query("How does P4M handle DICOM?")
```

**Pros:** Even simpler for basic use, excellent data connectors, built-in evaluation.
**Cons:** Opinionated about data flow, less flexible for custom pipelines, still heavy dependencies.

### Haystack Approach
```python
from haystack import Pipeline
from haystack.components.retrievers import QdrantEmbeddingRetriever
from haystack.components.generators import OllamaGenerator

pipeline = Pipeline()
pipeline.add_component("retriever", QdrantEmbeddingRetriever(...))
pipeline.add_component("generator", OllamaGenerator(model="qwen3.5:4b"))
pipeline.connect("retriever", "generator")
result = pipeline.run({"retriever": {"query": "How does P4M handle DICOM?"}})
```

**Pros:** Typed pipeline, production-focused, clear component boundaries.
**Cons:** More boilerplate, smaller ecosystem than LangChain.

### Jarvis Approach
```python
# Direct Qdrant + SentenceTransformers + Ollama — no framework
embedding = model.encode(query).tolist()
results = client.query_points(collection_name="ai_briefings", query=embedding, limit=5)
context = "\n".join([r.payload["text"] for r in results.points])
response = ollama.chat(model="qwen3.5:4b", messages=[
    {"role": "system", "content": f"Use this context:\n{context}"},
    {"role": "user", "content": query}
])
```

**Pros:** Full control, minimal dependencies, no abstraction layers, easy to debug, works offline.
**Cons:** Must implement everything yourself, no built-in evaluation, no community plugins.

---

## The Trade-Off Matrix

### When to Use a Framework

| Situation | Recommendation |
|-----------|---------------|
| Rapid prototyping | LangChain or LlamaIndex |
| Enterprise production with team | Haystack |
| Complex data pipelines (many sources) | LlamaIndex |
| Need evaluation/monitoring | LangChain + LangSmith |
| Cloud-first deployment | Any framework + managed vector DB |

### When to Build Custom (Like Jarvis)

| Situation | Recommendation |
|-----------|---------------|
| Single developer, specific needs | Custom |
| Must work fully offline | Custom |
| Need full control over every step | Custom |
| Minimal dependencies required | Custom |
| Learning how RAG works internally | Custom |
| Integrating with niche tools (Jira, git, Confluence) | Custom (or framework + custom tools) |

---

## What Jarvis Could Borrow from Frameworks

### From LangChain: Evaluation
LangChain's evaluation tools (faithfulness, answer relevance, context precision) would help measure if Jarvis's retrieval is actually good.

### From LlamaIndex: Semantic Chunking
LlamaIndex's `SemanticSplitterNodeParser` uses the embedding model itself to decide where to split text — chunks that are semantically coherent rather than arbitrarily cut at paragraph boundaries.

### From Haystack: Pipeline Architecture
Haystack's typed pipeline pattern would make it easier to swap components (e.g., replace MiniLM with a better model, or add a re-ranker step) without rewriting the whole system.

### From All: Hybrid Search
All three frameworks make it trivial to add BM25 alongside vector search. Jarvis now implements hybrid BM25+vector search with Reciprocal Rank Fusion, cross-encoder re-ranking, and LLM-based query rewriting.

---

## Dependency Comparison

| | LangChain | LlamaIndex | Haystack | **Jarvis** |
|-|:---------:|:----------:|:--------:|:----------:|
| Core packages | ~50 | ~40 | ~30 | **6** |
| Total (with extras) | ~200 | ~150 | ~80 | **~15** |
| Install size | ~2 GB | ~1.5 GB | ~800 MB | **~300 MB** |
| Startup time | 5-10s | 3-8s | 2-5s | **6s** (model load) |
| Breaking changes/year | High | Medium | Low | **None** (you control it) |

Jarvis's minimal dependency footprint is a genuine advantage for a single-user system that needs to "just work" without version conflicts.

---

## Summary

> **Jarvis is not trying to compete with frameworks.** It's a purpose-built system for a specific
> use case: a single developer's personal knowledge management + AI briefing pipeline.
>
> Frameworks excel at flexibility and ecosystem. Jarvis excels at simplicity, offline operation,
> and deep integration with specific tools (Jira, git, Confluence, 15 custom scrapers).
>
> The smartest path forward isn't "rewrite Jarvis in LangChain" — it's **selectively borrowing
> the best ideas** (hybrid search, re-ranking, semantic chunking, evaluation) while keeping
> the lightweight, zero-infrastructure architecture.

---

*Next: [Chapter 5 — ML & Future Roadmap](ch5-ml-roadmap.md) — How to evolve Jarvis with machine learning*
