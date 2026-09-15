import { useMemo, useState } from "react";
import { apiJson } from "@/lib/api";
import {
  formatIntradayShareLine,
  localToday,
  marketFlowNetCaption,
  nationalTeamView,
  formatFetchedAt,
  officialDayHeader,
  officialGridCaption,
  shareAnnouncementNote,
  type IntradayShareItem,
} from "@/lib/stockFormat";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataGrid } from "@/components/DataGrid";
import type { ColDef } from "ag-grid-community";

export function NationalTeamPanel() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [pdfUrl, setPdfUrl] = useState("");
  const [error, setError] = useState("");

  async function fetchLatest(force: boolean) {
    setBusy(true);
    setError("");
    setStatus(force ? "获取数据中... (含历史回填约30-60秒)" : "加载中...");
    try {
      const d = await apiJson<Record<string, unknown>>(`/api/stock/national-team?force=${force ? "1" : "0"}`);
      if (d.error) throw new Error(String(d.error));
      setData(d);
      setStatus("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("");
    } finally {
      setBusy(false);
    }
  }

  async function exportPdf() {
    if (!data) return;
    const payload = { ...data, date: new Date().toISOString().slice(0, 10) };
    const r = await apiJson<{ pdf_url?: string }>("/api/stock/export-pdf", {
      method: "POST",
      body: JSON.stringify({ type: "national_team", data: payload }),
    });
    if (r.pdf_url) setPdfUrl(r.pdf_url);
  }

  const v = data ? nationalTeamView(data) : null;
  const fs = data?.fund_signals && typeof data.fund_signals === "object" ? (data.fund_signals as Record<string, unknown>) : {};
  const mf = fs.market_flow && typeof fs.market_flow === "object" ? (fs.market_flow as Record<string, unknown>) : null;
  const flowCap = mf
    ? marketFlowNetCaption(mf.latest_date == null ? "" : String(mf.latest_date), localToday())
    : null;
  const shares = data?.intraday_shares && typeof data.intraday_shares === "object"
    ? (data.intraday_shares as Record<string, unknown>)
    : null;
  const shareItems = Array.isArray(shares?.items) ? (shares.items as IntradayShareItem[]) : [];
  const etfCols = useMemo(() => etfColumnDefs(v?.refDate, v?.fetchedAt), [v?.refDate, v?.fetchedAt]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>National team</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={busy} onClick={() => void fetchLatest(true)}>
          获取最新数据
        </Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={() => void fetchLatest(false)}>
          缓存
        </Button>
        <Button size="sm" variant="outline" disabled={!data} onClick={() => void exportPdf()}>
          导出PDF
        </Button>
        <span className="text-muted-foreground text-xs">{status}</span>
      </div>
      <p className="text-muted-foreground text-xs">监控16只核心ETF (9宽基 + 7行业)，跟踪汇金/社保/央企资金动向。数据来源: 上交所/深交所 ETF 份额公告。</p>
      {error ? <p className="text-destructive text-sm">{error}</p> : null}
      {pdfUrl ? (
        <a className="text-sm underline" href={pdfUrl} target="_blank" rel="noreferrer">
          Download PDF
        </a>
      ) : null}
      {v ? (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Card size="sm">
              <CardHeader>
                <CardTitle>宽基ETF总份额</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-medium">{v.broadYi.toFixed(1)} 亿份</p>
              </CardContent>
            </Card>
            <Card size="sm">
              <CardHeader>
                <CardTitle>行业ETF总份额</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-medium">{v.sectorYi.toFixed(1)} 亿份</p>
              </CardContent>
            </Card>
            <Card size="sm">
              <CardHeader>
                <CardTitle>国家队动向</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-lg font-medium">{v.signal}</p>
                {v.trendPct != null ? (
                  <p className="text-muted-foreground text-xs">
                    近期变化 {v.trendPct > 0 ? "+" : ""}
                    {v.trendPct}% · {v.trend}
                  </p>
                ) : null}
              </CardContent>
            </Card>
          </div>
          {v.fetchedAt ? <p className="text-muted-foreground text-xs">实时拉取: {v.fetchedAt.replace("T", " ").slice(0, 19)}</p> : null}
          {shares ? (
            <Card size="sm">
              <CardHeader>
                <CardTitle>开盘至今份额（宽基）</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                {shares.error ? (
                  <p className="text-destructive">暂不可用: {String(shares.error)}</p>
                ) : shareItems.length ? (
                  shareItems.map((it) => (
                    <p key={String(it.code || it.name)} className="text-xs">
                      {formatIntradayShareLine(it)}
                    </p>
                  ))
                ) : (
                  <p className="text-muted-foreground text-xs">无数据</p>
                )}
                {typeof shares.disclaimer === "string" && shares.disclaimer ? (
                  <p className="text-muted-foreground pt-1 text-[11px] leading-snug">{shares.disclaimer}</p>
                ) : null}
                {typeof shares.as_of === "string" && shares.as_of ? (
                  <p className="text-muted-foreground text-[11px]">检测时刻: {shares.as_of.replace("T", " ").slice(0, 19)}</p>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
          {mf && flowCap ? (
            <Card size="sm">
              <CardHeader>
                <CardTitle>资金信号 · 全市场主力</CardTitle>
              </CardHeader>
              <CardContent className="text-sm">
                <p>{String(mf.signal || "")}</p>
                <p className="text-muted-foreground text-xs">
                  {flowCap.netLabel} {String(mf.latest_net_yi ?? "")} 亿 · {flowCap.avgPrefix}{" "}
                  {String(mf.avg_5d_net_yi ?? "")} 亿
                </p>
                {Number(mf.consecutive_inflow) > 0 ? (
                  <p className="text-xs">连续流入 {String(mf.consecutive_inflow)} 日</p>
                ) : null}
                {Number(mf.consecutive_outflow) > 0 ? (
                  <p className="text-xs">连续流出 {String(mf.consecutive_outflow)} 日</p>
                ) : null}
                {flowCap.staleHint ? <p className="text-muted-foreground text-[11px]">{flowCap.staleHint}</p> : null}
                <p className="text-muted-foreground pt-1 text-[11px] leading-snug">
                  全 A 股超大单+大单，不是上方 16 只 ETF 的流入。
                </p>
              </CardContent>
            </Card>
          ) : null}
          {v.periods.length ? (
            <DataGrid
              rows={v.periods}
              columnDefs={PERIOD_COLS}
              getRowId={(p) => String(p.data.label || p.data.ref_date || "")}
            />
          ) : null}
          {v.etfs.length ? (
            <>
              <p className="text-sm font-medium">核心 ETF 官方份额</p>
              <p className="text-muted-foreground text-xs">{officialGridCaption(v.fetchedAt, v.refDate, v.sseStatDate)}</p>
              <DataGrid
                rows={v.etfs}
                columnDefs={etfCols}
                getRowId={(p) => String(p.data.code || p.data.name || "")}
              />
              <p className="text-muted-foreground text-[11px]">{shareAnnouncementNote(v.sseStatDate)}</p>
            </>
          ) : null}
        </>
      ) : null}
      </CardContent>
    </Card>
  );
}

function fmtPct(v: unknown): string {
  if (typeof v !== "number") return "-";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function range(from: unknown, to: unknown): string {
  if (typeof from !== "number" || typeof to !== "number") return "-";
  return `${from.toFixed(1)} → ${to.toFixed(1)}`;
}

const PERIOD_COLS: ColDef<Record<string, unknown>>[] = [
  { field: "label", headerName: "区间", width: 110, valueFormatter: (p) => String(p.value || "") },
  { field: "ref_date", headerName: "参考日期", width: 120, valueFormatter: (p) => String(p.value || "-") },
  { colId: "broad_chg", headerName: "宽基变化", width: 110, valueGetter: (p) => fmtPct(p.data?.broad_change_pct) },
  { colId: "broad_sh", headerName: "宽基份额", width: 140, valueGetter: (p) => range(p.data?.broad_from, p.data?.broad_to) },
  { colId: "sector_chg", headerName: "行业变化", width: 110, valueGetter: (p) => fmtPct(p.data?.sector_change_pct) },
  { colId: "sector_sh", headerName: "行业份额", flex: 1, minWidth: 140, valueGetter: (p) => range(p.data?.sector_from, p.data?.sector_to) },
];

function etfColumnDefs(
  refDate: string | undefined,
  fetchedAt: string | undefined,
): ColDef<Record<string, unknown>>[] {
  return [
    { field: "name", headerName: "名称", flex: 1, minWidth: 120, valueFormatter: (p) => String(p.value || "") },
    { field: "code", headerName: "代码", width: 90, valueFormatter: (p) => String(p.value || "") },
    { field: "index", headerName: "跟踪指数", flex: 1, minWidth: 120, valueFormatter: (p) => String(p.value || "") },
    {
      field: "shares_yi",
      headerName: "份额(亿份)",
      width: 110,
      valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(1) : "N/A"),
    },
    {
      colId: "refAt",
      headerName: "参考时间",
      width: 160,
      valueGetter: () => formatFetchedAt(fetchedAt),
    },
    { colId: "chg", headerName: officialDayHeader(refDate), width: 130, valueGetter: (p) => fmtPct(p.data?.change_pct) },
  ];
}
