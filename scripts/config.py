"""
Jarvis — centralized path configuration.

All paths are derived from environment variables or the project root.
No hardcoded user-specific paths. Override any path via its env var.

Environment variables (all optional — sensible defaults provided):
  JARVIS_ROOT          Project root (auto-detected if unset)
  JARVIS_REPORTS_ROOT  Reports output directory (default: C:/reports/ai)
  JIRA_SKILL_DIR       Directory containing atlassian-report.ps1
                       (default: scripts/ directory next to this file)
"""
import os

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))

JARVIS_ROOT = os.path.normpath(
    os.environ.get("JARVIS_ROOT", os.path.join(_THIS_DIR, ".."))
)

REPORTS_ROOT = os.path.normpath(
    os.environ.get("JARVIS_REPORTS_ROOT", "C:/reports/ai")
)

JIRA_SKILL_DIR = os.path.normpath(
    os.environ.get("JIRA_SKILL_DIR", os.path.join(_THIS_DIR, "tools"))
)

SNAPSHOT_PATH = os.path.join(REPORTS_ROOT, ".rag-store.json")
FEEDBACK_PATH = os.path.join(REPORTS_ROOT, ".rag-feedback.json")
KNOWLEDGE_ROOT = os.path.join(REPORTS_ROOT, "knowledge")
TOPIC_INDEX_PATH = os.path.join(REPORTS_ROOT, "topic-index.json")
MANIFEST_PATH = os.path.join(REPORTS_ROOT, ".index-manifest.json")
PROJECT_DIRS_PATH = os.path.join(REPORTS_ROOT, ".rag-projects.json")
PROJECT_GRAPH_PATH = os.path.join(REPORTS_ROOT, ".project-graph.json")
CHAT_SESSIONS_DIR = os.path.join(REPORTS_ROOT, ".chat-sessions")
NOTES_FILE = os.path.join(REPORTS_ROOT, ".learning-notes.json")

JIRA_REPORT_SCRIPT = os.path.join(JIRA_SKILL_DIR, "atlassian-report.ps1")

STOCK_REPORTS_ROOT = os.path.normpath(
    os.environ.get("STOCK_REPORTS_ROOT", "C:/reports/stock")
)
