import type { AudioVoice } from "@/lib/audioSettings";

export const PASSAGE_CHUNK_CHARS = 500;
export const BROWSER_CHUNK_CHARS = 120;

export type PassageLang = "en" | "zh";
export type PassageEngine = "browser" | "edge" | "mimo";

const SENTENCE_MARK = /[.!?。！？]/;

function splitSentences(body: string): string[] {
  const sentences: string[] = [];
  let buf = "";
  for (const ch of body) {
    buf += ch;
    if (SENTENCE_MARK.test(ch)) {
      const trimmed = buf.trim();
      if (trimmed) sentences.push(trimmed);
      buf = "";
    }
  }
  const rest = buf.trim();
  if (rest) sentences.push(rest);
  return sentences;
}

export function passageLang(text: string): PassageLang {
  const han = text.match(/[\u3400-\u9fff]/g)?.length ?? 0;
  const latin = text.match(/[A-Za-z]/g)?.length ?? 0;
  return han > latin ? "zh" : "en";
}

function pushHard(out: string[], text: string, max: number) {
  for (let i = 0; i < text.length; i += max) {
    const piece = text.slice(i, i + max).trim();
    if (piece) out.push(piece);
  }
}

export function passageChunks(text: string, max = PASSAGE_CHUNK_CHARS): string[] {
  const out: string[] = [];
  for (const para of text.split(/\n\n+/)) {
    const body = para.trim();
    if (!body) continue;
    if (body.length <= max) {
      out.push(body);
      continue;
    }
    let buf = "";
    for (const sentence of splitSentences(body)) {
      const part = sentence.trim();
      if (!part) continue;
      if (part.length > max) {
        if (buf) {
          out.push(buf);
          buf = "";
        }
        pushHard(out, part, max);
        continue;
      }
      const joined = joinSentences(buf, part);
      if (!buf) {
        buf = part;
      } else if (joined.length <= max) {
        buf = joined;
      } else {
        out.push(buf);
        buf = part;
      }
    }
    if (buf) out.push(buf);
  }
  return out;
}

export function chunkStarts(text: string, chunks: string[]): number[] {
  const starts: number[] = [];
  let cursor = 0;
  for (const part of chunks) {
    const at = text.indexOf(part, cursor);
    const start = at >= 0 ? at : cursor;
    starts.push(start);
    cursor = start + part.length;
  }
  return starts;
}

export function chunkIndexAt(starts: number[], offset: number): number {
  let index = 0;
  for (let i = 0; i < starts.length; i += 1) {
    if (starts[i] <= offset) index = i;
    else break;
  }
  return index;
}

export type NamedVoice = { name: string; lang: string; localService?: boolean };

function joinSentences(left: string, right: string): string {
  if (!left) return right;
  if (/\s$/.test(left) || /^\s/.test(right)) return `${left}${right.trimStart()}`;
  const cjk = /[\u3400-\u9fff。！？]$/.test(left) || /^[\u3400-\u9fff]/.test(right);
  return cjk ? `${left}${right}` : `${left} ${right}`;
}

const FEMALE_VOICE = /female|\bwoman\b|\bgirl\b|女|\bzira\b|\bhazel\b|\bhuihui\b|\byaoyao\b|\baria\b|\bjenny\b|\bxiaoxiao\b/i;
const MALE_VOICE = /\bmale\b|\bman\b|\bboy\b|男|\bdavid\b|\bmark\b|\bkangkang\b|\bguy\b|\bandrew\b|\byunjian\b/i;

function matchesGender(name: string, gender: AudioVoice): boolean {
  const female = FEMALE_VOICE.test(name);
  if (gender === "female") return female;
  if (female) return false;
  return MALE_VOICE.test(name);
}

export function pickBrowserVoice<T extends NamedVoice>(
  voices: T[],
  lang: PassageLang,
  gender: AudioVoice,
): T | null {
  const prefix = lang === "zh" ? "zh" : "en";
  const same = voices.filter((voice) => voice.lang.toLowerCase().startsWith(prefix));
  if (!same.length) return null;
  const installed = same.filter((voice) => voice.localService !== false);
  return (
    installed.find((voice) => matchesGender(voice.name, gender)) ??
    installed[0] ??
    same.find((voice) => matchesGender(voice.name, gender)) ??
    same[0]
  );
}

export function speakRequestBody(input: {
  text: string;
  engine: "edge" | "mimo";
  lang: PassageLang;
  gender: AudioVoice;
  style?: string;
}): Record<string, unknown> {
  const body: Record<string, unknown> = {
    text: input.text,
    engine: input.engine,
    lang: input.lang,
    gender: input.gender,
    pad: false,
    rate: "slow",
  };
  if (input.engine === "mimo" && input.style) body.style = input.style;
  return body;
}

function trackChunk(pending: Promise<Blob>): Promise<Blob> {
  pending.catch(() => undefined);
  return pending;
}

export async function playChunked(
  chunks: string[],
  fetchChunk: (text: string, signal: AbortSignal) => Promise<Blob>,
  playBlob: (blob: Blob) => Promise<void>,
  signal: AbortSignal,
): Promise<void> {
  if (!chunks.length || signal.aborted) return;
  let upcoming: Promise<Blob> | null = trackChunk(fetchChunk(chunks[0], signal));
  for (let i = 0; i < chunks.length; i += 1) {
    if (signal.aborted) return;
    let blob: Blob;
    try {
      blob = await upcoming!;
    } catch (error) {
      if (signal.aborted) return;
      throw error;
    }
    upcoming = null;
    if (signal.aborted) return;
    const next = i + 1 < chunks.length ? trackChunk(fetchChunk(chunks[i + 1], signal)) : null;
    try {
      await playBlob(blob);
    } catch (error) {
      if (signal.aborted) return;
      throw error;
    }
    if (signal.aborted) return;
    upcoming = next;
  }
}

type VoiceSynth = {
  getVoices: () => NamedVoice[];
  addEventListener: (type: string, listener: () => void) => void;
  removeEventListener: (type: string, listener: () => void) => void;
};

export function waitForVoices(synth: VoiceSynth, timeoutMs = 250): Promise<NamedVoice[]> {
  const ready = synth.getVoices();
  if (ready.length) return Promise.resolve(ready);
  return new Promise((resolve) => {
    const finish = (voices: NamedVoice[]) => {
      clearTimeout(timer);
      synth.removeEventListener("voiceschanged", onChange);
      resolve(voices);
    };
    const onChange = () => finish(synth.getVoices());
    const timer = setTimeout(() => finish(synth.getVoices()), timeoutMs);
    synth.addEventListener("voiceschanged", onChange);
  });
}

export function speakChoiceFromSettings(
  settings: {
    audio_engine?: string;
    audio_voice_en?: string;
    audio_voice_zh?: string;
    audio_mimo_style?: string;
  },
  touched: boolean,
): { engine: PassageEngine; voiceEn: AudioVoice; voiceZh: AudioVoice; style?: string } | null {
  if (touched) return null;
  return {
    engine: settings.audio_engine === "mimo" ? "mimo" : settings.audio_engine === "browser" ? "browser" : "edge",
    voiceEn: settings.audio_voice_en === "male" ? "male" : "female",
    voiceZh: settings.audio_voice_zh === "male" ? "male" : "female",
    style: settings.audio_mimo_style,
  };
}

export function silenceAudio(audio: { pause: () => void; removeAttribute: (name: string) => void; load: () => void }) {
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
}
