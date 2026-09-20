export const NEWS_TABS = [
  { id: "daily", label: "Daily fetch", path: "/news/daily" },
  { id: "monitor", label: "World monitor", path: "/news/monitor" },
  { id: "ai", label: "AI news", path: "/news/ai" },
  { id: "audio", label: "Audio from Knowledge", path: "/news/audio" },
  { id: "explain", label: "Explain This", path: "/news/explain" },
  { id: "trend", label: "Trend Analysis", path: "/news/trend" },
  { id: "finance", label: "Finance News Summary", path: "/news/finance" },
  { id: "learning", label: "Learning modes", path: "/news/learning" },
  { id: "notes", label: "My Notes", path: "/news/notes" },
] as const;

export type NewsTabId = (typeof NEWS_TABS)[number]["id"];
