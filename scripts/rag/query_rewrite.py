"""
Smart query rewriting for Jarvis RAG — unified alias expansion + LLM rewrite.

Replaces the scattered rewrite logic from intent.py (enhance_query) and
rag_engine.py (rewrite_query) with a single two-layer pipeline:

  Layer 1: Domain alias expansion (rule-based, ~0ms)
  Layer 2: Domain-aware LLM rewrite (qwen3:1.7b, ~200ms)

Usage:
    from query_rewrite import smart_rewrite
    result = smart_rewrite("admin project architecture", history=[...])
    # result.rewritten  -> "admin-app project architecture and dependencies"
    # result.aliases    -> [{"original": "admin", "expanded": "admin-app", ...}]
"""

import difflib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL_FAST = "qwen3:1.7b"

# ---------------------------------------------------------------------------
# Domain alias registry
# ---------------------------------------------------------------------------

PROJECT_ALIASES: dict[str, str] = {
    "admin": "admin-app",
    "admin project": "admin-app",
    "admin application": "admin-app",
    "p4m": "P4M Next",
    "p4m next": "P4M Next",
    "core": "core-framework",
    "core fw": "core-framework",
    "vaadin": "vaadin-ui",
    "vaadin ui": "vaadin-ui",
    "b4m": "b4m.next",
    "b4m next": "b4m.next",
    "app server": "applicationserver",
    "appserver": "applicationserver",
    "application server": "applicationserver",
    "apache": "apache-dist",
    "comm stack": "communication-stack",
    "communication": "communication-stack",
    "identity": "identityserver",
    "idserver": "identityserver",
    "kc": "keycloak",
    "gateway": "local-gateway",
    "local gw": "local-gateway",
    "gw plugins": "local-gateway-plugins",
    "gateway plugins": "local-gateway-plugins",
    "sms": "sms-service",
    "sms client": "sms-service-client",
    "teleradiology": "teleradiology-cloud-backend",
    "tele backend": "teleradiology-cloud-backend",
    "ris dashboard": "ris-utilization-dashboard",
    "ris util": "ris-utilization-dashboard",
    "aws infra": "aws-infra-p4m-eks",
    "eks": "aws-infra-p4m-eks",
}

TECH_ALIASES: dict[str, str] = {
    "dicom": "DICOM/dcm4chee",
    "dcm": "dcm4chee",
    "fhir": "FHIR/HL7",
    "hl7": "HL7/FHIR",
    "ris": "RIS (Radiology Information System)",
    "pacs": "PACS (Picture Archiving)",
    "spring": "Spring Boot/Framework",
    "sb": "Spring Boot",
    "k8s": "Kubernetes",
    "kube": "Kubernetes",
    "tf": "Terraform",
    "gh": "GitHub",
    "ci": "CI/CD pipeline",
    "cd": "CI/CD pipeline",
    "llm": "Large Language Model (LLM)",
    "rag": "RAG (Retrieval Augmented Generation)",
    "ml": "machine learning",
    "dl": "deep learning",
    "genai": "Generative AI",
    "gen ai": "Generative AI",
    "openai": "OpenAI",
    "gpt": "GPT (OpenAI)",
}

TEAM_ALIASES: dict[str, str] = {
    "jan": "Jan Loeffler",
    "jan loeffler": "Jan Loeffler",
    "raymond": "Rong Yin",
    "rong": "Rong Yin",
    "charlotte": "Charlotte Jiang",
    "christoph": "Christoph Scheben",
    "tobias": "Tobias Troesch",
}

# Combined for fuzzy matching (keys from all registries)
_ALL_ALIAS_KEYS: list[str] = []


def _rebuild_alias_keys() -> None:
    global _ALL_ALIAS_KEYS
    _ALL_ALIAS_KEYS = sorted(
        set(PROJECT_ALIASES) | set(TECH_ALIASES) | set(TEAM_ALIASES),
        key=len, reverse=True,
    )


_rebuild_alias_keys()


# ---------------------------------------------------------------------------
# Auto-discover project names from project graph
# ---------------------------------------------------------------------------
_project_graph_cache: dict = {}
_project_graph_mtime: float = 0.0


def _load_project_names() -> dict[str, str]:
    """Load project names from the project graph and build alias entries."""
    global _project_graph_cache, _project_graph_mtime

    try:
        from config import PROJECT_GRAPH_PATH
        if not os.path.isfile(PROJECT_GRAPH_PATH):
            return {}
        mtime = os.path.getmtime(PROJECT_GRAPH_PATH)
        if mtime == _project_graph_mtime and _project_graph_cache:
            return _project_graph_cache

        with open(PROJECT_GRAPH_PATH, "r", encoding="utf-8") as f:
            graph = json.load(f)

        auto_aliases: dict[str, str] = {}
        for pname in graph.get("projects", {}):
            name_lower = pname.lower()
            auto_aliases[name_lower] = pname
            no_dash = name_lower.replace("-", " ")
            if no_dash != name_lower:
                auto_aliases[no_dash] = pname
            parts = name_lower.split("-")
            if len(parts) >= 2:
                abbrev = "".join(p[0] for p in parts if p)
                if len(abbrev) >= 2 and abbrev not in TECH_ALIASES:
                    auto_aliases[abbrev] = pname

        _project_graph_cache = auto_aliases
        _project_graph_mtime = mtime
        return auto_aliases
    except Exception as e:
        logger.debug("Failed to load project graph for aliases: %s", e)
        return {}


# ---------------------------------------------------------------------------
# Dataclass for rewrite result
# ---------------------------------------------------------------------------
@dataclass
class AliasMatch:
    """One alias that was matched and expanded."""
    original: str
    expanded: str
    alias_type: str       # "project", "tech", or "team"
    fuzzy: bool = False   # True if matched via fuzzy matching


@dataclass
class SmartRewriteResult:
    """Full result of the smart rewrite pipeline."""
    original: str
    alias_expanded: Optional[str] = None
    rewritten: Optional[str] = None
    aliases: list[AliasMatch] = field(default_factory=list)
    skipped_llm: bool = False

    @property
    def effective_query(self) -> str:
        """Best query to use for RAG search."""
        return self.rewritten or self.alias_expanded or self.original

    @property
    def was_rewritten(self) -> bool:
        return (self.alias_expanded is not None and self.alias_expanded != self.original) or \
               (self.rewritten is not None and self.rewritten != (self.alias_expanded or self.original))

    def to_sse_event(self) -> Optional[dict]:
        """Build an SSE event dict for the frontend pipeline box."""
        if not self.was_rewritten:
            return None
        return {
            "type": "query_rewrite",
            "original": self.original,
            "alias_expanded": self.alias_expanded,
            "rewritten": self.rewritten,
            "aliases": [
                {"original": a.original, "expanded": a.expanded,
                 "type": a.alias_type, "fuzzy": a.fuzzy}
                for a in self.aliases
            ],
        }


# ---------------------------------------------------------------------------
# Layer 1: Domain alias expansion
# ---------------------------------------------------------------------------

def expand_domain_aliases(query: str, fuzzy_threshold: float = 0.75) -> tuple[str, list[AliasMatch]]:
    """Expand domain-specific aliases in the query.

    Tries exact match first (longest alias wins), then fuzzy matching.
    Prevents overlapping replacements: once a span is matched by a longer
    alias, shorter aliases covering any part of that span are skipped.
    Returns (expanded_query, list_of_matched_aliases).
    """
    graph_aliases = _load_project_names()

    all_aliases = {}
    for k, v in PROJECT_ALIASES.items():
        all_aliases[k] = (v, "project")
    for k, v in graph_aliases.items():
        if k not in all_aliases:
            all_aliases[k] = (v, "project")
    for k, v in TECH_ALIASES.items():
        all_aliases[k] = (v, "tech")
    for k, v in TEAM_ALIASES.items():
        all_aliases[k] = (v, "team")

    q_lower = query.lower()
    matches: list[AliasMatch] = []

    # Longest-first matching to prevent overlap
    sorted_keys = sorted(all_aliases.keys(), key=len, reverse=True)

    # Collect all replacements first (position-based), then apply
    replacements: list[tuple[int, int, str, str, str, str]] = []  # (start, end, alias_key, expanded_val, alias_type)
    consumed: set[int] = set()

    for alias_key in sorted_keys:
        expanded_val, alias_type = all_aliases[alias_key]
        pattern = r'\b' + re.escape(alias_key) + r'\b'
        for m in re.finditer(pattern, q_lower):
            span = set(range(m.start(), m.end()))
            if span & consumed:
                continue
            consumed |= span
            replacements.append((m.start(), m.end(), alias_key, expanded_val, alias_type))

    if replacements:
        # Sort by position for correct offset-adjusted replacement
        replacements.sort(key=lambda x: x[0])
        expanded = query
        offset = 0
        for start, end, alias_key, expanded_val, alias_type in replacements:
            adj_start = start + offset
            adj_end = end + offset
            expanded = expanded[:adj_start] + expanded_val + expanded[adj_end:]
            offset += len(expanded_val) - (end - start)
            matches.append(AliasMatch(
                original=alias_key,
                expanded=expanded_val,
                alias_type=alias_type,
                fuzzy=False,
            ))
    else:
        expanded = query

    # Fuzzy matching fallback (only if no exact matches found)
    if not matches:
        words = _extract_candidate_terms(query)
        fuzzy_used: set[str] = set()
        for term in words:
            if any(w in fuzzy_used for w in term.lower().split()):
                continue
            close = difflib.get_close_matches(
                term.lower(), sorted_keys,
                n=1, cutoff=fuzzy_threshold,
            )
            if close:
                best = close[0]
                expanded_val, alias_type = all_aliases[best]
                pattern = r'\b' + re.escape(term) + r'\b'
                if not re.search(pattern, expanded, re.IGNORECASE):
                    continue
                expanded = re.sub(
                    pattern, expanded_val, expanded,
                    flags=re.IGNORECASE, count=1,
                )
                fuzzy_used |= set(term.lower().split())
                matches.append(AliasMatch(
                    original=term,
                    expanded=expanded_val,
                    alias_type=alias_type,
                    fuzzy=True,
                ))
                break  # one fuzzy match per query to avoid over-expansion

    if matches:
        return expanded, matches
    return query, []


def _extract_candidate_terms(query: str) -> list[str]:
    """Extract multi-word and single-word candidate terms for fuzzy matching."""
    words = query.split()
    candidates = []
    for i in range(len(words)):
        for j in range(i + 1, min(i + 4, len(words) + 1)):
            term = " ".join(words[i:j])
            if len(term) >= 2:
                candidates.append(term)
    return candidates


# ---------------------------------------------------------------------------
# Layer 2: Domain-aware LLM rewrite
# ---------------------------------------------------------------------------

_DOMAIN_CONTEXT = (
    "You are a query rewriter for a knowledge base called Jarvis. "
    "The knowledge base contains:\n"
    "- Daily AI/ML technology briefings and research paper summaries\n"
    "- Java/Spring Boot project documentation (medavis healthcare software)\n"
    "- Confluence wiki pages from the development team\n"
    "- DICOM, FHIR, HL7 medical imaging protocol documentation\n"
    "- AWS certification study notes\n"
    "- Project architecture, dependencies, and code review summaries\n\n"
    "Rules:\n"
    "1. Preserve domain-specific terms exactly (project names, protocols, team names)\n"
    "2. Expand abbreviations only when you are confident about the meaning\n"
    "3. Resolve pronouns using conversation history when available\n"
    "4. Make vague queries concrete and searchable\n"
    "5. Do NOT invent entities or add information not implied by the query\n"
    "6. Output ONLY the rewritten query, nothing else — no quotes, no explanation"
)

_VAGUE_SIGNALS = [
    "that thing", "the stuff", "what's", "something about",
    "you know", "the other", "last time", "earlier", "before",
    "it", "this", "those", "that", "them",
    "same as", "like before", "again", "continue",
]


def _needs_llm_rewrite(query: str) -> bool:
    """Decide whether the LLM rewrite pass is useful for this query."""
    q = query.lower().strip()

    if len(query.split()) <= 2 and not re.match(r"^[\u4e00-\u9fff]+$", query):
        return True
    if any(v in q for v in _VAGUE_SIGNALS):
        return True
    if len(query) < 15 and "?" not in query:
        return True
    return False


def llm_rewrite(query: str, history: list[dict] | None = None) -> tuple[str, str]:
    """Use the fast LLM for domain-aware query rewriting.

    Returns (rewritten_query, brief_explanation).
    If rewrite is not needed or fails, returns the original query.
    """
    if not _needs_llm_rewrite(query):
        return query, ""

    recent_context = ""
    if history and len(history) >= 2:
        last_msgs = history[-4:]
        ctx_parts = []
        for msg in last_msgs:
            role = msg.get("role", "user")
            content = (msg.get("content", "") or "")[:200]
            ctx_parts.append(f"{role}: {content}")
        recent_context = "\nRecent conversation:\n" + "\n".join(ctx_parts)

    try:
        import requests as _req
        resp = _req.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL_FAST,
                "messages": [
                    {"role": "system", "content": _DOMAIN_CONTEXT},
                    {"role": "user", "content": (
                        f"Original query: {query}"
                        f"{recent_context}\n\n"
                        f"Rewritten query:"
                    )},
                ],
                "stream": False,
                "think": False,
                "options": {"num_predict": 80, "num_ctx": 512},
            },
            timeout=10,
        )
        rewritten = resp.json().get("message", {}).get("content", "").strip()
        first_line = rewritten.split("\n")[0].strip().strip('"').strip("'")
        if len(first_line) > 8 and len(first_line) < len(query) * 3:
            return first_line, "LLM rewrite applied"
    except Exception as e:
        logger.debug("LLM query rewrite failed: %s", e)

    return query, ""


# ---------------------------------------------------------------------------
# Unified smart rewrite entry point
# ---------------------------------------------------------------------------

def smart_rewrite(query: str, history: list[dict] | None = None) -> SmartRewriteResult:
    """Run the full smart rewrite pipeline: alias expansion → LLM rewrite.

    This is the main entry point. Call this instead of the old
    enhance_query() or rewrite_query().
    """
    result = SmartRewriteResult(original=query)

    expanded, aliases = expand_domain_aliases(query)
    if aliases:
        result.alias_expanded = expanded
        result.aliases = aliases
        logger.info(
            "Smart rewrite: alias expansion %r → %r (matched: %s)",
            query, expanded,
            [(a.original, a.expanded) for a in aliases],
        )

    llm_input = expanded if aliases else query
    rewritten, explanation = llm_rewrite(llm_input, history)

    if rewritten != llm_input:
        result.rewritten = rewritten
        logger.info("Smart rewrite: LLM rewrite %r → %r", llm_input, rewritten)
    else:
        result.skipped_llm = True

    return result
