import { useMemo, useState } from "react";
import { apiJson } from "@/lib/api";
import { isTerminalJobStatus, pollJob } from "@/lib/jobs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataGrid } from "@/components/DataGrid";
import type { ColDef, ValueGetterParams } from "ag-grid-community";

type WeeklyPick = {
  symbol?: string;
  name?: string;
  week_close?: number;
  returns?: number[];
};
type SelectResult = {
  picks?: WeeklyPick[];
  target?: string;
  weeks?: number;
  universe_total?: number;
  count?: number;
  skipped_no_data?: number;
  allow_network?: boolean;
  error?: string;
};
type BacktestResult = {
  metrics?: Record<string, number>;
  weeks?: number;
  initial_capital?: number;
  final_capital?: number;
  start?: string;
  end?: string;
  equity_curve?: { equity?: number }[];
  trades?: {
    entry_date?: string;
    exit_date?: string;
    symbol?: string;
    name?: string;
    entry_price?: number;
    exit_price?: number;
    return_pct?: number;
    reason?: string;
  }[];
  error?: string;
};

export function WeeklyPanel() {
  const today = new Date().toISOString().slice(0, 10);
  const [date, setDate] = useState(today);
  const [weeks, setWeeks] = useState(3);
  const [allowNet, setAllowNet] = useState(false);
  const [selStatus, setSelStatus] = useState("");
  const [selPhase, setSelPhase] = useState("");
  const [selRunning, setSelRunning] = useState(false);
  const [selResult, setSelResult] = useState<SelectResult | null>(null);

  const [btStart, setBtStart] = useState("2023-01-01");
  const [btEnd, setBtEnd] = useState(today);
  const [capital, setCapital] = useState(1000000);
  const [btWeeks, setBtWeeks] = useState(3);
  const [btStatus, setBtStatus] = useState("");
  const [btPhase, setBtPhase] = useState("");
  const [btRunning, setBtRunning] = useState(false);
  const [btResult, setBtResult] = useState<BacktestResult | null>(null);

  async function startSelect() {
    setSelRunning(true);
    setSelResult(null);
    setSelStatus("启动中...");
    try {
      await apiJson("/api/stock/weekly/select", {
        method: "POST",
        body: JSON.stringify({ date, weeks, allow_network: allowNet }),
      });
      const done = await pollJob(
        () => apiJson<{ status?: string; progress?: number; step?: string }>("/api/stock/weekly/select/status"),
        (j) => {
          setSelStatus(j.status || "");
          setSelPhase(`${j.progress ?? 0}% ${j.step || ""}`);
        },
        { intervalMs: 2000 },
      );
      setSelStatus(done.status || "");
      if (isTerminalJobStatus(done.status) && done.status !== "error") {
        const latest = await apiJson<SelectResult>("/api/stock/weekly/select/result");
        setSelResult(latest);
      }
    } catch (e) {
      setSelStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setSelRunning(false);
    }
  }

  async function startBacktest() {
    setBtRunning(true);
    setBtResult(null);
    setBtStatus("启动中...");
    try {
      await apiJson("/api/stock/weekly/backtest", {
        method: "POST",
        body: JSON.stringify({ start_date: btStart, end_date: btEnd, capital, weeks: btWeeks }),
      });
      const done = await pollJob(
        () => apiJson<{ status?: string; progress?: number; step?: string }>("/api/stock/weekly/backtest/status"),
        (j) => {
          setBtStatus(j.status || "");
          setBtPhase(`${j.progress ?? 0}% ${j.step || ""}`);
        },
        { intervalMs: 2000 },
      );
      setBtStatus(done.status || "");
      if (isTerminalJobStatus(done.status) && done.status !== "error") {
        const latest = await apiJson<BacktestResult>("/api/stock/weekly/backtest/result");
        setBtResult(latest);
      }
    } catch (e) {
      setBtStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setBtRunning(false);
    }
  }

  const m = btResult?.metrics || {};
  const picks = selResult?.picks || [];
  const wk = selResult?.weeks || weeks;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>周线选股 (连续收涨)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-muted-foreground text-xs">目标周五</label>
            <Input type="date" className="w-40" value={date} onChange={(e) => setDate(e.target.value)} />
            <label className="text-muted-foreground text-xs">连涨周数</label>
            <Input className="w-16" type="number" min={1} max={26} value={weeks} onChange={(e) => setWeeks(Number(e.target.value) || 3)} />
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={allowNet} onChange={(e) => setAllowNet(e.target.checked)} />
              联网补缺(逐只)
            </label>
            <Button size="sm" disabled={selRunning} onClick={() => void startSelect()}>
              运行选股
            </Button>
            <Button size="sm" variant="outline" onClick={() => void apiJson("/api/stock/weekly/select/stop", { method: "POST" })}>
              停止
            </Button>
          </div>
          <p className="text-muted-foreground text-xs">
            {selStatus} {selPhase}
          </p>
          {selResult ? (
            <div className="space-y-2 text-xs">
              <p>
                目标周五: {selResult.target} · 连涨 {wk} 周 · 全市场 {selResult.universe_total || 0} 只 · 入选 {selResult.count || 0}
                {selResult.skipped_no_data != null ? ` · 无缓存跳过 ${selResult.skipped_no_data}` : ""}
                {selResult.allow_network === false ? " · 仅本地缓存" : ""}
              </p>
              {picks.length ? <WeeklyPickGrid picks={picks} weeks={wk} /> : (
                <p className="text-muted-foreground">该周五无连续 {wk} 周收涨的股票。</p>
              )}
            </div>
          ) : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>策略回测 (周一买入, 持有5日, 5%止损)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-muted-foreground text-xs">起</label>
            <Input type="date" className="w-36" value={btStart} onChange={(e) => setBtStart(e.target.value)} />
            <label className="text-muted-foreground text-xs">止</label>
            <Input type="date" className="w-36" value={btEnd} onChange={(e) => setBtEnd(e.target.value)} />
            <label className="text-muted-foreground text-xs">资金</label>
            <Input className="w-28" type="number" value={capital} onChange={(e) => setCapital(Number(e.target.value) || 0)} />
            <label className="text-muted-foreground text-xs">连涨周数</label>
            <Input className="w-16" type="number" value={btWeeks} onChange={(e) => setBtWeeks(Number(e.target.value) || 3)} />
            <Button size="sm" disabled={btRunning} onClick={() => void startBacktest()}>
              运行回测
            </Button>
            <Button size="sm" variant="outline" onClick={() => void apiJson("/api/stock/weekly/backtest/stop", { method: "POST" })}>
              停止
            </Button>
          </div>
          <p className="text-muted-foreground text-xs">
            {btStatus} {btPhase}
          </p>
          {btResult ? (
            <div className="space-y-2 text-xs">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                <Metric label="总收益" value={`${(m.total_return_pct || 0).toFixed(2)}%`} />
                <Metric label="年化" value={`${(m.annual_return_pct || 0).toFixed(2)}%`} />
                <Metric label="最大回撤" value={`${(m.max_drawdown_pct || 0).toFixed(2)}%`} />
                <Metric label="夏普" value={(m.sharpe_ratio || 0).toFixed(3)} />
                <Metric label="胜率" value={`${(m.win_rate_pct || 0).toFixed(2)}%`} />
                <Metric label="交易次数" value={String(m.total_trades || 0)} />
              </div>
              <p className="text-muted-foreground">
                连涨 {btResult.weeks || 3} 周 · 初始 {btResult.initial_capital} → 期末 {btResult.final_capital} · {btResult.start} ~ {btResult.end}
              </p>
              <EquitySvg curve={btResult.equity_curve || []} />
              {(btResult.trades || []).length ? (
                <details>
                  <summary className="cursor-pointer">交易明细 ({btResult.trades?.length} 笔)</summary>
                  <div className="mt-2">
                    <DataGrid
                      rows={(btResult.trades || []).slice(0, 300)}
                      columnDefs={TRADE_COLS}
                      getRowId={(p) => `${p.data.symbol || "t"}-${p.data.entry_date || ""}-${p.data.exit_date || ""}`}
                    />
                  </div>
                </details>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

function WeeklyPickGrid({ picks, weeks }: { picks: WeeklyPick[]; weeks: number }) {
  const columnDefs = useMemo<ColDef<WeeklyPick>[]>(() => {
    const weekCols: ColDef<WeeklyPick>[] = Array.from({ length: weeks }, (_, i) => ({
      colId: `w${i}`,
      headerName: `周${i + 1}`,
      width: 80,
      valueGetter: (p: ValueGetterParams<WeeklyPick>) => {
        const v = p.data?.returns?.[i];
        return v != null ? `${v}%` : "";
      },
    }));
    return [
      { field: "symbol", headerName: "代码", width: 90 },
      { field: "name", headerName: "名称", flex: 1, minWidth: 100 },
      { field: "week_close", headerName: "周收盘", width: 90 },
      ...weekCols,
      {
        colId: "cum",
        headerName: "累计",
        width: 90,
        valueGetter: (p: ValueGetterParams<WeeklyPick>) => {
          const rets = p.data?.returns || [];
          return `${rets.reduce((a, b) => a + (b || 0), 0).toFixed(2)}%`;
        },
      },
    ];
  }, [weeks]);
  return (
    <DataGrid rows={picks} columnDefs={columnDefs} getRowId={(p) => p.data.symbol || ""} />
  );
}

const TRADE_COLS: ColDef<{
  entry_date?: string;
  exit_date?: string;
  symbol?: string;
  name?: string;
  entry_price?: number;
  exit_price?: number;
  return_pct?: number;
  reason?: string;
}>[] = [
  { field: "entry_date", headerName: "买入日", width: 110 },
  { field: "exit_date", headerName: "卖出日", width: 110 },
  { field: "symbol", headerName: "代码", width: 90 },
  { field: "name", headerName: "名称", flex: 1, minWidth: 100 },
  { field: "entry_price", headerName: "买价", width: 90 },
  { field: "exit_price", headerName: "卖价", width: 90 },
  {
    field: "return_pct",
    headerName: "收益",
    width: 90,
    valueFormatter: (p) => (p.value == null ? "" : `${p.value}%`),
  },
  { field: "reason", headerName: "原因", flex: 1, minWidth: 120 },
];

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border p-2">
      <div className="text-muted-foreground">{label}</div>
      <div className="text-sm font-medium">{value}</div>
    </div>
  );
}

function EquitySvg({ curve }: { curve: { equity?: number }[] }) {
  if (curve.length < 2) return <p className="text-muted-foreground">无权益曲线数据</p>;
  const W = 460;
  const H = 120;
  const pad = 6;
  const vals = curve.map((p) => Number(p.equity || 0));
  const minV = Math.min(...vals);
  const maxV = Math.max(...vals);
  const span = maxV === minV ? 1 : maxV - minV;
  const n = vals.length;
  const pts = vals
    .map((v, i) => {
      const x = pad + ((W - 2 * pad) * i) / (n - 1);
      const y = H - pad - ((H - 2 * pad) * (v - minV)) / span;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="rounded-lg border">
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}
