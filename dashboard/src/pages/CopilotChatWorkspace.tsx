import { useEffect, useMemo } from "react";
import {
  CopilotChat,
  CopilotKit,
  a2uiDefaultTheme,
  createA2UIMessageRenderer,
} from "@copilotkit/react-core/v2";
import "@copilotkit/react-core/v2/styles.css";
import UsageBadge from "../components/chat/UsageBadge";
import CopilotProcessingBridge from "../components/chat/CopilotProcessingBridge";
import { copilotKitHeaders } from "../a2ui/copilotKitHeaders";
import { ensureA2uiTheme } from "../a2ui/ensureA2uiTheme";
import type { UsageSnapshot } from "../utils/usageSnapshot";
import "../styles/a2ui-v0_9.css";

type Props = {
  sessionId: string;
  agentId?: string;
  usage: UsageSnapshot | Record<string, unknown> | null;
  onProcessingChange?: (working: boolean) => void;
  onChatComplete?: () => void;
  onDeleteSession?: (sessionId: string) => void | Promise<void>;
  onOpenMobileNav?: () => void;
};

/**
 * Chat workspace powered by CopilotKit + AG-UI when A2UI is enabled.
 * Replaces the legacy SSE + A2uiSurfaceHost path for interactive UI.
 */
export default function CopilotChatWorkspace({
  sessionId,
  agentId = "default",
  usage,
  onProcessingChange,
  onChatComplete,
  onDeleteSession,
  onOpenMobileNav,
}: Props) {
  const headers = useMemo(() => copilotKitHeaders(), []);
  const renderActivityMessages = useMemo(
    () => [
      createA2UIMessageRenderer({
        theme: a2uiDefaultTheme,
        recovery: {
          debugExposure: "collapsed",
          showAfterMs: 1200,
          showAfterAttempts: 1,
        },
      }),
    ],
    []
  );

  useEffect(() => {
    ensureA2uiTheme();
  }, []);

  return (
    <CopilotKit
      key={`${sessionId}:${agentId}`}
      runtimeUrl="/api/ag-ui"
      threadId={sessionId}
      headers={headers}
      defaultThrottleMs={0}
      a2ui={{}}
      renderActivityMessages={renderActivityMessages}
      onError={({ error }) => {
        console.error("[CopilotKit chat]", error);
      }}
    >
      <CopilotProcessingBridge
        agentId={agentId}
        onProcessingChange={onProcessingChange}
        onComplete={onChatComplete}
      />
      <div className="copilot-chat-workspace" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
        <header className="chat-header">
          <button type="button" className="mobile-menu-btn" onClick={onOpenMobileNav} aria-label="Open menu">
            <span className="material-icons-round">menu</span>
          </button>
          <div className="chat-header-info">
            <span className="profile-label">
              Session {sessionId.slice(0, 8)} · {agentId}
            </span>
            {usage && <UsageBadge usage={usage} className="header-usage-badge" />}
          </div>
          {onDeleteSession && (
            <button
              type="button"
              className="chat-header-delete"
              aria-label="Delete session"
              title="Delete session"
              onClick={() => {
                if (!window.confirm("Delete this session? This cannot be undone.")) return;
                void onDeleteSession(sessionId);
              }}
            >
              <span className="material-icons-round">delete</span>
            </button>
          )}
        </header>
        <div className="copilot-chat-body">
          <CopilotChat agentId={agentId} className="emperor-copilot-chat" throttleMs={0} />
        </div>
      </div>
    </CopilotKit>
  );
}
