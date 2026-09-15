import { describe, expect, it } from "vitest";
import { renderChatMarkdown } from "./chatMarkdown";

describe("renderChatMarkdown", () => {
  it("renders headings, bold, quotes, and safe links", () => {
    const html = renderChatMarkdown("## Title\n\n> quoted\n\n**bold** [x](https://ex.test/a)");
    expect(html).toContain("<h3");
    expect(html).toContain("<blockquote");
    expect(html).toContain("<strong>");
    expect(html).toContain('href="https://ex.test/a"');
  });

  it("keeps fenced code and escapes HTML", () => {
    const html = renderChatMarkdown("```js\n<script>x</script>\n```\n<img>");
    expect(html).toContain("<pre");
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<img>");
    expect(html).toContain("&lt;img&gt;");
  });
});
