export type MonitorVariant = "world" | "tech" | "finance" | "commodity" | "happy" | "energy";

export type MonitorPoint = {
  layer: string;
  lat: number;
  lon: number;
  hub_id?: string;
  hub_label?: string;
  title?: string;
  source?: string;
  url?: string;
};

export type HubCluster = {
  hub_id: string;
  lat: number;
  lon: number;
  label: string;
  count: number;
  titles: string[];
  layers: string[];
};

export type MonitorHeadline = {
  title?: string;
  source?: string;
  sources?: string[];
  source_count?: number;
  source_tier?: number;
  url?: string;
  streams?: string[];
  layers?: string[];
  news_category?: string;
  hubs?: string[];
  hub_ids?: string[];
  country_ids?: string[];
  report_date?: string;
};

export type RadarQuote = {
  id: string;
  symbol?: string;
  label: string;
  value: number | null;
  change_pct?: number | null;
  source?: string;
};

export type FinanceRadarSignals = {
  fear_greed: { value: number | null; label?: string; source?: string };
  vix: { value: number | null; change_pct?: number | null; source?: string };
  quotes: RadarQuote[];
  mood?: { risk_level?: string; signals?: string[]; recommendation?: string };
  fetched_at?: string;
};

export type MonitorDashboard = {
  date: string;
  lookback?: number;
  days?: string[];
  variant: MonitorVariant;
  variants: MonitorVariant[];
  layer_catalog: { id: string; label: string }[];
  engine: { globe: string; flat: string };
  stats: { world_items: number; ai_items: number; points: number };
  points: MonitorPoint[];
  headlines: MonitorHeadline[];
  correlation: { hub_id: string; label: string; streams: string[]; titles: string[] }[];
  finance_radar: {
    exchanges: { count: number; titles: string[] };
    commodities: { count: number; titles: string[] };
    crypto: { count: number; titles: string[] };
    composite: { count: number; titles: string[] };
    signals?: FinanceRadarSignals;
  };
  panels: { id: string; label: string }[];
};

export const LAYER_COLORS: Record<string, [number, number, number]> = {
  military: [220, 38, 38],
  economic: [217, 119, 6],
  disaster: [234, 88, 12],
  escalation: [192, 38, 211],
  happy: [22, 163, 74],
  energy: [202, 138, 4],
  finance_exchanges: [14, 165, 233],
  finance_commodities: [161, 98, 7],
  finance_crypto: [124, 58, 237],
  news_politics: [71, 85, 105],
  news_economics: [5, 150, 105],
  news_technology: [8, 145, 178],
  news_science: [13, 148, 136],
};

export function rgbOf(layer: string): [number, number, number] {
  return LAYER_COLORS[layer] || [148, 163, 184];
}

/** Shared by globe.gl and the 2D BitmapLayer. */
export const EARTH_IMAGE_URL = "https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg";

/**
 * Web Mercator is only defined to ±85.051129°. BitmapLayer bounds of ±90
 * produce infinite Y and a blank/white deck.gl canvas.
 */
export const EARTH_BITMAP_BOUNDS: [number, number, number, number] = [-180, -85.051129, 180, 85.051129];

/** Plate Carrée: x left→right −180…180, y top→bottom +90…−90. */
export function equirectangularProject(
  lat: number,
  lon: number,
  width: number,
  height: number,
): { x: number; y: number } {
  return {
    x: ((lon + 180) / 360) * width,
    y: ((90 - lat) / 180) * height,
  };
}

export function pointsForLayers(points: MonitorPoint[], enabled: Record<string, boolean>): MonitorPoint[] {
  return points.filter((p) => enabled[p.layer] !== false);
}

export function clusterByHub(points: MonitorPoint[]): HubCluster[] {
  const map = new Map<string, HubCluster>();
  for (const p of points) {
    const id = p.hub_id || `${p.lat},${p.lon}`;
    let rec = map.get(id);
    if (!rec) {
      rec = {
        hub_id: id,
        lat: p.lat,
        lon: p.lon,
        label: p.hub_label || p.hub_id || id,
        count: 0,
        titles: [],
        layers: [],
      };
      map.set(id, rec);
    }
    rec.count += 1;
    if (p.title && rec.titles.length < 8) rec.titles.push(p.title);
    if (!rec.layers.includes(p.layer)) rec.layers.push(p.layer);
  }
  return [...map.values()].sort((a, b) => b.count - a.count);
}

export function headlineHubIds(
  h: { hub_ids?: string[]; hubs?: string[] },
  points: MonitorPoint[],
): string[] {
  if (h.hub_ids?.length) return h.hub_ids;
  const labels = new Set((h.hubs || []).map((x) => x.toLowerCase()));
  if (!labels.size) return [];
  const ids = new Set<string>();
  for (const p of points) {
    const lab = (p.hub_label || p.hub_id || "").toLowerCase();
    if (p.hub_id && labels.has(lab)) ids.add(p.hub_id);
  }
  return [...ids];
}

export const LOOKBACK_DAYS = [1, 2, 5, 7] as const;

export function classifyInsight(text: string): "pending" | "ok" | "error" {
  const t = (text || "").trim();
  if (!t) return "error";
  if (t === "Ollama…" || t === "Ollama...") return "pending";
  if (/^HTTP \d+|Method Not Allowed|Failed to fetch|Not found|hub_id required/i.test(t)) return "error";
  return "ok";
}

export function headlinesForLayers(
  headlines: MonitorHeadline[],
  enabled: Record<string, boolean>,
): MonitorHeadline[] {
  const keys = Object.keys(enabled);
  if (!keys.length) return headlines;
  if (keys.every((k) => enabled[k] === false)) return [];
  return headlines.filter((h) => {
    const layers = h.layers?.length ? h.layers : h.streams || [];
    if (!layers.length) return keys.some((k) => k.startsWith("news_") && enabled[k] !== false);
    return layers.some((ly) => enabled[ly] !== false);
  });
}

export function headlinesForHub(
  headlines: MonitorHeadline[],
  hubId: string | null | undefined,
  points: MonitorPoint[] = [],
): MonitorHeadline[] {
  if (!hubId) return headlines;
  const labels = new Set<string>([hubId.toLowerCase()]);
  for (const p of points) {
    if (p.hub_id === hubId && p.hub_label) labels.add(p.hub_label.toLowerCase());
  }
  return headlines.filter((h) => {
    if ((h.hub_ids || []).includes(hubId)) return true;
    if ((h.country_ids || []).includes(hubId)) return true;
    return (h.hubs || []).some((x) => labels.has(x.toLowerCase()));
  });
}

export function formatHeadlineSources(h: {
  source?: string;
  sources?: string[];
}): string {
  if (h.sources?.length) return h.sources.join(" · ");
  return h.source || "";
}

export function formatSignedPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

export function hubLabelOf(dash: MonitorDashboard | null, hubId: string | null | undefined): string {
  if (!dash || !hubId) return "";
  const pt = dash.points.find((p) => p.hub_id === hubId);
  if (pt?.hub_label) return pt.hub_label;
  const corr = dash.correlation.find((c) => c.hub_id === hubId);
  return corr?.label || hubId;
}
