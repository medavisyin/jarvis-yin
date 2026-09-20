import { Navigate, Outlet, useParams } from "react-router-dom";
import { WorldMonitorPage } from "@/features/news/worldMonitor/WorldMonitorPage";
import { DailyFetchPanel } from "@/features/news/DailyFetchPanel";
import { AiNewsPanel } from "@/features/news/AiNewsPanel";
import { AudioKnowledgePanel } from "@/features/news/AudioKnowledgePanel";
import { ExplainThisForm, LearningModes, TrendAnalysisForm } from "@/features/news/ToolbarPanel";
import { FinanceNewsSummary } from "@/features/news/FinanceNewsSummary";
import { NotesPanel } from "@/features/news/NotesPanel";
import { PageFrame } from "@/layouts/PageFrame";
import { NEWS_TABS, type NewsTabId } from "@/lib/newsTabs";

export function NewsLayout() {
  return (
    <PageFrame title="News">
      <Outlet />
    </PageFrame>
  );
}

export function NewsToolPage() {
  const { tab } = useParams();
  const match = NEWS_TABS.find((t) => t.id === tab);
  if (!match) return <Navigate to="/news/daily" replace />;
  switch (match.id as NewsTabId) {
    case "daily":
      return <DailyFetchPanel />;
    case "monitor":
      return <WorldMonitorPage />;
    case "ai":
      return <AiNewsPanel />;
    case "audio":
      return <AudioKnowledgePanel />;
    case "explain":
      return <ExplainThisForm />;
    case "trend":
      return <TrendAnalysisForm />;
    case "finance":
      return <FinanceNewsSummary />;
    case "learning":
      return <LearningModes />;
    case "notes":
      return <NotesPanel />;
  }
}
