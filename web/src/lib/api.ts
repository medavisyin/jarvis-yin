import { parseSseChunk, type SseEvent } from "./sse";

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const resp = await fetch(path, { ...init, headers });
  const data = (await resp.json().catch(() => ({}))) as T;
  if (!resp.ok) {
    const err = data as { error?: string };
    throw new Error(err.error || `HTTP ${resp.status}`);
  }
  return data;
}

export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const resp = await fetch(path, { method: "POST", body: form });
  const data = (await resp.json().catch(() => ({}))) as T;
  if (!resp.ok) {
    const err = data as { error?: string };
    throw new Error(err.error || `HTTP ${resp.status}`);
  }
  return data;
}

export async function apiSsePost(
  path: string,
  body: unknown,
  onEvent: (event: SseEvent) => void,
): Promise<void> {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error((err as { error?: string }).error || `HTTP ${resp.status}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseChunk(buffer);
    buffer = parsed.rest;
    for (const event of parsed.events) {
      onEvent(event);
    }
  }
  if (buffer.startsWith("data: ")) {
    const parsed = parseSseChunk(buffer + "\n");
    for (const event of parsed.events) {
      onEvent(event);
    }
  }
}
