"""
新闻情绪分析 — 使用 Ollama LLM 分析个股新闻情绪.

读取本地缓存的新闻数据, 逐条分析情绪, 汇总为每日情绪评分.
"""
import json
import os
import logging
from datetime import datetime
from glob import glob

import requests

from config import STOCK_DATA_DIR, OLLAMA_HOST, MODEL_USAGE

log = logging.getLogger(__name__)


def _load_news(symbol: str, days: int = 3) -> list[dict]:
    """加载最近 N 天的新闻."""
    news_dir = os.path.join(STOCK_DATA_DIR, symbol, "news")
    if not os.path.isdir(news_dir):
        return []

    files = sorted(glob(os.path.join(news_dir, "*.json")), reverse=True)[:days]
    articles = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, list):
                    articles.extend(data)
        except Exception:
            pass
    return articles


def analyze_sentiment_single(article: dict, stock_name: str = "") -> dict:
    """
    用 LLM 分析单条新闻的情绪.

    Returns: {"score": float, "reason": str}
    """
    title = article.get("新闻标题") or article.get("title", "")
    content = article.get("新闻内容") or article.get("content", "")
    text = f"标题: {title}\n内容: {content[:500]}" if content else f"标题: {title}"

    if not text.strip():
        return {"score": 0.0, "reason": "无内容"}

    model = MODEL_USAGE.get("sentiment_batch", "qwen3:1.7b")

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是A股市场分析师。分析新闻对股票的情绪影响。\n"
                            "只输出JSON: {\"score\": 数字, \"reason\": \"一句话\"}\n"
                            "score范围: -1.0(非常利空) 到 +1.0(非常利好), 0=中性\n"
                            "不要输出其他内容。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"股票: {stock_name}\n{text}\n\n请分析情绪:",
                    },
                ],
                "stream": False,
                "think": False,
                "options": {"temperature": 0.1, "num_predict": 200},
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "")

        raw = raw.strip()
        if "<think>" in raw:
            raw = raw.split("</think>")[-1].strip()

        if "{" in raw:
            json_str = raw[raw.index("{"):raw.rindex("}") + 1]
            result = json.loads(json_str)
            return {
                "score": max(-1.0, min(1.0, float(result.get("score", 0)))),
                "reason": result.get("reason", ""),
            }
    except Exception as e:
        log.warning("情绪分析失败: %s", e)

    return {"score": 0.0, "reason": "分析失败"}


def _resolve_stock_name(symbol: str, stock_name: str = "") -> str:
    """Resolve stock display name from profile.json if not provided."""
    if stock_name:
        return stock_name
    profile_path = os.path.join(STOCK_DATA_DIR, symbol, "profile.json")
    if os.path.isfile(profile_path):
        try:
            with open(profile_path, encoding="utf-8") as f:
                return json.load(f).get("股票简称", symbol)
        except Exception:
            pass
    return symbol


def _aggregate_sentiment(symbol: str, stock_name: str, analyzed: list[dict]) -> dict:
    """Aggregate per-article scores into the standard sentiment result dict.

    `analyzed` items: {"title", "score", "reason", "date"}.
    """
    scores = [a["score"] for a in analyzed]
    daily_score = sum(scores) / len(scores) if scores else 0.0

    positive = sorted(analyzed, key=lambda x: x["score"], reverse=True)
    negative = sorted(analyzed, key=lambda x: x["score"])

    top_pos = positive[0]["title"] if positive and positive[0]["score"] > 0 else ""
    top_neg = negative[0]["title"] if negative and negative[0]["score"] < 0 else ""

    dated_articles = sorted(
        [a for a in analyzed if a.get("date")],
        key=lambda x: x["date"]
    )
    dated_scores = [a["score"] for a in dated_articles]
    if len(dated_scores) >= 3:
        first_half = dated_scores[:len(dated_scores) // 2]
        second_half = dated_scores[len(dated_scores) // 2:]
        avg_first = sum(first_half) / len(first_half) if first_half else 0
        avg_second = sum(second_half) / len(second_half) if second_half else 0
        diff = avg_second - avg_first
        if diff > 0.2:
            trend = "improving"
        elif diff < -0.2:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "stable"

    shift_alert = False
    if len(scores) >= 2:
        recent_avg = sum(scores[:5]) / min(5, len(scores))
        if abs(recent_avg - daily_score) > 0.5:
            shift_alert = True

    return {
        "symbol": symbol,
        "name": stock_name,
        "daily_score": round(daily_score, 3),
        "article_count": len(analyzed),
        "articles": analyzed,
        "top_positive": top_pos,
        "top_negative": top_neg,
        "trend": trend,
        "shift_alert": shift_alert,
        "analyzed_at": datetime.now().isoformat(),
    }


def analyze_stock_sentiment(symbol: str, stock_name: str = "", days: int = 3) -> dict:
    """
    分析某只股票的新闻情绪 (本地 Ollama 打分).

    结果写入 sentiment.json, 供本地分析路径使用.

    Returns:
    {
        "symbol": "600519",
        "daily_score": 0.35,
        "article_count": 10,
        "articles": [ { "title": ..., "score": ..., "reason": ... } ],
        "top_positive": "...",
        "top_negative": "...",
        "trend": "improving" | "declining" | "stable"
    }
    """
    articles = _load_news(symbol, days)
    if not articles:
        return {"symbol": symbol, "daily_score": 0.0, "article_count": 0,
                "articles": [], "error": "无新闻数据"}

    stock_name = _resolve_stock_name(symbol, stock_name)
    log.info("分析 %s (%s) 的 %d 条新闻情绪 (Ollama)...", symbol, stock_name, len(articles))

    analyzed = []
    for art in articles[:20]:
        title = art.get("新闻标题") or art.get("title", "")
        result = analyze_sentiment_single(art, stock_name)
        analyzed.append({
            "title": title,
            "score": result["score"],
            "reason": result["reason"],
            "date": art.get("发布时间") or art.get("date", ""),
        })
        log.info("  [%.2f] %s", result["score"], title[:40])

    result = _aggregate_sentiment(symbol, stock_name, analyzed)
    result["provider"] = "ollama"

    out_path = os.path.join(STOCK_DATA_DIR, symbol, "sentiment.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    log.info("情绪分析完成 → %s (得分: %.3f)", out_path, result["daily_score"])

    return result


def analyze_stock_sentiment_deepseek(symbol: str, stock_name: str = "", days: int = 3) -> dict:
    """
    分析某只股票的新闻情绪 (DeepSeek 批量打分).

    单次 DeepSeek 调用批量评分所有新闻, 结果写入 sentiment-deepseek.json,
    与 Ollama 版 (sentiment.json) 互不干扰, 供 DeepSeek 分析路径独立使用.
    """
    from config import call_deepseek

    articles = _load_news(symbol, days)
    if not articles:
        return {"symbol": symbol, "daily_score": 0.0, "article_count": 0,
                "articles": [], "error": "无新闻数据"}

    stock_name = _resolve_stock_name(symbol, stock_name)
    articles = articles[:20]
    log.info("DeepSeek 情绪分析 %s (%s) %d 条新闻...", symbol, stock_name, len(articles))

    # 构建批量打分提示词: 一次调用返回所有新闻的分数
    lines = [
        f"股票: {stock_name}",
        f"请对以下 {len(articles)} 条新闻逐条分析对该公司股价的情绪影响。",
        "只输出JSON数组, 不要输出任何其他内容。格式:",
        '[{"i":0,"score":0.0,"reason":"一句话"},...]',
        "score范围: -1.0(非常利空) 到 +1.0(非常利好), 0=中性",
        "reason 为简短中文一句话。",
        "",
    ]
    for i, art in enumerate(articles):
        title = art.get("新闻标题") or art.get("title", "")
        content = art.get("新闻内容") or art.get("content", "")
        body = f"标题: {title}" + (f"\n内容: {content[:300]}" if content else "")
        lines.append(f"[{i}] {body}")

    system_prompt = "你是A股市场分析师。分析每条新闻对股票的情绪影响。只输出JSON数组, 不输出其他内容。"
    user_prompt = "\n".join(lines)

    resp = call_deepseek(system_prompt, user_prompt, max_tokens=2048, reasoning_effort="low")

    scores_map: dict[int, dict] = {}
    if resp.get("ok"):
        raw = (resp.get("content") or "").strip()
        start, end = raw.find("["), raw.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                arr = json.loads(raw[start:end + 1])
                for item in arr:
                    if not isinstance(item, dict):
                        continue
                    idx = item.get("i", item.get("index"))
                    try:
                        idx = int(idx)
                    except (TypeError, ValueError):
                        continue
                    try:
                        score = max(-1.0, min(1.0, float(item.get("score", 0))))
                    except (TypeError, ValueError):
                        score = 0.0
                    reason = str(item.get("reason", ""))[:60]
                    scores_map[idx] = {"score": score, "reason": reason}
            except Exception as e:
                log.warning("DeepSeek 情绪 JSON 解析失败: %s", e)
    else:
        log.warning("DeepSeek 情绪打分失败: %s", resp.get("error"))

    analyzed = []
    for i, art in enumerate(articles):
        title = art.get("新闻标题") or art.get("title", "")
        sc = scores_map.get(i, {"score": 0.0, "reason": "未返回"})
        analyzed.append({
            "title": title,
            "score": sc["score"],
            "reason": sc["reason"],
            "date": art.get("发布时间") or art.get("date", ""),
        })
        log.info("  [%.2f] %s", sc["score"], title[:40])

    result = _aggregate_sentiment(symbol, stock_name, analyzed)
    result["provider"] = "deepseek"

    out_path = os.path.join(STOCK_DATA_DIR, symbol, "sentiment-deepseek.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    log.info("DeepSeek 情绪分析完成 → %s (得分: %.3f)", out_path, result["daily_score"])

    return result


def generate_sentiment_report(symbol: str) -> str:
    """生成中文情绪分析 Markdown 报告."""
    path = os.path.join(STOCK_DATA_DIR, symbol, "sentiment.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = analyze_stock_sentiment(symbol)

    name = data.get("name", symbol)
    score = data.get("daily_score", 0)
    articles = data.get("articles", [])

    if score > 0.3:
        mood = "偏乐观 🟢"
    elif score > 0:
        mood = "略偏正面 🟡"
    elif score > -0.3:
        mood = "略偏负面 🟡"
    else:
        mood = "偏悲观 🔴"

    lines = []
    lines.append(f"# {name} ({symbol}) 新闻情绪分析")
    lines.append(f"> 综合情绪: **{score:+.3f}** ({mood}) | 分析新闻: {len(articles)} 条")
    lines.append("")

    if articles:
        lines.append("## 新闻情绪明细")
        lines.append("")
        lines.append("| 情绪 | 得分 | 标题 | 分析 |")
        lines.append("|------|------|------|------|")
        for a in sorted(articles, key=lambda x: x["score"], reverse=True):
            s = a["score"]
            icon = "🟢" if s > 0.2 else "🔴" if s < -0.2 else "⚪"
            lines.append(f"| {icon} | {s:+.2f} | {a['title'][:40]} | {a['reason'][:30]} |")
        lines.append("")

    if data.get("top_positive"):
        lines.append(f"**最利好:** {data['top_positive']}")
    if data.get("top_negative"):
        lines.append(f"**最利空:** {data['top_negative']}")

    lines.append("")
    lines.append("---")
    lines.append(f"*分析时间: {data.get('analyzed_at', '')[:16]}*")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sym = sys.argv[1] if len(sys.argv) > 1 else "600519"
    report = generate_sentiment_report(sym)
    print(report)
