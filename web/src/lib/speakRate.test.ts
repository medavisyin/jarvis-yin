import { describe, expect, it } from "vitest";
import { browserSpeakRate, edgeSpeakRate, normalizeSpeakRate } from "./speakRate";

describe("normalizeSpeakRate", () => {
  it("keeps slow, medium, and fast", () => {
    expect(normalizeSpeakRate("slow")).toBe("slow");
    expect(normalizeSpeakRate("medium")).toBe("medium");
    expect(normalizeSpeakRate("FAST")).toBe("fast");
  });

  it("defaults to slow", () => {
    expect(normalizeSpeakRate(undefined)).toBe("slow");
    expect(normalizeSpeakRate("quick")).toBe("slow");
  });
});

describe("edgeSpeakRate", () => {
  it("maps to Edge TTS percent strings", () => {
    expect(edgeSpeakRate("slow")).toBe("-25%");
    expect(edgeSpeakRate("medium")).toBe("-10%");
    expect(edgeSpeakRate("fast")).toBe("+0%");
  });
});

describe("browserSpeakRate", () => {
  it("is slower than the old 0.92 default", () => {
    expect(browserSpeakRate("slow")).toBe(0.68);
    expect(browserSpeakRate("medium")).toBe(0.82);
    expect(browserSpeakRate("fast")).toBe(0.95);
    expect(browserSpeakRate("slow")).toBeLessThan(0.92);
  });
});
