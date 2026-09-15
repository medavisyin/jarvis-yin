import { describe, expect, it } from "vitest";
import { isTerminalJobStatus } from "./jobs";
import { formatScannerStatus, qvEmptyCopy, qvHorizonLabel, scannerResultMode, scanSectionRan } from "./scannerResults";

describe("scannerResultMode", () => {
  it("maps each scanner to its own layout, never generic four-column", () => {
    expect(scannerResultMode("qv")).toBe("qv");
    expect(scannerResultMode("scan")).toBe("scan");
    expect(scannerResultMode("long-term")).toBe("long-term");
    expect(scannerResultMode("midday")).toBe("midday");
    expect(scannerResultMode("right")).toBe("right");
    expect(scannerResultMode("unified")).toBe("unified");
    expect(scannerResultMode("qv")).not.toBe("generic");
  });
});

describe("formatScannerStatus", () => {
  it("does not render done done \u00b7 finished when status and step are both done", () => {
    const label = formatScannerStatus({ status: "done", step: "done" });
    expect(label).toBe("\u626b\u63cf\u5b8c\u6210");
    expect(label.toLowerCase()).not.toContain("done done");
    expect(label).not.toContain("finished");
  });

  it("hides idle and none placeholders", () => {
    expect(formatScannerStatus({ status: "none" })).toBe("");
    expect(formatScannerStatus({ status: "idle" })).toBe("");
    expect(formatScannerStatus({})).toBe("");
  });

  it("maps QV running steps and long-term phase statuses to Chinese labels", () => {
    expect(formatScannerStatus({ status: "running", step: "layer2", progress: 40 }, "qv")).toContain("基本面排雷");
    expect(formatScannerStatus({ status: "analyzing_metals" })).toContain("贵金属");
  });
});

describe("qvEmptyCopy", () => {
  it("uses 宁缺毋滥 copy when funnel ran and picked nothing", () => {
    const copy = qvEmptyCopy({ picks: [], stats: { layer1_out: 12 } });
    expect(copy.title).toContain("暂无推荐");
    expect(copy.title).toContain("宁缺毋滥");
    expect(copy.detail).toContain("漏斗");
  });

  it("uses snapshot-failure copy when the market snapshot was empty", () => {
    const copy = qvEmptyCopy({ picks: [], stats: { snapshot_failed: true } });
    expect(copy.title).toContain("快照");
    expect(copy.detail).toContain("漏斗未执行");
  });
});

describe("qvHorizonLabel", () => {
  it("labels long and medium holding windows", () => {
    expect(qvHorizonLabel("long")).toContain("6 个月");
    expect(qvHorizonLabel("medium")).toContain("1 个月");
  });
});

describe("scanSectionRan", () => {
  it("treats missing date and missing pick lists as not yet scanned", () => {
    expect(scanSectionRan(undefined)).toBe(false);
    expect(scanSectionRan({})).toBe(false);
  });

  it("treats a dated or listed section as already run, even with zero picks", () => {
    expect(scanSectionRan({ date: "2026-09-15", picks: [] })).toBe(true);
    expect(scanSectionRan({ top_picks: [] })).toBe(true);
  });
});

describe("isTerminalJobStatus", () => {
  it("treats right-side/midday completed and failed as terminal", () => {
    expect(isTerminalJobStatus("completed")).toBe(true);
    expect(isTerminalJobStatus("failed")).toBe(true);
  });
});
