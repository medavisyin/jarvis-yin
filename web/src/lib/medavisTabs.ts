export const MEDAVIS_TABS = [
  { id: "wiki", label: "Wiki Fetch", path: "/medavis/wiki" },
  { id: "jira", label: "Jira Daily", path: "/medavis/jira" },
  { id: "commit", label: "Commit Summary", path: "/medavis/commit" },
  { id: "platform", label: "Platform Updates", path: "/medavis/platform" },
  { id: "activity", label: "Team Activity", path: "/medavis/activity" },
  { id: "projects", label: "Projects", path: "/medavis/projects" },
] as const;

export type MedavisTabId = (typeof MEDAVIS_TABS)[number]["id"];
