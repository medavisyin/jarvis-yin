"""
Jarvis agent tools — registry and Ollama-compatible JSON schemas.

Each tool function accepts keyword arguments and returns a string result.
Tool schemas follow the Ollama function-calling format.
"""

from .schemas import TOOL_SCHEMAS
from .registry import TOOL_FUNCTIONS, register_tools, execute_tool
from .implementations import (
    get_all_tool_functions,
    init as init_tools,
    tool_commit_summary,
    tool_jira_report,
)

__all__ = [
    "TOOL_SCHEMAS", "TOOL_FUNCTIONS", "register_tools", "execute_tool",
    "get_all_tool_functions", "init_tools", "tool_commit_summary", "tool_jira_report",
]
