import { useEffect, useRef } from "react";
import MessageGroup from "./MessageGroup";
import ProcessGroup from "./ProcessGroup";
import Composer from "./Composer";
import UsageBadge from "./UsageBadge";
import type { TimelineItem } from "../../hooks/useRealtime";
import type { TimelineA2uiSurface } from "../../utils/chatTimeline";
import { LOGO_URL } from "../../constants/branding";
import type { UsageSnapshot } from "../../utils/usageSnapshot";

type Props = {
  timeline: TimelineItem[];
  streamText: string;
  streamA2ui?: TimelineA2uiSurface[];
  processing: boolean;
  usage: UsageSnapshot | Record<string, unknown> | null;
  input: string;
  sessionId: string | null;
  onInputChange: (v: string) => void;
  onSend: () => void;
  onAbort: () => void;
  onToggleGroup: (id: string) => void;
  onDeleteSession?: (sessionId: string) => void | Promise<void>;
  onOpenMobileNav?: () => void;
  onSelectQuestion?: (question: string) => void;
  onA2uiAction?: (action: Record<string, unknown>) => void;
  a2uiEnabled?: boolean;
};

export default function ChatHistory({
  timeline,
  streamText,
  streamA2ui = [],
  processing,
  usage,
  input,
  sessionId,
  onInputChange,
  onSend,
  onAbort,
  onToggleGroup,
  onDeleteSession,
  onOpenMobileNav,
  onSelectQuestion,
  onA2uiAction,
  a2uiEnabled = false,
}: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  const chatActive =
    Boolean(sessionId) ||
    timeline.length > 0 ||
    Boolean(streamText) ||
    streamA2ui.length > 0 ||
    processing;
  const showLiveAssistant =
    Boolean(streamText.trim()) || streamA2ui.some((surface) => surface.messages.length > 0);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [timeline, streamText, streamA2ui, processing]);

  return (
    <>
      <header className="chat-header">
        <button type="button" className="mobile-menu-btn" onClick={onOpenMobileNav} aria-label="Open menu">
          <span className="material-icons-round">menu</span>
        </button>
        <div className="chat-header-info">
          <span className="profile-label">{sessionId ? `Session ${sessionId.slice(0, 8)}` : "Emperor Chat"}</span>
          {usage && <UsageBadge usage={usage} className="header-usage-badge" />}
        </div>
        {sessionId && onDeleteSession && (
          <button
            type="button"
            className="chat-header-delete"
            aria-label="Delete session"
            title="Delete session"
            disabled={processing}
            onClick={() => {
              if (!window.confirm("Delete this session? This cannot be undone.")) return;
              void onDeleteSession(sessionId);
            }}
          >
            <span className="material-icons-round">delete</span>
          </button>
        )}
      </header>

      {!chatActive && (
        <div className="welcome-screen" id="welcome-screen">
          <div className="welcome-content">
            <img src={LOGO_URL} alt="Emperor" className="welcome-logo" />
            <h2 className="welcome-title">
              Welcome to <span className="gradient-text">Emperor</span>
            </h2>
            <p className="welcome-subtitle">
              ShibaClaw-style agent workspace. Start a new session or pick one from the sidebar.
            </p>
          </div>
        </div>
      )}

      <div className={`chat-history ${chatActive ? "active" : ""}`} id="chat-history">
        {timeline.map((item) =>
          item.kind === "message" ? (
            <MessageGroup
              key={item.id}
              role={item.role}
              content={item.content}
              timestamp={item.timestamp}
              followUpQuestions={item.followUpQuestions}
              showFollowUpQuestions={!processing && !streamText && streamA2ui.length === 0}
              onSelectQuestion={onSelectQuestion}
              followUpDisabled={processing}
              a2uiSurfaces={item.a2uiSurfaces}
              onA2uiAction={onA2uiAction}
              a2uiDisabled={processing || !a2uiEnabled}
            />
          ) : item.kind === "process" ? (
            <div className="process-group-row" key={item.id}>
              <ProcessGroup group={item.group} onToggle={() => onToggleGroup(item.id)} />
            </div>
          ) : null
        )}
        {showLiveAssistant && (
          <MessageGroup
            role="assistant"
            content={streamText}
            streaming={processing}
            a2uiSurfaces={streamA2ui}
            onA2uiAction={onA2uiAction}
            a2uiDisabled={!a2uiEnabled}
          />
        )}
        {processing && !showLiveAssistant && (
          <div className="message-group agent" id="typing-bubble">
            <div className="message-content">
              <div className="message-bubble typing-bubble">
                <span className="typing-dot" />
                <span className="typing-dot" />
                <span className="typing-dot" />
              </div>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="input-area">
        <div className="input-wrapper">
          {usage && <UsageBadge usage={usage} />}
          <Composer
            value={input}
            onChange={onInputChange}
            onSend={onSend}
            onAbort={onAbort}
            processing={processing}
          />
        </div>
      </div>
    </>
  );
}
