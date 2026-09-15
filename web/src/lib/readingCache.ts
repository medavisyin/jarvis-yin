export type CachedSlot = {
  text?: string;
  status?: string;
  offset?: number;
  part?: number;
  hasMore?: boolean;
  lastOffset?: number;
  reflection?: string;
};

export type ReadingSlot = {
  text: string;
  part: number;
  offset: number;
  hasMore: boolean;
  lastOffset: number;
  reflection: string;
};

export function emptyReadingSlot(): ReadingSlot {
  return { text: "", part: 1, offset: 0, hasMore: false, lastOffset: 0, reflection: "" };
}

export function cacheTabKey(kind: string, level: string, lang: string): string {
  if (!kind || kind === "speaking") return kind;
  return `${kind}__${level}__${lang}`;
}

export function lookupCachedTab(
  tabs: Record<string, CachedSlot> | null | undefined,
  kind: string,
  level: string,
  lang: string,
): CachedSlot | null {
  if (!tabs || !kind) return null;
  const key = cacheTabKey(kind, level, lang);
  if (tabs[key]) return tabs[key];
  if (lang !== "en") return null;
  for (const legacy of [`${kind}__${level}`, kind]) {
    if (tabs[legacy]) return tabs[legacy];
  }
  return null;
}

export function slotFromCache(raw: CachedSlot | null | undefined): ReadingSlot {
  if (!raw) return emptyReadingSlot();
  return {
    text: raw.text || "",
    part: Number(raw.part || 1) || 1,
    offset: Number(raw.offset || 0) || 0,
    hasMore: Boolean(raw.hasMore),
    lastOffset: Number(raw.lastOffset || 0) || 0,
    reflection: raw.reflection || "",
  };
}

export function slotsFromCachedTabs(
  tabs: Record<string, CachedSlot> | null | undefined,
  kinds: string[],
  level: string,
  lang: string,
): Record<string, ReadingSlot> {
  const out: Record<string, ReadingSlot> = {};
  for (const kind of kinds) {
    if (!kind || kind === "speaking") continue;
    const found = lookupCachedTab(tabs, kind, level, lang);
    if (found) out[kind] = slotFromCache(found);
  }
  return out;
}

export function pickTabWithText(
  kinds: string[],
  slots: Record<string, ReadingSlot>,
  fallback: string,
): string {
  for (const id of kinds) {
    if (!id || id === "speaking") continue;
    const slot = slots[id];
    if (slot && (slot.text.trim() || slot.reflection.trim())) return id;
  }
  return fallback;
}

export function analysisExplainEnabled(text: string, streaming: boolean): boolean {
  return Boolean(text.trim()) && !streaming;
}

export function slotToPersistBody(
  kind: string,
  slot: ReadingSlot,
  level: string,
  lang: string,
): {
  kind: string;
  slot: {
    text: string;
    status: "done" | "idle";
    offset: number;
    part: number;
    hasMore: boolean;
    lastOffset: number;
    learner_level: string;
    output_lang: string;
    reflection: string;
  };
  merge: true;
} {
  return {
    kind: cacheTabKey(kind, level, lang),
    slot: {
      text: slot.text,
      status: slot.text.trim() ? "done" : "idle",
      offset: slot.offset,
      part: slot.part,
      hasMore: slot.hasMore,
      lastOffset: slot.lastOffset,
      learner_level: level,
      output_lang: lang,
      reflection: slot.reflection,
    },
    merge: true,
  };
}
