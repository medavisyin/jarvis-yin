import { useEffect, useRef, useState } from "react";
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
  chat_agent?: string;
  glm_api_key_masked?: string;
  mimo_api_key_masked?: string;
  audio_engine?: string;
  audio_mimo_style?: string;
};

const LANGS = ["zh", "en"] as const;
const VOICES = ["female", "male"] as const;
const ENGINES = ["edge", "mimo"] as const;
const ENGINE_LABELS: Record<(typeof ENGINES)[number], string> = {
  edge: "Edge",
  mimo: "MiMo-V2.5-TTS",
};
const MIMO_STYLES = [
  "开心", "悲伤", "愤怒", "恐惧", "惊讶", "兴奋", "委屈", "平静", "冷漠",
  "怅然", "欣慰", "无奈", "愧疚", "释然", "嫉妒", "厌倦", "忐忑", "动情",
  "温柔", "高冷", "活泼", "严肃", "慵懒", "俏皮", "深沉", "干练", "凌厉",
  "磁性", "醇厚", "清亮", "空灵", "稚嫩", "苍老", "甜美", "沙哑", "醇雅",
  "夹子音", "御姐音", "正太音", "大叔音", "台湾腔",
  "东北话", "四川话", "河南话", "粤语",
  "孙悟空", "林黛玉",
  "唱歌",
] as const;

export function SettingsPage() {
  const [health, setHealth] = useState<Health>({});
  const [model, setModel] = useState("");
  const [settings, setSettings] = useState<GlobalSettings>({});
  const [deepseekKey, setDeepseekKey] = useState("");
  const [glmKey, setGlmKey] = useState("");
  const [mimoKey, setMimoKey] = useState("");
  const [status, setStatus] = useState("");
  const statusRef = useRef<HTMLParagraphElement>(null);
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

  useEffect(() => {
    if (status) statusRef.current?.scrollIntoView({ block: "nearest" });
  }, [status]);

  function reportFailure(e: unknown) {
    setStatus(e instanceof Error ? e.message : "Request failed");
  }

  async function saveChatAgent(next: string) {
    setStatus("");
    try {
      const r = await apiJson<{ settings: GlobalSettings }>("/api/settings", {
        method: "POST",
        body: JSON.stringify({ chat_agent: next }),
      });
      setSettings((prev) => ({ ...prev, ...r.settings }));
      setStatus(next === "glm" ? "Chat agent: GLM" : next === "mimo" ? "Chat agent: MiMo" : "Chat agent: Ollama");
    } catch (e) {
      reportFailure(e);
    }
  }

  async function saveGlmKey() {
    setStatus("");
    try {
      const r = await apiJson<{ ok: boolean; masked?: string }>("/api/settings/glm-key", {
        method: "POST",
        body: JSON.stringify({ api_key: glmKey }),
      });
      setGlmKey("");
      setSettings((prev) => ({ ...prev, glm_api_key_masked: r.masked || "" }));
      setStatus("GLM key saved");
    } catch (e) {
      reportFailure(e);
    }
  }

  async function testGlm() {
    setStatus("");
    try {
      const r = await apiJson<{ reply?: string }>("/api/glm/test", {
        method: "POST",
        body: JSON.stringify(glmKey.trim() ? { api_key: glmKey.trim() } : {}),
      });
      setStatus(r.reply ? `GLM ok: ${r.reply}` : "GLM ok");
    } catch (e) {
      reportFailure(e);
    }
  }

  async function saveMimoKey() {
    setStatus("");
    try {
      const r = await apiJson<{ ok: boolean; masked?: string }>("/api/settings/mimo-key", {
        method: "POST",
        body: JSON.stringify({ api_key: mimoKey }),
      });
      setMimoKey("");
      setSettings((prev) => ({ ...prev, mimo_api_key_masked: r.masked || "" }));
      setStatus("MiMo key saved");
    } catch (e) {
      reportFailure(e);
    }
  }

  async function testMimo() {
    setStatus("");
    try {
      const r = await apiJson<{ reply?: string }>("/api/mimo/test", {
        method: "POST",
        body: JSON.stringify(mimoKey.trim() ? { api_key: mimoKey.trim() } : {}),
      });
      setStatus(r.reply ? `MiMo ok: ${r.reply}` : "MiMo ok");
    } catch (e) {
      reportFailure(e);
    }
  }

  async function testMimoSpeech(mode: "speak" | "sing") {
    setStatus("");
    try {
      const res = await fetch("/api/mimo/tts/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || "MiMo request failed");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => URL.revokeObjectURL(url);
      await audio.play();
      setStatus(mode === "sing" ? "MiMo singing" : "MiMo speaking");
    } catch (e) {
      reportFailure(e);
    }
  }

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
        audio_engine: settings.audio_engine,
        audio_mimo_style: settings.audio_mimo_style,
      }),
    });
    setSettings((prev) => ({ ...prev, ...r.settings }));
    setStatus("Audio settings saved");
  }

  async function saveDeepseekKey() {
    setStatus("");
    try {
      const r = await apiJson<{ ok: boolean; masked?: string }>("/api/settings/deepseek-key", {
        method: "POST",
        body: JSON.stringify({ api_key: deepseekKey }),
      });
      setDeepseekKey("");
      setSettings((prev) => ({ ...prev, deepseek_api_key_masked: r.masked || "" }));
      setStatus("DeepSeek key saved");
    } catch (e) {
      reportFailure(e);
    }
  }

  async function testDeepseek() {
    setStatus("");
    try {
      const r = await apiJson<{ reply?: string }>("/api/deepseek/test", {
        method: "POST",
        body: JSON.stringify(deepseekKey.trim() ? { api_key: deepseekKey.trim() } : {}),
      });
      setStatus(r.reply ? `DeepSeek ok: ${r.reply}` : "DeepSeek ok");
    } catch (e) {
      reportFailure(e);
    }
  }

  function selectCls(
    value: string | undefined,
    onChange: (v: string) => void,
    options: readonly string[],
    labels?: Readonly<Record<string, string>>,
  ) {
    return (
      <select
        className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
        value={value || options[0]}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {labels?.[o] ?? o}
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
      {status ? (
        <p ref={statusRef} className="text-sm">
          {status}
        </p>
      ) : null}
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
          <CardTitle>Chat agent</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              variant={(settings.chat_agent || "ollama") === "ollama" ? "default" : "outline"}
              onClick={() => void saveChatAgent("ollama")}
            >
              Ollama
            </Button>
            <Button
              type="button"
              size="sm"
              variant={settings.chat_agent === "glm" ? "default" : "outline"}
              onClick={() => void saveChatAgent("glm")}
            >
              GLM
            </Button>
            <Button
              type="button"
              size="sm"
              variant={settings.chat_agent === "mimo" ? "default" : "outline"}
              onClick={() => void saveChatAgent("mimo")}
            >
              MiMo
            </Button>
          </div>
          {(settings.chat_agent || "ollama") === "ollama" ? (
            <div className="flex gap-2">
              <Input value={model} onChange={(e) => setModel(e.target.value)} list="ollama-models" />
              <datalist id="ollama-models">
                {(health.ollama_models || []).map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
              <Button type="button" onClick={() => void saveModel()}>
                Save
              </Button>
            </div>
          ) : settings.chat_agent === "mimo" ? (
            <p className="text-muted-foreground text-xs">Chat uses mimo-v2.6-flash. Set the MiMo key in API keys below.</p>
          ) : (
            <p className="text-muted-foreground text-xs">Chat uses glm-4.7-flash. Set the GLM key in API keys below.</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>API keys</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <p className="text-sm">DeepSeek</p>
            <p className="text-muted-foreground text-xs">
              {settings.deepseek_api_key_masked ? `Configured: ${settings.deepseek_api_key_masked}` : "Not set"}
            </p>
            <div className="flex gap-2">
              <Input
                type="password"
                value={deepseekKey}
                onChange={(e) => setDeepseekKey(e.target.value)}
                placeholder="DeepSeek API key"
              />
              <Button type="button" onClick={() => void saveDeepseekKey()} disabled={!deepseekKey.trim()}>
                Save
              </Button>
              <Button type="button" variant="outline" onClick={() => void testDeepseek()}>
                Test
              </Button>
            </div>
          </div>
          <div className="space-y-2">
            <p className="text-sm">GLM</p>
            <p className="text-muted-foreground text-xs">
              Model glm-4.7-flash.{" "}
              {settings.glm_api_key_masked ? `Configured: ${settings.glm_api_key_masked}` : "Not set"}
            </p>
            <div className="flex gap-2">
              <Input
                type="password"
                value={glmKey}
                onChange={(e) => setGlmKey(e.target.value)}
                placeholder="GLM API key"
              />
              <Button type="button" onClick={() => void saveGlmKey()} disabled={!glmKey.trim()}>
                Save
              </Button>
              <Button type="button" variant="outline" onClick={() => void testGlm()}>
                Test
              </Button>
            </div>
          </div>
          <div className="space-y-2">
            <p className="text-sm">MiMo</p>
            <p className="text-muted-foreground text-xs">
              Model mimo-v2.6-flash.{" "}
              {settings.mimo_api_key_masked ? `Configured: ${settings.mimo_api_key_masked}` : "Not set"}
            </p>
            <div className="flex gap-2">
              <Input
                type="password"
                value={mimoKey}
                onChange={(e) => setMimoKey(e.target.value)}
                placeholder="MiMo API key"
              />
              <Button type="button" onClick={() => void saveMimoKey()} disabled={!mimoKey.trim()}>
                Save
              </Button>
              <Button type="button" variant="outline" onClick={() => void testMimo()}>
                Test
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Audio</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <label className="flex items-center justify-between gap-2">
            Engine
            {selectCls(
              settings.audio_engine || "edge",
              (v) => setSettings((s) => ({ ...s, audio_engine: v })),
              ENGINES,
              ENGINE_LABELS,
            )}
          </label>
          {(settings.audio_engine || "edge") === "mimo" ? (
            <label className="flex items-center justify-between gap-2">
              Style
              {selectCls(
                settings.audio_mimo_style || "平静",
                (v) => setSettings((s) => ({ ...s, audio_mimo_style: v })),
                MIMO_STYLES,
              )}
            </label>
          ) : null}
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
          {(settings.audio_engine || "edge") === "mimo" ? (
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={() => void testMimoSpeech("speak")}>
                说话
              </Button>
              <Button type="button" variant="outline" onClick={() => void testMimoSpeech("sing")}>
                唱歌
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>
      <FinanceSourcesCard />
      <WorldSourcesCard />
      </div>
    </PageFrame>
  );
}
