import { renderChatMarkdown } from "./chatMarkdown";

export const ANALYSIS_LEGEND = [
  { id: "heading", label: "标题", hint: "字重" },
  { id: "quote", label: "引用", hint: "左边线" },
  { id: "emphasis", label: "强调", hint: "暖底" },
] as const;

export function renderAnalysisHtml(text: string): string {
  return renderChatMarkdown(text || "");
}
