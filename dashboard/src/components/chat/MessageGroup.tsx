import MarkdownContent from "./MarkdownContent";
import AskUserQuestions from "./AskUserQuestions";
import A2uiSurfaceHost from "./A2uiSurfaceHost";
import { EMPEROR_AVATAR_URL, MINISTER_AVATAR_URL } from "../../constants/branding";
import type { TimelineA2uiSurface } from "../../utils/chatTimeline";

type Props = {
  role: "user" | "assistant" | "error";
  content: string;
  timestamp?: number;
  streaming?: boolean;
  followUpQuestions?: string[];
  showFollowUpQuestions?: boolean;
  onSelectQuestion?: (question: string) => void;
  followUpDisabled?: boolean;
  a2uiSurfaces?: TimelineA2uiSurface[];
  onA2uiAction?: (action: Record<string, unknown>) => void;
  a2uiDisabled?: boolean;
};

export default function MessageGroup({
  role,
  content,
  timestamp,
  streaming = false,
  followUpQuestions,
  showFollowUpQuestions = false,
  onSelectQuestion,
  followUpDisabled = false,
  a2uiSurfaces,
  onA2uiAction,
  a2uiDisabled = false,
}: Props) {
  const type = role === "user" ? "user" : role === "error" ? "error" : "agent";
  const avatarUrl = role === "user" ? EMPEROR_AVATAR_URL : MINISTER_AVATAR_URL;
  const timeLabel = timestamp
    ? new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : null;
  const hasA2ui = Boolean(a2uiSurfaces?.some((surface) => surface.messages.length > 0));
  const hasText = Boolean(content.trim());

  return (
    <div className={`message-group ${type} show-avatar`}>
      <div className="message-avatar">
        <img
          src={avatarUrl}
          alt={role === "user" ? "Emperor" : "Minister"}
          className={role === "user" ? "user-avatar-img" : "agent-avatar-img"}
        />
      </div>
      <div className="message-content">
        {role === "error" ? (
          <div className="message-bubble message-error-bubble">{content}</div>
        ) : hasA2ui ? (
          <div className="message-bubble assistant-composite-bubble">
            {a2uiSurfaces!.map((surface) => (
              <div key={surface.surfaceId} className="message-a2ui-section">
                <A2uiSurfaceHost
                  messages={surface.messages}
                  onAction={onA2uiAction}
                  disabled={a2uiDisabled}
                />
              </div>
            ))}
            {hasText && (
              <div className="message-text-section">
                <MarkdownContent content={content} className="message-text-inner" allowHtml />
              </div>
            )}
          </div>
        ) : (
          <MarkdownContent content={content} allowHtml={role === "assistant"} />
        )}
        {!streaming && (
          <div className="message-meta">
            {timeLabel && <div className="message-time">{timeLabel}</div>}
            {hasText && (
              <button
                type="button"
                className="btn-copy-msg"
                title="Copy"
                onClick={() => navigator.clipboard.writeText(content)}
              >
                <span className="material-icons-round">content_copy</span>
              </button>
            )}
          </div>
        )}
        {role === "assistant" &&
          showFollowUpQuestions &&
          followUpQuestions &&
          followUpQuestions.length > 0 &&
          onSelectQuestion && (
            <AskUserQuestions
              questions={followUpQuestions}
              onSelect={onSelectQuestion}
              disabled={followUpDisabled}
            />
          )}
      </div>
    </div>
  );
}
