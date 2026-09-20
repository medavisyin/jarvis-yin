export type FinanceItem = {
  title?: string;
  url?: string;
  source?: string;
};

export type FinanceCategoryBlock = {
  category?: string;
  label?: string;
  items?: FinanceItem[];
};

export type SourceLike = { id: string; category?: string };

export function pickFinanceCategory(
  payload: { categories?: FinanceCategoryBlock[] } | null | undefined,
  catId: string,
): FinanceItem[] {
  const block = (payload?.categories || []).find((c) => c.category === catId);
  return block?.items || [];
}

export function mdFilesOnly(files: { name: string; size_kb?: number }[] | undefined) {
  return (files || []).filter((f) => f.name.endsWith(".md"));
}

export function audioTranslateTarget(current?: string): "en" | "zh" {
  return (current || "zh") === "zh" ? "en" : "zh";
}

export function refetchAudioSteps(stepName: string): string[] {
  if (stepName === "ai_audio") return ["refetch_ai", stepName];
  if (stepName === "finance_audio" || stepName.startsWith("fn_audio:")) {
    return ["refetch_finance", "finance_news_merge", "finance_news_translate", stepName];
  }
  return [stepName];
}

export function refetchWorldNewsSteps(): string[] {
  return ["refetch_world", "world_news_merge", "world_news_translate"];
}

export function enabledSourceIdsForCategory(
  sources: SourceLike[],
  enabled: Record<string, boolean>,
  catId: string,
): string[] {
  return sources.filter((s) => s.category === catId && enabled[s.id]).map((s) => s.id);
}

export function buildEnabledMap(
  sources: SourceLike[],
  enabled: Record<string, boolean>,
): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  for (const s of sources) out[s.id] = !!enabled[s.id];
  return out;
}

export function renderReportMarkdown(md: string): string {
  let rendered = md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, '<h4 class="text-primary mt-3 mb-1 text-sm font-medium">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 class="mt-4 mb-2 text-base font-medium">$1</h3>')
    .replace(/^# (.+)$/gm, '<h2 class="mt-4 mb-2 text-lg font-medium">$1</h2>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
      '<a class="text-primary underline" href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
    )
    .replace(/^\|(.+)\|$/gm, (match) => {
      const cells = match.split("|").filter((c) => c.trim() !== "");
      if (cells.every((c) => /^[\s-:]+$/.test(c))) return "";
      return (
        "<tr>" +
        cells
          .map((c) => `<td class="border-border border px-2 py-0.5">${c.trim()}</td>`)
          .join("") +
        "</tr>"
      );
    })
    .replace(/^- (.+)$/gm, '<li class="list-inside list-disc">$1</li>')
    .replace(/^---+$/gm, '<hr class="border-border my-3">')
    .replace(/\n{2,}/g, "<br><br>")
    .replace(/\n/g, "<br>");
  rendered = rendered.replace(
    /(<tr>[\s\S]*?<\/tr>(?:\s*<tr>[\s\S]*?<\/tr>)*)/g,
    '<table class="my-2 w-full border-collapse text-sm">$1</table>',
  );
  return rendered;
}

export type DeepDiveItem = {
  title: string;
  sourceUrl?: string;
  rawFile?: string;
};

export function parseLearningGuideDeepDives(md: string): DeepDiveItem[] {
  const items: DeepDiveItem[] = [];
  const chunks = md.split(/^\d+\.\s+/m).slice(1);
  for (const chunk of chunks) {
    const titleMatch = chunk.match(/^\*\*(.+?)\*\*/);
    if (!titleMatch) continue;
    const fileMatch = chunk.match(/File:\s*`([^`]+)`/i) || chunk.match(/File:\s+(\S+)/i);
    const srcMatch = chunk.match(/Source:\s*(https?:\/\/\S+)/i);
    items.push({
      title: titleMatch[1].trim(),
      rawFile: fileMatch?.[1],
      sourceUrl: srcMatch?.[1]?.replace(/[.,);]+$/, ""),
    });
  }
  return items;
}
