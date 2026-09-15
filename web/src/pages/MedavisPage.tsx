import { Navigate, Outlet, useParams } from "react-router-dom";
import { MedavisTool } from "@/features/medavis/MedavisPanel";
import { PageFrame } from "@/layouts/PageFrame";
import { MEDAVIS_TABS, type MedavisTabId } from "@/lib/medavisTabs";

export function MedavisLayout() {
  return (
    <PageFrame title="Medavis">
      <Outlet />
    </PageFrame>
  );
}

export function MedavisToolPage() {
  const { tab } = useParams();
  const match = MEDAVIS_TABS.find((t) => t.id === tab);
  if (!match) return <Navigate to="/medavis/wiki" replace />;
  return <MedavisTool tool={match.id as MedavisTabId} />;
}
