import { useEffect, useState } from "react";
import type { AppStatus } from "../../hooks/useAppState";
import type { ShibaAgent, ShibaSession } from "../../api/shibaAdapter";
import { LOGO_URL } from "../../constants/branding";

type Props = {
  sessions: ShibaSession[];
  agents: ShibaAgent[];
  activeId: string | null;
  activeView: "chat" | "monitor" | "a2ui-poc";
  selectedAgentId: string;
  status: AppStatus;
  providerLabel: string;
  channels: string[];
  onNewSession: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void | Promise<void>;
  onSelectAgent: (agentId: string) => void;
  onOpenMonitor: () => void;
  onOpenSettings: () => void;
  onLogout: () => void;
  mobileOpen: boolean;
  onToggleMobile: () => void;
};

const STATUS_LABEL: Record<AppStatus, string> = {
  connecting: "Connecting…",
  ready: "Ready",
  working: "Working…",
  "gateway-down": "Gateway down",
  "not-configured": "Not configured",
};

function sessionLabel(session: ShibaSession): string {
  return session.nickname || session.title || session.id.slice(0, 8);
}

export default function Sidebar({
  sessions,
  agents,
  activeId,
  activeView,
  selectedAgentId,
  status,
  providerLabel,
  channels,
  onNewSession,
  onSelectSession,
  onDeleteSession,
  onSelectAgent,
  onOpenMonitor,
  onOpenSettings,
  onLogout,
  mobileOpen,
  onToggleMobile,
}: Props) {
  const [menuSessionId, setMenuSessionId] = useState<string | null>(null);
  const [agentFilter, setAgentFilter] = useState<string>("all");
  const statusClass =
    status === "ready" ? "connected" : status === "working" ? "working" : "disconnected";

  useEffect(() => {
    if (!menuSessionId) return;
    const close = () => setMenuSessionId(null);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [menuSessionId]);

  const handleDelete = async (session: ShibaSession) => {
    const label = sessionLabel(session);
    if (!window.confirm(`Delete session "${label}"? This cannot be undone.`)) {
      return;
    }
    setMenuSessionId(null);
    await onDeleteSession(session.id);
  };

  const filteredSessions = sessions.filter((session) => {
    if (agentFilter === "all") return true;
    return (session.agent_id || "default") === agentFilter;
  });

  return (
    <>
      {mobileOpen && <div className="sidebar-backdrop" onClick={onToggleMobile} />}
      <aside className={`sidebar ${mobileOpen ? "open" : ""}`} id="sidebar">
        <div className="sidebar-header">
          <div className="logo">
            <img src={LOGO_URL} alt="Emperor" className="logo-icon" />
            <div className="logo-text">
              <h1>Emperor</h1>
              <div className="header-sub-row">
                <span className="version">v0.1.0</span>
                <div className="status-micro" id="status-card">
                  <div className={`status-dot ${statusClass}`} id="status-dot" />
                  <span className="status-text" id="status-text">
                    {STATUS_LABEL[status]}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <button type="button" className="sidebar-toggle" onClick={onToggleMobile} aria-label="Toggle sidebar">
            <span className="material-icons-round">menu</span>
          </button>
        </div>

        <div className="sidebar-actions">
          <div className="sidebar-agent-picker">
            <label htmlFor="sidebar-agent-select">Agent</label>
            <select
              id="sidebar-agent-select"
              value={selectedAgentId}
              onChange={(e) => onSelectAgent(e.target.value)}
            >
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name}
                </option>
              ))}
            </select>
          </div>
          <button type="button" className="btn-action btn-new-chat" id="btn-new-session" onClick={onNewSession}>
            <span className="material-icons-round">add_circle</span>
            <span>New Session</span>
          </button>
        </div>

        <div className="sidebar-section history-section">
          <div className="section-title-row">
            <div className="section-title">SESSIONS</div>
            <select
              className="session-agent-filter"
              value={agentFilter}
              onChange={(e) => setAgentFilter(e.target.value)}
              aria-label="Filter sessions by agent"
            >
              <option value="all">All agents</option>
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name}
                </option>
              ))}
            </select>
          </div>
          <div id="history-list" className="history-list">
            {filteredSessions.length === 0 && <div className="history-item loading">No sessions</div>}
            {filteredSessions.map((s) => (
              <div
                key={s.id}
                className={`history-item ${activeId === s.id ? "active" : ""}`}
              >
                <button
                  type="button"
                  className="history-item-main"
                  onClick={() => onSelectSession(s.id)}
                >
                  <div className="session-info">
                    <span className="session-name">{sessionLabel(s)}</span>
                    <span className="session-subline">
                      <span className="ob-badge badge-agent">{s.agent_id || "default"}</span>
                      <span className="ob-badge badge-channel-webui">{s.message_count} msgs</span>
                    </span>
                  </div>
                </button>
                <div className="session-actions">
                  <button
                    type="button"
                    className={`btn-session-menu ${menuSessionId === s.id ? "active" : ""}`}
                    aria-label="Session actions"
                    onClick={(event) => {
                      event.stopPropagation();
                      setMenuSessionId((current) => (current === s.id ? null : s.id));
                    }}
                  >
                    <span className="material-icons-round">more_vert</span>
                  </button>
                  {menuSessionId === s.id && (
                    <div className="session-dropdown active" onClick={(event) => event.stopPropagation()}>
                      <button
                        type="button"
                        className="dropdown-item danger"
                        onClick={() => void handleDelete(s)}
                      >
                        <span className="material-icons-round">delete</span>
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="sidebar-section workspace-summary-section" id="workspace-summary">
          <div className="workspace-summary-row">
            <div className={`status-dot ${channels.length ? "connected" : "disconnected"}`} />
            <span>
              Channel: <strong>{channels.join(", ") || "dashboard"}</strong>
            </span>
          </div>
          <div className="workspace-summary-row">
            <div className={`status-dot ${status !== "not-configured" ? "connected" : "disconnected"}`} />
            <span className="workspace-provider">
              Provider: <strong>{providerLabel}</strong>
            </span>
          </div>
        </div>

        <div className="sidebar-footer">
          <button
            type="button"
            className={`btn-command btn-monitor ${activeView === "monitor" ? "active" : ""}`}
            onClick={onOpenMonitor}
            title="Monitor"
          >
            <span className="material-icons-round">monitoring</span>
            <span>Monitor</span>
          </button>
          <button type="button" className="btn-command btn-settings" onClick={onOpenSettings} title="Settings">
            <span className="material-icons-round">settings</span>
            <span>Settings</span>
          </button>
          <button type="button" className="btn-command btn-logout" onClick={onLogout} title="Logout">
            <span className="material-icons-round">logout</span>
          </button>
        </div>
      </aside>
    </>
  );
}
