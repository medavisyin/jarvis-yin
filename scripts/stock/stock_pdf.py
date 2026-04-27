"""
Shared PDF generator for Jarvis stock features (ReportLab, Chinese, consistent styling).
"""
from __future__ import annotations

import html
import os
import re
from datetime import datetime
from typing import Any, List, Optional, Sequence, Union

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config import STOCK_REPORTS_ROOT

# ---------------------------------------------------------------------------
# Color scheme — stock-themed, consistent with the dark UI (#0f1117 bg)
# ---------------------------------------------------------------------------
COLORS = {
    "primary": HexColor("#1a237e"),  # deep blue — headers
    "secondary": HexColor("#283593"),  # medium blue — subheaders
    "accent_green": HexColor("#2e7d32"),  # positive / bullish
    "accent_red": HexColor("#c62828"),  # negative / bearish
    "accent_gold": HexColor("#f9a825"),  # gold / precious metals
    "accent_purple": HexColor("#6a1b9a"),  # themes / long-term
    "text": HexColor("#212121"),  # body text
    "text_light": HexColor("#757575"),  # secondary text
    "bg_light": HexColor("#f5f5f5"),  # table alternating rows
    "border": HexColor("#bdbdbd"),  # table borders
    "header_text": HexColor("#ffffff"),
}

_MARGIN_MM = 18
ALLOWED_TYPES = frozenset(
    {
        "short_term",
        "long_term",
        "stock_analysis",
        "price_prediction",
        "watchlist",
        "national_team",
    }
)

REPORT_TITLES = {
    "short_term": "短期推荐报告",
    "long_term": "长期推荐报告",
    "stock_analysis": "个股分析报告",
    "price_prediction": "价格预测报告",
    "watchlist": "自选股报告",
    "national_team": "国家队监控报告",
}

# Register Chinese font (STSong-Light CID) — same pattern as donor PDF
def _register_chinese_font() -> str:
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont

        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        return "STSong-Light"
    except Exception:
        return "Helvetica"


_CHINESE_FONT = _register_chinese_font()
_base = getSampleStyleSheet()

STYLES: dict[str, ParagraphStyle] = {
    "title": ParagraphStyle(
        "StockTitle",
        parent=_base["Title"],
        fontSize=24,
        leading=30,
        textColor=COLORS["primary"],
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName=_CHINESE_FONT,
    ),
    "subtitle": ParagraphStyle(
        "StockSubtitle",
        parent=_base["Normal"],
        fontSize=12,
        leading=15,
        textColor=COLORS["text_light"],
        alignment=TA_CENTER,
        spaceAfter=16,
        fontName=_CHINESE_FONT,
    ),
    "h1": ParagraphStyle(
        "StockH1",
        parent=_base["Heading1"],
        fontSize=16,
        leading=20,
        textColor=COLORS["primary"],
        spaceBefore=14,
        spaceAfter=8,
        fontName=_CHINESE_FONT,
    ),
    "h2": ParagraphStyle(
        "StockH2",
        parent=_base["Heading2"],
        fontSize=12,
        leading=15,
        textColor=COLORS["secondary"],
        spaceBefore=10,
        spaceAfter=5,
        fontName=_CHINESE_FONT,
    ),
    "h3": ParagraphStyle(
        "StockH3",
        parent=_base["Heading3"],
        fontSize=10.5,
        leading=14,
        textColor=COLORS["text"],
        spaceBefore=6,
        spaceAfter=3,
        fontName=_CHINESE_FONT,
    ),
    "body": ParagraphStyle(
        "StockBody",
        parent=_base["Normal"],
        fontSize=9.5,
        leading=13.5,
        textColor=COLORS["text"],
        spaceAfter=4,
        fontName=_CHINESE_FONT,
    ),
    "body_small": ParagraphStyle(
        "StockBodySmall",
        parent=_base["Normal"],
        fontSize=8.5,
        leading=12,
        textColor=COLORS["text_light"],
        spaceAfter=3,
        fontName=_CHINESE_FONT,
    ),
    "bullet": ParagraphStyle(
        "StockBullet",
        parent=_base["Normal"],
        fontSize=9.5,
        leading=13.5,
        textColor=COLORS["text"],
        leftIndent=14,
        bulletIndent=4,
        spaceAfter=2,
        fontName=_CHINESE_FONT,
    ),
    "table_cell": ParagraphStyle(
        "StockTableCell",
        parent=_base["Normal"],
        fontSize=8,
        leading=10,
        textColor=COLORS["text"],
        fontName=_CHINESE_FONT,
    ),
    "footer": ParagraphStyle(
        "StockFooter",
        parent=_base["Normal"],
        fontSize=7.5,
        textColor=COLORS["text_light"],
        alignment=TA_CENTER,
        spaceBefore=16,
        fontName=_CHINESE_FONT,
    ),
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _safe(text: Any) -> str:
    """Escape HTML entities for ReportLab Paragraph."""
    if text is None:
        return ""
    s = str(text)
    return html.escape(s, quote=True).replace("\n", "<br/>")


def _markdown_to_plain(text: str) -> str:
    if not text or not str(text).strip():
        return ""
    t = str(text)
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"[*_]([^*_]+)[*_]", r"\1", t)
    t = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"^\s*[-*+]\s+", "· ", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\d+\.\s+", "· ", t, flags=re.MULTILINE)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _hr() -> HRFlowable:
    return HRFlowable(
        width="100%",
        thickness=0.5,
        color=COLORS["border"],
        spaceBefore=6,
        spaceAfter=6,
    )


def _make_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    col_widths: Optional[Sequence[Union[int, float]]] = None,
) -> Table:
    """Consistent table style (header row + alternating body rows)."""
    header_cells = [Paragraph(_safe(h), STYLES["table_cell"]) for h in headers]
    data: List = [header_cells]
    for row in rows:
        r = []
        for cell in row:
            r.append(Paragraph(_safe(cell), STYLES["table_cell"]))
        data.append(r)
    if col_widths is None:
        n = len(headers)
        page_w = A4[0] - 2 * _MARGIN_MM * mm
        col_widths = [page_w / n] * n
    tbl = Table(data, colWidths=list(col_widths), repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COLORS["primary"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), COLORS["header_text"]),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("FONTSIZE", (0, 1), (-1, -1), 7.5),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.35, COLORS["border"]),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [COLORS["bg_light"], HexColor("#ffffff")],
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return tbl


def _badge(text: str, color: HexColor) -> str:
    """HTML snippet for a colored inline badge (use inside Paragraph)."""
    t = _safe(text)
    c = color.hexval() if hasattr(color, "hexval") else str(color)
    return f'<font color="{c}"><b>「 {t} 」</b></font>'


def _score_bar(score: float, max_score: float = 100) -> str:
    """Textual score bar for PDF."""
    try:
        s = float(score)
        m = float(max_score)
    except (TypeError, ValueError):
        return "—"
    if m <= 0:
        return "—"
    pct = max(0.0, min(1.0, s / m))
    filled = int(round(pct * 10))
    bar = "█" * filled + "░" * (10 - filled)
    return f"{bar} {s:.0f}/{m:.0f}"


def _extract_date_str(data: dict) -> str:
    d = data.get("date")
    if d:
        return str(d)[:10]
    return datetime.now().strftime("%Y-%m-%d")


def _append_body_paragraphs(elements: list, text: str, style_key: str = "body") -> None:
    """Split by blank lines; each block becomes one or more Paragraphs."""
    if not text or not str(text).strip():
        return
    plain = _markdown_to_plain(text)
    for block in re.split(r"\n\s*\n", plain):
        block = block.strip()
        if not block:
            continue
        for line in block.split("\n"):
            line = line.strip()
            if line:
                elements.append(Paragraph(_safe(line), STYLES[style_key]))


# ---------------------------------------------------------------------------
# Type-specific builders
# ---------------------------------------------------------------------------
def _build_short_term(data: dict, elements: list) -> None:
    date_str = _extract_date_str(data)
    elements.append(Spacer(1, 24))
    elements.append(Paragraph(_safe(REPORT_TITLES["short_term"]), STYLES["title"]))
    elements.append(Paragraph(_safe(date_str), STYLES["subtitle"]))
    meta = data.get("meta") or {}
    m_rows = [
        [
            "全市场",
            meta.get("market_total", "—"),
            "一层筛",
            meta.get("layer1_count", "—"),
            "二层筛",
            meta.get("layer2_count", "—"),
        ]
    ]
    elements.append(
        _make_table(
            ["项", "数量", "项", "数量", "项", "数量"],
            m_rows,
            col_widths=[50 * mm, 28 * mm, 50 * mm, 28 * mm, 50 * mm, 28 * mm],
        )
    )
    elements.append(Spacer(1, 6))
    elements.append(_hr())

    picks: List[dict] = data.get("top_picks") or []
    for rank, pick in enumerate(picks, 1):
        name = pick.get("name", "—")
        sym = pick.get("symbol", "—")
        hot = pick.get("is_hot")
        hot_badge = f" { _badge('热门', COLORS['accent_gold']) }" if hot else ""
        elements.append(Paragraph(f"<b>#{rank}</b> {_safe(name)} <font size=8>({_safe(sym)})</font>{hot_badge}", STYLES["h1"]))
        price = pick.get("price", "—")
        chg = pick.get("change_pct", "—")
        elements.append(
            Paragraph(
                f"价格: {_safe(price)} &nbsp;|&nbsp; 涨跌: {_safe(chg)}%",
                STYLES["body"],
            )
        )
        score_rows = [
            [
                "综合",
                pick.get("final_score", "—"),
                "资金",
                pick.get("fund_score", "—"),
                "技术",
                pick.get("tech_score", "—"),
                "情绪",
                pick.get("sentiment_score", "—"),
            ]
        ]
        elements.append(
            _make_table(
                ["指标", "得分", "指标", "得分", "指标", "得分", "指标", "得分"],
                score_rows,
                col_widths=[22 * mm] * 8,
            )
        )
        if pick.get("pe") is not None:
            elements.append(Paragraph(f"PE: {_safe(pick.get('pe'))}", STYLES["body_small"]))
        elements.append(Paragraph("<b>逻辑</b>", STYLES["h3"]))
        _append_body_paragraphs(elements, str(pick.get("reasoning") or ""))
        elements.append(Paragraph("<b>风险</b>", STYLES["h3"]))
        _append_body_paragraphs(elements, str(pick.get("risk") or ""))
        elements.append(Paragraph("<b>策略</b>", STYLES["h3"]))
        _append_body_paragraphs(elements, str(pick.get("strategy") or ""))
        bl, bh = pick.get("buy_low"), pick.get("buy_high")
        if bl is not None or bh is not None:
            elements.append(
                Paragraph(
                    f"建议区间: {_safe(bl)} — {_safe(bh)}",
                    STYLES["body"],
                )
            )
        comp = pick.get("comprehensive")
        if isinstance(comp, dict) and comp:
            elements.append(Paragraph("维度得分", STYLES["h2"]))
            for key, sub in comp.items():
                if not isinstance(sub, dict):
                    elements.append(Paragraph(f"{_safe(key)}: {_safe(sub)}", STYLES["bullet"]))
                    continue
                label = str(sub.get("name") or sub.get("label") or key)
                sc = sub.get("score", sub.get("value"))
                elements.append(
                    Paragraph(
                        f"<b>{_safe(label)}</b>: {_safe(sc)} — {_safe(sub.get('detail', sub.get('summary', '')))}",
                        STYLES["body"],
                    )
                )
        ds = pick.get("deepseek")
        if isinstance(ds, dict) and (ds.get("report") or ds.get("reasoning")):
            elements.append(Paragraph("DeepSeek 分析", STYLES["h2"]))
            if ds.get("report"):
                _append_body_paragraphs(elements, str(ds["report"]))
            if ds.get("reasoning"):
                _append_body_paragraphs(elements, str(ds["reasoning"]))
        elements.append(_hr())


def _build_long_term(data: dict, elements: list) -> None:
    date_str = _extract_date_str(data)
    elements.append(Spacer(1, 24))
    elements.append(Paragraph(_safe(REPORT_TITLES["long_term"]), STYLES["title"]))
    elements.append(Paragraph(_safe(date_str), STYLES["subtitle"]))
    elements.append(Paragraph("贵金属", STYLES["h1"]))
    pm = data.get("precious_metals") or {}
    for metal_key, title_cn in (("gold", "黄金"), ("silver", "白银")):
        m = pm.get(metal_key) or {}
        if not m:
            continue
        elements.append(Paragraph(f"<b>{title_cn}</b>", STYLES["h2"]))
        if not m.get("data_available", True) and m.get("latest_price") is None:
            elements.append(Paragraph("数据暂不可用", STYLES["body_small"]))
            continue
        m_rows = [
            [
                "最新价",
                m.get("latest_price", "—"),
                "趋势",
                m.get("trend", "—"),
                "上涨分",
                m.get("upside_score", "—"),
            ],
            [
                "14日%",
                m.get("change_14d_pct", "—"),
                "60日%",
                m.get("change_60d_pct", "—"),
                "RSI(14)",
                m.get("rsi_14", "—"),
            ],
            [
                "年内位置",
                m.get("position_vs_52w", "—"),
                "",
                "",
                "",
            ],
        ]
        elements.append(
            _make_table(
                ["项", "值", "项", "值", "项", "值"],
                m_rows,
                col_widths=[32 * mm, 38 * mm, 32 * mm, 38 * mm, 32 * mm, 38 * mm],
            )
        )
    if pm.get("gold_silver_ratio") is not None or pm.get("ratio_signal"):
        elements.append(
            Paragraph(
                f"金银比: {_safe(pm.get('gold_silver_ratio'))} &nbsp; {_safe(pm.get('ratio_signal', ''))}",
                STYLES["body"],
            )
        )
    llm = pm.get("llm_outlook") or {}
    if llm:
        elements.append(Paragraph("LLM 展望", STYLES["h2"]))
        for k in ("gold", "silver", "summary"):
            block = llm.get(k) if k != "summary" else llm.get("summary")
            if not block:
                continue
            if k == "summary":
                _append_body_paragraphs(elements, str(block))
            elif isinstance(block, dict):
                label = "黄金" if k == "gold" else "白银" if k == "silver" else k
                elements.append(Paragraph(f"<b>{_safe(label)}</b>", STYLES["h3"]))
                for fld in ("trend", "drivers", "advice", "price_range"):
                    if block.get(fld):
                        elements.append(Paragraph(f"{_safe(fld)}: {_safe(block.get(fld))}", STYLES["body"]))

    elements.append(_hr())
    elements.append(Paragraph("主题", STYLES["h1"]))
    for th in data.get("themes") or []:
        elements.append(Paragraph(f"<b>{_safe(th.get('name', '—'))}</b>", STYLES["h2"]))
        elements.append(Paragraph(f"逻辑: {_safe(th.get('logic'))}", STYLES["body"]))
        inds = th.get("industries") or []
        if inds:
            elements.append(Paragraph("行业: " + "、".join(_safe(x) for x in inds), STYLES["body_small"]))
        cats = th.get("catalysts") or []
        if cats:
            for c in cats:
                elements.append(Paragraph(f"· {_safe(c)}", STYLES["bullet"]))
        elements.append(
            Paragraph(
                f"周期: {_safe(th.get('time_horizon'))} &nbsp;|&nbsp; 置信: {_safe(th.get('confidence'))}",
                STYLES["body_small"],
            )
        )
    elements.append(_hr())
    elements.append(Paragraph("长期标的", STYLES["h1"]))
    for pick in data.get("picks") or []:
        elements.append(Paragraph(f"{_safe(pick.get('name', '—'))} ({_safe(pick.get('symbol', '—'))})", STYLES["h1"]))
        elements.append(Paragraph(f"主题: {_safe(pick.get('theme'))}", STYLES["body"]))
        _append_body_paragraphs(elements, str(pick.get("recommendation_reason") or ""))
        elements.append(Paragraph("<b>风险</b>", STYLES["h3"]))
        _append_body_paragraphs(elements, str(pick.get("recommendation_risk") or ""))
        elements.append(
            Paragraph(
                f"关注价: {_safe(pick.get('watch_price'))} &nbsp;|&nbsp; 周期: {_safe(pick.get('time_horizon'))}",
                STYLES["body"],
            )
        )
        up = pick.get("upside") or {}
        if isinstance(up, dict) and up.get("dimensions"):
            us = up.get("upside_score")
            elements.append(Paragraph(f"上涨综合分: {_safe(us)} &nbsp; {_score_bar(float(us) if us is not None else 0)}", STYLES["h2"]))
            dims = up.get("dimensions") or {}
            for dk, dv in dims.items():
                if not isinstance(dv, dict):
                    elements.append(Paragraph(f"{_safe(dk)}: {_safe(dv)}", STYLES["body"]))
                    continue
                nm = dv.get("name", dk)
                sc = dv.get("score", "—")
                elements.append(
                    Paragraph(
                        f"<b>{_safe(nm)}</b> ({_safe(sc)}): {_safe(dv.get('detail', ''))}",
                        STYLES["body"],
                    )
                )
        elements.append(Spacer(1, 4))


def _build_stock_analysis(data: dict, elements: list) -> None:
    sym = data.get("symbol", "—")
    elements.append(Spacer(1, 24))
    elements.append(Paragraph(_safe(REPORT_TITLES["stock_analysis"]), STYLES["title"]))
    elements.append(Paragraph(f"股票代码: {_safe(sym)}", STYLES["subtitle"]))
    elements.append(_hr())
    sections = [
        ("技术分析", "technical_report"),
        ("基本面", "fundamental_report"),
        ("情绪", "sentiment_report"),
        ("资金流", "fund_flow_report"),
        ("XGB 模型", "xgb_report"),
        ("价格预测", "prediction_report"),
        ("DeepSeek 汇总", "deepseek_report"),
    ]
    for title, key in sections:
        raw = data.get(key)
        if not raw or not str(raw).strip():
            continue
        elements.append(Paragraph(_safe(title), STYLES["h1"]))
        _append_body_paragraphs(elements, str(raw))
        elements.append(Spacer(1, 4))


def _build_price_prediction(data: dict, elements: list) -> None:
    date_str = _extract_date_str(data)
    elements.append(Spacer(1, 24))
    elements.append(Paragraph(_safe(REPORT_TITLES["price_prediction"]), STYLES["title"]))
    elements.append(Paragraph(_safe(date_str), STYLES["subtitle"]))

    sent = data.get("sentiment") or {}
    if sent:
        elements.append(Paragraph("市场情绪", STYLES["h1"]))
        elements.append(
            Paragraph(
                f"恐惧贪婪: {_safe(sent.get('fear_greed'))} &nbsp;|&nbsp; VIX: {_safe(sent.get('vix'))} &nbsp;|&nbsp; 情绪: {_safe(sent.get('mood'))}",
                STYLES["body"],
            )
        )
    bs = data.get("black_swan") or {}
    alerts = bs.get("alerts") or []
    if alerts:
        elements.append(Paragraph("黑天鹅/预警", STYLES["h2"]))
        for a in alerts:
            elements.append(Paragraph(f"· {_safe(a)}", STYLES["bullet"]))

    ver = data.get("verifications") or []
    if ver:
        elements.append(Paragraph("昨日预测验证", STYLES["h1"]))
        v_rows = []
        for r in ver:
            v_rows.append(
                [
                    r.get("symbol", "—"),
                    r.get("name", "—"),
                    r.get("predicted_close", "—"),
                    r.get("actual_close", "—"),
                    f"{_safe(r.get('error_pct'))}",
                    "是" if r.get("direction_correct") else "否",
                ]
            )
        elements.append(
            _make_table(
                ["代码", "名称", "预测收", "实际收", "误差%", "方向"],
                v_rows,
            )
        )

    agg = data.get("aggregate_stats") or {}
    if agg:
        elements.append(Paragraph("汇总统计", STYLES["h2"]))
        elements.append(
            Paragraph(
                f"MAPE: {_safe(agg.get('mape'))} &nbsp;|&nbsp; 方向准确率: {_safe(agg.get('direction_accuracy'))}",
                STYLES["body"],
            )
        )

    results = data.get("results") or []
    if results:
        elements.append(Paragraph("明日预测", STYLES["h1"]))
        res_rows = []
        for r in results:
            res_rows.append(
                [
                    r.get("symbol", "—"),
                    r.get("name", "—"),
                    r.get("current_price", "—"),
                    r.get("predicted_close", "—"),
                    r.get("predicted_high", "—"),
                    r.get("predicted_low", "—"),
                    f"{_safe(r.get('change_pct'))}",
                    r.get("health", "—"),
                ]
            )
        elements.append(
            _make_table(
                [
                    "代码",
                    "名称",
                    "现价",
                    "预测收",
                    "高",
                    "低",
                    "涨跌%",
                    "健康度",
                ],
                res_rows,
            )
        )
    if data.get("status") and str(data.get("status")).lower() != "done":
        elements.append(Paragraph(f"状态: {_safe(data.get('status'))}", STYLES["h2"]))


def _build_watchlist(data: dict, elements: list) -> None:
    date_str = _extract_date_str(data)
    elements.append(Spacer(1, 24))
    elements.append(Paragraph(_safe(REPORT_TITLES["watchlist"]), STYLES["title"]))
    elements.append(Paragraph(_safe(date_str), STYLES["subtitle"]))
    wl = data.get("watchlist") or []
    rows = []
    for w in wl:
        rows.append(
            [
                w.get("symbol", "—"),
                w.get("name", "—"),
                w.get("price", "—"),
                f"{_safe(w.get('change_pct'))}",
                w.get("sector", "—"),
            ]
        )
    if rows:
        elements.append(
            _make_table(
                ["代码", "名称", "价格", "涨跌幅%", "板块"],
                rows,
            )
        )
    else:
        elements.append(Paragraph("自选股列表为空", STYLES["body"]))


def _format_kv(obj: Any, indent: int = 0) -> str:
    if obj is None:
        return ""
    if isinstance(obj, (str, int, float, bool)):
        return "  " * indent + str(obj)
    if isinstance(obj, dict):
        parts = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                parts.append("  " * indent + f"{k}:")
                parts.append(_format_kv(v, indent + 1))
            else:
                parts.append("  " * indent + f"{k}: {v}")
        return "\n".join(parts)
    if isinstance(obj, list):
        return "\n".join("  " * indent + f"- {x}" for x in obj)
    return str(obj)


def _build_national_team(data: dict, elements: list) -> None:
    date_str = _extract_date_str(data)
    elements.append(Spacer(1, 24))
    elements.append(Paragraph(_safe(REPORT_TITLES["national_team"]), STYLES["title"]))
    elements.append(Paragraph(_safe(date_str), STYLES["subtitle"]))

    snap = data.get("snapshot") or {}
    if snap:
        elements.append(Paragraph("快照概览", STYLES["h1"]))
        for k, v in snap.items():
            elements.append(Paragraph(f"{_safe(k)}: {_safe(v)}", STYLES["body"]))

    etfs = data.get("etfs") or []
    if etfs:
        elements.append(Paragraph("ETF", STYLES["h1"]))
        e_rows = []
        for e in etfs:
            e_rows.append(
                [
                    e.get("name", "—"),
                    e.get("code", "—"),
                    e.get("price", "—"),
                    f"{_safe(e.get('change_pct'))}",
                    e.get("volume", "—"),
                    e.get("net_flow", "—"),
                ]
            )
        elements.append(
            _make_table(
                ["名称", "代码", "价格", "涨跌%", "量", "净流入"],
                e_rows,
            )
        )

    tr = data.get("trends")
    if tr:
        elements.append(Paragraph("趋势", STYLES["h2"]))
        _append_body_paragraphs(elements, _format_kv(tr))

    sig = data.get("signals") or []
    if sig:
        elements.append(Paragraph("信号", STYLES["h2"]))
        for s in sig:
            elements.append(Paragraph(f"· {_safe(s) if not isinstance(s, dict) else _safe(_format_kv(s))}", STYLES["bullet"]))

    ano = data.get("anomalies") or []
    if ano:
        elements.append(Paragraph("异常", STYLES["h2"]))
        for a in ano:
            elements.append(Paragraph(f"· {_safe(a) if not isinstance(a, dict) else _safe(_format_kv(a))}", STYLES["bullet"]))

    if data.get("verdict"):
        elements.append(Paragraph("结论", STYLES["h1"]))
        _append_body_paragraphs(elements, str(data["verdict"]))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def generate_stock_pdf(report_type: str, data: dict, output_dir: Optional[str] = None) -> str:
    """Generate a stock report PDF. Returns the absolute file path.

    report_type: one of short_term, long_term, stock_analysis, price_prediction, watchlist, national_team
    data: the JSON data from the corresponding API endpoint
    output_dir: optional override for output directory
    """
    if report_type not in ALLOWED_TYPES:
        raise ValueError(f"Unknown report_type: {report_type!r}; expected one of {sorted(ALLOWED_TYPES)}")

    date_str = _extract_date_str(data)
    base = output_dir or os.path.join(STOCK_REPORTS_ROOT, "pdf")
    os.makedirs(base, exist_ok=True)
    out_name = f"{report_type}_{date_str}.pdf"
    pdf_path = os.path.normpath(os.path.join(base, out_name))

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=_MARGIN_MM * mm,
        rightMargin=_MARGIN_MM * mm,
        topMargin=_MARGIN_MM * mm,
        bottomMargin=_MARGIN_MM * mm,
    )
    story: list = []
    if report_type == "short_term":
        _build_short_term(data, story)
    elif report_type == "long_term":
        _build_long_term(data, story)
    elif report_type == "stock_analysis":
        _build_stock_analysis(data, story)
    elif report_type == "price_prediction":
        _build_price_prediction(data, story)
    elif report_type == "watchlist":
        _build_watchlist(data, story)
    else:
        _build_national_team(data, story)

    story.append(
        Paragraph(
            _safe(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}") + f"<br/>Jarvis 股票模块 · {REPORT_TITLES.get(report_type, report_type)}",
            STYLES["footer"],
        )
    )
    doc.build(story)
    return os.path.abspath(pdf_path)


__all__ = [
    "COLORS",
    "STYLES",
    "generate_stock_pdf",
    "ALLOWED_TYPES",
    "REPORT_TITLES",
]
