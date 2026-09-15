import { describe, expect, it } from "vitest";
import { normalizeSelectionText } from "./selection";

describe("normalizeSelectionText", () => {
  it("collapses whitespace and trims", () => {
    expect(normalizeSelectionText("  good\n  sentence  ")).toBe("good sentence");
  });

  it("caps length", () => {
    expect(normalizeSelectionText("abcdefghij", 4)).toBe("abcd");
  });
});
