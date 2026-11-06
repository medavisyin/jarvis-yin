import { describe, expect, it } from "vitest";
import { spineIndexFor, startPageFor } from "./chapterTarget";

describe("chapter targets", () => {
  it("matches a chapter menu title to the EPUB spine, ignoring part suffixes", () => {
    const spine = [{ title: "cover" }, { title: "CHAPTER 1" }, { title: "CHAPTER 2" }];
    expect(spineIndexFor(spine, "Chapter 1 (2)")).toBe(1);
    expect(spineIndexFor(spine, "Missing")).toBe(-1);
  });

  it("uses the stored PDF start page for that chapter", () => {
    const toc = [
      { title: "CHAPTER 1" },
      { title: "CHAPTER 2", start_page: 38 },
    ];
    expect(startPageFor(toc, "CHAPTER 2 (1)")).toBe(38);
    expect(startPageFor(toc, "CHAPTER 1")).toBeNull();
  });
});
