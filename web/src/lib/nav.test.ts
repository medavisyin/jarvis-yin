import { describe, expect, it } from "vitest";
import { accordionValuesForPath, defaultChildPath, isNavGroup, NAV } from "./nav";
import { NEWS_TABS } from "./newsTabs";

describe("NAV", () => {
  it("places Medavis after Reading and before Settings", () => {
    const labels = NAV.map((n) => n.label);
    expect(labels.indexOf("Reading")).toBeGreaterThan(-1);
    expect(labels.indexOf("Medavis")).toBe(labels.indexOf("Reading") + 1);
    expect(labels.indexOf("Settings")).toBe(labels.indexOf("Medavis") + 1);
  });

  it("routes Medavis to /medavis", () => {
    expect(NAV.find((n) => n.label === "Medavis")?.to).toBe("/medavis");
  });

  it("nests News / Stock / Medavis children and keeps Chat / Reading / Settings as leaves", () => {
    const news = NAV.find((n) => n.label === "News");
    const stock = NAV.find((n) => n.label === "Stock");
    const medavis = NAV.find((n) => n.label === "Medavis");
    expect(news && isNavGroup(news)).toBe(true);
    expect(stock && isNavGroup(stock)).toBe(true);
    expect(medavis && isNavGroup(medavis)).toBe(true);
    expect(NAV.filter((n) => !isNavGroup(n)).map((n) => n.label)).toEqual(["Chat", "Reading", "Settings"]);
    expect(isNavGroup(news!) ? news.children.map((c) => c.label) : []).toEqual(NEWS_TABS.map((t) => t.label));
    expect(isNavGroup(news!) ? news.children.map((c) => c.to) : []).toEqual([
      "/news/daily",
      "/news/monitor",
      "/news/ai",
      "/news/audio",
      "/news/explain",
      "/news/trend",
      "/news/finance",
      "/news/learning",
      "/news/notes",
    ]);
    expect(isNavGroup(stock!) ? stock.children.map((c) => c.to) : []).toEqual([
      "/stock/watch",
      "/stock/scan",
      "/stock/weekly",
      "/stock/analyze",
      "/stock/national",
      "/stock/train",
    ]);
    expect(isNavGroup(medavis!) ? medavis.children.map((c) => c.to) : []).toEqual([
      "/medavis/wiki",
      "/medavis/jira",
      "/medavis/commit",
      "/medavis/platform",
      "/medavis/activity",
      "/medavis/projects",
    ]);
    const allChildLabels = NAV.flatMap((n) => (isNavGroup(n) ? n.children.map((c) => c.label) : []));
    expect(allChildLabels).not.toContain("Toolbar");
  });

  it("defaults each group to its first child and auto-opens the matching accordion", () => {
    const news = NAV.find((n) => n.label === "News");
    expect(news && isNavGroup(news) ? defaultChildPath(news) : "").toBe("/news/daily");
    expect(accordionValuesForPath("/news/ai")).toEqual(["news"]);
    expect(accordionValuesForPath("/news")).toEqual(["news"]);
    expect(accordionValuesForPath("/stock/watch")).toEqual(["stock"]);
    expect(accordionValuesForPath("/medavis/wiki")).toEqual(["medavis"]);
    expect(accordionValuesForPath("/reading")).toEqual([]);
    expect(accordionValuesForPath("/")).toEqual([]);
  });
});
