export const READING_PREFS_KEY = "jarvis-reading-prefs";

export type FontSize = 18 | 20 | 22;

export type ReadingPrefs = {
  fontSize: FontSize;
  focus: boolean;
  splitPercent: number;
};

export const DEFAULT_SPLIT_PERCENT = 62;
export const MIN_SPLIT_PERCENT = 30;
export const MAX_SPLIT_PERCENT = 75;

export function parseFontSize(raw: unknown): FontSize {
  if (raw === 20 || raw === 22 || raw === 18) return raw;
  if (raw === "20" || raw === "22" || raw === "18") return Number(raw) as FontSize;
  return 18;
}

export function parseSplitPercent(raw: unknown): number {
  const n = typeof raw === "number" ? raw : typeof raw === "string" ? Number(raw) : NaN;
  if (!Number.isFinite(n)) return DEFAULT_SPLIT_PERCENT;
  return Math.min(MAX_SPLIT_PERCENT, Math.max(MIN_SPLIT_PERCENT, Math.round(n)));
}

export function parseReadingPrefs(raw: string | null | undefined): ReadingPrefs {
  try {
    const data = raw ? JSON.parse(raw) : {};
    return {
      fontSize: parseFontSize(data.fontSize),
      focus: data.focus === true,
      splitPercent: parseSplitPercent(data.splitPercent),
    };
  } catch {
    return { fontSize: 18, focus: false, splitPercent: DEFAULT_SPLIT_PERCENT };
  }
}

export function readReadingPrefs(): ReadingPrefs {
  if (typeof localStorage === "undefined") return parseReadingPrefs(null);
  return parseReadingPrefs(localStorage.getItem(READING_PREFS_KEY));
}

export function writeReadingPrefs(prefs: ReadingPrefs) {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(READING_PREFS_KEY, JSON.stringify(prefs));
}

export function hideReadingSidebar(focus: boolean, bookOpen: boolean, pathname: string): boolean {
  return Boolean(focus && bookOpen && pathname.startsWith("/reading"));
}

export function isEditableKeyTarget(target: EventTarget | null): boolean {
  if (!target || typeof target !== "object") return false;
  const el = target as { tagName?: string; isContentEditable?: boolean };
  const tag = (el.tagName || "").toUpperCase();
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return Boolean(el.isContentEditable);
}

export function passageMetrics(fontSize: FontSize, focus: boolean): {
  fontSize: string;
  lineHeight: number;
  maxWidth: string;
} {
  return {
    fontSize: `${fontSize}px`,
    lineHeight: focus ? 1.8 : 1.72,
    maxWidth: focus ? "40em" : "38em",
  };
}
