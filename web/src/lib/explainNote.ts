export type ExplainNoteInput = {
  selected: string;
  explanation: string;
  bookId: string;
  bookTitle?: string;
  chunkTitle?: string;
  chunkIndex?: number;
};

export function formatExplainNote(input: ExplainNoteInput): {
  title: string;
  content: string;
  tags: string[];
  session_type: string;
} {
  const selected = input.selected.trim();
  const chapter = input.chunkIndex != null ? String(input.chunkIndex + 1) : "";
  const loc = [input.bookTitle?.trim(), chapter ? `第 ${chapter} 节` : "", input.chunkTitle?.trim()]
    .filter(Boolean)
    .join(" · ");
  const content = [`**${selected}**`, loc, input.explanation.trim()].filter(Boolean).join("\n\n");
  return {
    title: selected,
    content,
    tags: ["intensive_reading", input.bookId].filter(Boolean),
    session_type: "intensive_reading",
  };
}

export function canSaveExplainNote(input: { explanation: string; busy?: boolean }): boolean {
  if (input.busy) return false;
  const text = input.explanation.trim();
  if (!text || text === "解释中…" || text === "没有返回解释") return false;
  return true;
}
