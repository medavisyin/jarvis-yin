import { useEffect, useMemo, useState } from "react";
import { apiJson } from "@/lib/api";
import { DualMap } from "@/features/news/worldMonitor/DualMap";
import {
  LOOKBACK_DAYS,
  classifyInsight,
  headlinesForHub,
  headlinesForLayers,
  hubLabelOf,
  type MonitorDashboard,
  type MonitorVariant,
} from "@/lib/worldMonitor";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const VARIANT_LABEL: Record<MonitorVariant, string> = {
  world: "World",
  tech: "Tech",
  finance: "Finance",
  commodity: "Commodity",
  happy: "Happy",
  energy: "Energy",
};

export function WorldMonitorPage() {
  const date = new Date().toISOString().slice(0, 10);
  const [variant, setVariant] = useState<MonitorVariant>("world");
  const [lookback, setLookback] = useState<(typeof LOOKBACK_DAYS)[number]>(1);
  const [engine, setEngine] = useState<"globe" | "flat">("globe");
  const [dash, setDash] = useState<MonitorDashboard | null>(null);
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});
  const [error, setError] = useState("");
  const [selectedHubId, setSelectedHubId] = useState<string | null>(null);
  const [insight, setInsight] = useState("");
  const [loading, setLoading] = useState(false);

  async function load(nextVariant = variant, nextLookback = lookback) {
    setError("");
    setLoading(true);
    try {
      const data = await apiJson<MonitorDashboard>(
        `/api/toolbar/world-monitor?date=${encodeURIComponent(date)}&variant=${encodeURIComponent(nextVariant)}&lookback=${nextLookback}`,
      );
      setDash(data);
      const on: Record<string, boolean> = {};
      (data.layer_catalog || []).forEach((ly) => {
        on[ly.id] = true;
      });
      setEnabled(on);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load().catch((e: Error) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const panels = useMemo(() => new Set((dash?.panels || []).map((p) => p.id)), [dash]);
  const visibleHeadlines = useMemo(
    () => headlinesForHub(headlinesForLayers(dash?.headlines || [], enabled), selectedHubId, dash?.points || []),
    [dash, selectedHubId, enabled],
  );
  const hubLabel = hubLabelOf(dash, selectedHubId);
  const insightKind = classifyInsight(insight);

  useEffect(() => {
    if (!selectedHubId) {
      setInsight("");
      return;
    }
    let cancelled = false;
    setInsight("Ollama…");
    void apiJson<{ insight?: string; error?: string }>("/api/toolbar/world-monitor/insight", {
      method: "POST",
      body: JSON.stringify({ date, variant, lookback, hub_id: selectedHubId }),
    })
      .then((data) => {
        if (!cancelled) setInsight(data.insight || data.error || "");
      })
      .catch((e: Error) => {
        if (!cancelled) setInsight(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedHubId, date, variant, lookback]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex flex-wrap gap-1">
          {(dash?.variants || (Object.keys(VARIANT_LABEL) as MonitorVariant[])).map((v) => (
            <Button
              key={v}
              size="sm"
              variant={v === variant ? "default" : "outline"}
              onClick={() => {
                setVariant(v);
                void load(v, lookback).catch((e: Error) => setError(e.message));
              }}
            >
              {VARIANT_LABEL[v] || v}
            </Button>
          ))}
        </div>
        <div className="flex rounded-lg border text-sm">
          <Button
            size="sm"
            variant={engine === "globe" ? "default" : "ghost"}
            onClick={() => setEngine("globe")}
          >
            3D 地球
          </Button>
          <Button
            size="sm"
            variant={engine === "flat" ? "default" : "ghost"}
            onClick={() => setEngine("flat")}
          >
            2D 地图
          </Button>
        </div>
        <Button size="sm" onClick={() => void load(variant, lookback).catch((e: Error) => setError(e.message))}>
          Reload
        </Button>
      </div>
      {error ? <p className="text-destructive text-sm">{error}</p> : null}
      <p className="text-muted-foreground text-xs">
        点击光点后，下方 Headlines 只显示该地新闻，并由本地 Ollama 写一段 insight。时间窗口是最近 N 个 Daily Fetch 日期。
        {dash
          ? ` · ${dash.stats.world_items} 条新闻 · ${dash.stats.points} 个定位 · ${lookback}d${dash.days?.length ? `（${dash.days.join(" · ")}）` : ""}`
          : ""}
        {loading ? " · 加载中…" : ""}
      </p>
      {dash ? (
        <DualMap
          engine={engine}
          points={dash.points}
          enabled={enabled}
          selectedHubId={selectedHubId}
          onSelectHub={setSelectedHubId}
        />
      ) : null}
      <div className="grid gap-3 md:grid-cols-2">
        {panels.has("layers") ? (
          <Card>
            <CardHeader>
              <CardTitle>Map layers</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="flex flex-wrap gap-1">
                {LOOKBACK_DAYS.map((n) => (
                  <Button
                    key={n}
                    size="sm"
                    variant={lookback === n ? "default" : "outline"}
                    onClick={() => {
                      setLookback(n);
                      void load(variant, n).catch((e: Error) => setError(e.message));
                    }}
                    disabled={loading}
                  >
                    {n}d
                  </Button>
                ))}
              </div>
              {(dash?.layer_catalog || []).map((ly) => (
                <label key={ly.id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={enabled[ly.id] !== false}
                    onChange={(e) => setEnabled((prev) => ({ ...prev, [ly.id]: e.target.checked }))}
                  />
                  {ly.label}
                </label>
              ))}
            </CardContent>
          </Card>
        ) : null}
        {panels.has("headlines") ? (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
              <CardTitle>
                {selectedHubId ? `${hubLabel} · ${visibleHeadlines.length} 条` : "Headlines"}
              </CardTitle>
              {selectedHubId ? (
                <Button size="sm" variant="ghost" onClick={() => setSelectedHubId(null)}>
                  显示全部
                </Button>
              ) : null}
            </CardHeader>
            <CardContent className="max-h-80 space-y-2 overflow-y-auto text-sm">
              {selectedHubId && insightKind === "pending" ? (
                <p className="text-muted-foreground text-xs">正在生成本地 insight…</p>
              ) : null}
              {selectedHubId && insightKind === "ok" ? (
                <p className="bg-muted rounded px-2 py-2 text-sm whitespace-pre-wrap">{insight}</p>
              ) : null}
              {visibleHeadlines.length === 0 ? (
                <p className="text-muted-foreground">
                  {selectedHubId ? "该地点在当前时间窗口没有匹配新闻。" : "暂无标题。"}
                </p>
              ) : (
                visibleHeadlines.map((h, i) => (
                  <div key={`${h.title}-${i}`} className="block w-full rounded px-1 py-1 text-left">
                    <a
                      className="underline"
                      href={h.url || "#"}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {h.title}
                    </a>
                    <div className="text-muted-foreground text-xs">
                      {h.source} {(h.hubs || []).join(", ")} {(h.streams || []).join(" · ")}
                      {h.report_date ? ` · ${h.report_date}` : ""}
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        ) : null}
        {panels.has("correlation") ? (
          <Card>
            <CardHeader>
              <CardTitle>Cross-stream correlation</CardTitle>
            </CardHeader>
            <CardContent className="max-h-64 space-y-2 overflow-y-auto text-sm">
              {(dash?.correlation || []).length === 0 ? (
                <p className="text-muted-foreground">No hub with two+ of military / economic / disaster / escalation.</p>
              ) : (
                (dash?.correlation || []).map((c) => (
                  <button
                    type="button"
                    key={c.hub_id}
                    className={`block w-full rounded px-1 py-1 text-left ${selectedHubId === c.hub_id ? "bg-sky-100 dark:bg-sky-900/40" : ""}`}
                    onClick={() => setSelectedHubId(c.hub_id)}
                  >
                    <div className="font-medium">
                      {c.label}: {c.streams.join(" + ")}
                    </div>
                    <div className="text-muted-foreground text-xs">{c.titles.join(" · ")}</div>
                  </button>
                ))
              )}
            </CardContent>
          </Card>
        ) : null}
        {panels.has("finance_radar") ? (
          <Card>
            <CardHeader>
              <CardTitle>Finance radar</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {(["exchanges", "commodities", "crypto", "composite"] as const).map((k) => (
                <div key={k}>
                  <div className="font-medium">
                    {k} · {dash?.finance_radar?.[k].count ?? 0}
                  </div>
                  <div className="text-muted-foreground text-xs">
                    {(dash?.finance_radar?.[k].titles || []).slice(0, 4).join(" · ")}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
