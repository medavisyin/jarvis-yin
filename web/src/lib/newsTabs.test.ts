import { describe, expect, it } from "vitest";
import { NEWS_TABS } from "./newsTabs";

describe("NEWS_TABS", () => {
  it("is a flat list with Daily fetch, AI news, and former toolbar tools — no Toolbar wrapper", () => {
    const labels = NEWS_TABS.map((t) => t.label);
    expect(labels).toEqual([
      "Daily fetch",
      "World monitor",
      "AI news",
      "Audio from Knowledge",
      "Explain This",
      "Trend Analysis",
      "Finance News Summary",
      "Learning modes",
      "My Notes",
    ]);
    expect(labels).not.toContain("Toolbar");
    expect(NEWS_TABS.map((t) => t.path)).toEqual([
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
  });
});
