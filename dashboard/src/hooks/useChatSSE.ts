import { useCallback, useRef, useState } from "react";
import { AUTH_TOKEN_KEY, getProfile } from "../api/client";
import { normalizeUsage, applyUsageChunk, type UsageSnapshot } from "../utils/usageSnapshot";

export type ChatBlock =
  | { type: "text"; content: string }
  | { type: "tool"; name: string; input?: unknown; result?: string };

function chunkDelta(payload: Record<string, unknown>): Record<string, unknown> {
  const choices = payload.choices;
  if (!Array.isArray(choices) || choices.length === 0) return {};
  const choice = choices[0];
  if (!choice || typeof choice !== "object") return {};
  const delta = (choice as Record<string, unknown>).delta;
  return delta && typeof delta === "object" ? (delta as Record<string, unknown>) : {};
}

export function useChatSSE(sessionId: string | null) {
  const [streaming, setStreaming] = useState(false);
  const [blocks, setBlocks] = useState<ChatBlock[]>([]);
  const [usage, setUsage] = useState<UsageSnapshot | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (content: string) => {
      if (!sessionId || !content.trim()) return;
      setBlocks((b) => [...b, { type: "text", content: `You: ${content}` }]);
      setStreaming(true);
      abortRef.current = new AbortController();
      const token = localStorage.getItem(AUTH_TOKEN_KEY);
      const profile = getProfile();

      const res = await fetch(`/api/chat/sessions/${sessionId}/messages`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          "X-Emperor-Profile": profile,
        },
        body: JSON.stringify({ content, profile }),
        signal: abortRef.current.signal,
      });

      if (!res.ok || !res.body) {
        setStreaming(false);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assistantText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const part of parts) {
          const lines = part.split("\n");
          let data = "";
          for (const line of lines) {
            if (line.startsWith("data: ")) data = line.slice(6);
          }
          if (!data || data === "[DONE]") continue;
          try {
            const payload = JSON.parse(data) as Record<string, unknown>;
            if (payload.object === "emperor.event") {
              const type = String(payload.type || "");
              if (type === "tool_end") {
                setBlocks((b) => {
                  const copy = [...b];
                  for (let i = copy.length - 1; i >= 0; i--) {
                    const block = copy[i];
                    if (block.type === "tool" && block.name === payload.name) {
                      copy[i] = { ...block, result: String(payload.result ?? "") };
                      break;
                    }
                  }
                  return copy;
                });
              }
              continue;
            }

            const delta = chunkDelta(payload);
            if (typeof delta.content === "string" && delta.content) {
              assistantText += delta.content;
              setBlocks((b) => {
                const copy = [...b];
                const last = copy[copy.length - 1];
                if (last?.type === "text" && last.content.startsWith("Assistant:")) {
                  copy[copy.length - 1] = {
                    type: "text",
                    content: `Assistant: ${assistantText}`,
                  };
                } else {
                  copy.push({ type: "text", content: `Assistant: ${assistantText}` });
                }
                return copy;
              });
            }

            const toolCalls = delta.tool_calls;
            if (Array.isArray(toolCalls) && toolCalls.length > 0) {
              const first = toolCalls[0] as Record<string, unknown>;
              const fn = first.function as Record<string, unknown> | undefined;
              setBlocks((b) => [
                ...b,
                { type: "tool", name: String(fn?.name || "?"), input: fn?.arguments },
              ]);
            }

            if (payload.usage && typeof payload.usage === "object") {
              setUsage((prev) => applyUsageChunk(prev, payload));
            }
          } catch {
            /* ignore parse errors */
          }
        }
      }
      setStreaming(false);
    },
    [sessionId]
  );

  const abort = useCallback(async () => {
    abortRef.current?.abort();
    if (sessionId) {
      const token = localStorage.getItem(AUTH_TOKEN_KEY);
      await fetch(`/api/chat/sessions/${sessionId}/abort`, {
        method: "POST",
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          "X-Emperor-Profile": getProfile(),
        },
      });
    }
    setStreaming(false);
  }, [sessionId]);

  const reset = useCallback(() => {
    setBlocks([]);
    setUsage(null);
  }, []);

  return { send, abort, streaming, blocks, usage, reset };
}
