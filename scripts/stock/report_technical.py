"""
技术分析报告生成器 — 将技术分析结果转换为中文 Markdown 报告.

可独立运行, 也可被 agent.py 调用.
"""
import json
import os
import logging
from datetime import datetime

from config import STOCK_DATA_DIR, OLLAMA_HOST, MODEL_USAGE
from technical_analysis import analyze

log = logging.getLogger(__name__)


def _risk_level(analysis: dict) -> tuple[int, str]:
    """根据技术指标计算风险等级 (1-5)."""
    indicators = analysis.get("indicators", {})
    signals = analysis.get("signals", {})

    risk = 3
    atr_pct = indicators.get("atr_pct", 0)
    if atr_pct > 4:
        risk += 1
    elif atr_pct < 1.5:
        risk -= 1

    rsi = indicators.get("rsi_14", 50)
    if rsi and (rsi > 80 or rsi < 20):
        risk += 1

    vol_ratio = indicators.get("volume_ratio", 1)
    if vol_ratio and vol_ratio > 2.5:
        risk += 1

    risk = max(1, min(5, risk))
    labels = {1: "很低", 2: "偏低", 3: "中等", 4: "偏高", 5: "很高"}
    return risk, labels[risk]


def _trend_assessment(analysis: dict) -> dict:
    """评估短/中/长期趋势."""
    indicators = analysis.get("indicators", {})
    price = analysis.get("price", {})
    close = price.get("close")
    if not close:
        return {"short": "无数据", "medium": "无数据", "long": "无数据"}

    ma5 = indicators.get("ma5")
    ma20 = indicators.get("ma20")
    ma60 = indicators.get("ma60")

    def _trend(ma):
        if ma is None:
            return "无数据"
        pct = (close - ma) / ma * 100
        if pct > 5:
            return f"强势看涨 (高于均线 {pct:.1f}%)"
        elif pct > 0:
            return f"偏多 (高于均线 {pct:.1f}%)"
        elif pct > -5:
            return f"偏空 (低于均线 {abs(pct):.1f}%)"
        else:
            return f"弱势看跌 (低于均线 {abs(pct):.1f}%)"

    return {
        "short": _trend(ma5),
        "medium": _trend(ma20),
        "long": _trend(ma60),
    }


def generate_report(symbol: str, analysis: dict | None = None) -> str:
    """
    生成中文技术分析 Markdown 报告.

    Args:
        symbol: 股票代码
        analysis: 预计算的分析结果, 为 None 则自动计算

    Returns:
        Markdown 格式的报告文本
    """
    if analysis is None:
        analysis = analyze(symbol)

    if "error" in analysis:
        return f"## 错误\n\n{analysis['error']}"

    price = analysis.get("price", {})
    signals = analysis.get("signals", {})
    indicators = analysis.get("indicators", {})
    patterns = analysis.get("patterns", [])
    sr = analysis.get("support_resistance", {})
    overall = analysis.get("overall", "中性")
    date = analysis.get("date", datetime.now().strftime("%Y-%m-%d"))

    risk_num, risk_label = _risk_level(analysis)
    trends = _trend_assessment(analysis)

    name = symbol
    profile_path = os.path.join(STOCK_DATA_DIR, symbol, "profile.json")
    if os.path.isfile(profile_path):
        try:
            with open(profile_path, encoding="utf-8") as f:
                p = json.load(f)
            name = p.get("股票简称", symbol)
        except Exception:
            pass

    risk_bar = "🟢" * (5 - risk_num) + "🔴" * risk_num

    lines = []
    lines.append(f"# {name} ({symbol}) 技术分析报告")
    lines.append(f"> 日期: {date} | 综合判断: **{overall}** | 风险等级: {risk_bar} {risk_num}/5 ({risk_label})")
    lines.append("")

    lines.append("## 价格概览")
    lines.append("")
    lines.append(f"| 项目 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 收盘价 | ¥{price.get('close', 'N/A')} |")
    chg = price.get("change_pct")
    chg_str = f"{chg:+.2f}%" if chg is not None else "N/A"
    lines.append(f"| 涨跌幅 | {chg_str} |")
    lines.append(f"| 最高 | ¥{price.get('high', 'N/A')} |")
    lines.append(f"| 最低 | ¥{price.get('low', 'N/A')} |")
    vol = price.get("volume")
    if vol:
        if vol > 100_000_000:
            vol_str = f"{vol / 100_000_000:.2f}亿"
        elif vol > 10_000:
            vol_str = f"{vol / 10_000:.1f}万"
        else:
            vol_str = str(int(vol))
        lines.append(f"| 成交量 | {vol_str} |")
    lines.append("")

    lines.append("## 趋势评估")
    lines.append("")
    lines.append(f"| 周期 | 判断 |")
    lines.append(f"|------|------|")
    lines.append(f"| 短期 (1-5天) | {trends['short']} |")
    lines.append(f"| 中期 (1-4周) | {trends['medium']} |")
    lines.append(f"| 长期 (1-3月) | {trends['long']} |")
    lines.append("")

    lines.append("## 技术指标信号")
    lines.append("")
    lines.append(f"| 指标 | 信号 |")
    lines.append(f"|------|------|")
    for k, v in signals.items():
        icon = "🟢" if "看涨" in v or "金叉" in v or "超卖" in v else "🔴" if "看跌" in v or "死叉" in v or "超买" in v else "⚪"
        lines.append(f"| {icon} {k} | {v} |")
    lines.append("")

    lines.append("## 关键指标数值")
    lines.append("")
    lines.append(f"| 指标 | 数值 | 说明 |")
    lines.append(f"|------|------|------|")

    rsi = indicators.get("rsi_14")
    if rsi:
        note = "超买区" if rsi > 70 else "超卖区" if rsi < 30 else "正常"
        lines.append(f"| RSI(14) | {rsi:.1f} | {note} |")

    macd_h = indicators.get("macd_histogram")
    if macd_h is not None:
        note = "多头动能" if macd_h > 0 else "空头动能"
        lines.append(f"| MACD柱 | {macd_h:.4f} | {note} |")

    kdj_j = indicators.get("kdj_j")
    if kdj_j is not None:
        note = "超买" if kdj_j > 100 else "超卖" if kdj_j < 0 else "正常"
        lines.append(f"| KDJ-J | {kdj_j:.1f} | {note} |")

    bb_pct = indicators.get("bollinger_pct")
    if bb_pct is not None:
        note = "上轨附近" if bb_pct > 0.8 else "下轨附近" if bb_pct < 0.2 else "中轨附近"
        lines.append(f"| 布林%B | {bb_pct:.2f} | {note} |")

    vol_ratio = indicators.get("volume_ratio")
    if vol_ratio is not None:
        note = "显著放量" if vol_ratio > 2 else "放量" if vol_ratio > 1.5 else "缩量" if vol_ratio < 0.5 else "正常"
        lines.append(f"| 量比 | {vol_ratio:.2f} | {note} |")

    atr_pct = indicators.get("atr_pct")
    if atr_pct is not None:
        note = "高波动" if atr_pct > 3 else "低波动" if atr_pct < 1 else "正常"
        lines.append(f"| ATR% | {atr_pct:.2f}% | {note} |")
    lines.append("")

    if sr:
        lines.append("## 支撑/阻力位")
        lines.append("")
        lines.append(f"| 类型 | 价位 |")
        lines.append(f"|------|------|")
        if sr.get("resistance_2"):
            lines.append(f"| 阻力2 | ¥{sr['resistance_2']} |")
        if sr.get("resistance_1"):
            lines.append(f"| 阻力1 | ¥{sr['resistance_1']} |")
        if sr.get("pivot"):
            lines.append(f"| 枢轴点 | ¥{sr['pivot']} |")
        if sr.get("support_1"):
            lines.append(f"| 支撑1 | ¥{sr['support_1']} |")
        if sr.get("support_2"):
            lines.append(f"| 支撑2 | ¥{sr['support_2']} |")
        lines.append(f"| 近期最高 ({sr.get('lookback_days', 60)}日) | ¥{sr.get('recent_high', 'N/A')} |")
        lines.append(f"| 近期最低 ({sr.get('lookback_days', 60)}日) | ¥{sr.get('recent_low', 'N/A')} |")
        lines.append("")

    if patterns:
        lines.append("## 形态识别")
        lines.append("")
        lines.append(f"| 形态 | 方向 | 强度 | 说明 |")
        lines.append(f"|------|------|------|------|")
        for p in patterns:
            icon = "🟢" if p["direction"] == "看涨" else "🔴" if p["direction"] == "看跌" else "⚪"
            lines.append(f"| {icon} {p['name']} | {p['direction']} | {p['strength']} | {p['desc']} |")
        lines.append("")
    else:
        lines.append("## 形态识别")
        lines.append("")
        lines.append("今日未检测到显著K线形态。")
        lines.append("")

    lines.append("---")
    lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 数据来源: 新浪财经/东方财富*")

    return "\n".join(lines)


def save_report(symbol: str, analysis: dict | None = None) -> str:
    """生成报告并保存为 Markdown 文件. 返回文件路径."""
    report = generate_report(symbol, analysis)
    out_dir = os.path.join(STOCK_DATA_DIR, symbol)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "technical-report.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    log.info("报告已保存 → %s", out_path)
    return out_path


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sym = sys.argv[1] if len(sys.argv) > 1 else "600519"
    path = save_report(sym)
    print(f"\n报告已保存: {path}\n")
    with open(path, encoding="utf-8") as f:
        print(f.read())
