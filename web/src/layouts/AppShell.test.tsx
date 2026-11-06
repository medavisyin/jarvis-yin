import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppShell } from "./AppShell";

describe("AppShell sidebar", () => {
  it("shows Notes as its own left-menu link", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter initialEntries={["/"]}>
        <AppShell />
      </MemoryRouter>,
    );
    expect(html).toContain(">Notes<");
    expect(html).toContain('href="/notes"');
    expect(html).not.toContain('href="/news/notes"');
  });
});
