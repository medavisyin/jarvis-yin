import { describe, expect, it } from "vitest";
import {
  clusterByHub,
  EARTH_BITMAP_BOUNDS,
  classifyInsight,
  equirectangularProject,
  formatSignedPct,
  formatHeadlineSources,
  headlineHubIds,
  headlinesForHub,
  headlinesForLayers,
  pointsForLayers,
  type MonitorPoint,
} from "./worldMonitor";

describe("pointsForLayers", () => {
  const pts: MonitorPoint[] = [
    { layer: "military", lat: 1, lon: 2, title: "a" },
    { layer: "happy", lat: 3, lon: 4, title: "b" },
  ];
  it("drops disabled layers", () => {
    expect(pointsForLayers(pts, { military: true, happy: false }).map((p) => p.layer)).toEqual(["military"]);
  });
});

describe("clusterByHub", () => {
  it("collapses stacked news at the same hub into one marker", () => {
    const pts: MonitorPoint[] = [
      { layer: "military", lat: 50.45, lon: 30.52, hub_id: "kyiv", hub_label: "Kyiv", title: "Strike 1" },
      { layer: "economic", lat: 50.45, lon: 30.52, hub_id: "kyiv", hub_label: "Kyiv", title: "Sanctions" },
      { layer: "news_politics", lat: 39.9, lon: 116.4, hub_id: "beijing", hub_label: "Beijing", title: "Talks" },
    ];
    const hubs = clusterByHub(pts);
    expect(hubs).toHaveLength(2);
    const kyiv = hubs.find((h) => h.hub_id === "kyiv")!;
    expect(kyiv.count).toBe(2);
    expect(kyiv.titles).toEqual(["Strike 1", "Sanctions"]);
    expect(kyiv.layers).toEqual(["military", "economic"]);
  });
});

describe("EARTH_BITMAP_BOUNDS", () => {
  it("stays inside Web Mercator so the 2D BitmapLayer is not NaN/white", () => {
    const [west, south, east, north] = EARTH_BITMAP_BOUNDS;
    expect(west).toBe(-180);
    expect(east).toBe(180);
    // Web Mercator is only defined to ±85.051129°. ±90 maps to infinity and
    // blank/white-fills the deck.gl canvas.
    expect(Math.abs(south)).toBeLessThan(85.06);
    expect(Math.abs(north)).toBeLessThan(85.06);
    expect(Math.abs(south)).toBeGreaterThanOrEqual(85);
    expect(Math.abs(north)).toBeGreaterThanOrEqual(85);
  });
});

describe("equirectangularProject", () => {
  it("puts the equator and prime meridian at the map center", () => {
    expect(equirectangularProject(0, 0, 360, 180)).toEqual({ x: 180, y: 90 });
  });

  it("places Beijing in the eastern hemisphere, north of the equator", () => {
    const p = equirectangularProject(39.9, 116.4, 1000, 500);
    expect(p.x).toBeGreaterThan(700);
    expect(p.x).toBeLessThan(900);
    expect(p.y).toBeGreaterThan(100);
    expect(p.y).toBeLessThan(250);
  });
});

describe("headlineHubIds", () => {
  it("falls back from hub labels to point ids", () => {
    const ids = headlineHubIds(
      { hubs: ["Kyiv"] },
      [{ layer: "military", lat: 1, lon: 2, hub_id: "kyiv", hub_label: "Kyiv" }],
    );
    expect(ids).toEqual(["kyiv"]);
  });
});

describe("headlinesForHub", () => {
  const rows = [
    { title: "a", hub_ids: ["kyiv"], country_ids: ["UA"] },
    { title: "b", hub_ids: ["beijing"], country_ids: ["CN"] },
  ];
  it("returns all headlines when no hub is selected", () => {
    expect(headlinesForHub(rows, null)).toHaveLength(2);
  });
  it("matches city hub_id or country_ids", () => {
    expect(headlinesForHub(rows, "kyiv").map((h) => h.title)).toEqual(["a"]);
    expect(headlinesForHub(rows, "CN").map((h) => h.title)).toEqual(["b"]);
  });
  it("matches hub label when hub_ids are missing", () => {
    const loose = [{ title: "c", hubs: ["Beijing"] }];
    const pts: MonitorPoint[] = [{ layer: "news_politics", lat: 1, lon: 2, hub_id: "beijing", hub_label: "Beijing" }];
    expect(headlinesForHub(loose, "beijing", pts).map((h) => h.title)).toEqual(["c"]);
  });
});

describe("headlinesForLayers", () => {
  const rows = [
    { title: "strike", layers: ["military", "news_politics"], streams: ["military"] },
    { title: "tariff", layers: ["economic", "news_economics"], streams: ["economic"] },
    { title: "garden", layers: ["news_politics"] },
  ];
  it("keeps headlines whose layers are enabled", () => {
    expect(headlinesForLayers(rows, { military: false, news_politics: true, economic: true, news_economics: true }).map((h) => h.title)).toEqual([
      "strike",
      "tariff",
      "garden",
    ]);
    expect(headlinesForLayers(rows, { military: true, news_politics: false, economic: false, news_economics: false }).map((h) => h.title)).toEqual([
      "strike",
    ]);
  });
  it("returns nothing when every layer is off", () => {
    expect(headlinesForLayers(rows, { military: false, news_politics: false, economic: false, news_economics: false })).toEqual([]);
  });
});

describe("classifyInsight", () => {
  it("hides transport errors so they are not shown as headlines", () => {
    expect(classifyInsight("HTTP 405")).toBe("error");
    expect(classifyInsight("Method Not Allowed")).toBe("error");
    expect(classifyInsight("Ollama…")).toBe("pending");
    expect(classifyInsight("北京近期以政治报道为主。")).toBe("ok");
  });
});

describe("formatHeadlineSources", () => {
  it("joins corroborating wires", () => {
    expect(formatHeadlineSources({ source: "Reuters", sources: ["Reuters", "BBC World News"] })).toBe(
      "Reuters · BBC World News",
    );
    expect(formatHeadlineSources({ source: "DW" })).toBe("DW");
  });
});

describe("formatSignedPct", () => {
  it("shows a plus for gains and a dash for missing", () => {
    expect(formatSignedPct(0.4)).toBe("+0.4%");
    expect(formatSignedPct(-0.8)).toBe("-0.8%");
    expect(formatSignedPct(0)).toBe("0.0%");
    expect(formatSignedPct(null)).toBe("—");
  });
});
