# Getting Started: Build Jarvis from Zero

A complete beginner's guide. By the end you will have a working Jarvis system that collects AI news, generates PDF reports and Chinese audio podcasts, and lets you chat with an AI assistant backed by your own local knowledge base.

**Time required:** ~45 minutes (mostly waiting for downloads).

---

## Table of Contents

1. [What Is Jarvis?](#1-what-is-jarvis)
2. [What You Will Build](#2-what-you-will-build)
3. [Prerequisites Overview](#3-prerequisites-overview)
4. [Step 1 — Install Python](#step-1--install-python)
5. [Step 2 — Get the Jarvis Code](#step-2--get-the-jarvis-code)
6. [Step 3 — Install Python Packages](#step-3--install-python-packages)
7. [Step 4 — Install Playwright & Chromium](#step-4--install-playwright--chromium)
8. [Step 5 — Install Ollama & Download a Model](#step-5--install-ollama--download-a-model)
9. [Step 6 — Create the Reports Folder](#step-6--create-the-reports-folder)
10. [Step 7 — Run the Briefing Pipeline](#step-7--run-the-briefing-pipeline)
11. [Step 8 — Start the Search UI](#step-8--start-the-search-ui)
12. [Step 9 — Start the Jarvis Agent](#step-9--start-the-jarvis-agent)
13. [Step 10 — One-Click Start (Optional)](#step-10--one-click-start-optional)
14. [Verify Everything Works](#verify-everything-works)
15. [Add Your Own Knowledge](#add-your-own-knowledge)
16. [Daily Workflow](#daily-workflow)
17. [Troubleshooting](#troubleshooting)
18. [Glossary](#glossary)
19. [What's Next?](#whats-next)

---

## 1. What Is Jarvis?

Jarvis is a personal AI assistant that runs entirely on your own computer. It has three main parts:

| Part | What It Does |
|------|-------------|
| **Briefing Pipeline** | Scrapes 10 AI news sources and 6 world/Chinese news agencies every day, then produces a PDF report, world news audio, Chinese news audio, and AI briefing audio |
| **Search UI** | A web page where you can search through everything Jarvis has collected — no AI model needed |
| **Chat Agent** | An AI chatbot that answers your questions using your local knowledge base, with access to tools like Jira, git, and Confluence |

All data stays on your machine. No cloud APIs, no subscriptions, no data leaving your network.

---

## 2. What You Will Build

```
┌──────────────────────────────────────────────────────────────┐
│                        YOUR MACHINE                          │
│                                                              │
│  News Sources ──→ Briefing Pipeline ──→ PDF + Audio          │
│  (10 AI + 6 news)   (Playwright)        (C:/reports/ai/)     │
│                          │                                   │
│                          ▼                                   │
│                    RAG Knowledge Base                         │
│                    (18,000+ chunks)                           │
│                          │                                   │
│              ┌───────────┴───────────┐                       │
│              ▼                       ▼                       │
│     Search UI (:18888)      Chat Agent (:18889)              │
│     (browse & search)       (AI answers + tools)             │
│              │                       │                       │
│              └───────────┬───────────┘                       │
│                          ▼                                   │
│                     Ollama LLM                               │
│                   (runs locally)                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Prerequisites Overview

| Requirement | Why | Install Time |
|-------------|-----|:------------:|
| **Python 3.10+** | Jarvis is written in Python | ~5 min |
| **pip packages** | Libraries for scraping, embeddings, PDF, audio, etc. | ~5 min |
| **Playwright + Chromium** | Headless browser that scrapes websites | ~3 min |
| **Ollama** | Runs AI language models locally on your CPU/GPU | ~5 min |
| **An Ollama model** | The actual AI brain (default: `qwen3.5:4b`) | ~10 min |
| **~5 GB disk space** | For models, packages, and reports | — |

**Operating system:** This guide is written for **Windows 10/11**. The Python scripts work on macOS/Linux too, but the `.bat` launchers are Windows-only.

---

## Step 1 — Install Python

If you already have Python 3.10 or newer, skip to [Step 2](#step-2--get-the-jarvis-code).

### Option A: Download from python.org (recommended)

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Click the big yellow **"Download Python 3.x.x"** button
3. Run the installer
4. **Important:** Check the box that says **"Add Python to PATH"** at the bottom of the first screen
5. Click **Install Now**

### Option B: Microsoft Store

1. Open the Microsoft Store
2. Search for "Python 3"
3. Click **Get** on the latest version

### Verify

Open a new terminal (press `Win + R`, type `cmd`, press Enter) and run:

```
python --version
```

You should see something like `Python 3.12.4`. If you see an error, close and reopen the terminal — the PATH update needs a fresh window.

> **What is Python?** Python is a programming language. Jarvis is written in it. Think of it as the engine that runs all the scripts.

---

## Step 2 — Get the Jarvis Code

If you already have the code at `C:\jarvis`, skip to [Step 3](#step-3--install-python-packages).

### Option A: Clone with git

If you have git installed:

```
git clone <your-repo-url> C:\jarvis
```

### Option B: Download and extract

1. Download the project as a ZIP file
2. Extract it to `C:\jarvis`

The folder should look like this:

```
C:\jarvis\
├── README.md
├── bin\
├── docs\
├── references\
└── scripts\
```

---

## Step 3 — Install Python Packages

Open a terminal and run this single command to install everything Jarvis needs:

```
pip install flask qdrant-client sentence-transformers pypdf reportlab edge-tts playwright requests pyyaml feedparser ollama rank-bm25
```

**What each package does:**

| Package | Purpose |
|---------|---------|
| `flask` | Runs the two web servers (Search UI and Chat Agent) |
| `qdrant-client` | The vector database that stores and searches your knowledge |
| `sentence-transformers` | Turns text into numbers (embeddings) so the computer can compare meanings |
| `pypdf` | Reads text from PDF files |
| `reportlab` | Creates the daily briefing PDF |
| `edge-tts` | Converts text to spoken Chinese audio (text-to-speech for Daily Fetch podcasts and Audio from Knowledge) |
| `playwright` | Controls a headless browser to scrape websites |
| `requests` | Makes HTTP requests (used for Confluence/Jira APIs) |
| `pyyaml` | Reads YAML configuration in Markdown files |
| `feedparser` | Parses RSS news feeds (BBC, AP News, etc.) |
| `ollama` | Python client that talks to the Ollama AI model server |
| `rank-bm25` | Keyword search engine used alongside vector search |

> **What is pip?** `pip` is Python's package installer. It downloads libraries from the internet and installs them so your Python scripts can use them.

---

## Step 4 — Install Playwright & Chromium

Playwright needs a real browser engine to scrape websites. Run:

```
playwright install chromium
```

This downloads a standalone Chromium browser (~150 MB). It does not affect your regular Chrome/Edge browser.

> **What is Playwright?** Playwright is a tool that controls a web browser programmatically. Jarvis uses it to visit news websites, wait for pages to load, and extract article text — just like you would do manually, but automated.

> **What is Chromium?** Chromium is the open-source browser that Chrome and Edge are built on. Playwright uses its own copy so it does not interfere with your daily browser.

---

## Step 5 — Install Ollama & Download a Model

Ollama is what runs the AI language model on your computer. The Chat Agent needs it to generate answers.

### 5a. Install Ollama

1. Go to [ollama.com/download](https://ollama.com/download)
2. Click **Download for Windows**
3. Run the installer — it installs and starts Ollama as a background service

### 5b. Verify Ollama is running

Open a terminal and run:

```
ollama list
```

If Ollama is running, you will see an empty table (no models yet) or a list of models. If you get an error, Ollama may not have started — try running `ollama serve` in a separate terminal.

### 5c. Download the default model

Jarvis uses `qwen3.5:4b` by default — a 4-billion parameter model that runs well on CPU:

```
ollama pull qwen3.5:4b
```

This downloads ~2.5 GB. Wait for it to finish.

### 5d. (Optional) Download the vision model

If you want Jarvis to analyze images you upload in chat:

```
ollama pull qwen3-vl:8b
```

This is a larger model (~5 GB) and slower on CPU. Skip it if you just want text chat.

### 5e. Verify the model works

```
ollama run qwen3.5:4b "Hello, are you working?"
```

You should see the model respond with text. Press `Ctrl+D` or type `/bye` to exit.

> **What is Ollama?** Ollama is a program that downloads and runs large language models (LLMs) on your own computer. Instead of sending your questions to ChatGPT's servers, Ollama runs a smaller model right on your machine. It is slower but completely private.

> **What is qwen3.5:4b?** It is a language model made by Alibaba's Qwen team. The "4b" means 4 billion parameters — the "neurons" of the AI. Larger models are smarter but slower. 4B is a good balance for CPU-only machines.

---

## Step 6 — Create the Reports Folder

Jarvis stores all its output (PDFs, audio, knowledge base) in `C:\reports\ai`. Create it:

```
mkdir C:\reports\ai
```

You can use a different location by setting an environment variable:

```
set JARVIS_REPORTS_ROOT=D:\my-reports
```

But for this guide we will use the default `C:\reports\ai`.

---

## Step 7 — Run the Briefing Pipeline

Now let's collect some data. The briefing pipeline scrapes 10 AI news sources in parallel (9 by the pipeline, 1 manual-only).

### 7a. Run the preflight check

This tests whether your network can reach the news sources:

```
cd C:\jarvis
python scripts/pipeline/preflight-check.py
```

You will see a list of sources with "OK" or "FAIL" next to each. If most sources fail, you are likely behind a corporate firewall and need a proxy (see [Troubleshooting](#troubleshooting)).

### 7b. Run the AI briefing pipeline

```
python scripts/pipeline/run-all-sources.py
```

**On a corporate network?** Add a proxy:

```
python scripts/pipeline/run-all-sources.py --proxy socks5://localhost:10808
```

This takes 20–30 seconds. It will:
1. Check which sources are reachable
2. Scrape all reachable sources in parallel
3. Merge the results into one JSON file
4. Deduplicate topics
5. Index the content into the RAG knowledge base

### 7c. (Optional) Run the world news pipeline

```
python scripts/pipeline/run-world-news.py
```

This scrapes BBC, Reuters, AP News, Deutsche Welle, and The Guardian.

### What you should see

After the pipeline finishes, check the output:

```
dir C:\reports\ai
```

You should see a date folder like `2026-04-13\` containing JSON data files. The PDF and audio are generated later by the AI agent during synthesis.

> **What is web scraping?** It means using a program to visit websites and extract information automatically. Instead of you reading 9 websites every morning, Jarvis reads them all in 20 seconds.

> **What is RAG?** RAG stands for Retrieval-Augmented Generation. It means: when you ask the AI a question, it first *retrieves* relevant documents from the knowledge base, then *generates* an answer using those documents as context. This way the AI answers based on real data, not just its training.

---

## Step 8 — Start the Search UI

The Search UI lets you browse and search everything Jarvis has collected — no AI model needed.

```
python scripts/rag/search_ui.py
```

Open your browser and go to: **http://localhost:18888**

You should see a search page. Try searching for any AI topic. The **Library** tab shows all indexed documents. The **Chunk Analysis** tab shows statistics about your knowledge base.

> **What is a "chunk"?** Jarvis breaks long documents into smaller pieces called chunks (typically a few paragraphs each). This is because AI models work better with focused, relevant snippets than with entire documents.

> **What is port 18888?** A port is like a door number on your computer. When you run the Search UI, it opens door 18888 and listens for browser connections there. That is why the URL has `:18888` at the end.

---

## Step 9 — Start the Jarvis Agent

Open a **second terminal** (keep the Search UI running in the first one) and run:

```
python scripts/rag/agent.py
```

Open your browser and go to: **http://localhost:18889**

You should see a chat interface. Try asking something like:

- "What's new in AI today?"
- "Explain what RAG is"
- "Summarize the latest news"

The agent will automatically search the knowledge base for relevant context and generate an answer using the Ollama model.

**First-time startup is slower** (~15–30 seconds) because it loads the embedding model (~80 MB download on first use) and the Qdrant knowledge base into memory.

> **What is the difference between the Search UI and the Agent?**
> - **Search UI** (port 18888): Fast, simple search. Shows you raw chunks from the knowledge base. No AI generation. Works without Ollama.
> - **Agent** (port 18889): Full AI chatbot. Searches the knowledge base, then uses the LLM to write a human-readable answer. Needs Ollama running.

---

## Step 10 — One-Click Start (Optional)

Instead of opening two terminals every time, use the batch launchers in the `bin\` folder:

| Launcher | What It Does |
|----------|-------------|
| `bin\jarvis-start.bat` | Starts both servers (Search UI + Agent) in minimized windows |
| `bin\jarvis-stop.bat` | Stops both servers |
| `bin\jarvis-restart.bat` | Restarts both servers |
| `bin\jarvis-servers.bat` | Interactive menu: start, stop, restart, check status |

Double-click `bin\jarvis-start.bat` from File Explorer. Wait ~15 seconds, then open:
- http://localhost:18888 (Search UI)
- http://localhost:18889 (Chat Agent)

---

## Verify Everything Works

Run through this checklist:

| # | Check | How | Expected |
|:-:|-------|-----|----------|
| 1 | Python installed | `python --version` | `Python 3.10+` |
| 2 | Packages installed | `python -c "import flask, qdrant_client, sentence_transformers"` | No error |
| 3 | Playwright ready | `python -c "from playwright.sync_api import sync_playwright"` | No error |
| 4 | Ollama running | `ollama list` | Shows `qwen3.5:4b` |
| 5 | Reports folder exists | `dir C:\reports\ai` | Folder exists |
| 6 | Search UI responds | Open http://localhost:18888 | Search page loads |
| 7 | Agent responds | Open http://localhost:18889 | Chat page loads |
| 8 | Agent can answer | Ask "hello" in the chat | Gets a response |

---

## Add Your Own Knowledge

Jarvis can index your own documents. Place files in subfolders under `C:\reports\ai\knowledge\`:

```
C:\reports\ai\knowledge\
├── books\       ← Book chapters (PDF or Markdown)
├── projects\    ← Project documentation
├── notes\       ← Personal learning notes
└── tasks\       ← Task descriptions
```

Then index them:

```
python scripts/rag/index_custom.py scan
```

Your documents are now searchable in both the Search UI and the Chat Agent.

**Supported formats:** `.md`, `.txt`, `.pdf`

You can add optional metadata to Markdown files with YAML frontmatter:

```yaml
---
title: My Notes on Transformers
tags: [ai, deep-learning]
difficulty: beginner
---

Your content here...
```

---

## Daily Workflow

Once everything is set up, your daily routine is simple:

### Morning

1. **Start the servers** — double-click `bin\jarvis-start.bat`
2. **Run the briefing pipeline** — `python scripts/pipeline/run-all-sources.py`
3. **Open the Agent** — http://localhost:18889 and ask "daily briefing" to trigger synthesis

### Anytime

- **Search your knowledge** — http://localhost:18888
- **Ask the AI** — http://localhost:18889
- **Add documents** — drop files in `C:\reports\ai\knowledge\` and run `python scripts/rag/index_custom.py scan`

### Periodic Maintenance

```
python scripts/rag/reindex_all.py
```

This incrementally re-indexes all sources (briefings, codebase, Confluence). Only changed content is re-processed.

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| `python` not found | Python not in PATH | Reinstall Python and check "Add to PATH", or restart your terminal |
| `pip install` fails | No internet or corporate firewall | Try `pip install --proxy http://proxy:port <package>` |
| Preflight check: all sources FAIL | Firewall blocking websites | Use `--proxy socks5://localhost:10808` (set up a SOCKS proxy first) |
| `ollama list` errors | Ollama not installed or not running | Install from ollama.com, then run `ollama serve` |
| `ollama pull` is slow | Large download (~2.5 GB) | Wait — it only downloads once |
| Agent page loads but no response | Ollama not running or model not pulled | Run `ollama serve` in one terminal, then `ollama pull qwen3.5:4b` |
| Port 18888/18889 already in use | Previous server still running | Run `bin\jarvis-stop.bat` first, or `netstat -ano \| findstr :18888` to find and kill the process |
| Search returns no results | No data indexed yet | Run the briefing pipeline first (Step 7), or add your own documents |
| "No module named X" | Package not installed | Run the `pip install` command from Step 3 again |
| Edge-TTS "no audio" error | Temporary network issue | Retry — the script has built-in 3x retry logic |
| PDF generation fails | `reportlab` not installed | `pip install reportlab` |
| Embedding model download slow | First-time ~80 MB download | Wait — it is cached after the first use |

---

## Glossary

New to AI and programming? Here are the key terms used throughout this guide:

| Term | Meaning |
|------|---------|
| **Python** | A programming language. Jarvis is written in it. |
| **pip** | Python's package installer. Downloads and installs libraries. |
| **Terminal / Command Prompt** | The text-based interface where you type commands. On Windows: `cmd` or PowerShell. |
| **Playwright** | A tool that controls a web browser programmatically for scraping. |
| **Chromium** | The open-source browser engine used by Chrome and Edge. Playwright uses its own copy. |
| **Ollama** | A program that runs AI language models locally on your computer. |
| **LLM (Large Language Model)** | An AI model trained on text that can understand and generate language. Examples: GPT-4, Qwen, Llama. |
| **qwen3.5:4b** | The default AI model Jarvis uses. Made by Alibaba's Qwen team. 4 billion parameters. |
| **RAG** | Retrieval-Augmented Generation. The AI retrieves relevant documents first, then generates an answer using them. |
| **Embedding** | A list of numbers that represents the meaning of a piece of text. Similar texts have similar embeddings. |
| **Vector** | Another word for embedding — a list of numbers representing meaning. |
| **Qdrant** | The vector database that stores embeddings and lets you search by meaning. |
| **Chunk** | A small piece of a document (a few paragraphs). Documents are split into chunks for better search. |
| **Flask** | A Python library for building web servers. Jarvis uses it for both the Search UI and the Agent. |
| **Port** | A number that identifies a specific service on your computer. Like a door number. |
| **SSE (Server-Sent Events)** | A technology that lets the server stream text to your browser in real time (how chat tokens appear one by one). |
| **JSON** | A text format for structured data. Looks like `{"key": "value"}`. Jarvis stores data in JSON files. |
| **API** | Application Programming Interface. A way for programs to talk to each other over HTTP. |
| **Proxy** | A middleman server that forwards your internet traffic. Useful for bypassing corporate firewalls. |

---

## What's Next?

Now that Jarvis is running, explore further:

| Goal | Read |
|------|------|
| Understand the full system architecture | [Backend Overview](backend-overview.md) |
| Learn how RAG works conceptually | [Ch. 1: RAG Concepts](ch1-rag-concepts.md) |
| Understand the technologies used | [Tech Stack Overview](implementation/tech-stack-overview.md) |
| Learn how each script works | [Implementation Index](implementation/README.md) |
| Customize the briefing depth | Edit [`references/knowledge-scope.md`](../references/knowledge-scope.md) |
| See the full documentation map | [Documentation Index](docs-index.md) |

**Reading order for beginners:**

1. This guide (you are here)
2. [Tech Stack Overview](implementation/tech-stack-overview.md) — what each technology does
3. [Ch. 1: RAG Concepts](learning/rag/ch1-rag-concepts.md) — how the AI search works
4. [Ch. 3: Vector Search Explained](learning/rag/ch3-vector-search-explained.md) — the math behind it
5. [Backend Overview](backend-overview.md) — the full system reference
