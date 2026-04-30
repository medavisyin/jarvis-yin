"""
Query processing pipeline orchestrator for the Jarvis RAG agent.

Chains together: routing → enhancement → classification → decomposition → generation.
This is the single entry point that api_agent() calls to handle a user query.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

from decomposer import (
    DecompositionResult,
    SubQuery,
    classify_sub_queries,
    decompose_query,
    get_sub_query_tools,
)
from intent import (
    Intent,
    IntentResult,
    RetrievalConfidence,
    process_query,
)
from memory.retriever import query_memories_for_context, get_tool_suggestions_from_memory
from prompts import (
    SYSTEM_PROMPT_COMPACT,
    SYSTEM_PROMPT_FULL,
    SYSTEM_PROMPT_PROJECT_ADDON,
)
from router import RouteResult, route_session

logger = logging.getLogger(__name__)


@dataclass
class PipelineContext:
    """Full context built by the pipeline before LLM generation."""
    query: str
    effective_query: str
    rag_query: Optional[str]
    system_prompt: Optional[str]
    route: RouteResult
    intent_result: IntentResult
    decomposition: Optional[DecompositionResult] = None
    web_refs: str = ""
    image_b64: Optional[str] = None
    history: list[dict] = field(default_factory=list)
    memory_tools: list[str] = field(default_factory=list)

    @property
    def is_decomposed(self) -> bool:
        return self.decomposition is not None and self.decomposition.is_complex

    @property
    def all_suggested_tools(self) -> list[str]:
        """All tools suggested across decomposed sub-queries, intent, and memory."""
        if self.is_decomposed:
            tools = get_sub_query_tools(self.decomposition)
        else:
            tools = list(self.intent_result.suggested_tools)
        tools.extend(t for t in self.memory_tools if t not in tools)
        return tools


def handle_query(query: str, session_id: str = "",
                 history: list[dict] | None = None,
                 image_b64: str | None = None,
                 load_session_fn=None) -> PipelineContext:
    """Run the full query processing pipeline.

    This is the main orchestrator. It:
    1. Routes the session (determines learning mode, prompt)
    2. Enhances and classifies the query (intent detection)
    3. Decomposes complex multi-part queries into sub-questions
    4. Builds the pipeline context for downstream generation

    The actual LLM generation (run_agent) is NOT called here — the caller
    (api_agent) handles that using the returned PipelineContext.

    Args:
        query: Raw user query text.
        session_id: Session UUID (may be a learning session).
        history: Conversation history.
        image_b64: Optional base64-encoded image.
        load_session_fn: Function to load session data (for deep_dive detection).

    Returns:
        PipelineContext with all information needed for generation.
    """
    if history is None:
        history = []

    # Step 1: Route the session
    route = route_session(session_id, load_session_fn=load_session_fn)

    # Step 2: Process query (enhance + classify + RAG check)
    intent_result = process_query(
        query=query,
        session_type=route.session_type,
        history=history,
    )

    # Step 3: Determine effective query and system prompt
    effective_query = intent_result.enhanced_query or query
    rag_query = None
    system_prompt = route.learning_prompt

    # Step 3b: Augment with conversation memory on low/medium confidence
    memory_context = ""
    memory_tools: list[str] = []
    if intent_result.rag_confidence in (
        RetrievalConfidence.LOW.value, RetrievalConfidence.MEDIUM.value
    ):
        try:
            memory_context = query_memories_for_context(effective_query)
            memory_tools = get_tool_suggestions_from_memory(effective_query)
            if memory_context:
                effective_query = f"{memory_context}\n\n{effective_query}"
                logger.info("Pipeline: injected memory context (%d chars)", len(memory_context))
        except Exception as e:
            logger.debug("Memory retrieval skipped: %s", e)

    # Step 4: Decompose complex queries (non-learning only)
    decomposition = None
    if not route.is_learning:
        decomposition = decompose_query(effective_query, history)
        if decomposition.is_complex:
            decomposition = classify_sub_queries(
                decomposition, session_type=route.session_type, history=history,
            )
            effective_query = _build_decomposed_prompt(decomposition, effective_query)
            logger.info(
                "Pipeline: decomposed into %d sub-queries: %s",
                len(decomposition.sub_queries),
                [sq.text[:40] for sq in decomposition.sub_queries],
            )
        else:
            effective_query = _apply_intent_strategy(intent_result, query, effective_query)

    ctx = PipelineContext(
        query=query,
        effective_query=effective_query,
        rag_query=rag_query,
        system_prompt=system_prompt,
        route=route,
        intent_result=intent_result,
        decomposition=decomposition,
        image_b64=image_b64,
        history=history,
        memory_tools=memory_tools,
    )

    logger.info(
        "Pipeline: query=%r → intent=%s (%.2f) | rag_conf=%s (%.3f) | decomposed=%s | enhanced=%r",
        query[:50],
        intent_result.intent.value,
        intent_result.confidence,
        intent_result.rag_confidence or "n/a",
        intent_result.rag_score,
        ctx.is_decomposed,
        effective_query[:50] if effective_query != query else "(unchanged)",
    )

    return ctx


def _build_decomposed_prompt(decomposition: DecompositionResult, fallback: str) -> str:
    """Build a structured prompt that instructs the LLM to answer each sub-question.

    The LLM sees all sub-questions with dependency markers so it can plan
    tool calls and synthesis steps accordingly.
    """
    if not decomposition.sub_queries:
        return fallback

    parts = [
        "This question has multiple parts. Please address each sub-question "
        "and then provide a combined answer:\n"
    ]
    for i, sq in enumerate(decomposition.sub_queries):
        prefix = f"Part {i + 1}"
        if sq.is_synthesis:
            dep_refs = ", ".join(f"Part {d + 1}" for d in (sq.depends_on or []))
            prefix += f" (combines {dep_refs})"
        if sq.intent and sq.intent.suggested_tools:
            tool_hint = f" [use: {', '.join(sq.intent.suggested_tools)}]"
        else:
            tool_hint = ""
        parts.append(f"  {prefix}: {sq.text}{tool_hint}")

    parts.append(
        "\nAnswer each part, then synthesize a final combined response."
    )
    return "\n".join(parts)


def _apply_intent_strategy(intent_result: IntentResult, original: str, enhanced: str) -> str:
    """Apply intent-specific query transformations for non-learning sessions.

    Strategy depends on both intent type and RAG confidence level:
    - Tool intents: pass through (tools handle their own data)
    - High RAG confidence: answer directly from context
    - Medium RAG confidence: answer with advisory caveat
    - Low RAG confidence: add explicit caveat + encourage tool use
    - No RAG confidence: instruct honesty, may refuse
    """
    intent = intent_result.intent
    rag_conf = intent_result.rag_confidence

    tool_intents = {Intent.JIRA_REPORT, Intent.COMMIT_SUMMARY,
                    Intent.PROJECT_QUERY, Intent.TEAM_ACTIVITY}
    if intent in tool_intents:
        return enhanced

    if intent == Intent.SMALLTALK or intent == Intent.OUT_OF_SCOPE:
        return enhanced

    if rag_conf == RetrievalConfidence.HIGH.value:
        return enhanced

    if rag_conf == RetrievalConfidence.MEDIUM.value:
        return (
            f"{enhanced}\n\n"
            f"[SYSTEM NOTE: The retrieved context is partially relevant. "
            f"Answer using what is available, but note if key details are missing.]"
        )

    if rag_conf == RetrievalConfidence.LOW.value:
        return (
            f"{enhanced}\n\n"
            f"[SYSTEM NOTE: Limited relevant context was found for this query. "
            f"Use what is available but clearly indicate gaps. "
            f"If appropriate, suggest using a specific tool (e.g., rag_search with different terms).]"
        )

    if rag_conf == RetrievalConfidence.NONE.value:
        return (
            f"{enhanced}\n\n"
            f"[SYSTEM NOTE: The knowledge base has no relevant content for this query. "
            f"If you cannot answer from the provided context, say so honestly. "
            f"Do NOT fabricate information. Suggest what the user could try instead.]"
        )

    return enhanced


@dataclass
class ResponseStrategy:
    """Confidence-based response strategy for the SSE stream."""
    use_rag: bool = True
    confidence_level: str = "unknown"
    disclaimer: Optional[str] = None
    suggest_web_search: bool = False


def build_response_strategy(intent_result: IntentResult) -> ResponseStrategy:
    """Build a structured response strategy based on intent + RAG confidence.

    Used by api_agent() to decide what SSE events to emit.
    """
    rag_conf = intent_result.rag_confidence
    intent = intent_result.intent

    tool_intents = {Intent.JIRA_REPORT, Intent.COMMIT_SUMMARY,
                    Intent.PROJECT_QUERY, Intent.TEAM_ACTIVITY}
    if intent in tool_intents:
        return ResponseStrategy(
            use_rag=True,
            confidence_level="tool_action",
        )

    if rag_conf == RetrievalConfidence.HIGH.value:
        return ResponseStrategy(use_rag=True, confidence_level="high")

    if rag_conf == RetrievalConfidence.MEDIUM.value:
        return ResponseStrategy(
            use_rag=True,
            confidence_level="medium",
            disclaimer="Based on partially matching context — some details may be approximate.",
        )

    if rag_conf == RetrievalConfidence.LOW.value:
        return ResponseStrategy(
            use_rag=True,
            confidence_level="low",
            disclaimer="Based on limited available context — some details may be incomplete.",
            suggest_web_search=True,
        )

    if rag_conf == RetrievalConfidence.NONE.value:
        return ResponseStrategy(
            use_rag=False,
            confidence_level="none",
            disclaimer=None,
            suggest_web_search=True,
        )

    return ResponseStrategy(use_rag=True, confidence_level="unknown")


def get_response_disclaimer(intent_result: IntentResult) -> Optional[str]:
    """Generate a user-facing disclaimer based on RAG confidence."""
    strategy = build_response_strategy(intent_result)
    return strategy.disclaimer


def get_confidence_event(intent_result: IntentResult) -> Optional[dict]:
    """Generate an SSE confidence event for the UI.

    Returns a dict ready to be JSON-serialized and sent as an SSE event,
    or None if no confidence info is available.
    """
    strategy = build_response_strategy(intent_result)
    if strategy.confidence_level == "unknown":
        return None

    return {
        "type": "confidence",
        "level": strategy.confidence_level,
        "score": round(intent_result.rag_score, 3),
        "intent": intent_result.intent.value,
        "suggest_web_search": strategy.suggest_web_search,
    }
