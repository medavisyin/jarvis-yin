import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EpubHtml } from "./EpubHtml";

describe("EpubHtml", () => {
  it("keeps the chapter HTML, including images, inside the passage", () => {
    const html = renderToStaticMarkup(
      <EpubHtml
        documents={[
          {
            href: "OEBPS/chap1.xhtml",
            html: '<h1>Chapter One</h1><p>The ship sailed.</p><img src="/api/pic.png" alt="harbour"/>',
          },
        ]}
      />,
    );
    expect(html).toContain("Chapter One");
    expect(html).toContain("The ship sailed.");
    expect(html).toContain('src="/api/pic.png"');
    expect(html).toContain("reading-epub");
  });
});
