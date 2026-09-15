import { useEffect, useState } from "react";
import { apiJson } from "@/lib/api";
import { renderReportMarkdown } from "@/lib/dailyFetch";
import {
  backtestMarkdown,
  changeDirection,
  drawdownMarkdown,
  formatChangePct,
  formatPrice,
  portfolioMarkdown,
  realtimeQuote,
  relativeStrengthMarkdown,
  stockReportMarkdown,
} from "@/lib/stockFormat";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Regime = { market?: { regime_zh?: string; advice?: string }; symbol_regime?: { regime_zh?: string } };
type Tab = "local" | "deepseek";

export function AnalyzePanel({
  symbol,
  onSymbolChange,
}: {
  symbol: string;
  onSymbolChange: (s: string) => void;
}) {
  const [cost, setCost] = useState("");
  const [deepseek, setDeepseek] = useState(false);
  const [tab, setTab] = useState<Tab>("local");
  const [regime, setRegime] = useState<Regime>({});
  const [localHtml, setLocalHtml] = useState("");
  const [dsHtml, setDsHtml] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [pdfUrl, setPdfUrl] = useState("");
  const [cache, setCache] = useState<Record<string, unknown> | null>(null);
  const [quote, setQuote] = useState<ReturnType<typeof realtimeQuote>>(null);
  const [uncertainty, setUncertainty] = useState<{ level?: string; level_zh?: string; ci_80_price?: number[] } | null>(null);

  useEffect(() => {
    const url = symbol.trim() ? `/api/stock/regime/${encodeURIComponent(symbol.trim())}` : "/api/stock/regime";
    apiJson<Regime>(url)
      .then(setRegime)
      .catch(() => setRegime({}));
  }, [symbol]);

  function payload(mode: string) {
    const body: Record<string, unknown> = { symbol: symbol.trim(), mode };
    const n = parseFloat(cost);
    if (n > 0) body.cost_price = n;
    return body;
  }

  function renderLocal(d: Record<string, unknown>) {
    setQuote(realtimeQuote(d));
    setUncertainty((d.uncertainty as typeof uncertainty) || null);
    setLocalHtml(renderReportMarkdown(stockReportMarkdown(d)));
    setCache({ ...d, symbol: symbol.trim() });
    setTab("local");
  }

  async function runFull() {
    if (!symbol.trim()) return;
    setBusy(true);
    setStatus("正在分析...（需要1-3分钟）");
    setLocalHtml("");
    setDsHtml("");
    setPdfUrl("");
    try {
      const data = await apiJson<Record<string, unknown>>("/api/stock/analyze", {
        method: "POST",
        body: JSON.stringify(payload("full")),
      });
      if (data.error) {
        setLocalHtml(`<p class="text-destructive">${String(data.error)}</p>`);
        setCache({ symbol: symbol.trim(), _local_error: data.error });
      } else {
        renderLocal(data);
      }
      if (deepseek) {
        setStatus("DeepSeek 分析中...");
        setTab("deepseek");
        const dsPayload: Record<string, unknown> = { symbol: symbol.trim() };
        const n = parseFloat(cost);
        if (n > 0) dsPayload.cost_price = n;
        const ds = await apiJson<Record<string, unknown>>("/api/stock/analyze/deepseek", {
          method: "POST",
          body: JSON.stringify(dsPayload),
        });
        let html = "";
        if (typeof ds.reasoning === "string" && ds.reasoning) {
          html += `<details class="mb-3"><summary class="text-primary cursor-pointer text-sm">推理过程 (Chain of Thought)</summary><pre class="bg-muted mt-2 max-h-96 overflow-auto rounded-lg p-2 text-xs whitespace-pre-wrap">${escapeHtml(ds.reasoning)}</pre></details>`;
        }
        if (ds.error) html += `<p class="text-destructive">${escapeHtml(String(ds.error))}</p>`;
        else html += renderReportMarkdown(String(ds.report || ""));
        const usage = ds.usage && typeof ds.usage === "object" ? (ds.usage as { total_tokens?: number }) : {};
        if (usage.total_tokens) {
          html += `<p class="text-muted-foreground mt-2 text-right text-xs">Model: ${String(ds.model || "")} | Tokens: ${usage.total_tokens}</p>`;
        }
        setDsHtml(html);
        setCache((prev) => ({
          ...(prev || { symbol: symbol.trim() }),
          symbol: symbol.trim(),
          deepseek_report: ds.report || "",
          deepseek_reasoning: ds.reasoning || "",
        }));
      }
      setStatus("");
    } catch (e) {
      setLocalHtml(`<p class="text-destructive">${escapeHtml(e instanceof Error ? e.message : String(e))}</p>`);
      setStatus("");
    } finally {
      setBusy(false);
    }
  }

  async function runPartial(mode: string) {
    if (!symbol.trim()) return;
    setBusy(true);
    setStatus("分析中...");
    setTab("local");
    try {
      const data = await apiJson<Record<string, unknown>>("/api/stock/analyze", {
        method: "POST",
        body: JSON.stringify({ symbol: symbol.trim(), mode }),
      });
      if (data.error) setLocalHtml(`<p class="text-destructive">${escapeHtml(String(data.error))}</p>`);
      else renderLocal(data);
      setStatus("");
    } catch (e) {
      setLocalHtml(`<p class="text-destructive">${escapeHtml(e instanceof Error ? e.message : String(e))}</p>`);
      setStatus("");
    } finally {
      setBusy(false);
    }
  }

  async function runMd(path: string, toMd: (d: Record<string, unknown>) => string, init?: RequestInit) {
    setBusy(true);
    setTab("local");
    setStatus("加载中...");
    try {
      const data = await apiJson<Record<string, unknown>>(path, init);
      if (data.error) setLocalHtml(`<p class="text-destructive">${escapeHtml(String(data.error))}</p>`);
      else setLocalHtml(renderReportMarkdown(toMd(data)));
      setStatus("");
    } catch (e) {
      setLocalHtml(`<p class="text-destructive">${escapeHtml(e instanceof Error ? e.message : String(e))}</p>`);
      setStatus("");
    } finally {
      setBusy(false);
    }
  }

  async function exportPdf() {
    if (!cache) return;
    const data = { ...cache, date: new Date().toISOString().slice(0, 10) };
    const r = await apiJson<{ pdf_url?: string }>("/api/stock/export-pdf", {
      method: "POST",
      body: JSON.stringify({ type: "stock_analysis", data }),
    });
    if (r.pdf_url) setPdfUrl(r.pdf_url);
  }

  const qDir = changeDirection(quote?.changePct);
  const qColor = qDir === "up" ? "#dc2626" : qDir === "down" ? "#16a34a" : undefined;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Analyze</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-muted-foreground text-xs">
          市场: {regime.market?.regime_zh || "未知"} {regime.market?.advice ? `— ${regime.market.advice}` : ""}
          {regime.symbol_regime?.regime_zh ? ` | 个股: ${regime.symbol_regime.regime_zh}` : ""}
        </p>
        <div className="flex flex-wrap gap-2">
          <Input className="w-32" placeholder="代码" value={symbol} onChange={(e) => onSymbolChange(e.target.value)} />
          <Input className="w-28" placeholder="成本价 (选填)" value={cost} onChange={(e) => setCost(e.target.value)} />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={deepseek} onChange={(e) => setDeepseek(e.target.checked)} />
            DeepSeek
          </label>
          <Button size="sm" disabled={busy || !symbol.trim()} onClick={() => void runFull()}>
            全面分析
          </Button>
        </div>
        <div className="flex flex-wrap gap-1">
          <Button size="xs" variant="outline" disabled={busy || !symbol.trim()} onClick={() => void runPartial("technical")}>
            技术分析
          </Button>
          <Button size="xs" variant="outline" disabled={busy || !symbol.trim()} onClick={() => void runPartial("fundamental")}>
            基本面
          </Button>
          <Button size="xs" variant="outline" disabled={busy || !symbol.trim()} onClick={() => void runPartial("sentiment")}>
            情绪分析
          </Button>
          <Button size="xs" variant="outline" disabled={busy || !symbol.trim()} onClick={() => void runPartial("xgboost")}>
            ML预测
          </Button>
          <Button size="xs" variant="outline" disabled={busy || !symbol.trim()} onClick={() => void runPartial("fund_flow")}>
            聪明钱
          </Button>
          <Button size="xs" variant="outline" disabled={busy || !symbol.trim()} onClick={() => void runPartial("valuation")}>
            估值
          </Button>
          <Button size="xs" variant="outline" disabled={busy} onClick={() => void runMd("/api/stock/portfolio", portfolioMarkdown)}>
            仓位
          </Button>
          <Button size="xs" variant="outline" disabled={busy} onClick={() => void runMd("/api/stock/drawdown", drawdownMarkdown)}>
            回撤
          </Button>
          <Button size="xs" variant="outline" disabled={busy} onClick={() => void runMd("/api/stock/relative-strength", relativeStrengthMarkdown)}>
            相对强度
          </Button>
          <Button
            size="xs"
            variant="outline"
            disabled={busy || !symbol.trim()}
            onClick={() =>
              void runMd(`/api/stock/backtest/${encodeURIComponent(symbol.trim())}`, backtestMarkdown, {
                method: "POST",
                body: JSON.stringify({ strategy: "momentum", capital: 500000 }),
              })
            }
          >
            回测
          </Button>
          <Button size="xs" variant="outline" disabled={!cache} onClick={() => void exportPdf()}>
            导出PDF
          </Button>
        </div>
        {status ? <p className="text-muted-foreground text-xs">{status}</p> : null}
        {pdfUrl ? (
          <a className="text-sm underline" href={pdfUrl} target="_blank" rel="noreferrer">
            Download PDF
          </a>
        ) : null}
        {deepseek && (localHtml || dsHtml) ? (
          <div className="flex gap-1">
            <Button size="xs" variant={tab === "local" ? "default" : "outline"} onClick={() => setTab("local")}>
              本地
            </Button>
            <Button size="xs" variant={tab === "deepseek" ? "default" : "outline"} onClick={() => setTab("deepseek")}>
              DeepSeek
            </Button>
          </div>
        ) : null}
        {tab === "local" && quote ? (
          <div className="rounded-xl border p-3 text-sm">
            <div className="flex flex-wrap items-baseline gap-3">
              <span className="text-muted-foreground text-xs">实时行情</span>
              <span className="text-xl font-medium" style={{ color: qColor }}>
                {formatPrice(quote.last)}
              </span>
              <span style={{ color: qColor }}>{formatChangePct(quote.changePct)}</span>
            </div>
            <div className="text-muted-foreground mt-1 flex flex-wrap gap-3 text-xs">
              {quote.open != null ? <span>今开: {formatPrice(quote.open)}</span> : null}
              {quote.high != null ? <span>最高: {formatPrice(quote.high)}</span> : null}
              {quote.low != null ? <span>最低: {formatPrice(quote.low)}</span> : null}
              {quote.prevClose != null ? <span>昨收: {formatPrice(quote.prevClose)}</span> : null}
            </div>
          </div>
        ) : null}
        {tab === "local" && uncertainty ? (
          <p className="text-muted-foreground text-xs">
            模型不确定性: <strong>{uncertainty.level_zh || uncertainty.level}</strong>
            {uncertainty.ci_80_price?.length === 2
              ? ` | 80%区间: ¥${uncertainty.ci_80_price[0]} ~ ¥${uncertainty.ci_80_price[1]}`
              : ""}
          </p>
        ) : null}
        {tab === "local" && localHtml ? (
          <div className="bg-muted/40 max-h-[60vh] overflow-auto rounded-xl border p-3 text-sm" dangerouslySetInnerHTML={{ __html: localHtml }} />
        ) : null}
        {tab === "deepseek" && dsHtml ? (
          <div className="bg-muted/40 max-h-[60vh] overflow-auto rounded-xl border p-3 text-sm" dangerouslySetInnerHTML={{ __html: dsHtml }} />
        ) : null}
      </CardContent>
    </Card>
  );
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
