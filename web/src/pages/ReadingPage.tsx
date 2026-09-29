import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { apiJson, apiSsePost, apiUpload } from "@/lib/api";
import { CloudModelSelect, type CloudModel } from "@/components/CloudModelSelect";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ExplainPopover } from "@/features/reading/ExplainPopover";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { cn } from "@/lib/utils";
import { ANALYSIS_LEGEND, renderAnalysisHtml } from "@/lib/analysisMarkdown";
import { useReadingFocus } from "@/lib/readingFocus";
import {
  parseFontSize,
  parseSplitPercent,
  passageMetrics,
  readReadingPrefs,
  writeReadingPrefs,
  isEditableKeyTarget,
  type FontSize,
} from "@/lib/readingPrefs";
import {
  analysisExplainEnabled,
  emptyReadingSlot,
  pickTabWithText,
  slotToPersistBody,
  slotsFromCachedTabs,
  type CachedSlot,
  type ReadingSlot,
} from "@/lib/readingCache";

type Book = {
  book_id: string;
  title?: string;
  book_type?: string;
  status?: string;
  chunk_count?: number;
  rag_status?: string;
  progress?: { chunk_index?: number; total?: number } | null;
};

type TocEntry = { title?: string; chunk_index: number };

type ChunkResp = {
  chunk?: { text?: string; is_toc?: boolean };
  chunk_index?: number;
  total?: number;
  next_index?: number | null;
  prev_index?: number | null;
  has_next?: boolean;
  has_prev?: boolean;
  title?: string;
  book_type?: string;
};

type TabInfo = { id?: string; label?: string };

type Slot = ReadingSlot;
type SpeakingCache = {
  oral?: string;
  logic?: string;
  cue?: string;
  pressure_attack?: string;
  pressure_defense?: string;
  active_exercise?: string;
};

function emptySlot(): Slot {
  return emptyReadingSlot();
}

function emptySpeaking(): SpeakingCache {
  return {
    oral: "",
    logic: "",
    cue: "",
    pressure_attack: "",
    pressure_defense: "",
    active_exercise: "",
  };
}

function speakOutFromCache(sp: SpeakingCache): string {
  const ex = sp.active_exercise;
  if (ex === "cue") return sp.cue || "";
  if (ex === "pressure") return sp.pressure_attack || sp.pressure_defense || "";
  return sp.logic || sp.cue || sp.pressure_attack || "";
}

export function ReadingPage() {
  const [books, setBooks] = useState<Book[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [bookType, setBookType] = useState("novel");
  const fileRef = useRef<HTMLInputElement>(null);
  const [openId, setOpenId] = useState("");
  const [toc, setToc] = useState<TocEntry[]>([]);
  const [showToc, setShowToc] = useState(false);
  const [chunk, setChunk] = useState<ChunkResp | null>(null);
  const [kind, setKind] = useState("vocab");
  const [tabs, setTabs] = useState<TabInfo[]>([]);
  const [slots, setSlots] = useState<Record<string, Slot>>({});
  const [cachedTabs, setCachedTabs] = useState<Record<string, CachedSlot>>({});
  const [streaming, setStreaming] = useState(false);
  const [level, setLevel] = useState("university");
  const [llm, setLlm] = useState<CloudModel>(() => {
    const saved = localStorage.getItem("jarvis-reading-llm");
    return saved === "deepseek" || saved === "glm" || saved === "mimo" ? saved : "local";
  });
  const [outLang, setOutLang] = useState("zh");
  const [oral, setOral] = useState("");
  const [speakOut, setSpeakOut] = useState("");
  const [speaking, setSpeaking] = useState<SpeakingCache>(emptySpeaking);
  const loadSeq = useRef(0);
  const { focus, setFocus, setBookOpen } = useReadingFocus();
  const [fontSize, setFontSize] = useState<FontSize>(() => readReadingPrefs().fontSize);
  const [splitPercent, setSplitPercent] = useState(() => readReadingPrefs().splitPercent);
  const [analysisOpen, setAnalysisOpen] = useState(false);

  const loadBooks = useCallback(async () => {
    const data = await apiJson<{ books: Book[] }>("/api/intensive-reading/books");
    setBooks(data.books || []);
  }, []);

  useEffect(() => {
    loadBooks().catch((e: Error) => setError(e.message));
  }, [loadBooks]);

  useEffect(() => {
    setBookOpen(Boolean(openId));
    return () => setBookOpen(false);
  }, [openId, setBookOpen]);

  useEffect(() => {
    writeReadingPrefs({ fontSize, focus, splitPercent });
  }, [fontSize, focus, splitPercent]);

  useEffect(() => {
    if (!focus) return;
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      if (isEditableKeyTarget(e.target)) return;
      setFocus(false);
      setAnalysisOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focus, setFocus]);

  async function upload() {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("Missing file");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("book_type", bookType);
      await apiUpload("/api/intensive-reading/upload", form);
      if (fileRef.current) fileRef.current.value = "";
      await loadBooks();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function persistSlot(
    analysisKind: string,
    slot: Slot,
    learnerLevel = level,
    lang = outLang,
  ): Promise<Record<string, CachedSlot>> {
    if (!openId || chunk?.chunk_index == null || analysisKind === "speaking") return cachedTabs;
    if (!slot.text.trim() && !slot.reflection.trim()) return cachedTabs;
    const body = slotToPersistBody(analysisKind, slot, learnerLevel, lang);
    await apiJson(`/api/intensive-reading/books/${openId}/chunks/${chunk.chunk_index}/analysis`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    const nextCache = { ...cachedTabs, [body.kind]: body.slot };
    setCachedTabs(nextCache);
    return nextCache;
  }

  async function persistSpeaking(next: SpeakingCache) {
    if (!openId || chunk?.chunk_index == null) return;
    await apiJson(`/api/intensive-reading/books/${openId}/chunks/${chunk.chunk_index}/analysis`, {
      method: "PUT",
      body: JSON.stringify({ speaking: next, merge: true }),
    });
  }

  async function persistCurrentBeforeLeave() {
    if (kind === "speaking") {
      await persistSpeaking({ ...speaking, oral }).catch(() => undefined);
      return;
    }
    await persistSlot(kind, slotFor(kind)).catch(() => undefined);
  }

  async function openBook(id: string, index?: number) {
    setError("");
    setOpenId(id);
    setSlots({});
    setCachedTabs({});
    setSpeakOut("");
    setSpeaking(emptySpeaking());
    const meta = await apiJson<{
      book_type?: string;
      progress?: { chunk_index?: number };
      title?: string;
      toc?: TocEntry[];
    }>(`/api/intensive-reading/books/${id}`);
    setToc(meta.toc || []);
    const bt = meta.book_type || "novel";
    const tabData = await apiJson<{ tabs?: TabInfo[] }>(
      `/api/intensive-reading/tabs?book_type=${encodeURIComponent(bt)}`,
    );
    const kinds = tabData.tabs || [];
    setTabs(kinds);
    const first = kinds.find((t) => t.id && t.id !== "speaking")?.id || "vocab";
    setKind(first);
    const start = index ?? meta.progress?.chunk_index ?? 0;
    await loadChunk(id, start, kinds);
  }

  async function loadChunk(id: string, index: number, tabList?: TabInfo[]) {
    const seq = ++loadSeq.current;
    const kinds = (tabList || tabs).map((t) => t.id || "").filter(Boolean);
    const data = await apiJson<ChunkResp>(`/api/intensive-reading/books/${id}/chunks/${index}`);
    let cache: { tabs?: Record<string, CachedSlot>; speaking?: SpeakingCache } = { tabs: {} };
    try {
      cache = await apiJson(`/api/intensive-reading/books/${id}/chunks/${data.chunk_index}/analysis`);
    } catch {
      cache = { tabs: {} };
    }
    if (seq !== loadSeq.current) return;
    const mapped = slotsFromCachedTabs(cache.tabs || {}, kinds, level, outLang);
    setChunk(data);
    setCachedTabs(cache.tabs || {});
    setSlots(mapped);
    const first = kinds.find((k) => k && k !== "speaking") || "vocab";
    setKind(pickTabWithText(kinds, mapped, first));
    const sp = { ...emptySpeaking(), ...(cache.speaking || {}) };
    setSpeaking(sp);
    setOral(sp.oral || "");
    setSpeakOut(speakOutFromCache(sp));
    await apiJson("/api/intensive-reading/progress", {
      method: "POST",
      body: JSON.stringify({ book_id: id, chunk_index: data.chunk_index, total: data.total }),
    }).catch(() => undefined);
  }

  function slotFor(k: string): Slot {
    return slots[k] || emptySlot();
  }

  async function runAnalyze(continueNext: boolean) {
    if (!openId || chunk?.chunk_index == null || kind === "speaking") return;
    const prev = slotFor(kind);
    let offset = 0;
    let part = 1;
    let previous = "";
    if (continueNext && prev.hasMore) {
      offset = prev.offset;
      part = prev.part + 1;
      previous = prev.text;
    } else if (continueNext) {
      offset = prev.lastOffset;
      part = prev.part;
      previous = prev.text;
    }
    setStreaming(true);
    setError("");
    let text = "";
    let saved: Slot | null = null;
    try {
      await apiSsePost(
        "/api/intensive-reading/analyze",
        {
          book_id: openId,
          chunk_index: chunk.chunk_index,
          analysis_kind: kind,
          offset,
          part,
          previous_analysis: previous,
          learner_level: level,
          output_lang: outLang,
          learner_reflection: prev.reflection,
          llm,
        },
        (event) => {
          if (event.type === "token" && typeof event.content === "string") {
            text += event.content;
            const live = continueNext && previous ? `${previous}\n\n---\n\n## Part ${part}\n\n${text}` : text;
            setSlots((s) => ({ ...s, [kind]: { ...(s[kind] || emptySlot()), text: live } }));
          } else if (event.type === "done") {
            const full = typeof event.content === "string" ? event.content : text;
            const live = continueNext && previous ? `${previous}\n\n---\n\n## Part ${part}\n\n${full}` : full;
            saved = {
              ...prev,
              text: live,
              hasMore: Boolean(event.has_more),
              offset: Number(event.next_offset || 0),
              part: Number(event.part || part),
              lastOffset: Number(event.offset || 0),
            };
            setSlots((s) => ({ ...s, [kind]: saved as Slot }));
          } else if (event.type === "error" && typeof event.content === "string") {
            setError(event.content);
          }
        },
      );
      if (saved) {
        await persistSlot(kind, saved).catch((e: Error) => setError(e.message));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStreaming(false);
    }
  }

  async function speak(exercise: string) {
    setSpeakOut("");
    setStreaming(true);
    let text = "";
    try {
      await apiSsePost(
        "/api/intensive-reading/speaking",
        {
          book_id: openId,
          chunk_index: chunk?.chunk_index,
          exercise,
          oral_text: oral,
          llm,
        },
        (event) => {
          if (event.type === "token" && typeof event.content === "string") {
            text += event.content;
            setSpeakOut(text);
          } else if (event.type === "error" && typeof event.content === "string") {
            setError(event.content);
          }
        },
      );
      const field = exercise === "cue" ? "cue" : exercise === "pressure" ? "pressure_attack" : "logic";
      const next = { ...speaking, oral, [field]: text, active_exercise: exercise };
      setSpeaking(next);
      await persistSpeaking(next).catch((e: Error) => setError(e.message));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStreaming(false);
    }
  }

  async function goChunk(index: number) {
    await persistCurrentBeforeLeave();
    await loadChunk(openId, index);
  }

  async function changeLearnerPref(nextLevel: string, nextLang: string) {
    const nextCache = await persistSlot(kind, slotFor(kind));
    setLevel(nextLevel);
    setOutLang(nextLang);
    const kinds = tabs.map((t) => t.id || "").filter(Boolean);
    setSlots(slotsFromCachedTabs(nextCache, kinds, nextLevel, nextLang));
  }

  const active = slotFor(kind);
  const canExplainAnalysis = analysisExplainEnabled(active.text, streaming);
  const metrics = passageMetrics(fontSize, focus);

  function enterFocus() {
    setAnalysisOpen(false);
    setFocus(true);
  }

  function exitFocus() {
    setFocus(false);
    setAnalysisOpen(false);
  }

  if (!openId) {
    return (
      <div className="h-full space-y-4 overflow-y-auto p-6">
        <h1 className="text-xl font-medium">Reading</h1>
        <div className="flex flex-wrap items-end gap-2">
          <input ref={fileRef} type="file" accept=".pdf,.epub" />
          <select
            className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
            value={bookType}
            onChange={(e) => setBookType(e.target.value)}
          >
            <option value="novel">Novel / Ebook</option>
            <option value="magazine">Magazine</option>
          </select>
          <Button size="sm" disabled={busy} onClick={() => void upload()}>
            Upload & Index
          </Button>
        </div>
        {error ? <p className="text-destructive text-sm">{error}</p> : null}
        <div className="space-y-2">
          {books.map((b) => (
            <Card key={b.book_id} size="sm">
              <CardHeader>
                <CardTitle className="text-sm">{b.title || b.book_id}</CardTitle>
              </CardHeader>
              <CardContent className="text-muted-foreground flex items-center justify-between gap-2 text-xs">
                <span>
                  {b.book_type} · {b.chunk_count || 0} chunks
                  {b.progress ? ` · chunk ${(b.progress.chunk_index || 0) + 1}` : ""}
                </span>
                <span className="flex gap-1">
                  <Button size="xs" onClick={() => void openBook(b.book_id, b.progress?.chunk_index)}>
                    Read
                  </Button>
                  <Button
                    size="xs"
                    variant="outline"
                    disabled={busy}
                    onClick={() =>
                      void apiJson(`/api/intensive-reading/books/${b.book_id}/reindex`, { method: "POST" }).then(loadBooks)
                    }
                  >
                    Re-index
                  </Button>
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={() =>
                      void apiJson(`/api/intensive-reading/books/${b.book_id}`, { method: "DELETE" }).then(loadBooks)
                    }
                  >
                    Delete
                  </Button>
                </span>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-2 p-3">
      <ExplainPopover
        enabled
        bookId={openId}
        bookTitle={books.find((b) => b.book_id === openId)?.title || ""}
        title={chunk?.title || ""}
        chunkIndex={chunk?.chunk_index}
        learnerLevel={level}
        llm={llm}
      />
      <div className="flex flex-wrap items-center gap-2">
        {focus ? (
          <Button size="sm" variant="outline" onClick={exitFocus}>
            ← 退出
          </Button>
        ) : (
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              void persistCurrentBeforeLeave().then(() => {
                setOpenId("");
                setChunk(null);
              });
            }}
          >
            ← Library
          </Button>
        )}
        <strong className="text-sm">{chunk?.title}</strong>
        <span className="text-muted-foreground text-xs">
          {(chunk?.chunk_index ?? 0) + 1} / {chunk?.total ?? "?"}
        </span>
        <span className="ml-auto flex flex-wrap items-center gap-1">
          {([18, 20, 22] as FontSize[]).map((size) => (
            <Button
              key={size}
              size="xs"
              variant={fontSize === size ? "default" : "outline"}
              onClick={() => setFontSize(parseFontSize(size))}
            >
              {size}
            </Button>
          ))}
          {focus ? (
            <Button size="xs" variant={analysisOpen ? "default" : "outline"} onClick={() => setAnalysisOpen((v) => !v)}>
              Analysis
            </Button>
          ) : (
            <Button size="xs" variant="outline" onClick={enterFocus}>
              Focus
            </Button>
          )}
        </span>
      </div>
      {error ? <p className="text-destructive text-xs">{error}</p> : null}
      {(() => {
        const passage = (
        <section className="border-border reading-paper flex h-full min-h-0 flex-col overflow-hidden rounded-xl border">
          <div className="text-muted-foreground flex items-center gap-2 border-b px-3 py-2 text-xs">
            <span>Passage · 选中词句后点「解释」</span>
            {toc.length > 0 ? (
              <div className="relative ml-auto">
                <Button size="xs" variant="outline" onClick={() => setShowToc((v) => !v)}>
                  {chunk?.book_type === "novel" ? "Chapters" : "Articles"} ▾
                </Button>
                {showToc ? (
                  <div className="bg-card absolute top-full right-0 z-20 mt-1 max-h-64 w-72 overflow-y-auto rounded-lg border p-1 shadow">
                    {toc.map((e) => (
                      <button
                        key={`${e.chunk_index}-${e.title}`}
                        type="button"
                        className={cn(
                          "block w-full truncate rounded px-2 py-1 text-left text-xs",
                          chunk?.chunk_index === e.chunk_index ? "bg-muted" : "hover:bg-muted/60",
                        )}
                        onClick={() => {
                          setShowToc(false);
                          void goChunk(e.chunk_index);
                        }}
                      >
                        {e.title || `Chunk ${e.chunk_index + 1}`}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
          <article
            data-explain-root="passage"
            className="reading-passage reading-paper flex-1 overflow-y-auto px-7 py-10 select-text"
            style={
              {
                "--reading-font-size": metrics.fontSize,
                "--reading-line-height": String(metrics.lineHeight),
              } as CSSProperties
            }
          >
            <div className="mx-auto" style={{ maxWidth: metrics.maxWidth }}>
              {(chunk?.chunk?.text || "").split(/\n\n+/).map((p, i) => (
                <p key={i} className="mb-[1em] indent-[1.25em]">
                  {p}
                </p>
              ))}
            </div>
          </article>
        </section>
        );
        const analysis = (
        <section
          className={cn(
            "border-border reading-paper flex h-full min-h-0 flex-col overflow-hidden rounded-xl border",
            focus && "absolute inset-y-0 right-0 z-20 w-[min(28rem,92vw)] shadow-xl",
            focus && !analysisOpen && "hidden",
          )}
        >
          <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2 text-xs">
            <span className="text-muted-foreground">Analysis · 选中后可「解释」</span>
            <span className="text-muted-foreground flex flex-wrap items-center gap-2">
              {ANALYSIS_LEGEND.map((item) => (
                <span key={item.id} className={cn("text-[11px]", `reading-legend-${item.id}`)}>
                  {item.label}·{item.hint}
                </span>
              ))}
            </span>
            <CloudModelSelect
              value={llm}
              disabled={streaming}
              onChange={(next) => {
                setLlm(next);
                localStorage.setItem("jarvis-reading-llm", next);
              }}
            />
            <label className="ml-auto flex items-center gap-1">
              难度
              <select
                className="border-input bg-background h-7 rounded border px-1"
                value={level}
                disabled={streaming}
                onChange={(e) => void changeLearnerPref(e.target.value, outLang)}
              >
                <option value="university">大学</option>
                <option value="high_school">高中</option>
                <option value="middle_school">初中</option>
              </select>
            </label>
          </div>
          <div className="flex flex-wrap gap-1 border-b p-2">
            {tabs.map((t) => (
              <Button
                key={t.id}
                size="xs"
                variant={kind === t.id ? "default" : "outline"}
                onClick={() => {
                  const next = t.id || "vocab";
                  if (next === kind) return;
                  void persistCurrentBeforeLeave().then(() => setKind(next));
                }}
              >
                {t.label || t.id}
              </Button>
            ))}
          </div>
          <div
            data-explain-root={canExplainAnalysis ? "analysis" : undefined}
            className="reading-analysis min-h-0 flex-1 overflow-y-auto p-3 text-sm select-text"
          >
            {kind === "speaking" ? (
              <div className="space-y-2">
                <Textarea value={oral} onChange={(e) => setOral(e.target.value)} placeholder="Type your spoken retelling…" />
                <div className="flex flex-wrap gap-1">
                  <Button size="xs" variant="outline" disabled={streaming} onClick={() => void speak("logic")}>
                    逻辑显形
                  </Button>
                  <Button size="xs" variant="outline" disabled={streaming} onClick={() => void speak("cue")}>
                    口语提词卡
                  </Button>
                  <Button size="xs" variant="outline" disabled={streaming} onClick={() => void speak("pressure")}>
                    压力测试
                  </Button>
                </div>
                {speakOut ? <div className="whitespace-pre-wrap">{speakOut}</div> : null}
              </div>
            ) : kind === "socratic" ? (
              <div className="space-y-2">
                <Textarea
                  value={active.reflection}
                  onChange={(e) =>
                    setSlots((s) => ({ ...s, socratic: { ...slotFor("socratic"), reflection: e.target.value } }))
                  }
                  placeholder="读后感 / reflection"
                />
                <div>{active.text || (streaming ? "…" : "写完读后感后点 Generate")}</div>
              </div>
            ) : active.text ? (
              <div dangerouslySetInnerHTML={{ __html: renderAnalysisHtml(active.text) }} />
            ) : (
              streaming ? "Generating…" : "点 Generate 生成本页分析（好词好句等）"
            )}
          </div>
          {kind !== "speaking" ? (
            <div className="flex flex-wrap items-center justify-end gap-2 border-t p-2">
              <label className="text-muted-foreground flex items-center gap-1 text-xs">
                语言
                <select
                  className="border-input bg-background h-7 rounded border px-1"
                  value={outLang}
                  disabled={streaming}
                  onChange={(e) => void changeLearnerPref(level, e.target.value)}
                >
                  <option value="zh">中文</option>
                  <option value="en">英文</option>
                </select>
              </label>
              <Button size="sm" disabled={streaming} onClick={() => void runAnalyze(false)}>
                Generate
              </Button>
              {active.hasMore ? (
                <Button size="sm" variant="outline" disabled={streaming} onClick={() => void runAnalyze(true)}>
                  Continue
                </Button>
              ) : null}
            </div>
          ) : null}
        </section>
        );
        if (focus) {
          return (
            <div className="relative grid min-h-0 flex-1 grid-cols-1 gap-3">
              {passage}
              {analysis}
            </div>
          );
        }
        return (
          <ResizablePanelGroup
            id="reading-split"
            orientation="horizontal"
            className="min-h-0 flex-1"
            defaultLayout={{ passage: splitPercent, analysis: 100 - splitPercent }}
            onLayoutChanged={(layout, meta) => {
              if (!meta.isUserInteraction) return;
              setSplitPercent(parseSplitPercent(layout.passage));
            }}
          >
            <ResizablePanel id="passage" minSize="30%" className="min-h-0">
              {passage}
            </ResizablePanel>
            <ResizableHandle withHandle className="mx-1" />
            <ResizablePanel id="analysis" minSize="25%" className="min-h-0">
              {analysis}
            </ResizablePanel>
          </ResizablePanelGroup>
        );
      })()}
      <div className="flex justify-end gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={!chunk?.has_prev || streaming}
          onClick={() => chunk?.prev_index != null && void goChunk(chunk.prev_index)}
        >
          Back
        </Button>
        <Button
          size="sm"
          disabled={!chunk?.has_next || streaming}
          onClick={() => chunk?.next_index != null && void goChunk(chunk.next_index)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
