import { Button } from "@/components/ui/button";
import { AUDIO_VOICES, MIMO_STYLES, type AudioVoice } from "@/lib/audioSettings";
import type { PassageEngine } from "./passageSpeak";

const selectCls = "border-input bg-background h-7 rounded border px-1";

type Props = {
  engine: PassageEngine;
  voiceEn: AudioVoice;
  voiceZh: AudioVoice;
  style: string;
  speaking: boolean;
  canResume: boolean;
  error: string;
  onEngine: (engine: PassageEngine) => void;
  onVoiceEn: (voice: AudioVoice) => void;
  onVoiceZh: (voice: AudioVoice) => void;
  onStyle: (style: string) => void;
  onToggle: () => void;
};

function voiceOptions() {
  return AUDIO_VOICES.map((voice) => (
    <option key={voice} value={voice}>
      {voice === "female" ? "女" : "男"}
    </option>
  ));
}

export function PassageSpeakBar({
  engine,
  voiceEn,
  voiceZh,
  style,
  speaking,
  canResume,
  error,
  onEngine,
  onVoiceEn,
  onVoiceZh,
  onStyle,
  onToggle,
}: Props) {
  return (
    <span className="flex flex-wrap items-center gap-1">
      <Button type="button" size="xs" variant="outline" onClick={onToggle}>
        {speaking ? "停止" : canResume ? "继续" : "阅读全文"}
      </Button>
      <label className="flex items-center gap-1">
        引擎
        <select className={selectCls} value={engine} onChange={(e) => onEngine(e.target.value as PassageEngine)}>
          <option value="browser">浏览器</option>
          <option value="edge">Edge</option>
          <option value="mimo">MiMo</option>
        </select>
      </label>
      <label className="flex items-center gap-1">
        Voice EN
        <select className={selectCls} value={voiceEn} onChange={(e) => onVoiceEn(e.target.value as AudioVoice)}>
          {voiceOptions()}
        </select>
      </label>
      <label className="flex items-center gap-1">
        Voice ZH
        <select className={selectCls} value={voiceZh} onChange={(e) => onVoiceZh(e.target.value as AudioVoice)}>
          {voiceOptions()}
        </select>
      </label>
      {engine === "mimo" ? (
        <label className="flex items-center gap-1">
          Style
          <select className={selectCls} value={style} onChange={(e) => onStyle(e.target.value)}>
            {MIMO_STYLES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {error ? <span className="text-destructive">{error}</span> : null}
    </span>
  );
}
