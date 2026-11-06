import { NotesPanel } from "@/features/news/NotesPanel";
import { PageFrame } from "@/layouts/PageFrame";

export function NotesPage() {
  return (
    <PageFrame title="Notes">
      <NotesPanel />
    </PageFrame>
  );
}
