import { useCallback, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";
import { renderReportMarkdown } from "@/lib/dailyFetch";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

type Note = {
  id: string;
  title?: string;
  content?: string;
  created_at?: string;
  tags?: string[];
};

export function NotesPanel() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [tag, setTag] = useState("");
  const [openId, setOpenId] = useState("");
  const [editing, setEditing] = useState("");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const url = tag ? `/api/notes?tag=${encodeURIComponent(tag)}` : "/api/notes";
    const data = await apiJson<Note[]>(url);
    setNotes(Array.isArray(data) ? data : []);
  }, [tag]);

  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);

  async function save(id: string) {
    const content = draft.trim();
    if (!content) return;
    await apiJson(`/api/notes/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    });
    setEditing("");
    await load();
  }

  async function remove(id: string) {
    await apiJson(`/api/notes/${encodeURIComponent(id)}`, { method: "DELETE" });
    await load();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>My Notes</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <label className="flex items-center gap-2 text-xs">
          Filter tag
          <input
            className="border-input bg-background h-8 rounded-lg border px-2"
            value={tag}
            onChange={(e) => setTag(e.target.value)}
            placeholder="e.g. ai_learning"
          />
        </label>
        {error ? <p className="text-destructive">{error}</p> : null}
        {notes.length === 0 ? (
          <p className="text-muted-foreground py-8 text-center text-xs">
            No notes yet. Save assistant replies from Chat (coming next on Chat page).
          </p>
        ) : (
          notes.map((n) => (
            <div key={n.id} className="rounded-lg border p-2">
              <button type="button" className="flex w-full items-center gap-2 text-left" onClick={() => setOpenId((id) => (id === n.id ? "" : n.id))}>
                <span className="font-medium">{n.title || (n.content || "").slice(0, 80)}</span>
                <span className="text-muted-foreground ml-auto text-xs">{(n.created_at || "").slice(0, 10)}</span>
              </button>
              {openId === n.id ? (
                <div className="mt-2 space-y-2">
                  {editing === n.id ? (
                    <>
                      <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} />
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => void save(n.id)}>
                          Save
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => setEditing("")}>
                          Cancel
                        </Button>
                      </div>
                    </>
                  ) : (
                    <>
                      <div
                        className="text-sm"
                        dangerouslySetInnerHTML={{ __html: renderReportMarkdown(n.content || "") }}
                      />
                      <div className="flex flex-wrap gap-1">
                        {(n.tags || []).map((t) => (
                          <span key={t} className="bg-muted rounded px-1 text-[10px]">
                            {t}
                          </span>
                        ))}
                      </div>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setEditing(n.id);
                            setDraft(n.content || "");
                          }}
                        >
                          Edit
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => void remove(n.id)}>
                          Delete
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              ) : null}
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}
