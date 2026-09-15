"""TDD: Analysis pane selection-explain (function-body wiring, no unused Python splitter)."""

from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "scripts" / "rag" / "templates" / "index.html"
TEXT_FORMAT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "rag"
    / "intensive_reading"
    / "text_format.py"
)


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _function_source(html: str, name: str) -> str:
    start = -1
    for prefix in (f"function {name}(", f"async function {name}("):
        start = html.find(prefix)
        if start != -1:
            break
    if start < 0:
        raise AssertionError(f"missing function {name}")
    nxt = html.find("\nfunction ", start + 1)
    nxt_async = html.find("\nasync function ", start + 1)
    ends = [i for i in (nxt, nxt_async) if i != -1]
    end = min(ends) if ends else start + 4000
    return html[start:end]


def test_text_format_has_no_unused_split_plain_paras():
    src = TEXT_FORMAT.read_text(encoding="utf-8")
    assert "def split_plain_paras" not in src


def test_ir_analysis_explain_enabled_requires_done_in_function_body():
    src = _function_source(_html(), "irAnalysisExplainEnabled")
    assert "status !== 'done'" in src
    assert "slot.text" in src


def test_ir_render_plain_paras_splits_and_uses_text_content():
    src = _function_source(_html(), "irRenderPlainParas")
    assert r"split(/\n\s*\n/)" in src
    assert "node.textContent" in src
    assert "className = 'ir-para'" in src


def test_hide_explain_on_tab_generate_and_chunk_in_function_bodies():
    html = _html()
    assert "irHideSelectionExplain" in _function_source(html, "irSelectTab")
    assert "irHideSelectionExplain" in _function_source(html, "irRunAnalyzeKind")
    assert "irHideSelectionExplain" in _function_source(html, "irLoadChunk")


def test_show_active_analysis_renders_paras_when_not_running():
    src = _function_source(_html(), "irShowActiveAnalysis")
    assert "irRenderPlainParas" in src
    assert "Click Generate on this tab" in src


def test_find_para_and_context_require_root_no_passage_default():
    find = _function_source(_html(), "irFindIrPara")
    build = _function_source(_html(), "irBuildSelectionContext")
    assert "root || document.getElementById('irPassage')" not in find
    assert "root || document.getElementById('irPassage')" not in build
    assert "if (!root)" in find
    assert "if (!root)" in build


def test_explain_posts_analysis_source_from_selection_root():
    html = _html()
    on_sel = _function_source(html, "irOnPassageSelectionChange")
    run = _function_source(html, "irRunSelectionExplain")
    assert "source:" in on_sel
    assert "'analysis'" in on_sel or '"analysis"' in on_sel
    assert "source:" in run
    assert "_irExplainSel.source" in run
