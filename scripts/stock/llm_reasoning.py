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
from sentiment import analyze_stock_sentiment, analyze_stock_sentiment_deepseek

log = logging.getLogger(__name__)


def _load_or_compute(symbol: str, sentiment_provider: str = "ollama") -> dict:
    """加载或计算所有分析数据.

    sentiment_provider:
        "ollama"    -> 使用 sentiment.json (本地 Ollama 打分), 缺失则用 Ollama 实时打分
        "deepseek"  -> 使用 sentiment-deepseek.json (DeepSeek 打分), 缺失则用 DeepSeek 实时打分
    """
    tech = tech_analyze(symbol)

    fund_data = load_fundamentals(symbol)
    if not fund_data or not fund_data.get("financials"):
        try:
            fund_data = fetch_fundamentals(symbol)
        except Exception as e:
            log.warning("获取基本面数据失败, 使用空数据: %s", e)
            fund_data = fund_data or {}
    fund_score = score_fundamentals(fund_data) if fund_data else {}

    if sentiment_provider == "deepseek":
        sent_path = os.path.join(STOCK_DATA_DIR, symbol, "sentiment-deepseek.json")
        if os.path.isfile(sent_path):
            with open(sent_path, encoding="utf-8") as f:
                sentiment = json.load(f)
        else:
            sentiment = analyze_stock_sentiment_deepseek(symbol)
    else:
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

    realtime = data.get("realtime_quote", {})
    if realtime and realtime.get("最新价"):
        sections.append(f"【实时行情】当前价: ¥{realtime['最新价']} | 今日涨跌: {realtime.get('涨跌幅', 'N/A')}% | 今开: ¥{realtime.get('今开', 'N/A')} | 最高: ¥{realtime.get('最高', 'N/A')} | 最低: ¥{realtime.get('最低', 'N/A')}")
        sections.append(f"  成交额: {realtime.get('成交额', 'N/A')} | 昨收: ¥{realtime.get('昨收', 'N/A')}")

    price = tech.get("price", {})
    if realtime and realtime.get("最新价"):
        sections.append(f"【历史收盘参考】上一交易日收盘: ¥{price.get('close', 'N/A')} | 涨跌: {price.get('change_pct', 'N/A')}%")
    else:
        sections.append(f"【价格】收盘: ¥{price.get('close', 'N/A')} | 涨跌: {price.get('change_pct', 'N/A')}% (注意: 未能获取实时价格, 此为历史收盘价)")

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


def _make_system_prompt(cost_price: float | None = None) -> str:
    base = (
        "你是一位资深A股市场分析师，为散户投资者撰写预测报告。\n"
        "要求：\n"
        "1. 用中文撰写，技术术语可保留英文\n"
        "2. 诚实面对不确定性，不夸大预测准确度\n"
        "3. 解释推理过程，让初学者也能理解\n"
        "4. 基于实时价格（如有）进行判断，而非仅看历史收盘价\n"
        "5. 给出明确的操作建议和关键价位\n"
        "6. 报告结构必须包含以下部分:\n"
        "   - 买入判断 (明确回答: 建议买入 / 建议观望 / 建议回避)\n"
        "   - 方向判断 (看涨/看跌/震荡)\n"
        "   - 信心水平 (高/中/低)\n"
        "   - 时间范围 (短期2周到2-3个月)\n"
        "   - 核心理由 (3-5条)\n"
        "   - 风险因素\n"
        "   - 建议操作 (买入区间/持有/减仓/观望)\n"
        "   - 关键价位 (支撑/阻力/止损/止盈目标)\n"
        "7. A股T+1规则意味着买入当天不能卖出，追高风险极大\n"
        "8. 如果数据中提供了实时行情，请以实时价格作为当前价位进行分析"
    )
    if cost_price is not None and cost_price > 0:
        base += (
            f"\n9. 【重要】用户已持有该股票，持仓成本 ¥{cost_price:.2f}。"
            "\n   报告中必须额外包含以下'持仓操作策略'板块，根据当前盈亏状态给出不同建议："
            "\n"
            "\n   **如果当前浮亏（现价 < 成本价）：**"
            "\n   - 补仓建议 (是否建议补仓、补仓时机和条件)"
            "\n   - 建议补仓价位 (具体价格区间，需低于成本价)"
            "\n   - 补仓比例建议 (加仓多少比例合适)"
            "\n   - 摊薄后预期成本 (补仓后新成本大约多少)"
            "\n   - 回本预期 (基于当前趋势大概多久回本)"
            "\n   - 最终止损价 (跌破什么价位考虑止损)"
            "\n"
            "\n   **如果当前浮盈（现价 >= 成本价）：**"
            "\n   - 止盈建议 (是否应该卖出获利？分批还是一次性？)"
            "\n   - 建议止盈价位 (目标卖出价格或价格区间)"
            "\n   - 分批止盈策略 (到什么价位卖多少比例)"
            "\n   - 继续持有条件 (什么情况下可以继续拿着不卖)"
            "\n   - 回撤保护价 (如果从高点回落到什么价位必须卖出锁定利润)"
            "\n"
            "\n   基本原则："
            "\n   - 浮亏时：补仓前提是基本面未恶化且有技术支撑"
            "\n   - 浮盈时：不贪心，设好止盈位；趋势好可以用移动止盈保护利润"
        )
    return base


def generate_prediction(symbol: str, stream: bool = False, realtime_quote: dict | None = None, cost_price: float | None = None):
    """
    生成 AI 综合预测报告 (本地 Ollama).

    Args:
        symbol: 股票代码
        stream: True 则返回 generator (用于 SSE), False 则返回完整文本
        realtime_quote: 实时行情数据 (可选, 由调用方提供)
        cost_price: 用户持仓成本价 (可选)

    Returns:
        str (完整报告) 或 generator (逐 token)
    """
    log.info("开始生成 %s AI 预测...", symbol)

    data = _load_or_compute(symbol)
    if realtime_quote:
        data["realtime_quote"] = realtime_quote
    elif not data.get("realtime_quote"):
        try:
            from fetch_market_data import fetch_realtime_quote
            data["realtime_quote"] = fetch_realtime_quote(symbol)
        except Exception as e:
            log.warning("获取实时行情失败: %s", e)
    analysis_text = _build_prompt(symbol, data)

    name = data.get("fundamental", {}).get("profile", {}).get("name") or symbol
    model = MODEL_USAGE.get("prediction_reasoning", "qwen3.5:4b")

    system_prompt = _make_system_prompt(cost_price=cost_price)

    cost_section = ""
    if cost_price is not None and cost_price > 0:
        current = None
        if realtime_quote and realtime_quote.get("最新价"):
            current = realtime_quote["最新价"]
        elif data.get("technical", {}).get("price", {}).get("close"):
            current = data["technical"]["price"]["close"]
        pnl_str = ""
        if current:
            pnl_pct = (current - cost_price) / cost_price * 100
            pnl_str = f"（当前{'浮盈' if pnl_pct >= 0 else '浮亏'} {pnl_pct:+.2f}%）"
        if current and current >= cost_price:
            cost_section = (
                f"\n\n【持仓信息 — 当前浮盈】\n"
                f"用户已持有该股，成本价: ¥{cost_price:.2f} {pnl_str}\n"
                f"请重点给出止盈策略：\n"
                f"1. 是否建议现在卖出获利？还是继续持有？\n"
                f"2. 目标止盈价位是多少？分批卖出还是一次性？\n"
                f"3. 如果继续持有，什么条件下必须卖出（回撤保护价）？\n"
                f"4. 分批止盈方案（到什么价位卖多少比例）\n"
            )
        else:
            cost_section = (
                f"\n\n【持仓信息 — 当前浮亏】\n"
                f"用户已持有该股，成本价: ¥{cost_price:.2f} {pnl_str}\n"
                f"用户不希望割肉，请重点给出：\n"
                f"1. 是否建议补仓？在什么价位补仓？\n"
                f"2. 补仓后的摊薄成本大概是多少？\n"
                f"3. 如果不补仓，预计需要等多久才能回本？\n"
                f"4. 止损价位（如果跌破某个关键位，可能需要考虑止损）\n"
            )

    user_prompt = (
        f"请根据以下{name}({symbol})的分析数据，撰写一份完整的AI预测报告:\n\n"
        f"{analysis_text}{cost_section}\n\n"
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


def _build_deepseek_prompt(symbol: str, data: dict) -> str:
    """构建 DeepSeek 专用的深度分析提示词，比本地版本多出大量原始数据。"""
    import pandas as pd

    sections = []
    tech = data.get("technical", {})
    fund = data.get("fundamental", {})
    fund_score = data.get("fund_score", {})
    sentiment = data.get("sentiment", {})

    name = fund.get("profile", {}).get("name") or symbol
    industry = fund.get("profile", {}).get("industry", "未知")

    sections.append(f"# {name} ({symbol}) | 行业: {industry}")

    # ── Section 0: Real-time quote ──
    realtime = data.get("realtime_quote", {})
    if realtime and realtime.get("最新价"):
        sections.append("\n## 实时行情 (当前)")
        sections.append(f"- **当前价格**: ¥{realtime['最新价']}")
        sections.append(f"- **今日涨跌**: {realtime.get('涨跌幅', 'N/A')}% (涨跌额: {realtime.get('涨跌额', 'N/A')})")
        sections.append(f"- **今开**: ¥{realtime.get('今开', 'N/A')} | **最高**: ¥{realtime.get('最高', 'N/A')} | **最低**: ¥{realtime.get('最低', 'N/A')}")
        sections.append(f"- **昨收**: ¥{realtime.get('昨收', 'N/A')}")
        sections.append(f"- **成交量**: {realtime.get('成交量', 'N/A')} | **成交额**: {realtime.get('成交额', 'N/A')}")
    else:
        sections.append("\n## ⚠ 未获取到实时行情, 以下分析基于历史收盘数据")

    # ── Section 1: Recent OHLCV (last 20 trading days) ──
    ohlcv_path = os.path.join(STOCK_DATA_DIR, symbol, "daily.csv")
    if os.path.isfile(ohlcv_path):
        try:
            df = pd.read_csv(ohlcv_path)
            if len(df) > 20:
                df = df.tail(20)
            sections.append("\n## 近20日行情数据 (OHLCV)")
            sections.append("| 日期 | 开盘 | 最高 | 最低 | 收盘 | 成交量 | 涨跌幅% |")
            sections.append("|------|------|------|------|------|--------|---------|")
            for _, row in df.iterrows():
                date = str(row.get("date", row.get("日期", "")))[:10]
                o = row.get("open", row.get("开盘", ""))
                h = row.get("high", row.get("最高", ""))
                l = row.get("low", row.get("最低", ""))
                c = row.get("close", row.get("收盘", ""))
                v = row.get("volume", row.get("成交量", ""))
                chg = row.get("change_pct", row.get("涨跌幅", ""))
                sections.append(f"| {date} | {o} | {h} | {l} | {c} | {v} | {chg} |")
        except Exception:
            pass

    # ── Section 2: Full technical analysis ──
    sections.append("\n## 技术分析")
    price = tech.get("price", {})
    sections.append(f"收盘价: ¥{price.get('close', 'N/A')} | 涨跌: {price.get('change_pct', 'N/A')}%")

    signals = tech.get("signals", {})
    if signals:
        sections.append(f"综合判断: {tech.get('overall', '中性')}")
        for k, v in signals.items():
            sections.append(f"  - {k}: {v}")

    indicators = tech.get("indicators", {})
    if indicators:
        sections.append("关键指标:")
        for k, v in indicators.items():
            if v is not None:
                sections.append(f"  - {k}: {v}")

    sr = tech.get("support_resistance", {})
    if sr:
        sections.append("支撑阻力:")
        for k, v in sr.items():
            sections.append(f"  - {k}: {v}")

    patterns = tech.get("patterns", [])
    if patterns:
        sections.append("K线形态: " + ", ".join(
            f"{p['name']}({p['direction']}, 可靠度={p.get('reliability','?')})" for p in patterns))

    bullish = tech.get("bullish_signals", [])
    bearish = tech.get("bearish_signals", [])
    if bullish:
        sections.append("看涨信号: " + ", ".join(bullish))
    if bearish:
        sections.append("看跌信号: " + ", ".join(bearish))

    # ── Section 3: Fundamentals (full detail) ──
    sections.append("\n## 基本面分析")
    fin = fund.get("financials", {})
    if fin:
        for k, v in fin.items():
            if v is not None:
                sections.append(f"  - {k}: {v}")

    val = fund.get("valuation", {})
    if val:
        sections.append("估值:")
        for k, v in val.items():
            if v is not None:
                sections.append(f"  - {k}: {v}")

    if fund_score:
        sections.append(f"基本面综合评分: {fund_score.get('total_score', 'N/A')}/100")
        dims = fund_score.get("dimensions", {})
        for dim_name, dim_data in dims.items():
            if isinstance(dim_data, dict):
                sections.append(f"  - {dim_name}: {dim_data.get('score', 'N/A')}/100 ({dim_data.get('detail', '')})")

    # ── Section 4: Sentiment (all articles) ──
    sections.append("\n## 新闻情绪")
    sections.append(f"综合得分: {sentiment.get('daily_score', 0):+.3f} (共{sentiment.get('article_count', 0)}条)")
    articles = sentiment.get("articles", [])
    if articles:
        sections.append("| 得分 | 标题 | 原因 |")
        sections.append("|------|------|------|")
        for a in sorted(articles, key=lambda x: abs(x.get("score", 0)), reverse=True)[:8]:
            sections.append(f"| {a.get('score', 0):+.2f} | {a.get('title', '')[:60]} | {a.get('reason', '')[:50]} |")

    # ── Section 5: ML predictions ──
    xgb = data.get("xgb_prediction")
    if xgb and "prediction" in xgb:
        sections.append("\n## XGBoost 机器学习预测")
        sections.append(f"预测方向: {xgb['prediction']} (置信度: {xgb.get('confidence', 0):.1%})")
        probs = xgb.get("probabilities", {})
        if probs:
            sections.append(f"概率分布: 涨={probs.get('涨', 0):.1%}, 平={probs.get('平', 0):.1%}, 跌={probs.get('跌', 0):.1%}")
        wf = xgb.get("walk_forward", {})
        if wf:
            sections.append(f"Walk-Forward 准确率: {wf.get('overall_accuracy', 0):.1%} (共{wf.get('n_splits', '?')}轮验证)")
        feats = xgb.get("feature_importance", [])[:10]
        if feats:
            sections.append("特征重要性 TOP 10:")
            for f in feats:
                sections.append(f"  - {f['name']}: {f['importance']:.4f}")

    # ── Section 6: Price prediction (if exists) ──
    pp_path = os.path.join(STOCK_DATA_DIR, symbol, "price_prediction.json")
    if os.path.isfile(pp_path):
        try:
            with open(pp_path, encoding="utf-8") as f:
                pp = json.load(f)
            sections.append("\n## 明日价格预测 (XGBoost回归)")
            if pp.get("predictions"):
                pred = pp["predictions"]
                sections.append(f"预测收盘价: ¥{pred.get('close', 'N/A')}")
                sections.append(f"预测最高价: ¥{pred.get('high', 'N/A')}")
                sections.append(f"预测最低价: ¥{pred.get('low', 'N/A')}")
            if pp.get("change_pct"):
                chg = pp["change_pct"]
                sections.append(f"预测涨跌幅: 收盘{chg.get('close', 0):+.2f}%, 最高{chg.get('high', 0):+.2f}%, 最低{chg.get('low', 0):+.2f}%")
        except Exception:
            pass

    # ── Section 7: Fund flow / Smart money ──
    try:
        from china_market_data import stock_fund_flow_signals
        ff = stock_fund_flow_signals(symbol)
        if ff and ff.get("data_days", 0) >= 3:
            sections.append("\n## 资金流向与聪明钱分析")
            sections.append(f"聪明钱阶段: {ff.get('smart_money_phase', '无信号')}")
            sections.append(f"布局得分: {ff.get('accumulation_score', 0)}/100")
            sections.append(f"3日主力净流入: {ff.get('main_net_3d', 0)}")
            sections.append(f"10日主力净流入: {ff.get('main_net_10d', 0)}")
            sections.append(f"3日主力净占比: {ff.get('main_pct_3d', 0)}%")
            sections.append(f"超大单占比: {ff.get('super_large_ratio', 0)}")
            sections.append(f"价格-资金背离度: {ff.get('fund_price_divergence', 0)}")
            detail = ff.get("detail", "")
            if detail:
                sections.append(f"判断: {detail}")
    except Exception:
        pass

    # ── Section 8: Market context ──
    try:
        from market_sentiment import get_market_sentiment
        ms = get_market_sentiment()
        if ms:
            sections.append("\n## 大盘环境")
            if ms.get("fear_greed"):
                fg = ms["fear_greed"]
                sections.append(f"CNN恐惧贪婪指数: {fg.get('value', 'N/A')} ({fg.get('label', '')})")
            if ms.get("vix"):
                sections.append(f"VIX波动率: {ms['vix'].get('value', 'N/A')}")
    except Exception:
        pass

    return "\n".join(sections)


def generate_prediction_deepseek(symbol: str, realtime_quote: dict | None = None, cost_price: float | None = None) -> dict:
    """生成 AI 综合预测报告 via DeepSeek API (deepseek-v4-flash with thinking).

    与本地 Ollama 版本相比，DeepSeek 版本:
    1. 提供完整 20 日 OHLCV 原始数据供模型自行分析趋势
    2. 包含所有技术指标细节（不只是关键指标摘要）
    3. 包含资金流向和聪明钱分析
    4. 包含明日价格预测数据
    5. 包含大盘恐惧贪婪指数等市场环境
    6. 更严格的系统提示词，要求多维度交叉验证和概率化判断

    Returns dict with:
      - report: str (full markdown report)
      - reasoning: str (chain-of-thought from deepseek-v4-flash thinking)
      - model: str
      - usage: dict (token usage)
      - error: str (if failed)
    """
    from config import call_deepseek

    log.info("开始生成 %s DeepSeek 深度预测...", symbol)

    data = _load_or_compute(symbol, sentiment_provider="deepseek")
    if realtime_quote:
        data["realtime_quote"] = realtime_quote
    elif not data.get("realtime_quote"):
        try:
            from fetch_market_data import fetch_realtime_quote
            data["realtime_quote"] = fetch_realtime_quote(symbol)
        except Exception as e:
            log.warning("获取实时行情失败: %s", e)
    analysis_text = _build_deepseek_prompt(symbol, data)
    name = data.get("fundamental", {}).get("profile", {}).get("name") or symbol

    cost_system_extra = ""
    if cost_price is not None and cost_price > 0:
        cost_system_extra = (
            f"\n\n**【重要：用户持仓信息】**\n"
            f"用户已持有该股，成本价: ¥{cost_price:.2f}。\n"
            f"报告中必须新增一个独立板块 '## 持仓操作策略（成本 ¥{cost_price:.2f}）'，根据当前盈亏状态给出建议：\n\n"
            f"**如果当前浮亏（现价 < 成本价）：**\n"
            f"- 是否建议补仓（结合技术面支撑位和资金流向判断）\n"
            f"- 建议补仓价位区间（需低于成本价，说明理由）\n"
            f"- 建议补仓比例（当前仓位的百分比）\n"
            f"- 补仓后的摊薄成本计算（假设等量补仓）\n"
            f"- 不补仓情况下的回本时间估计\n"
            f"- 最终止损线（跌破什么价位不宜再持有）\n\n"
            f"**如果当前浮盈（现价 >= 成本价）：**\n"
            f"- 是否建议止盈卖出？还是继续持有？\n"
            f"- 目标止盈价位（具体价格或价格区间）\n"
            f"- 分批止盈方案（不同价位卖出不同比例）\n"
            f"- 继续持有条件（什么指标/信号支持继续拿着）\n"
            f"- 回撤保护价（从高点回落到什么价位必须卖出锁利）\n\n"
            f"原则：浮亏时补仓前提是基本面未恶化；浮盈时用移动止盈保护利润，不贪。"
        )

    system_prompt = (
        "你是一位顶级A股量化分析师，精通技术分析、基本面分析、资金流向分析和市场微观结构。\n"
        "你正在使用 deepseek-v4-flash (thinking mode) 进行深度推理分析，请充分利用你的推理能力。\n\n"
        "分析要求（必须全部满足）：\n"
        "1. **多维度交叉验证**: 不要简单罗列每个维度的结论，而是找出不同维度之间的矛盾和共振点。"
        "例如：资金在流入但技术面偏弱意味着什么？基本面优秀但估值偏高怎么解读？\n"
        "2. **概率化判断**: 给出具体的概率估计而非模糊描述。"
        "例如：'70%概率1周内向上突破¥10.04' 而非 '可能会上涨'\n"
        "3. **A股特色分析**: 必须考虑T+1交易制度、涨跌停板制度、散户占比高的市场特征、"
        "主力资金行为（吸筹/拉升/出货）对股价的影响\n"
        "4. **利用原始数据**: 我提供了近20日的原始行情数据，请自行分析量价关系、趋势强度、"
        "成交量变化趋势、是否有放量/缩量特征\n"
        "5. **资金流向深度解读**: 分析主力资金的真实意图 — 是在吸筹布局还是借利好出货？"
        "超大单占比说明什么？\n"
        "6. **给出差异化建议**: 不同仓位水平的投资者应该如何操作？\n"
        "   - 空仓者：是否建仓？建仓价位？分几批？\n"
        "   - 轻仓者：是否加仓？在什么条件下加？\n"
        "   - 重仓者：是否减仓？止盈/止损策略？\n"
        "7. **风险量化**: 给出具体的最大回撤估计和止损价位，而非泛泛而谈\n\n"
        "报告结构：\n"
        "1. 一句话结论（含方向、概率、时间框架）\n"
        "2. 多维度交叉分析（技术×资金×基本面×情绪的交叉验证）\n"
        "3. 量价关系分析（基于原始OHLCV数据）\n"
        "4. 关键矛盾点（不同信号的冲突及解读）\n"
        "5. 三类投资者操作建议（空仓/轻仓/重仓）\n"
        "6. 关键价位与触发条件\n"
        "7. 风险评估与止损策略\n"
        "8. 未来1周/2周情景分析（乐观/中性/悲观三种情景及概率）"
        + cost_system_extra
    )

    cost_user_extra = ""
    if cost_price is not None and cost_price > 0:
        current = None
        if realtime_quote and realtime_quote.get("最新价"):
            current = realtime_quote["最新价"]
        elif data.get("technical", {}).get("price", {}).get("close"):
            current = data["technical"]["price"]["close"]
        pnl_str = ""
        if current:
            pnl_pct = (current - cost_price) / cost_price * 100
            pnl_str = f"（当前{'浮盈' if pnl_pct >= 0 else '浮亏'} {pnl_pct:+.2f}%）"
        if current and current >= cost_price:
            cost_user_extra = (
                f"\n\n【用户持仓 — 浮盈】成本价 ¥{cost_price:.2f} {pnl_str}\n"
                f"请重点给出：止盈目标价、分批卖出策略、回撤保护价（利润回吐到什么程度必须卖）。"
            )
        else:
            cost_user_extra = (
                f"\n\n【用户持仓 — 浮亏】成本价 ¥{cost_price:.2f} {pnl_str}\n"
                f"用户不希望割肉，请重点给出补仓策略（价位、比例、摊薄成本）和回本路径。"
            )

    user_prompt = (
        f"请对 {name}({symbol}) 进行深度分析。以下是完整的多维度数据：\n\n"
        f"{analysis_text}{cost_user_extra}\n\n"
        f"请基于以上所有数据，按照要求的结构进行深度分析。"
        f"特别注意：请自行从原始OHLCV数据中发现量价关系趋势，不要只看我提供的技术指标摘要。"
    )

    result = call_deepseek(system_prompt, user_prompt, max_tokens=8192)

    if not result["ok"]:
        log.error("DeepSeek 预测 %s 失败: %s", symbol, result.get("error"))
        return {"error": result["error"]}

    content = result["content"]
    reasoning = result.get("reasoning_content", "")

    header = f"# {name} ({symbol}) DeepSeek 深度分析报告\n"
    header += f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 模型: {result['model']} (DeepSeek API)\n\n"

    report = header + content

    out_path = os.path.join(STOCK_DATA_DIR, symbol, "prediction-report-deepseek.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    log.info("DeepSeek 深度分析报告已保存 → %s", out_path)

    return {
        "report": report,
        "reasoning": reasoning,
        "model": result["model"],
        "usage": result.get("usage", {}),
    }


def generate_prediction_verdict(symbol: str, realtime_quote: dict | None = None) -> dict:
    """轻量深度复核：复用深度分析的完整数据装配，但只输出结构化方向判断。

    用于 scanner Top5 复核——保证短期推荐与"A股分析&AI预测"深度分析逻辑一致，
    而无需生成完整 8 段报告（max_tokens=1500, reasoning medium，约为完整报告 1/5 开销）。

    Returns dict:
      - ok: bool
      - direction: "看多" / "看空" / "中性"
      - confidence: int (0-100)
      - reason: str (一句话核心理由)
      - veto_reason: str (若看空，给出否决依据)
      - usage: dict
      - error: str (if ok=False)
    """
    from config import call_deepseek

    log.info("轻量深度复核 %s ...", symbol)
    data = _load_or_compute(symbol, sentiment_provider="deepseek")
    if realtime_quote:
        data["realtime_quote"] = realtime_quote
    elif not data.get("realtime_quote"):
        try:
            from fetch_market_data import fetch_realtime_quote
            data["realtime_quote"] = fetch_realtime_quote(symbol)
        except Exception as e:
            log.warning("复核获取实时行情失败: %s", e)

    analysis_text = _build_deepseek_prompt(symbol, data)

    system_prompt = (
        "你是一位顶级A股量化分析师。基于与深度分析完全相同的多维度数据"
        "（技术×资金×基本面×情绪×原始OHLCV），给出一个**结构化方向判断**。\n\n"
        "要求：\n"
        "1. 必须交叉验证各维度，特别关注主力资金流向（净流入/净流出/出货期）与技术面的共振/矛盾。\n"
        "2. 概率化判断，给出明确方向（看多/看空/中性）与置信度。\n"
        "3. 若主力资金持续大幅净流出或处于出货期，且无压倒性反向证据，应判\"看空\"。\n"
        "4. A股T+1，追高风险需考虑。\n\n"
        "只输出一个JSON对象，不要任何其他文字或```json围栏：\n"
        '{"direction":"看空","confidence":65,"reason":"一句话核心理由","veto_reason":"若看空给出否决依据，否则留空"}\n'
        "direction 只能是 \"看多\" / \"看空\" / \"中性\"。confidence 0-100。"
    )

    result = call_deepseek(system_prompt, analysis_text, max_tokens=1500, reasoning_effort="medium")
    if not result["ok"]:
        return {"ok": False, "error": result.get("error", "DeepSeek 调用失败")}

    import re as _re
    text = result["content"].strip()
    # 防御性剥离可能的 think 标签块（DeepSeek 通常把推理放 reasoning_content，content 一般已干净）
    text = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL).strip()
    m = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, _re.DOTALL)
    if m:
        text = m.group(1)
    start = text.find("{")
    end = text.rfind("}") + 1
    parsed = None
    if start >= 0 and end > start:
        import json as _json
        try:
            parsed = _json.loads(text[start:end].replace("'", '"'))
        except (ValueError, _json.JSONDecodeError) as e:
            log.warning("复核 JSON 解析失败 %s: %s", symbol, e)
    # 回退：直接搜索含 "direction" 的 JSON 对象（抗 think 标签噪声）
    if parsed is None:
        import json as _json2
        m2 = _re.search(r'\{[^{}]*"direction"[^{}]*\}', result["content"], _re.DOTALL)
        if m2:
            try:
                parsed = _json2.loads(m2.group(0).replace("'", '"'))
            except (ValueError, _json2.JSONDecodeError):
                parsed = None

    if parsed is not None:
        direction = str(parsed.get("direction", "")).strip()
        if "空" in direction or "跌" in direction:
            direction = "看空"
        elif "多" in direction or "涨" in direction:
            direction = "看多"
        else:
            direction = "中性"
        return {
            "ok": True,
            "direction": direction,
            "confidence": int(parsed.get("confidence", 50)),
            "reason": parsed.get("reason", ""),
            "veto_reason": parsed.get("veto_reason", ""),
            "usage": result.get("usage", {}),
        }

    # 解析失败时，从原文做兜底关键词判断
    low = text
    bearish_kw = ["看空", "看跌", "卖出", "减仓", "止损", "出货", "净流出", "空头"]
    bullish_kw = ["看多", "看涨", "买入", "加仓", "多头"]
    bearish = sum(1 for k in bearish_kw if k in low)
    bullish = sum(1 for k in bullish_kw if k in low)
    direction = "看空" if bearish > bullish else ("看多" if bullish > bearish else "中性")
    return {
        "ok": True,
        "direction": direction,
        "confidence": 50,
        "reason": "LLM结构化输出解析失败，基于关键词兜底判断",
        "veto_reason": text[:200] if direction == "看空" else "",
        "usage": result.get("usage", {}),
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sym = sys.argv[1] if len(sys.argv) > 1 else "600519"
    report = generate_prediction(sym, stream=False)
    print(report)
