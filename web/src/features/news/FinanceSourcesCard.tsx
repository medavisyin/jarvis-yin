import { useCallback, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";
import { buildEnabledMap } from "@/lib/dailyFetch";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type FnSource = { id: string; display?: string; category?: string; default_enabled?: boolean };
type FnCat = { id: string; label?: string };

export function FinanceSourcesCard() {
  const [cats, setCats] = useState<FnCat[]>([]);
  const [sources, setSources] = useState<FnSource[]>([]);
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const loadSources = useCallback(async () => {
    const data = await apiJson<{
      categories?: FnCat[];
      sources?: FnSource[];
      enabled?: string[];
    }>("/api/toolbar/finance-sources");
    setCats(data.categories || []);
    setSources(data.sources || []);
    const on: Record<string, boolean> = {};
    (data.enabled || []).forEach((id) => {
      on[id] = true;
    });
    setEnabled(on);
  }, []);

  useEffect(() => {
    loadSources().catch((e: Error) => setError(e.message));
  }, [loadSources]);

  async function save() {
    setError("");
    await apiJson("/api/toolbar/finance-sources", {
      method: "POST",
      body: JSON.stringify({ enabled: buildEnabledMap(sources, enabled) }),
    });
    setStatus("Finance sources saved");
    await loadSources();
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Finance sources (category + publisher)</CardTitle>
        <Button size="sm" variant="outline" onClick={() => void save()}>
          Save
        </Button>
      </CardHeader>
      <CardContent className="max-h-80 space-y-3 overflow-y-auto text-sm">
        {cats.length === 0 && !error ? <p className="text-muted-foreground">Loading…</p> : null}
        {cats.map((c) => {
          const kids = sources.filter((s) => s.category === c.id);
          const allOn = kids.length > 0 && kids.every((s) => enabled[s.id]);
          return (
            <div key={c.id}>
              <label className="flex items-center gap-2 font-medium">
                <input
                  type="checkbox"
                  checked={allOn}
                  onChange={(e) => {
                    const next = { ...enabled };
                    kids.forEach((s) => {
                      next[s.id] = e.target.checked;
                    });
                    setEnabled(next);
                  }}
                />
                {c.label || c.id}
              </label>
              <div className="mt-1 space-y-1 pl-5">
                {kids.map((s) => (
                  <label key={s.id} className="text-muted-foreground flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={!!enabled[s.id]}
                      onChange={(e) => setEnabled((prev) => ({ ...prev, [s.id]: e.target.checked }))}
                    />
                    {s.display || s.id}
                    {s.default_enabled ? null : <span className="text-xs">(optional)</span>}
                  </label>
                ))}
              </div>
            </div>
          );
        })}
        {status ? <p className="text-xs">{status}</p> : null}
        {error ? <p className="text-destructive text-xs">{error}</p> : null}
      </CardContent>
    </Card>
  );
}
