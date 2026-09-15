import { describe, expect, it } from "vitest";
import { parseTheme, themeClass } from "./theme";

describe("themeClass", () => {
  it("maps day to light and night to dark", () => {
    expect(themeClass("day")).toBe("light");
    expect(themeClass("night")).toBe("dark");
  });

  it("keeps reading on the light paper palette", () => {
    expect(themeClass("reading")).toBe("light");
  });
});

describe("parseTheme", () => {
  it("accepts day, night, and reading", () => {
    expect(parseTheme("day")).toBe("day");
    expect(parseTheme("night")).toBe("night");
    expect(parseTheme("reading")).toBe("reading");
  });

  it("falls back to day for unknown values", () => {
    expect(parseTheme(null)).toBe("day");
    expect(parseTheme("sepia")).toBe("day");
  });
});
