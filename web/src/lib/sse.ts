export type SseEvent = Record<string, unknown> & { type?: string };

export function parseSseChunk(chunk: string): { events: SseEvent[]; rest: string } {
  const lines = chunk.split("\n");
  const rest = lines.pop() ?? "";
  const events: SseEvent[] = [];
  for (const line of lines) {
    if (!line.startsWith("data: ")) continue;
    const payload = line.slice(6).trim();
    if (payload === "[DONE]") continue;
    try {
      events.push(JSON.parse(payload) as SseEvent);
    } catch {
      continue;
    }
  }
  return { events, rest };
}
