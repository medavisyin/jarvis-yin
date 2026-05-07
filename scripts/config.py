"""
Jarvis — centralized path configuration.

All paths are derived from environment variables or the project root.
No hardcoded user-specific paths. Override any path via its env var.

Environment variables (all optional — sensible defaults provided):
  JARVIS_ROOT          Project root (auto-detected if unset)
  JARVIS_REPORTS_ROOT  Reports output directory
                       (default: ~/reports/ai on Mac/Linux, C:/reports/ai on Windows)
  JARVIS_STOCK_ROOT    Stock reports directory (similar defaults)
  BRIEFING_PROXY       SOCKS5 proxy for fetchers (optional, e.g. socks5://localhost:10808)
  JIRA_SKILL_DIR       Directory containing atlassian-report.ps1
                       (default: scripts/ directory next to this file)
"""
import os
import platform

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))

JARVIS_ROOT = os.path.normpath(
    os.environ.get("JARVIS_ROOT", os.path.join(_THIS_DIR, ".."))
)

_DEFAULT_REPORTS = (
    "C:/reports/ai"
    if platform.system() == "Windows"
    else os.path.join(os.path.expanduser("~"), "reports", "ai")
)

REPORTS_ROOT = os.path.normpath(
    os.environ.get("JARVIS_REPORTS_ROOT", _DEFAULT_REPORTS)
)

JIRA_SKILL_DIR = os.path.normpath(
    os.environ.get("JIRA_SKILL_DIR", os.path.join(_THIS_DIR, "tools"))
)

SNAPSHOT_PATH = os.path.join(REPORTS_ROOT, ".rag-store.json")
MEMORY_SNAPSHOT_PATH = os.path.join(REPORTS_ROOT, ".conversation-memory.json")
FEEDBACK_PATH = os.path.join(REPORTS_ROOT, ".rag-feedback.json")
KNOWLEDGE_ROOT = os.path.join(REPORTS_ROOT, "knowledge")
TOPIC_INDEX_PATH = os.path.join(REPORTS_ROOT, "topic-index.json")
MANIFEST_PATH = os.path.join(REPORTS_ROOT, ".index-manifest.json")
PROJECT_DIRS_PATH = os.path.join(REPORTS_ROOT, ".rag-projects.json")
PROJECT_GRAPH_PATH = os.path.join(REPORTS_ROOT, ".project-graph.json")
CHAT_SESSIONS_DIR = os.path.join(REPORTS_ROOT, ".chat-sessions")
NOTES_FILE = os.path.join(REPORTS_ROOT, ".learning-notes.json")

JIRA_REPORT_SCRIPT = os.path.join(JIRA_SKILL_DIR, "atlassian-report.ps1")

_DEFAULT_STOCK = (
    "C:/reports/stock"
    if platform.system() == "Windows"
    else os.path.join(os.path.expanduser("~"), "reports", "stock")
)

STOCK_REPORTS_ROOT = os.path.normpath(
    os.environ.get("STOCK_REPORTS_ROOT", _DEFAULT_STOCK)
)
