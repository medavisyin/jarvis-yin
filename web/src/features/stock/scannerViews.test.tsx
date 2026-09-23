import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ScannerResultBody } from "@/features/stock/scannerViews";

describe("ScannerResultBody", () => {
  it("does not render unified/generic column titles for a quality-value empty payload", () => {
    const html = renderToStaticMarkup(
      <ScannerResultBody kindId="qv" result={{ picks: [], stats: { layer1_out: 3 } }} />,
    );
    expect(html).toContain("宁缺毋滥");
    expect(html).not.toContain("左侧");
    expect(html).not.toContain("右侧");
    expect(html).not.toContain("近5年高");
    expect(html).not.toContain("Picks");
    expect(html).not.toContain("Left / short-term");
    expect(html).not.toContain("ATH rebreak");
  });

  it("shows API error copy instead of 宁缺毋滥 when result.error is set", () => {
    const html = renderToStaticMarkup(
      <ScannerResultBody kindId="qv" result={{ picks: [], error: "暂无优质低估结果" }} />,
    );
    expect(html).toContain("暂无优质低估结果");
    expect(html).not.toContain("宁缺毋滥");
  });

  it("uses 尚未扫描 copy for unified columns that have no date or pick list", () => {
    const html = renderToStaticMarkup(<ScannerResultBody kindId="unified" result={{}} />);
    expect(html).toContain("尚未扫描");
    expect(html).not.toContain("近5年高");
  });

  it("renders only left and right unified columns even if ath picks exist", () => {
    const html = renderToStaticMarkup(
      <ScannerResultBody
        kindId="unified"
        result={{
          left: { date: "2026-09-17", top_picks: [] },
          right: { date: "2026-09-17", picks: [] },
          ath: { date: "2026-09-17", picks: [{ symbol: "600519", name: "茅台" }] },
        }}
      />,
    );
    expect(html).toContain("左侧");
    expect(html).toContain("右侧");
    expect(html).not.toContain("近5年高");
    expect(html).not.toContain("600519");
  });

  it("shows long-term metals outlook and thermometer when prices and themes are missing", () => {
    const html = renderToStaticMarkup(
      <ScannerResultBody
        kindId="long-term"
        result={{
          picks: [],
          themes: [],
          precious_metals: {
            gold: { data_available: false },
            silver: { data_available: false },
            llm_outlook: {
              gold: { trend: "中期震荡偏多", advice: "不追高" },
              silver: { trend: "中期震荡", advice: "跟随黄金" },
              summary: "黄金为主配置",
            },
          },
          factors: {
            macro: {
              series: [{ label: "失业率", latest: 4.2, prior: 4.1, data_available: true }],
              official_headlines: [{ headline: "央行发声" }],
            },
            llm_outlook: { summary: "类滞胀格局", macro: { trend: "震荡", advice: "控制久期" } },
          },
        }}
      />,
    );
    expect(html).toContain("中期震荡偏多");
    expect(html).toContain("不追高");
    expect(html).toContain("黄金为主配置");
    expect(html).toContain("宏观与市场温度计");
    expect(html).toContain("失业率");
    expect(html).toContain("未产出投资主题");
    expect(html).toContain("暂无个股推荐");
  });

  it("shows long-term API error instead of empty-picks copy", () => {
    const html = renderToStaticMarkup(
      <ScannerResultBody kindId="long-term" result={{ error: "暂无长期推荐结果", picks: [] }} />,
    );
    expect(html).toContain("暂无长期推荐结果");
    expect(html).not.toContain("暂无个股推荐");
  });

  it("includes the midday overnight exit plan on a pick card", () => {
    const html = renderToStaticMarkup(
      <ScannerResultBody
        kindId="midday"
        result={{
          picks: [{ symbol: "002396", name: "星网锐捷", price: 41.5, reasoning: "x", risk: "y" }],
        }}
      />,
    );
    expect(html).toContain("冲高失败");
    expect(html).toContain("10:00");
  });
});
