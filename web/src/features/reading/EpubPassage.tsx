import { useEffect, useState, type ReactNode } from "react";
import { apiJson } from "@/lib/api";
import { spineIndexFor } from "./chapterTarget";
import { EpubHtml, type EpubDocument } from "./EpubHtml";

type SpineItem = { href?: string; title?: string };

export function EpubPassage({
  bookId,
  chapterTitle,
  fallback,
}: {
  bookId: string;
  chapterTitle?: string;
  fallback?: ReactNode;
}) {
  const [spine, setSpine] = useState<SpineItem[]>([]);
  const [index, setIndex] = useState(0);
  const [document, setDocument] = useState<EpubDocument | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancel = false;
    setSpine([]);
    setIndex(0);
    setDocument(null);
    setError("");
    apiJson<{ spine?: SpineItem[] }>(`/api/intensive-reading/books/${bookId}/rendition`)
      .then((body) => {
        if (!cancel) setSpine(body.spine || []);
      })
      .catch((err: unknown) => {
        if (!cancel) setError(err instanceof Error ? err.message : "EPUB 打不开");
      });
    return () => {
      cancel = true;
    };
  }, [bookId]);

  useEffect(() => {
    const found = spineIndexFor(spine, chapterTitle);
    if (found >= 0) setIndex(found);
  }, [chapterTitle, spine]);

  const current = spine[index];
  const href = current?.href || "";

  useEffect(() => {
    if (!href) return;
    let cancel = false;
    setDocument(null);
    apiJson<{ html?: string }>(
      `/api/intensive-reading/books/${bookId}/rendition/document?href=${encodeURIComponent(href)}`,
    )
      .then((body) => {
        if (!cancel) setDocument({ href, html: body.html || "" });
      })
      .catch((err: unknown) => {
        if (!cancel) setError(err instanceof Error ? err.message : "这一章打不开");
      });
    return () => {
      cancel = true;
    };
  }, [bookId, href]);

  if (error || !document) return <>{fallback}</>;
  return (
    <div>
      {spine.length > 1 ? (
        <div className="mb-4 flex items-center justify-center gap-3 text-sm">
          <button
            type="button"
            className="rounded border px-2 py-1 disabled:opacity-40"
            disabled={index <= 0}
            onClick={() => setIndex((value) => Math.max(0, value - 1))}
          >
            上一章
          </button>
          <span className="text-muted-foreground">
            {current?.title || href} · {index + 1}/{spine.length}
          </span>
          <button
            type="button"
            className="rounded border px-2 py-1 disabled:opacity-40"
            disabled={index >= spine.length - 1}
            onClick={() => setIndex((value) => Math.min(spine.length - 1, value + 1))}
          >
            下一章
          </button>
        </div>
      ) : null}
      <EpubHtml documents={[document]} />
    </div>
  );
}
