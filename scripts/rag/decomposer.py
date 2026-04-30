"""
Query decomposition for the Jarvis RAG agent.

Detects complex multi-part questions and breaks them into independent
sub-queries, each with its own intent classification and retrieval strategy.

Pipeline: Enhanced Query → Complexity Check → Decompose → Classify Each → Merge
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from intent import Intent, IntentResult, classify_intent

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL_FAST = "qwen3:1.7b"


@dataclass
class SubQuery:
    """A single sub-question extracted from a complex query."""
    text: str
    intent: Optional[IntentResult] = None
    depends_on: Optional[int] = None
    is_synthesis: bool = False


@dataclass
class DecompositionResult:
    """Result of query decomposition."""
    is_complex: bool = False
    sub_queries: list[SubQuery] = field(default_factory=list)
    original_query: str = ""
    reasoning: str = ""


def is_complex_query(query: str) -> bool:
    """Heuristic: does this query likely contain multiple sub-questions?

    Signals for complexity:
    - Conjunctions joining distinct actions ("and then", "also", "as well as")
    - Multiple question words
    - Comparison/relationship requests between different data sources
    """
    q = query.lower()

    multi_action = [
        " and ", " also ", " as well ", " plus ", " additionally ",
        " then ", " after that ", " meanwhile ", " together with ",
    ]
    conjunction_count = sum(1 for m in multi_action if m in q)
    if conjunction_count == 0:
        return False

    question_words = re.findall(r'\b(what|who|how|when|where|which|show|list|get|find)\b', q)
    if len(question_words) >= 2 and conjunction_count >= 1:
        return True

    cross_source_pairs = [
        (r'\b(commit|push|merge|git)\b', r'\b(jira|ticket|sprint|issue)\b'),
        (r'\b(commit|push|merge|git)\b', r'\b(confluence|wiki|page)\b'),
        (r'\b(jira|ticket|sprint)\b', r'\b(confluence|wiki|page)\b'),
        (r'\b(project|dependency)\b', r'\b(commit|push|jira|ticket)\b'),
    ]
    for pat_a, pat_b in cross_source_pairs:
        if re.search(pat_a, q) and re.search(pat_b, q):
            return True

    action_verbs = re.findall(r'\b(show|get|find|list|check|compare|analyze|summarize)\b', q)
    if len(action_verbs) >= 2 and conjunction_count >= 1:
        return True

    return False


def decompose_query(query: str, history: list[dict] | None = None) -> DecompositionResult:
    """Break a complex query into independent sub-questions.

    Uses the fast LLM to intelligently decompose. Falls back to the original
    query as a single SubQuery if decomposition fails or the query is simple.
    """
    if not is_complex_query(query):
        return DecompositionResult(
            is_complex=False,
            sub_queries=[SubQuery(text=query)],
            original_query=query,
            reasoning="Single-intent query, no decomposition needed",
        )

    try:
        import requests as _req
        resp = _req.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL_FAST,
                "messages": [
                    {"role": "system", "content": (
                        "You decompose complex user questions into simpler sub-questions. "
                        "Each sub-question should be answerable independently using a single data source. "
                        "If a sub-question requires combining results from earlier sub-questions, "
                        'mark it with "depends_on" pointing to the indices of prerequisite sub-questions.\n\n'
                        "Output ONLY a JSON array:\n"
                        '[{"text": "sub-question text", "depends_on": null}, '
                        '{"text": "synthesis question", "depends_on": [0, 1]}]'
                    )},
                    {"role": "user", "content": f"Decompose this question into 2-4 sub-questions:\n\n{query}"},
                ],
                "stream": False,
                "think": False,
                "options": {"num_predict": 300, "num_ctx": 512},
            },
            timeout=15,
        )
        raw = resp.json().get("message", {}).get("content", "").strip()

        json_match = re.search(r'\[.*\]', raw, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            sub_queries = []
            for i, item in enumerate(parsed[:4]):
                text = item.get("text", "").strip()
                if not text:
                    continue
                depends = item.get("depends_on")
                is_synth = depends is not None and depends != []
                sub_queries.append(SubQuery(
                    text=text,
                    depends_on=depends if is_synth else None,
                    is_synthesis=is_synth,
                ))

            if len(sub_queries) >= 2:
                return DecompositionResult(
                    is_complex=True,
                    sub_queries=sub_queries,
                    original_query=query,
                    reasoning=f"Decomposed into {len(sub_queries)} sub-queries",
                )
    except Exception as e:
        logger.debug("Query decomposition failed: %s", e)

    return DecompositionResult(
        is_complex=False,
        sub_queries=[SubQuery(text=query)],
        original_query=query,
        reasoning="Decomposition failed or produced insufficient sub-queries",
    )


def classify_sub_queries(result: DecompositionResult,
                         session_type: str | None = None,
                         history: list[dict] | None = None) -> DecompositionResult:
    """Classify the intent of each sub-query independently."""
    for sq in result.sub_queries:
        if sq.is_synthesis:
            sq.intent = IntentResult(
                intent=Intent.KNOWLEDGE_QA,
                confidence=0.8,
                enhanced_query=sq.text,
                original_query=sq.text,
                reasoning="Synthesis sub-query (combines other sub-query results)",
            )
        else:
            sq.intent = classify_intent(
                query=sq.text,
                enhanced_query=sq.text,
                session_type=session_type,
                history=history,
            )
    return result


def get_sub_query_tools(result: DecompositionResult) -> list[str]:
    """Collect all suggested tools from all sub-queries (deduplicated)."""
    seen = set()
    tools = []
    for sq in result.sub_queries:
        if sq.intent:
            for t in sq.intent.suggested_tools:
                if t not in seen:
                    seen.add(t)
                    tools.append(t)
    return tools
