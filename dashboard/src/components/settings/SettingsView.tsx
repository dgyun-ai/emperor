import { useEffect, useState } from "react";
import { shiba, ShibaSettings } from "../../api/shibaAdapter";
import AgentPanel from "./AgentPanel";
import AgentsPanel from "./AgentsPanel";
import GatewayPanel from "./GatewayPanel";
import McpPanel from "./McpPanel";
import ProviderPanel from "./ProviderPanel";
import SkillsPanel from "./SkillsPanel";
import { SettingsToast } from "./SettingsPanel";

const TAB_STORAGE_KEY = "emperor.settings.tab";

const TABS = [
  { id: "agent", label: "Agent", icon: "smart_toy" },
  { id: "agents", label: "Agents", icon: "groups" },
  { id: "provider", label: "Provider", icon: "dns" },
  { id: "skills", label: "Skills", icon: "school" },
  { id: "mcp", label: "MCP", icon: "hub" },
  { id: "gateway", label: "Gateway", icon: "router" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function loadStoredTab(): TabId {
  const stored = localStorage.getItem(TAB_STORAGE_KEY);
  if (stored && TABS.some((tab) => tab.id === stored)) {
    return stored as TabId;
  }
  return "agent";
}

type Props = {
  open: boolean;
  onClose: () => void;
};

export default function SettingsView({ open, onClose }: Props) {
  const [tab, setTab] = useState<TabId>(loadStoredTab);
  const [settings, setSettings] = useState<ShibaSettings>({});
  const [plugins, setPlugins] = useState<Array<{ name: string; version: string }>>([]);
  const [oauth, setOauth] = useState<Array<{ id: string; name: string; configured: boolean }>>([]);
  const [testMsg, setTestMsg] = useState<string | null>(null);
  const [toolsets, setToolsets] = useState("");

  const selectTab = (next: TabId) => {
    setTab(next);
    localStorage.setItem(TAB_STORAGE_KEY, next);
  };

  const reload = async () => {
    const [s, pl, oa] = await Promise.all([
      shiba.settingsGet(),
      shiba.plugins(),
      shiba.oauthProviders(),
    ]);
    setSettings(s);
    setToolsets((s.toolsets || []).join(","));
    setPlugins(pl.plugins);
    setOauth(oa.providers);
  };

  useEffect(() => {
    if (open) reload().catch(() => undefined);
  }, [open]);

  const patchSettings = (patch: Partial<ShibaSettings>) => {
    setSettings((current) => ({ ...current, ...patch }));
  };

  const save = async () => {
    await shiba.settingsPost({
      provider: settings.provider,
      model: settings.model,
      base_url: settings.base_url,
      api_key: settings.api_key,
      api_key_env: settings.api_key_env,
      toolsets: toolsets.split(",").map((t) => t.trim()).filter(Boolean),
      ui_language: settings.ui_language,
      lane_by_profile: settings.lane_by_profile,
      ask_user_questions: settings.ask_user_questions,
      a2ui_enabled: settings.a2ui_enabled,
      gateway: settings.gateway,
    });
    setTestMsg("Settings saved.");
  };

  if (!open) return null;

  return (
    <div className="modal-backdrop active" onClick={onClose}>
      <div className="modal modal-settings" onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <h2>
            <span className="material-icons-round">settings</span>
            Settings
          </h2>
          <button type="button" className="btn-icon" onClick={onClose} aria-label="Close settings">
            <span className="material-icons-round">close</span>
          </button>
        </div>

        <div className="settings-view">
          <div className="settings-layout">
            <nav className="settings-sidebar">
              {TABS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`settings-sidebar-item ${tab === item.id ? "active" : ""}`}
                  onClick={() => selectTab(item.id)}
                >
                  <span className="material-icons-round">{item.icon}</span>
                  {item.label}
                </button>
              ))}
            </nav>

            <div className="settings-content">
              <SettingsToast message={testMsg} />

              {tab === "agent" && (
                <AgentPanel
                  settings={settings}
                  toolsets={toolsets}
                  onSettingsChange={patchSettings}
                  onToolsetsChange={setToolsets}
                />
              )}
              {tab === "agents" && <AgentsPanel />}
              {tab === "provider" && (
                <ProviderPanel
                  settings={settings}
                  oauth={oauth}
                  plugins={plugins}
                  onChange={patchSettings}
                  onTestMessage={setTestMsg}
                />
              )}
              {tab === "skills" && <SkillsPanel />}
              {tab === "mcp" && <McpPanel />}
              {tab === "gateway" && (
                <GatewayPanel settings={settings} onSettingsChange={patchSettings} onMessage={setTestMsg} />
              )}
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn-primary" onClick={() => void save()}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
