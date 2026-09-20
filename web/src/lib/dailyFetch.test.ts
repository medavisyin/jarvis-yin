import { describe, expect, it } from "vitest";
import {
  audioTranslateTarget,
  buildEnabledMap,
  enabledSourceIdsForCategory,
  mdFilesOnly,
  pickFinanceCategory,
  refetchAudioSteps,
  refetchWorldNewsSteps,
  renderReportMarkdown,
  parseLearningGuideDeepDives,
} from "./dailyFetch";

describe("pickFinanceCategory", () => {
  it("returns items for the clicked finance category", () => {
    const payload = {
      categories: [
        {
          category: "gold",
          items: [{ title: "Gold jumps", url: "https://ex.test/g", source: "Kitco" }],
        },
        { category: "oil", items: [{ title: "Oil", url: "", source: "EIA" }] },
      ],
    };
    expect(pickFinanceCategory(payload, "gold")).toEqual([
      { title: "Gold jumps", url: "https://ex.test/g", source: "Kitco" },
    ]);
    expect(pickFinanceCategory(payload, "crypto")).toEqual([]);
  });
});

describe("mdFilesOnly", () => {
  it("keeps report markdown, not json dumps", () => {
    expect(
      mdFilesOnly([
        { name: "wiki-fetch-2026-09-14.md", size_kb: 2 },
        { name: "briefing-data.json", size_kb: 10 },
      ]),
    ).toEqual([{ name: "wiki-fetch-2026-09-14.md", size_kb: 2 }]);
  });
});

describe("renderReportMarkdown", () => {
  it("turns titles into links and keeps headings", () => {
    const html = renderReportMarkdown(
      "## Gold\n\n**Kitco** [Gold jumps](https://ex.test/g)\n",
    );
    expect(html).toContain("<h3");
    expect(html).toContain("<strong");
    expect(html).toContain('href="https://ex.test/g"');
    expect(html).toContain("Gold jumps");
    expect(html).not.toContain("<script");
  });

  it("escapes raw HTML before rendering", () => {
    const html = renderReportMarkdown('<img src=x onerror=alert(1)>');
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });
});

describe("audioTranslateTarget", () => {
  it("flips zh to en and en to zh", () => {
    expect(audioTranslateTarget("zh")).toBe("en");
    expect(audioTranslateTarget("en")).toBe("zh");
    expect(audioTranslateTarget(undefined)).toBe("en");
  });
});

describe("refetchAudioSteps", () => {
  it("prefixes AI refetch before ai_audio", () => {
    expect(refetchAudioSteps("ai_audio")).toEqual(["refetch_ai", "ai_audio"]);
  });

  it("prefixes finance pipeline before category audio", () => {
    expect(refetchAudioSteps("fn_audio:gold")).toEqual([
      "refetch_finance",
      "finance_news_merge",
      "finance_news_translate",
      "fn_audio:gold",
    ]);
  });

  it("prefixes world fetch before merge and translate", () => {
    expect(refetchWorldNewsSteps()).toEqual([
      "refetch_world",
      "world_news_merge",
      "world_news_translate",
    ]);
  });
});

describe("enabledSourceIdsForCategory", () => {
  const sources = [
    { id: "kitco", category: "gold" },
    { id: "eia", category: "oil" },
    { id: "kitco2", category: "gold" },
  ];
  it("returns only enabled publishers in that finance category", () => {
    expect(
      enabledSourceIdsForCategory(sources, { kitco: true, kitco2: false, eia: true }, "gold"),
    ).toEqual(["kitco"]);
  });
});

describe("buildEnabledMap", () => {
  it("includes every source id as true or false for POST", () => {
    expect(
      buildEnabledMap(
        [{ id: "a" }, { id: "b" }],
        { a: true },
      ),
    ).toEqual({ a: true, b: false });
  });
});

describe("parseLearningGuideDeepDives", () => {
  it("extracts title, source url, and raw file from numbered items", () => {
    const md = [
      "## Today's Reading List",
      "",
      "1. **LoRA fine-tuning**",
      "- File: `raw/lora.md`",
      "- Source: https://ex.test/lora",
      "",
      "2. **RLHF**",
      "- File: `raw/rlhf.md`",
      "- Source: https://ex.test/rlhf",
    ].join("\n");
    expect(parseLearningGuideDeepDives(md)).toEqual([
      { title: "LoRA fine-tuning", rawFile: "raw/lora.md", sourceUrl: "https://ex.test/lora" },
      { title: "RLHF", rawFile: "raw/rlhf.md", sourceUrl: "https://ex.test/rlhf" },
    ]);
  });
});
