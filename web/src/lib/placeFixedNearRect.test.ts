import { describe, expect, it } from "vitest";
import { placeFixedNearRect } from "./placeFixedNearRect";

const viewport = { width: 800, height: 600 };
const size = { width: 380, height: 280 };

describe("placeFixedNearRect", () => {
  it("places below the selection when there is room", () => {
    const placed = placeFixedNearRect(
      { left: 200, top: 80, width: 40, height: 20, bottom: 100 },
      size,
      { preferBelow: true, viewport },
    );
    expect(placed.top).toBe(108);
    expect(placed.left).toBe(Math.round(200 + 20 - 190));
  });

  it("flips above the selection when below would overflow the viewport", () => {
    const placed = placeFixedNearRect(
      { left: 200, top: 500, width: 40, height: 20, bottom: 520 },
      size,
      { preferBelow: true, viewport },
    );
    expect(placed.top).toBe(500 - 280 - 8);
  });

  it("clamps into the viewport when the panel is taller than remaining space", () => {
    const tall = { width: 380, height: 580 };
    const placed = placeFixedNearRect(
      { left: 200, top: 40, width: 40, height: 20, bottom: 60 },
      tall,
      { preferBelow: true, viewport },
    );
    expect(placed.top).toBe(8);
    expect(placed.top + tall.height).toBeLessThanOrEqual(viewport.height - 8);
  });
});
