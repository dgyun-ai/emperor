import type { MessageProcessor } from "@a2ui/web_core/v0_9";
import type { A2uiMessage as WireA2uiMessage } from "@a2ui/web_core/v0_9";
import type { ReactComponentImplementation } from "@a2ui/react/v0_9";
import { normalizeA2uiMessages } from "./normalizeA2uiMessages";

export type A2uiMessage = Record<string, unknown>;

function surfaceIdFromCreateMessage(message: A2uiMessage): string | null {
  const create = message.createSurface;
  if (!create || typeof create !== "object") return null;
  const surfaceId = (create as { surfaceId?: unknown }).surfaceId;
  return typeof surfaceId === "string" && surfaceId.trim() ? surfaceId.trim() : null;
}

function shouldSkipMessage(
  processor: MessageProcessor<ReactComponentImplementation>,
  message: A2uiMessage
): boolean {
  const surfaceId = surfaceIdFromCreateMessage(message);
  if (surfaceId && processor.model.getSurface(surfaceId)) {
    return true;
  }
  return false;
}

/** Apply only new messages; skip duplicate createSurface for existing surfaces. */
export function applyA2uiMessagesIncrementally(
  processor: MessageProcessor<ReactComponentImplementation>,
  messages: A2uiMessage[],
  appliedCount: number
): number {
  if (appliedCount >= messages.length) {
    return appliedCount;
  }

  const pending = normalizeA2uiMessages(messages.slice(appliedCount));
  for (const raw of pending) {
    if (!raw || typeof raw !== "object") continue;
    if (shouldSkipMessage(processor, raw)) continue;
    try {
      processor.processMessages([raw as unknown as WireA2uiMessage]);
    } catch (err) {
      console.warn("[A2UI] skipped message:", err);
    }
  }
  return messages.length;
}
