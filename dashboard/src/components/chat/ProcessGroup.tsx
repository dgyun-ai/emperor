import { useEffect, useState } from "react";
import type { ProcessGroupState } from "../../hooks/useRealtime";

type Props = {
  group: ProcessGroupState;
  onToggle: () => void;
};

function stepLabel(badge: "GEN" | "EXE") {
  return badge === "GEN" ? "推理" : "工具";
}

export default function ProcessGroup({ group, onToggle }: Props) {
  const [now, setNow] = useState(() => Date.now());
  const active = group.endTime == null;
  const done = group.endTime != null;

  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);

  const endMs = group.endTime ?? now;
  const elapsed = Math.max(1, Math.round((endMs - group.startTime) / 1000));
  const reasoningSteps = group.steps.filter((step) => step.badge === "GEN");
  const toolSteps = group.steps.filter((step) => step.badge === "EXE");
  const latestStep = group.steps[group.steps.length - 1];
  const reasoningText = reasoningSteps.map((step) => step.text).join("");

  const headerTitle = (() => {
    if (!done) return "思考中…";
    const parts: string[] = [];
    if (reasoningText) parts.push("推理");
    if (toolSteps.length > 0) parts.push(`${toolSteps.length} 次工具`);
    if (parts.length === 0) return "已完成思考";
    return `已完成思考 · ${parts.join(" · ")}`;
  })();

  return (
    <div
      className={`process-group ${group.collapsed ? "completed" : "expanded"} ${active ? "active" : ""}`}
    >
      <button type="button" className="process-group-header" onClick={onToggle}>
        <span className="pg-expand-icon" aria-hidden />
        <span className={`pg-title ${active ? "shiny-text" : ""}`}>{headerTitle}</span>
        {!group.collapsed && latestStep && (
          <span className={`step-badge ${latestStep.badge}`}>{stepLabel(latestStep.badge)}</span>
        )}
        <span className="pg-time">{elapsed}s</span>
        {group.collapsed && done && (
          <span className="pg-summary">{group.steps.length} 步</span>
        )}
      </button>
      {!group.collapsed && (
        <div className="pg-content">
          {reasoningText && (
            <div className="pg-section">
              <div className="pg-section-label">推理过程</div>
              <div className="pg-step pg-step-gen pg-step-gen-merged">
                <span className="step-badge GEN">推理</span>
                <span className="pg-step-text">{reasoningText}</span>
              </div>
            </div>
          )}
          {toolSteps.length > 0 && (
            <div className="pg-section">
              <div className="pg-section-label">工具调用</div>
              {toolSteps.map((step) => (
                <div key={step.id} className="pg-step pg-step-exe">
                  <span className={`step-badge ${step.badge}`}>{stepLabel(step.badge)}</span>
                  <span className="pg-step-text">{step.text}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
