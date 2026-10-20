import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PassageSpeakBar } from "./PassageSpeakBar";

const base = {
  engine: "edge" as const,
  voiceEn: "female" as const,
  voiceZh: "male" as const,
  style: "平静",
  speaking: false,
  canResume: false,
  error: "",
  onEngine: () => undefined,
  onVoiceEn: () => undefined,
  onVoiceZh: () => undefined,
  onStyle: () => undefined,
  onToggle: () => undefined,
};

describe("PassageSpeakBar", () => {
  it("puts 阅读全文 beside the passage label and hides style unless MiMo", () => {
    const html = renderToStaticMarkup(<PassageSpeakBar {...base} />);
    expect(html).toContain("阅读全文");
    expect(html).toContain("Voice EN");
    expect(html).toContain("Voice ZH");
    expect(html).not.toContain(">Style<");
  });

  it("shows 继续 when this page can resume", () => {
    const html = renderToStaticMarkup(<PassageSpeakBar {...base} canResume />);
    expect(html).toContain("继续");
    expect(html).not.toContain("阅读全文");
  });

  it("shows Style for MiMo and 停止 while speaking", () => {
    const html = renderToStaticMarkup(
      <PassageSpeakBar {...base} engine="mimo" speaking error="朗读失败" />,
    );
    expect(html).toContain("停止");
    expect(html).toContain("Style");
    expect(html).toContain("平静");
    expect(html).toContain("朗读失败");
  });
});
