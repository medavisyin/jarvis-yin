"""Contract: pre-annotate and pack are gone; in-Jarvis reading stays."""
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "scripts" / "rag" / "templates" / "index.html"
ROUTES = Path(__file__).resolve().parents[1] / "scripts" / "rag" / "routes" / "intensive_reading.py"


def test_html_has_no_preannotate_or_pack():
    text = HTML.read_text(encoding="utf-8")
    assert "Pre-annotate selected" not in text
    assert "irDownloadPack" not in text
    assert "irRunOverlayJob" not in text
    assert "function irApplyOverlayToPara" not in text
    assert "pack.zip" not in text
    assert "function irOpenBook" in text
    assert "function irRenderPassage" in text
    assert "Explain" in text


def test_routes_have_no_overlay_or_pack_keep_progress():
    text = ROUTES.read_text(encoding="utf-8")
    assert "/api/intensive-reading/overlay/run" not in text
    assert "pack.zip" not in text
    assert "load_all_progress" in text
    assert "save_progress" in text
