export type SpeakRate = "slow" | "medium" | "fast";

const EDGE: Record<SpeakRate, string> = {
  slow: "-25%",
  medium: "-10%",
  fast: "+0%",
};

const BROWSER: Record<SpeakRate, number> = {
  slow: 0.68,
  medium: 0.82,
  fast: 0.95,
};

export function normalizeSpeakRate(raw: string | null | undefined): SpeakRate {
  const rate = (raw || "").trim().toLowerCase();
  if (rate === "medium" || rate === "fast" || rate === "slow") return rate;
  return "slow";
}

export function edgeSpeakRate(raw: string | null | undefined): string {
  return EDGE[normalizeSpeakRate(raw)];
}

export function browserSpeakRate(raw: string | null | undefined): number {
  return BROWSER[normalizeSpeakRate(raw)];
}
