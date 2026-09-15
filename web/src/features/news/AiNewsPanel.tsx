import { useCallback, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";
import { isTerminalJobStatus, pollJob } from "@/lib/jobs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type KbItem = {
  date?: string;
  title?: string;
  category?: string;
  source?: string;
  summary?: string;
  url?: string;
};

type AudioJob = { status?: string; error?: string; output_url?: string };

export function AiNewsPanel() {
  const [items, setItems] = useState<KbItem[]>([]);
  const [audios, setAudios] = useState<Record<string, string>>({});
  const [total, setTotal] = useState(0);
  const [scanned, setScanned] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [audioBusy, setAudioBusy] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [src, setSrc] = useState("");
  const [open, setOpen] = useState<number | null>(null);

  const load = useCallback(async () => {
    const data = await apiJson<{ items: KbItem[]; total?: number; last_scanned?: string }>("/api/toolbar/ai-news-kb");
    setItems(data.items || []);
    setTotal(data.total || (data.items || []).length);
    setScanned(data.last_scanned || "");
  }, []);

  const loadAudios = useCallback(async () => {
    const data = await apiJson<{ audios?: Record<string, string> }>("/api/toolbar/ai-news-kb/article-audios");
    setAudios(data.audios || {});
  }, []);

  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
    loadAudios().catch(() => undefined);
  }, [load, loadAudios]);

  async function scan() {
    setBusy(true);
    setError("");
    try {
      await apiJson("/api/toolbar/ai-news-kb/scan", { method: "POST" });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function generateAudio(it: KbItem, lang?: "zh" | "en") {
    const key = `${it.title || ""}:${lang || "bilingual"}`;
    setAudioBusy(key);
    const langLabel = lang === "zh" ? " (中文)" : lang === "en" ? " (EN)" : " (bilingual)";
    setStatus(`Generating audio${langLabel} for: ${(it.title || "").slice(0, 50)}…`);
    try {
      const payload: Record<string, string> = {
        title: it.title || "",
        summary: it.summary || "",
        url: it.url || "",
        source: it.source || "",
      };
      if (lang) payload.language = lang;
      const started = await apiJson<{ job_id?: string; error?: string }>("/api/toolbar/ai-news-kb/article-audio", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!started.job_id) throw new Error(started.error || "No job_id");
      const done = await pollJob(
        () => apiJson<AudioJob>(`/api/toolbar/audio-knowledge/${started.job_id}`),
        (job) => {
          if (!isTerminalJobStatus(job.status)) setStatus(job.status || "Working…");
        },
        { intervalMs: 5000 },
      );
      if (done.error) throw new Error(done.error);
      if (done.output_url && it.title) {
        const title = it.title;
        const url = done.output_url;
        setAudios((prev) => ({ ...prev, [title]: url }));
      }
      setStatus("Audio ready");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("");
    } finally {
      setAudioBusy("");
    }
  }

  async function sendTelegram(audioUrl: string, title: string) {
    setStatus("Sending to Telegram…");
    try {
      await apiJson("/api/toolbar/ai-news-kb/send-telegram", {
        method: "POST",
        body: JSON.stringify({ audio_url: audioUrl, title }),
      });
      setStatus("Sent to Telegram");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("");
    }
  }

  const cats = Array.from(new Set(items.map((i) => i.category).filter(Boolean))) as string[];
  const srcs = Array.from(new Set(items.map((i) => i.source).filter(Boolean))) as string[];
  const filtered = items.filter((it) => {
    if (cat && it.category !== cat) return false;
    if (src && it.source !== src) return false;
    if (q) {
      const blob = `${it.title} ${it.summary} ${it.source}`.toLowerCase();
      if (!blob.includes(q.toLowerCase())) return false;
    }
    return true;
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>AI news</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={busy} onClick={() => void scan()}>
          Scan KB
        </Button>
        <span className="text-muted-foreground text-xs">
          {total} items{scanned ? ` · last scan ${scanned}` : ""}
        </span>
        <input
          className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
          placeholder="Filter keyword"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select className="border-input bg-background h-8 rounded-lg border px-2 text-sm" value={cat} onChange={(e) => setCat(e.target.value)}>
          <option value="">All Categories</option>
          {cats.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select className="border-input bg-background h-8 rounded-lg border px-2 text-sm" value={src} onChange={(e) => setSrc(e.target.value)}>
          <option value="">All Sources</option>
          {srcs.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      {status ? <p className="text-muted-foreground text-xs">{status}</p> : null}
      {error ? <p className="text-destructive text-sm">{error}</p> : null}
      <div className="space-y-2">
        {filtered.slice(0, 80).map((it, i) => {
          const audioUrl = it.title ? audios[it.title] : "";
          const busyKey = `${it.title || ""}:`;
          return (
            <Card key={`${it.date}-${it.title}-${i}`} size="sm">
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center gap-2">
                  <button type="button" className="text-left" onClick={() => setOpen(open === i ? null : i)}>
                    {it.title || "(untitled)"}
                  </button>
                  {it.url ? (
                    <a className="text-primary text-xs" href={it.url} target="_blank" rel="noreferrer">
                      link
                    </a>
                  ) : null}
                  <span className="ml-auto flex flex-wrap gap-1">
                    {audioUrl ? (
                      <>
                        <audio controls className="h-8 max-w-48" src={audioUrl} />
                        <Button size="xs" variant="outline" title="Regenerate in Chinese" disabled={!!audioBusy} onClick={() => void generateAudio(it, "zh")}>
                          →中文
                        </Button>
                        <Button size="xs" variant="outline" title="Regenerate in English" disabled={!!audioBusy} onClick={() => void generateAudio(it, "en")}>
                          → EN
                        </Button>
                        <Button size="xs" variant="outline" title="Regenerate (bilingual)" disabled={!!audioBusy} onClick={() => void generateAudio(it)}>
                          ↻
                        </Button>
                        <Button size="xs" variant="outline" title="Send to Telegram" onClick={() => void sendTelegram(audioUrl, it.title || "")}>
                          TG
                        </Button>
                      </>
                    ) : (
                      <Button
                        size="xs"
                        variant="outline"
                        disabled={!!audioBusy}
                        title="Generate deep-dive audio (bilingual)"
                        onClick={() => void generateAudio(it)}
                      >
                        {audioBusy.startsWith(busyKey) ? "…" : "🎧"}
                      </Button>
                    )}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="text-muted-foreground text-xs">
                {[it.date, it.category, it.source].filter(Boolean).join(" · ")}
                {open === i && it.summary ? <p className="mt-1">{it.summary}</p> : it.summary ? <p className="mt-1 line-clamp-2">{it.summary}</p> : null}
              </CardContent>
            </Card>
          );
        })}
      </div>
      </CardContent>
    </Card>
  );
}
