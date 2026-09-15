import type { LucideIcon } from "lucide-react";
import { BookOpen, Building2, LineChart, MessageSquare, Newspaper, Settings } from "lucide-react";
import { MEDAVIS_TABS } from "./medavisTabs";
import { NEWS_TABS } from "./newsTabs";
import { STOCK_TABS } from "./stockTabs";

export type NavChild = { to: string; label: string };

export type NavLeaf = {
  kind: "leaf";
  id: string;
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
};

export type NavGroup = {
  kind: "group";
  id: string;
  to: string;
  label: string;
  icon: LucideIcon;
  children: NavChild[];
};

export type NavItem = NavLeaf | NavGroup;

export function isNavGroup(item: NavItem): item is NavGroup {
  return item.kind === "group";
}

export function defaultChildPath(group: NavGroup): string {
  return group.children[0]?.to || group.to;
}

export function accordionValuesForPath(pathname: string): string[] {
  return NAV.filter(isNavGroup)
    .filter((g) => pathname === g.to || pathname.startsWith(`${g.to}/`))
    .map((g) => g.id);
}

export const NAV: NavItem[] = [
  { kind: "leaf", id: "chat", to: "/", label: "Chat", icon: MessageSquare, end: true },
  {
    kind: "group",
    id: "news",
    to: "/news",
    label: "News",
    icon: Newspaper,
    children: NEWS_TABS.map((t) => ({ to: t.path, label: t.label })),
  },
  {
    kind: "group",
    id: "stock",
    to: "/stock",
    label: "Stock",
    icon: LineChart,
    children: STOCK_TABS.map((t) => ({ to: t.path, label: t.label })),
  },
  { kind: "leaf", id: "reading", to: "/reading", label: "Reading", icon: BookOpen },
  {
    kind: "group",
    id: "medavis",
    to: "/medavis",
    label: "Medavis",
    icon: Building2,
    children: MEDAVIS_TABS.map((t) => ({ to: t.path, label: t.label })),
  },
  { kind: "leaf", id: "settings", to: "/settings", label: "Settings", icon: Settings },
];
