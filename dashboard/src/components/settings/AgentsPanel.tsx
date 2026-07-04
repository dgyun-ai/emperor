import { useEffect, useState } from "react";
import { shiba, ShibaAgent } from "../../api/shibaAdapter";
import {
  FieldRow,
  FieldRowStack,
  SettingsPanel,
  SettingsToast,
} from "./SettingsPanel";

const EMPTY_FORM = {
  id: "",
  name: "",
  description: "",
  system_prompt: "",
  model: "",
  toolsets: "core,file,terminal,web,todo,kanban,cron",
};

export default function AgentsPanel() {
  const [agents, setAgents] = useState<ShibaAgent[]>([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const reload = async () => {
    const data = await shiba.agentsList();
    setAgents(data.agents);
  };

  useEffect(() => {
    shiba.agentsList()
      .then((data) => {
        setAgents(data.agents);
        if (data.agents.length && !editingId) {
          startEdit(data.agents[0]);
        }
      })
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setMessage(null);
  };

  const startEdit = (agent: ShibaAgent) => {
    setEditingId(agent.id);
    setForm({
      id: agent.id,
      name: agent.name,
      description: agent.description,
      system_prompt: agent.system_prompt,
      model: agent.model,
      toolsets: (agent.toolsets || []).join(","),
    });
    setMessage(null);
  };

  const save = async () => {
    const payload = {
      name: form.name.trim(),
      description: form.description.trim(),
      system_prompt: form.system_prompt,
      model: form.model.trim(),
      toolsets: form.toolsets.split(",").map((t) => t.trim()).filter(Boolean),
    };
    if (!payload.name) {
      setMessage("Name is required.");
      return;
    }
    if (editingId) {
      await shiba.agentsUpdate(editingId, payload);
      setMessage("Agent updated.");
    } else {
      const id = form.id.trim();
      if (!id) {
        setMessage("Agent id is required.");
        return;
      }
      await shiba.agentsCreate({ id, ...payload });
      setMessage("Agent created.");
    }
    await reload();
    if (!editingId) {
      setForm(EMPTY_FORM);
    }
  };

  const remove = async (agent: ShibaAgent) => {
    if (!window.confirm(`Delete agent "${agent.name}"?`)) return;
    await shiba.agentsDelete(agent.id);
    if (editingId === agent.id) {
      startCreate();
    }
    await reload();
    setMessage("Agent deleted.");
  };

  return (
    <SettingsPanel
      title="Agents"
      divider="Multi-agent configuration"
      actions={
        <button type="button" className="btn-action" onClick={startCreate}>
          New agent
        </button>
      }
    >
      <SettingsToast message={message} />

      <div className="agents-split">
        <div className="agents-split-list">
          {agents.map((agent) => (
            <div
              key={agent.id}
              className={`skill-card ${editingId === agent.id ? "active" : ""}`}
            >
              <button type="button" className="skill-card-body agent-list-btn" onClick={() => startEdit(agent)}>
                <div className="skill-card-name">{agent.name}</div>
                <div className="skill-card-desc">{agent.description || agent.id}</div>
                <div className="skill-card-meta">
                  <span className="skill-badge workspace">{agent.id}</span>
                </div>
              </button>
              <div className="skill-card-actions">
                <button
                  type="button"
                  className="btn-icon danger"
                  onClick={() => void remove(agent)}
                  aria-label="Delete agent"
                >
                  <span className="material-icons-round">delete</span>
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="agents-split-detail">
          <h4>{editingId ? `Edit ${editingId}` : "Create agent"}</h4>
          {!editingId && (
            <FieldRow label="Agent id">
              <input
                className="form-input"
                value={form.id}
                onChange={(e) => setForm({ ...form, id: e.target.value })}
                placeholder="coder"
              />
            </FieldRow>
          )}
          <FieldRow label="Name">
            <input
              className="form-input"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </FieldRow>
          <FieldRow label="Description">
            <input
              className="form-input"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </FieldRow>
          <FieldRow label="Model override">
            <input
              className="form-input"
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
              placeholder="Optional"
            />
          </FieldRow>
          <FieldRow label="Toolsets">
            <input
              className="form-input"
              value={form.toolsets}
              onChange={(e) => setForm({ ...form, toolsets: e.target.value })}
            />
          </FieldRow>
          <FieldRowStack label="System prompt override">
            <textarea
              className="form-input"
              rows={6}
              value={form.system_prompt}
              onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
              placeholder="Optional custom system prompt"
            />
          </FieldRowStack>
          <button type="button" className="btn-primary" onClick={() => void save()}>
            {editingId ? "Update agent" : "Create agent"}
          </button>
        </div>
      </div>
    </SettingsPanel>
  );
}
