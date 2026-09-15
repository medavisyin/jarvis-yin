import { describe, expect, it } from "vitest";
import { canSaveExplainNote, formatExplainNote } from "./explainNote";

describe("formatExplainNote", () => {
  it("puts selected word, book/chapter, and explanation in the note", () => {
    const note = formatExplainNote({
      selected: "congressman",
      explanation: "国会议员",
      bookId: "promised-land",
      bookTitle: "A Promised Land",
      chunkTitle: "Chapter 16",
      chunkIndex: 15,
    });
    expect(note.title).toBe("congressman");
    expect(note.content).toContain("congressman");
    expect(note.content).toContain("A Promised Land");
    expect(note.content).toContain("16");
    expect(note.content).toContain("Chapter 16");
    expect(note.content).toContain("国会议员");
    expect(note.tags).toEqual(["intensive_reading", "promised-land"]);
    expect(note.session_type).toBe("intensive_reading");
  });
});

describe("canSaveExplainNote", () => {
  it("is false while explaining or when the body is empty", () => {
    expect(canSaveExplainNote({ explanation: "国会议员", busy: true })).toBe(false);
    expect(canSaveExplainNote({ explanation: "", busy: false })).toBe(false);
    expect(canSaveExplainNote({ explanation: "解释中…", busy: false })).toBe(false);
    expect(canSaveExplainNote({ explanation: "国会议员", busy: false })).toBe(true);
  });
});
