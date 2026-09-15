import { useEffect, useState } from "react";
import { apiJson } from "@/lib/api";
import { pollJob } from "@/lib/jobs";
import { AUDIO_SOURCE_TYPES } from "@/lib/toolbar";
import { audioTranslateTarget } from "@/lib/dailyFetch";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type HistoryItem = { url?: string; display?: string; size_kb?: number; date?: string };
type AudioItem = {
  parent_title?: string;
  date?: string;
  chunk_count?: number;
  chunks?: { title?: string }[];
};
type AudioJob = {
  status?: string;
  error?: string;
  output_url?: string;
  items_found?: number;
  narration_length?: number;
  narration_preview?: string;
};

export function AudioKnowledgePanel() {
  const [step, setStep] = useState<1 | 2>(1);
  const [srcType, setSrcType] = useState("");
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [histDate, setHistDate] = useState("");
  const [items, setItems] = useState<AudioItem[]>([]);
  const [showDates, setShowDates] = useState(false);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [lang, setLang] = useState("zh");
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState("");
  const [resultUrl, setResultUrl] = useState("");
  const [preview, setPreview] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    apiJson<{ history?: HistoryItem[] }>("/api/toolbar/audio-knowledge/history")
      .then((d) => setHistory(d.history || []))
      .catch(() => setHistory([]));
    apiJson<{ audio_lang_knowledge?: string }>("/api/settings")
      .then((d) => {
        if (d.audio_lang_knowledge) setLang(d.audio_lang_knowledge);
      })
      .catch(() => undefined);
  }, []);

  async function next() {
    if (!srcType) {
      setError("Select a content source first");
      return;
    }
    setError("");
    setStep(2);
    setLoading(true);
    setResultUrl("");
    try {
      const data = await apiJson<{ items?: AudioItem[]; show_dates?: boolean }>(
        `/api/toolbar/audio-knowledge/items?type=${encodeURIComponent(srcType)}`,
      );
      const list = data.items || [];
      setItems(list);
      setShowDates(!!data.show_dates);
      const on: Record<string, boolean> = {};
      list.forEach((g) => {
        on[g.parent_title || ""] = true;
      });
      setPicked(on);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function generate() {
    const selectedParents = Object.keys(picked).filter((k) => picked[k] && k);
    if (!selectedParents.length) {
      setError("Select at least one item");
      return;
    }
    setError("");
    setProgress("Submitting request...");
    setResultUrl("");
    try {
      const started = await apiJson<{ job_id: string }>("/api/toolbar/audio-knowledge", {
        method: "POST",
        body: JSON.stringify({ item_type: srcType, selected_parents: selectedParents, language: lang }),
      });
      const done = await pollJob(
        () => apiJson<AudioJob>(`/api/toolbar/audio-knowledge/${started.job_id}`),
        (j) => {
          if (j.status === "searching") setProgress("Searching knowledge base...");
          else if (j.status === "searching_web") setProgress(`Found ${j.items_found || "?"} items. Searching web...`);
          else if (j.status === "generating_script") setProgress("Generating narration script (RAG + web)...");
          else if (j.status === "generating_audio") {
            setProgress(`Narration ready (${j.narration_length || "?"} chars). Generating audio...`);
          } else setProgress(j.status || "working…");
        },
        { intervalMs: 2000 },
      );
      if (done.error) throw new Error(done.error);
      setResultUrl(done.output_url || "");
      setPreview(done.narration_preview || "");
      setProgress("Audio generated!");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setProgress("");
    }
  }

  const shownHistory = histDate ? history.filter((h) => h.date === histDate) : history;
  const isBook = srcType === "book_chapter";
  const target = audioTranslateTarget(lang);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Audio from Knowledge</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {step === 1 ? (
          <>
            <p className="text-muted-foreground text-xs">Step 1: Choose a content source</p>
            <div className="space-y-1">
              {AUDIO_SOURCE_TYPES.map((t) => (
                <label key={t.id} className="flex items-center gap-2">
                  <input type="radio" name="audioSrc" checked={srcType === t.id} onChange={() => setSrcType(t.id)} />
                  {t.label}
                </label>
              ))}
            </div>
            <div className="flex justify-end">
              <Button size="sm" onClick={() => void next()}>
                Next
              </Button>
            </div>
            {history.length ? (
              <div className="space-y-2 border-t pt-3">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-muted-foreground text-xs">Previously generated audio</p>
                  <input
                    type="date"
                    className="border-input bg-background h-8 rounded-lg border px-2"
                    value={histDate}
                    onChange={(e) => setHistDate(e.target.value)}
                  />
                  <Button size="sm" variant="outline" onClick={() => setHistDate("")}>
                    All
                  </Button>
                </div>
                <div className="max-h-52 space-y-2 overflow-y-auto">
                  {shownHistory.length === 0 ? (
                    <p className="text-muted-foreground text-xs">No audio files for this date.</p>
                  ) : (
                    shownHistory.map((h) => (
                      <div key={h.url} className="flex items-center gap-2">
                        <audio controls preload="none" className="h-8 flex-1" src={h.url} />
                        <span className="text-muted-foreground text-xs whitespace-nowrap">{h.display}</span>
                        <span className="text-muted-foreground text-[10px]">{h.size_kb}KB</span>
                        {h.url ? (
                          <a className="text-primary text-xs" href={h.url} download>
                            Download
                          </a>
                        ) : null}
                      </div>
                    ))
                  )}
                </div>
              </div>
            ) : null}
          </>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={() => setStep(1)}>
                Back
              </Button>
              <p className="text-muted-foreground text-xs">
                Step 2: Select items from {AUDIO_SOURCE_TYPES.find((t) => t.id === srcType)?.label}
              </p>
            </div>
            {loading ? <p className="text-muted-foreground text-xs">Loading items…</p> : null}
            {!loading ? (
              <>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      const on: Record<string, boolean> = {};
                      items.forEach((g) => {
                        on[g.parent_title || ""] = true;
                      });
                      setPicked(on);
                    }}
                  >
                    Select All
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setPicked({})}>
                    Select None
                  </Button>
                  <span className="text-muted-foreground ml-auto text-xs">{items.length} items</span>
                </div>
                <div className="max-h-64 space-y-1 overflow-y-auto">
                  {items.length === 0 ? <p className="text-muted-foreground text-xs">No items found for this source type.</p> : null}
                  {items.map((g) =>
                    isBook && g.chunks?.length ? (
                      <div key={g.parent_title}>
                        <p className="font-medium">
                          {g.parent_title} ({g.chunks.length} chapters)
                        </p>
                        {g.chunks.map((ch) => (
                          <label key={ch.title} className="flex items-center gap-2 pl-4 text-xs">
                            <input
                              type="checkbox"
                              checked={!!picked[g.parent_title || ""]}
                              onChange={(e) => setPicked((p) => ({ ...p, [g.parent_title || ""]: e.target.checked }))}
                            />
                            {ch.title}
                          </label>
                        ))}
                      </div>
                    ) : (
                      <label key={g.parent_title} className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={!!picked[g.parent_title || ""]}
                          onChange={(e) => setPicked((p) => ({ ...p, [g.parent_title || ""]: e.target.checked }))}
                        />
                        {g.parent_title}
                        {showDates && g.date ? <span className="text-muted-foreground text-xs">({g.date})</span> : null}
                        <span className="text-muted-foreground text-xs">[{g.chunk_count} chunks]</span>
                      </label>
                    ),
                  )}
                </div>
                <label className="flex items-center gap-2">
                  Language
                  <select
                    className="border-input bg-background h-8 rounded-lg border px-2"
                    value={lang}
                    onChange={(e) => setLang(e.target.value)}
                  >
                    <option value="zh">Chinese (中文)</option>
                    <option value="en">English</option>
                  </select>
                </label>
                <Button size="sm" onClick={() => void generate()}>
                  Generate Audio
                </Button>
              </>
            ) : null}
            {progress ? <p className="text-muted-foreground text-xs">{progress}</p> : null}
            {resultUrl ? (
              <div className="space-y-2">
                <audio controls className="w-full" src={resultUrl} />
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <a className="text-primary" href={resultUrl} download>
                    Download MP3
                  </a>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setLang(target);
                      void generate();
                    }}
                  >
                    {target === "en" ? "→ EN" : "→ 中文"}
                  </Button>
                  {preview ? <span className="text-muted-foreground">Preview: {preview.slice(0, 200)}…</span> : null}
                </div>
              </div>
            ) : null}
          </>
        )}
        {error ? <p className="text-destructive text-sm">{error}</p> : null}
      </CardContent>
    </Card>
  );
}
