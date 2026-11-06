export type ChapterSpineItem = { href?: string; title?: string };
export type ChapterTocEntry = { title?: string; start_page?: number };

export function chapterKey(title: string | undefined): string {
  return (title || "").replace(/\s*\(\d+\)\s*$/, "").trim().toLowerCase();
}

export function spineIndexFor(spine: ChapterSpineItem[], title: string | undefined): number {
  const want = chapterKey(title);
  if (!want) return -1;
  return spine.findIndex((item) => chapterKey(item.title) === want);
}

export function startPageFor(toc: ChapterTocEntry[], title: string | undefined): number | null {
  const want = chapterKey(title);
  if (!want) return null;
  const hit = toc.find((entry) => chapterKey(entry.title) === want && typeof entry.start_page === "number");
  return hit?.start_page ?? null;
}
