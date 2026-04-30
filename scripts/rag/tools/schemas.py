"""
Ollama-compatible tool schemas for the Jarvis agent.

These define the function signatures that the LLM uses to decide which tools to call.
"""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": (
                "Semantic search across the full RAG knowledge base: AI briefings, "
                "raw research articles, custom documents, learning guides, and wiki pages. "
                "USE WHEN: user asks factual questions about AI/ML topics, team documentation, "
                "or anything potentially in the knowledge base. "
                "DO NOT USE: for real-time data like git commits, Jira tickets, or project dependencies."
            ),
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "top_k": {"type": "integer", "description": "Max results (default 5)"},
                    "min_score": {"type": "number", "description": "Min relevance 0-1 (default 0.3)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "briefing_search",
            "description": (
                "Date-filtered search across daily AI briefings. Use when the user "
                "asks about AI news on specific dates or from specific sources."
            ),
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "date_from": {"type": "string", "description": "Start date YYYY-MM-DD (optional)"},
                    "date_to": {"type": "string", "description": "End date YYYY-MM-DD (optional)"},
                    "source": {"type": "string", "description": "Source filter e.g. 'arxiv' (optional)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confluence_search",
            "description": (
                "Search indexed Confluence wiki pages from the team's knowledge base. "
                "USE WHEN: user asks about team documentation, wiki articles, processes, "
                "or internal team knowledge that lives in Confluence. "
                "DO NOT USE: for AI briefings, research papers, or code-level documentation."
            ),
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "space": {"type": "string", "description": "Confluence space key (optional)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jira_report",
            "description": (
                "Run the Jira/Confluence daily report to get current open tickets, "
                "sprint status, and recent wiki updates for the team. "
                "USE WHEN: user asks about Jira tickets, sprint progress, team workload, "
                "open issues, task status, or backlog items. "
                "DO NOT USE: for code changes, architecture questions, or AI news."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "report_dir": {
                        "type": "string",
                        "description": "Output directory for the report (optional, defaults to today's folder)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "commit_summary",
            "description": (
                "Get recent commit activity across monitored git repositories. "
                "USE WHEN: user asks about code changes, what was pushed/merged/committed, "
                "recent development activity, what someone deployed, or git history. "
                "DO NOT USE: for Jira tickets, documentation searches, or AI news."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {
                        "type": "integer",
                        "description": "Look back N hours (default 24). Ignored if since_date is provided.",
                    },
                    "authors": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by author names (partial match). E.g. ['rong', 'jan'].",
                    },
                    "since_date": {
                        "type": "string",
                        "description": "Start date YYYY-MM-DD (optional, overrides hours).",
                    },
                    "until_date": {
                        "type": "string",
                        "description": "End date YYYY-MM-DD (optional).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_image",
            "description": (
                "Request a focused re-analysis of the user's uploaded image. "
                "USE WHEN: user has uploaded an image and asks a follow-up question "
                "about its content, or you need a more targeted analysis of specific details. "
                "DO NOT USE: when there is no uploaded image in the conversation."
            ),
            "parameters": {
                "type": "object",
                "required": ["image_description_request"],
                "properties": {
                    "image_description_request": {
                        "type": "string",
                        "description": "What to focus on in the image",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "project_query",
            "description": (
                "Query the project knowledge graph for project info, dependencies, "
                "dependents, impact analysis, or cross-project relationships. "
                "USE WHEN: user asks about project structure, service dependencies, "
                "what depends on what, or the impact of changes to a project/service. "
                "DO NOT USE: for code-level details, git history, or documentation lookup."
            ),
            "parameters": {
                "type": "object",
                "required": ["query_type"],
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": ["list", "info", "dependencies", "dependents", "impact", "relationships"],
                        "description": (
                            "Type of query: list (all projects), info (project details), "
                            "dependencies (what it uses), dependents (what uses it), "
                            "impact (change impact analysis), relationships (full graph)"
                        ),
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Project name (fuzzy matched). Required for info/dependencies/dependents/impact.",
                    },
                },
            },
        },
    },
]
