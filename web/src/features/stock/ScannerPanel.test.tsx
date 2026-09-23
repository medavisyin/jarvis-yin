import { describe, expect, it } from "vitest";
import { SCANNER_KINDS } from "@/features/stock/ScannerPanel";

describe("SCANNER_KINDS", () => {
  it("keeps four scanners and drops AI scan, Right-side", () => {
    expect(SCANNER_KINDS.map((k) => k.id)).toEqual(["unified", "long-term", "qv", "midday"]);
    expect(SCANNER_KINDS.map((k) => k.label)).toEqual(["Left-Right-ATH", "Long-term", "Quality-value", "Midday"]);
  });
});
