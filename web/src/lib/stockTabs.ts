export const STOCK_TABS = [
  { id: "watch", label: "Watchlist", path: "/stock/watch" },
  { id: "scan", label: "Scanners", path: "/stock/scan" },
  { id: "weekly", label: "Weekly", path: "/stock/weekly" },
  { id: "analyze", label: "Analyze", path: "/stock/analyze" },
  { id: "national", label: "National team", path: "/stock/national" },
  { id: "train", label: "Price train", path: "/stock/train" },
] as const;

export type StockTabId = (typeof STOCK_TABS)[number]["id"];
