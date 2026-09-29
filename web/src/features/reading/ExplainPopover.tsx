import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { apiJson, apiSsePost } from "@/lib/api";
import { normalizeSelectionText } from "@/lib/selection";
import { canSaveExplainNote, formatExplainNote } from "@/lib/explainNote";
import { placeFixedNearRect } from "@/lib/placeFixedNearRect";
import { browserSpeakRate, normalizeSpeakRate, type SpeakRate } from "@/lib/speakRate";
import { Button } from "@/components/ui/button";

type Sel = {
  text: string;
  context: string;
  source: "passage" | "analysis";
  left: number;
  top: number;
  width: number;
  height: number;
  bottom: number;
};

export function ExplainPopover({
  enabled,
  bookId,
  bookTitle,
  title,
  chunkIndex,
  learnerLevel,
  llm,
}: {
  enabled: boolean;
  bookId: string;
  bookTitle?: string;
  title: string;
  chunkIndex?: number;
  learnerLevel: string;
  llm: "local" | "deepseek" | "glm" | "mimo";
}) {
  const [btn, setBtn] = useState<Sel | null>(null);
  const [open, setOpen] = useState(false);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [speakBusy, setSpeakBusy] = useState(false);
  const [speakHint, setSpeakHint] = useState("");
  const [noteHint, setNoteHint] = useState("");
  const [noteBusy, setNoteBusy] = useState(false);
  const [rate, setRate] = useState<SpeakRate>("slow");
  const saved = useRef<Sel | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const speakAbort = useRef<AbortController | null>(null);
  const speakGen = useRef(0);
  const btnRef = useRef<HTMLSpanElement | null>(null);
  const popRef = useRef<HTMLDivElement | null>(null);
  const btnPos = useNearRect(btn && !open ? btn : null, btnRef);
  const popPos = useNearRect(open && btn ? btn : null, popRef);

  const stopSpeak = useCallback(() => {
    speakGen.current += 1;
    speakAbort.current?.abort();
    speakAbort.current = null;
    audioRef.current?.pause();
    if (audioRef.current?.src) URL.revokeObjectURL(audioRef.current.src);
    audioRef.current = null;
    window.speechSynthesis?.cancel();
    setSpeakBusy(false);
    setSpeakHint("");
  }, []);

  useEffect(() => {
    if (!enabled) {
      stopSpeak();
      setBtn(null);
      setOpen(false);
      return;
    }
    function onSel() {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || !sel.rangeCount) {
        return;
      }
      const range = sel.getRangeAt(0);
      const root = rootFromRange(range);
      if (!root) {
        setBtn(null);
        return;
      }
      const text = normalizeSelectionText(sel.toString());
      if (!text) {
        setBtn(null);
        return;
      }
      let rect = range.getBoundingClientRect();
      if (!rect.width && !rect.height) {
        const rects = range.getClientRects();
        if (rects.length) rect = rects[0];
      }
      if (!rect.width && !rect.height) {
        setBtn(null);
        return;
      }
      setOpen(false);
      const next: Sel = {
        text,
        context: normalizeSelectionText(root.innerText || text, 8000),
        source: root.dataset.explainRoot === "analysis" ? "analysis" : "passage",
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
        bottom: rect.bottom,
      };
      saved.current = next;
      setBtn(next);
    }
    document.addEventListener("selectionchange", onSel);
    function onDocDown(e: MouseEvent) {
      const t = e.target as HTMLElement | null;
      if (t?.closest("[data-explain-ui]")) return;
      stopSpeak();
      setBtn(null);
      setOpen(false);
    }
    document.addEventListener("mousedown", onDocDown);
    return () => {
      document.removeEventListener("selectionchange", onSel);
      document.removeEventListener("mousedown", onDocDown);
      stopSpeak();
    };
  }, [enabled, stopSpeak]);

  async function explain() {
    const s = saved.current;
    if (!s) return;
    setOpen(true);
    setBody("解释中…");
    setBusy(true);
    setNoteHint("");
    let text = "";
    try {
      await apiSsePost(
        "/api/intensive-reading/explain-selection",
        {
          selected_text: s.text,
          context: s.context,
          book_id: bookId,
          title,
          source: s.source,
          learner_level: learnerLevel,
          llm,
        },
        (event) => {
          if (event.type === "token" && typeof event.content === "string") {
            text += event.content;
            setBody(text);
          } else if (event.type === "error" && typeof event.content === "string") {
            setBody(event.content);
          }
        },
      );
      if (!text.trim()) setBody("没有返回解释");
    } catch (e) {
      setBody(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function speak() {
    const s = saved.current?.text || "";
    if (!s) return;
    if (audioRef.current && !audioRef.current.paused) {
      stopSpeak();
      return;
    }
    if (window.speechSynthesis?.speaking) {
      window.speechSynthesis.cancel();
      return;
    }
    const chosen = normalizeSpeakRate(rate);
    const gen = speakGen.current + 1;
    speakGen.current = gen;
    speakAbort.current?.abort();
    const ac = new AbortController();
    speakAbort.current = ac;
    setSpeakBusy(true);
    setSpeakHint("生成语音…");
    let url = "";
    try {
      const resp = await fetch("/api/intensive-reading/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: s, rate: chosen }),
        signal: ac.signal,
      });
      if (!resp.ok) throw new Error("edge-tts");
      const blob = await resp.blob();
      url = URL.createObjectURL(blob);
      if (gen !== speakGen.current) {
        URL.revokeObjectURL(url);
        return;
      }
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => {
        URL.revokeObjectURL(url);
        audioRef.current = null;
      };
      setSpeakHint("");
      await audio.play();
    } catch (e) {
      if (url) URL.revokeObjectURL(url);
      if (gen !== speakGen.current) return;
      if (e instanceof DOMException && e.name === "AbortError") return;
      setSpeakHint("改用系统朗读");
      if (!window.speechSynthesis) return;
      const u = new SpeechSynthesisUtterance(s);
      u.lang = "en-US";
      u.rate = browserSpeakRate(chosen);
      window.speechSynthesis.speak(u);
    } finally {
      if (gen === speakGen.current) setSpeakBusy(false);
    }
  }

  async function saveNote() {
    const selected = saved.current?.text || "";
    if (!canSaveExplainNote({ explanation: body, busy }) || !selected) return;
    setNoteBusy(true);
    setNoteHint("");
    try {
      const note = formatExplainNote({
        selected,
        explanation: body,
        bookId,
        bookTitle,
        chunkTitle: title,
        chunkIndex,
      });
      await apiJson("/api/notes", {
        method: "POST",
        body: JSON.stringify(note),
      });
      setNoteHint("已保存");
    } catch (e) {
      setNoteHint(e instanceof Error ? e.message : String(e));
    } finally {
      setNoteBusy(false);
    }
  }

  if (!enabled) return null;

  return (
    <>
      {btn && !open ? (
        <span
          ref={btnRef}
          data-explain-ui="btn"
          className="fixed z-50"
          style={{
            left: btnPos.left,
            top: btnPos.top,
            visibility: btnPos.ready ? "visible" : "hidden",
          }}
        >
          <Button
            type="button"
            size="sm"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => void explain()}
          >
            解释
          </Button>
        </span>
      ) : null}
      {open && btn ? (
        <div
          ref={popRef}
          className="bg-card border-border fixed z-50 max-h-[50vh] w-[min(380px,92vw)] overflow-auto rounded-xl border p-3 text-sm shadow-lg"
          data-explain-ui="pop"
          style={{
            left: popPos.left,
            top: popPos.top,
            visibility: popPos.ready ? "visible" : "hidden",
          }}
        >
          <div className="mb-2 flex items-center justify-between gap-2 border-b pb-2 text-xs">
            <span className="text-muted-foreground shrink-0">选中文本解释</span>
            <span className="flex flex-wrap items-center justify-end gap-1">
              {(["slow", "medium", "fast"] as SpeakRate[]).map((item) => (
                <Button
                  key={item}
                  type="button"
                  size="xs"
                  variant={rate === item ? "default" : "ghost"}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => setRate(item)}
                >
                  {item === "slow" ? "慢" : item === "medium" ? "中" : "快"}
                </Button>
              ))}
              <Button type="button" size="xs" variant="ghost" disabled={speakBusy} onMouseDown={(e) => e.preventDefault()} onClick={() => void speak()}>
                {speakBusy ? "…" : "朗读"}
              </Button>
              <Button
                type="button"
                size="xs"
                variant="ghost"
                disabled={noteBusy || !canSaveExplainNote({ explanation: body, busy })}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => void saveNote()}
              >
                {noteBusy ? "…" : "加入笔记"}
              </Button>
              <Button
                type="button"
                size="xs"
                variant="ghost"
                onClick={() => {
                  setOpen(false);
                  stopSpeak();
                }}
              >
                ×
              </Button>
            </span>
          </div>
          <p className="text-muted-foreground mb-2 text-xs">“{saved.current?.text}”</p>
          {speakHint ? <p className="text-muted-foreground mb-2 text-xs">{speakHint}</p> : null}
          {noteHint ? <p className="text-muted-foreground mb-2 text-xs">{noteHint}</p> : null}
          <div className="whitespace-pre-wrap">{busy && !body ? "解释中…" : body}</div>
        </div>
      ) : null}
    </>
  );
}

function rootFromRange(range: Range): HTMLElement | null {
  const anc = range.commonAncestorContainer;
  const node = anc.nodeType === 3 ? anc.parentElement : (anc as HTMLElement);
  return node?.closest("[data-explain-root]") as HTMLElement | null;
}

function useNearRect(anchor: Sel | null, elRef: RefObject<HTMLElement | null>) {
  const [pos, setPos] = useState({ left: 0, top: 0, ready: false });

  useLayoutEffect(() => {
    if (!anchor) {
      setPos({ left: 0, top: 0, ready: false });
      return;
    }
    const el = elRef.current;
    if (!el) return;

    const apply = () => {
      const next = placeFixedNearRect(anchor, {
        width: el.offsetWidth,
        height: el.offsetHeight,
      });
      setPos((prev) =>
        prev.ready && prev.left === next.left && prev.top === next.top
          ? prev
          : { ...next, ready: true },
      );
    };

    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    window.addEventListener("resize", apply);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", apply);
    };
  }, [anchor, elRef]);

  return pos;
}
