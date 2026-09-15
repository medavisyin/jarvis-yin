import { describe, expect, it } from "vitest";
import {
  analysisExplainEnabled,
  cacheTabKey,
  lookupCachedTab,
  pickTabWithText,
  slotFromCache,
  slotToPersistBody,
  slotsFromCachedTabs,
} from "./readingCache";

describe("cacheTabKey", () => {
  it("keys analysis tabs as kind__level__lang", () => {
    expect(cacheTabKey("vocab", "university", "zh")).toBe("vocab__university__zh");
  });

  it("leaves speaking unscoped", () => {
    expect(cacheTabKey("speaking", "university", "zh")).toBe("speaking");
  });
});

describe("lookupCachedTab", () => {
  const tabs = {
    vocab__university__zh: { text: "好词" },
    vocab__university: { text: "legacy-level" },
    vocab: { text: "legacy-kind" },
  };

  it("prefers the current level and language key", () => {
    expect(lookupCachedTab(tabs, "vocab", "university", "zh")?.text).toBe("好词");
  });

  it("falls back to unscoped English keys only when language is en", () => {
    expect(lookupCachedTab(tabs, "vocab", "university", "en")?.text).toBe("legacy-level");
    expect(lookupCachedTab({ vocab: { text: "legacy-kind" } }, "vocab", "university", "en")?.text).toBe(
      "legacy-kind",
    );
    expect(lookupCachedTab({ vocab: { text: "legacy-kind" } }, "vocab", "university", "zh")).toBeNull();
  });
});

describe("slotsFromCachedTabs", () => {
  it("maps cache keys onto tab ids used by the UI", () => {
    const slots = slotsFromCachedTabs(
      {
        vocab__university__zh: {
          text: "好词好句",
          offset: 1200,
          part: 2,
          hasMore: true,
          lastOffset: 800,
          reflection: "",
        },
        socratic__university__zh: { text: "", reflection: "读后感" },
      },
      ["vocab", "socratic", "speaking"],
      "university",
      "zh",
    );
    expect(slots.vocab.text).toBe("好词好句");
    expect(slots.vocab.hasMore).toBe(true);
    expect(slots.vocab.offset).toBe(1200);
    expect(slots.socratic.reflection).toBe("读后感");
    expect(slots.speaking).toBeUndefined();
  });
});

describe("pickTabWithText", () => {
  it("selects the first analysis tab that already has text", () => {
    expect(
      pickTabWithText(
        ["speaking", "vocab", "themes"],
        { themes: slotFromCache({ text: "主题" }) },
        "vocab",
      ),
    ).toBe("themes");
  });
});

describe("analysisExplainEnabled", () => {
  it("is on only when analysis text is present and not streaming", () => {
    expect(analysisExplainEnabled("  分析  ", false)).toBe(true);
    expect(analysisExplainEnabled("分析", true)).toBe(false);
    expect(analysisExplainEnabled("   ", false)).toBe(false);
  });
});

describe("slotToPersistBody", () => {
  it("PUTs under the scoped cache key with merge", () => {
    const body = slotToPersistBody(
      "vocab",
      slotFromCache({ text: "好词", offset: 10, part: 1, hasMore: false, lastOffset: 10 }),
      "university",
      "zh",
    );
    expect(body).toEqual({
      kind: "vocab__university__zh",
      slot: {
        text: "好词",
        status: "done",
        offset: 10,
        part: 1,
        hasMore: false,
        lastOffset: 10,
        learner_level: "university",
        output_lang: "zh",
        reflection: "",
      },
      merge: true,
    });
  });
});
