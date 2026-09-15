import { useEffect, useState } from "react";
import { apiJson } from "@/lib/api";
import { isTerminalJobStatus, wait } from "@/lib/jobs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataGrid } from "@/components/DataGrid";
import type { ColDef } from "ag-grid-community";

type TrainStatus = {
  status?: string;
  completed?: number;
  total?: number;
  current?: string;
  ok?: boolean;
  error?: string;
  results?: Record<string, unknown>[];
  verifications?: Record<string, unknown>[];
  sentiment?: Record<string, unknown>;
  black_swan?: Record<string, unknown>;
  aggregate_stats?: Record<string, unknown>;
};

export function TrainPanel() {
  const [deepseek, setDeepseek] = useState(false);
  const [st, setSt] = useState<TrainStatus>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pdfUrl, setPdfUrl] = useState("");

  useEffect(() => {
    apiJson<TrainStatus>("/api/stock/train/status")
      .then(setSt)
      .catch(() => undefined);
  }, []);

  async function start() {
    setBusy(true);
    setError("");
    setPdfUrl("");
    try {
      const started = await apiJson<TrainStatus>("/api/stock/train/daily", {
        method: "POST",
        body: JSON.stringify({ use_deepseek: deepseek }),
      });
      if (started.ok === false) throw new Error(started.error || "启动失败");
      let sawRunning = false;
      for (;;) {
        const s = await apiJson<TrainStatus>("/api/stock/train/status");
        setSt(s);
        if (s.status === "running") sawRunning = true;
        if (s.status === "error") break;
        if (sawRunning && isTerminalJobStatus(s.status)) break;
        if (sawRunning && s.status === "idle") break;
        await wait(3000);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function exportPdf() {
    if (!st.results && !st.verifications) return;
    const r = await apiJson<{ pdf_url?: string }>("/api/stock/export-pdf", {
      method: "POST",
      body: JSON.stringify({ type: "price_prediction", data: { ...st, date: new Date().toISOString().slice(0, 10) } }),
    });
    if (r.pdf_url) setPdfUrl(r.pdf_url);
  }

  const pct = st.total ? Math.round(((st.completed || 0) / st.total) * 100) : 0;
  const running = st.status === "running" || busy;
  const fg = st.sentiment && typeof st.sentiment.fear_greed === "object" ? (st.sentiment.fear_greed as Record<string, unknown>) : null;
  const results = st.results || [];
  const verifications = (st.verifications || []).filter((v) => v.actual_close != null);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Price train</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={running} onClick={() => void start()}>
          开始训练
        </Button>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={deepseek} onChange={(e) => setDeepseek(e.target.checked)} />
          启用 DeepSeek 专家校准
        </label>
        <Button size="sm" variant="outline" disabled={!results.length && !verifications.length} onClick={() => void exportPdf()}>
          导出PDF
        </Button>
        <span className="text-muted-foreground text-xs">
          {st.status === "idle" ? "就绪" : st.status === "done" ? `训练完成 (${results.length} 只股票)` : `${st.completed || 0}/${st.total || 0}`}
        </span>
      </div>
      <p className="text-muted-foreground text-xs">为自选股训练明日价格预测：预测收盘价、最高价、最低价。</p>
      {running && st.status === "running" ? (
        <div>
          <div className="bg-muted h-5 overflow-hidden rounded-lg">
            <div className="bg-primary h-full text-center text-[10px] leading-5 text-white" style={{ width: `${pct}%` }}>
              {pct}%
            </div>
          </div>
          <p className="text-muted-foreground mt-1 text-xs">{st.current}</p>
        </div>
      ) : null}
      {error ? <p className="text-destructive text-sm">{error}</p> : null}
      {pdfUrl ? (
        <a className="text-sm underline" href={pdfUrl} target="_blank" rel="noreferrer">
          Download PDF
        </a>
      ) : null}
      {fg ? (
        <Card size="sm">
          <CardHeader>
            <CardTitle>市场情绪</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <p>
              {String(fg.value ?? "")} {String(fg.label || "")}
            </p>
          </CardContent>
        </Card>
      ) : null}
      {verifications.length ? (
        <div className="space-y-1">
          <p className="text-sm font-medium">昨日预测验证</p>
          <DataGrid
            rows={verifications}
            columnDefs={VERIFY_COLS}
            getRowId={(p) => String(p.data.symbol || p.data.name || "")}
          />
        </div>
      ) : null}
      {results.length ? (
        <div className="space-y-1">
          <p className="text-sm font-medium">明日价格预测</p>
          <DataGrid
            rows={results}
            columnDefs={PRED_COLS}
            getRowId={(p) => String(p.data.symbol || "")}
          />
        </div>
      ) : null}
      </CardContent>
    </Card>
  );
}

function num(v: unknown): string {
  return typeof v === "number" ? `¥${v.toFixed(2)}` : "-";
}

function isPending(r: Record<string, unknown> | undefined): boolean {
  return Boolean(r?.pending || r?.error || !r?.predictions);
}

const VERIFY_COLS: ColDef<Record<string, unknown>>[] = [
  {
    colId: "stock",
    headerName: "股票",
    flex: 1,
    minWidth: 140,
    valueGetter: (p) => String(p.data?.name || p.data?.symbol || ""),
    cellRenderer: (p: { data?: Record<string, unknown> }) => (
      <div>
        <div>{String(p.data?.name || p.data?.symbol || "")}</div>
        <div className="text-muted-foreground text-xs">{String(p.data?.target_date || "")}</div>
      </div>
    ),
  },
  { colId: "pred", headerName: "预测收盘", width: 110, valueGetter: (p) => num(p.data?.predicted_close) },
  { colId: "act", headerName: "实际收盘", width: 110, valueGetter: (p) => num(p.data?.actual_close) },
  {
    colId: "err",
    headerName: "误差",
    width: 90,
    valueGetter: (p) => (p.data?.error_pct_close != null ? `${Number(p.data.error_pct_close).toFixed(2)}%` : "-"),
  },
  { colId: "ph", headerName: "预测最高", width: 110, valueGetter: (p) => num(p.data?.predicted_high) },
  { colId: "ah", headerName: "实际最高", width: 110, valueGetter: (p) => num(p.data?.actual_high) },
  { colId: "pl", headerName: "预测最低", width: 110, valueGetter: (p) => num(p.data?.predicted_low) },
  { colId: "al", headerName: "实际最低", width: 110, valueGetter: (p) => num(p.data?.actual_low) },
  {
    colId: "dir",
    headerName: "方向",
    width: 80,
    valueGetter: (p) => (p.data?.direction_correct === true ? "✓" : p.data?.direction_correct === false ? "✗" : "—"),
  },
];

const PRED_COLS: ColDef<Record<string, unknown>>[] = [
  {
    colId: "stock",
    headerName: "股票",
    flex: 1,
    minWidth: 140,
    valueGetter: (p) => `${p.data?.name || p.data?.symbol || ""} ${p.data?.symbol || ""}`.trim(),
  },
  {
    colId: "cur",
    headerName: "当前价",
    width: 100,
    valueGetter: (p) => (isPending(p.data) ? "待训练" : num(p.data?.current_close)),
  },
  {
    colId: "close",
    headerName: "预测收盘",
    width: 110,
    valueGetter: (p) => {
      if (isPending(p.data)) return "";
      const pred = p.data?.predictions as Record<string, number> | undefined;
      return num(pred?.close);
    },
  },
  {
    colId: "high",
    headerName: "预测最高",
    width: 110,
    valueGetter: (p) => {
      if (isPending(p.data)) return "";
      const pred = p.data?.predictions as Record<string, number> | undefined;
      return num(pred?.high);
    },
  },
  {
    colId: "low",
    headerName: "预测最低",
    width: 110,
    valueGetter: (p) => {
      if (isPending(p.data)) return "";
      const pred = p.data?.predictions as Record<string, number> | undefined;
      return num(pred?.low);
    },
  },
  {
    colId: "chg",
    headerName: "涨跌幅",
    width: 90,
    valueGetter: (p) => {
      if (isPending(p.data)) return "";
      const c = p.data?.change_pct as Record<string, number> | undefined;
      const pct = c?.close != null ? `${c.close > 0 ? "+" : ""}${Number(c.close).toFixed(2)}%` : "";
      const dir = typeof p.data?.direction_label === "string" ? p.data.direction_label : "";
      return [pct, dir].filter(Boolean).join(" ");
    },
  },
  {
    colId: "health",
    headerName: "健康",
    width: 80,
    valueGetter: (p) => {
      if (isPending(p.data)) return "";
      const hl = p.data?.health as Record<string, string> | undefined;
      return hl?.grade || "-";
    },
  },
];
