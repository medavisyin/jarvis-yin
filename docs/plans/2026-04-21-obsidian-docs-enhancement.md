# Obsidian Docs Enhancement Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Leverage Obsidian's unique features — Canvas visual boards, wiki-links, tags, graph view, and templates — to transform the Jarvis docs from a flat markdown folder into an interconnected, navigable knowledge base with visual architecture maps.

**Architecture:** Three Canvas boards (system architecture, learning path, implementation roadmap) serve as visual entry points. Wiki-links (`[[...]]`) create a navigable graph. Tags enable cross-cutting filtering. Obsidian settings are tuned for the vault.

**Tech Stack:** Obsidian Canvas (JSON format), Obsidian wiki-links, YAML frontmatter, Obsidian tags

---

## Background: What Obsidian Can Do for Your Docs

### Features That Matter for Jarvis Docs

| Feature | What it does | Why it helps |
|---------|-------------|--------------|
| **Wiki-links** `[[page]]` | Click any `[[link]]` to jump to that doc | Navigate between 85+ docs without remembering paths |
| **Graph View** | Visual node graph of all docs and their connections | See which docs are orphans, which are hubs, find clusters |
| **Canvas** | Infinite whiteboard: place docs, cards, arrows, groups | Visual architecture diagrams that LINK to actual docs |
| **Tags** `#tag` | Cross-cutting labels on any doc | Filter all docs by `#rag`, `#stock`, `#learning` etc. |
| **Backlinks** | See every doc that links TO this doc | "Who references this page?" — automatic |
| **Outline** | Shows heading structure of current doc | Navigate within long docs (backend-overview is 992 lines!) |
| **Search** | Full-text + tag + path search | Find anything across 85+ docs instantly |
| **Frontmatter** | YAML metadata at top of file | Status, category, date — filterable, queryable |
| **Templates** | Reusable doc templates | Consistent structure for new impl docs, learning chapters |
| **Embeds** `![[page]]` | Inline-embed another doc's content | Show architecture diagram inside multiple docs |

### Canvas Specifically

Canvas is Obsidian's killer feature for your use case. It's a `.canvas` file (JSON format) that creates an infinite visual board where you can:

- **Place file cards** — drag any `.md` file onto the canvas; clicking opens the actual doc
- **Add text cards** — free-form notes, labels, descriptions
- **Draw edges (arrows)** — show data flow, dependencies, reading order
- **Create groups** — colored rectangles that visually cluster related items
- **Mix everything** — combine file references, text notes, and arrows on one board

This means your Mermaid diagrams in `architecture.md` become **interactive** — each box links to the real implementation doc.

---

## Task 1: Configure Obsidian Settings for the Vault

**Files:**
- Modify: `docs/.obsidian/app.json`

**Step 1: Update Obsidian app settings for wiki-links and readable paths**

Update `app.json` to enable wiki-links with relative paths (so links work both in Obsidian and on GitHub):

```json
{
  "useMarkdownLinks": false,
  "newLinkFormat": "relative",
  "showFrontmatter": true,
  "strictLineBreaks": true,
  "readableLineLength": true
}
```

**Step 2: Verify in Obsidian**

Open Obsidian → Settings → Files & Links:
- Expected: "Use [[Wikilinks]]" is ON
- Expected: "New link format" is "Relative path to file"

---

## Task 2: Create System Architecture Canvas

**Files:**
- Create: `docs/design/jarvis-architecture.canvas`

**Purpose:** Visual system architecture board showing all Jarvis components, how they connect, and linking each component to its implementation doc. This replaces "reading" the Mermaid diagrams — now you can SEE the system and CLICK into any part.

**Layout plan:**

```
┌──────────────────────────────────────────────────────────────┐
│  GROUP: External Systems (top)                                │
│  [News Sources] [Ollama] [Atlassian] [Git] [AKShare] [TTS]  │
└──────────────────────────────────────────────────────────────┘
          │ arrows down
┌──────────────────────────────────────────────────────────────┐
│  GROUP: Presentation Layer (upper-middle)                     │
│  [Search UI :18888] [Chat Agent :18889] [Telegram Bot]       │
└──────────────────────────────────────────────────────────────┘
          │ arrows down
┌──────────────────────────────────────────────────────────────┐
│  GROUP: Application Layer (middle)                            │
│  [Agent Loop] [Auto-RAG] [Tool Router] [Daily Fetch] [Stock]│
└──────────────────────────────────────────────────────────────┘
          │ arrows down
┌──────────────────────────────────────────────────────────────┐
│  GROUP: Processing Layer (lower-middle)                       │
│  [16 Fetchers] [Merge+Dedup] [6 Indexers] [Audio] [Scanner] │
└──────────────────────────────────────────────────────────────┘
          │ arrows down
┌──────────────────────────────────────────────────────────────┐
│  GROUP: Intelligence + Storage (bottom)                       │
│  [Ollama LLMs] [Embeddings] [XGBoost] [Qdrant] [File System]│
└──────────────────────────────────────────────────────────────┘
```

**What makes this powerful:** Each card is a FILE card pointing to the real implementation doc. Click "Agent Loop" → opens `implementation/rag/agent-impl.md`. Click "Scanner" → opens `implementation/stock/scanner-impl.md`.

**Step 1: Create the canvas JSON**

The canvas file follows this JSON schema:
```json
{
  "nodes": [
    { "id": "...", "type": "file", "file": "path/to/doc.md", "x": 0, "y": 0, "width": 250, "height": 60 },
    { "id": "...", "type": "text", "text": "Label text", "x": 0, "y": 0, "width": 250, "height": 60 },
    { "id": "...", "type": "group", "label": "Group Name", "x": 0, "y": 0, "width": 800, "height": 200 }
  ],
  "edges": [
    { "id": "...", "fromNode": "node1", "toNode": "node2", "fromSide": "bottom", "toSide": "top" }
  ]
}
```

Create the full architecture canvas with 5 layer groups, ~20 file/text cards, and ~15 edges showing data flow.

**Step 2: Open and verify in Obsidian**

Open `design/jarvis-architecture.canvas` in Obsidian:
- Expected: 5 colored groups arranged top-to-bottom
- Expected: Each component card is clickable → opens the linked doc
- Expected: Arrows show data flow between layers

---

## Task 3: Create Learning Path Canvas

**Files:**
- Create: `docs/learning/learning-path.canvas`

**Purpose:** Visual learning roadmap showing the recommended reading order from `learning/README.md` as a flowchart. Learners can see the full path and click any chapter to start reading.

**Layout plan:**

```
[Phase 1: Foundations]          [Stock Track (独立)]
  ML Ch.1 → ML Ch.2 → HF Ch.1   Stock Ch.1 → Ch.2 → ... → Ch.10
       ↓
[Phase 2: Core RAG]
  RAG Ch.1 → HF Ch.2 → RAG Ch.2 → HF Ch.4
       ↓
[Phase 3: Retrieval Deep Dive]
  RAG Ch.3 → HF Ch.3 → RAG Ch.11
       ↓
[Phase 4: Advanced]
  ML Ch.3 → RAG Ch.7 → LLM Guides
```

**Step 1: Create the learning path canvas JSON**

Each chapter becomes a file card. Groups represent phases. Arrows show the recommended sequence. The stock track is a separate group on the right (independent path).

**Step 2: Verify in Obsidian**

- Expected: 4 phase groups + 1 stock group
- Expected: Chapters are clickable file cards
- Expected: Arrows show recommended reading order

---

## Task 4: Create Implementation & Roadmap Canvas

**Files:**
- Create: `docs/plans/roadmap.canvas`

**Purpose:** Visual project roadmap combining the enhancement plan tiers with links to relevant implementation docs. See what's done, what's next, and what each tier involves.

**Layout plan:**

```
[Tier 0: Bug Fixes]     → status: priority
[Tier 1: Testing]       → status: next
[Tier 2: RAG Upgrades]  → linked to: plan-advanced-rag.md
[Tier 3: Stock v2]      → linked to: plan-ml-integration.md
[Tier 4: Infrastructure] → Docker, CI/CD
[Tier 5: Future]         → new features
```

**Step 1: Create the roadmap canvas**

Each tier is a group. Key items within each tier are text cards with status labels. Links to detailed plan docs are file cards within the groups.

**Step 2: Verify in Obsidian**

- Expected: 6 tier groups arranged left-to-right or top-to-bottom
- Expected: Plan docs are clickable
- Expected: Status visible at a glance

---

## Task 5: Add YAML Frontmatter to Key Docs

**Files:**
- Modify: ~15 key docs (README files, architecture, guides)

**Purpose:** Add YAML frontmatter with `tags`, `category`, and `status` so docs are filterable in Obsidian's search and can show metadata in graph view.

**Step 1: Add frontmatter to hub docs**

Example frontmatter format:
```yaml
---
tags:
  - architecture
  - design
category: design
status: current
last-updated: 2026-04-20
---
```

Tag taxonomy:
- **Domain:** `#rag`, `#stock`, `#briefing`, `#telegram`, `#learning`
- **Type:** `#architecture`, `#implementation`, `#guide`, `#plan`, `#tutorial`
- **Status:** `#current`, `#draft`, `#completed`
- **Language:** `#chinese`, `#english`

Target docs for frontmatter:
1. `README.md` — tags: `#hub`
2. `design/architecture.md` — tags: `#architecture`, `#design`
3. `design/rag-agent-design.md` — tags: `#architecture`, `#rag`
4. `getting-started.md` — tags: `#guide`, `#setup`
5. `backend-overview.md` — tags: `#architecture`, `#implementation`
6. `implementation/README.md` — tags: `#hub`, `#implementation`
7. `implementation/stock/README.md` — tags: `#hub`, `#stock`
8. `learning/README.md` — tags: `#hub`, `#learning`
9. `guides/stock-usage-guide.md` — tags: `#guide`, `#stock`, `#chinese`
10. `guides/telegram-bot-guide.md` — tags: `#guide`, `#telegram`
11. `plans/2026-04-17-jarvis-next.md` — tags: `#plan`, `#roadmap`
12. `plans/2026-04-12-stock-prediction.md` — tags: `#plan`, `#stock`

**Step 2: Verify in Obsidian**

Open Obsidian → Tags pane (right sidebar):
- Expected: Tags appear with counts
- Expected: Clicking a tag filters to matching docs

---

## Task 6: Delete Empty Canvas and Clean Up

**Files:**
- Delete: `docs/Untitled.canvas` (empty, replaced by the 3 new canvases)

**Step 1: Remove the empty default canvas**

**Step 2: Verify**

- Expected: `Untitled.canvas` no longer appears in Obsidian file explorer

---

## Summary: What You Get After This Plan

| Before | After |
|--------|-------|
| 85+ flat markdown files | Interconnected wiki-linked knowledge base |
| Mermaid diagrams you read | Interactive Canvas boards you click through |
| Remember file paths | Click through visual architecture map |
| Linear reading order | Visual learning path with phase groups |
| No metadata | Tagged, filterable, searchable docs |
| Empty `Untitled.canvas` | 3 purpose-built Canvas boards |
| No graph connections | Graph view shows doc relationships |

**Canvas boards created:**
1. `design/jarvis-architecture.canvas` — System architecture (5 layers, ~20 components, clickable to impl docs)
2. `learning/learning-path.canvas` — Learning roadmap (4 phases + stock track, clickable chapters)
3. `plans/roadmap.canvas` — Enhancement roadmap (6 tiers, linked to plan docs)
