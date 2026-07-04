import { useCallback, useEffect, useState } from "react";
import {
  apiPost,
  clearToken,
  DashboardBootstrapStatus,
  getProfile,
  publicGet,
  saveProfile,
  saveToken,
} from "./api/client";
import { AGENT_STORAGE_KEY, shiba, ShibaAgent, ShibaSession } from "./api/shibaAdapter";
import Sidebar from "./components/layout/Sidebar";
import SettingsView from "./components/settings/SettingsView";
import ChatWorkspace from "./pages/ChatWorkspace";
import A2uiCopilotPOC from "./pages/A2uiCopilotPOC";
import MonitorPage from "./pages/MonitorPage";
import WelcomePage from "./pages/WelcomePage";
import { useAppState } from "./hooks/useAppState";

type MainView = "chat" | "monitor" | "a2ui-poc";

function loadStoredAgentId(): string {
  return localStorage.getItem(AGENT_STORAGE_KEY) || "default";
}

export default function App() {
  const [boot, setBoot] = useState<DashboardBootstrapStatus | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [bootLoading, setBootLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [mainView, setMainView] = useState<MainView>("chat");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [sessions, setSessions] = useState<ShibaSession[]>([]);
  const [agents, setAgents] = useState<ShibaAgent[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState(loadStoredAgentId);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sessionAgents, setSessionAgents] = useState<Record<string, string>>({});

  const { status, providerLabel, channels, setWorking } = useAppState();

  const refreshAgents = useCallback(async () => {
    const data = await shiba.agentsList();
    setAgents(data.agents);
    if (!data.agents.some((agent) => agent.id === selectedAgentId)) {
      const fallback = data.agents[0]?.id || "default";
      setSelectedAgentId(fallback);
      localStorage.setItem(AGENT_STORAGE_KEY, fallback);
    }
  }, [selectedAgentId]);

  const refreshBoot = async () => {
    setBootLoading(true);
    setBootError(null);
    try {
      const data = await publicGet<DashboardBootstrapStatus>("/api/dashboard/bootstrap/status");
      setBoot(data);
      if (!localStorage.getItem("emperor.dashboard.profile")) {
        saveProfile(data.last_profile);
      }
    } catch (err) {
      setBoot(null);
      setBootError(err instanceof Error ? err.message : String(err));
      throw err;
    } finally {
      setBootLoading(false);
    }
  };

  const refreshApp = async () => {
    const [sessionData] = await Promise.all([shiba.sessions(), refreshAgents()]);
    setSessions(sessionData.sessions);
    const agentMap: Record<string, string> = {};
    for (const session of sessionData.sessions) {
      agentMap[session.id] = session.agent_id || "default";
    }
    setSessionAgents(agentMap);
    if (!activeSessionId && sessionData.sessions.length) {
      setActiveSessionId(sessionData.sessions[0].id);
    }
  };

  const deleteSession = useCallback(async (sessionId: string) => {
    await shiba.sessionDelete(sessionId);
    const data = await shiba.sessions();
    setSessions(data.sessions);
    setActiveSessionId((current) => {
      if (current !== sessionId) return current;
      return data.sessions[0]?.id ?? null;
    });
  }, []);

  const loadSessions = useCallback(async () => {
    const data = await shiba.sessions();
    setSessions(data.sessions);
    const agentMap: Record<string, string> = {};
    for (const session of data.sessions) {
      agentMap[session.id] = session.agent_id || "default";
    }
    setSessionAgents(agentMap);
  }, []);

  useEffect(() => {
    refreshBoot().catch(() => undefined);
    const params = new URLSearchParams(window.location.search);
    if (params.get("view") === "a2ui-poc") {
      setMainView("a2ui-poc");
    }
  }, []);

  useEffect(() => {
    if (!boot?.initialized) return;
    const token = localStorage.getItem("emperor.dashboard.token");
    if (!token) {
      setAuthenticated(false);
      return;
    }
    apiPost<{ ok: boolean; last_profile: string }>("/api/dashboard/auth/login", { token }, true)
      .then(async (data) => {
        saveProfile(getProfile() || data.last_profile);
        setAuthenticated(true);
        await refreshApp();
      })
      .catch(() => {
        clearToken();
        setAuthenticated(false);
      });
  }, [boot?.initialized]);

  const newSession = async () => {
    const res = await shiba.createSession({ agent_id: selectedAgentId });
    setActiveSessionId(res.session_id);
    setSessionAgents((current) => ({ ...current, [res.session_id]: selectedAgentId }));
    setMainView("chat");
    await loadSessions();
  };

  const handleSelectAgent = (agentId: string) => {
    setSelectedAgentId(agentId);
    localStorage.setItem(AGENT_STORAGE_KEY, agentId);
  };

  const activeAgentId = activeSessionId
    ? sessionAgents[activeSessionId] || selectedAgentId
    : selectedAgentId;

  if (bootLoading && !boot) {
    return <div className="boot-screen">正在加载 Emperor 控制台…</div>;
  }

  if (!boot) {
    return (
      <div className="boot-screen">
        <div className="login-card boot-error-panel">
          <h2>无法连接 Dashboard</h2>
          <p className="inline-error">{bootError || "未知错误"}</p>
          <p>请访问 <code>http://127.0.0.1:9119/</code></p>
          <button className="login-btn" onClick={() => refreshBoot().catch(() => undefined)}>
            重试
          </button>
        </div>
      </div>
    );
  }

  if (!boot.initialized || !authenticated) {
    return (
      <WelcomePage
        initialized={boot.initialized}
        profiles={boot.profiles}
        onBootstrapped={async (token, profile) => {
          saveToken(token);
          saveProfile(profile);
          await refreshBoot();
          setAuthenticated(true);
          await refreshApp();
        }}
        onLoggedIn={async (token, profile) => {
          saveToken(token);
          saveProfile(profile);
          setAuthenticated(true);
          await refreshApp();
        }}
      />
    );
  }

  return (
    <div className="app-container" id="app-container">
      <Sidebar
        sessions={sessions}
        agents={agents}
        activeId={activeSessionId}
        activeView={mainView}
        selectedAgentId={selectedAgentId}
        status={status}
        providerLabel={providerLabel}
        channels={channels}
        onNewSession={newSession}
        onSelectSession={(id) => {
          setActiveSessionId(id);
          setMainView("chat");
        }}
        onDeleteSession={deleteSession}
        onSelectAgent={handleSelectAgent}
        onOpenMonitor={() => setMainView("monitor")}
        onOpenSettings={() => setSettingsOpen(true)}
        onLogout={() => {
          clearToken();
          setAuthenticated(false);
        }}
        mobileOpen={mobileNavOpen}
        onToggleMobile={() => setMobileNavOpen((v) => !v)}
      />

      <main className={mainView === "chat" ? "chat-area" : "main-content"} id={mainView === "chat" ? "chat-area" : undefined}>
        {mainView === "chat" && (
          <ChatWorkspace
            sessionId={activeSessionId}
            agentId={activeAgentId}
            onProcessingChange={setWorking}
            onChatComplete={loadSessions}
            onDeleteSession={deleteSession}
            onOpenMobileNav={() => setMobileNavOpen(true)}
          />
        )}
        {mainView === "monitor" && (
          <MonitorPage
            onOpenSession={(sessionId) => {
              setActiveSessionId(sessionId);
              setMainView("chat");
            }}
          />
        )}
        {mainView === "a2ui-poc" && (
          <A2uiCopilotPOC
            sessionId={activeSessionId}
            onProcessingChange={setWorking}
          />
        )}
      </main>

      <SettingsView open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
