import { describe, expect, it } from "vitest";
import { parseSseChunk } from "./sse";

describe("parseSseChunk", () => {
  it("yields JSON events and ignores [DONE]", () => {
    const { events, rest } = parseSseChunk(
      'data: {"type":"token","content":"Hi"}\n\ndata: [DONE]\n\npartial',
    );
    expect(events).toEqual([{ type: "token", content: "Hi" }]);
    expect(rest).toBe("partial");
  });
});
