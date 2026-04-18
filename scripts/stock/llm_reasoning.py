"""
AI 综合预测 — 将技术面、基本面、情绪分析汇总, 由 LLM 生成预测报告.

使用 HEAVY 模型 (prediction_reasoning 配置), 输出完整的中文预测分析报告.
"""
import json
import os
import logging
from datetime import datetime

import requests

from config import STOCK_DATA_DIR, OLLAMA_HOST, MODEL_USAGE
from technical_analysis import analyze as tech_analyze
from fundamental_analysis import load_fundamentals, fetch_fundamentals, score_fundamentals
from sentiment import analyze_stock_sentiment

log = logging.getLogger(__name__)


def _load_or_compute(symbol: str) -> dict:
    """加载或计算所有分析数据."""
    tech = tech_analyze(symbol)

    fund_data = load_fundamentals(symbol)
    if not fund_data or not fund_data.get("financials"):
        try:
            fund_data = fetch_fundamentals(symbol)
        except Exception as e:
            log.warning("获取基本面数据失败, 使用空数据: %s", e)
            fund_data = fund_data or {}
    fund_score = score_fundamentals(fund_data) if fund_data else {}

    sent_path = os.path.join(STOCK_DATA_DIR, symbol, "sentiment.json")
    if os.path.isfile(sent_path):
        with open(sent_path, encoding="utf-8") as f:
            sentiment = json.load(f)
    else:
        sentiment = analyze_stock_sentiment(symbol)

    xgb_path = os.path.join(STOCK_DATA_DIR, symbol, "xgb_prediction.json")
    xgb_pred = None
    if os.path.isfile(xgb_path):
        try:
            with open(xgb_path, encoding="utf-8") as f:
                xgb_pred = json.load(f)
        except Exception:
            pass

    return {"technical": tech, "fundamental": fund_data, "fund_score": fund_score,
            "sentiment": sentiment, "xgb_prediction": xgb_pred}


def _build_prompt(symbol: str, data: dict) -> str:
    """构建发送给 LLM 的分析数据摘要."""
    tech = data.get("technical", {})
    fund = data.get("fundamental", {})
    fund_score = data.get("fund_score", {})
    sentiment = data.get("sentiment", {})

    name = fund.get("profile", {}).get("name") or symbol
    industry = fund.get("profile", {}).get("industry", "未知")

    sections = []
    sections.append(f"股票: {name} ({symbol}) | 行业: {industry}")
    sections.append("")

    price = tech.get("price", {})
    sections.append(f"【价格】收盘: ¥{price.get('close', 'N/A')} | 涨跌: {price.get('change_pct', 'N/A')}%")

    signals = tech.get("signals", {})
    if signals:
        sig_str = ", ".join(f"{k}={v}" for k, v in signals.items())
        sections.append(f"【技术信号】{sig_str}")
        sections.append(f"【综合技术判断】{tech.get('overall', '中性')}")

    indicators = tech.get("indicators", {})
    ind_items = []
    for k in ["rsi_14", "macd_histogram", "kdj_j", "bollinger_pct", "volume_ratio", "atr_pct"]:
        v = indicators.get(k)
        if v is not None:
            ind_items.append(f"{k}={v}")
    if ind_items:
        sections.append(f"【关键指标】{', '.join(ind_items)}")

    sr = tech.get("support_resistance", {})
    if sr:
        sections.append(f"【支撑/阻力】支撑1=¥{sr.get('support_1', 'N/A')}, 阻力1=¥{sr.get('resistance_1', 'N/A')}, 近期高=¥{sr.get('recent_high', 'N/A')}, 近期低=¥{sr.get('recent_low', 'N/A')}")

    patterns = tech.get("patterns", [])
    if patterns:
        pat_str = ", ".join(f"{p['name']}({p['direction']})" for p in patterns)
        sections.append(f"【K线形态】{pat_str}")

    fin = fund.get("financials", {})
    if fin:
        items = []
        for k, label in [("roe", "ROE"), ("net_margin", "净利率"), ("debt_ratio", "负债率"),
                          ("revenue_yoy", "营收增长"), ("profit_yoy", "利润增长")]:
            v = fin.get(k)
            if v is not None:
                items.append(f"{label}={v}%")
        if items:
            sections.append(f"【基本面】{', '.join(items)}")

    if fund_score:
        sections.append(f"【基本面评分】{fund_score.get('total_score', 'N/A')}/100")

    val = fund.get("valuation", {})
    if val:
        items = []
        for k, label in [("pe_dynamic", "PE"), ("pb", "PB")]:
            v = val.get(k)
            if v is not None:
                items.append(f"{label}={v}")
        if items:
            sections.append(f"【估值】{', '.join(items)}")

    sent_score = sentiment.get("daily_score", 0)
    sent_count = sentiment.get("article_count", 0)
    sections.append(f"【新闻情绪】得分={sent_score:+.3f} (分析{sent_count}条新闻)")

    top_pos = sentiment.get("top_positive", "")
    top_neg = sentiment.get("top_negative", "")
    if top_pos:
        sections.append(f"  最利好: {top_pos}")
    if top_neg:
        sections.append(f"  最利空: {top_neg}")

    articles = sentiment.get("articles", [])
    if articles:
        top3 = sorted(articles, key=lambda x: abs(x.get("score", 0)), reverse=True)[:3]
        for a in top3:
            sections.append(f"  [{a.get('score', 0):+.2f}] {a.get('title', '')[:50]} — {a.get('reason', '')[:40]}")

    xgb = data.get("xgb_prediction")
    if xgb and "prediction" in xgb:
        sections.append(f"【XGBoost ML预测】方向={xgb['prediction']}, 置信度={xgb.get('confidence', 0):.1%}")
        probs = xgb.get("probabilities", {})
        if probs:
            prob_str = f"涨={probs.get('涨', 0):.1%}, 平={probs.get('平', 0):.1%}, 跌={probs.get('跌', 0):.1%}"
            sections.append(f"  概率分布: {prob_str}")
        wf = xgb.get("walk_forward", {})
        if wf:
            sections.append(f"  Walk-Forward准确率: {wf.get('overall_accuracy', 0):.1%}")
        feats = xgb.get("feature_importance", [])[:5]
        if feats:
            feat_str = ", ".join(f"{f['name']}={f['importance']:.3f}" for f in feats)
            sections.append(f"  关键特征: {feat_str}")

    return "\n".join(sections)


def generate_prediction(symbol: str, stream: bool = False):
    """
    生成 AI 综合预测报告.

    Args:
        symbol: 股票代码
        stream: True 则返回 generator (用于 SSE), False 则返回完整文本

    Returns:
        str (完整报告) 或 generator (逐 token)
    """
    log.info("开始生成 %s AI 预测...", symbol)

    data = _load_or_compute(symbol)
    analysis_text = _build_prompt(symbol, data)

    name = data.get("fundamental", {}).get("profile", {}).get("name") or symbol
    model = MODEL_USAGE.get("prediction_reasoning", "qwen3.5:4b")

    system_prompt = (
        "你是一位资深A股市场分析师，为散户投资者撰写预测报告。\n"
        "要求：\n"
        "1. 用中文撰写，技术术语可保留英文\n"
        "2. 诚实面对不确定性，不夸大预测准确度\n"
        "3. 解释推理过程，让初学者也能理解\n"
        "4. 给出明确的操作建议和关键价位\n"
        "5. 报告结构必须包含以下部分:\n"
        "   - 方向判断 (看涨/看跌/震荡)\n"
        "   - 信心水平 (高/中/低)\n"
        "   - 时间范围 (1周/2周)\n"
        "   - 核心理由 (3-5条)\n"
        "   - 风险因素\n"
        "   - 建议操作 (买入/持有/减仓/观望)\n"
        "   - 关键价位 (支撑/阻力/止损)"
    )

    user_prompt = (
        f"请根据以下{name}({symbol})的分析数据，撰写一份完整的AI预测报告:\n\n"
        f"{analysis_text}\n\n"
        f"请按照要求的结构撰写报告。"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": stream,
        "think": False,
        "options": {"temperature": 0.6, "num_predict": 1500, "num_ctx": 4096},
    }

    if not stream:
        log.info("调用 %s 生成预测 (非流式)...", model)
        resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=300)
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "")
        if "<think>" in raw:
            raw = raw.split("</think>")[-1].strip()

        header = f"# {name} ({symbol}) AI 预测报告\n"
        header += f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 模型: {model}\n\n"

        report = header + raw

        out_path = os.path.join(STOCK_DATA_DIR, symbol, "prediction-report.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)
        log.info("预测报告已保存 → %s", out_path)

        return report

    def _stream_gen():
        log.info("调用 %s 生成预测 (流式)...", model)
        resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, stream=True, timeout=300)
        resp.raise_for_status()

        in_think = False
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if not token:
                    if chunk.get("done"):
                        break
                    continue

                if "<think>" in token:
                    in_think = True
                    continue
                if in_think:
                    if "</think>" in token:
                        in_think = False
                        after = token.split("</think>", 1)[-1]
                        if after.strip():
                            yield after
                    continue

                yield token
                if chunk.get("done"):
                    break
            except json.JSONDecodeError:
                pass

    return _stream_gen()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sym = sys.argv[1] if len(sys.argv) > 1 else "600519"
    report = generate_prediction(sym, stream=False)
    print(report)
