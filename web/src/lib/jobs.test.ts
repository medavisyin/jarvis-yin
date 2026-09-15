import { describe, expect, it } from "vitest";
import { isTerminalJobStatus, wait } from "./jobs";

describe("isTerminalJobStatus", () => {
  it("treats done, error, stopped, complete, completed, and failed as terminal", () => {
    expect(isTerminalJobStatus("done")).toBe(true);
    expect(isTerminalJobStatus("error")).toBe(true);
    expect(isTerminalJobStatus("stopped")).toBe(true);
    expect(isTerminalJobStatus("complete")).toBe(true);
    expect(isTerminalJobStatus("completed")).toBe(true);
    expect(isTerminalJobStatus("failed")).toBe(true);
  });

  it("treats in-progress statuses as not terminal", () => {
    expect(isTerminalJobStatus("starting")).toBe(false);
    expect(isTerminalJobStatus("running")).toBe(false);
    expect(isTerminalJobStatus("layer1")).toBe(false);
    expect(isTerminalJobStatus("")).toBe(false);
    expect(isTerminalJobStatus(undefined)).toBe(false);
  });
});

describe("wait", () => {
  it("rejects with AbortError when the signal aborts during sleep", async () => {
    const ac = new AbortController();
    const pending = wait(500, ac.signal);
    ac.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});
