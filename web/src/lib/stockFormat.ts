export function formatPrice(price: number | null | undefined): string {
  if (price == null || Number.isNaN(price)) return "—";
  return `¥${price}`;
}

export function formatChangePct(chg: number | null | undefined): string {
  if (chg == null || Number.isNaN(chg)) return "—";
  return `${chg > 0 ? "+" : ""}${chg.toFixed(2)}%`;
}

export function changeDirection(chg: number | null | undefined): "up" | "down" | "flat" {
  if (chg == null || chg === 0 || Number.isNaN(chg)) return "flat";
  return chg > 0 ? "up" : "down";
}

export type ScanPick = {
  symbol?: string;
  name?: string;
  score?: number;
  final_score?: number;
  reason?: string;
  reasoning?: string;
  change_pct?: number;
};

export function pickScore(p: ScanPick): number | undefined {
  const v = p.score ?? p.final_score;
  return typeof v === "number" ? v : undefined;
}

export function pickNote(p: ScanPick): string {
  return String(p.reason || p.reasoning || "");
}

export function asPickList(value: unknown): ScanPick[] {
  if (!Array.isArray(value)) return [];
  return value.filter((x) => x && typeof x === "object") as ScanPick[];
}

export function extractScanSections(result: unknown): {
  left: ScanPick[];
  right: ScanPick[];
  ath: ScanPick[];
  picks: ScanPick[];
} {
  const obj = result && typeof result === "object" ? (result as Record<string, unknown>) : {};
  const left = obj.left && typeof obj.left === "object" ? (obj.left as Record<string, unknown>) : {};
  const right = obj.right && typeof obj.right === "object" ? (obj.right as Record<string, unknown>) : {};
  const ath = obj.ath && typeof obj.ath === "object" ? (obj.ath as Record<string, unknown>) : {};
  return {
    left: asPickList(left.top_picks || left.picks),
    right: asPickList(right.picks || right.top_picks),
    ath: asPickList(ath.picks || ath.top_picks),
    picks: asPickList(obj.picks || obj.top_picks),
  };
}

export function stockReportMarkdown(d: Record<string, unknown>): string {
  let md = String(d.report || d.technical_report || d.fundamental_report || d.sentiment_report || "");
  for (const key of ["valuation_report", "fund_flow_report", "xgb_report", "prediction_report"]) {
    const extra = d[key];
    if (typeof extra === "string" && extra.trim()) md += `\n\n---\n\n${extra}`;
  }
  return md;
}

type NamedRow = Record<string, unknown>;

export function portfolioMarkdown(d: Record<string, unknown>): string {
  const rows = Array.isArray(d.allocations) ? (d.allocations as NamedRow[]) : [];
  let md = "# 组合仓位建议\n\n";
  md += `> 市场: **${d.market_regime_zh || ""}** — ${d.regime_advice || ""}\n\n`;
  md += "| 标的 | 建议仓位 | 金额 | 评分 |\n|------|---------|------|------|\n";
  for (const a of rows) {
    md += `| ${a.symbol || ""} ${a.name || ""} | ${a.weight_pct}% | ¥${a.amount} | ${a.score} |\n`;
  }
  md += `\n**现金建议**: ${d.cash_pct}% (¥${d.cash_amount})\n`;
  const corr = d.correlation && typeof d.correlation === "object" ? (d.correlation as { warnings?: string[] }) : {};
  if (corr.warnings?.length) {
    md += "\n## 相关性预警\n";
    for (const w of corr.warnings) md += `- ${w}\n`;
  }
  return md;
}

export function drawdownMarkdown(d: Record<string, unknown>): string {
  const alerts = Array.isArray(d.alerts) ? (d.alerts as NamedRow[]) : [];
  const positions = Array.isArray(d.positions) ? (d.positions as NamedRow[]) : [];
  let md = "# 回撤监控\n\n";
  if (alerts.length) {
    md += "## 预警\n";
    for (const a of alerts) md += `- **${a.level}**: ${a.message}\n`;
  } else {
    md += "> 暂无预警\n\n";
  }
  md += "| 标的 | 现价 | 成本 | 回撤 | 盈亏 |\n|------|------|------|------|------|\n";
  for (const p of positions) {
    md += `| ${p.symbol} | ${p.price} | ${p.cost_price} | ${p.drawdown_pct}% | ${p.pnl_pct}% |\n`;
  }
  return md;
}

export function relativeStrengthMarkdown(d: Record<string, unknown>): string {
  const rankings = Array.isArray(d.rankings) ? (d.rankings as NamedRow[]) : [];
  let md = "# 自选股相对强度排名\n\n";
  md += "| 排名 | 标的 | 20日收益 | 5日动量 | 综合分 | 分位 |\n|------|------|---------|---------|--------|------|\n";
  for (const x of rankings) {
    md += `| ${x.rank} | ${x.symbol} | ${x.ret_20d}% | ${x.momentum_5d}% | ${x.composite_score} | ${x.percentile}% |\n`;
  }
  const picks = Array.isArray(d.top_picks) ? (d.top_picks as NamedRow[]) : [];
  if (picks.length) {
    md += `\n**建议关注 (前20%)**: ${picks.map((t) => t.symbol).join(", ")}\n`;
  }
  return md;
}

export function backtestMarkdown(d: Record<string, unknown>): string {
  let md = `# 回测报告 (${d.strategy || ""})\n\n`;
  md += `- 总收益: **${d.total_return_pct}%**\n`;
  md += `- 年化: **${d.annual_return_pct}%**\n`;
  md += `- 夏普: **${d.sharpe_ratio}**\n`;
  md += `- 最大回撤: **${d.max_drawdown_pct}%**\n`;
  md += `- 胜率: **${d.win_rate}%**\n`;
  md += `- 交易次数: **${d.total_trades}**\n`;
  return md;
}

export type NationalTeamView = {
  broadYi: number;
  sectorYi: number;
  signal: string;
  trendPct: number | null;
  trend: string;
  fetchedAt: string;
  etfs: NamedRow[];
  periods: NamedRow[];
  sseStatDate: string;
  refDate: string;
};

export function localToday(now: Date = new Date()): string {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function marketFlowNetCaption(
  latestDate: string | null | undefined,
  today: string,
): { netLabel: string; avgPrefix: string; stale: boolean; staleHint: string } {
  const date = String(latestDate || "").slice(0, 10);
  if (!date) {
    return { netLabel: "净流入", avgPrefix: "5日均", stale: true, staleHint: "日期未知" };
  }
  if (date === today) {
    return { netLabel: "今日净流入", avgPrefix: "5日均", stale: false, staleHint: "" };
  }
  return {
    netLabel: `净流入（截至 ${date}）`,
    avgPrefix: `5日均（截至 ${date}）`,
    stale: true,
    staleHint: `数据截至 ${date}（非当日）`,
  };
}

export function officialDayHeader(refDate: string | null | undefined): string {
  const d = String(refDate || "").slice(0, 10);
  return d ? `当天 vs ${d}` : "当天";
}

export function shareAnnouncementNote(sseStatDate: string | null | undefined): string {
  const d = String(sseStatDate || "").slice(0, 10);
  if (!d) return "份额公告日: 深市为最新日";
  return `份额公告日: ${d}（深市为最新日）`;
}

export function formatFetchedAt(iso: string | null | undefined): string {
  const s = String(iso || "").replace("T", " ").slice(0, 19);
  return s || "未知";
}

export function officialGridCaption(
  fetchedAt: string | null | undefined,
  refDate: string | null | undefined,
  sseStatDate: string | null | undefined,
): string {
  const when = formatFetchedAt(fetchedAt);
  const ref = String(refDate || "").slice(0, 10) || "未知";
  const sse = String(sseStatDate || "").slice(0, 10);
  const announce = sse ? `份额公告日 ${sse}（深市为最新日）` : "份额公告日 深市为最新日";
  return `参考时间 ${when} · 对比日 ${ref} · ${announce}`;
}

export type IntradayShareItem = {
  name?: string;
  code?: string;
  prev_yi?: number | null;
  curr_yi?: number | null;
  change_pct?: number | null;
  status?: string;
};

export function formatIntradayShareLine(item: IntradayShareItem): string {
  const name = String(item.name || "");
  const code = String(item.code || "");
  if (item.status !== "ok" || item.prev_yi == null || item.curr_yi == null) {
    return `${name} (${code}): 无数据`;
  }
  const pct =
    item.change_pct == null
      ? ""
      : ` (${item.change_pct > 0 ? "+" : ""}${item.change_pct.toFixed(2)}%)`;
  return `${name} (${code}): ${item.prev_yi.toFixed(1)} → ${item.curr_yi.toFixed(1)} 亿份${pct}`;
}

export function nationalTeamView(d: Record<string, unknown>): NationalTeamView {
  const snap = d.snapshot && typeof d.snapshot === "object" ? (d.snapshot as NamedRow) : {};
  const trend = d.trend && typeof d.trend === "object" ? (d.trend as NamedRow) : {};
  const ps = d.period_stats && typeof d.period_stats === "object" ? (d.period_stats as NamedRow) : {};
  const sigs = snap.signals && typeof snap.signals === "object" ? (snap.signals as NamedRow) : {};
  const daily = snap.daily_change && typeof snap.daily_change === "object" ? (snap.daily_change as NamedRow) : {};
  return {
    broadYi: Number(snap.total_broad_shares_yi || 0),
    sectorYi: Number(snap.total_sector_shares_yi || 0),
    signal: String(sigs.broad_total_change || "无数据"),
    trendPct: typeof trend.total_change_pct === "number" ? trend.total_change_pct : null,
    trend: String(trend.trend || ""),
    fetchedAt: String(snap.fetched_at || ""),
    etfs: Array.isArray(snap.etf_snapshot) ? (snap.etf_snapshot as NamedRow[]) : [],
    periods: Array.isArray(ps.periods) ? (ps.periods as NamedRow[]) : [],
    sseStatDate: String(snap.sse_stat_date || ""),
    refDate: String(daily.ref_date || ""),
  };
}

export type RealtimeQuote = {
  last?: number;
  changePct?: number;
  open?: number;
  high?: number;
  low?: number;
  prevClose?: number;
};

export function realtimeQuote(d: Record<string, unknown>): RealtimeQuote | null {
  const q = d.realtime_quote;
  if (!q || typeof q !== "object") return null;
  const row = q as NamedRow;
  const last = row["最新价"];
  if (last == null) return null;
  return {
    last: Number(last),
    changePct: row["涨跌幅"] == null ? undefined : Number(row["涨跌幅"]),
    open: row["今开"] == null ? undefined : Number(row["今开"]),
    high: row["最高"] == null ? undefined : Number(row["最高"]),
    low: row["最低"] == null ? undefined : Number(row["最低"]),
    prevClose: row["昨收"] == null ? undefined : Number(row["昨收"]),
  };
}
