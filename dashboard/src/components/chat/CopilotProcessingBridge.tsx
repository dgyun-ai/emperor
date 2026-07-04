import { useEffect } from "react";
import { useAgent } from "@copilotkit/react-core/v2";

type Props = {
  agentId?: string;
  onProcessingChange?: (working: boolean) => void;
  onComplete?: () => void;
};

/** Bridge CopilotKit agent run lifecycle to Emperor workspace callbacks. */
export default function CopilotProcessingBridge({
  agentId = "default",
  onProcessingChange,
  onComplete,
}: Props) {
  const { agent } = useAgent({ agentId });

  useEffect(() => {
    let running = false;
    let lastSignature = "";

    const buildSignature = () =>
      agent.messages
        .map((message) => {
          const content =
            typeof message.content === "string"
              ? message.content
              : Array.isArray(message.content)
                ? message.content.length
                : 0;
          const activityType = "activityType" in message ? String(message.activityType || "") : "";
          return `${message.id}:${message.role}:${content}:${activityType}`;
        })
        .join("|");

    const subscription = agent.subscribe({
      onRunStartedEvent: () => {
        running = true;
        lastSignature = buildSignature();
        onProcessingChange?.(true);
      },
      onMessagesChanged: () => {
        const nextSignature = buildSignature();
        if (nextSignature !== lastSignature) {
          lastSignature = nextSignature;
          if (agent.isRunning) onProcessingChange?.(true);
        }
      },
      onRunFinalized: () => {
        if (running) onComplete?.();
        running = false;
        lastSignature = buildSignature();
        onProcessingChange?.(false);
      },
      onRunFailed: () => {
        running = false;
        lastSignature = buildSignature();
        onProcessingChange?.(false);
      },
    });
    return () => subscription.unsubscribe();
  }, [agent, onComplete, onProcessingChange]);

  return null;
}
