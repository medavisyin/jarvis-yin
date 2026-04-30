"""
Request routing for the Jarvis RAG agent.

Maps session IDs to their corresponding system prompts and identifies whether
a request is a learning session, which mode it's in, and what base prompt to use.

The detailed query transformation logic (AWS cert patterns, English learning
classification) remains in api_agent() for now due to tight coupling with
helper functions. This module provides the initial classification layer.
"""

from dataclasses import dataclass
from typing import Optional

from prompts import (
    SYSTEM_PROMPT_AI_LEARNING,
    SYSTEM_PROMPT_ENGLISH_LEARNING,
    SYSTEM_PROMPT_CASUAL_ENGLISH,
    SYSTEM_PROMPT_AWS_CERT,
    SYSTEM_PROMPT_DEEP_DIVE,
)
from learning.constants import LEARNING_SESSION_IDS


@dataclass
class RouteResult:
    """Result of routing a request based on session_id."""
    is_learning: bool = False
    learning_prompt: Optional[str] = None
    session_type: Optional[str] = None  # "ai_learning", "english_learning", etc.
    is_aws_cert: bool = False
    is_deep_dive: bool = False


def route_session(session_id: str, load_session_fn=None) -> RouteResult:
    """Determine the routing for a request based on session_id.

    Args:
        session_id: The session UUID from the request.
        load_session_fn: Callable to load a session file (for deep_dive detection).
                         Signature: (session_id: str) -> dict | None

    Returns:
        RouteResult with prompt and mode information.
    """
    if not session_id:
        return RouteResult()

    if session_id == LEARNING_SESSION_IDS.get("ai_learning"):
        return RouteResult(
            is_learning=True,
            learning_prompt=SYSTEM_PROMPT_AI_LEARNING,
            session_type="ai_learning",
        )
    elif session_id == LEARNING_SESSION_IDS.get("english_learning"):
        return RouteResult(
            is_learning=True,
            learning_prompt=SYSTEM_PROMPT_ENGLISH_LEARNING,
            session_type="english_learning",
        )
    elif session_id == LEARNING_SESSION_IDS.get("casual_english"):
        return RouteResult(
            is_learning=True,
            learning_prompt=SYSTEM_PROMPT_CASUAL_ENGLISH,
            session_type="casual_english",
        )
    elif session_id == LEARNING_SESSION_IDS.get("aws_cert"):
        return RouteResult(
            is_learning=True,
            learning_prompt=SYSTEM_PROMPT_AWS_CERT,
            session_type="aws_cert",
            is_aws_cert=True,
        )
    else:
        if load_session_fn:
            session_data = load_session_fn(session_id)
            if session_data and session_data.get("session_type") == "deep_dive":
                return RouteResult(
                    is_learning=True,
                    learning_prompt=SYSTEM_PROMPT_DEEP_DIVE,
                    session_type="deep_dive",
                    is_deep_dive=True,
                )

    return RouteResult()
