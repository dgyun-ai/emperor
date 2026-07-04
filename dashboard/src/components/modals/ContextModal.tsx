import { useEffect, useState } from "react";
import { shiba } from "../../api/shibaAdapter";

type Props = {
  open: boolean;
  onClose: () => void;
};

export default function ContextModal({ open, onClose }: Props) {
  const [prompt, setPrompt] = useState("");
  const [estimate, setEstimate] = useState(0);

  useEffect(() => {
    if (!open) return;
    shiba.context().then((d) => {
      setPrompt(d.system_prompt);
      setEstimate(d.token_estimate);
    });
  }, [open]);

  if (!open) return null;

  return (
    <div className="modal-overlay active" onClick={onClose}>
      <div className="modal-content context-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Context (~{estimate} tokens)</h2>
          <button type="button" className="btn-close" onClick={onClose}>
            <span className="material-icons-round">close</span>
          </button>
        </div>
        <pre className="context-viewer">{prompt}</pre>
      </div>
    </div>
  );
}
