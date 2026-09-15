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
