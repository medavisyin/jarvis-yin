import { useEffect, useMemo, useRef, useState } from "react";
import {
  clusterByHub,
  EARTH_IMAGE_URL,
  equirectangularProject,
  pointsForLayers,
  rgbOf,
  type HubCluster,
  type MonitorPoint,
} from "@/lib/worldMonitor";

type GlobeApi = {
  width: (w: number) => GlobeApi;
  height: (h: number) => GlobeApi;
  pointsData: (d: HubCluster[]) => GlobeApi;
  labelsData: (d: HubCluster[]) => GlobeApi;
  pointOfView: (pov: { lat: number; lng: number; altitude?: number }, ms?: number) => GlobeApi;
  _destructor: () => void;
};

type Props = {
  engine: "globe" | "flat";
  points: MonitorPoint[];
  enabled: Record<string, boolean>;
  selectedHubId?: string | null;
  onSelectHub?: (hubId: string) => void;
};

function paint(cluster: HubCluster): [number, number, number] {
  return rgbOf(cluster.layers[0] || "news_politics");
}

function cssRgb(cluster: HubCluster): string {
  const [r, g, b] = paint(cluster);
  return `rgb(${r},${g},${b})`;
}

export function DualMap({ engine, points, enabled, selectedHubId, onSelectHub }: Props) {
  const globeHost = useRef<HTMLDivElement>(null);
  const globeRef = useRef<GlobeApi | null>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [mapSize, setMapSize] = useState({ w: 732, h: 480 });
  const selectedRef = useRef(selectedHubId);
  const onSelectRef = useRef(onSelectHub);
  const clustersRef = useRef<HubCluster[]>([]);
  selectedRef.current = selectedHubId;
  onSelectRef.current = onSelectHub;

  const visible = useMemo(() => pointsForLayers(points, enabled), [points, enabled]);
  const clusters = useMemo(() => clusterByHub(visible), [visible]);
  clustersRef.current = clusters;

  useEffect(() => {
    const el = globeHost.current;
    if (!el) return;
    let cancelled = false;
    let globe: GlobeApi | null = null;
    const run = async () => {
      const Globe = (await import("globe.gl")).default;
      if (cancelled || !globeHost.current) return;
      const host = globeHost.current;
      globe = new Globe(host)
        .width(host.clientWidth || 640)
        .height(host.clientHeight || 480)
        .backgroundColor("rgba(15,23,42,1)")
        .globeImageUrl(EARTH_IMAGE_URL)
        .pointsData(clustersRef.current)
        .pointLat("lat")
        .pointLng("lon")
        .pointAltitude((d) => ((d as HubCluster).hub_id === selectedRef.current ? 0.12 : 0.05))
        .pointRadius((d) => 0.45 + Math.min((d as HubCluster).count, 10) * 0.08)
        .pointColor((d) => cssRgb(d as HubCluster))
        .pointLabel((d) => {
          const c = d as HubCluster;
          return `<b>${c.label}</b> · ${c.count} items<br/>${(c.titles || []).slice(0, 3).join("<br/>")}`;
        })
        .labelsData(clustersRef.current)
        .labelLat("lat")
        .labelLng("lon")
        .labelText((d) => {
          const c = d as HubCluster;
          return `${c.label} (${c.count})`;
        })
        .labelSize(1.4)
        .labelDotRadius(0.35)
        .labelColor(() => "rgba(255,255,255,0.92)")
        .labelResolution(2)
        .onPointClick((pt) => {
          const c = pt as HubCluster;
          if (c?.hub_id) onSelectRef.current?.(c.hub_id);
        })
        .onLabelClick((pt) => {
          const c = pt as HubCluster;
          if (c?.hub_id) onSelectRef.current?.(c.hub_id);
        }) as unknown as GlobeApi;
      globeRef.current = globe;
    };
    void run();
    return () => {
      cancelled = true;
      globeRef.current = null;
      globe?._destructor();
    };
  }, []);

  useEffect(() => {
    const globe = globeRef.current;
    if (!globe) return;
    globe.pointsData(clusters).labelsData(clusters);
  }, [clusters]);

  useEffect(() => {
    const globe = globeRef.current;
    const hit = clusters.find((c) => c.hub_id === selectedHubId);
    if (engine !== "globe" || !globe || !hit) return;
    globe.pointOfView({ lat: hit.lat, lng: hit.lon, altitude: 1.55 }, 700);
  }, [selectedHubId, clusters, engine]);

  useEffect(() => {
    const gEl = globeHost.current;
    if (engine !== "globe" || !globeRef.current || !gEl) return;
    globeRef.current.width(gEl.clientWidth || 640).height(gEl.clientHeight || 480);
  }, [engine]);

  useEffect(() => {
    const el = frameRef.current;
    if (!el) return;
    const apply = () => setMapSize({ w: el.clientWidth || 732, h: el.clientHeight || 480 });
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const mapW = mapSize.w;
  const mapH = mapSize.h;
  const selected = clusters.find((c) => c.hub_id === selectedHubId);
  const focus = selected ? equirectangularProject(selected.lat, selected.lon, mapW, mapH) : null;
  const scale = focus ? 2.35 : 1;
  const tx = focus ? mapW / 2 - focus.x * scale : 0;
  const ty = focus ? mapH / 2 - focus.y * scale : 0;

  return (
    <div className="relative">
      <div ref={frameRef} className="relative h-[480px] w-full overflow-hidden rounded-lg bg-slate-950">
        <div
          ref={globeHost}
          className={`absolute inset-0 ${engine === "globe" ? "z-10" : "pointer-events-none invisible z-0"}`}
        />
        {engine === "flat" ? (
          <div className="absolute inset-0 z-10 bg-[#0b1220]">
            <div
              className="absolute inset-0 origin-top-left transition-transform duration-500"
              style={{ transform: `translate(${tx}px, ${ty}px) scale(${scale})` }}
            >
              <img
                src={EARTH_IMAGE_URL}
                alt="World map"
                className="pointer-events-none absolute inset-0 h-full w-full object-fill"
                draggable={false}
              />
              {clusters.map((c) => {
                const { x, y } = equirectangularProject(c.lat, c.lon, mapW, mapH);
                const active = c.hub_id === selectedHubId;
                const size = 10 + Math.min(c.count, 10);
                return (
                  <button
                    key={c.hub_id}
                    type="button"
                    title={`${c.label} (${c.count})\n${(c.titles || []).slice(0, 3).join("\n")}`}
                    className="absolute -translate-x-1/2 -translate-y-1/2"
                    style={{ left: x, top: y, zIndex: active ? 1000 : 10 + c.count }}
                    onClick={() => onSelectHub?.(c.hub_id)}
                  >
                    <span
                      className="block rounded-full border border-white/80"
                      style={{
                        width: size,
                        height: size,
                        background: cssRgb(c),
                        boxShadow: active ? "0 0 0 4px rgba(255,255,255,0.55)" : "0 0 0 1px rgba(0,0,0,0.4)",
                      }}
                    />
                    <span className="absolute top-1/2 left-full ml-1 -translate-y-1/2 whitespace-nowrap text-[10px] font-medium text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)]">
                      {c.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
      <div className="pointer-events-none absolute top-3 left-3 z-20 rounded bg-black/60 px-2 py-1 text-xs text-white">
        {engine === "globe" ? "3D globe.gl" : "2D 平面地图"} · {clusters.length} hubs · {visible.length} items
        {clusters.length === 0 ? " · 当前图层没有可定位新闻" : " · 点击光点查看新闻"}
      </div>
    </div>
  );
}
