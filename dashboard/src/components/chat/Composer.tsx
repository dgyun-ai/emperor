import { useEffect, useRef } from "react";

type Props = {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onAbort: () => void;
  processing: boolean;
  disabled?: boolean;
};

export default function Composer({ value, onChange, onSend, onAbort, processing, disabled }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const canSteer = processing && value.trim().length > 0;
  const showStop = processing && !value.trim();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const handleAction = () => {
    if (showStop) {
      onAbort();
      return;
    }
    onSend();
  };

  return (
    <div className="input-container">
      <textarea
        ref={ref}
        id="chat-input"
        placeholder="Message Emperor…"
        rows={1}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (canSteer || (!processing && value.trim())) handleAction();
          }
        }}
      />
      <button
        type="button"
        id={showStop ? "btn-stop" : "btn-send"}
        className={`btn-send${showStop ? " btn-send-stop" : ""}`}
        disabled={!showStop && !canSteer && !value.trim()}
        title={showStop ? "Stop" : processing ? "Steer the agent" : "Send message"}
        onClick={handleAction}
      >
        <span className="material-icons-round">
          {showStop ? "stop" : processing ? "navigation" : "send"}
        </span>
      </button>
    </div>
  );
}
