import { describe, expect, it } from "vitest";
import { clampGridHeight } from "./dataGrid";

describe("clampGridHeight", () => {
  it("sizes to row count and caps at the max", () => {
    expect(clampGridHeight(0)).toBe(120);
    expect(clampGridHeight(3, 36, 40, 420)).toBe(40 + 3 * 36);
    expect(clampGridHeight(50, 36, 40, 420)).toBe(420);
  });
});
