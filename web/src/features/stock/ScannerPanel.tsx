import { useEffect, useRef, useState } from "react";
import { apiJson } from "@/lib/api";
import { pollJob } from "@/lib/jobs";
import { formatScannerStatus } from "@/lib/scannerResults";
import { HistoryList, ScannerResultBody } from "@/features/stock/scannerViews";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type ScanKind = {
  id: string;
  label: string;
  start: string;
  status: string;
  stop: string;
  result: string;
  history?: string;
  datedResult?: (date: string) => string;
};

const SCANS: ScanKind[] = [
  { id: "unified", label: "Left-Right-ATH", start: "/api/stock/unified_scan/start", status: "/api/stock/unified_scan/status", stop: "/api/stock/unified_scan/stop", result: "/api/stock/unified_scan/result" },
  { id: "scan", label: "AI scan", start: "/api/stock/scan/start", status: "/api/stock/scan/status", stop: "/api/stock/scan/stop", result: "/api/stock/scan/result", history: "/api/stock/scan/history", datedResult: (d) => `/api/stock/scan/result/${d}` },
  { id: "long-term", label: "Long-term", start: "/api/stock/long-term/start", status: "/api/stock/long-term/status", stop: "/api/stock/long-term/stop", result: "/api/stock/long-term/result", history: "/api/stock/long-term/history", datedResult: (d) => `/api/stock/long-term/result/${d}` },
  { id: "qv", label: "Quality-value", start: "/api/stock/quality-value/start", status: "/api/stock/quality-value/status", stop: "/api/stock/quality-value/stop", result: "/api/stock/quality-value/result", history: "/api/stock/quality-value/history", datedResult: (d) => `/api/stock/quality-value/result/${d}` },
  { id: "midday", label: "Midday", start: "/api/stock/midday/start", status: "/api/stock/midday/status", stop: "/api/stock/midday/stop", result: "/api/stock/midday/result" },
  { id: "right", label: "Right-side", start: "/api/stock/right_side/start", status: "/api/stock/right_side/status", stop: "/api/stock/right_side/stop", result: "/api/stock/right_side/result" },
];

const PDF_TYPE: Record<string, string> = {
  scan: "short_term",
  unified: "short_term",
  midday: "short_term",
  right: "short_term",
  "long-term": "long_term",
  qv: "quality_value",
};

export function ScannerPanel({ onAnalyze }: { onAnalyze: (symbol: string) => void }) {
  const [kind, setKind] = useState(SCANS[0]);
  const [status, setStatus] = useState<Record<string, unknown>>({});
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [deepseek, setDeepseek] = useState(false);
  const [horizon, setHorizon] = useState<"long" | "medium">("long");
  const [running, setRunning] = useState(false);
  const [pdfUrl, setPdfUrl] = useState("");
  const [error, setError] = useState("");
  const [history, setHistory] = useState<{ date?: string; picks?: unknown[] }[] | null>(null);
  const kindIdRef = useRef(kind.id);
  kindIdRef.current = kind.id;
  const abortRef = useRef<AbortController | null>(null);

  function resultFromError(e: unknown): Record<string, unknown> {
    return { error: e instanceof Error ? e.message : String(e), picks: [] };
  }

  useEffect(() => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    let cancelled = false;
    setPdfUrl("");
    setError("");
    setHistory(null);
    apiJson<Record<string, unknown>>(kind.status)
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        if (!cancelled) setStatus({});
      });
    apiJson<Record<string, unknown>>(kind.result)
      .then((r) => {
        if (!cancelled) setResult(r);
      })
      .catch((e: unknown) => {
        if (!cancelled) setResult(resultFromError(e));
      });
    return () => {
      cancelled = true;
      ac.abort();
      setRunning(false);
    };
  }, [kind]);

  async function start() {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    const startedId = kind.id;
    setRunning(true);
    setResult(null);
    setPdfUrl("");
    setError("");
    setHistory(null);
    try {
      const body: Record<string, unknown> = { use_deepseek: deepseek };
      if (kind.id === "qv") body.horizon = horizon;
      await apiJson(kind.start, { method: "POST", body: JSON.stringify(body) });
      const done = await pollJob(
        () => apiJson<Record<string, unknown> & { status?: string }>(kind.status),
        (job) => {
          if (kindIdRef.current === startedId) setStatus(job);
        },
        { intervalMs: 4000, signal: ac.signal },
      );
      if (kindIdRef.current !== startedId) return;
      setStatus(done);
      try {
        const latest = await apiJson<Record<string, unknown>>(kind.result);
        if (kindIdRef.current !== startedId) return;
        setResult(latest);
      } catch (e) {
        if (kindIdRef.current !== startedId) return;
        setResult(resultFromError(e));
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      if (kindIdRef.current !== startedId) return;
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (kindIdRef.current === startedId) setRunning(false);
    }
  }

  async function exportPdf() {
    if (!result) return;
    const r = await apiJson<{ pdf_url?: string }>("/api/stock/export-pdf", {
      method: "POST",
      body: JSON.stringify({ type: PDF_TYPE[kind.id] || "short_term", data: result }),
    });
    if (r.pdf_url) setPdfUrl(r.pdf_url);
  }

  async function loadHistory() {
    if (!kind.history) return;
    setError("");
    try {
      const d = await apiJson<{ history?: { date?: string; picks?: unknown[] }[] }>(kind.history);
      setHistory(d.history || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function loadDated(date: string) {
    if (!kind.datedResult) return;
    setHistory(null);
    try {
      const d = await apiJson<Record<string, unknown>>(kind.datedResult(date));
      setResult(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Scanners</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-1">
          {SCANS.map((s) => (
            <Button key={s.id} size="sm" variant={kind.id === s.id ? "default" : "outline"} onClick={() => setKind(s)}>
              {s.label}
            </Button>
          ))}
        </div>
        {kind.id === "qv" ? (
          <label className="flex items-center gap-2 text-sm">
            持有口径
            <select
              className="border-input bg-background h-7 rounded-md border px-2 text-sm"
              value={horizon}
              onChange={(e) => setHorizon(e.target.value === "medium" ? "medium" : "long")}
            >
              <option value="long">6 个月～2 年</option>
              <option value="medium">1 个月～6 个月</option>
            </select>
          </label>
        ) : null}
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={deepseek} onChange={(e) => setDeepseek(e.target.checked)} />
          Use DeepSeek
        </label>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={running} onClick={() => void start()}>
            Start
          </Button>
          <Button size="sm" variant="outline" onClick={() => void apiJson(kind.stop, { method: "POST" })}>
            Stop
          </Button>
          {kind.history ? (
            <Button size="sm" variant="outline" onClick={() => void loadHistory()}>
              历史记录
            </Button>
          ) : null}
          <Button size="sm" variant="outline" disabled={!result} onClick={() => void exportPdf()}>
            Export PDF
          </Button>
        </div>
        <p className="text-muted-foreground text-xs">{formatScannerStatus(status, kind.id)}</p>
        {error ? <p className="text-destructive text-sm">{error}</p> : null}
        {pdfUrl ? (
          <a className="text-sm underline" href={pdfUrl} target="_blank" rel="noreferrer">
            Download PDF
          </a>
        ) : null}
        {history ? (
          <HistoryList
            entries={history}
            onPickDate={(d) => {
              void loadDated(d);
            }}
          />
        ) : (
          <ScannerResultBody kindId={kind.id} result={result} onAnalyze={onAnalyze} />
        )}
      </CardContent>
    </Card>
  );
}
