"""
Stock market data fetcher using akshare.

Fetches historical OHLCV, real-time quotes, financial summaries,
and company profiles for A-share stocks.

All output files are stored under STOCK_DATA_DIR/{symbol}/.
"""
import json
import os
import time
import logging
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd
import requests

from config import STOCK_DATA_DIR, STOCK_CACHE_DIR, STOCK_PROXY

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_RETRY_DELAY = 1
_MAX_RETRIES = 2
_PROXIES = {"http": STOCK_PROXY, "https": STOCK_PROXY} if STOCK_PROXY else None


def _symbol_dir(symbol: str) -> str:
    d = os.path.join(STOCK_DATA_DIR, symbol)
    os.makedirs(d, exist_ok=True)
    return d


def _sina_prefix(symbol: str) -> str:
    """Map stock code to Sina exchange prefix (sh/sz)."""
    if symbol.startswith(("6", "5", "9")):
        return "sh"
    return "sz"


def _retry(fn, *args, retries=_MAX_RETRIES, **kwargs):
    """Retry wrapper for flaky network calls."""
    last_err = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            log.warning("尝试 %d/%d 失败: %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                time.sleep(_RETRY_DELAY * (attempt + 1))
    raise last_err


def _fetch_ohlcv_sina(symbol: str, datalen: int = 500) -> pd.DataFrame:
    """通过新浪财经 API 获取日线数据 (备用方案).

    注意: 不支持 start_date/end_date 和复权参数, 仅返回最近 datalen 根日线 (不复权).
    """
    sina_symbol = f"{_sina_prefix(symbol)}{symbol}"

    url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {"symbol": sina_symbol, "scale": "240", "ma": "no", "datalen": str(datalen)}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn",
    }

    resp = requests.get(url, params=params, headers=headers, timeout=30, proxies=_PROXIES)
    resp.raise_for_status()
    data = resp.json()

    if not data:
        raise ValueError(f"新浪返回空数据: {symbol}")

    rows = []
    for item in data:
        rows.append({
            "日期": item["day"],
            "开盘": float(item["open"]),
            "收盘": float(item["close"]),
            "最高": float(item["high"]),
            "最低": float(item["low"]),
            "成交量": int(item["volume"]),
            "成交额": 0.0,
            "振幅": 0.0,
            "涨跌幅": 0.0,
            "涨跌额": 0.0,
            "换手率": 0.0,
        })

    df = pd.DataFrame(rows)
    if len(df) > 1:
        df["涨跌额"] = df["收盘"] - df["收盘"].shift(1)
        df["涨跌幅"] = (df["涨跌额"] / df["收盘"].shift(1) * 100).round(2)
        df["振幅"] = ((df["最高"] - df["最低"]) / df["收盘"].shift(1) * 100).round(2)
    return df


def fetch_daily_ohlcv(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    adjust: str = "qfq",
) -> pd.DataFrame:
    """
    获取个股日线历史数据 (OHLCV).

    Args:
        symbol: 股票代码, e.g. "600519"
        start_date: 起始日期 YYYYMMDD, 默认2年前
        end_date: 结束日期 YYYYMMDD, 默认今天
        adjust: 复权类型 "qfq"(前复权) / "hfq"(后复权) / ""(不复权)

    Returns:
        DataFrame with columns: 日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率
    """
    if not end_date:
        end_date = datetime.now().strftime("%Y%m%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")

    log.info("获取 %s 日线数据 %s ~ %s (复权: %s)", symbol, start_date, end_date, adjust)
    df = None
    try:
        import signal
        import threading

        result_holder = [None, None]

        def _ak_fetch():
            try:
                result_holder[0] = ak.stock_zh_a_hist(
                    symbol=symbol, period="daily",
                    start_date=start_date, end_date=end_date, adjust=adjust,
                )
            except Exception as e:
                result_holder[1] = e

        t = threading.Thread(target=_ak_fetch, daemon=True)
        t.start()
        t.join(timeout=20)
        if t.is_alive() or result_holder[1] or result_holder[0] is None:
            raise TimeoutError(result_holder[1] or "akshare 超时")
        df = result_holder[0]
    except Exception as e1:
        log.warning("akshare API 失败 (%s), 尝试新浪财经备用 API (注意: 备用方案不支持日期范围和复权参数)", e1)
        df = _fetch_ohlcv_sina(symbol)

    csv_path = os.path.join(_symbol_dir(symbol), "daily.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    log.info("已保存 %s (%d 行)", csv_path, len(df))
    return df


def _fetch_realtime_sina(symbol: str) -> dict:
    """通过新浪实时行情 API 获取单只股票报价 (轻量, 不需下载全市场)."""
    sina_sym = f"{_sina_prefix(symbol)}{symbol}"
    url = f"https://hq.sinajs.cn/list={sina_sym}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn",
    }
    resp = requests.get(url, headers=headers, timeout=10, proxies=_PROXIES)
    resp.raise_for_status()
    text = resp.text.strip()

    parts_start = text.find('"')
    parts_end = text.rfind('"')
    if parts_start == -1 or parts_end <= parts_start:
        raise ValueError(f"新浪实时行情返回无效: {text[:100]}")
    raw = text[parts_start + 1:parts_end]
    fields = raw.split(",")
    if len(fields) < 32:
        raise ValueError(f"新浪实时行情字段不足: {len(fields)}")

    yesterday_close = float(fields[2]) if fields[2] else 0
    latest = float(fields[3]) if fields[3] else 0
    change_pct = round((latest - yesterday_close) / yesterday_close * 100, 2) if yesterday_close else 0

    return {
        "代码": symbol,
        "名称": fields[0],
        "今开": float(fields[1]) if fields[1] else None,
        "昨收": yesterday_close or None,
        "最新价": latest or None,
        "最高": float(fields[4]) if fields[4] else None,
        "最低": float(fields[5]) if fields[5] else None,
        "成交量": int(float(fields[8])) if fields[8] else None,
        "成交额": float(fields[9]) if fields[9] else None,
        "涨跌幅": change_pct,
        "涨跌额": round(latest - yesterday_close, 2) if yesterday_close else None,
    }


def fetch_realtime_quote(symbol: str) -> dict:
    """
    获取个股实时行情.

    先尝试新浪单股API (轻量), 失败后回退到 akshare 全市场接口.

    Returns dict with keys: 代码,名称,最新价,涨跌幅,涨跌额,成交量,成交额, etc.
    """
    log.info("获取 %s 实时行情", symbol)

    record = None
    try:
        record = _fetch_realtime_sina(symbol)
        log.info("通过新浪API获取实时行情成功")
    except Exception as e:
        log.warning("新浪实时行情失败 (%s), 尝试 akshare", e)
        try:
            df = _retry(ak.stock_zh_a_spot_em)
            row = df[df["代码"] == symbol]
            if not row.empty:
                record = row.iloc[0].to_dict()
        except Exception as e2:
            raise RuntimeError(f"实时行情获取失败 (新浪 + akshare): {e2}") from e2

    if not record:
        log.warning("未找到股票 %s", symbol)
        return {}

    out_path = os.path.join(_symbol_dir(symbol), "realtime.json")
    record["_fetched_at"] = datetime.now().isoformat()

    for k, v in record.items():
        if isinstance(v, float) and (pd.isna(v) or v != v):
            record[k] = None

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2, default=str)
    log.info("已保存实时行情 → %s", out_path)
    return record


def fetch_company_profile(symbol: str) -> dict:
    """
    获取公司基本信息 (行业, 总市值, 流通市值等).
    Tries akshare first, falls back to EastMoney CompanySurvey API.
    """
    log.info("获取 %s 公司信息", symbol)

    profile = _fetch_profile_akshare(symbol)
    if not profile or not profile.get("行业"):
        fallback = _fetch_profile_em_survey(symbol)
        if fallback:
            profile = {**profile, **fallback} if profile else fallback

    if profile:
        profile["_fetched_at"] = datetime.now().isoformat()
        out_path = os.path.join(_symbol_dir(symbol), "profile.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2, default=str)
        log.info("已保存公司信息 → %s", out_path)
    return profile


def _fetch_profile_akshare(symbol: str) -> dict:
    try:
        df = _retry(ak.stock_individual_info_em, symbol=symbol)
        profile = {}
        for _, row in df.iterrows():
            profile[row.iloc[0]] = row.iloc[1]
        return profile
    except Exception as e:
        log.warning("akshare 公司信息失败 %s: %s", symbol, e)
        return {}


def _fetch_profile_em_survey(symbol: str) -> dict:
    """Fallback: EastMoney CompanySurvey web API (different endpoint, more reliable)."""
    try:
        prefix = "SH" if symbol.startswith(("6", "5", "9")) else "SZ"
        url = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax"
        resp = requests.get(
            url, params={"code": f"{prefix}{symbol}"},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://emweb.securities.eastmoney.com",
            },
            timeout=15, proxies=_PROXIES,
        )
        resp.raise_for_status()
        data = resp.json()
        jbzl = data.get("jbzl", {})
        if not jbzl:
            return {}
        profile = {
            "股票代码": jbzl.get("agdm", symbol),
            "股票简称": jbzl.get("agjc", ""),
            "行业": jbzl.get("sshy", ""),
            "证监会行业": jbzl.get("sszjhhy", ""),
        }
        profile = {k: v for k, v in profile.items() if v}
        log.info("CompanySurvey fallback 成功 %s: 行业=%s", symbol, profile.get("行业", "?"))
        return profile
    except Exception as e:
        log.warning("CompanySurvey fallback 失败 %s: %s", symbol, e)
        return {}


def fetch_stock_news(symbol: str, limit: int = 20) -> list[dict]:
    """
    获取个股新闻.

    Returns list of dicts with keys: 标题, 内容, 发布时间, 文章来源, 新闻链接
    """
    log.info("获取 %s 最新新闻 (limit=%d)", symbol, limit)
    try:
        df = _retry(ak.stock_news_em, symbol=symbol)
        if df is None or df.empty:
            log.info("无新闻数据")
            return []

        articles = df.head(limit).to_dict("records")
        today = datetime.now().strftime("%Y-%m-%d")
        news_dir = os.path.join(_symbol_dir(symbol), "news")
        os.makedirs(news_dir, exist_ok=True)
        out_path = os.path.join(news_dir, f"{today}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2, default=str)
        log.info("已保存 %d 条新闻 → %s", len(articles), out_path)
        return articles
    except Exception as e:
        log.error("获取新闻失败 %s: %s", symbol, e)
        return []


def load_daily_ohlcv(symbol: str) -> pd.DataFrame | None:
    """从本地 CSV 加载日线数据."""
    csv_path = os.path.join(_symbol_dir(symbol), "daily.csv")
    if not os.path.isfile(csv_path):
        return None
    return pd.read_csv(csv_path, encoding="utf-8-sig")


def load_realtime(symbol: str) -> dict:
    """从本地 JSON 加载最近一次实时行情."""
    path = os.path.join(_symbol_dir(symbol), "realtime.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def update_stock_data(symbol: str) -> dict:
    """
    一键更新某只股票的所有数据: 日线 + 公司信息 + 新闻.

    Returns summary dict.
    """
    summary = {"symbol": symbol, "errors": []}

    try:
        df = fetch_daily_ohlcv(symbol)
        summary["daily_rows"] = len(df)
    except Exception as e:
        summary["errors"].append(f"日线: {e}")

    try:
        profile = fetch_company_profile(symbol)
        if profile:
            summary["profile"] = True
        else:
            cached = os.path.join(_symbol_dir(symbol), "profile.json")
            if os.path.isfile(cached):
                log.info("使用缓存的公司信息")
                summary["profile"] = True
            else:
                summary["profile"] = False
    except Exception as e:
        summary["errors"].append(f"公司信息: {e}")

    try:
        news = fetch_stock_news(symbol)
        summary["news_count"] = len(news)
    except Exception as e:
        summary["errors"].append(f"新闻: {e}")

    try:
        rt = fetch_realtime_quote(symbol)
        summary["realtime"] = bool(rt)
    except Exception as e:
        summary["errors"].append(f"实时行情: {e}")

    summary["updated_at"] = datetime.now().isoformat()
    log.info("更新完成 %s: %s", symbol, summary)
    return summary


if __name__ == "__main__":
    import sys

    sym = sys.argv[1] if len(sys.argv) > 1 else "600519"
    print(f"\n=== 更新股票数据: {sym} ===\n")
    result = update_stock_data(sym)
    print(f"\n=== 结果 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
