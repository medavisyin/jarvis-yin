"""Quality-value funnel tests."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "stock"))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "stock"))

from quality_value_scanner import (
    is_finance_industry,
    layer1_coarse_filter,
    layer2_fundamental_filter,
    pb_roe_score,
    layer3_rank_and_cap,
    pe_percentile_in_window,
    apply_pe_percentile_gate,
    parse_value_verdict,
    parse_value_verdict_list,
    select_final_picks,
    parse_clist_row,
    VALUE_CLIST_FIELDS,
    rows_from_spot_df,
    attach_industry,
)


def test_finance_industry_keywords():
    assert is_finance_industry("银行")
    assert is_finance_industry("非银金融")
    assert is_finance_industry("保险")
    assert is_finance_industry("证券")
    assert not is_finance_industry("白酒")
    assert not is_finance_industry("互联网")


def test_layer1_excludes_st_and_nonpositive_pe():
    rows = [
        {"symbol": "000001", "name": "平安银行", "industry": "银行", "pe": 5.0, "pb": 0.8, "div_yield": 4.0},
        {"symbol": "000002", "name": "ST地产", "industry": "房地产", "pe": 8.0, "pb": 0.5, "div_yield": 5.0},
        {"symbol": "600001", "name": "亏损制造", "industry": "机械", "pe": -10.0, "pb": 1.0, "div_yield": 3.0},
    ]
    kept, _stats = layer1_coarse_filter(rows)
    symbols = {r["symbol"] for r in kept}
    assert "000002" not in symbols
    assert "600001" not in symbols


def test_layer1_excludes_chinext_keeps_star():
    """ChiNext 300/301 out even if cheaper; STAR 688 is eligible (may still fail relative PE/PB)."""
    rows = [
        {"symbol": "000001", "name": "主板甲", "industry": "机械", "pe": 12.0, "pb": 1.5, "div_yield": 3.0},
        {"symbol": "600000", "name": "主板乙", "industry": "机械", "pe": 10.0, "pb": 1.2, "div_yield": 3.0},
        {"symbol": "300750", "name": "创业板乙", "industry": "机械", "pe": 5.0, "pb": 0.8, "div_yield": 3.5},
        {"symbol": "301001", "name": "创业板丙", "industry": "机械", "pe": 6.0, "pb": 0.9, "div_yield": 3.0},
        {"symbol": "688001", "name": "科创甲", "industry": "机械", "pe": 9.0, "pb": 1.1, "div_yield": 2.8},
    ]
    kept, stats = layer1_coarse_filter(rows)
    symbols = {r["symbol"] for r in kept}
    assert "300750" not in symbols
    assert "301001" not in symbols
    assert "688001" in symbols
    assert "600000" in symbols
    assert stats.get("dropped_chinext", 0) >= 2


def test_layer1_pe_pb_vs_industry_mean_not_cross_industry():
    rows = [
        {"symbol": "A1", "name": "银行甲", "industry": "银行", "pe": 5.0, "pb": 0.7, "div_yield": 4.0},
        {"symbol": "A2", "name": "银行乙", "industry": "银行", "pe": 9.0, "pb": 1.2, "div_yield": 3.0},
        {"symbol": "B1", "name": "软件甲", "industry": "软件", "pe": 25.0, "pb": 3.0, "div_yield": 2.6},
        {"symbol": "B2", "name": "软件乙", "industry": "软件", "pe": 40.0, "pb": 6.0, "div_yield": 2.6},
    ]
    kept, _ = layer1_coarse_filter(rows)
    symbols = {r["symbol"] for r in kept}
    assert "A1" in symbols
    assert "A2" not in symbols
    assert "B1" in symbols
    assert "B2" not in symbols


def test_layer1_missing_dividend_does_not_kill():
    rows = [
        {"symbol": "C1", "name": "制造甲", "industry": "机械", "pe": 10.0, "pb": 1.2, "div_yield": None},
        {"symbol": "C2", "name": "制造乙", "industry": "机械", "pe": 12.0, "pb": 1.5, "div_yield": None},
    ]
    kept, _ = layer1_coarse_filter(rows)
    assert {r["symbol"] for r in kept} == {"C1"}


def test_layer1_unknown_industry_skips_relative_filter():
    rows = [
        {"symbol": "U1", "name": "未知甲", "industry": "", "pe": 8.0, "pb": 1.0, "div_yield": 3.0},
    ]
    kept, _ = layer1_coarse_filter(rows)
    assert kept[0]["symbol"] == "U1"
    assert kept[0].get("industry_unknown") is True


def test_layer1_caps_at_100_keeping_cheapest():
    rows = []
    for i in range(1, 301):
        rows.append({
            "symbol": f"{i:06d}",
            "name": f"机{i}",
            "industry": "机械",
            "pe": float(i),
            "pb": None,
            "div_yield": 3.0,
        })
    kept, stats = layer1_coarse_filter(rows, cap=100)
    assert len(kept) == 100
    assert stats["out"] == 100
    assert kept[0]["pe"] == 1.0
    assert all(r["pe"] <= kept[-1]["pe"] for r in kept)


def test_layer2_requires_roe_and_growth():
    rows = [
        {"symbol": "G1", "industry": "白酒", "roe": 12, "np_cagr_3y": 6, "debt_ratio": 40, "nonrecurring_ratio": 0.9},
        {"symbol": "G2", "industry": "白酒", "roe": 8, "np_cagr_3y": 6, "debt_ratio": 40, "nonrecurring_ratio": 0.9},
        {"symbol": "G3", "industry": "白酒", "roe": 12, "np_cagr_3y": 2, "debt_ratio": 40, "nonrecurring_ratio": 0.9},
    ]
    kept, _ = layer2_fundamental_filter(rows)
    assert {r["symbol"] for r in kept} == {"G1"}


def test_layer2_debt_gate_skips_finance():
    rows = [
        {"symbol": "BK", "industry": "银行", "roe": 11, "np_cagr_3y": 5, "debt_ratio": 92, "div_yield": 4.0},
        {"symbol": "MF", "industry": "机械", "roe": 11, "np_cagr_3y": 5, "debt_ratio": 92, "div_yield": 4.0},
    ]
    kept, _ = layer2_fundamental_filter(rows)
    symbols = {r["symbol"] for r in kept}
    assert "BK" in symbols
    assert "MF" not in symbols


def test_layer2_unknown_nonrecurring_does_not_kill():
    rows = [
        {"symbol": "U", "industry": "机械", "roe": 12, "np_cagr_3y": 6, "debt_ratio": 40, "nonrecurring_ratio": None},
    ]
    kept, _ = layer2_fundamental_filter(rows)
    assert kept[0]["symbol"] == "U"
    assert kept[0]["nonrecurring_status"] == "unknown"


def test_layer2_finance_missing_dividend_keeps_low_dividend_drops():
    rows = [
        {"symbol": "BK1", "industry": "银行", "roe": 11, "np_cagr_3y": 5, "debt_ratio": 92, "div_yield": None},
        {"symbol": "BK2", "industry": "银行", "roe": 11, "np_cagr_3y": 5, "debt_ratio": 92, "div_yield": 1.0},
    ]
    kept, _ = layer2_fundamental_filter(rows)
    symbols = {r["symbol"] for r in kept}
    assert "BK1" in symbols
    assert "BK2" not in symbols


def test_pb_roe_prefers_high_roe_low_pb():
    cheap_quality = {"roe": 20.0, "pb": 1.0}
    expensive_weak = {"roe": 10.0, "pb": 4.0}
    assert pb_roe_score(cheap_quality) > pb_roe_score(expensive_weak)


def test_layer3_caps_two_per_industry_and_keeps_top():
    rows = []
    for i in range(5):
        rows.append({"symbol": f"B{i}", "industry": "白酒", "roe": 20 - i, "pb": 1 + i * 0.2})
    for i in range(3):
        rows.append({"symbol": f"M{i}", "industry": "机械", "roe": 18 - i, "pb": 1.1 + i * 0.2})
    ranked = layer3_rank_and_cap(rows, per_industry=2, top_n=20)
    industries = [r["industry"] for r in ranked]
    assert industries.count("白酒") <= 2
    assert industries.count("机械") <= 2
    assert ranked[0]["symbol"] == "B0"


def test_pe_percentile_uses_five_year_window_not_all_history():
    idx = pd.to_datetime([
        "2015-12-31", "2016-12-31", "2017-12-31", "2018-12-31", "2019-12-31",
        "2020-12-31", "2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31",
    ])
    pe = [5, 5, 5, 5, 5, 20, 22, 24, 26, 28]
    hist = pd.DataFrame({"数据日期": idx, "PE(TTM)": pe})
    as_of = pd.Timestamp("2024-12-31")
    pct_5y = pe_percentile_in_window(21.0, hist, as_of=as_of, years=5)
    pct_all = pe_percentile_in_window(21.0, hist, as_of=as_of, years=20)
    assert pct_5y is not None and pct_5y <= 30
    assert pct_all is not None and pct_all > 30


def test_layer3_drops_only_when_percentile_known_and_high():
    rows = [
        {"symbol": "LOW", "pe_percentile_5y": 20},
        {"symbol": "HIGH", "pe_percentile_5y": 80},
        {"symbol": "UNK", "pe_percentile_5y": None},
    ]
    kept = apply_pe_percentile_gate(rows, max_pct=30)
    assert {r["symbol"] for r in kept} == {"LOW", "UNK"}


def test_parse_value_verdict_extracts_json():
    raw = '```json\n{"verdict":"买入","score":80,"cycle":"平稳","trap":false,"reason":"x","risk":"y"}\n```'
    out = parse_value_verdict(raw)
    assert out["verdict"] == "买入"
    assert out["cycle"] == "平稳"
    assert out["trap"] is False


def test_parse_value_verdict_list_batch():
    raw = '[{"symbol":"600000","verdict":"买入","score":80,"cycle":"平稳","trap":false}]'
    out = parse_value_verdict_list(raw)
    assert len(out) == 1
    assert out[0]["symbol"] == "600000"


def test_select_final_picks_vetoes_decline_and_trap_and_caps_five():
    cands = []
    for i in range(8):
        cands.append({
            "symbol": f"S{i}",
            "industry": f"I{i}",
            "llm": {
                "verdict": "买入",
                "score": 90 - i,
                "cycle": "上升" if i < 6 else "衰退",
                "trap": i == 1,
            },
        })
    picks = select_final_picks(cands, max_n=5)
    symbols = [p["symbol"] for p in picks]
    assert "S1" not in symbols
    assert "S6" not in symbols and "S7" not in symbols
    assert len(picks) <= 5
    assert "S0" in symbols


def test_parse_clist_row_pe_pb_div():
    item = {"f12": "600000", "f14": "浦发银行", "f2": 8.5, "f9": 5.2, "f23": 0.45, "f133": 5.1, "f20": 1e11}
    row = parse_clist_row(item)
    assert row["symbol"] == "600000"
    assert row["name"] == "浦发银行"
    assert row["pe"] == 5.2
    assert row["pb"] == 0.45
    assert row["div_yield"] == 5.1


def test_parse_clist_row_div_alias_f37():
    item = {"f12": "000001", "f14": "平安银行", "f9": 5.0, "f23": 0.6, "f37": 4.2}
    row = parse_clist_row(item)
    assert row["div_yield"] == 4.2


def test_value_clist_fields_include_pb_and_div():
    assert "f23" in VALUE_CLIST_FIELDS
    assert "f133" in VALUE_CLIST_FIELDS or "f37" in VALUE_CLIST_FIELDS


def test_rows_from_spot_df_maps_chinese_columns():
    df = pd.DataFrame([
        {"代码": "600000", "名称": "浦发银行", "市盈率-动态": 5.2, "市净率": 0.45, "股息率": 5.1},
        {"代码": 1, "名称": "平安银行", "市盈率-动态": 5.0, "市净率": 0.7, "股息率": None},
    ])
    rows = rows_from_spot_df(df)
    assert rows[0]["symbol"] == "600000"
    assert rows[0]["pe"] == 5.2
    assert rows[0]["pb"] == 0.45
    assert rows[0]["div_yield"] == 5.1
    assert rows[1]["symbol"] == "000001"
    assert rows[1]["div_yield"] is None


def test_attach_industry_uses_provided_map_not_network():
    rows = [{"symbol": "600000", "name": "浦发银行"}]
    out = attach_industry(rows, industry_map={"600000": "银行"})
    assert out[0]["industry"] == "银行"


def test_attach_industry_cache_miss_blank():
    rows = [{"symbol": "999999", "name": "不存在"}]
    out = attach_industry(rows, industry_map={})
    assert out[0].get("industry", "") == ""


def test_parse_ths_annuals_extracts_roe_debt_and_3y_cagr():
    from quality_value_scanner import parse_ths_annuals

    df = pd.DataFrame([
        {"报告期": "2024-12-31", "净利润": "121亿", "净资产收益率": "15.2%", "资产负债率": "45%"},
        {"报告期": "2023-12-31", "净利润": "110亿", "净资产收益率": "14.0%", "资产负债率": "46%"},
        {"报告期": "2022-12-31", "净利润": "100亿", "净资产收益率": "13.0%", "资产负债率": "47%"},
    ])
    out = parse_ths_annuals(df)
    assert out["roe"] == 15.2
    assert out["debt_ratio"] == 45.0
    assert out["np_cagr_3y"] == 10.0


def test_parse_nonrecurring_percent_vs_amount():
    from quality_value_scanner import parse_ths_annuals

    pct = pd.DataFrame([
        {"报告期": "2024-12-31", "净利润": "100亿", "扣非净利润": "92.5%"},
        {"报告期": "2023-12-31", "净利润": "90亿"},
        {"报告期": "2022-12-31", "净利润": "80亿"},
    ])
    assert parse_ths_annuals(pct)["nonrecurring_ratio"] == 0.925

    amt = pd.DataFrame([
        {"报告期": "2024-12-31", "净利润": "121亿", "扣非净利润": "110亿"},
        {"报告期": "2023-12-31", "净利润": "110亿"},
        {"报告期": "2022-12-31", "净利润": "100亿"},
    ])
    ratio = parse_ths_annuals(amt)["nonrecurring_ratio"]
    assert abs(ratio - 110 / 121) < 1e-6


def test_infer_payout_stable_from_dividend_years():
    from quality_value_scanner import infer_payout_stable

    stable = pd.DataFrame([
        {"年度": 2024, "现金分红": 0.5},
        {"年度": 2023, "现金分红": 0.4},
        {"年度": 2022, "现金分红": 0.3},
    ])
    assert infer_payout_stable(stable) is True

    weak = pd.DataFrame([
        {"年度": 2024, "现金分红": 0},
        {"年度": 2023, "现金分红": 0},
        {"年度": 2022, "现金分红": 0.3},
    ])
    assert infer_payout_stable(weak) is False
    assert infer_payout_stable(None) is None
    assert infer_payout_stable(pd.DataFrame()) is None


def test_fetch_fundamentals_for_value_uses_24h_cache(tmp_path, monkeypatch):
    from datetime import datetime, timedelta
    from quality_value_scanner import fetch_fundamentals_for_value

    calls = {"n": 0}

    def fake_ths(_symbol):
        calls["n"] += 1
        return pd.DataFrame([
            {"报告期": "2024-12-31", "净利润": "121亿", "净资产收益率": "15.2%", "资产负债率": "45%"},
            {"报告期": "2023-12-31", "净利润": "110亿"},
            {"报告期": "2022-12-31", "净利润": "100亿"},
        ])

    def fake_div(_symbol):
        return pd.DataFrame([
            {"年度": 2024, "现金分红": 0.5},
            {"年度": 2023, "现金分红": 0.4},
            {"年度": 2022, "现金分红": 0.3},
        ])

    t0 = datetime(2026, 8, 16, 12, 0, 0)
    kwargs = {
        "cache_dir": str(tmp_path),
        "ths_fetcher": fake_ths,
        "dividend_fetcher": fake_div,
    }
    first = fetch_fundamentals_for_value("600000", now=t0, **kwargs)
    second = fetch_fundamentals_for_value("600000", now=t0 + timedelta(hours=12), **kwargs)
    third = fetch_fundamentals_for_value("600000", now=t0 + timedelta(hours=25), **kwargs)
    assert first["roe"] == 15.2
    assert first["payout_stable"] is True
    assert second["roe"] == 15.2
    assert calls["n"] == 2
    assert third["roe"] == 15.2


def test_fetch_fundamentals_for_value_failure_leaves_none(tmp_path):
    from quality_value_scanner import fetch_fundamentals_for_value

    def boom(_symbol):
        raise RuntimeError("network down")

    out = fetch_fundamentals_for_value(
        "600000",
        cache_dir=str(tmp_path),
        ths_fetcher=boom,
        dividend_fetcher=boom,
    )
    assert out["roe"] is None
    assert out["np_cagr_3y"] is None
    assert out["debt_ratio"] is None
    assert out["nonrecurring_ratio"] is None
    assert out["payout_stable"] is None
