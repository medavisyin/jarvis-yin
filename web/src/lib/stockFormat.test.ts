import { describe, expect, it } from "vitest";
import { changeDirection, extractScanSections, formatChangePct, formatFetchedAt, formatIntradayShareLine, formatPrice, marketFlowNetCaption, nationalTeamView, officialDayHeader, officialGridCaption, pickNote, pickScore, portfolioMarkdown, shareAnnouncementNote, stockReportMarkdown } from "./stockFormat";

describe("stockFormat", () => {
  it("formats A-share price and change", () => {
    expect(formatPrice(6.16)).toBe("¥6.16");
    expect(formatPrice(null)).toBe("—");
    expect(formatChangePct(0.26)).toBe("+0.26%");
    expect(formatChangePct(-1.76)).toBe("-1.76%");
    expect(formatChangePct(undefined)).toBe("—");
  });

  it("maps up/down for A-share red/green", () => {
    expect(changeDirection(0.26)).toBe("up");
    expect(changeDirection(-1.76)).toBe("down");
    expect(changeDirection(0)).toBe("flat");
  });
});

describe("extractScanSections", () => {
  it("pulls left/right/ath pick lists from unified result", () => {
    const sections = extractScanSections({
      left: { top_picks: [{ symbol: "600519", name: "茅台" }] },
      right: { picks: [{ symbol: "000001" }] },
      ath: { picks: [] },
    });
    expect(sections.left).toEqual([{ symbol: "600519", name: "茅台" }]);
    expect(sections.right[0].symbol).toBe("000001");
    expect(sections.ath).toEqual([]);
  });
});

describe("pickScore / pickNote", () => {
  it("prefers score/reason and falls back to final_score/reasoning", () => {
    expect(pickScore({ score: 88, final_score: 10 })).toBe(88);
    expect(pickScore({ final_score: 71.2 })).toBe(71.2);
    expect(pickNote({ reason: "a", reasoning: "b" })).toBe("a");
    expect(pickNote({ reasoning: "逻辑" })).toBe("逻辑");
  });
});

describe("stockReportMarkdown", () => {
  it("joins report fields in old UI order", () => {
    expect(
      stockReportMarkdown({
        report: "Main",
        valuation_report: "Val",
        fund_flow_report: "FF",
      }),
    ).toContain("Main");
    expect(
      stockReportMarkdown({
        report: "Main",
        valuation_report: "Val",
        fund_flow_report: "FF",
      }),
    ).toMatch(/Main[\s\S]*Val[\s\S]*FF/);
  });
});

describe("portfolioMarkdown", () => {
  it("renders allocation table and cash advice", () => {
    const md = portfolioMarkdown({
      market_regime_zh: "震荡",
      regime_advice: "控制仓位",
      allocations: [{ symbol: "600519", name: "茅台", weight_pct: 10, amount: 10000, score: 88 }],
      cash_pct: 40,
      cash_amount: 40000,
    });
    expect(md).toContain("组合仓位建议");
    expect(md).toContain("600519");
    expect(md).toContain("40%");
  });
});

describe("nationalTeamView", () => {
  it("pulls snapshot totals and signal", () => {
    const v = nationalTeamView({
      snapshot: {
        total_broad_shares_yi: 12.5,
        total_sector_shares_yi: 3.2,
        signals: { broad_total_change: "温和增持" },
        etf_snapshot: [{ code: "510300" }],
        sse_stat_date: "2026-09-11",
        daily_change: { ref_date: "2026-09-14" },
      },
      trend: { total_change_pct: 1.2, trend: "up" },
    });
    expect(v.broadYi).toBe(12.5);
    expect(v.signal).toBe("温和增持");
    expect(v.etfs).toHaveLength(1);
    expect(v.sseStatDate).toBe("2026-09-11");
    expect(v.refDate).toBe("2026-09-14");
  });
});

describe("marketFlowNetCaption", () => {
  it("says 今日 only when latest_date is today", () => {
    const same = marketFlowNetCaption("2026-09-15", "2026-09-15");
    expect(same.netLabel).toBe("今日净流入");
    expect(same.stale).toBe(false);
    expect(same.staleHint).toBe("");
  });

  it("labels the real date when latest_date is not today", () => {
    const stale = marketFlowNetCaption("2026-09-08", "2026-09-15");
    expect(stale.netLabel).toBe("净流入（截至 2026-09-08）");
    expect(stale.avgPrefix).toBe("5日均（截至 2026-09-08）");
    expect(stale.stale).toBe(true);
    expect(stale.staleHint).toBe("数据截至 2026-09-08（非当日）");
  });

  it("does not say 今日 when latest_date is missing", () => {
    const unknown = marketFlowNetCaption("", "2026-09-15");
    expect(unknown.netLabel).toBe("净流入");
    expect(unknown.stale).toBe(true);
    expect(unknown.staleHint).toBe("日期未知");
  });
});

describe("officialDayHeader", () => {
  it("includes the comparison date", () => {
    expect(officialDayHeader("2026-09-14")).toBe("当天 vs 2026-09-14");
    expect(officialDayHeader(null)).toBe("当天");
  });
});

describe("shareAnnouncementNote", () => {
  it("shows SSE announcement date and SZSE caveat", () => {
    expect(shareAnnouncementNote("2026-09-11")).toBe("份额公告日: 2026-09-11（深市为最新日）");
  });
});

describe("formatFetchedAt", () => {
  it("shows local-looking date and time without timezone suffix", () => {
    expect(formatFetchedAt("2026-09-15T12:53:04.123456")).toBe("2026-09-15 12:53:04");
  });

  it("says 未知 when fetch time is missing", () => {
    expect(formatFetchedAt("")).toBe("未知");
    expect(formatFetchedAt(null)).toBe("未知");
  });
});

describe("officialGridCaption", () => {
  it("puts current fetch datetime first, then comparison and announcement dates", () => {
    expect(
      officialGridCaption("2026-09-15T12:53:04", "2026-09-14", "2026-09-11"),
    ).toBe("参考时间 2026-09-15 12:53:04 · 对比日 2026-09-14 · 份额公告日 2026-09-11（深市为最新日）");
  });
});

describe("formatIntradayShareLine", () => {
  it("renders open-to-now share change", () => {
    expect(
      formatIntradayShareLine({
        name: "300ETF",
        code: "510300",
        prev_yi: 233.99,
        curr_yi: 230.1,
        change_pct: -1.66,
        status: "ok",
      }),
    ).toBe("300ETF (510300): 234.0 → 230.1 亿份 (-1.66%)");
  });

  it("says 无数据 when spot is missing", () => {
    expect(formatIntradayShareLine({ name: "50ETF", code: "510050", status: "无数据" })).toBe(
      "50ETF (510050): 无数据",
    );
  });
});
