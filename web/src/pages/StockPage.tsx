import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { Outlet, useNavigate, useSearchParams } from "react-router-dom";
import { apiJson } from "@/lib/api";
import { AnalyzePanel } from "@/features/stock/AnalyzePanel";
import { NationalTeamPanel } from "@/features/stock/NationalTeamPanel";
import { ScannerPanel } from "@/features/stock/ScannerPanel";
import { TrainPanel } from "@/features/stock/TrainPanel";
import { WeeklyPanel } from "@/features/stock/WeeklyPanel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PageFrame } from "@/layouts/PageFrame";

const WatchlistGrid = lazy(() =>
  import("@/features/stock/WatchlistGrid").then((m) => ({ default: m.WatchlistGrid })),
);

type Stock = {
  symbol: string;
  name?: string;
  sector?: string;
  latest_price?: number;
  change_pct?: number;
  volume?: number;
};

type Prefetch = {
  running?: boolean;
  status?: string;
  progress_pct?: number;
  can_resume?: boolean;
  message?: string;
};

export function StockLayout() {
  return (
    <PageFrame title="Stock">
      <Outlet />
    </PageFrame>
  );
}

export function StockWatchPage() {
  const nav = useNavigate();
  return <WatchlistPanel onAnalyze={(sym) => nav(`/stock/analyze?symbol=${encodeURIComponent(sym)}`)} />;
}

export function StockScanPage() {
  const nav = useNavigate();
  return <ScannerPanel onAnalyze={(sym) => nav(`/stock/analyze?symbol=${encodeURIComponent(sym)}`)} />;
}

export function StockWeeklyPage() {
  return <WeeklyPanel />;
}

export function StockAnalyzePage() {
  const [params, setParams] = useSearchParams();
  const symbol = params.get("symbol") || "";
  return (
    <AnalyzePanel
      symbol={symbol}
      onSymbolChange={(s) => setParams(s ? { symbol: s } : {}, { replace: true })}
    />
  );
}

export function StockNationalPage() {
  return <NationalTeamPanel />;
}

export function StockTrainPage() {
  return <TrainPanel />;
}

function WatchlistPanel({ onAnalyze }: { onAnalyze: (symbol: string) => void }) {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [symbol, setSymbol] = useState("");
  const [name, setName] = useState("");
  const [sector, setSector] = useState("");
  const [error, setError] = useState("");
  const [prefetch, setPrefetch] = useState<Prefetch>({});
  const [busy, setBusy] = useState(false);
  const [pdfUrl, setPdfUrl] = useState("");

  const load = useCallback(async () => {
    const data = await apiJson<{ stocks?: Stock[]; error?: string }>("/api/stock/watchlist");
    setStocks(data.stocks || []);
  }, []);

  const loadPrefetch = useCallback(async () => {
    const data = await apiJson<Prefetch>("/api/stock/prefetch/status");
    setPrefetch(data);
  }, []);

  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
    loadPrefetch().catch(() => undefined);
  }, [load, loadPrefetch]);

  async function add() {
    setError("");
    await apiJson("/api/stock/watchlist", {
      method: "POST",
      body: JSON.stringify({ symbol, name, sector }),
    });
    setSymbol("");
    setName("");
    setSector("");
    await load();
  }

  async function remove(sym: string) {
    await apiJson(`/api/stock/watchlist/${sym}`, { method: "DELETE" });
    await load();
  }

  async function refresh() {
    setBusy(true);
    try {
      const data = await apiJson<{ stocks?: Stock[] }>("/api/stock/watchlist/refresh", { method: "POST" });
      setStocks(data.stocks || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function exportPdf() {
    const r = await apiJson<{ pdf_url?: string }>("/api/stock/export-pdf", {
      method: "POST",
      body: JSON.stringify({ type: "watchlist", data: { stocks, date: new Date().toISOString().slice(0, 10) } }),
    });
    if (r.pdf_url) setPdfUrl(r.pdf_url);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Watchlist</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Input className="w-28" placeholder="Code" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
        <Input className="w-32" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <Input className="w-32" placeholder="Sector" value={sector} onChange={(e) => setSector(e.target.value)} />
        <Button size="sm" onClick={() => void add()} disabled={!symbol.trim()}>
          Add
        </Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={() => void refresh()}>
          Refresh prices
        </Button>
        <Button size="sm" variant="outline" disabled={!stocks.length} onClick={() => void exportPdf()}>
          导出PDF
        </Button>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={() => void apiJson("/api/stock/prefetch/start", { method: "POST", body: "{}" }).then(loadPrefetch)}>
          Prefetch
        </Button>
        <Button size="sm" variant="outline" onClick={() => void apiJson("/api/stock/prefetch/pause", { method: "POST" }).then(loadPrefetch)}>
          Pause
        </Button>
        <Button size="sm" variant="outline" onClick={() => void apiJson("/api/stock/prefetch/resume", { method: "POST" }).then(loadPrefetch)}>
          Resume
        </Button>
        <Button size="sm" variant="outline" onClick={() => void apiJson("/api/stock/prefetch/stop", { method: "POST" }).then(loadPrefetch)}>
          Stop
        </Button>
        <span className="text-muted-foreground text-xs">
          {prefetch.status || (prefetch.running ? "running" : "idle")} {prefetch.progress_pct != null ? `${prefetch.progress_pct}%` : ""}
        </span>
      </div>
      {pdfUrl ? (
        <a className="text-sm underline" href={pdfUrl} target="_blank" rel="noreferrer">
          Download PDF
        </a>
      ) : null}
      {error ? <p className="text-destructive text-sm">{error}</p> : null}
      <Suspense fallback={<p className="text-muted-foreground text-sm">Loading grid…</p>}>
        <WatchlistGrid rows={stocks} onRemove={(sym) => void remove(sym)} onAnalyze={onAnalyze} />
      </Suspense>
      </CardContent>
    </Card>
  );
}
