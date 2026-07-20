"""
数据质量校验 — OHLCV 完整性、异常值检测、复权来源标记.

Phase 1.1 (ch9-enhancement-roadmap): 缺失日期检测、异常涨跌幅、验收报告.
"""
import json
import os
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from config import STOCK_DATA_DIR

log = logging.getLogger(__name__)

MIN_TRADING_DAYS = 750
MAX_GAP_CALENDAR_DAYS = 15
ANOMALY_PCT_THRESHOLD = 25.0
CHINEXT_PREFIXES = ("300", "301", "688")

OHLCV_COLUMNS = [
    "日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额",
    "振幅", "涨跌幅", "涨跌额", "换手率",
]


def daily_meta_path(symbol: str) -> str:
    return os.path.join(STOCK_DATA_DIR, symbol, "daily_meta.json")


def quality_report_path(symbol: str) -> str:
    return os.path.join(STOCK_DATA_DIR, symbol, "data_quality.json")


def load_daily_meta(symbol: str) -> dict:
    path = daily_meta_path(symbol)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def is_ml_safe(symbol: str) -> bool:
    """ML 训练应仅使用前复权数据; 新浪备用非复权数据返回 False."""
    meta = load_daily_meta(symbol)
    return meta.get("adjust_source", "qfq") == "qfq"


def _limit_pct_threshold(symbol: str) -> float:
    if symbol.startswith(CHINEXT_PREFIXES):
        return 21.0
    return 11.0


def validate_ohlcv(
    df: pd.DataFrame,
    symbol: str,
    adjust_source: str = "qfq",
) -> dict:
    """
    校验日线数据质量.

    Returns report dict with keys: passed, trading_days, issues, warnings, stats.
    """
    report = {
        "symbol": symbol,
        "adjust_source": adjust_source,
        "checked_at": datetime.now().isoformat(),
        "trading_days": 0,
        "passed": False,
        "issues": [],
        "warnings": [],
        "stats": {},
    }

    if df is None or df.empty:
        report["issues"].append("数据为空")
        return report

    work = df.copy()
    if "日期" not in work.columns:
        report["issues"].append("缺少日期列")
        return report

    work["日期"] = pd.to_datetime(work["日期"], errors="coerce")
    work = work.dropna(subset=["日期"]).sort_values("日期").reset_index(drop=True)
    report["trading_days"] = len(work)

    if len(work) < MIN_TRADING_DAYS:
        report["warnings"].append(
            f"交易日不足 {MIN_TRADING_DAYS} 天 (当前 {len(work)} 天)"
        )

    if adjust_source != "qfq":
        report["warnings"].append(
            f"复权来源为 {adjust_source}, 不宜用于 ML 训练"
        )

    # duplicate dates
    dupes = work["日期"].duplicated().sum()
    if dupes:
        report["issues"].append(f"重复日期 {dupes} 条")

    for col in ["开盘", "收盘", "最高", "最低"]:
        if col in work.columns:
            nulls = work[col].isna().sum()
            if nulls:
                report["issues"].append(f"{col} 缺失 {nulls} 条")

    if "收盘" in work.columns:
        zeros = (pd.to_numeric(work["收盘"], errors="coerce") <= 0).sum()
        if zeros:
            report["issues"].append(f"收盘价 <= 0 共 {zeros} 条")

    # calendar gaps (停牌/节假日)
    if len(work) >= 2:
        gaps = work["日期"].diff().dt.days.dropna()
        large_gaps = gaps[gaps > MAX_GAP_CALENDAR_DAYS]
        if len(large_gaps):
            report["warnings"].append(
                f"存在 {len(large_gaps)} 处日期间隔 > {MAX_GAP_CALENDAR_DAYS} 天 "
                f"(最大 {int(large_gaps.max())} 天, 可能长期停牌)"
            )
        report["stats"]["max_calendar_gap_days"] = int(gaps.max()) if len(gaps) else 0

    # abnormal pct_change
    if "涨跌幅" in work.columns:
        pct = pd.to_numeric(work["涨跌幅"], errors="coerce")
        limit_thr = _limit_pct_threshold(symbol)
        anomalies = pct[pct.abs() > ANOMALY_PCT_THRESHOLD]
        if len(anomalies):
            report["warnings"].append(
                f"涨跌幅超过 {ANOMALY_PCT_THRESHOLD}% 共 {len(anomalies)} 天"
            )
        suspicious = pct[(pct.abs() > limit_thr) & (pct.abs() <= ANOMALY_PCT_THRESHOLD)]
        if len(suspicious) > 3:
            report["warnings"].append(
                f"涨跌幅超过板块阈值 {limit_thr}% 共 {len(suspicious)} 天 (可能复权异常)"
            )
        report["stats"]["pct_change_max"] = round(float(pct.abs().max()), 2) if pct.notna().any() else None

    report["stats"]["date_from"] = str(work["日期"].iloc[0].date())
    report["stats"]["date_to"] = str(work["日期"].iloc[-1].date())
    report["passed"] = (
        not report["issues"]
        and report["trading_days"] >= MIN_TRADING_DAYS
        and adjust_source == "qfq"
    )
    return report


def save_daily_meta(symbol: str, meta: dict) -> str:
    path = daily_meta_path(symbol)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return path


def save_quality_report(symbol: str, report: dict) -> str:
    path = quality_report_path(symbol)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return path


def validate_and_persist(
    df: pd.DataFrame,
    symbol: str,
    adjust_source: str,
    adjust: str = "qfq",
) -> dict:
    """校验并持久化 meta + quality 报告."""
    report = validate_ohlcv(df, symbol, adjust_source=adjust_source)
    meta = {
        "symbol": symbol,
        "adjust": adjust,
        "adjust_source": adjust_source,
        "row_count": len(df) if df is not None else 0,
        "fetched_at": datetime.now().isoformat(),
        "quality_passed": report["passed"],
        "ml_safe": adjust_source == "qfq",
    }
    save_daily_meta(symbol, meta)
    save_quality_report(symbol, report)
    log.info(
        "%s 数据质量: %d 天, source=%s, passed=%s",
        symbol, report["trading_days"], adjust_source, report["passed"],
    )
    return report
