import type { ProcessGroupState, ProcessStep } from "../hooks/useRealtime";

export type A2uiMessage = Record<string, unknown>;

export type TimelineA2uiSurface = {
  surfaceId: string;
  messages: A2uiMessage[];
};

export type TimelineMessage = {
  kind: "message";
  id: string;
  role: "user" | "assistant" | "error";
  content: string;
  timestamp?: number;
  streaming?: boolean;
  followUpQuestions?: string[];
  a2uiSurfaces?: TimelineA2uiSurface[];
};

export type TimelineProcess = {
  kind: "process";
  id: string;
  group: ProcessGroupState;
};

export type TimelineA2ui = {
  kind: "a2ui";
  id: string;
  surfaceId: string;
  messages: A2uiMessage[];
  timestamp?: number;
};

export type TimelineItem = TimelineMessage | TimelineProcess | TimelineA2ui;

export type StoredMessage = {
  role: string;
  content?: string;
  _thinking?: string;
  tool_calls?: Array<{ id?: string; function?: { name?: string } }>;
  tool_call_id?: string;
  created_at?: number;
  a2ui_messages?: A2uiMessage[];
  a2ui_surface_id?: string;
};

export type OpenClawEvent = {
  type: string;
  id?: string;
  parentId?: string | null;
  timestamp?: string;
  message?: {
    role?: string;
    content?: string | Array<{
      type?: string;
      text?: string;
      thinking?: string;
      id?: string;
      name?: string;
      surfaceId?: string;
      messages?: A2uiMessage[];
    }>;
    timestamp?: number;
    _thinking?: string;
    tool_calls?: Array<{ id?: string; function?: { name?: string; arguments?: unknown } }>;
    a2ui_messages?: A2uiMessage[];
    a2ui_surface_id?: string;
  };
};

function toolNameFromCall(tc: { function?: { name?: string } }): string {
  return tc.function?.name || "?";
}

function addProcessStep(group: ProcessGroupState, step: ProcessStep) {
  if (step.badge === "GEN") {
    const last = group.steps[group.steps.length - 1];
    if (last?.badge === "GEN") {
      last.text += step.text;
      return;
    }
  }
  group.steps.push(step);
}

function surfaceIdFromA2uiMessage(message: A2uiMessage): string {
  const keys = ["createSurface", "updateComponents", "updateDataModel", "deleteSurface"] as const;
  for (const key of keys) {
    const payload = message[key];
    if (payload && typeof payload === "object") {
      const surfaceId = (payload as { surfaceId?: unknown }).surfaceId;
      if (typeof surfaceId === "string" && surfaceId.trim()) {
        return surfaceId.trim();
      }
    }
  }
  return "main";
}

function mergeA2uiIntoHistory(
  history: Map<string, A2uiMessage[]>,
  messages: A2uiMessage[]
): Set<string> {
  const updated = new Set<string>();
  for (const message of messages) {
    const surfaceId = surfaceIdFromA2uiMessage(message);
    const existing = history.get(surfaceId) ?? [];
    history.set(surfaceId, [...existing, message]);
    updated.add(surfaceId);
  }
  return updated;
}

function markLatestToolDone(group: ProcessGroupState) {
  const matching = [...group.steps]
    .reverse()
    .find((step) => step.badge === "EXE" && step.text.startsWith("Tool:"));
  if (matching) {
    matching.text = `Done: ${matching.text.replace(/^Tool:\s*/, "")}`;
  }
}

function messageEventTimestamp(event: OpenClawEvent): number | undefined {
  const ts = event.message?.timestamp;
  return ts !== undefined ? ts : undefined;
}

function blocksToText(blocks: OpenClawEvent["message"] extends infer M ? M : never): string {
  if (!blocks || typeof blocks !== "object") return "";
  const content = (blocks as { content?: unknown }).content;
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .filter((block) => block && typeof block === "object" && block.type === "text")
    .map((block) => String(block.text || ""))
    .join("");
}

function buildA2uiSurfacesForTurn(
  surfaceHistory: Map<string, A2uiMessage[]>,
  surfaceIds: Set<string>
): TimelineA2uiSurface[] {
  const surfaces: TimelineA2uiSurface[] = [];
  for (const surfaceId of surfaceIds) {
    const messages = surfaceHistory.get(surfaceId);
    if (!messages?.length) continue;
    surfaces.push({ surfaceId, messages: [...messages] });
  }
  return surfaces;
}

type NormalizedAssistantMessage = {
  role: "assistant";
  content: string;
  thinking: string;
  toolCalls: Array<{ id?: string; function?: { name?: string } }>;
  a2uiMessages: A2uiMessage[];
  a2uiSurfaceId?: string;
  timestamp?: number;
};

type NormalizedToolMessage = {
  role: "tool";
  timestamp?: number;
};

type NormalizedTurnMessage = NormalizedAssistantMessage | NormalizedToolMessage;

function mergeConsecutiveAssistants(
  prev: NormalizedAssistantMessage,
  cur: NormalizedAssistantMessage
): NormalizedAssistantMessage {
  return {
    role: "assistant",
    content: `${prev.content}${cur.content}`,
    thinking: `${prev.thinking}${cur.thinking}`,
    toolCalls: prev.toolCalls.length > 0 ? prev.toolCalls : cur.toolCalls,
    a2uiMessages: [...prev.a2uiMessages, ...cur.a2uiMessages],
    a2uiSurfaceId: prev.a2uiSurfaceId || cur.a2uiSurfaceId,
    timestamp: cur.timestamp ?? prev.timestamp,
  };
}

function extractA2uiFromBlocks(
  blocks: Array<{
    type?: string;
    surfaceId?: string;
    messages?: A2uiMessage[];
  }>
): { messages: A2uiMessage[]; surfaceId?: string } {
  const messages: A2uiMessage[] = [];
  let surfaceId: string | undefined;
  for (const block of blocks) {
    if (block?.type !== "a2ui") continue;
    if (Array.isArray(block.messages)) {
      messages.push(...block.messages.filter((m): m is A2uiMessage => Boolean(m && typeof m === "object")));
    }
    if (!surfaceId && typeof block.surfaceId === "string" && block.surfaceId.trim()) {
      surfaceId = block.surfaceId.trim();
    }
  }
  return { messages, surfaceId };
}

function normalizeAssistantEvent(event: OpenClawEvent): NormalizedAssistantMessage | null {
  const msg = event.message;
  if (!msg || msg.role !== "assistant") return null;
  const blocks = Array.isArray(msg.content) ? msg.content : [];
  const { messages, surfaceId } = extractA2uiFromBlocks(blocks);
  const legacyToolCalls = Array.isArray(msg.tool_calls) ? msg.tool_calls : [];
  const legacyA2uiMessages = Array.isArray(msg.a2ui_messages) ? msg.a2ui_messages : [];
  const textFromStringContent = typeof msg.content === "string" ? msg.content : "";
  const legacyThinking = typeof msg._thinking === "string" ? msg._thinking : "";
  return {
    role: "assistant",
    content:
      textFromStringContent ||
      blocks
        .filter((block) => block?.type === "text")
        .map((block) => String(block.text || ""))
        .join(""),
    thinking:
      legacyThinking ||
      blocks
        .filter((block) => block?.type === "thinking")
        .map((block) => String(block.thinking || ""))
        .join(""),
    toolCalls:
      legacyToolCalls.length > 0
        ? legacyToolCalls
        : blocks
            .filter((block) => block?.type === "toolCall")
            .map((block) => ({
              id: block.id,
              function: { name: block.name },
            })),
    a2uiMessages: legacyA2uiMessages.length > 0 ? legacyA2uiMessages : messages,
    a2uiSurfaceId:
      (typeof msg.a2ui_surface_id === "string" && msg.a2ui_surface_id.trim()
        ? msg.a2ui_surface_id.trim()
        : undefined) || surfaceId,
    timestamp: messageEventTimestamp(event),
  };
}

function normalizeStoredAssistantMessage(message: StoredMessage): NormalizedAssistantMessage | null {
  if (message.role !== "assistant") return null;
  return {
    role: "assistant",
    content: message.content || "",
    thinking: message._thinking || "",
    toolCalls: [...(message.tool_calls || [])],
    a2uiMessages: [...(message.a2ui_messages || [])],
    a2uiSurfaceId: message.a2ui_surface_id,
    timestamp: message.created_at ? Math.round(message.created_at * 1000) : undefined,
  };
}

function normalizeTurnMessagesFromEvents(turnEvents: OpenClawEvent[]): NormalizedTurnMessage[] {
  const normalized: NormalizedTurnMessage[] = [];
  for (const event of turnEvents) {
    if (event.message?.role === "assistant") {
      const assistant = normalizeAssistantEvent(event);
      if (!assistant) continue;
      const last = normalized[normalized.length - 1];
      if (last?.role === "assistant") {
        normalized[normalized.length - 1] = mergeConsecutiveAssistants(last, assistant);
      } else {
        normalized.push(assistant);
      }
      continue;
    }
    if (event.message?.role === "tool") {
      normalized.push({
        role: "tool",
        timestamp: messageEventTimestamp(event),
      });
    }
  }
  return normalized;
}

function normalizeTurnMessagesFromStoredMessages(turnMessages: StoredMessage[]): NormalizedTurnMessage[] {
  const normalized: NormalizedTurnMessage[] = [];
  for (const message of turnMessages) {
    if (message.role === "assistant") {
      const assistant = normalizeStoredAssistantMessage(message);
      if (!assistant) continue;
      const last = normalized[normalized.length - 1];
      if (last?.role === "assistant") {
        normalized[normalized.length - 1] = mergeConsecutiveAssistants(last, assistant);
      } else {
        normalized.push(assistant);
      }
      continue;
    }
    if (message.role === "tool") {
      normalized.push({
        role: "tool",
        timestamp: message.created_at ? Math.round(message.created_at * 1000) : undefined,
      });
    }
  }
  return normalized;
}

function buildTurnItems(
  turnMessages: NormalizedTurnMessage[],
  turnKey: string,
  surfaceHistory: Map<string, A2uiMessage[]>
): TimelineItem[] {
  const items: TimelineItem[] = [];
  if (turnMessages.length === 0) return items;

  const lastAssistantIndex = (() => {
    for (let i = turnMessages.length - 1; i >= 0; i -= 1) {
      if (turnMessages[i].role === "assistant") return i;
    }
    return -1;
  })();

  const process: ProcessGroupState = {
    id: `pg-h-${turnKey}`,
    steps: [],
    collapsed: true,
    startTime: turnMessages.find((msg) => msg.timestamp !== undefined)?.timestamp ?? Date.now(),
  };

  let finalContent: string | null = null;
  let finalTimestamp: number | undefined;
  const preambleMessages: TimelineMessage[] = [];
  const surfacesUpdatedThisTurn = new Set<string>();

  turnMessages.forEach((msg, index) => {
    const ts = msg.timestamp;

    if (msg.role === "assistant") {
      const hasTools = msg.toolCalls.length > 0;
      const isFinalAnswer = index === lastAssistantIndex && !hasTools;

      if (msg.thinking) {
        addProcessStep(process, {
          id: `${process.id}-gen-${process.steps.length}`,
          badge: "GEN",
          text: msg.thinking,
        });
      }

      if (msg.a2uiMessages.length > 0) {
        const updated = mergeA2uiIntoHistory(surfaceHistory, msg.a2uiMessages);
        updated.forEach((surfaceId) => surfacesUpdatedThisTurn.add(surfaceId));
      }

      if (isFinalAnswer) {
        finalContent = msg.content;
        finalTimestamp = ts;
        return;
      }

      if (msg.content && hasTools) {
        preambleMessages.push({
          kind: "message",
          id: `${process.id}-pre-${preambleMessages.length}`,
          role: "assistant",
          content: msg.content,
          timestamp: ts,
        });
      }

      for (const tc of msg.toolCalls) {
        addProcessStep(process, {
          id: `${process.id}-exe-${process.steps.length}`,
          badge: "EXE",
          text: `Tool: ${toolNameFromCall(tc)}`,
        });
      }
      return;
    }

    if (msg.role === "tool") {
      markLatestToolDone(process);
    }
  });

  const lastPreamble = preambleMessages[preambleMessages.length - 1];
  if (typeof finalContent === "string" && lastPreamble && lastPreamble.content.trim() === String(finalContent).trim()) {
    preambleMessages.pop();
  }

  if (process.steps.length > 0) {
    const turnTimestamps = turnMessages
      .map((message) => message.timestamp)
      .filter((ts): ts is number => ts !== undefined);
    if (turnTimestamps.length > 0) {
      process.endTime = Math.max(...turnTimestamps);
    } else if (finalTimestamp !== undefined) {
      process.endTime = finalTimestamp;
    }
    items.push(...preambleMessages);
    items.push({ kind: "process", id: process.id, group: process });
  } else if (preambleMessages.length > 0) {
    items.push(...preambleMessages);
  }
  const a2uiSurfaces = buildA2uiSurfacesForTurn(surfaceHistory, surfacesUpdatedThisTurn);
  if (finalContent !== null || a2uiSurfaces.length > 0) {
    items.push({
      kind: "message",
      id: `h-a-${turnKey}`,
      role: "assistant",
      content: finalContent ?? "",
      timestamp: finalTimestamp,
      a2uiSurfaces: a2uiSurfaces.length > 0 ? a2uiSurfaces : undefined,
    });
  }

  return items;
}

export function mergeStreamA2uiSurfaces(
  existing: TimelineA2uiSurface[],
  incoming: A2uiMessage[]
): TimelineA2uiSurface[] {
  if (incoming.length === 0) return existing;
  const next = existing.map((surface) => ({
    surfaceId: surface.surfaceId,
    messages: [...surface.messages],
  }));
  for (const message of incoming) {
    const surfaceId = surfaceIdFromA2uiMessage(message);
    const index = next.findIndex((surface) => surface.surfaceId === surfaceId);
    if (index >= 0) {
      next[index] = {
        surfaceId,
        messages: [...next[index].messages, message],
      };
    } else {
      next.push({ surfaceId, messages: [message] });
    }
  }
  return next;
}

export function buildTimelineFromEvents(events: OpenClawEvent[]): TimelineItem[] {
  const items: TimelineItem[] = [];
  const surfaceHistory = new Map<string, A2uiMessage[]>();
  let turnEvents: OpenClawEvent[] = [];
  let turnCounter = 0;

  const flushTurn = () => {
    if (turnEvents.length === 0) return;
    const normalized = normalizeTurnMessagesFromEvents(turnEvents);
    items.push(...buildTurnItems(normalized, String(turnCounter++), surfaceHistory));
    turnEvents = [];
  };

  events.forEach((event, index) => {
    if (event.type !== "message") return;
    const role = event.message?.role;
    if (role === "user") {
      flushTurn();
      const content = blocksToText(event.message);
      if (content) {
        items.push({
          kind: "message",
          id: `h-u-${index}`,
          role: "user",
          content,
          timestamp: messageEventTimestamp(event),
        });
      }
      return;
    }
    turnEvents.push(event);
  });

  flushTurn();
  return items;
}

export function buildTimelineFromStoredMessages(messages: StoredMessage[]): TimelineItem[] {
  const items: TimelineItem[] = [];
  const surfaceHistory = new Map<string, A2uiMessage[]>();
  let turnMessages: StoredMessage[] = [];
  let turnCounter = 0;

  const flushTurn = () => {
    if (turnMessages.length === 0) return;
    const normalized = normalizeTurnMessagesFromStoredMessages(turnMessages);
    items.push(...buildTurnItems(normalized, String(turnCounter++), surfaceHistory));
    turnMessages = [];
  };

  messages.forEach((msg, index) => {
    if (msg.role === "user") {
      flushTurn();
      if (msg.content) {
        items.push({
          kind: "message",
          id: `h-u-${index}`,
          role: "user",
          content: msg.content,
          timestamp: msg.created_at ? Math.round(msg.created_at * 1000) : undefined,
        });
      }
      return;
    }

    turnMessages.push(msg);
  });

  flushTurn();
  return items;
}

export function mergeA2uiTimelineItem(
  items: TimelineItem[],
  messages: A2uiMessage[],
  id: string
): TimelineItem[] {
  if (messages.length === 0) return items;
  const surfaceId =
    (messages.find((m) => m.createSurface && typeof m.createSurface === "object") as
      | { createSurface?: { surfaceId?: string } }
      | undefined)?.createSurface?.surfaceId || "main";
  const existingIndex = items.findIndex((item) => item.kind === "a2ui" && item.id === id);
  if (existingIndex >= 0) {
    const existing = items[existingIndex] as TimelineA2ui;
    const hasCreate = existing.messages.some((m) => Boolean(m.createSurface));
    const incoming = hasCreate ? messages.filter((m) => !m.createSurface) : messages;
    if (incoming.length === 0) return items;
    return items.map((item, idx) =>
      idx === existingIndex
        ? {
            ...existing,
            messages: [...existing.messages, ...incoming],
            surfaceId,
          }
        : item
    );
  }
  return [
    ...items,
    {
      kind: "a2ui",
      id,
      surfaceId,
      messages: [...messages],
      timestamp: Date.now(),
    },
  ];
}
