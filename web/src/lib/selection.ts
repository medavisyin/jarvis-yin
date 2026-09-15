export function normalizeSelectionText(raw: string, max = 2000): string {
  return raw.replace(/\s+/g, " ").trim().slice(0, max);
}
