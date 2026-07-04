import { useEffect, useMemo, useState } from "react";
import { shiba, ShibaSettings } from "../../api/shibaAdapter";
import { FieldRow, FieldRowStack, SettingsPanel, SettingsToast } from "./SettingsPanel";

type Preset = {
  id: string;
  label: string;
  provider: string;
  model: string;
  base_url?: string;
  api_key?: string;
  api_key_env?: string;
};

type Props = {
  settings: ShibaSettings;
  oauth: Array<{ id: string; name: string; configured: boolean }>;
  plugins: Array<{ name: string; version: string }>;
  onChange: (patch: Partial<ShibaSettings>) => void;
  onTestMessage?: (msg: string) => void;
};

const PROVIDER_ICONS: Record<string, string> = {
  openrouter: "hub",
  openai: "smart_toy",
  anthropic: "psychology",
  local: "computer",
  ollama: "computer",
};

function providerIcon(id: string): string {
  const key = id.toLowerCase();
  for (const [name, icon] of Object.entries(PROVIDER_ICONS)) {
    if (key.includes(name)) return icon;
  }
  return "dns";
}

function uniqueProviders(presets: Preset[]): Preset[] {
  const seen = new Set<string>();
  const result: Preset[] = [];
  for (const preset of presets) {
    const key = preset.provider;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(preset);
  }
  return result;
}

export default function ProviderPanel({ settings, oauth, plugins, onChange, onTestMessage }: Props) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [localMsg, setLocalMsg] = useState<string | null>(null);

  useEffect(() => {
    shiba.models().then((data) => {
      setPresets((data.presets as Preset[]) || []);
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (settings.provider) {
      setExpanded(settings.provider);
    }
  }, [settings.provider]);

  const providers = useMemo(() => uniqueProviders(presets), [presets]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return providers;
    return providers.filter(
      (p) =>
        p.provider.toLowerCase().includes(q) ||
        p.label.toLowerCase().includes(q) ||
        p.model.toLowerCase().includes(q)
    );
  }, [providers, query]);

  const configuredCount = providers.filter((p) => settings.provider === p.provider).length;

  const applyPreset = (preset: Preset) => {
    onChange({
      provider: preset.provider,
      model: preset.model,
      base_url: preset.base_url,
      api_key_env: preset.api_key_env,
    });
  };

  const test = async () => {
    const res = await shiba.providerTest("Reply OK only.");
    const msg = res.ok ? `OK: ${res.response}` : `Failed: ${res.error}`;
    setLocalMsg(msg);
    onTestMessage?.(msg);
  };

  const isConfigured = (provider: string) => settings.provider === provider;
  const isExpanded = (provider: string) => expanded === provider;

  return (
    <SettingsPanel title="Provider">
      <SettingsToast message={localMsg} />

      <div className="provider-stats-bar">
        <div className="provider-search-wrap">
          <span className="material-icons-round">search</span>
          <input
            className="provider-search-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search providers..."
          />
        </div>
        <div className="provider-stats-count">
          <span className="stat-configured">{configuredCount || 0}</span> configured
        </div>
      </div>

      <div className="provider-grid">
        {filtered.map((preset) => (
          <button
            key={preset.id}
            type="button"
            className={`provider-tile ${isConfigured(preset.provider) ? "configured" : ""} ${isExpanded(preset.provider) ? "expanded" : ""}`}
            onClick={() => {
              setExpanded((current) => (current === preset.provider ? null : preset.provider));
              applyPreset(preset);
            }}
          >
            <div className="provider-tile-icon">
              <span className="material-icons-round">{providerIcon(preset.provider)}</span>
            </div>
            <div className="provider-tile-name">{preset.provider}</div>
            <span className={`provider-tile-badge ${isConfigured(preset.provider) ? "on" : "off"}`}>
              {isConfigured(preset.provider) ? "active" : "idle"}
            </span>
          </button>
        ))}

        {expanded && (
          <div className="provider-tile-expand">
            <div className="provider-expand-header">
              <div className="provider-expand-title">
                <span className="material-icons-round">tune</span>
                {expanded}
              </div>
              <button
                type="button"
                className="provider-expand-close"
                onClick={() => setExpanded(null)}
                aria-label="Close provider details"
              >
                <span className="material-icons-round">close</span>
              </button>
            </div>
            <FieldRow label="Provider">
              <input
                className="form-input"
                value={settings.provider || ""}
                onChange={(e) => onChange({ provider: e.target.value })}
              />
            </FieldRow>
            <FieldRow label="Model">
              <input
                className="form-input"
                value={settings.model || ""}
                onChange={(e) => onChange({ model: e.target.value })}
              />
            </FieldRow>
            <FieldRow label="Base URL">
              <input
                className="form-input"
                value={settings.base_url || ""}
                onChange={(e) => onChange({ base_url: e.target.value })}
              />
            </FieldRow>
            <FieldRow label="API Key">
              <input
                type="password"
                className="form-input"
                value={settings.api_key || ""}
                onChange={(e) => onChange({ api_key: e.target.value })}
              />
            </FieldRow>
            <FieldRow label="API Key Env">
              <input
                className="form-input"
                value={settings.api_key_env || ""}
                onChange={(e) => onChange({ api_key_env: e.target.value })}
              />
            </FieldRow>
            <button type="button" className="btn-primary" onClick={() => void test()}>
              Test connection
            </button>
          </div>
        )}
      </div>

      <div className="settings-section-divider">
        <span className="material-icons-round">key</span>
        OAuth
      </div>
      <div className="oauth-list">
        {oauth.map((p) => (
          <div key={p.id} className="oauth-item">
            <strong>{p.name}</strong>
            <span> — {p.configured ? "configured" : "use API key above"}</span>
          </div>
        ))}
      </div>

      <div className="settings-section-divider">
        <span className="material-icons-round">extension</span>
        Plugins
      </div>
      <ul className="settings-note">
        {plugins.map((p) => (
          <li key={p.name}>
            {p.name} v{p.version}
          </li>
        ))}
      </ul>
    </SettingsPanel>
  );
}
