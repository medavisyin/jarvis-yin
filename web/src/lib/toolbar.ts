export type Member = { id: string; label: string; defaultOn?: boolean };

export const WIKI_USERS: Member[] = [
  { id: "Rong Yin", label: "Rong Yin", defaultOn: true },
  { id: "Raymond Shen", label: "Raymond Shen" },
  { id: "Charlotte Jiang", label: "Charlotte Jiang" },
  { id: "Christoph Scheben", label: "Christoph Scheben" },
  { id: "Tobias Troesch", label: "Tobias Troesch" },
  { id: "Jan Loeffler", label: "Jan Loeffler (CTO)" },
  { id: "Belen Liu", label: "Belen Liu" },
  { id: "Eason Li", label: "Eason Li" },
  { id: "Johnny Yang", label: "Johnny Yang" },
  { id: "Bin Si", label: "Bin Si" },
  { id: "Deniz Erginos", label: "Deniz Erginos" },
  { id: "Djilija Vranic", label: "Djilija Vranic" },
  { id: "Dominik Kowalski", label: "Dominik Kowalski" },
  { id: "Eatin Yang", label: "Eatin Yang" },
  { id: "Ehsan Esmaili", label: "Ehsan Esmaili" },
  { id: "Emrys MacInally", label: "Emrys MacInally" },
  { id: "Erik Zweier", label: "Erik Zweier" },
  { id: "Holger Pflüger", label: "Holger Pflüger" },
  { id: "Martin Leim", label: "Martin Leim" },
  { id: "Mathias Stümpert", label: "Mathias Stümpert" },
  { id: "Michael Mauer", label: "Michael Mauer" },
  { id: "Patrick Höhle", label: "Patrick Höhle" },
  { id: "Quan Cheng", label: "Quan Cheng" },
  { id: "Samer Abdalla", label: "Samer Abdalla" },
  { id: "Steffen Eitelmann", label: "Steffen Eitelmann" },
  { id: "Tamino Fischer", label: "Tamino Fischer" },
  { id: "Thomas Freier", label: "Thomas Freier" },
  { id: "Thomas Simon", label: "Thomas Simon" },
];

export const COMMIT_USERS: Member[] = [
  { id: "Rong Yin", label: "Rong Yin", defaultOn: true },
  { id: "Raymond Shen", label: "Raymond Shen", defaultOn: true },
  { id: "Charlotte Jiang", label: "Charlotte Jiang", defaultOn: true },
  { id: "Christoph Scheben", label: "Christoph Scheben", defaultOn: true },
  { id: "Tobias Troesch", label: "Tobias Troesch", defaultOn: true },
  { id: "Jan Loeffler", label: "Jan Loeffler (CTO)" },
  { id: "Belen Liu", label: "Belen Liu", defaultOn: true },
  { id: "Eason Li", label: "Eason Li", defaultOn: true },
  { id: "Johnny Yang", label: "Johnny Yang", defaultOn: true },
];

export const PROJECT_QUICK_ASKS: { label: string; query: string }[] = [
  {
    label: "System Architecture Overview",
    query: "List all indexed projects and give me a high-level overview of the system architecture.",
  },
  {
    label: "Project Dependencies Graph",
    query: "What are the key dependencies between all projects? Show me the dependency graph.",
  },
  {
    label: "Impact Analysis",
    query: "What would break if I change Core Framework? Do a full impact analysis.",
  },
  {
    label: "REST Endpoints Discovery",
    query: "What are the main REST API endpoints across all projects?",
  },
];

export const AUDIO_SOURCE_TYPES: { id: string; label: string }[] = [
  { id: "news_item", label: "AI Briefings / News" },
  { id: "raw_content", label: "Raw Articles" },
  { id: "wiki_page", label: "Wiki Pages" },
  { id: "code_doc", label: "Code Documentation" },
  { id: "book_chapter", label: "Books / Learning" },
  { id: "project_doc", label: "Project Docs" },
];

export const TREND_CATEGORIES: { id: string; label: string; hint?: string }[] = [
  { id: "ai_news", label: "AI News" },
  { id: "world_news", label: "World News" },
  { id: "commits", label: "Commits" },
  { id: "jira", label: "Jira", hint: "per-person items in RAG + reports" },
  { id: "wiki", label: "Wiki Pages" },
];

export function memberDefaults(members: Member[]): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  for (const m of members) out[m.id] = !!m.defaultOn;
  return out;
}

export function selectedValues(flags: Record<string, boolean>): string[] {
  return Object.keys(flags).filter((k) => flags[k]);
}

export function isoDay(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function defaultDateRange(days: number, now = new Date()): { from: string; to: string } {
  const to = new Date(now);
  const from = new Date(now);
  from.setDate(from.getDate() - days);
  return { from: isoDay(from), to: isoDay(to) };
}

export function monthAgoRange(now = new Date()): { from: string; to: string } {
  const to = new Date(now);
  const from = new Date(now);
  from.setMonth(from.getMonth() - 1);
  return { from: isoDay(from), to: isoDay(to) };
}

export function dateRangeToHours(from: string, to: string): number {
  if (!from || !to) return 48;
  const ms = new Date(`${to}T23:59:59`).getTime() - new Date(`${from}T00:00:00`).getTime();
  return Math.max(1, Math.ceil(ms / 3600000));
}

export function dateRangeLabel(from: string, to: string): string {
  return `${from || "?"} to ${to || "?"}`;
}

export function buildExplainPrompt(topic: string, depth: "quick" | "deep", useWeb: boolean): string {
  const depthInstruction =
    depth === "quick"
      ? "Give a concise explanation (2-3 paragraphs). Cover: what it is, why it matters, and one practical example."
      : "Give a comprehensive deep-dive explanation. Cover: 1) What it is and core concepts, 2) How it works technically, 3) Why it matters in the AI/tech landscape, 4) Practical applications and examples, 5) How it relates to Java/medtech/healthcare if applicable, 6) Resources to learn more. Use clear analogies for complex concepts.";
  const webInstruction = useWeb
    ? "The user also wants you to search the web for the latest information on this topic. Use your web search tool if available."
    : "";
  return (
    `EXPLAIN THIS: "${topic}"\n\n` +
    depthInstruction +
    "\n" +
    webInstruction +
    "\n" +
    "Search the knowledge base (RAG) for any relevant context about this topic from previous briefings, articles, or documentation. " +
    "Combine RAG context with your own knowledge to provide the most helpful explanation. " +
    "Format with clear headings and structure. If the topic appeared in recent AI briefings, reference those."
  );
}

export function buildCommitChatPrompt(members: string[], range: string): string {
  return (
    `IMPORTANT: Use ONLY the latest commit data block above (the one marked [Git Commits ${range}]). ` +
    "Ignore any older commit data in the conversation. Summarize the commits for " +
    `${members.join(", ")} (${range}): group by person and repository, highlight key changes, areas of focus, and notable patterns. ` +
    "Do NOT invent job titles or roles for anyone."
  );
}

export function buildTeamActivityChatPrompt(members: string[], range: string, hasCommits: boolean): string {
  let prompt =
    "IMPORTANT: Use ONLY the latest commit data block above. Ignore any older data in the conversation. " +
    `Show comprehensive team activity for ${members.join(", ")} from ${range}. `;
  if (hasCommits) prompt += "Git commit data is shown above — summarize ALL commits, not just the preview. ";
  prompt +=
    "Also search for their Jira ticket updates, wiki page changes, and any other tracked activity. " +
    "Group everything by person with sections for commits, Jira, and wiki. Do NOT invent job titles or roles for anyone.";
  return prompt;
}

export function buildJiraChatPrompt(): string {
  return "Summarize the Jira daily report above: group open tickets and activity by team member, highlight blockers or high-priority items, and note sprint progress. Include Confluence page updates.";
}

export const PENDING_CHAT_KEY = "jarvis.pendingChat";

export type PendingChat = {
  sessionId?: string;
  report?: string;
  prompt?: string;
  autoSend?: boolean;
  useDeep?: boolean;
};

export function stashPendingChat(pending: PendingChat) {
  sessionStorage.setItem(PENDING_CHAT_KEY, JSON.stringify(pending));
}

export function takePendingChat(): PendingChat | null {
  const raw = sessionStorage.getItem(PENDING_CHAT_KEY);
  if (!raw) return null;
  sessionStorage.removeItem(PENDING_CHAT_KEY);
  try {
    return JSON.parse(raw) as PendingChat;
  } catch {
    return null;
  }
}

export const LEARNING_SESSION_TYPES: Record<string, string> = {
  "00000000-0000-0000-0000-000000000001": "ai_learning",
  "00000000-0000-0000-0000-000000000002": "tech_english",
  "00000000-0000-0000-0000-000000000003": "casual_english",
  "00000000-0000-0000-0000-000000000004": "aws_cert",
};

export function noteSessionType(sessionId: string | undefined | null): string {
  if (!sessionId) return "general";
  return LEARNING_SESSION_TYPES[sessionId] || "general";
}

export type PendingChatMessage = { role: "user" | "assistant"; content: string };

export function pendingSendContext(
  pending: PendingChat,
  opened: { id: string; messages: PendingChatMessage[] } | null,
  currentSessionId: string,
): { sessionId: string; history: PendingChatMessage[] } {
  if (pending.report) {
    return {
      sessionId: opened?.id || pending.sessionId || currentSessionId,
      history: [{ role: "assistant", content: pending.report }],
    };
  }
  return {
    sessionId: opened?.id || pending.sessionId || currentSessionId,
    history: opened?.messages || [],
  };
}

