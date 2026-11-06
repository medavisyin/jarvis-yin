import { useEffect, useRef, useState, type ReactNode } from "react";
import { apiJson } from "@/lib/api";
import "./pdfMapPolyfill.js";
import { chapterKey } from "./chapterTarget";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

const pdfWorkerPolyfill = `
function install(prototype) {
  if (typeof prototype.getOrInsert !== "function") {
    Object.defineProperty(prototype, "getOrInsert", {
      configurable: true,
      writable: true,
      value(key, value) {
        if (!this.has(key)) this.set(key, value);
        return this.get(key);
      },
    });
  }
  if (typeof prototype.getOrInsertComputed !== "function") {
    Object.defineProperty(prototype, "getOrInsertComputed", {
      configurable: true,
      writable: true,
      value(key, callback) {
        if (!this.has(key)) this.set(key, callback(key));
        return this.get(key);
      },
    });
  }
}
install(Map.prototype);
install(WeakMap.prototype);
`;

let pdfWorkerReady = false;

function ensurePdfWorker() {
  if (pdfWorkerReady) return;
  pdfWorkerReady = true;
  const file = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).href;
  const source = `${pdfWorkerPolyfill}\nawait import(${JSON.stringify(file)});\n`;
  pdfjs.GlobalWorkerOptions.workerSrc = URL.createObjectURL(new Blob([source], { type: "text/javascript" }));
}

export function PdfPassage({
  bookId,
  chapterTitle,
  startPage,
  excerpt,
  fallback,
}: {
  bookId: string;
  chapterTitle?: string;
  startPage?: number | null;
  excerpt?: string;
  fallback?: ReactNode;
}) {
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(1);
  const [failed, setFailed] = useState(false);
  const [width, setWidth] = useState(720);
  const wrap = useRef<HTMLDivElement>(null);
  const ready = pages > 0 && !failed;
  ensurePdfWorker();

  useEffect(() => {
    if (typeof startPage === "number" && startPage >= 0) {
      setPage(startPage + 1);
      return;
    }
    const title = chapterKey(chapterTitle);
    const opening = (excerpt || "").replace(/\s+/g, " ").trim().slice(0, 80);
    if (!title && !opening) return;
    let cancel = false;
    const params = new URLSearchParams();
    if (chapterTitle) params.set("title", chapterTitle);
    if (opening) params.set("excerpt", opening);
    apiJson<{ page?: number }>(
      `/api/intensive-reading/books/${bookId}/rendition/location?${params.toString()}`,
    )
      .then((body) => {
        if (!cancel && typeof body.page === "number" && body.page >= 0) setPage(body.page + 1);
      })
      .catch(() => undefined);
    return () => {
      cancel = true;
    };
  }, [bookId, chapterTitle, startPage, excerpt]);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const apply = () => setWidth(Math.max(280, Math.floor(el.clientWidth) - 8));
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(el);
    return () => observer.disconnect();
  }, [ready]);

  return (
    <div ref={wrap} className="reading-pdf">
      {ready ? null : fallback}
      <div className={ready ? undefined : "hidden"}>
      {pages > 1 ? (
        <div className="mb-4 flex items-center justify-center gap-3 text-sm">
          <button
            type="button"
            className="rounded border px-2 py-1 disabled:opacity-40"
            disabled={page <= 1}
            onClick={() => setPage((value) => Math.max(1, value - 1))}
          >
            上一页
          </button>
          <span className="text-muted-foreground">
            {page}/{pages}
          </span>
          <button
            type="button"
            className="rounded border px-2 py-1 disabled:opacity-40"
            disabled={page >= pages}
            onClick={() => setPage((value) => Math.min(pages, value + 1))}
          >
            下一页
          </button>
        </div>
      ) : null}
      <Document
        file={`/api/intensive-reading/books/${bookId}/original`}
        onLoadSuccess={(doc) => {
          setFailed(false);
          setPages(doc.numPages);
        }}
        onLoadError={() => setFailed(true)}
        loading={null}
        error={null}
      >
        {pages > 0 ? (
          <Page pageNumber={page} width={width} renderTextLayer renderAnnotationLayer />
        ) : null}
      </Document>
      </div>
    </div>
  );
}
