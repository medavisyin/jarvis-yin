import { useEffect, useState } from "react";
import { apiJson } from "@/lib/api";
import { applyTheme, readTheme, type ThemeId } from "@/lib/theme";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FinanceSourcesCard } from "@/features/news/FinanceSourcesCard";
import { WorldSourcesCard } from "@/features/news/WorldSourcesCard";
import { PageFrame } from "@/layouts/PageFrame";

type Health = {
  ollama?: boolean;
  qdrant?: boolean;
  model?: string;
  ollama_models?: string[];
};

type GlobalSettings = {
  audio_lang_ai?: string;
  audio_lang_finance?: string;
  audio_lang_knowledge?: string;
  audio_voice_zh?: string;
  audio_voice_en?: string;
  deepseek_api_key_masked?: string;
};

const LANGS = ["zh", "en"] as const;
const VOICES = ["female", "male"] as const;

export function SettingsPage() {
  const [health, setHealth] = useState<Health>({});
  const [model, setModel] = useState("");
  const [settings, setSettings] = useState<GlobalSettings>({});
  const [deepseekKey, setDeepseekKey] = useState("");
  const [status, setStatus] = useState("");
  const [theme, setTheme] = useState<ThemeId>(() => readTheme());

  async function reload() {
    const h = await apiJson<Health>("/api/health");
    setHealth(h);
    const m = await apiJson<{ model: string }>("/api/switch-model");
    setModel(m.model || h.model || "");
    const s = await apiJson<GlobalSettings>("/api/settings");
    setSettings(s);
  }

  useEffect(() => {
    reload().catch((e: Error) => setStatus(e.message));
  }, []);

  async function saveModel() {
    setStatus("");
    const r = await apiJson<{ model: string }>("/api/switch-model", {
      method: "POST",
      body: JSON.stringify({ model }),
    });
    setModel(r.model);
    setStatus("Model updated");
  }

  async function saveAudio() {
    setStatus("");
    const r = await apiJson<{ settings: GlobalSettings }>("/api/settings", {
      method: "POST",
      body: JSON.stringify({
        audio_lang_ai: settings.audio_lang_ai,
        audio_lang_finance: settings.audio_lang_finance,
        audio_lang_knowledge: settings.audio_lang_knowledge,
        audio_voice_zh: settings.audio_voice_zh,
        audio_voice_en: settings.audio_voice_en,
      }),
    });
    setSettings((prev) => ({ ...prev, ...r.settings }));
    setStatus("Audio settings saved");
  }

  async function saveDeepseekKey() {
    setStatus("");
    const r = await apiJson<{ ok: boolean; masked?: string }>("/api/settings/deepseek-key", {
      method: "POST",
      body: JSON.stringify({ api_key: deepseekKey }),
    });
    setDeepseekKey("");
    setSettings((prev) => ({ ...prev, deepseek_api_key_masked: r.masked || "" }));
    setStatus("DeepSeek key saved");
  }

  function selectCls(value: string | undefined, onChange: (v: string) => void, options: readonly string[]) {
    return (
      <select
        className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
        value={value || options[0]}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    );
  }

  function setAppearance(next: ThemeId) {
    setTheme(next);
    applyTheme(next);
  }

  return (
    <PageFrame title="Settings">
      <div className="mx-auto max-w-4xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Theme</CardTitle>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Button size="sm" variant={theme === "day" ? "default" : "outline"} onClick={() => setAppearance("day")}>
            Day
          </Button>
          <Button size="sm" variant={theme === "night" ? "default" : "outline"} onClick={() => setAppearance("night")}>
            Night
          </Button>
          <Button size="sm" variant={theme === "reading" ? "default" : "outline"} onClick={() => setAppearance("reading")}>
            Reading
          </Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Health</CardTitle>
        </CardHeader>
        <CardContent className="text-muted-foreground space-y-1 text-sm">
          <p>Ollama: {health.ollama ? "up" : "down"}</p>
          <p>Qdrant: {health.qdrant ? "up" : "down"}</p>
          <p>Model: {health.model}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Chat model</CardTitle>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Input value={model} onChange={(e) => setModel(e.target.value)} list="ollama-models" />
          <datalist id="ollama-models">
            {(health.ollama_models || []).map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
          <Button type="button" onClick={() => void saveModel()}>
            Save
          </Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Audio</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <label className="flex items-center justify-between gap-2">
            AI news
            {selectCls(settings.audio_lang_ai, (v) => setSettings((s) => ({ ...s, audio_lang_ai: v })), LANGS)}
          </label>
          <label className="flex items-center justify-between gap-2">
            Finance
            {selectCls(settings.audio_lang_finance, (v) => setSettings((s) => ({ ...s, audio_lang_finance: v })), LANGS)}
          </label>
          <label className="flex items-center justify-between gap-2">
            Knowledge
            {selectCls(settings.audio_lang_knowledge, (v) => setSettings((s) => ({ ...s, audio_lang_knowledge: v })), LANGS)}
          </label>
          <label className="flex items-center justify-between gap-2">
            Voice ZH
            {selectCls(settings.audio_voice_zh, (v) => setSettings((s) => ({ ...s, audio_voice_zh: v })), VOICES)}
          </label>
          <label className="flex items-center justify-between gap-2">
            Voice EN
            {selectCls(settings.audio_voice_en, (v) => setSettings((s) => ({ ...s, audio_voice_en: v })), VOICES)}
          </label>
          <Button type="button" onClick={() => void saveAudio()}>
            Save audio
          </Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>DeepSeek key</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="text-muted-foreground text-xs">
            {settings.deepseek_api_key_masked ? `Configured: ${settings.deepseek_api_key_masked}` : "Not set"}
          </p>
          <div className="flex gap-2">
            <Input
              type="password"
              value={deepseekKey}
              onChange={(e) => setDeepseekKey(e.target.value)}
              placeholder="sk-..."
            />
            <Button type="button" onClick={() => void saveDeepseekKey()} disabled={!deepseekKey.trim()}>
              Save
            </Button>
          </div>
        </CardContent>
      </Card>
      <FinanceSourcesCard />
      <WorldSourcesCard />
      {status ? <p className="text-sm">{status}</p> : null}
      </div>
    </PageFrame>
  );
}
