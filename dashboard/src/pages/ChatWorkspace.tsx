import { useEffect, useRef, useState } from "react";
import ChatHistory from "../components/chat/ChatHistory";
import CopilotChatWorkspace from "./CopilotChatWorkspace";
import { useRealtime } from "../hooks/useRealtime";
import { shiba } from "../api/shibaAdapter";

type Props = {
  sessionId: string | null;
  agentId?: string;
  onProcessingChange?: (working: boolean) => void;
  onChatComplete?: () => void;
  onDeleteSession?: (sessionId: string) => void | Promise<void>;
  onOpenMobileNav?: () => void;
};

export default function ChatWorkspace({
  sessionId,
  agentId = "default",
  onProcessingChange,
  onChatComplete,
  onDeleteSession,
  onOpenMobileNav,
}: Props) {
  const [input, setInput] = useState("");
  const [askUserQuestionsEnabled, setAskUserQuestionsEnabled] = useState(true);
  const [a2uiEnabled, setA2uiEnabled] = useState(false);
  const [copilotProcessing, setCopilotProcessing] = useState(false);
  const rt = useRealtime(sessionId, { askUserQuestionsEnabled, a2uiEnabled });
  const wasProcessing = useRef(false);
  const processing = a2uiEnabled ? copilotProcessing : rt.processing;

  useEffect(() => {
    shiba.settingsGet().then((settings) => {
      setAskUserQuestionsEnabled(settings.ask_user_questions ?? true);
      setA2uiEnabled(settings.a2ui_enabled ?? false);
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!sessionId) {
      rt.reset();
      return;
    }
    rt.reset();
    rt.loadHistory(sessionId).catch(() => undefined);
  }, [sessionId]);

  useEffect(() => {
    onProcessingChange?.(processing);
  }, [processing, onProcessingChange]);

  useEffect(() => {
    if (wasProcessing.current && !processing) {
      onChatComplete?.();
      if (a2uiEnabled && sessionId) {
        rt.loadHistory(sessionId).catch(() => undefined);
      }
    }
    wasProcessing.current = processing;
  }, [processing, onChatComplete, a2uiEnabled, sessionId]);

  const handleSend = () => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    rt.send(text, rt.processing);
  };

  const handleSelectQuestion = (question: string) => {
    setInput("");
    rt.send(question, rt.processing);
  };

  if (a2uiEnabled && sessionId) {
    return (
      <CopilotChatWorkspace
        sessionId={sessionId}
        agentId={agentId}
        usage={rt.usage}
        onProcessingChange={setCopilotProcessing}
        onChatComplete={onChatComplete}
        onDeleteSession={onDeleteSession}
        onOpenMobileNav={onOpenMobileNav}
      />
    );
  }

  return (
    <ChatHistory
      timeline={rt.timeline}
      streamText={rt.streamText}
      streamA2ui={rt.streamA2ui}
      processing={rt.processing}
      usage={rt.usage}
      input={input}
      sessionId={sessionId}
      onInputChange={setInput}
      onSend={handleSend}
      onAbort={rt.abort}
      onToggleGroup={rt.toggleProcessGroup}
      onDeleteSession={onDeleteSession}
      onOpenMobileNav={onOpenMobileNav}
      onSelectQuestion={handleSelectQuestion}
      onA2uiAction={(action) => {
        void rt.sendA2uiAction(action);
      }}
      a2uiEnabled={a2uiEnabled}
    />
  );
}
