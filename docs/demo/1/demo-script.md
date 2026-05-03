# Jarvis & RAG Demo — Full Script & Demo Guide

**Duration:** 60 minutes
**Presenter:** Rong Yin
**Audience:** Team (familiar with LLMs, new to RAG & Jarvis)
**Prerequisites:** Jarvis running at `localhost:18889`, Search UI at `localhost:18888`

---

## Pre-Demo Checklist

- [ ] Jarvis agent running: `http://localhost:18889`
- [ ] Search UI running: `http://localhost:18888`
- [ ] Ollama running with `qwen3.5:4b` model loaded
- [ ] Browser open with both tabs ready
- [ ] PowerPoint presentation open (slide 1 visible)
- [ ] Fresh chat session (clear any previous conversations)
- [ ] VPN/proxy running if Daily Fetch will scrape live sources
- [ ] Audio output working (for MP3 playback demo)

---

## Section 1: What is Jarvis? (Slides 1-3, 5 min)

### Slide 1 — Title

**Speech:**

> Welcome everyone, and thanks for joining. Today I want to introduce Jarvis — an AI assistant I've built that uses a technique called RAG, or Retrieval-Augmented Generation. It's designed specifically for our medavis team and our daily workflow.
>
> Over the next hour, I'll explain what RAG adds on top of the LLMs you already know, give you two live demos, and share what I've learned building this.

**Timing:** 1 minute. Advance to slide 2.

---

### Slide 2 — Agenda

**Speech:**

> Here's our plan. We start with context — what is Jarvis and why. Then a quick RAG primer — you all know LLMs, so I'll focus on what RAG adds. Then the architecture overview, followed by our first live demo of the medavis features — Jira, Confluence, commits, codebase queries.
>
> After that, I'll show you how the Auto-RAG engine works under the hood, then a second demo of the Daily Fetch pipeline. We'll wrap up with lessons and Q&A. About an hour total.

**Timing:** 1 minute. Advance to slide 3.

---

### Slide 3 — What is Jarvis?

**Speech:**

> So, what is Jarvis? It's an AI assistant that runs entirely locally — on my machine. No data leaves your computer. No API calls to OpenAI or anyone else. It uses Ollama for the LLM and Qdrant as a vector database.
>
> The key thing: it has over 18,000 indexed knowledge chunks. These come from our Confluence wiki, Jira tickets, our Java codebase, daily AI briefings, git commit history, and more.
>
> The core innovation is something I call Auto-RAG — it ALWAYS retrieves relevant context before answering any question. Unlike ChatGPT, which just uses its training data, Jarvis looks things up first. Think of it like this: a regular LLM is a smart person who answers from memory. Jarvis is a smart person who checks their notes before answering.
>
> On the right you can see the tech stack — small but effective. A 4-billion parameter model, 384-dimensional embeddings, Flask backend, all local.

**Timing:** 3 minutes. Advance to slide 4.

---

## Section 2: RAG 101 for LLM Users (Slides 4-6, 8 min)

### Slide 4 — The Problem LLMs Have

**Speech:**

> You all use LLMs. You know they're powerful. But they have a fundamental gap: they don't know about YOUR data. The model's knowledge was frozen at training time. It has no idea what's in our Jira board, what our wiki says, what code we committed last week.
>
> On the left — LLM alone: frozen knowledge, no company data, hallucinations on domain questions, generic answers.
>
> On the right — LLM plus RAG: always up-to-date because it retrieves from your knowledge base, grounded answers with sources you can verify, reduced hallucinations because it has evidence.
>
> RAG stands for Retrieval-Augmented Generation. The simplest way to think about it: "Don't just think — look it up first, then answer."

**Timing:** 3 minutes. Advance to slide 5.

---

### Slide 5 — How RAG Works

**Speech:**

> Here's how RAG works in four steps.
>
> **Step 1 — Index.** You take your documents — wiki pages, reports, code files — split them into chunks of maybe 200-500 tokens each, convert each chunk into a vector embedding, and store them in a vector database. This is the offline part, done once and updated incrementally.
>
> **Step 2 — Retrieve.** When a user asks a question, you convert their question into the same kind of embedding, then search the vector database for the most similar chunks. This is extremely fast — milliseconds.
>
> **Step 3 — Augment.** You take those retrieved chunks and inject them into the LLM's prompt. So now the LLM has both the question AND relevant evidence.
>
> **Step 4 — Generate.** The LLM produces an answer that's grounded in the actual data, not just its training knowledge.
>
> The key insight: the LLM never answers from memory alone. It always has evidence to reference.

**Timing:** 3 minutes. Advance to slide 6.

---

### Slide 6 — Key Concepts

**Speech:**

> A few key concepts. Since you know LLMs, I'll keep this quick.
>
> **Embeddings** — these are 384-dimensional vectors that capture semantic meaning. "How to deploy" and "deployment process" end up as very similar vectors, even though the words are different. That's the power — semantic search, not just keyword matching.
>
> **Vector Search** — finding the most similar chunks by cosine similarity. Even with 18,000+ chunks, this takes about 35 milliseconds.
>
> **Hybrid Search** — this is important. We don't ONLY do vector search. We also run BM25, which is classic keyword search. Then we merge the results using Reciprocal Rank Fusion. Why? Because vector search is great for "what is this about?" but can miss exact terms. BM25 catches exact matches. Together, they're stronger than either alone.
>
> **Chunking** — how you split documents matters a lot. Too big, and you waste context. Too small, and you lose meaning. We use overlapping chunks to preserve context across boundaries.

**Timing:** 2 minutes. Advance to slide 7.

---

## Section 3: Jarvis Architecture (Slides 7, 5 min)

### Slide 7 — Architecture Overview

**Speech:**

> Here's the full Jarvis architecture. Let me walk through the layers.
>
> **Top layer** — the web UI. Simple chat interface, SSE streaming so you see tokens as they're generated, image upload support, and a model selector.
>
> **Middle layer** — Flask with blueprints. The toolbar blueprint handles medavis features. The daily fetch blueprint manages the pipeline. Intent routing figures out what you're asking about.
>
> **The core** — three engines working together. The Auto-RAG Engine handles all retrieval — vector search, BM25, entity filtering, vague query rewriting. The Tool System calls out to Jira, git, Confluence as needed. The Agent Loop orchestrates everything in a ReAct pattern — think, act, observe, repeat.
>
> **Infrastructure** — all local. Ollama runs the LLM, Qdrant stores vectors in-memory with disk snapshots, MiniLM-L6 does embeddings, Edge TTS generates audio.
>
> **Bottom** — the knowledge base. Over 18,000 chunks from AI briefings, Confluence, our Java codebase, git history, Jira, and custom documents. All searchable through natural language.

**Timing:** 5 minutes. Advance to slide 8.

---

## Section 4: Live Demo — Medavis Features (Slides 8-9, 15 min)

### Slide 8 — Section Divider

**Speech:**

> Alright, let's switch to the live demo. I'll show you the medavis-specific features — the tools that integrate with our daily work.

**Action:** Leave this slide up for 10 seconds, then switch to the browser.

---

### Slide 9 — Features Overview (show briefly)

**Speech:**

> These are the five features I'll demo. Let me switch to the browser.

**Action:** Show slide 9 for 15 seconds, then switch to browser at `http://localhost:18889`.

---

### Demo 4.1: Jira Daily Report (3 min)

**Steps:**

1. Open Jarvis chat at `http://localhost:18889`
2. Type: **"Show me today's Jira report for our team"**
3. Wait for the response to stream in
4. Point out:
   - The streaming response (tokens appearing one by one)
   - The tool call happening (Jira report execution)
   - The structured output (open tickets, sprint activity)
   - The source attribution at the bottom

**Speech while waiting:**

> I'm asking Jarvis about our Jira status. Watch what happens — it detects the intent as a Jira report request, triggers the Jira tool, and streams the response. You can see the tokens appearing in real-time via SSE. The tool runs a PowerShell script that queries our Atlassian instance.
>
> Notice the sources at the bottom — you can verify where the information came from.

---

### Demo 4.2: Confluence Wiki Search (3 min)

**Steps:**

1. Type: **"What did the team update on Confluence this week?"**
2. Wait for response
3. Point out:
   - RAG retrieval from indexed wiki pages
   - Version diff summaries (what changed)
   - Team member attribution

**Speech:**

> Now I'm asking about Confluence updates. Jarvis has indexed our team's wiki pages. It retrieves relevant chunks, shows what changed, and who made the changes. This is all from the vector database — no live Confluence API call needed for search, because the content was indexed during Daily Fetch.

---

### Demo 4.3: Commit Summary (3 min)

**Steps:**

1. Type: **"What were the recent commits from the team?"**
2. Wait for response
3. Point out:
   - Multi-repo coverage
   - Author aliases (mapping git emails to names)
   - Bitbucket links

**Speech:**

> Commit summaries pull from multiple git repositories. Jarvis knows about author aliases — so it maps git email addresses to team member names. It generates Bitbucket links so you can click through to the actual commits. This runs as a tool call — executing git log across configured repos.

---

### Demo 4.4: Codebase Query (3 min)

**Steps:**

1. Type: **"How does the PDF generation work in Portal4Med?"** (or a relevant project-specific question)
2. Wait for response
3. Point out:
   - RAG retrieving from indexed Java codebase
   - Project-scoped filtering
   - Code context in the response

**Speech:**

> This is one of my favorites. I'm asking about our codebase. Jarvis has indexed our Java source files — it understands class structures, method signatures, configuration files. The retrieval is project-scoped, so it knows to look in the P4M codebase specifically. The response includes actual code context — not hallucinated code, but references to real files.

---

### Demo 4.5: Project Dependency Graph (3 min)

**Steps:**

1. Type: **"What depends on the reporting module?"** (or relevant dependency question)
2. Wait for response
3. Point out:
   - Dependency graph traversal
   - Impact analysis
   - pom.xml-derived relationships

**Speech:**

> The project graph feature parses our Maven pom.xml files to build a dependency graph. When you ask "what depends on X?", Jarvis traverses the graph and shows you the impact chain. This is incredibly useful for refactoring — before you change a module, you can see exactly what might break.

**Action:** Switch back to PowerPoint, advance to slide 10.

---

## Section 5: How Auto-RAG Works (Slides 10-11, 5 min)

### Slide 10 — Auto-RAG Deep Dive

**Speech:**

> Now let me explain what was happening under the hood during those demos. This is what makes Jarvis different from basic RAG implementations.
>
> The flow goes: user query arrives, intent classification routes it, batch embedding encodes the query and entity names, vector search runs against Qdrant, and context assembly collects the top-K chunks plus any tool results.
>
> **What makes this different?** Eight things.
>
> First, it's always-on. RAG runs on EVERY query. The LLM doesn't decide whether to search — it always gets context.
>
> Second, hybrid search — vector plus BM25 with RRF fusion. Best of both worlds.
>
> Third, entity-awareness — it knows about team members, wiki page types, project names, and uses these as filters.
>
> Fourth, vague query rewriting — if your question is unclear, the LLM rewrites it before searching.
>
> And then parallel execution, project graph expansion, adaptive prompting that switches between compact and full system prompts, and confidence scoring for disclaimers.

**Timing:** 3 minutes. Advance to slide 11.

---

### Slide 11 — Data Flow

**Speech:**

> Here's the actual data flow for every query, as pseudocode. Three threads run in parallel — that's the key to performance.
>
> Thread 1 is Auto-RAG: vague query check, batch embedding at 24 milliseconds, Qdrant vector search at 35 milliseconds, BM25, entity filtering. Total maybe 100-200ms.
>
> Thread 2 and 3 are auto-tools — commit summary and Jira report, only if the intent suggests they're needed.
>
> All threads finish, results are assembled into an augmented prompt, and Ollama starts streaming. If the model wants to call a tool during generation, it can — that's the ReAct loop.
>
> The important takeaway: retrieval happens BEFORE generation, in parallel with tool calls. The user sees the first token very quickly.

**Timing:** 2 minutes. Advance to slide 12.

---

## Section 6: Live Demo — Daily Fetch (Slides 12-13, 12 min)

### Slide 12 — Section Divider

**Speech:**

> Now let's see the Daily Fetch pipeline — this is how Jarvis aggregates information from multiple sources every day.

**Action:** Show for 10 seconds, then switch to slide 13 briefly.

---

### Slide 13 — Pipeline Overview

**Speech:**

> The pipeline has six major steps. Let me show you.

**Action:** Show slide 13 for 20 seconds, then switch to browser.

---

### Demo 6.1: Trigger Daily Fetch (3 min)

**Steps:**

1. In Jarvis UI, find the toolbar area
2. Click the "Daily Fetch" button (or navigate to the toolbar section)
3. Show the job starting in the background
4. Point out the progress indicators

**Speech:**

> I'm triggering the Daily Fetch from the toolbar. This kicks off a background thread that runs through all six pipeline steps. You can see the job ID and progress status. In production, this would run on a schedule — I trigger it manually for the demo.
>
> The fetchers scrape from 16 different AI news sources in parallel — sites like The Verge AI, MIT Tech Review, Hugging Face papers, and more. Each fetcher handles its own source format and error handling.

---

### Demo 6.2: Show Briefing Output (3 min)

**Steps:**

1. Navigate to the reports folder (or show a pre-generated briefing)
2. Open the daily briefing PDF
3. Show the briefing-data.json structure
4. Point out: topics, sources, deduplication results

**Speech:**

> Here's what the pipeline produces. The briefing PDF has today's AI news — synthesized, deduplicated, and organized by topic. The raw data is in briefing-data.json, which also feeds into the vector database for future search.
>
> The topic deduplication is LLM-based — it identifies when two different sources report on the same story and merges them. This prevents the same news from appearing five times in your briefing.

---

### Demo 6.3: Audio Playback (2 min)

**Steps:**

1. Find the generated MP3 files (ai-briefing.mp3, world-news.mp3)
2. Play a 15-20 second clip of the AI briefing audio
3. Point out the natural-sounding TTS

**Speech:**

> The pipeline also generates audio podcasts using Microsoft Edge TTS. There are three: AI news, world news, and China news. The narration is generated by the LLM — it writes a podcast-style script, then TTS converts it to speech. Here's a quick clip.
>
> [Play 15-20 seconds of audio]
>
> The voice quality is surprisingly good for free TTS. You can listen to these during your commute or morning coffee.

---

### Demo 6.4: Search UI (4 min)

**Steps:**

1. Switch to `http://localhost:18888`
2. Type a search query: **"transformer architecture advances"** (or something from today's briefing)
3. Show the search results with:
   - Relevance scores
   - Source types (briefing, wiki, code)
   - Chunk previews
4. Try a filter (e.g., filter by `item_type: wiki_page`)
5. Show the library management view

**Speech:**

> Finally, let me show you the Search UI. This is a standalone search interface into the entire knowledge base. I can search semantically — "transformer architecture advances" — and see all relevant chunks ranked by relevance.
>
> Notice the scores, the source types, and the chunk previews. I can filter by type — wiki pages only, briefings only, codebase only. This is useful for exploring what's in the knowledge base and verifying retrieval quality.
>
> The library view shows index statistics — how many chunks from each source, when they were last updated. You can trigger re-indexing from here too.

**Action:** Switch back to PowerPoint, advance to slide 14.

---

## Section 7: Lessons & Takeaways (Slide 14, 5 min)

### Slide 14 — Lessons & Takeaways

**Speech:**

> Let me wrap up with what I've learned building this.
>
> **What worked well:** Auto-RAG — always retrieving context — is the single most impactful design decision. The model never answers blind. Hybrid search catches both semantic and keyword matches, which matters when people use exact product names or ticket numbers. Running locally means complete privacy and no API costs. And incremental indexing means we only re-embed what changed.
>
> **Challenges:** The 4-billion parameter model has quality limits compared to GPT-4. Complex multi-step reasoning can be shaky. Tool calling reliability depends on model capability — bigger models are better at it. The embedding model is English-focused, so Chinese content retrieval is less precise. And in-memory Qdrant means we need careful snapshot management.
>
> **The big takeaway:** RAG is the practical bridge between powerful-but-generic LLMs and your team's specific knowledge. You don't need GPT-4 to build useful tools — a small model plus great retrieval goes a long way. And the real engineering investment should be in the retrieval pipeline, not the generation step. The pipeline is where the quality comes from.

**Timing:** 5 minutes. Advance to slide 15.

---

## Section 8: Q&A (Slide 15, 5 min)

### Slide 15 — Thank You

**Speech:**

> Thank you for your time! I'm happy to take any questions. You can try Jarvis yourself — the agent is at localhost 18889, and the search UI is at 18888. Feel free to explore, break things, and give me feedback.
>
> What questions do you have?

**Prepared Q&A answers:**

| Likely Question | Answer |
|---|---|
| "How much does it cost to run?" | Zero ongoing cost. All local — Ollama is free, Qdrant is open-source, Edge TTS is free. Just your laptop's electricity. |
| "How long does indexing take?" | Incremental indexing takes 1-3 minutes. Full re-index from scratch takes about 15-20 minutes for 18K chunks. |
| "Can we use GPT-4 instead?" | Yes, the model is configurable. You can point Ollama to any model, or configure DeepSeek API for cloud models. Trade-off is privacy vs quality. |
| "How accurate is the retrieval?" | Hybrid search with RRF typically gets relevant results in the top 5. We have evaluation datasets to measure this. |
| "Can other teams use this?" | The architecture is generic. You'd need to configure their data sources (different Jira boards, Confluence spaces, repos) but the core is reusable. |
| "How does it handle outdated information?" | Incremental indexing updates changed documents. Old versions get replaced. The daily fetch pipeline keeps AI news current. |

---

## Timing Summary

| Section | Slides | Duration | Cumulative |
|---|---|---|---|
| What is Jarvis? | 1-3 | 5 min | 5 min |
| RAG 101 | 4-6 | 8 min | 13 min |
| Architecture | 7 | 5 min | 18 min |
| **LIVE DEMO: Medavis** | 8-9 | **15 min** | 33 min |
| Auto-RAG Deep Dive | 10-11 | 5 min | 38 min |
| **LIVE DEMO: Daily Fetch** | 12-13 | **12 min** | 50 min |
| Lessons | 14 | 5 min | 55 min |
| Q&A | 15 | 5 min | 60 min |

---

## Emergency Backup Plans

| Problem | Fallback |
|---|---|
| Jarvis server is down | Show pre-recorded screenshots in the PPT; narrate the flow verbally |
| Ollama is slow / unresponsive | Use the Search UI (18888) which doesn't need LLM; explain the retrieval results |
| Daily Fetch fails (network/proxy) | Show pre-generated briefing files from a previous run |
| Audio playback doesn't work | Skip audio; describe the TTS feature verbally |
| Tool call fails (Jira/git) | Show the RAG-only response; explain that tools add extra context |
