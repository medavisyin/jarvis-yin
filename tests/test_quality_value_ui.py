"""Contract: quality-value toolbar + modal exist in index.html."""
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "scripts" / "rag" / "templates" / "index.html"


def test_index_has_quality_value_ui():
    text = HTML.read_text(encoding="utf-8")
    assert "openQualityValueModal" in text
    assert "优质低估" in text
    assert "/api/stock/quality-value/start" in text
    assert "qvUseDeepseek" in text
    assert "qualityValueModal" in text
    assert "exportStockPdf('quality_value','qv')" in text
    assert "_cachePdfData('qv'" in text
    assert "btnQvPdf" in text
    assert "qvHorizon" in text
    assert "1 个月" in text or "1个月" in text
    assert "horizon" in text[text.find("async function startQvScan"):text.find("async function stopQvScan")]


def test_poll_qv_status_treats_idle_as_not_running():
    """Opening the modal polls status; idle must not disable 开始扫描."""
    text = HTML.read_text(encoding="utf-8")
    start = text.find("async function pollQvStatus")
    end = text.find("function renderQvResult")
    assert start != -1 and end > start
    fn = text[start:end]
    assert "d.status === 'idle'" in fn
    idle_idx = fn.find("d.status === 'idle'")
    disable_running = fn.find("btnQvStart').disabled = true")
    assert disable_running == -1 or idle_idx < disable_running


def test_poll_qv_error_loads_result():
    text = HTML.read_text(encoding="utf-8")
    start = text.find("async function pollQvStatus")
    end = text.find("function renderQvResult")
    assert start != -1 and end > start
    fn = text[start:end]
    err_idx = fn.find("d.status === 'error'")
    assert err_idx != -1
    err_chunk = fn[err_idx:]
    assert "quality-value/result" in err_chunk
    assert "renderQvResult" in err_chunk
    assert "renderQvResult(d)" not in err_chunk
    assert "qvResult" in err_chunk
    assert "d.error" in err_chunk
    assert "catch(_e) {}" not in err_chunk


def test_render_qv_distinguishes_snapshot_failure():
    text = HTML.read_text(encoding="utf-8")
    start = text.find("function renderQvResult")
    end = text.find("async function loadQvHistory")
    assert start != -1 and end > start
    fn = text[start:end]
    assert "snapshot_failed" in fn
    assert "行情快照" in fn or "拉取失败" in fn


def test_render_qv_shows_prediction_trade_levels():
    text = HTML.read_text(encoding="utf-8")
    start = text.find("function renderQvResult")
    end = text.find("async function loadQvHistory")
    assert start != -1 and end > start
    fn = text[start:end]
    assert "prediction" in fn
    assert "buy_low" in fn
    assert "stop_loss" in fn
    assert "target_price" in fn
    assert "建议买入" in fn or "买入区间" in fn
    assert "止损" in fn
    assert "抛" in fn or "目标" in fn
    assert "1～2周" in fn or "1-2周" in fn or "1～2 周" in fn
    banner_idx = fn.find("不构成投资建议")
    assert banner_idx != -1
    banner = fn[banner_idx:banner_idx + 400]
    assert "use_deepseek" in banner or "prediction" in banner
