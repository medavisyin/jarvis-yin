import { useState } from "react";
import { apiJson } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const CATEGORIES = [
  ["markets", "综合市场"],
  ["china-policy", "中国政策金融"],
  ["us-political", "美国政治金融"],
  ["crypto", "数字货币"],
  ["gold", "黄金"],
  ["oil", "石油"],
] as const;

export function FinanceNewsSummary() {
  const today = new Date().toISOString().slice(0, 10);
  const week = new Date();
  week.setDate(week.getDate() - 6);
  const [start, setStart] = useState(week.toISOString().slice(0, 10));
  const [end, setEnd] = useState(today);
  const [cats, setCats] = useState<string[]>(CATEGORIES.map(([id]) => id));
  const [out, setOut] = useState("");
  const [items, setItems] = useState<{ title?: string; url?: string; source?: string; category?: string }[]>([]);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setOut("Generating…");
    try {
      const data = await apiJson<{
        summary?: string;
        items?: { title?: string; url?: string; source?: string; category?: string }[];
      }>("/api/toolbar/finance-news-summary", {
        method: "POST",
        body: JSON.stringify({ start, end, categories: cats }),
      });
      setOut(data.summary || "");
      setItems(data.items || []);
    } catch (e) {
      setOut(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Finance News Summary</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground text-xs">
          Pick a date range and categories. Summary is Chinese; titles/links stay as fetched.
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            {CATEGORIES.map(([id, lab]) => (
              <label key={id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={cats.includes(id)}
                  onChange={(e) =>
                    setCats((prev) => (e.target.checked ? [...prev, id] : prev.filter((x) => x !== id)))
                  }
                />
                {lab}
              </label>
            ))}
          </div>
          <div className="space-y-2">
            <label className="block">
              From
              <input
                type="date"
                className="border-input bg-background mt-1 h-8 w-full rounded-lg border px-2"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </label>
            <label className="block">
              To
              <input
                type="date"
                className="border-input bg-background mt-1 h-8 w-full rounded-lg border px-2"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
              />
            </label>
          </div>
        </div>
        <Button size="sm" disabled={busy} onClick={() => void run()}>
          Generate summary
        </Button>
        {out ? <pre className="whitespace-pre-wrap">{out}</pre> : null}
        {items.length ? (
          <ul className="list-disc space-y-1 pl-5 text-xs">
            {items.map((it, i) => (
              <li key={i}>
                [{it.category}] {it.source} —{" "}
                {it.url ? (
                  <a className="text-primary underline" href={it.url} target="_blank" rel="noreferrer">
                    {it.title}
                  </a>
                ) : (
                  it.title
                )}
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}
