import { describe, expect, it } from "vitest";
import { parseFontSize, parseReadingPrefs, parseSplitPercent, passageMetrics, hideReadingSidebar, isEditableKeyTarget } from "./readingPrefs";

describe("parseFontSize", () => {
  it("accepts 18, 20, and 22", () => {
    expect(parseFontSize(18)).toBe(18);
    expect(parseFontSize(20)).toBe(20);
    expect(parseFontSize(22)).toBe(22);
  });

  it("falls back to 18 for unknown values", () => {
    expect(parseFontSize(19)).toBe(18);
    expect(parseFontSize("xl")).toBe(18);
    expect(parseFontSize(undefined)).toBe(18);
  });
});

describe("parseSplitPercent", () => {
  it("keeps passage share between 30 and 75", () => {
    expect(parseSplitPercent(62)).toBe(62);
    expect(parseSplitPercent(30)).toBe(30);
    expect(parseSplitPercent(75)).toBe(75);
    expect(parseSplitPercent(10)).toBe(30);
    expect(parseSplitPercent(90)).toBe(75);
    expect(parseSplitPercent("55.4")).toBe(55);
    expect(parseSplitPercent(undefined)).toBe(62);
  });
});

describe("parseReadingPrefs", () => {
  it("reads fontSize, focus, and splitPercent from JSON", () => {
    expect(parseReadingPrefs('{"fontSize":22,"focus":true,"splitPercent":40}')).toEqual({
      fontSize: 22,
      focus: true,
      splitPercent: 40,
    });
  });

  it("defaults when missing or invalid", () => {
    expect(parseReadingPrefs(null)).toEqual({ fontSize: 18, focus: false, splitPercent: 62 });
    expect(parseReadingPrefs("{")).toEqual({ fontSize: 18, focus: false, splitPercent: 62 });
  });
});

describe("passageMetrics", () => {
  it("uses a wider measure and looser leading in focus", () => {
    const normal = passageMetrics(18, false);
    const focus = passageMetrics(18, true);
    expect(normal.fontSize).toBe("18px");
    expect(focus.lineHeight).toBeGreaterThan(normal.lineHeight);
    expect(Number.parseFloat(focus.maxWidth)).toBeGreaterThanOrEqual(36);
  });
});

describe("hideReadingSidebar", () => {
  it("hides only when Focus is on and a book is open on /reading", () => {
    expect(hideReadingSidebar(true, true, "/reading")).toBe(true);
    expect(hideReadingSidebar(true, false, "/reading")).toBe(false);
    expect(hideReadingSidebar(false, true, "/reading")).toBe(false);
    expect(hideReadingSidebar(true, true, "/")).toBe(false);
  });
});

describe("isEditableKeyTarget", () => {
  it("treats form fields as editable", () => {
    expect(isEditableKeyTarget({ tagName: "TEXTAREA" } as EventTarget)).toBe(true);
    expect(isEditableKeyTarget({ tagName: "INPUT" } as EventTarget)).toBe(true);
    expect(isEditableKeyTarget({ tagName: "DIV" } as EventTarget)).toBe(false);
  });
});
