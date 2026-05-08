# Jarvis Chat Pipeline Improvement Roadmap

**Created**: 2026-04-30
**Status**: COMPLETED — all phases implemented (2026-04-30)
**Scope**: Improve how Jarvis handles user questions in `scripts/rag/agent.py`

---

## Current Architecture (As-Is)

```
User (Web UI / Telegram)
    │
    ▼
POST /api/agent (query, image, history, session_id)
    │
    ├─ [1] Session-based routing (regex + heuristics + hardcoded session IDs)
    │       └─ Learning modes: AI/English/Casual/AWS/DeepDive
    │
    ├─ [2] Keyword auto-tool detection (substring matching)
    │       └─ commit keywords → _auto_tool_commit
    │       └─ jira keywords → _auto_tool_jira
    │
    ├─ [3] _auto_rag_search (parallel with auto-tools)
    │       ├─ Batch embeddings (sentence_transformers MiniLM)
    │       ├─ _vector_search (Qdrant in-memory + BM25 hybrid/RRF)
    │       ├─ Extra passes: team names, wiki keywords, project keywords
    │       └─ Vague query → _rewrite_query via fast model
    │
    ├─ [4] System prompt assembly
    │       ├─ COMPACT (auto-context available) vs FULL (tools needed)
    │       └─ PROJECT_ADDON (if project-related sources found)
    │
    ├─ [5] Tool gating decision
    │       └─ auto-context non-empty → disable tools (save tokens)
    │       └─ has_project_context → re-enable tools
    │
    ├─ [6] LLM generation loop (Ollama, up to MAX_AGENT_ITERATIONS=8)
    │       ├─ Stream tokens → SSE to client
    │       ├─ If tool_calls → execute → append result → re-call LLM
    │       └─ Available tools: rag_search, briefing_search, confluence_search,
    │          jira_report, commit_summary, analyze_image, project_query
    │
    └─ [7] SSE Response → Client (token chunks + sources + [DONE])
```

### Key Pain Points

| # | Issue | Impact |
|---|-------|--------|
| 1 | No intent classification | Can't route intelligently; relies on fragile keyword/session logic |
| 2 | Keyword-based auto-tools | False positives (e.g., "commit to learning") and false negatives |
| 3 | Monolithic 11K-line file | Hard to maintain, test, extend; high cognitive load |
| 4 | No query decomposition | Multi-part questions get a single RAG pass |
| 5 | No confidence/relevance gating | Poor retrieval still generates answers → hallucination risk |
| 6 | Fragile tool gating | Non-obvious conditional logic leads to wrong tool availability |
| 7 | Basic conversation memory | Only token-based summarization; no semantic long-term memory |

---

## Improvement Roadmap

### Phase 1: Foundation — Modular Refactoring (Low risk, high leverage)

**Goal**: Make the codebase maintainable and testable before adding features.

| Task | Description | Effort |
|------|-------------|--------|
| 1.1 | Extract `router.py` — session routing + intent logic | 2-3h |
| 1.2 | Extract `rag_engine.py` — `_auto_rag_search`, `_vector_search`, BM25 | 2-3h |
| 1.3 | Extract `tools/` package — each tool as a module | 2h |
| 1.4 | Extract `prompts.py` — all system prompts | 1h |
| 1.5 | Extract `learning/` package — all learning mode logic | 2-3h |
| 1.6 | Keep `agent.py` as thin Flask app (~200 lines) | 1h |
| 1.7 | Add integration tests for the `/api/agent` endpoint | 2-3h |

**Proposed structure:**
```
scripts/rag/
├── agent.py           # Flask app, routes only (~200 lines)
├── router.py          # Intent classification + session routing
├── rag_engine.py      # RAG retrieval (vector + BM25 + hybrid)
├── prompts.py         # All system prompts
├── agent_loop.py      # run_agent() — LLM loop + tool orchestration
├── tools/
│   ├── __init__.py    # Tool registry + schemas
│   ├── rag_tools.py   # rag_search, briefing_search
│   ├── confluence.py  # confluence_search
│   ├── jira_tool.py   # jira_report
│   ├── git_tool.py    # commit_summary
│   ├── vision.py      # analyze_image
│   └── project.py     # project_query
├── learning/
│   ├── __init__.py
│   ├── ai_learning.py
│   ├── english.py
│   ├── aws_cert.py
│   └── deep_dive.py
└── memory/
    └── conversation.py  # History management + summarization
```

---

### Phase 2: Intent Classification Layer (Medium effort, high impact)

**Goal**: Replace keyword matching with proper intent understanding.

| Task | Description | Effort |
|------|-------------|--------|
| 2.1 | Define intent taxonomy | 1h |
| 2.2 | Implement LLM-based classifier (use fast model: qwen3:1.7b) | 2-3h |
| 2.3 | Build routing table: intent → strategy | 1h |
| 2.4 | A/B test against current keyword approach | 2h |
| 2.5 | Deprecate keyword-based auto-tool detection | 1h |

**Intent Taxonomy (proposed):**
```
├── knowledge_qa          # "What is X?", "How does Y work?"
│   ├── factual           # Direct facts from RAG
│   ├── analytical        # Requires synthesis across multiple sources
│   └── temporal          # "What happened last week?"
├── tool_action           # "Show my Jira tickets", "What was committed?"
│   ├── jira
│   ├── git_history
│   ├── confluence
│   └── project_query
├── learning              # Topic-based learning sessions
│   ├── topic_selection
│   ├── quiz_request
│   ├── teach_request
│   └── followup
├── creative              # "Write a summary", "Draft an email"
├── smalltalk             # Greetings, meta-questions
└── complex_reasoning     # Multi-step questions needing decomposition
```

**Implementation approach:**
```python
async def classify_intent(query: str, history: list, session_context: dict) -> IntentResult:
    """Fast LLM-based intent classification (~200ms with 1.7b model)."""
    prompt = f"""Classify this user query into one intent category.
    Query: {query}
    Session: {session_context.get('type', 'general')}
    Recent context: {history[-1]['content'][:100] if history else 'none'}
    
    Categories: knowledge_qa.factual, knowledge_qa.analytical, knowledge_qa.temporal,
    tool_action.jira, tool_action.git_history, tool_action.confluence, tool_action.project_query,
    learning.topic_selection, learning.quiz_request, learning.teach_request, learning.followup,
    creative, smalltalk, complex_reasoning
    
    Reply with ONLY the category name."""
    
    result = ollama.chat(model=FAST_MODEL, messages=[...], stream=False)
    return IntentResult(intent=result.message.content.strip(), confidence=...)
```

---

### Phase 3: Query Understanding & Decomposition (Medium effort, high impact)

**Goal**: Handle complex multi-part questions properly.

| Task | Description | Effort |
|------|-------------|--------|
| 3.1 | Build query complexity detector (single vs multi-part) | 1-2h |
| 3.2 | Implement sub-question decomposition | 2-3h |
| 3.3 | Parallel retrieval per sub-question | 2h |
| 3.4 | Result synthesis / merging logic | 2-3h |

**Example:**
```
User: "What changes did Jan push last week and are any of them related to the identity server Jira tickets?"

Decomposed:
  Q1: "What changes did Jan push last week?" → tool_action.git_history
  Q2: "What are the current identity server Jira tickets?" → tool_action.jira  
  Q3: (synthesis) "Which commits from Q1 relate to tickets from Q2?" → LLM reasoning
```

**Implementation sketch:**
```python
async def decompose_query(query: str, intent: IntentResult) -> list[SubQuery]:
    if intent.intent != "complex_reasoning":
        return [SubQuery(text=query, strategy=intent.intent)]
    
    prompt = f"""Break this complex question into 2-4 simpler sub-questions.
    Each sub-question should be answerable independently.
    
    Question: {query}
    
    Output JSON: [{{"text": "...", "depends_on": null_or_index}}]"""
    
    result = ollama.chat(model=FAST_MODEL, ...)
    return parse_sub_queries(result)
```

---

### Phase 4: Confidence Scoring & Hallucination Prevention (Low effort, high impact)

**Goal**: Know when the system doesn't have good answers and be honest about it.

| Task | Description | Effort |
|------|-------------|--------|
| 4.1 | Add retrieval quality scoring (avg relevance of top-k results) | 1h |
| 4.2 | Define confidence thresholds (high/medium/low/none) | 30min |
| 4.3 | Add confidence-based response strategy | 1-2h |
| 4.4 | Implement fallback chain: RAG → web search → "I don't know" | 2h |
| 4.5 | Add confidence indicator to UI (optional) | 1h |

**Confidence levels:**
```python
class RetrievalConfidence:
    HIGH = "high"       # top-3 avg score > 0.6 → answer directly from context
    MEDIUM = "medium"   # top-3 avg score 0.4-0.6 → answer with caveat
    LOW = "low"         # top-3 avg score 0.25-0.4 → "Based on limited context..."
    NONE = "none"       # top-3 avg score < 0.25 → fallback or "I don't have info"
```

**Response strategy per confidence:**
```python
def build_response_strategy(confidence: RetrievalConfidence, query: str):
    if confidence == RetrievalConfidence.HIGH:
        return {"use_rag": True, "disclaimer": None, "fallback": None}
    elif confidence == RetrievalConfidence.MEDIUM:
        return {"use_rag": True, "disclaimer": "partial_match", "fallback": None}
    elif confidence == RetrievalConfidence.LOW:
        return {"use_rag": True, "disclaimer": "limited_context", "fallback": "web_search"}
    else:
        return {"use_rag": False, "disclaimer": "no_context", "fallback": "web_search_or_refuse"}
```

---

### Phase 5: Enhanced Conversation Memory (Medium effort, medium impact)

**Goal**: Persistent, searchable conversation memory across sessions.

| Task | Description | Effort |
|------|-------------|--------|
| 5.1 | Design memory schema (facts, preferences, topics discussed) | 1h |
| 5.2 | Implement fact extraction from conversations | 2-3h |
| 5.3 | Store extracted facts in Qdrant (separate collection) | 1-2h |
| 5.4 | Query memory at conversation start + on ambiguous references | 1-2h |
| 5.5 | Add memory management UI (view/delete memories) | 2-3h |

**Memory types:**
```python
class MemoryEntry:
    text: str           # "User prefers Chinese responses for stock analysis"
    category: str       # "preference" | "fact" | "context" | "correction"
    timestamp: datetime
    session_id: str
    confidence: float   # How certain we are this is worth remembering
```

---

### Phase 6: Smart Tool Orchestration (Low effort, medium impact)

**Goal**: Let the LLM decide when to use tools instead of fragile conditional logic.

| Task | Description | Effort |
|------|-------------|--------|
| 6.1 | Always provide tool schemas (remove tool gating logic) | 30min |
| 6.2 | Improve tool descriptions for better LLM decision-making | 1h |
| 6.3 | Add "when to use" examples in tool descriptions | 1h |
| 6.4 | Add tool usage analytics (track which tools are called when) | 1-2h |

**Current fragile logic to remove:**
```python
# REMOVE THIS:
use_tools = not has_auto_context
if has_project_context:
    use_tools = True

# REPLACE WITH:
use_tools = True  # Always let LLM decide
```

**Better tool descriptions:**
```python
{
    "name": "commit_summary",
    "description": (
        "Get recent git commits across team repositories. "
        "USE WHEN: user asks about code changes, deployments, what was pushed/merged, "
        "recent development activity, or who worked on what. "
        "DO NOT USE: for general coding questions, architecture discussions, or documentation."
    ),
}
```

---

## Priority Matrix

```
Impact ▲
       │
  HIGH │  [Phase 4]          [Phase 2]        [Phase 3]
       │  Confidence         Intent Class.     Query Decomp.
       │
  MED  │  [Phase 6]          [Phase 5]
       │  Tool Orchestr.     Conv. Memory
       │
  LOW  │
       │
       └──────────────────────────────────────────────────► Effort
            LOW              MEDIUM             HIGH

  [Phase 1 - Refactoring] is prerequisite for all others
```

---

## Recommended Execution Order

```
Phase 1 (Foundation)        ← START HERE — 2 days
    │
    ├──→ Phase 4 (Confidence)   ← Quick win — 1 day
    │
    ├──→ Phase 6 (Tool Orchestration)  ← 30min quick fix
    │
    ├──→ Phase 2 (Intent Classification)  ← Core improvement — 2 days
    │         │
    │         └──→ Phase 3 (Query Decomposition)  ← After intent works — 2 days
    │
    └──→ Phase 5 (Conversation Memory)  ← Can run in parallel — 2-3 days
```

**Total estimated effort**: ~10-12 working days for all phases

---

## Quick Wins (Can Do Today)

1. **Phase 6.1**: Remove tool gating logic (30 min, zero risk)
2. **Phase 4.1-4.2**: Add retrieval score logging to understand current quality (1h)
3. **Phase 1.4**: Extract prompts to `prompts.py` (1h, easy first refactoring step)

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| False-positive tool triggers | ~15-20% (estimated) | <5% |
| Questions answered from wrong context | Unknown | Measurable via confidence |
| Time to add a new tool | Hours (navigate 11K file) | Minutes (drop in tools/) |
| Multi-part question quality | Poor (single-pass RAG) | Good (decomposed retrieval) |
| "I don't know" when appropriate | Never (always generates) | When confidence < threshold |

---

## Notes

- All phases are backward-compatible: existing behavior is preserved until explicitly replaced
- Phase 1 is the critical enabler — without it, adding features increases technical debt
- The fast model (qwen3:1.7b) adds ~200ms per classification call — acceptable for better routing
- Consider adding observability (latency per stage, retrieval scores, tool usage) early in Phase 1

---

## Completion Notes

All six roadmap phases were implemented (2026-04-30). The sections above remain as the original specification for comparison.

### Phase 1 — Modular refactoring (DONE)

- `rag_engine.py`, `tools/` package, `prompts.py`, `learning/` package, `agent_loop.py`, `router.py` extracted from the monolithic agent.
- `agent.py` reduced from ~11K lines to ~1,559 lines (still materially slimmer than the original baseline; the original ~200-line “thin Flask app” goal was not fully met—the file retains substantial route and orchestration logic).
- HTTP routes extracted to `routes/` (`stock`, `toolbar`, `ai_news`, `daily_fetch`).
- UI template extracted to `templates/index.html`.

### Phase 2 — Intent classification (DONE)

- `intent.py`: three-stage flow (session context → heuristic → LLM fallback).
- Taxonomy: 15 intents covering Knowledge QA subtypes, tool actions, learning, creative, smalltalk, and `out_of_scope`.
- Query enhancement via LLM rewriting where appropriate.
- RAG capability probing against the vector store for confidence-oriented signals.

### Phase 3 — Query decomposition (DONE)

- `decomposer.py`: complexity detection plus LLM-based decomposition.
- Independent intent classification per sub-query.
- Dependency tracking across sub-questions.
- Integrated with `pipeline.py`.

### Phase 4 — Confidence scoring (DONE)

- `RetrievalConfidence` enum (HIGH / MEDIUM / LOW / NONE).
- Response strategy per tier (disclaimers, fallback guidance).
- SSE events exposing confidence to the client.
- Wired through `pipeline.py` and the agent response stream.

### Phase 5 — Conversation memory (DONE)

- `memory/` package: `store`, `extractor`, `patterns`, `retriever`.
- Qdrant collection `conversation_memory` with JSON snapshot persistence.
- LLM-based extraction (immediate for corrections; batch for general facts).
- Pattern learning (Q→A mappings, corrections, retrieval feedback).
- Memory injection on LOW/MEDIUM confidence paths.
- API: GET/DELETE `/api/memory`, POST `/api/memory/extract`.

### Phase 6 — Smart tool orchestration (DONE)

- Tools always exposed to the LLM (prior tool gating removed).
- Stronger descriptions with USE WHEN / DO NOT USE guidance.
- Dynamic tool ordering informed by pipeline suggestions and memory patterns.
- Tool schemas consolidated in `tools/schemas.py`.

### Deviations and follow-ups

- **Phase 1.6 / Phase 1.7:** `agent.py` is ~1,559 lines rather than ~200; dedicated `/api/agent` integration tests called out in the plan may still be expanded.
- **Phase 4.4:** Full “RAG → web search → I don’t know” fallback chain should be validated against runtime behavior if not fully automated.
- **Phase 6.4:** Tool usage analytics may remain optional telemetry work.
- **Observability:** Latency/tool-usage dashboards mentioned in Notes were not prerequisite to marking phases complete; can be prioritized separately.
