import { useCallback, useRef, useState } from "react";
import { apiStream } from "../api/client";
import { shiba } from "../api/shibaAdapter";
import {
  buildTimelineFromEvents,
  buildTimelineFromStoredMessages,
  mergeStreamA2uiSurfaces,
  type A2uiMessage,
  type OpenClawEvent,
  type TimelineA2uiSurface,
  type TimelineItem,
  type TimelineProcess,
} from "../utils/chatTimeline";
import { normalizeUsage, applyUsageChunk, type UsageSnapshot } from "../utils/usageSnapshot";

export type ProcessStep = { id: string; badge: "GEN" | "EXE"; text: string };
export type ProcessGroupState = {
  id: string;
  steps: ProcessStep[];
  collapsed: boolean;
  startTime: number;
  /** Frozen when the turn finishes; elapsed stops updating. */
  endTime?: number;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "error";
  content: string;
  timestamp?: number;
};

export type RealtimeEvent =
  | { type: "response_chunk"; text: string }
  | { type: "agent_thinking"; text: string }
  | { type: "agent_tool"; name: string; input?: unknown; result?: string; phase: "start" | "end" }
  | { type: "usage_update"; payload: UsageSnapshot }
  | { type: "terminal"; reason?: string }
  | { type: "error"; message: string };

export type { TimelineItem };

function chunkDelta(data: Record<string, unknown>): Record<string, unknown> {
  const choices = data.choices;
  if (!Array.isArray(choices) || choices.length === 0) return {};
  const choice = choices[0];
  if (!choice || typeof choice !== "object") return {};
  const delta = (choice as Record<string, unknown>).delta;
  return delta && typeof delta === "object" ? (delta as Record<string, unknown>) : {};
}

function chunkFinishReason(data: Record<string, unknown>): string | null {
  const choices = data.choices;
  if (!Array.isArray(choices) || choices.length === 0) return null;
  const choice = choices[0];
  if (!choice || typeof choice !== "object") return null;
  const reason = (choice as Record<string, unknown>).finish_reason;
  return typeof reason === "string" ? reason : null;
}

function chunkEmperorMeta(data: Record<string, unknown>): Record<string, unknown> | null {
  const emperor = data.emperor;
  return emperor && typeof emperor === "object" ? (emperor as Record<string, unknown>) : null;
}

function normalizeFollowUpQuestions(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((q): q is string => typeof q === "string" && q.trim().length > 0)
    .map((q) => q.trim())
    .slice(0, 3);
}

function clearAllFollowUpQuestions(items: TimelineItem[]): TimelineItem[] {
  return items.map((item) =>
    item.kind === "message" && item.followUpQuestions
      ? { ...item, followUpQuestions: undefined }
      : item
  );
}

function attachFollowUpToLastAssistant(items: TimelineItem[], questions: string[]): TimelineItem[] {
  const normalized = normalizeFollowUpQuestions(questions);
  if (normalized.length === 0) return items;
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const item = items[i];
    if (item.kind === "message" && item.role === "assistant") {
      return items.map((it, idx) =>
        idx === i ? { ...it, followUpQuestions: normalized } : it
      );
    }
  }
  return items;
}

function appendErrorMessages(items: TimelineItem[], errors: string[]): TimelineItem[] {
  if (errors.length === 0) return items;
  let next = items;
  for (const raw of errors) {
    const content = raw.trim();
    if (!content) continue;
    const exists = next.some(
      (item) => item.kind === "message" && item.role === "error" && item.content === content
    );
    if (exists) continue;
    next = [
      ...next,
      {
        kind: "message",
        id: `err-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        role: "error",
        content,
        timestamp: Date.now(),
      },
    ];
  }
  return next;
}

function terminalErrorMessage(emperor: Record<string, unknown> | null): string | null {
  if (!emperor || typeof emperor.reason !== "string") return null;
  const reason = emperor.reason;
  if (reason !== "error" && reason !== "max_iterations" && reason !== "aborted") return null;
  const detail =
    (typeof emperor.error === "string" && emperor.error.trim()) ||
    (typeof emperor.message === "string" && emperor.message.trim()) ||
    "";
  if (reason === "aborted") return detail || "Request aborted.";
  if (reason === "max_iterations") return detail || "Reached maximum iterations.";
  return detail || "Request failed.";
}

/** Append assistant text unless the terminal chunk signals a non-success stop. */
function shouldAppendAssistantMessage(emperor: Record<string, unknown> | null): boolean {
  const reason = emperor?.reason;
  if (typeof reason !== "string") return true;
  return reason === "complete" || reason === "loop_detected";
}

function hasA2uiContent(surfaces: TimelineA2uiSurface[]): boolean {
  return surfaces.some((surface) => surface.messages.length > 0);
}

function appendAssistantMessage(
  items: TimelineItem[],
  content: string,
  a2uiSurfaces?: TimelineA2uiSurface[]
): TimelineItem[] {
  const trimmed = content.trim();
  const a2ui = a2uiSurfaces?.filter((surface) => surface.messages.length > 0);
  if (!trimmed && !a2ui?.length) return items;
  const last = items[items.length - 1];
  if (
    last?.kind === "message" &&
    last.role === "assistant" &&
    last.content === trimmed &&
    !a2ui?.length
  ) {
    return items;
  }
  if (
    last?.kind === "message" &&
    last.role === "assistant" &&
    last.content === trimmed &&
    a2ui?.length
  ) {
    return items.map((it, idx) =>
      idx === items.length - 1
        ? {
            ...last,
            a2uiSurfaces: mergeStreamA2uiSurfaces(
              last.a2uiSurfaces ?? [],
              a2ui.flatMap((surface) => surface.messages)
            ),
          }
        : it
    );
  }
  if (last?.kind === "message" && last.role === "assistant" && !trimmed && a2ui?.length) {
    return items.map((it, idx) =>
      idx === items.length - 1
        ? {
            ...last,
            a2uiSurfaces: mergeStreamA2uiSurfaces(last.a2uiSurfaces ?? [], a2ui.flatMap((s) => s.messages)),
          }
        : it
    );
  }
  return [
    ...items,
    {
      kind: "message",
      id: `a-${Date.now()}`,
      role: "assistant",
      content: trimmed,
      timestamp: Date.now(),
      a2uiSurfaces: a2ui?.length ? a2ui : undefined,
    },
  ];
}

function finalizeTurnTimeline(
  items: TimelineItem[],
  streamText: string,
  streamA2ui: TimelineA2uiSurface[]
): TimelineItem[] {
  const trimmed = streamText.trim();
  const a2ui = streamA2ui.filter((surface) => surface.messages.length > 0);
  if (!trimmed && a2ui.length === 0) return items;

  for (let i = items.length - 1; i >= 0; i -= 1) {
    const item = items[i];
    if (item.kind !== "message" || item.role !== "assistant") continue;
    const nextContent = trimmed || item.content;
    const nextA2ui =
      a2ui.length > 0
        ? mergeStreamA2uiSurfaces(item.a2uiSurfaces ?? [], a2ui.flatMap((surface) => surface.messages))
        : item.a2uiSurfaces;
    if (nextContent === item.content && nextA2ui === item.a2uiSurfaces) return items;
    return items.map((it, idx) =>
      idx === i
        ? {
            ...item,
            content: nextContent,
            a2uiSurfaces: nextA2ui?.length ? nextA2ui : undefined,
          }
        : it
    );
  }

  return appendAssistantMessage(items, trimmed, a2ui.length > 0 ? a2ui : undefined);
}

function updateProcessItem(
  items: TimelineItem[],
  groupId: string,
  updater: (group: ProcessGroupState) => ProcessGroupState
): TimelineItem[] {
  return items.map((item) =>
    item.kind === "process" && item.id === groupId
      ? { ...item, group: updater(item.group) }
      : item
  );
}

function markLatestLiveToolDone(group: ProcessGroupState, name: string): ProcessGroupState {
  const steps = [...group.steps];
  for (let i = steps.length - 1; i >= 0; i -= 1) {
    const step = steps[i];
    if (step.badge !== "EXE") continue;
    if (!step.text.startsWith("Tool:")) continue;
    const toolName = step.text.replace(/^Tool:\s*/, "");
    if (toolName === name || !name) {
      steps[i] = { ...step, text: `Done: ${toolName}` };
      return { ...group, steps };
    }
  }
  steps.push({ id: `${group.id}-${steps.length}`, badge: "EXE", text: `Done: ${name || "?"}` });
  return { ...group, steps };
}

export function useRealtime(
  sessionId: string | null,
  options?: { askUserQuestionsEnabled?: boolean; a2uiEnabled?: boolean }
) {
  const askUserQuestionsEnabled = options?.askUserQuestionsEnabled ?? true;
  const a2uiEnabled = options?.a2uiEnabled ?? false;
  const [processing, setProcessing] = useState(false);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [usage, setUsage] = useState<UsageSnapshot | null>(null);
  const [streamText, setStreamText] = useState("");
  const [streamA2ui, setStreamA2ui] = useState<TimelineA2uiSurface[]>([]);
  const streamTextRef = useRef("");
  const streamA2uiRef = useRef<TimelineA2uiSurface[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const groupIdRef = useRef<string | null>(null);
  const streamErrorsRef = useRef<string[]>([]);

  const recordStreamError = useCallback((message: string) => {
    const content = message.trim();
    if (!content) return;
    if (!streamErrorsRef.current.includes(content)) {
      streamErrorsRef.current.push(content);
    }
    setTimeline((items) => appendErrorMessages(items, [content]));
  }, []);

  const setStreamingText = useCallback((value: string | ((prev: string) => string)) => {
    setStreamText((prev) => {
      const next = typeof value === "function" ? value(prev) : value;
      streamTextRef.current = next;
      return next;
    });
  }, []);

  const ensureGroup = useCallback(() => {
    if (groupIdRef.current) {
      return groupIdRef.current;
    }
    const id = `pg-${Date.now()}`;
    groupIdRef.current = id;
    const processItem: TimelineProcess = {
      kind: "process",
      id,
      group: { id, steps: [], collapsed: true, startTime: Date.now() },
    };
    setTimeline((items) => [...items, processItem]);
    return id;
  }, []);

  const addStep = useCallback(
    (badge: "GEN" | "EXE", text: string) => {
      const gid = ensureGroup();
      setTimeline((items) =>
        updateProcessItem(items, gid, (group) => ({
          ...group,
          steps: [...group.steps, { id: `${gid}-${group.steps.length}`, badge, text }],
        }))
      );
    },
    [ensureGroup]
  );

  const appendGenText = useCallback(
    (text: string) => {
      const gid = ensureGroup();
      setTimeline((items) =>
        updateProcessItem(items, gid, (group) => {
          const steps = [...group.steps];
          const last = steps[steps.length - 1];
          if (last?.badge === "GEN") {
            steps[steps.length - 1] = { ...last, text: last.text + text };
          } else {
            steps.push({ id: `${gid}-${steps.length}`, badge: "GEN", text });
          }
          return { ...group, steps };
        })
      );
    },
    [ensureGroup]
  );

  const commitStreamAsAssistantMessage = useCallback(() => {
    const text = streamTextRef.current.trim();
    if (!text) return;
    streamTextRef.current = "";
    setStreamText("");
    setTimeline((items) => {
      const processIndex =
        groupIdRef.current != null
          ? items.findIndex((item) => item.kind === "process" && item.id === groupIdRef.current)
          : -1;
      const message: TimelineItem = {
        kind: "message",
        id: `a-${Date.now()}`,
        role: "assistant",
        content: text,
        timestamp: Date.now(),
      };
      if (processIndex >= 0) {
        return [...items.slice(0, processIndex), message, ...items.slice(processIndex)];
      }
      return appendAssistantMessage(items, text);
    });
  }, []);

  const setStreamingA2ui = useCallback((value: TimelineA2uiSurface[] | ((prev: TimelineA2uiSurface[]) => TimelineA2uiSurface[])) => {
    setStreamA2ui((prev) => {
      const next = typeof value === "function" ? value(prev) : value;
      streamA2uiRef.current = next;
      return next;
    });
  }, []);

  const appendA2uiMessages = useCallback((messages: A2uiMessage[]) => {
    if (!a2uiEnabled || messages.length === 0) return;
    setStreamingA2ui((prev) => mergeStreamA2uiSurfaces(prev, messages));
  }, [a2uiEnabled, setStreamingA2ui]);

  const handleEvent = useCallback(
    (event: string, data: Record<string, unknown>) => {
      if (event === "chat.completion.chunk") {
        const delta = chunkDelta(data);
        const content = delta.content;
        if (typeof content === "string" && content) {
          setStreamingText((prev) => prev + content);
        }
        const reasoning = delta.reasoning_content;
        if (typeof reasoning === "string" && reasoning) {
          appendGenText(reasoning);
        }
        const toolCalls = delta.tool_calls;
        if (Array.isArray(toolCalls) && toolCalls.length > 0) {
          commitStreamAsAssistantMessage();
          const first = toolCalls[0] as Record<string, unknown>;
          const fn = first.function as Record<string, unknown> | undefined;
          addStep("EXE", `Tool: ${String(fn?.name || "?")}`);
        }
        const usage = data.usage;
        if (usage && typeof usage === "object") {
          setUsage((prev) => applyUsageChunk(prev, data));
        }
        const finishReason = chunkFinishReason(data);
        if (finishReason) {
          const emperor = chunkEmperorMeta(data);
          const terminalError = terminalErrorMessage(emperor);
          if (terminalError) {
            recordStreamError(terminalError);
          } else {
            const deltaContent = delta.content;
            const message =
              typeof deltaContent === "string" && deltaContent.trim()
                ? deltaContent
                : typeof emperor?.message === "string"
                  ? emperor.message
                  : streamTextRef.current.trim();
            const a2uiSnapshot = streamA2uiRef.current;
            if (
              (message.trim() || hasA2uiContent(a2uiSnapshot)) &&
              shouldAppendAssistantMessage(emperor)
            ) {
              setTimeline((items) =>
                appendAssistantMessage(items, message, hasA2uiContent(a2uiSnapshot) ? a2uiSnapshot : undefined)
              );
              streamTextRef.current = "";
              setStreamText("");
              if (hasA2uiContent(a2uiSnapshot)) {
                streamA2uiRef.current = [];
                setStreamingA2ui([]);
              }
            }
          }
        }
        return;
      }

      if (event === "emperor.event") {
        const type = String(data.type || "");
        if (type === "tool_end") {
          const gid = ensureGroup();
          setTimeline((items) =>
            updateProcessItem(items, gid, (group) =>
              markLatestLiveToolDone(group, String(data.name || "?"))
            )
          );
        } else if (type === "ask_user_questions" && askUserQuestionsEnabled) {
          if (streamErrorsRef.current.length > 0) return;
          const questions = normalizeFollowUpQuestions(data.questions);
          if (questions.length > 0) {
            setTimeline((items) => attachFollowUpToLastAssistant(items, questions));
          }
        } else if (type === "a2ui" && a2uiEnabled) {
          const raw = data.messages;
          if (Array.isArray(raw)) {
            const messages = raw.filter(
              (m): m is A2uiMessage => Boolean(m && typeof m === "object")
            );
            appendA2uiMessages(messages);
          }
        } else if (type === "error") {
          recordStreamError(String(data.message || "Error"));
        }
        return;
      }
    },
    [addStep, appendGenText, appendA2uiMessages, askUserQuestionsEnabled, a2uiEnabled, commitStreamAsAssistantMessage, ensureGroup, recordStreamError, setStreamingText, setStreamingA2ui]
  );

  const reset = useCallback(() => {
    setTimeline([]);
    streamTextRef.current = "";
    setStreamText("");
    streamA2uiRef.current = [];
    setStreamingA2ui([]);
    setUsage(null);
    groupIdRef.current = null;
  }, [setStreamingA2ui]);

  const syncSessionMeta = useCallback(async (sid: string) => {
    const data = await shiba.sessionGet(sid);
    setUsage(normalizeUsage(data.usage ?? null));
    if (askUserQuestionsEnabled && data.follow_up_questions?.length) {
      setTimeline((items) => attachFollowUpToLastAssistant(items, data.follow_up_questions ?? []));
    }
  }, [askUserQuestionsEnabled]);

  const loadHistory = useCallback(async (sid: string, extraErrors: string[] = []) => {
    const data = await shiba.sessionGet(sid);
    const events = (data.events || []) as OpenClawEvent[];
    let items: TimelineItem[];
    if (events.length > 0) {
      items = buildTimelineFromEvents(events);
    } else {
      items = buildTimelineFromStoredMessages(data.messages || []);
    }
    if (askUserQuestionsEnabled && data.follow_up_questions?.length && extraErrors.length === 0) {
      items = attachFollowUpToLastAssistant(items, data.follow_up_questions);
    }
    items = appendErrorMessages(items, extraErrors);
    setTimeline(items);
    setUsage(normalizeUsage(data.usage ?? null));
  }, [askUserQuestionsEnabled]);

  const send = useCallback(
    async (content: string, steer = false) => {
      if (!sessionId || !content.trim()) return;
      setTimeline((items) =>
        clearAllFollowUpQuestions([
          ...items,
          {
            kind: "message",
            id: `u-${Date.now()}`,
            role: "user",
            content,
            timestamp: Date.now(),
          },
        ])
      );
      setProcessing(true);
      setStreamingText("");
      streamA2uiRef.current = [];
      setStreamingA2ui([]);
      groupIdRef.current = null;
      streamErrorsRef.current = [];
      abortRef.current = new AbortController();
      try {
        await apiStream(
          `/api/chat/sessions/${sessionId}/messages`,
          { content, steer },
          (event, data) => {
            handleEvent(event, data);
          },
          abortRef.current.signal
        );
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          recordStreamError(String(err));
        }
      } finally {
        const pendingErrors = [...streamErrorsRef.current];
        streamErrorsRef.current = [];
        const pendingText = streamTextRef.current;
        const pendingA2ui = streamA2uiRef.current;
        if (groupIdRef.current) {
          const gid = groupIdRef.current;
          setTimeline((items) => {
            let next = updateProcessItem(items, gid, (group) => ({
              ...group,
              collapsed: true,
              endTime: group.endTime ?? Date.now(),
            }));
            next = finalizeTurnTimeline(next, pendingText, pendingA2ui);
            return appendErrorMessages(next, pendingErrors);
          });
          groupIdRef.current = null;
        } else {
          setTimeline((items) => {
            let next = finalizeTurnTimeline(items, pendingText, pendingA2ui);
            return appendErrorMessages(next, pendingErrors);
          });
        }
        streamTextRef.current = "";
        setStreamText("");
        streamA2uiRef.current = [];
        setStreamingA2ui([]);
        setProcessing(false);
        if (sessionId) {
          await syncSessionMeta(sessionId);
        }
      }
    },
    [sessionId, handleEvent, setStreamingText, setStreamingA2ui, syncSessionMeta, recordStreamError]
  );

  const sendA2uiAction = useCallback(
    async (action: Record<string, unknown>) => {
      if (!sessionId || !a2uiEnabled) return;
      const surfaceId = String(action.surfaceId || "main");
      const context =
        action.context && typeof action.context === "object"
          ? (action.context as Record<string, unknown>)
          : {};
      const dataModel =
        action.dataModel && typeof action.dataModel === "object"
          ? (action.dataModel as Record<string, unknown>)
          : undefined;
      const steer = processing;
      setProcessing(true);
      streamA2uiRef.current = [];
      setStreamingA2ui([]);
      streamErrorsRef.current = [];
      abortRef.current = new AbortController();
      try {
        await apiStream(
          `/api/chat/sessions/${sessionId}/a2ui-action`,
          {
            surfaceId,
            action,
            context,
            dataModel,
            steer,
          },
          (event, data) => {
            handleEvent(event, data);
          },
          abortRef.current.signal
        );
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          recordStreamError(String(err));
        }
      } finally {
        const pendingErrors = [...streamErrorsRef.current];
        streamErrorsRef.current = [];
        const pendingText = streamTextRef.current;
        const pendingA2ui = streamA2uiRef.current;
        setTimeline((items) => {
          let next = finalizeTurnTimeline(items, pendingText, pendingA2ui);
          return appendErrorMessages(next, pendingErrors);
        });
        streamTextRef.current = "";
        setStreamText("");
        streamA2uiRef.current = [];
        setStreamingA2ui([]);
        setProcessing(false);
        if (sessionId) {
          await syncSessionMeta(sessionId);
        }
      }
    },
    [sessionId, a2uiEnabled, processing, handleEvent, setStreamingA2ui, syncSessionMeta, recordStreamError, setStreamingText]
  );

  const abort = useCallback(async () => {
    abortRef.current?.abort();
    if (sessionId) {
      await fetch(`/api/chat/sessions/${sessionId}/abort`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("emperor.dashboard.token") || ""}`,
          "X-Emperor-Profile": localStorage.getItem("emperor.dashboard.profile") || "default",
        },
      });
    }
    setProcessing(false);
  }, [sessionId]);

  const toggleProcessGroup = useCallback((id: string) => {
    setTimeline((items) =>
      updateProcessItem(items, id, (group) => ({ ...group, collapsed: !group.collapsed }))
    );
  }, []);

  return {
    send,
    sendA2uiAction,
    abort,
    processing,
    timeline,
    streamText,
    streamA2ui,
    usage,
    reset,
    loadHistory,
    toggleProcessGroup,
    setProcessing,
    a2uiEnabled,
  };
}
