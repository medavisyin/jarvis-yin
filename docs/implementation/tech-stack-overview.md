# Jarvis Technology Stack Overview

Jarvis combines a daily briefing pipeline (fetch, merge, deduplicate, render) with a retrieval-augmented question-answering stack (embeddings, vector store, search UI, and agent). This document summarizes each technology in plain terms, why it is used, version or model details where they matter, and how it connects to scripts and data flow.

---

## Core Python libraries

### sentence-transformers (all-MiniLM-L6-v2)

**What it is:** A library that loads pretrained transformer models and turns text into dense vectors (embeddings) so semantically similar phrases land near each other in vector space.

**Why Jarvis uses it:** Indexers need a single, local embedding model for chunks of briefings, code, Confluence pages, and other sources so queries and documents can be compared without calling a remote embedding API.

**Version / model:** The `all-MiniLM-L6-v2` model produces **384-dimensional** vectors. It balances quality and speed for interactive search and batch indexing on typical developer hardware.

**Architecture role:** Used by the six indexer scripts that embed text and upsert into Qdrant. The same model (or a deployment-consistent companion) must be used at query time in `search_ui.py` and `agent.py` so query vectors match stored document vectors.

---

### qdrant-client

**What it is:** The official Python client for Qdrant, a vector database optimized for similarity search, filtering, and payload metadata alongside vectors.

**Why Jarvis uses it:** Jarvis stores millions of embedding vectors with metadata (source id, path, title) and needs fast approximate nearest-neighbor search for the Search UI and agent context retrieval.

**Version / model:** Use a `qdrant-client` version compatible with your Qdrant server or embedded mode. Pin versions in your environment to avoid API drift.

**Architecture role:** All RAG indexers write to Qdrant; `search_ui.py` runs searches without an LLM; `agent.py` runs searches then passes top chunks to the LLM. Persistence is **in-memory** with a JSON snapshot written to **`C:/reports/ai/.rag-store.json`** so the index can be reloaded between process restarts without rebuilding from scratch every time.

---

### Flask

**What it is:** A lightweight Python web framework for HTTP routes, templates, JSON APIs, and streaming responses.

**Why Jarvis uses it:** Jarvis exposes two local HTTP services: a search interface for human debugging and exploration, and an agent API that streams model output.

**Version / model:** Pin Flask (and Werkzeug) in `requirements` or lockfiles for reproducible deployments.

**Architecture role:** **`search_ui.py`** serves the Search UI on **port 18888**. **`agent.py`** serves the RAG-backed agent on **port 18889**, including server-sent events (SSE) for streamed answers.

---

### Ollama (qwen3.5:4b)

**What it is:** A local runtime that pulls and serves large language models via a simple HTTP API, without shipping your prompts to a third-party API by default.

**Why Jarvis uses it:** The agent needs natural-language answers grounded in retrieved context. Running a small local model keeps latency and data residency under your control for many workflows.

**Version / model:** Jarvis is configured to use **`qwen3.5:4b`** (or the project’s current pinned tag) through Ollama. Ensure the model is pulled (`ollama pull`) before starting the agent.

**Architecture role:** **`agent.py`** calls Ollama at **`http://localhost:11434`** (default Ollama HTTP API). The flow is: user query → automatic RAG search over Qdrant → inject retrieved text into the prompt → Ollama generates the reply → stream tokens to the client via SSE.

---

### DeepSeek API (`deepseek-v4-pro`, optional, stock only)

**What it is:** A hosted large-language-model API accessed via the **OpenAI SDK** (`from openai import OpenAI` with `base_url="https://api.deepseek.com"`). When enabled, Jarvis uses the **`deepseek-v4-pro`** model with **thinking enabled** (`reasoning_effort="high"`, `extra_body={"thinking": {"type": "enabled"}}`) for the **last mile** of certain stock flows.

**Why Jarvis uses it (optionally):** The stock module can delegate **final Chinese narrative synthesis** to a strong reasoning model while keeping **all feature computation** (technical, fundamental, XGBoost, fund-flow inputs, scanner filtering) **local**. This path is **not** used for RAG chat, agent SSE, or the daily briefing pipeline.

**Version / model:** The stock integration targets **`deepseek-v4-pro`** with chain-of-thought reasoning via the thinking API. The API key is set in the **Global Settings** UI and persisted in **`scripts/rag/.global_settings.json`**.

**Architecture role:** **`config.py`** exposes **`get_deepseek_key()`**, **`_get_deepseek_client()`**, and **`call_deepseek()`**; **`llm_reasoning.generate_prediction_deepseek()`** and the **AI 股票推荐** scanner (TOP 5 enrichment when `use_deepseek` is true) call into it. See [stock/llm-synthesis-impl.md](./stock/llm-synthesis-impl.md) and [stock/stock-prediction-impl.md](./stock/stock-prediction-impl.md).

---

### Playwright

**What it is:** A browser automation library that drives Chromium, Firefox, or WebKit in headless or headed mode, including modern JavaScript-heavy sites.

**Why Jarvis uses it:** Many news and dashboard pages do not return complete content as static HTML. Fetch scripts need a real browser context to render pages and extract the same content a user would see.

**Version / model:** Playwright versions are tied to browser binaries; run the framework’s install step so browsers match the library version.

**Architecture role:** All **`fetch-*.py`** scripts in the briefing pipeline use Playwright (directly or via shared helpers) to scrape sources. Output is structured data (often JSON on disk) consumed by merge and downstream steps.

---

### pypdf

**What it is:** A pure-Python library for reading PDF files and extracting text, metadata, and page boundaries.

**Why Jarvis uses it:** Briefing content sometimes arrives or is archived as PDF. Indexers need reliable text extraction to chunk and embed that content like any other document.

**Version / model:** Pin `pypdf` (or `pypdf2` lineage) to match your Python version and API expectations.

**Architecture role:** Used when indexing briefing PDFs (for example paths touched by **`index_briefing.py`** and related tooling) so RAG search includes previously generated reports.

---

### ReportLab

**What it is:** A Python library for programmatic PDF generation: pages, fonts, images, tables, and layouts.

**Why Jarvis uses it:** The briefing is rendered as a polished PDF from structured JSON rather than only as HTML or plain text.

**Version / model:** Pin ReportLab for stable font and layout behavior across machines.

**Architecture role:** **`scripts/output/briefing-template.py`** (and any shared layout helpers) build the final briefing PDF from merged briefing data.

---

### edge-tts

**What it is:** A Python interface to Microsoft Edge’s online text-to-speech voices, often used for high-quality neural voices without a local GPU TTS model.

**Why Jarvis uses it:** Jarvis can produce **Chinese** audio podcasts from briefing text with natural-sounding voices and manageable setup.

**Version / model:** Depends on network access to Edge TTS endpoints; voice names and availability follow Microsoft’s catalog.

**Architecture role:** Used in the **Daily Fetch** audio pipeline (segmented per-source/category narration in `agent.py`), standalone **`generate-audio.py`** for legacy use, and **Audio from Knowledge** for educational podcasts. Daily Fetch generates narration via the fast model (`qwen3:1.7b`), then converts to speech with Edge-TTS.

---

### moviepy and Pillow

**What they are:** **MoviePy** edits and composes video from clips, images, and audio timelines. **Pillow** is the de facto Python imaging library for opening, resizing, and saving raster images.

**Why Jarvis uses them:** Briefing output can include a **video** composed from slide-like frames plus narration or music.

**Version / model:** Pin both; MoviePy often depends on FFmpeg being installed on the system PATH.

**Architecture role:** Used in **video generation** alongside slide assets produced from the briefing pipeline (see output-generation documentation).

---

## Data flow (high level)

### Briefing pipeline: fetch → merge → PDF (and media)

1. **Fifteen `fetch-*.py` scripts** run (manually or orchestrated). Each uses Playwright (and sometimes simpler HTTP) to pull content from its source and write **JSON** files to a known layout.
2. **`scripts/pipeline/merge-sources.py`** (and related merge steps) combine those JSON payloads into a single canonical artifact such as **`briefing-data.json`**.
3. **`scripts/output/briefing-template.py`** reads that structure and produces the **PDF** via ReportLab. Optional stages add **edge-tts** audio and **moviepy**/**Pillow** video.

### RAG: index → Qdrant → snapshot

1. **Six indexer scripts** chunk source text, embed with **SentenceTransformer** (`all-MiniLM-L6-v2`, 384-dim vectors), and upsert vectors plus payloads into **Qdrant** held **in memory**.
2. The collection state is persisted to **`C:/reports/ai/.rag-store.json`** so restarts can reload the snapshot.

### Query paths

| Entry | Flow |
|--------|------|
| **`search_ui.py`** | User query → embed with the same embedding stack → **Qdrant search** → return ranked results. **No LLM** is required for this path. |
| **`agent.py`** | User query → **automatic RAG search** (Qdrant) → inject retrieved chunks into the prompt → **Ollama** (`qwen3.5:4b` at `localhost:11434`) → **SSE** stream of the answer to the client. **(RAG does not use DeepSeek;** optional **DeepSeek API (deepseek-v4-pro with thinking) for stock analysis via Global Settings** is stock-only.) |

---

## Quick reference map

| Technology | Primary scripts / artifacts |
|------------|----------------------------|
| sentence-transformers | Indexers, `search_ui.py`, `agent.py` |
| qdrant-client | Indexers, `search_ui.py`, `agent.py`; snapshot `.rag-store.json` |
| Flask | `search_ui.py` (:18888), `agent.py` (:18889) |
| Ollama | `agent.py` → `localhost:11434` |
| DeepSeek (optional) | `scripts/stock/config.py` `call_deepseek` / `get_deepseek_key`; stock synthesis & scanner TOP 5 only |
| Playwright | All `fetch-*.py` |
| pypdf | Briefing PDF indexing |
| ReportLab | `briefing-template.py` → PDF |
| edge-tts | Chinese/English audio podcast generation (Daily Fetch segmented audio, standalone pipeline, agent "Audio from Knowledge") |
| moviepy, Pillow | Video from slides / assets |
| xgboost | `model_xgboost.py` (3-class classifier), `model_price_predictor.py` (price regressors) |
| akshare | `fetch_market_data.py`, `hot_sectors.py`, `fundamental_analysis.py` — A-share data |
| feedparser | `fetch-china-news.py` (People's Daily RSS), `run-world-news.py` (RSS parsing) |
| pandas-ta | `technical_analysis.py` — MACD, RSI, KDJ, Bollinger Bands, ATR |

For step-by-step implementation detail per file, see [README.md](./README.md) in this folder.
