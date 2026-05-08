"""
Intent classification and query enhancement for the Jarvis RAG agent.

Pipeline: User Query → Enhance → RAG Capability Check → Classify → Route

This module replaces the keyword-matching approach with a two-stage pipeline:
1. Query Enhancement: Rewrite ambiguous/unclear input using the fast LLM
2. Intent Classification: Determine what Jarvis capability best serves the query
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from query_rewrite import SmartRewriteResult, smart_rewrite

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL_FAST = "qwen3:1.7b"


# ---------------------------------------------------------------------------
# Intent taxonomy — aligned with actual Jarvis UI features/menus
# ---------------------------------------------------------------------------
class Intent(str, Enum):
    """All intents Jarvis can handle, mapped to actual UI features."""

    # Core RAG chat (default)
    KNOWLEDGE_QA = "knowledge_qa"           # General Q&A using RAG knowledge base

    # Medavis tooling (toolbar menu)
    JIRA_REPORT = "jira_report"             # Jira tickets, sprint status, team workload
    COMMIT_SUMMARY = "commit_summary"       # Git commits, code changes, who pushed what
    CONFLUENCE_WIKI = "confluence_wiki"      # Confluence wiki search/fetch
    PROJECT_QUERY = "project_query"         # Project dependencies, architecture, impact analysis
    TEAM_ACTIVITY = "team_activity"         # Combined team activity (commits + jira)

    # Usage tools
    EXPLAIN_TOPIC = "explain_topic"         # Deep explanation of a topic (Explain This)
    TREND_ANALYSIS = "trend_analysis"       # Trend analysis across knowledge base
    AI_NEWS_KB = "ai_news_kb"              # AI news knowledge base queries

    # Learning modes (sidebar sessions)
    LEARNING_AI = "learning_ai"             # AI/ML learning session
    LEARNING_ENGLISH_TECH = "learning_english_tech"  # Tech English
    LEARNING_ENGLISH_CASUAL = "learning_english_casual"  # Casual English
    LEARNING_AWS_CERT = "learning_aws_cert"  # AWS AIF-C01 certification
    LEARNING_DEEP_DIVE = "learning_deep_dive"  # Deep dive on a briefing topic

    # Stock analysis
    STOCK_ANALYSIS = "stock_analysis"       # Stock analysis, watchlist, scanning

    # Meta / out-of-scope
    SMALLTALK = "smalltalk"                 # Greetings, meta-questions, casual chat
    OUT_OF_SCOPE = "out_of_scope"           # Things Jarvis genuinely cannot do


@dataclass
class IntentResult:
    """Result of intent classification."""
    intent: Intent
    confidence: float = 0.0
    enhanced_query: str = ""
    original_query: str = ""
    reasoning: str = ""
    suggested_tools: list[str] = field(default_factory=list)
    is_ambiguous: bool = False
    rag_confidence: Optional[str] = None  # RetrievalConfidence value or None if not checked
    rag_score: float = 0.0
    rewrite_result: Optional[SmartRewriteResult] = None


# ---------------------------------------------------------------------------
# Jarvis capability description (used as context for the LLM classifier)
# ---------------------------------------------------------------------------
JARVIS_CAPABILITIES = """Jarvis is an AI assistant for the medavis P4M development team. It can:

1. KNOWLEDGE Q&A: Answer questions using a RAG knowledge base containing:
   - Daily AI/ML briefings and research papers
   - Confluence wiki pages from the team
   - Jira tickets and sprint data
   - Project documentation and code analysis
   - Custom documents and learning guides

2. JIRA & SPRINT: Query current Jira tickets, sprint status, team workload, open issues

3. GIT COMMITS: Show recent git commits across team repositories, who pushed what, code changes

4. CONFLUENCE WIKI: Search and retrieve team wiki pages

5. PROJECT INTELLIGENCE: Query project dependency graphs, architecture, impact analysis,
   cross-project relationships for medavis Java/WildFly/Vaadin projects

6. TREND ANALYSIS: Analyze trends across the knowledge base over time

7. AI NEWS: Query and summarize AI industry news from the knowledge base

8. LEARNING MODES: Specialized teaching sessions for AI/ML, English, AWS certification

9. STOCK ANALYSIS: A-share stock analysis, watchlists, scanning, recommendations

10. IMAGE ANALYSIS: Analyze uploaded images using vision capabilities

Things Jarvis CANNOT do:
- Execute arbitrary code or access the internet in real-time
- Modify files on the filesystem
- Send emails or messages
- Access databases directly
- Perform actions outside its defined tools"""


# ---------------------------------------------------------------------------
# Query Enhancement
# ---------------------------------------------------------------------------
def enhance_query(query: str, history: list[dict] | None = None) -> tuple[str, SmartRewriteResult]:
    """Smart query rewrite: alias expansion + domain-aware LLM rewrite.

    Delegates to query_rewrite.smart_rewrite(). Returns both the effective
    query string and the full SmartRewriteResult for pipeline visibility.
    """
    rewrite = smart_rewrite(query, history)
    return rewrite.effective_query, rewrite


# ---------------------------------------------------------------------------
# Intent Classification
# ---------------------------------------------------------------------------
def classify_intent(query: str, enhanced_query: str = "",
                    session_type: str | None = None,
                    history: list[dict] | None = None) -> IntentResult:
    """Classify user intent using fast LLM + heuristic fallback.

    Pipeline:
    1. Check if session_type already determines intent (learning modes)
    2. Run keyword heuristics for obvious cases (fast, no LLM call)
    3. Fall back to LLM classification for ambiguous queries

    Args:
        query: The original user query.
        enhanced_query: The LLM-enhanced query (if different from original).
        session_type: The current session type (from router.py).
        history: Conversation history for context.
    """
    effective_query = enhanced_query or query

    # Stage 1: Session-based routing (deterministic, no LLM needed)
    if session_type:
        session_intent = _session_to_intent(session_type)
        if session_intent:
            return IntentResult(
                intent=session_intent,
                confidence=1.0,
                enhanced_query=effective_query,
                original_query=query,
                reasoning=f"Determined by session type: {session_type}",
            )

    # Stage 2: Keyword heuristics (fast, high-confidence for obvious cases)
    heuristic = _keyword_heuristic(effective_query)
    if heuristic and heuristic.confidence >= 0.8:
        return heuristic

    # Stage 3: LLM-based classification
    return _llm_classify(query, effective_query, history)


def _session_to_intent(session_type: str) -> Optional[Intent]:
    """Map a known session type to its intent."""
    mapping = {
        "ai_learning": Intent.LEARNING_AI,
        "english_learning": Intent.LEARNING_ENGLISH_TECH,
        "casual_english": Intent.LEARNING_ENGLISH_CASUAL,
        "aws_cert": Intent.LEARNING_AWS_CERT,
        "deep_dive": Intent.LEARNING_DEEP_DIVE,
    }
    return mapping.get(session_type)


def _keyword_heuristic(query: str) -> Optional[IntentResult]:
    """Fast keyword-based classification for obvious intents."""
    q = query.lower()

    # Jira / sprint / tickets
    jira_kw = ("jira", "ticket", "sprint", "backlog", "open issue", "task status",
               "story point", "kanban", "scrum")
    if any(kw in q for kw in jira_kw):
        return IntentResult(
            intent=Intent.JIRA_REPORT,
            confidence=0.9,
            enhanced_query=query,
            original_query=query,
            reasoning=f"Jira keyword detected",
            suggested_tools=["jira_report"],
        )

    # Git / commits
    git_kw = ("commit", "git log", "push", "merge", "code change",
              "repository activity", "pull request", "branch", "deployed",
              "what did .* push", "who committed")
    if any(kw in q for kw in git_kw) or re.search(r"\b(push|merge|commit)\w*\b", q):
        return IntentResult(
            intent=Intent.COMMIT_SUMMARY,
            confidence=0.9,
            enhanced_query=query,
            original_query=query,
            reasoning=f"Git/commit keyword detected",
            suggested_tools=["commit_summary"],
        )

    # Project / architecture / dependencies
    project_kw = ("project dependency", "depends on", "impact analysis",
                  "architecture of", "what uses", "project graph")
    if any(kw in q for kw in project_kw):
        return IntentResult(
            intent=Intent.PROJECT_QUERY,
            confidence=0.85,
            enhanced_query=query,
            original_query=query,
            reasoning=f"Project/architecture keyword detected",
            suggested_tools=["project_query"],
        )

    # Stock analysis (Chinese keywords common)
    stock_kw = ("stock", "股票", "自选股", "watchlist", "scanner",
                "推荐", "行情", "k线", "涨跌", "分析", "预测")
    if any(kw in q for kw in stock_kw):
        return IntentResult(
            intent=Intent.STOCK_ANALYSIS,
            confidence=0.9,
            enhanced_query=query,
            original_query=query,
            reasoning=f"Stock analysis keyword detected",
        )

    # Smalltalk (greetings, meta)
    smalltalk_patterns = [
        r"^(hi|hello|hey|good morning|good evening|你好|早上好)\s*[!.]?$",
        r"^(thanks|thank you|谢谢|好的)\s*[!.]?$",
        r"^who are you\??$",
        r"^what can you do\??$",
    ]
    for pattern in smalltalk_patterns:
        if re.match(pattern, q, re.IGNORECASE):
            return IntentResult(
                intent=Intent.SMALLTALK,
                confidence=0.95,
                enhanced_query=query,
                original_query=query,
                reasoning="Smalltalk pattern matched",
            )

    return None


def _llm_classify(query: str, enhanced_query: str,
                  history: list[dict] | None = None) -> IntentResult:
    """Use the fast LLM to classify intent when heuristics are insufficient."""

    intent_options = "\n".join([
        "- knowledge_qa: General question answerable from AI briefings, wiki, docs, or team knowledge",
        "- jira_report: About Jira tickets, sprints, team workload, task status",
        "- commit_summary: About git commits, code changes, who pushed/merged what",
        "- confluence_wiki: About Confluence wiki pages, team documentation",
        "- project_query: About project dependencies, architecture, impact analysis",
        "- team_activity: About overall team activity (commits + tickets combined)",
        "- explain_topic: Requesting a deep explanation or tutorial on a specific topic",
        "- trend_analysis: Analyzing trends over time in the knowledge base",
        "- ai_news_kb: About recent AI industry news, research papers, tech developments",
        "- stock_analysis: About stock market, A-shares, investment analysis",
        "- smalltalk: Greetings, thanks, or casual non-task conversation",
        "- out_of_scope: Request that Jarvis cannot fulfill (e.g., sending emails, browsing live web)",
    ])

    try:
        import requests as _req
        resp = _req.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL_FAST,
                "messages": [
                    {"role": "system", "content": (
                        "You classify user queries for an AI assistant called Jarvis. "
                        "Jarvis is a RAG-based assistant for a Java development team. "
                        "It has a knowledge base of AI briefings, Confluence wiki, Jira data, "
                        "project docs, and team activity.\n\n"
                        f"Available intents:\n{intent_options}\n\n"
                        "Output ONLY a JSON object: "
                        "{\"intent\": \"<intent_name>\", \"confidence\": 0.0-1.0, "
                        "\"reasoning\": \"<brief reason>\"}"
                    )},
                    {"role": "user", "content": enhanced_query},
                ],
                "stream": False,
                "think": False,
                "options": {"num_predict": 100, "num_ctx": 512},
            },
            timeout=10,
        )
        raw = resp.json().get("message", {}).get("content", "").strip()
        json_match = re.search(r"\{[^}]+\}", raw)
        if json_match:
            result = json.loads(json_match.group())
            intent_str = result.get("intent", "knowledge_qa")
            confidence = float(result.get("confidence", 0.5))
            reasoning = result.get("reasoning", "")

            try:
                intent = Intent(intent_str)
            except ValueError:
                intent = Intent.KNOWLEDGE_QA
                reasoning = f"Unknown intent '{intent_str}', defaulting to knowledge_qa"

            return IntentResult(
                intent=intent,
                confidence=confidence,
                enhanced_query=enhanced_query,
                original_query=query,
                reasoning=reasoning,
                suggested_tools=_intent_to_tools(intent),
            )
    except Exception as e:
        logger.debug("LLM classification failed: %s", e)

    return IntentResult(
        intent=Intent.KNOWLEDGE_QA,
        confidence=0.3,
        enhanced_query=enhanced_query,
        original_query=query,
        reasoning="LLM classification failed, defaulting to knowledge_qa",
        is_ambiguous=True,
    )


def _intent_to_tools(intent: Intent) -> list[str]:
    """Map an intent to its suggested tools."""
    mapping = {
        Intent.JIRA_REPORT: ["jira_report"],
        Intent.COMMIT_SUMMARY: ["commit_summary"],
        Intent.CONFLUENCE_WIKI: ["confluence_search"],
        Intent.PROJECT_QUERY: ["project_query"],
        Intent.TEAM_ACTIVITY: ["commit_summary", "jira_report"],
        Intent.KNOWLEDGE_QA: ["rag_search"],
        Intent.AI_NEWS_KB: ["briefing_search"],
        Intent.EXPLAIN_TOPIC: ["rag_search"],
        Intent.TREND_ANALYSIS: ["rag_search"],
    }
    return mapping.get(intent, [])


# ---------------------------------------------------------------------------
# RAG Capability Check
# ---------------------------------------------------------------------------
class RetrievalConfidence(str, Enum):
    """How confident we are that RAG retrieval can answer the query."""
    HIGH = "high"       # Top-3 avg score > 0.5 — answer directly from context
    MEDIUM = "medium"   # Top-3 avg score 0.35-0.5 — answer with caveat
    LOW = "low"         # Top-3 avg score 0.2-0.35 — limited context disclaimer
    NONE = "none"       # Top-3 avg score < 0.2 — fall back or refuse


def check_rag_capability(query: str) -> tuple[RetrievalConfidence, float]:
    """Quick probe of the RAG store to see if we have relevant content.

    Does a fast vector search with minimal top_k to estimate retrieval quality.
    Returns (confidence_level, avg_score).
    """
    try:
        from rag_engine import vector_search
        results = vector_search(query, top_k=3, min_score=0.1)
        if not results:
            return RetrievalConfidence.NONE, 0.0

        avg_score = sum(r.get("score", 0) for r in results) / len(results)

        if avg_score > 0.5:
            return RetrievalConfidence.HIGH, avg_score
        elif avg_score > 0.35:
            return RetrievalConfidence.MEDIUM, avg_score
        elif avg_score > 0.2:
            return RetrievalConfidence.LOW, avg_score
        else:
            return RetrievalConfidence.NONE, avg_score
    except Exception as e:
        logger.debug("RAG capability check failed: %s", e)
        return RetrievalConfidence.NONE, 0.0


# ---------------------------------------------------------------------------
# Public pipeline function
# ---------------------------------------------------------------------------
def process_query(query: str, session_type: str | None = None,
                  history: list[dict] | None = None) -> IntentResult:
    """Full query processing pipeline: enhance → classify.

    This is the main entry point for the intent system.

    Args:
        query: Raw user input.
        session_type: Current session type (from router.py RouteResult).
        history: Conversation history.

    Returns:
        IntentResult with intent, enhanced query, confidence, and suggested tools.
    """
    enhanced, rewrite_result = enhance_query(query, history)

    result = classify_intent(
        query=query,
        enhanced_query=enhanced,
        session_type=session_type,
        history=history,
    )

    if not result.enhanced_query:
        result.enhanced_query = enhanced
    result.original_query = query
    result.rewrite_result = rewrite_result

    # RAG capability check for knowledge-based intents
    rag_intents = {
        Intent.KNOWLEDGE_QA, Intent.EXPLAIN_TOPIC, Intent.AI_NEWS_KB,
        Intent.TREND_ANALYSIS, Intent.CONFLUENCE_WIKI,
    }
    if result.intent in rag_intents:
        rag_conf, rag_score = check_rag_capability(enhanced)
        result.rag_confidence = rag_conf.value
        result.rag_score = rag_score

    return result
