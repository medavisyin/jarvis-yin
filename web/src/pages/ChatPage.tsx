import { useCallback, useEffect, useRef, useState } from "react";
import { apiJson, apiSsePost } from "@/lib/api";
import { takePendingChat, noteSessionType, pendingSendContext } from "@/lib/toolbar";
import { renderChatMarkdown } from "@/lib/chatMarkdown";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type SessionMeta = {
  id: string;
  title: string;
  message_count: number;
};

type ChatMessage = { role: "user" | "assistant"; content: string; imageUrl?: string };

export function ChatPage() {
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [sessionType, setSessionType] = useState("general");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [imageB64, setImageB64] = useState("");
  const [imagePreview, setImagePreview] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [status, setStatus] = useState("");
  const [traces, setTraces] = useState<string[]>([]);
  const [noteStatus, setNoteStatus] = useState("");
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadSessions = useCallback(async () => {
    const data = await apiJson<{ sessions: SessionMeta[] }>("/api/sessions");
    setSessions(data.sessions || []);
  }, []);

  useEffect(() => {
    loadSessions().catch((e: Error) => setError(e.message));
    const pending = takePendingChat();
    if (!pending) return;
    void (async () => {
      try {
        if (pending.useDeep) {
          await apiJson("/api/switch-model", { method: "POST", body: JSON.stringify({ model: "qwen3:8b" }) }).catch(
            () => undefined,
          );
        }
        let opened: { id: string; messages: ChatMessage[] } | null = null;
        if (pending.sessionId) {
          opened = await openSession(pending.sessionId);
        }
        if (pending.report) {
          setMessages([{ role: "assistant", content: pending.report }]);
        }
        if (pending.prompt && pending.autoSend) {
          const ctx = pendingSendContext(pending, opened, opened?.id || "");
          await sendQuery(pending.prompt, ctx.history, ctx.sessionId);
        } else if (pending.prompt) {
          setDraft(pending.prompt);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- consume pending chat once on mount
  }, [loadSessions]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, status]);

  async function openSession(id: string) {
    const data = await apiJson<{ id: string; messages?: ChatMessage[]; session_type?: string }>(`/api/sessions/${id}`);
    setSessionId(data.id);
    setSessionType(data.session_type || noteSessionType(data.id));
    const msgs = (data.messages || []).filter(
      (m) => m.role === "user" || m.role === "assistant",
    );
    setMessages(msgs);
    setError("");
    return { id: data.id, messages: msgs };
  }

  async function newSession() {
    const data = await apiJson<{ id: string }>("/api/sessions", { method: "POST" });
    setSessionId(data.id);
    setSessionType("general");
    setMessages([]);
    setError("");
    await loadSessions();
  }

  async function deleteSession() {
    if (!sessionId) return;
    await apiJson(`/api/sessions/${sessionId}`, { method: "DELETE" });
    setSessionId("");
    setSessionType("general");
    setMessages([]);
    await loadSessions();
  }

  async function clearSession() {
    if (!sessionId) return;
    await apiJson(`/api/sessions/${sessionId}/clear`, { method: "POST" });
    setMessages([]);
  }

  function onPickImage(file: File | undefined) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const comma = result.indexOf(",");
      setImagePreview(result);
      setImageB64(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.readAsDataURL(file);
  }

  async function sendQuery(query: string, seedHistory?: ChatMessage[], sessionOverride?: string) {
    if ((!query && !imageB64) || streaming) return;
    setError("");
    setStatus("");
    setDraft("");
    const attachedPreview = imagePreview;
    const attachedB64 = imageB64;
    setImageB64("");
    setImagePreview("");
    let sid = sessionOverride || sessionId;
    if (!sid) {
      const created = await apiJson<{ id: string }>("/api/sessions", { method: "POST" });
      sid = created.id;
      setSessionId(sid);
    }
    const base = seedHistory ?? messages;
    const history = base.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [
      ...(seedHistory ?? prev),
      { role: "user", content: query || "(image)", imageUrl: attachedPreview || undefined },
    ]);
    setStreaming(true);
    setTraces([]);
    let assistant = "";
    try {
      const body: Record<string, unknown> = { query: query || "What's in this image?", history, session_id: sid };
      if (attachedB64) body.image = attachedB64;
      await apiSsePost("/api/agent", body, (event) => {
        if (event.type === "model" && typeof event.model === "string") {
          setStatus(`Using LLM: ${event.model}`);
        } else if (event.type === "query_rewrite") {
          const rewritten = typeof event.content === "string" ? event.content : JSON.stringify(event);
          setTraces((t) => [...t, `Query rewrite: ${rewritten}`]);
        } else if (event.type === "thinking") {
          const tool = typeof event.tool === "string" ? event.tool : "";
          const content = typeof event.content === "string" ? event.content : "";
          const args = event.args ? JSON.stringify(event.args).slice(0, 120) : "";
          const line = tool ? `Calling ${tool}${args ? ` (${args})` : ""}` : content.slice(0, 200);
          if (line) {
            setTraces((t) => [...t, line]);
            setStatus(line);
          }
        } else if (event.type === "tool_result" && typeof event.tool === "string") {
          setTraces((t) => [...t, `tool: ${event.tool}`]);
          setStatus(`tool: ${event.tool}`);
        } else if (event.type === "token" && typeof event.content === "string") {
          assistant += event.content;
          const text = assistant;
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "assistant") {
              next[next.length - 1] = { role: "assistant", content: text };
            } else {
              next.push({ role: "assistant", content: text });
            }
            return next;
          });
        } else if (event.type === "error" && typeof event.content === "string") {
          setError(event.content);
        }
      });
      if (assistant) {
        await apiJson(`/api/sessions/${sid}/messages`, {
          method: "POST",
          body: JSON.stringify({ user_message: query || "(image)", assistant_message: assistant }),
        });
        await loadSessions();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStreaming(false);
      setStatus("");
    }
  }

  async function saveNote(content: string) {
    const st = sessionType || noteSessionType(sessionId);
    try {
      await apiJson("/api/notes", {
        method: "POST",
        body: JSON.stringify({
          content,
          tags: [st],
          session_id: sessionId,
          session_type: st,
        }),
      });
      setNoteStatus("Saved to notes");
      setTimeout(() => setNoteStatus(""), 2000);
    } catch (e) {
      setNoteStatus(e instanceof Error ? e.message : String(e));
    }
  }

  async function send() {
    await sendQuery(draft.trim());
  }

  return (
    <div className="flex h-full min-h-0">
      <div className="border-border flex w-56 shrink-0 flex-col border-r">
        <div className="flex items-center justify-between p-3">
          <span className="text-sm font-medium">Sessions</span>
          <Button type="button" size="sm" variant="outline" onClick={() => void newSession()}>
            New
          </Button>
        </div>
        <ScrollArea className="flex-1">
          <div className="flex flex-col gap-1 p-2">
            {sessions.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => void openSession(s.id)}
                className={cn(
                  "rounded-lg px-2 py-2 text-left text-xs",
                  s.id === sessionId ? "bg-muted" : "hover:bg-muted/60",
                )}
              >
                <span className="line-clamp-2">{s.title || "Untitled"}</span>
              </button>
            ))}
          </div>
        </ScrollArea>
        <div className="flex gap-1 p-2">
          <Button type="button" size="sm" variant="ghost" disabled={!sessionId} onClick={() => void clearSession()}>
            Clear
          </Button>
          <Button type="button" size="sm" variant="ghost" disabled={!sessionId} onClick={() => void deleteSession()}>
            Delete
          </Button>
        </div>
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {messages.map((m, i) => (
            <div
              key={`${m.role}-${i}`}
              className={cn(
                "max-w-[80%] rounded-xl px-3 py-2 text-sm",
                m.role === "user" ? "bg-primary text-primary-foreground ml-auto whitespace-pre-wrap" : "bg-muted",
              )}
            >
              {m.imageUrl ? (
                <img src={m.imageUrl} alt="" className="mb-2 max-h-40 rounded-md" />
              ) : null}
              {m.role === "assistant" ? (
                <>
                  <div dangerouslySetInnerHTML={{ __html: renderChatMarkdown(m.content) }} />
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="mt-1 h-6 px-1 text-xs"
                    title="Save to Notes"
                    onClick={() => void saveNote(m.content)}
                  >
                    Save note
                  </Button>
                </>
              ) : (
                m.content
              )}
            </div>
          ))}
          {traces.length ? (
            <div className="border-border text-muted-foreground max-w-[80%] rounded-xl border border-dashed px-3 py-2 text-xs">
              {traces.map((t, i) => (
                <div key={i}>{t}</div>
              ))}
            </div>
          ) : null}
          {streaming && <p className="text-muted-foreground text-xs">{status || "Streaming…"}</p>}
          {noteStatus ? <p className="text-muted-foreground text-xs">{noteStatus}</p> : null}
          <div ref={bottomRef} />
        </div>
        {error ? <p className="text-destructive px-4 text-sm">{error}</p> : null}
        {imagePreview ? (
          <div className="flex items-center gap-2 px-3 pt-2">
            <img src={imagePreview} alt="" className="h-12 rounded-md" />
            <Button type="button" size="sm" variant="ghost" onClick={() => { setImageB64(""); setImagePreview(""); }}>
              Remove
            </Button>
          </div>
        ) : null}
        <form
          className="border-border flex items-end gap-2 border-t p-3"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => onPickImage(e.target.files?.[0])}
          />
          <Button type="button" variant="outline" onClick={() => fileRef.current?.click()}>
            Image
          </Button>
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask Jarvis…"
            className="min-h-12"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
          />
          <Button type="submit" disabled={streaming || (!draft.trim() && !imageB64)}>
            Send
          </Button>
        </form>
      </div>
    </div>
  );
}
