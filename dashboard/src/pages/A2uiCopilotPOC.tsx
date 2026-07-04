import { useEffect, useMemo, useState } from "react";
import { CopilotChat, CopilotKit } from "@copilotkit/react-core/v2";
import "@copilotkit/react-core/v2/styles.css";
import { shiba } from "../api/shibaAdapter";
import { copilotKitHeaders } from "../a2ui/copilotKitHeaders";
import CopilotProcessingBridge from "../components/chat/CopilotProcessingBridge";

type Props = {
  sessionId: string | null;
  onProcessingChange?: (working: boolean) => void;
};

/**
 * Standalone CopilotKit + A2UI POC page.
 * Uses AG-UI endpoint at /api/ag-ui with threadId mapped to Emperor sessionId.
 */
export default function A2uiCopilotPOC({ sessionId, onProcessingChange }: Props) {
  const [ready, setReady] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const headers = useMemo(() => copilotKitHeaders(), []);

  useEffect(() => {
    shiba.settingsGet()
      .then((settings) => {
        setEnabled(settings.a2ui_enabled ?? false);
        setReady(true);
      })
      .catch(() => setReady(true));
  }, []);

  if (!ready) {
    return <div className="boot-screen">Loading A2UI CopilotKit POC…</div>;
  }

  if (!enabled) {
    return (
      <div className="boot-screen">
        <div className="login-card">
          <h2>A2UI POC</h2>
          <p>Enable A2UI in Settings before using the CopilotKit POC.</p>
        </div>
      </div>
    );
  }

  if (!sessionId) {
    return (
      <div className="boot-screen">
        <div className="login-card">
          <h2>A2UI POC</h2>
          <p>Select or create a session in the sidebar first.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="a2ui-copilot-poc" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <header className="chat-header">
        <div className="chat-header-info">
          <span className="profile-label">A2UI CopilotKit POC · {sessionId.slice(0, 8)}</span>
        </div>
      </header>
      <div style={{ flex: 1, minHeight: 0 }}>
        <CopilotKit
          runtimeUrl="/api/ag-ui"
          threadId={sessionId}
          headers={headers}
          a2ui={{}}
          onError={({ error }) => {
            console.error("[A2UI POC]", error);
          }}
        >
          <CopilotProcessingBridge onProcessingChange={onProcessingChange} />
          <CopilotChat agentId="default" className="h-full" />
        </CopilotKit>
      </div>
    </div>
  );
}
