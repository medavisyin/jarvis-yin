import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "stock"))

import long_term_scanner as lt


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _finance_payload():
    return {
        "categories": [
            {
                "category": "china-policy",
                "label": "中国政策金融",
                "items": [
                    {
                        "title": "PBOC holds rates",
                        "title_zh": "央行维持利率不变",
                        "summary": "policy",
                        "summary_zh": "政策纪要",
                        "source_id": "pboc",
                    },
                    {
                        "title": "Yicai market color",
                        "title_zh": "第一财经市场观察",
                        "summary": "color",
                        "source_id": "yicai",
                    },
                ],
            },
            {
                "category": "oil",
                "label": "石油",
                "items": [
                    {
                        "title": "Brent climbs",
                        "title_zh": "布伦特上涨",
                        "summary": "supply",
                        "source_id": "oilprice",
                    }
                ],
            },
        ]
    }


def test_collect_reads_finance_and_world_news_separately(tmp_path, monkeypatch):
    day = _today()
    root = tmp_path
    _write_json(
        root / day / "world-news" / "world-news-data.json",
        {"categories": [{"category": "world", "items": [{"headline": "UN vote"}]}]},
    )
    _write_json(
        root / day / "briefing-data.json",
        {"categories": [{"category": "ai", "items": [{"title": "New LLM"}]}]},
    )
    _write_json(
        root / day / "finance-news" / "finance-news-data.json",
        _finance_payload(),
    )
    monkeypatch.setattr(lt, "_REPORTS_AI_ROOT", str(root))
    monkeypatch.setattr(lt, "SIGNAL_WINDOW_DAYS", 1)
    monkeypatch.setattr(lt, "_collect_live_market_signals", lambda signals: None)

    signals = lt._collect_signals()
    assert any(i["headline"] == "UN vote" for i in signals["world_news"])
    assert any("LLM" in i["headline"] for i in signals["ai_tech_news"])
    headlines = [i["headline"] for i in signals["finance_news"]]
    assert "央行维持利率不变" in headlines
    assert "布伦特上涨" in headlines
    assert signals["finance_by_category"]["china-policy"]
    assert signals["finance_by_category"]["oil"]


def test_finance_prefers_zh_and_keeps_source_id():
    items = lt._extract_finance_news_items(_finance_payload(), "2026-08-29")
    pboc = next(i for i in items if i["source_id"] == "pboc")
    assert pboc["headline"] == "央行维持利率不变"
    assert pboc["category"] == "china-policy"
    assert pboc["source_type"] == "finance"


def test_does_not_use_world_news_as_finance_fallback(tmp_path, monkeypatch):
    day = _today()
    _write_json(
        tmp_path / day / "world-news" / "world-news-data.json",
        {"categories": [{"category": "world", "items": [{"headline": "Only world"}]}]},
    )
    monkeypatch.setattr(lt, "_REPORTS_AI_ROOT", str(tmp_path))
    monkeypatch.setattr(lt, "SIGNAL_WINDOW_DAYS", 1)
    monkeypatch.setattr(lt, "_collect_live_market_signals", lambda signals: None)
    signals = lt._collect_signals()
    assert signals["finance_news"] == []
    assert any(i["headline"] == "Only world" for i in signals["world_news"])


def _prices(n=80, start=100.0, step=0.4):
    vals = [start + i * step for i in range(n)]
    dates = pd.bdate_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame({"date": dates, "price": vals})


def test_analyze_series_rising_not_overheated():
    out = lt._analyze_series("WTI原油", _prices())
    assert out["data_available"] is True
    assert out["latest_price"] is not None
    assert out["change_14d_pct"] > 0
    assert out["trend"] in ("上涨", "震荡", "过热")
    assert 0 <= out["upside_score"] <= 100


def test_analyze_series_insufficient():
    df = pd.DataFrame({
        "date": pd.bdate_range("2024-01-02", periods=10, freq="B"),
        "price": list(range(10)),
    })
    out = lt._analyze_series("WTI原油", df)
    assert out["data_available"] is False


def test_analyze_series_none():
    out = lt._analyze_series("WTI原油", None)
    assert out["data_available"] is False


def test_parse_yahoo_chart_json():
    payload = {
        "chart": {
            "result": [{
                "timestamp": [1704067200 + i * 86400 for i in range(5)],
                "indicators": {"quote": [{"close": [70.0, 71.0, None, 72.5, 73.0]}]},
            }]
        }
    }
    df = lt._yahoo_chart_to_df(payload)
    assert list(df["price"]) == [70.0, 71.0, 72.5, 73.0]
    assert len(df) == 4


def test_fetch_yahoo_daily_uses_proxy_and_symbol(monkeypatch):
    calls = {}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "chart": {
                    "result": [{
                        "timestamp": [1704067200 + i * 86400 for i in range(40)],
                        "indicators": {"quote": [{"close": [50.0 + i for i in range(40)]}]},
                    }]
                }
            }

    def fake_get(url, headers=None, timeout=None, proxies=None):
        calls["url"] = url
        calls["proxies"] = proxies
        return _Resp()

    monkeypatch.setattr(lt.requests, "get", fake_get)
    monkeypatch.setattr(
        lt, "_yahoo_proxies",
        lambda: {"http": "http://127.0.0.1:9", "https": "http://127.0.0.1:9"},
    )
    df = lt._fetch_yahoo_daily("CL=F")
    assert "CL=F" in calls["url"] or "CL%3DF" in calls["url"]
    assert calls["proxies"]["https"]
    assert len(df) >= 30


def test_macro_dashboard_from_history_and_headlines():
    history = {
        "nfp": [
            {"date": "2026-06-01", "value": 200.0},
            {"date": "2026-07-01", "value": 180.0},
            {"date": "2026-08-01", "value": 150.0},
        ]
    }
    headlines = [
        {"category": "us-political", "source_id": "fed", "headline": "Fed holds", "date": "2026-08-28"},
        {"category": "china-policy", "source_id": "pboc", "headline": "央行维持利率不变", "date": "2026-08-29"},
        {"category": "oil", "source_id": "oilprice", "headline": "ignore me", "date": "2026-08-29"},
    ]
    dash = lt._build_macro_dashboard(history, headlines)
    nfp = next(s for s in dash["series"] if s["id"] == "nfp")
    assert nfp["latest"] == 150.0
    assert nfp["prior"] == 180.0
    assert nfp["data_available"] is True
    texts = [h["headline"] for h in dash["official_headlines"]]
    assert "Fed holds" in texts
    assert "央行维持利率不变" in texts
    assert "ignore me" not in texts


def test_macro_empty_series_still_ok():
    dash = lt._build_macro_dashboard({}, [])
    assert dash["series"]
    assert all(s["data_available"] is False for s in dash["series"])


def test_analyze_all_factors_composes_macro_and_series(monkeypatch):
    monkeypatch.setattr(lt, "_analyze_market_factors", lambda: {
        "oil": {"name": "WTI原油", "data_available": True, "trend": "上涨"},
        "dollar": {"name": "美元指数", "data_available": False},
        "rates": {"name": "美债10Y", "data_available": False},
        "crypto": {"name": "比特币", "data_available": False},
    })
    monkeypatch.setattr(
        lt, "_fetch_usa_macro_history",
        lambda: {"nfp": [{"date": "2026-08-01", "value": 150.0}]},
    )
    signals = {"finance_news": [{"source_id": "fed", "headline": "Fed holds"}]}
    out = lt._analyze_all_factors(signals)
    assert out["oil"]["data_available"] is True
    assert any(s["id"] == "nfp" and s["data_available"] for s in out["macro"]["series"])
    texts = [h["headline"] for h in out["macro"]["official_headlines"]]
    assert "Fed holds" in texts


def test_signal_summary_prefers_recent_and_caps_at_20():
    signals = {
        "world_news": [],
        "ai_tech_news": [],
        "black_swan": None,
        "hot_sectors": [],
        "market_sentiment": None,
        "finance_news": [
            {
                "date": "2026-08-01",
                "category": "us-political",
                "source_id": "fed",
                "headline": f"old-fed-{i}",
            }
            for i in range(25)
        ] + [
            {
                "date": "2026-08-29",
                "category": "us-political",
                "source_id": "cnbc-economy",
                "headline": "Today Fed watch",
            },
            {
                "date": "2026-08-29",
                "category": "oil",
                "source_id": "oilprice",
                "headline": "Oil story",
            },
        ],
        "finance_by_category": {},
    }
    text = lt._build_signal_summary(signals, {}, factors=None)
    assert "【财经新闻-美国政治金融" in text
    us_block = text.split("【财经新闻-美国政治金融")[1].split("【")[0]
    assert "Today Fed watch" in us_block
    assert us_block.count("old-fed-") == 19
    assert "Oil story" in text
    assert "国际新闻" not in text


def test_legacy_world_news_folds_into_markets_not_own_heading():
    signals = {
        "world_news": [{"date": "d", "headline": "Legacy UN vote", "source_id": ""}],
        "ai_tech_news": [],
        "black_swan": None,
        "hot_sectors": [],
        "market_sentiment": None,
        "finance_news": [{
            "date": "d", "category": "markets", "source_id": "reuters-markets",
            "headline": "Reuters markets",
        }],
        "finance_by_category": {},
    }
    text = lt._build_signal_summary(signals, {}, factors=None)
    assert "国际新闻" not in text
    assert "【财经新闻-综合市场" in text
    assert "Legacy UN vote" in text
    assert "Reuters markets" in text


def test_theme_prompt_requires_new_factors():
    prompt = lt._theme_system_prompt()
    for needle in ("中国政策", "石油", "美元", "利率", "加密", "官方宏观"):
        assert needle in prompt
    assert "禁止只凭科技简报" in prompt or "不要只根据AI" in prompt


def test_parse_thermometer_outlook_ok():
    raw = {
        "macro": {"trend": "中性", "drivers": "NFP放缓", "overheated": False, "advice": "观察", "a_share_implication": "内需"},
        "oil": {"trend": "看涨", "drivers": "供给", "overheated": False, "advice": "跟踪", "a_share_implication": "油服"},
        "dollar": {"trend": "看跌", "drivers": "降息", "overheated": False, "advice": "观察", "a_share_implication": "出口"},
        "rates": {"trend": "震荡", "drivers": "10Y", "overheated": False, "advice": "观察", "a_share_implication": "成长"},
        "crypto": {"trend": "看涨", "drivers": "风险偏好", "overheated": True, "advice": "谨慎", "a_share_implication": "风险偏好"},
        "summary": "风险偏好回暖",
    }
    out = lt._parse_thermometer_outlook(raw)
    assert out["oil"]["a_share_implication"] == "油服"
    assert "error" not in out


def test_parse_thermometer_outlook_malformed():
    out = lt._parse_thermometer_outlook(["not", "a", "dict"])
    assert out.get("error")


def _empty_series(label="x"):
    return {"name": label, "data_available": False}


def _sample_factors():
    oil = lt._analyze_series("WTI原油", _prices())
    return {
        "macro": {
            "series": [{
                "id": "nfp", "label": "非农就业", "latest": 150, "prior": 180,
                "date": "2026-08-01", "data_available": True, "history": [],
            }],
            "official_headlines": [{"headline": "Fed holds", "source_id": "fed"}],
        },
        "oil": oil,
        "dollar": _empty_series("美元指数"),
        "rates": _empty_series("美债10Y"),
        "crypto": _empty_series("比特币"),
        "llm_outlook": {
            "oil": {"trend": "看涨", "drivers": "供给", "advice": "跟踪油服", "a_share_implication": "油服"},
            "summary": "油强美元弱",
        },
    }


def test_report_has_thermometer_sections_when_data_present():
    md = lt._generate_report(
        [], {}, [],
        {"world_news_count": 1, "ai_news_count": 0, "finance_news_count": 3},
        factors=_sample_factors(),
    )
    assert "## 二、宏观与市场温度计" in md
    assert "### 油价" in md
    assert "### 官方宏观" in md
    assert "非农就业" in md
    assert "油服" in md
    assert "## 三、投资主题" in md
    assert "## 四、长期推荐" in md
    assert "**财经新闻**" in md
    assert "**国际新闻**" not in md


def test_report_omits_empty_series_subsections():
    factors = {
        "macro": {"series": [], "official_headlines": []},
        "oil": _empty_series("WTI原油"),
        "dollar": _empty_series("美元指数"),
        "rates": _empty_series("美债10Y"),
        "crypto": _empty_series("比特币"),
    }
    md = lt._generate_report([], {}, [], {}, factors=factors)
    assert "### 油价" not in md
    assert "## 二、宏观与市场温度计" in md


def test_save_results_includes_factors(tmp_path, monkeypatch):
    monkeypatch.setattr(lt, "LONG_TERM_DIR", str(tmp_path))
    monkeypatch.setattr(lt, "_index_report_to_rag", lambda *a, **k: None)
    lt._save_results([], {}, [], {"finance_news_count": 2}, factors=_sample_factors())
    date_str = datetime.now().strftime("%Y-%m-%d")
    data = json.loads((tmp_path / f"{date_str}.json").read_text(encoding="utf-8"))
    assert "factors" in data
    assert data["factors"]["oil"]["data_available"] is True
    hist = json.loads((tmp_path / "history.json").read_text(encoding="utf-8"))
    assert hist[-1].get("oil_trend")


HTML = Path(__file__).resolve().parents[1] / "scripts" / "rag" / "templates" / "index.html"


def test_lt_ui_has_factor_cards_and_phase():
    text = HTML.read_text(encoding="utf-8")
    fn = text[text.find("function renderLtResult"): text.find("async function loadLtHistory")]
    for needle in ("官方宏观", "油价", "美元", "美债", "加密", "data.factors"):
        assert needle in fn
    assert "escHtml" in fn and "a_share_implication" in fn
    poll = text[text.find("function pollLtStatus"): text.find("function renderLtResult")]
    assert "analyzing_factors" in poll
    hist = text[text.find("async function loadLtHistory"): text.find("async function loadLtDate")]
    assert "oil_trend" in hist
