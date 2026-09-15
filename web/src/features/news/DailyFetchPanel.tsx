import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { apiJson } from "@/lib/api";
import { pollJob } from "@/lib/jobs";
import {
  audioTranslateTarget,
  enabledSourceIdsForCategory,
  mdFilesOnly,
  parseLearningGuideDeepDives,
  pickFinanceCategory,
  refetchAudioSteps,
  renderReportMarkdown,
  type DeepDiveItem,
  type FinanceItem,
} from "@/lib/dailyFetch";
import { stashPendingChat } from "@/lib/toolbar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type DailyHistory = {
  date?: string;
  files?: { name: string; size_kb?: number }[];
  missing_steps?: string[];
  has_audio?: boolean;
  has_finance_audio?: boolean;
  finance_audio_files?: Record<string, boolean>;
  finance_categories?: { id: string; label?: string; audio_file?: string }[];
  audio_langs?: Record<string, string>;
  stats?: {
    ai_items?: number;
    ai_by_source?: Record<string, number>;
    finance_news_items?: number;
    finance_by_source?: Record<string, number>;
    finance_by_category?: Record<string, number>;
    finance_by_region?: Record<string, number>;
    jira_tickets?: number;
    confluence_pages?: number;
    wiki_pages?: number;
  };
};

type DailyJob = {
  status?: string;
  step?: string;
  steps?: { step?: string; exit_code?: number; output?: string }[];
  daily_summary?: string;
  error?: string;
};

type FnSource = { id: string; display?: string; category?: string; default_enabled?: boolean };

const STEP_LABELS: Record<string, string> = {
  fetch_sources: "Source Fetch",
  topic_dedup: "Topic Dedup",
  commit_report: "Commit Report",
  jira_daily: "Jira Report",
  wiki_fetch: "Wiki Fetch",
  finance_news_merge: "Finance News Merge",
  refetch_finance: "Finance News Fetch",
  finance_news_translate: "Finance News Translate",
  ai_audio: "AI Audio",
  finance_audio: "Finance Audio",
};

export function DailyFetchPanel() {
  const nav = useNavigate();
  const [hist, setHist] = useState<DailyHistory>({});
  const [error, setError] = useState("");
  const [job, setJob] = useState<DailyJob | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState("");
  const [sources, setSources] = useState<FnSource[]>([]);
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});
  const [preview, setPreview] = useState<ReactNode>(null);
  const [activeReport, setActiveReport] = useState("");
  const [audioBust, setAudioBust] = useState(0);
  const [diveBusy, setDiveBusy] = useState("");
  const [deepItems, setDeepItems] = useState<DeepDiveItem[]>([]);

  const load = useCallback(async (date?: string) => {
    const url = date
      ? `/api/toolbar/daily-fetch/history?date=${encodeURIComponent(date)}`
      : "/api/toolbar/daily-fetch/history";
    const data = await apiJson<DailyHistory>(url);
    setHist(data);
    setPreview(null);
    setActiveReport("");
    setDeepItems([]);
    setAudioBust(Date.now());
  }, []);

  const loadSources = useCallback(async () => {
    const data = await apiJson<{
      sources?: FnSource[];
      enabled?: string[];
    }>("/api/toolbar/finance-sources");
    setSources(data.sources || []);
    const on: Record<string, boolean> = {};
    (data.enabled || []).forEach((id) => {
      on[id] = true;
    });
    setEnabled(on);
  }, []);

  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
    loadSources().catch((e: Error) => setError(e.message));
  }, [load, loadSources]);

  async function runContinue(
    steps: string[],
    label: string,
    extra?: { lang_overrides?: Record<string, string>; finance_sources?: string[] },
  ) {
    if (!hist.date) return;
    setError("");
    setRunning(true);
    setProgress(label);
    setJob(null);
    try {
      const started = await apiJson<{ job_id: string }>("/api/toolbar/daily-fetch/continue", {
        method: "POST",
        body: JSON.stringify({
          steps,
          date: hist.date,
          ...(extra?.lang_overrides ? { lang_overrides: extra.lang_overrides } : {}),
          ...(extra?.finance_sources?.length ? { finance_sources: extra.finance_sources } : {}),
        }),
      });
      const done = await pollJob(
        () => apiJson<DailyJob>(`/api/toolbar/daily-fetch/${started.job_id}`),
        (st) => {
          setJob(st);
          setProgress(st.step || label);
        },
        { intervalMs: 4000 },
      );
      setJob(done);
      setProgress(done.status === "error" ? `Error: ${done.step || done.error || "unknown"}` : "Done");
      await load(hist.date);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setProgress("");
    } finally {
      setRunning(false);
    }
  }

  async function runToday() {
    setError("");
    setRunning(true);
    setProgress("Starting pipeline...");
    setJob(null);
    try {
      const started = await apiJson<{ job_id: string }>("/api/toolbar/daily-fetch", { method: "POST" });
      const done = await pollJob(
        () => apiJson<DailyJob>(`/api/toolbar/daily-fetch/${started.job_id}`),
        (st) => {
          setJob(st);
          setProgress(st.step || "Working...");
        },
      );
      setJob(done);
      setProgress(done.status === "error" ? `Error: ${done.step || done.error || "unknown"}` : "Complete");
      await load(new Date().toISOString().slice(0, 10));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setProgress("");
    } finally {
      setRunning(false);
    }
  }

  async function openFinanceCategory(catId: string, label: string) {
    if (!hist.date) return;
    setActiveReport(`fn:${catId}`);
    setDeepItems([]);
    setPreview(<p className="text-muted-foreground text-sm">Loading…</p>);
    try {
      const data = await apiJson<{ categories?: { category?: string; items?: FinanceItem[] }[] }>(
        `/api/toolbar/daily-fetch/finance-items/${encodeURIComponent(hist.date)}`,
      );
      const items = pickFinanceCategory(data, catId);
      if (!items.length) {
        setPreview(
          <p className="text-muted-foreground text-sm">
            No items in {label} for {hist.date}.
          </p>,
        );
        return;
      }
      setPreview(
        <div>
          <p className="mb-2 text-sm font-medium">
            {label} · {items.length}
          </p>
          <ul className="list-disc space-y-2 pl-5 text-sm">
            {items.map((it, i) => (
              <li key={`${it.url || it.title}-${i}`}>
                {it.url ? (
                  <a className="text-primary underline" href={it.url} target="_blank" rel="noreferrer">
                    {it.title}
                  </a>
                ) : (
                  <span>{it.title}</span>
                )}
                {it.source ? <span className="text-muted-foreground"> ({it.source})</span> : null}
              </li>
            ))}
          </ul>
        </div>,
      );
    } catch (e) {
      setPreview(<p className="text-destructive text-sm">{e instanceof Error ? e.message : String(e)}</p>);
    }
  }

  async function startDeepDive(item: DeepDiveItem) {
    setDiveBusy(item.title);
    setError("");
    try {
      const data = await apiJson<{ session_id?: string; error?: string }>("/api/toolbar/deep-dive", {
        method: "POST",
        body: JSON.stringify({
          title: item.title,
          source_url: item.sourceUrl || "",
          raw_file: item.rawFile || "",
        }),
      });
      if (!data.session_id) throw new Error(data.error || "Deep dive session missing");
      stashPendingChat({
        sessionId: data.session_id,
        prompt: "Please teach me about this topic.",
        autoSend: true,
      });
      nav("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDiveBusy("");
    }
  }

  async function openMdReport(filename: string) {
    if (!hist.date) return;
    setActiveReport(`md:${filename}`);
    setPreview(<p className="text-muted-foreground text-sm">Loading…</p>);
    try {
      const data = await apiJson<{ content?: string; error?: string }>(
        `/api/toolbar/report-content/${encodeURIComponent(hist.date)}/${encodeURIComponent(filename)}`,
      );
      if (data.error) {
        setPreview(<p className="text-destructive text-sm">{data.error}</p>);
        return;
      }
      const content = data.content || "";
      const html = renderReportMarkdown(content);
      setDeepItems(filename.startsWith("learning-guide") ? parseLearningGuideDeepDives(content) : []);
      setPreview(
        <div>
          <div className="text-muted-foreground mb-2 flex justify-between text-xs">
            <span>{filename}</span>
            <a
              className="text-primary"
              href={`/api/toolbar/audio-file/${encodeURIComponent(hist.date)}/${encodeURIComponent(filename)}`}
              download
            >
              Download
            </a>
          </div>
          <div className="text-sm leading-relaxed" dangerouslySetInnerHTML={{ __html: html }} />
        </div>,
      );
    } catch (e) {
      setPreview(<p className="text-destructive text-sm">{e instanceof Error ? e.message : String(e)}</p>);
    }
  }

  async function translateAudio(stepName: string, label: string, langKey: string) {
    const cur = hist.audio_langs?.[langKey] || "zh";
    const target = audioTranslateTarget(cur);
    const targetLabel = target === "en" ? "English" : "Chinese";
    try {
      await apiJson("/api/settings", {
        method: "POST",
        body: JSON.stringify({ [langKey]: target }),
      });
    } catch {
      /* settings save is best-effort, same as old UI */
    }
    await runContinue([stepName], `Translating ${label} to ${targetLabel}`, {
      lang_overrides: { [stepName]: target },
    });
  }

  const stats = hist.stats || {};
  const missing = hist.missing_steps || [];
  const hasFiles = (hist.files || []).length > 0;
  const mdFiles = mdFilesOnly(hist.files);
  const fcat = hist.finance_categories || [];
  const fcounts = stats.finance_by_category || {};
  const showHistory = Boolean(hist.date && hasFiles);
  const showContinue = missing.length > 0 && hasFiles;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Daily fetch</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground text-xs">Browse date</span>
        <input
          type="date"
          className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
          value={hist.date || ""}
          onChange={(e) => void load(e.target.value).catch((err: Error) => setError(err.message))}
        />
        <Button
          size="sm"
          variant="outline"
          disabled={!hist.date || running}
          onClick={() => hist.date && void load(shiftDate(hist.date, -1))}
        >
          Prev
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={!hist.date || running}
          onClick={() => hist.date && void load(shiftDate(hist.date, 1))}
        >
          Next
        </Button>
        <span className="text-sm font-medium">{hist.date || "No data"}</span>
      </div>

      {showHistory ? (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Stat label="AI News" value={stats.ai_items} suffix="items" breakdown={stats.ai_by_source} />
            <Stat
              label="Finance News"
              value={stats.finance_news_items}
              suffix="items"
              extra={regionLine(stats.finance_by_region)}
              breakdown={stats.finance_by_source}
            />
            <Stat label="Jira Tickets" value={stats.jira_tickets} />
            <Stat label="Confluence" value={stats.confluence_pages} suffix="pages" />
            <Stat label="Wiki Fetch" value={stats.wiki_pages} suffix="pages">
              <Button
                size="sm"
                variant="outline"
                className="mt-2"
                disabled={running}
                title="Re-run wiki fetch + change detection for all team members"
                onClick={() => void runContinue(["wiki_fetch"], "Refreshing & recreating wiki fetch")}
              >
                Refresh & Recreate
              </Button>
            </Stat>
          </div>

          {missing.length > 0 ? (
            <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 p-3 text-sm">
              <p className="mb-2 font-medium text-amber-500">Incomplete — missing steps:</p>
              <div className="flex flex-wrap gap-1">
                {missing.map((s) => (
                  <span key={s} className="rounded border border-amber-700/50 px-2 py-0.5 text-xs">
                    {STEP_LABELS[s] || s}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {hist.has_audio || hist.has_finance_audio ? (
            <div className="space-y-3">
              {hist.has_audio ? (
                <AudioBlock
                  title="AI Briefing Audio"
                  src={`/api/toolbar/audio-file/${hist.date}/ai-briefing.mp3`}
                  bust={audioBust}
                  lang={hist.audio_langs?.audio_lang_ai}
                  disabled={running}
                  onTranslate={() => void translateAudio("ai_audio", "AI Briefing", "audio_lang_ai")}
                  onRecreate={() => void runContinue(["ai_audio"], "Recreating AI Briefing audio")}
                  onRefetch={() =>
                    void runContinue(refetchAudioSteps("ai_audio"), "Refetching & recreating AI Briefing audio")
                  }
                />
              ) : null}
              {hist.has_finance_audio
                ? fcat.map((c) =>
                    c.audio_file ? (
                      <AudioBlock
                        key={c.id}
                        title={c.label || c.id}
                        src={
                          hist.finance_audio_files?.[c.id]
                            ? `/api/toolbar/audio-file/${hist.date}/${c.audio_file}`
                            : undefined
                        }
                        bust={audioBust}
                        lang={hist.audio_langs?.audio_lang_finance}
                        disabled={running}
                        onTranslate={() =>
                          void translateAudio(`fn_audio:${c.id}`, c.label || c.id, "audio_lang_finance")
                        }
                        onRecreate={() =>
                          void runContinue([`fn_audio:${c.id}`], `Recreating ${c.label || c.id} audio`)
                        }
                        onRefetch={() =>
                          void runContinue(
                            [
                              "refetch_finance",
                              "finance_news_merge",
                              "finance_news_translate",
                              `fn_audio:${c.id}`,
                            ],
                            `Refetching ${c.label || c.id}`,
                            { finance_sources: enabledSourceIdsForCategory(sources, enabled, c.id) },
                          )
                        }
                      />
                    ) : null,
                  )
                : null}
            </div>
          ) : null}

          {mdFiles.length > 0 || fcat.length > 0 ? (
            <div className="space-y-2">
              <p className="text-muted-foreground text-xs">Reports</p>
              <div className="flex flex-wrap gap-1">
                {mdFiles.map((f) => (
                  <Button
                    key={f.name}
                    size="sm"
                    variant={activeReport === `md:${f.name}` ? "default" : "outline"}
                    title={`${f.size_kb} KB`}
                    onClick={() => void openMdReport(f.name)}
                  >
                    {f.name}
                  </Button>
                ))}
                {fcat.map((c) => (
                  <Button
                    key={c.id}
                    size="sm"
                    variant={activeReport === `fn:${c.id}` ? "default" : "outline"}
                    onClick={() => void openFinanceCategory(c.id, c.label || c.id)}
                  >
                    {c.label || c.id} ({fcounts[c.id] || 0})
                  </Button>
                ))}
              </div>
              {deepItems.length ? (
                <div className="flex flex-wrap gap-1">
                  {deepItems.map((item) => (
                    <Button
                      key={`${item.title}-${item.rawFile || ""}`}
                      size="xs"
                      variant="outline"
                      disabled={!!diveBusy}
                      title="Start a deep-dive learning session for this topic"
                      onClick={() => void startDeepDive(item)}
                    >
                      {diveBusy === item.title ? "Creating…" : `Deep Dive · ${item.title}`}
                    </Button>
                  ))}
                </div>
              ) : null}
              {preview ? (
                <div className="bg-muted/40 max-h-[40vh] overflow-y-auto rounded-xl border p-4">{preview}</div>
              ) : null}
            </div>
          ) : null}
        </>
      ) : (
        <p className="text-muted-foreground py-6 text-center text-sm">No reports found for this date.</p>
      )}

      <div className="flex flex-wrap items-center justify-end gap-2 border-t pt-3">
        {showContinue ? (
          <Button
            size="sm"
            variant="outline"
            disabled={running}
            onClick={() => void runContinue(missing, `Continuing: ${missing.join(", ")}`)}
          >
            Continue ({missing.length})
          </Button>
        ) : null}
        <Button size="sm" disabled={running} onClick={() => void runToday()}>
          Run Today's Fetch
        </Button>
      </div>

      {progress || job ? (
        <div className="bg-muted/40 rounded-xl border p-3 text-sm">
          <p>{progress || job?.status}</p>
          {(job?.steps || []).map((s) => (
            <div key={s.step} className="text-muted-foreground text-xs">
              {s.exit_code === 0 ? "✓" : "✗"} {s.step}
              {s.exit_code === 0 ? "" : ` — ${(s.output || "").slice(0, 80)}`}
            </div>
          ))}
          {job?.daily_summary ? (
            <pre className="mt-2 max-h-48 overflow-auto text-xs whitespace-pre-wrap">{job.daily_summary}</pre>
          ) : null}
        </div>
      ) : null}
      {error ? <p className="text-destructive text-sm">{error}</p> : null}
      </CardContent>
    </Card>
  );
}

function Stat({
  label,
  value,
  suffix,
  extra,
  breakdown,
  children,
}: {
  label: string;
  value?: number;
  suffix?: string;
  extra?: string;
  breakdown?: Record<string, number>;
  children?: ReactNode;
}) {
  const keys = Object.keys(breakdown || {}).sort((a, b) => (breakdown?.[b] || 0) - (breakdown?.[a] || 0));
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="text-muted-foreground text-xs uppercase">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-lg font-medium">
          {value ?? 0}
          {suffix ? <span className="text-muted-foreground ml-1 text-xs font-normal">{suffix}</span> : null}
        </p>
        {extra ? <p className="text-muted-foreground mt-1 text-[11px]">{extra}</p> : null}
        {breakdown ? (
          keys.length ? (
            <div className="mt-2 space-y-0.5 border-t pt-1">
              {keys.map((k) => (
                <div key={k} className="text-muted-foreground flex justify-between text-[11px]">
                  <span className="truncate pr-2">{k}</span>
                  <span>{breakdown[k]}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground mt-1 text-[11px] italic">No sources</p>
          )
        ) : null}
        {children}
      </CardContent>
    </Card>
  );
}

function AudioBlock({
  title,
  src,
  bust,
  lang,
  disabled,
  onTranslate,
  onRecreate,
  onRefetch,
}: {
  title: string;
  src?: string;
  bust: number;
  lang?: string;
  disabled?: boolean;
  onTranslate: () => void;
  onRecreate: () => void;
  onRefetch: () => void;
}) {
  const target = audioTranslateTarget(lang);
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <p className="text-xs font-medium">{title}</p>
        <Button size="sm" variant="outline" disabled={disabled} title={`Regenerate in ${target === "en" ? "English" : "Chinese"}`} onClick={onTranslate}>
          {target === "en" ? "→ EN" : "→ 中文"}
        </Button>
        <Button size="sm" variant="outline" disabled={disabled} title="Regenerate audio from existing data" onClick={onRecreate}>
          Recreate
        </Button>
        <Button size="sm" variant="outline" disabled={disabled} title="Re-fetch sources then recreate audio" onClick={onRefetch}>
          Refetch & Recreate
        </Button>
      </div>
      {src ? <audio controls className="w-full" src={`${src}?t=${bust}`} /> : null}
    </div>
  );
}

function regionLine(fr?: Record<string, number>) {
  if (!fr) return "";
  return `US ${fr.us || 0} · APAC ${fr.apac || 0} · CN ${fr.china || 0}`;
}

function shiftDate(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}
