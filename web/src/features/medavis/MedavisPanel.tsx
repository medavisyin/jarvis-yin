import { useState, type ReactNode } from "react";
import { apiJson } from "@/lib/api";
import { pollJob } from "@/lib/jobs";
import { renderReportMarkdown } from "@/lib/dailyFetch";
import {
  COMMIT_USERS,
  PROJECT_QUICK_ASKS,
  WIKI_USERS,
  buildCommitChatPrompt,
  buildJiraChatPrompt,
  buildTeamActivityChatPrompt,
  dateRangeLabel,
  defaultDateRange,
  memberDefaults,
  monthAgoRange,
  selectedValues,
  stashPendingChat,
  type Member,
} from "@/lib/toolbar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useNavigate } from "react-router-dom";
import type { MedavisTabId } from "@/lib/medavisTabs";

type ToolbarJob = { status?: string; progress?: string; result?: string; error?: string };

export function MedavisTool({ tool }: { tool: MedavisTabId }) {
  return (
    <>
      {tool === "wiki" ? <WikiFetchForm /> : null}
      {tool === "jira" ? <JiraDailyForm /> : null}
      {tool === "commit" ? <CommitSummaryForm /> : null}
      {tool === "platform" ? <PlatformUpdatesForm /> : null}
      {tool === "activity" ? <TeamActivityForm /> : null}
      {tool === "projects" ? <ProjectsForm /> : null}
    </>
  );
}

function WikiFetchForm() {
  const range0 = monthAgoRange();
  const [picked, setPicked] = useState(memberDefaults(WIKI_USERS));
  const [from, setFrom] = useState(range0.from);
  const [to, setTo] = useState(range0.to);
  return (
    <JobForm
      title="Wiki Fetch — Select Team Members"
      hint="Select users whose Confluence wiki pages to fetch and index into RAG."
      actionLabel="Fetch Selected"
      run={async (setLog) => {
        const users = selectedValues(picked);
        if (!users.length) throw new Error("Select at least one team member");
        const started = await apiJson<{ job_id: string }>("/api/toolbar/wiki-fetch", {
          method: "POST",
          body: JSON.stringify({ users, date_from: from, date_to: to }),
        });
        const done = await pollJob(
          () => apiJson<ToolbarJob>(`/api/toolbar/wiki-fetch/${started.job_id}`),
          (j) => setLog(j.progress || j.status || "working…"),
          { intervalMs: 3000 },
        );
        if (done.status === "error") throw new Error(done.error || done.result || "Wiki fetch failed");
        return done.result || "Wiki fetch complete.";
      }}
    >
      <MemberChecklist members={WIKI_USERS} picked={picked} setPicked={setPicked} />
      <DateRange from={from} to={to} setFrom={setFrom} setTo={setTo} />
    </JobForm>
  );
}

function JiraDailyForm() {
  const nav = useNavigate();
  return (
    <JobForm
      title="Jira Daily"
      hint="Runs the Jira/Confluence daily report, then you can send it to Chat for a team summary."
      actionLabel="Run Jira report"
      run={async () => {
        const data = await apiJson<{ result?: string }>("/api/toolbar/jira-report", { method: "POST" });
        const report = data.result || "";
        if (!report) throw new Error("Jira report returned empty — check if Atlassian API is reachable");
        return report;
      }}
      onDone={(report) => (
        <Button
          size="sm"
          className="mt-2"
          onClick={() => {
            stashPendingChat({ report, prompt: buildJiraChatPrompt(), autoSend: true });
            nav("/");
          }}
        >
          Summarize in Chat
        </Button>
      )}
    />
  );
}

function CommitSummaryForm() {
  const nav = useNavigate();
  const range0 = defaultDateRange(2);
  const [picked, setPicked] = useState(memberDefaults(COMMIT_USERS));
  const [from, setFrom] = useState(range0.from);
  const [to, setTo] = useState(range0.to);
  return (
    <JobForm
      title="Commit Summary — Options"
      hint="Select team members and date range for the commit summary."
      actionLabel="Generate Summary"
      run={async () => {
        const authors = selectedValues(picked);
        if (!authors.length) throw new Error("Select at least one team member");
        const data = await apiJson<{ result?: string }>("/api/toolbar/commit-summary", {
          method: "POST",
          body: JSON.stringify({ since_date: from, until_date: to, authors }),
        });
        return data.result || "No commits found.";
      }}
      onDone={(report) => (
        <Button
          size="sm"
          className="mt-2"
          onClick={() => {
            stashPendingChat({
              report,
              prompt: buildCommitChatPrompt(selectedValues(picked), dateRangeLabel(from, to)),
              autoSend: true,
            });
            nav("/");
          }}
        >
          Analyze in Chat
        </Button>
      )}
    >
      <MemberChecklist members={COMMIT_USERS} picked={picked} setPicked={setPicked} />
      <DateRange from={from} to={to} setFrom={setFrom} setTo={setTo} />
    </JobForm>
  );
}

function PlatformUpdatesForm() {
  const range0 = defaultDateRange(7);
  const [from, setFrom] = useState(range0.from);
  const [to, setTo] = useState(range0.to);
  const [platform, setPlatform] = useState("radiology");
  return (
    <JobForm
      title="Platform Updates — Options"
      hint="Task-based summary of work merged to master. Radiology groups backend + frontend by JIRA key."
      actionLabel="Generate Summary"
      run={async (setLog) => {
        const started = await apiJson<{ job_id: string }>("/api/toolbar/platform-updates", {
          method: "POST",
          body: JSON.stringify({ platform, date_from: from, date_to: to }),
        });
        const done = await pollJob(
          () => apiJson<ToolbarJob>(`/api/toolbar/platform-updates/${started.job_id}`),
          (j) => setLog(j.progress || j.status || "working…"),
          { intervalMs: 3000 },
        );
        if (done.status === "error") throw new Error(done.error || done.result || "Platform updates failed");
        return done.result || "No updates.";
      }}
    >
      <label className="block text-sm">
        Platform
        <select
          className="border-input bg-background mt-1 h-8 w-full rounded-lg border px-2 text-sm"
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
        >
          <option value="radiology">Radiology Platform</option>
        </select>
      </label>
      <DateRange from={from} to={to} setFrom={setFrom} setTo={setTo} />
    </JobForm>
  );
}

function TeamActivityForm() {
  const nav = useNavigate();
  const range0 = defaultDateRange(7);
  const [picked, setPicked] = useState(memberDefaults(COMMIT_USERS));
  const [from, setFrom] = useState(range0.from);
  const [to, setTo] = useState(range0.to);
  return (
    <JobForm
      title="Team Activity — Options"
      hint="Select team members and date range. Commits are fetched here; Jira/wiki activity is asked in Chat."
      actionLabel="Generate Report"
      run={async () => {
        const authors = selectedValues(picked);
        if (!authors.length) throw new Error("Select at least one team member");
        const data = await apiJson<{ result?: string }>("/api/toolbar/commit-summary", {
          method: "POST",
          body: JSON.stringify({ since_date: from, until_date: to, authors }),
        });
        return data.result || "";
      }}
      onDone={(report) => (
        <Button
          size="sm"
          className="mt-2"
          onClick={() => {
            stashPendingChat({
              report,
              prompt: buildTeamActivityChatPrompt(selectedValues(picked), dateRangeLabel(from, to), !!report),
              autoSend: true,
            });
            nav("/");
          }}
        >
          Continue in Chat
        </Button>
      )}
    >
      <MemberChecklist members={COMMIT_USERS} picked={picked} setPicked={setPicked} />
      <DateRange from={from} to={to} setFrom={setFrom} setTo={setTo} />
    </JobForm>
  );
}

function ProjectsForm() {
  const nav = useNavigate();
  const [query, setQuery] = useState("");
  const [deep, setDeep] = useState(false);
  function ask(q: string) {
    if (!q.trim()) return;
    stashPendingChat({ prompt: q, autoSend: true, useDeep: deep });
    nav("/");
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Projects Intelligence</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground text-xs">
          Ask deep questions about MEDAVIS project architecture, dependencies, and code.
        </p>
        <div className="flex flex-col gap-2">
          {PROJECT_QUICK_ASKS.map((p) => (
            <Button key={p.label} variant="outline" className="h-auto justify-start py-2 text-left" onClick={() => ask(p.query)}>
              {p.label}
            </Button>
          ))}
        </div>
        <label className="block">
          Or ask your own project question
          <div className="mt-1 flex gap-2">
            <Input
              value={query}
              placeholder="e.g. How does P4M connect to Admin App?"
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") ask(query.trim());
              }}
            />
            <Button onClick={() => ask(query.trim())} disabled={!query.trim()}>
              Ask
            </Button>
          </div>
        </label>
        <label className="flex items-center gap-2 text-xs">
          <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} />
          Use qwen3:8b (deep) for complex questions
        </label>
      </CardContent>
    </Card>
  );
}

function JobForm({
  title,
  hint,
  actionLabel,
  run,
  children,
  onDone,
}: {
  title: string;
  hint: string;
  actionLabel: string;
  run: (setLog: (s: string) => void) => Promise<string>;
  children?: ReactNode;
  onDone?: (result: string) => ReactNode;
}) {
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState("");
  const [result, setResult] = useState("");
  const [error, setError] = useState("");

  async function go() {
    setBusy(true);
    setError("");
    setResult("");
    setLog("starting…");
    try {
      const out = await run(setLog);
      setResult(out);
      setLog("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLog("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground text-xs">{hint}</p>
        {children}
        <div className="flex justify-end gap-2">
          <Button size="sm" disabled={busy} onClick={() => void go()}>
            {actionLabel}
          </Button>
        </div>
        {log ? <p className="text-muted-foreground text-xs">{log}</p> : null}
        {error ? <p className="text-destructive text-sm">{error}</p> : null}
        {result ? (
          <div>
            <div
              className="bg-muted/40 max-h-96 overflow-auto rounded-xl border p-3 text-sm"
              dangerouslySetInnerHTML={{ __html: renderReportMarkdown(result) }}
            />
            {onDone ? onDone(result) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function MemberChecklist({
  members,
  picked,
  setPicked,
}: {
  members: Member[];
  picked: Record<string, boolean>;
  setPicked: (next: Record<string, boolean>) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="max-h-56 space-y-1 overflow-y-auto text-sm">
        {members.map((m) => (
          <label key={m.id} className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={!!picked[m.id]}
              onChange={(e) => setPicked({ ...picked, [m.id]: e.target.checked })}
            />
            {m.label}
          </label>
        ))}
      </div>
      <div className="flex gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            const next: Record<string, boolean> = {};
            members.forEach((m) => {
              next[m.id] = true;
            });
            setPicked(next);
          }}
        >
          Select All
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            const next: Record<string, boolean> = {};
            members.forEach((m) => {
              next[m.id] = false;
            });
            setPicked(next);
          }}
        >
          None
        </Button>
      </div>
    </div>
  );
}

function DateRange({
  from,
  to,
  setFrom,
  setTo,
}: {
  from: string;
  to: string;
  setFrom: (v: string) => void;
  setTo: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <label className="flex items-center gap-2">
        From
        <input
          type="date"
          className="border-input bg-background h-8 rounded-lg border px-2"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
      </label>
      <label className="flex items-center gap-2">
        To
        <input
          type="date"
          className="border-input bg-background h-8 rounded-lg border px-2"
          value={to}
          onChange={(e) => setTo(e.target.value)}
        />
      </label>
    </div>
  );
}
