import { describe, expect, it } from "vitest";
import {
  buildExplainPrompt,
  dateRangeToHours,
  defaultDateRange,
  noteSessionType,
  pendingSendContext,
  selectedValues,
} from "./toolbar";

describe("dateRangeToHours", () => {
  it("counts inclusive calendar hours from from-start to to-end", () => {
    expect(dateRangeToHours("2026-09-12", "2026-09-14")).toBe(72);
  });

  it("defaults to 48 when a bound is missing", () => {
    expect(dateRangeToHours("", "2026-09-14")).toBe(48);
    expect(dateRangeToHours("2026-09-12", "")).toBe(48);
  });
});

describe("defaultDateRange", () => {
  it("returns ISO from/to spanning the requested days", () => {
    const { from, to } = defaultDateRange(2, new Date("2026-09-14T12:00:00"));
    expect(to).toBe("2026-09-14");
    expect(from).toBe("2026-09-12");
  });
});

describe("buildExplainPrompt", () => {
  it("includes topic, deep-dive instructions, and web search when asked", () => {
    const p = buildExplainPrompt("LoRA", "deep", true);
    expect(p).toContain('EXPLAIN THIS: "LoRA"');
    expect(p).toContain("comprehensive deep-dive");
    expect(p).toContain("web search");
    expect(p).toContain("knowledge base");
  });

  it("uses a short instruction for quick depth", () => {
    const p = buildExplainPrompt("RLHF", "quick", false);
    expect(p).toContain("2-3 paragraphs");
    expect(p).not.toContain("web search");
  });
});

describe("selectedValues", () => {
  it("returns only checked member ids", () => {
    expect(selectedValues({ a: true, b: false, c: true })).toEqual(["a", "c"]);
  });
});

describe("noteSessionType", () => {
  it("maps learning session UUIDs and defaults to general", () => {
    expect(noteSessionType("00000000-0000-0000-0000-000000000001")).toBe("ai_learning");
    expect(noteSessionType("00000000-0000-0000-0000-000000000002")).toBe("tech_english");
    expect(noteSessionType("00000000-0000-0000-0000-000000000003")).toBe("casual_english");
    expect(noteSessionType("00000000-0000-0000-0000-000000000004")).toBe("aws_cert");
    expect(noteSessionType("abc")).toBe("general");
    expect(noteSessionType("")).toBe("general");
  });
});

describe("pendingSendContext", () => {
  it("uses the opened deep-dive session id and its messages, not an empty current session", () => {
    const ctx = pendingSendContext(
      { sessionId: "dive-1", prompt: "Please teach me about this topic.", autoSend: true },
      { id: "dive-1", messages: [{ role: "user", content: "seed teaching prompt" }] },
      "",
    );
    expect(ctx.sessionId).toBe("dive-1");
    expect(ctx.history).toEqual([{ role: "user", content: "seed teaching prompt" }]);
  });
});
