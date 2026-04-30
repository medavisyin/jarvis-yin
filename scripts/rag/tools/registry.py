"""
Tool function registry — maps tool names to their implementation functions.

Tool implementations currently live in agent.py and are registered here at import
time. As the refactoring progresses, implementations will move into this package.
"""

from typing import Any

# Tool functions are registered by agent.py at startup via register_tools()
_TOOL_FUNCTIONS: dict[str, Any] = {}


def register_tools(functions: dict[str, Any]) -> None:
    """Register tool implementations. Called by agent.py at startup."""
    _TOOL_FUNCTIONS.update(functions)


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Dispatch a tool call and return its string result."""
    fn = _TOOL_FUNCTIONS.get(name)
    if fn is None:
        return f"Error: unknown tool '{name}'"
    try:
        return fn(**arguments)
    except Exception as e:
        return f"Error executing {name}: {e}"


TOOL_FUNCTIONS = _TOOL_FUNCTIONS
