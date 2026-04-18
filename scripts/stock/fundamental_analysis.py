"""
基本面分析 — 获取财务数据并计算综合评分.

从 akshare 获取财务指标, 计算各维度得分 (0-100),
生成中文基本面分析报告.
"""
import json
import os
import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from config import STOCK_DATA_DIR

log = logging.getLogger(__name__)


def _safe_float(val, default=None):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def fetch_fundamentals(symbol: str) -> dict:
    """
    获取股票基本面数据.

    Returns dict with financial metrics or cached data on failure.
    """
    out_path = os.path.join(STOCK_DATA_DIR, symbol, "fundamentals.json")

    data = {
        "symbol": symbol,
        "fetched_at": datetime.now().isoformat(),
        "profile": {},
        "valuation": {},
        "financials": {},
    }

    try:
        profile_path = os.path.join(STOCK_DATA_DIR, symbol, "profile.json")
        if os.path.isfile(profile_path):
            with open(profile_path, encoding="utf-8") as f:
                p = json.load(f)
            data["profile"] = {
                "name": p.get("股票简称", ""),
                "industry": p.get("行业", ""),
                "listed_date": p.get("上市时间", ""),
                "total_shares": _safe_float(p.get("总股本")),
                "float_shares": _safe_float(p.get("流通股")),
                "market_cap": _safe_float(p.get("总市值")),
            }
    except Exception as e:
        log.warning("加载公司信息失败: %s", e)

    try:
        rt_path = os.path.join(STOCK_DATA_DIR, symbol, "realtime.json")
        if os.path.isfile(rt_path):
            with open(rt_path, encoding="utf-8") as f:
                rt = json.load(f)
            data["valuation"] = {
                "pe_dynamic": _safe_float(rt.get("市盈率-动态")),
                "pb": _safe_float(rt.get("市净率")),
                "price": _safe_float(rt.get("最新价")),
                "market_cap": _safe_float(rt.get("总市值")),
                "float_cap": _safe_float(rt.get("流通市值")),
            }
    except Exception as e:
        log.warning("加载实时数据失败: %s", e)

    try:
        log.info("获取 %s 财务指标...", symbol)
        df = ak.stock_financial_abstract_ths(symbol=symbol, indicator="按年度")
        if df is not None and not df.empty:
            df = df.sort_values("报告期", ascending=False).reset_index(drop=True)
            latest = df.iloc[0].to_dict()

            def _parse_cn_number(val):
                """解析中文数字格式: '1862.22亿' -> 186222000000"""
                if val is None or val is False:
                    return None
                s = str(val).strip().rstrip("%")
                if not s or s == "False":
                    return None
                multiplier = 1
                if s.endswith("亿"):
                    multiplier = 100_000_000
                    s = s[:-1]
                elif s.endswith("万"):
                    multiplier = 10_000
                    s = s[:-1]
                try:
                    return float(s) * multiplier
                except ValueError:
                    return None

            def _parse_pct(val):
                """解析百分比: '52.19%' -> 52.19"""
                if val is None or val is False:
                    return None
                s = str(val).strip().rstrip("%")
                if not s or s == "False":
                    return None
                try:
                    return float(s)
                except ValueError:
                    return None

            data["financials"] = {
                "report_date": str(latest.get("报告期", "")),
                "revenue": _parse_cn_number(latest.get("营业总收入")),
                "net_profit": _parse_cn_number(latest.get("净利润")),
                "roe": _parse_pct(latest.get("净资产收益率")),
                "gross_margin": _parse_pct(latest.get("销售毛利率")),
                "net_margin": _parse_pct(latest.get("销售净利率")),
                "debt_ratio": _parse_pct(latest.get("资产负债率")),
                "revenue_yoy": _parse_pct(latest.get("营业总收入同比增长率")),
                "profit_yoy": _parse_pct(latest.get("净利润同比增长率")),
                "eps": _safe_float(latest.get("基本每股收益")),
                "bvps": _safe_float(latest.get("每股净资产")),
                "current_ratio": _safe_float(latest.get("流动比率")),
            }
    except Exception as e:
        log.warning("获取财务指标失败 (可能网络问题): %s", e)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info("基本面数据已保存 → %s", out_path)
    return data


def load_fundamentals(symbol: str) -> dict:
    """从本地缓存加载基本面数据."""
    path = os.path.join(STOCK_DATA_DIR, symbol, "fundamentals.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def score_fundamentals(data: dict) -> dict:
    """
    计算基本面综合评分 (0-100).

    维度:
      盈利能力 25% | 成长性 25% | 估值 20% | 财务健康 15% | 综合 15%
    """
    fin = data.get("financials", {})
    val = data.get("valuation", {})

    scores = {}

    roe = fin.get("roe")
    net_margin = fin.get("net_margin")
    profit_score = 50
    if roe is not None:
        if roe > 25:
            profit_score = 95
        elif roe > 20:
            profit_score = 85
        elif roe > 15:
            profit_score = 75
        elif roe > 10:
            profit_score = 60
        elif roe > 5:
            profit_score = 40
        else:
            profit_score = 20
    if net_margin is not None and net_margin > 30:
        profit_score = min(100, profit_score + 10)
    scores["盈利能力"] = {"score": profit_score, "weight": 0.25,
                        "detail": f"ROE={roe}%, 净利率={net_margin}%"}

    rev_yoy = fin.get("revenue_yoy")
    profit_yoy = fin.get("profit_yoy")
    growth_score = 50
    if profit_yoy is not None:
        if profit_yoy > 50:
            growth_score = 95
        elif profit_yoy > 30:
            growth_score = 85
        elif profit_yoy > 15:
            growth_score = 70
        elif profit_yoy > 0:
            growth_score = 55
        elif profit_yoy > -10:
            growth_score = 35
        else:
            growth_score = 15
    if rev_yoy is not None:
        if rev_yoy > 30:
            growth_score = min(100, growth_score + 10)
        elif rev_yoy < -10:
            growth_score = max(0, growth_score - 10)
    scores["成长性"] = {"score": growth_score, "weight": 0.25,
                      "detail": f"营收增长={rev_yoy}%, 利润增长={profit_yoy}%"}

    pe = val.get("pe_dynamic")
    pb = val.get("pb")
    value_score = 50
    if pe is not None:
        if 0 < pe < 10:
            value_score = 90
        elif pe < 15:
            value_score = 80
        elif pe < 25:
            value_score = 65
        elif pe < 40:
            value_score = 45
        elif pe < 80:
            value_score = 25
        else:
            value_score = 10
    if pb is not None and pb < 1:
        value_score = min(100, value_score + 15)
    scores["估值水平"] = {"score": value_score, "weight": 0.20,
                        "detail": f"PE={pe}, PB={pb}"}

    debt = fin.get("debt_ratio")
    health_score = 50
    if debt is not None:
        if debt < 30:
            health_score = 90
        elif debt < 50:
            health_score = 75
        elif debt < 65:
            health_score = 55
        elif debt < 80:
            health_score = 30
        else:
            health_score = 10
    scores["财务健康"] = {"score": health_score, "weight": 0.15,
                        "detail": f"负债率={debt}%"}

    cap = val.get("market_cap")
    misc_score = 50
    if cap:
        cap_yi = cap / 100_000_000
        if cap_yi > 1000:
            misc_score = 70
        elif cap_yi > 100:
            misc_score = 60
        elif cap_yi > 30:
            misc_score = 50
        else:
            misc_score = 40
    scores["综合因素"] = {"score": misc_score, "weight": 0.15,
                        "detail": f"市值={cap / 100_000_000:.0f}亿" if cap else "N/A"}

    total = sum(s["score"] * s["weight"] for s in scores.values())

    return {
        "total_score": round(total, 1),
        "dimensions": scores,
        "symbol": data.get("symbol", ""),
        "name": data.get("profile", {}).get("name", ""),
    }


def generate_fundamental_report(symbol: str) -> str:
    """生成中文基本面分析 Markdown 报告."""
    data = load_fundamentals(symbol)
    if not data:
        data = fetch_fundamentals(symbol)

    scoring = score_fundamentals(data)
    fin = data.get("financials", {})
    val = data.get("valuation", {})
    profile = data.get("profile", {})

    name = profile.get("name") or symbol
    total = scoring["total_score"]

    if total >= 80:
        grade = "优秀 ⭐⭐⭐⭐⭐"
    elif total >= 65:
        grade = "良好 ⭐⭐⭐⭐"
    elif total >= 50:
        grade = "一般 ⭐⭐⭐"
    elif total >= 35:
        grade = "偏弱 ⭐⭐"
    else:
        grade = "较差 ⭐"

    lines = []
    lines.append(f"# {name} ({symbol}) 基本面分析报告")
    lines.append(f"> 综合评分: **{total}/100** ({grade})")
    lines.append("")

    lines.append("## 评分详情")
    lines.append("")
    lines.append("| 维度 | 得分 | 权重 | 说明 |")
    lines.append("|------|------|------|------|")
    for dim_name, dim in scoring["dimensions"].items():
        bar = "█" * (dim["score"] // 10) + "░" * (10 - dim["score"] // 10)
        lines.append(f"| {dim_name} | {dim['score']}/100 {bar} | {int(dim['weight']*100)}% | {dim['detail']} |")
    lines.append("")

    lines.append("## 财务数据")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")

    def _fmt_money(val):
        if val is None:
            return "N/A"
        v = abs(val)
        if v >= 100_000_000:
            return f"{'−' if val < 0 else ''}{v / 100_000_000:.2f}亿"
        elif v >= 10_000:
            return f"{'−' if val < 0 else ''}{v / 10_000:.1f}万"
        return f"{val:.2f}"

    lines.append(f"| 营业收入 | {_fmt_money(fin.get('revenue'))} |")
    lines.append(f"| 净利润 | {_fmt_money(fin.get('net_profit'))} |")
    lines.append(f"| ROE | {fin.get('roe', 'N/A')}% |")
    lines.append(f"| 毛利率 | {fin.get('gross_margin', 'N/A')}% |")
    lines.append(f"| 净利率 | {fin.get('net_margin', 'N/A')}% |")
    lines.append(f"| 负债率 | {fin.get('debt_ratio', 'N/A')}% |")
    lines.append(f"| 营收同比 | {fin.get('revenue_yoy', 'N/A')}% |")
    lines.append(f"| 利润同比 | {fin.get('profit_yoy', 'N/A')}% |")
    lines.append("")

    lines.append("## 估值数据")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append(f"| 市盈率 (PE) | {val.get('pe_dynamic', 'N/A')} |")
    lines.append(f"| 市净率 (PB) | {val.get('pb', 'N/A')} |")
    cap = val.get("market_cap")
    lines.append(f"| 总市值 | {_fmt_money(cap)} |")
    lines.append(f"| 行业 | {profile.get('industry', 'N/A')} |")
    lines.append("")

    lines.append("---")
    lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    report = "\n".join(lines)

    out_path = os.path.join(STOCK_DATA_DIR, symbol, "fundamental-report.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    log.info("基本面报告已保存 → %s", out_path)

    return report


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sym = sys.argv[1] if len(sys.argv) > 1 else "600519"
    report = generate_fundamental_report(sym)
    print(report)
