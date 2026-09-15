import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiJson } from "@/lib/api";
import { renderReportMarkdown } from "@/lib/dailyFetch";
import {
  TREND_CATEGORIES,
  buildExplainPrompt,
  stashPendingChat,
} from "@/lib/toolbar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export function ExplainThisForm() {
  const nav = useNavigate();
  const [topic, setTopic] = useState("");
  const [depth, setDepth] = useState<"quick" | "deep">("deep");
  const [web, setWeb] = useState(true);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Explain This — Deep Dive</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground text-xs">
          Enter a topic from AI news or tech. Jarvis will search the knowledge base and the web.
        </p>
        <Input value={topic} placeholder="e.g. LoRA fine-tuning, RLHF, FHIR R4..." onChange={(e) => setTopic(e.target.value)} />
        <div className="flex gap-4">
          <label className="flex items-center gap-2">
            <input type="radio" checked={depth === "quick"} onChange={() => setDepth("quick")} />
            Quick (2-3 min)
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" checked={depth === "deep"} onChange={() => setDepth("deep")} />
            Deep Dive (5-10 min)
          </label>
        </div>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={web} onChange={(e) => setWeb(e.target.checked)} />
          Also search the web for latest information
        </label>
        <Button
          disabled={!topic.trim()}
          onClick={() => {
            stashPendingChat({ prompt: buildExplainPrompt(topic.trim(), depth, web), autoSend: true });
            nav("/");
          }}
        >
          Explain
        </Button>
      </CardContent>
    </Card>
  );
}

export function TrendAnalysisForm() {
  const [cats, setCats] = useState<string[]>(TREND_CATEGORIES.map((c) => c.id));
  const [days, setDays] = useState(7);
  const [out, setOut] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function run() {
    if (!cats.length) {
      setStatus("Select at least one category");
      return;
    }
    setBusy(true);
    setOut("");
    setStatus(`Collecting data and streaming ${days}-day analysis via Ollama...`);
    try {
      const resp = await fetch("/api/toolbar/trend-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ categories: cats, days }),
      });
      if (!resp.ok || !resp.body) {
        const err = await resp.json().catch(() => ({}));
        throw new Error((err as { error?: string }).error || `HTTP ${resp.status}`);
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let rest = "";
      let full = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        rest += decoder.decode(value, { stream: true });
        const lines = rest.split("\n");
        rest = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const ev = JSON.parse(line.slice(6)) as { type?: string; content?: string; message?: string };
            if (ev.type === "token") {
              full += ev.content || "";
              setOut(full);
            } else if (ev.type === "done") {
              full = ev.content || full;
              setOut(full);
            } else if (ev.type === "error") {
              throw new Error(ev.message || "unknown");
            }
          } catch (e) {
            if (e instanceof SyntaxError) continue;
            throw e;
          }
        }
      }
      setStatus("");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Trend Analysis</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground text-xs">
          Select categories and a date window. Data comes from the RAG store, commit reports, and Atlassian daily markdown when Jira is selected.
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            {TREND_CATEGORIES.map((c) => (
              <label key={c.id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={cats.includes(c.id)}
                  onChange={(e) =>
                    setCats((prev) => (e.target.checked ? [...prev, c.id] : prev.filter((x) => x !== c.id)))
                  }
                />
                {c.label}
                {c.hint ? <span className="text-muted-foreground text-xs">({c.hint})</span> : null}
              </label>
            ))}
          </div>
          <div className="space-y-1">
            {[7, 14, 30].map((d) => (
              <label key={d} className="flex items-center gap-2">
                <input type="radio" checked={days === d} onChange={() => setDays(d)} />
                Last {d} days
              </label>
            ))}
          </div>
        </div>
        <Button size="sm" disabled={busy} onClick={() => void run()}>
          Analyze
        </Button>
        {status ? <p className="text-muted-foreground text-xs">{status}</p> : null}
        {out ? (
          <div
            className="bg-muted/40 max-h-96 overflow-auto rounded-xl border p-3 text-sm"
            dangerouslySetInnerHTML={{ __html: renderReportMarkdown(out) }}
          />
        ) : null}
      </CardContent>
    </Card>
  );
}

export function LearningModes() {
  const nav = useNavigate();
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function open(type: string, label: string) {
    setBusy(label);
    setError("");
    try {
      const freshStart = type === "english_learning" || type === "casual_english";
      const [sess, ctx] = await Promise.all([
        apiJson<{ id: string; messages?: unknown[] }>("/api/toolbar/learning-session", {
          method: "POST",
          body: JSON.stringify({ type }),
        }),
        apiJson<Record<string, unknown>>(`/api/toolbar/learning-context?type=${encodeURIComponent(type)}`),
      ]);
      if (freshStart && sess.id) {
        await apiJson(`/api/sessions/${sess.id}/clear`, { method: "POST" });
      }
      const welcome = buildLearningWelcome(type, ctx);
      if (welcome && (freshStart || !(sess.messages && sess.messages.length))) {
        await apiJson(`/api/sessions/${sess.id}/messages`, {
          method: "POST",
          body: JSON.stringify({ user_message: "", assistant_message: welcome }),
        });
      }
      stashPendingChat({ sessionId: sess.id });
      nav("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Learning</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground text-xs">Opens a dedicated learning session in Chat.</p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={!!busy} onClick={() => void open("ai_learning", "AI")}>
            AI Learning
          </Button>
          <Button size="sm" disabled={!!busy} onClick={() => void open("english_learning", "Tech English")}>
            Tech English
          </Button>
          <Button size="sm" disabled={!!busy} onClick={() => void open("casual_english", "Casual English")}>
            Casual English
          </Button>
          <Button size="sm" disabled={!!busy} onClick={() => void open("aws_cert", "AWS")}>
            AWS AIF-C01
          </Button>
        </div>
        {busy ? <p className="text-muted-foreground text-xs">Opening {busy}…</p> : null}
        {error ? <p className="text-destructive text-sm">{error}</p> : null}
      </CardContent>
    </Card>
  );
}

function buildLearningWelcome(type: string, ctx: Record<string, unknown>): string {
  if (type === "ai_learning") {
    const domains = (ctx.domains || []) as { domain?: string; category?: string; topic?: string; description?: string }[];
    if (!domains.length) return "";
    let msg = "## AI Learning — LLM, RAG & AI Engineering\n\n**7 Domains** covering the full AI/LLM engineering stack.\n\n### Study Categories\n\n";
    let lastDomain = "";
    let lastCategory = "";
    for (const d of domains) {
      if (d.domain !== lastDomain) {
        msg += `\n#### ${d.domain}\n\n`;
        lastDomain = d.domain || "";
        lastCategory = "";
      }
      if (d.category && d.category !== lastCategory) {
        msg += `**${d.category}**\n`;
        lastCategory = d.category;
      }
      msg += `- \`${d.topic}\`${d.description ? ` — ${d.description}` : ""}\n`;
    }
    msg += "\n---\n\nType `teach me RAG` or any AI/LLM topic to start a lesson.\n";
    return msg;
  }
  if (type === "english_learning") {
    const titles = (ctx.news_titles || []) as string[];
    let msg = "## Tech English Learning\n\nPick a topic and I will analyze the article for key phrases and how to discuss it in English.\n\n";
    if (titles.length) {
      msg += "### Recent AI news:\n\n";
      titles.slice(0, 20).forEach((t, i) => {
        msg += `${i + 1}. ${t}\n`;
      });
      msg += "\nType a number to pick a topic, or paste any text.\n";
    } else {
      msg += "No AI news topics available right now. Paste any text to practice.\n";
    }
    return msg;
  }
  if (type === "casual_english") {
    const items = (ctx.news_items || []) as { category?: string; title?: string }[];
    let msg = "## Casual English Learning\n\nEveryday phrases, idioms, and how native speakers would discuss the news.\n\n";
    if (items.length) {
      msg += "### Recent world news:\n\n";
      let lastCat = "";
      items.slice(0, 20).forEach((it, i) => {
        if (it.category !== lastCat) {
          msg += `\n**${it.category}**\n`;
          lastCat = it.category || "";
        }
        msg += `${i + 1}. ${it.title}\n`;
      });
      msg += "\nType a number, or write anything to practice.\n";
    } else {
      msg += "No world news topics right now. Write anything in English to practice.\n";
    }
    return msg;
  }
  if (type === "aws_cert") {
    const domains = (ctx.domains || []) as { domain?: string; topic?: string }[];
    let msg = "## AWS Certified AI Practitioner (AIF-C01)\n\n**Exam:** 65 questions | 90 min | Passing: 700/1000\n\n### Study Categories\n\n";
    let lastDomain = "";
    for (const d of domains) {
      if (d.domain !== lastDomain) {
        msg += `\n#### ${d.domain}\n\n`;
        lastDomain = d.domain || "";
      }
      if (d.topic) msg += `- ${d.topic}\n`;
    }
    msg += "\nType `teach me` plus a topic, `quiz`, or `progress`.\n";
    return msg;
  }
  return "";
}
