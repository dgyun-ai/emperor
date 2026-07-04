import { useEffect, useState } from "react";
import { AutomationJob, shiba } from "../../api/shibaAdapter";

type Props = {
  open: boolean;
  onClose: () => void;
};

export default function AutomationModal({ open, onClose }: Props) {
  const [jobs, setJobs] = useState<AutomationJob[]>([]);
  const [name, setName] = useState("Job");
  const [at, setAt] = useState("");
  const [message, setMessage] = useState("");
  const [sessionId, setSessionId] = useState("");

  const reload = () => shiba.automationJobs().then((d) => setJobs(d.jobs));

  useEffect(() => {
    if (open) reload().catch(() => undefined);
  }, [open]);

  const create = async () => {
    if (!message.trim() || !sessionId.trim() || !at.trim()) return;
    await shiba.automationCreate({
      name,
      schedule: { kind: "at", at: new Date(at).toISOString() },
      payload: { kind: "agentTurn", message },
      target_session_id: sessionId,
      enabled: true,
    });
    setMessage("");
    await reload();
  };

  if (!open) return null;

  return (
    <div className="modal-overlay active" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Automation</h2>
          <button type="button" className="btn-close" onClick={onClose}>
            <span className="material-icons-round">close</span>
          </button>
        </div>
        <div className="modal-body">
          <div className="form-row">
            <label>Name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="form-row">
            <label>Run At</label>
            <input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} />
          </div>
          <div className="form-row">
            <label>Session ID</label>
            <input value={sessionId} onChange={(e) => setSessionId(e.target.value)} />
          </div>
          <div className="form-row">
            <label>Message</label>
            <input value={message} onChange={(e) => setMessage(e.target.value)} />
          </div>
          <button type="button" className="btn-action" onClick={create}>
            Add Job
          </button>
          <ul className="job-list">
            {jobs.map((j) => (
              <li key={j.id}>
                <code>{j.schedule.kind}</code> — {j.name} — {j.payload.kind}
                <button type="button" onClick={() => shiba.automationDelete(j.id).then(reload)}>
                  Delete
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
