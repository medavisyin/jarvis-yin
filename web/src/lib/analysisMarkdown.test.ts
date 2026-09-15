import { describe, expect, it } from "vitest";
import { ANALYSIS_LEGEND, renderAnalysisHtml } from "./analysisMarkdown";

describe("ANALYSIS_LEGEND", () => {
  it("explains heading, quote, and emphasis only", () => {
    expect(ANALYSIS_LEGEND.map((item) => item.id)).toEqual(["heading", "quote", "emphasis"]);
    expect(ANALYSIS_LEGEND).toHaveLength(3);
  });
});

describe("renderAnalysisHtml", () => {
  it("turns headings, quotes, and bold into the legend styles", () => {
    const html = renderAnalysisHtml("## Title\n\n> quoted\n\n**warm**");
    expect(html).toContain("<h3");
    expect(html).toContain("<blockquote");
    expect(html).toContain("<strong>");
    expect(html).not.toContain("<img>");
  });
});
