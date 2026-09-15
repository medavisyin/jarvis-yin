from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "scripts" / "rag" / "templates" / "index.html"


def _unified_modal_slice(text: str) -> str:
    start = text.find('id="unifiedModal"')
    assert start >= 0
    end = text.find('id="weeklyModal"', start)
    return text[start:end]


def test_unified_modal_has_third_ath_column():
    text = HTML.read_text(encoding="utf-8")
    modal = _unified_modal_slice(text)
    assert "uniAthResult" in modal
    assert "近5年高" in modal
    assert "grid-template-columns:1fr 1fr 1fr" in modal
    assert "历史最高" not in modal
    assert "两份报告" not in modal


def test_ath_html_renders_watch_when_picks_exist():
    text = HTML.read_text(encoding="utf-8")
    start = text.find("function _buildAthRebreakHtml")
    end = text.find("// --- Unified Scanner", start)
    fn = text[start:end]
    picks_loop = fn.find("picks.forEach")
    assert picks_loop >= 0
    after = fn[picks_loop:]
    assert "watchHtml" in after or "meta.watch" in after
