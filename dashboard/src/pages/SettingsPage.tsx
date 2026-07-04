import { useEffect, useState } from "react";
import { apiGet, apiPost, apiPut, ProviderConfig, ProviderState } from "../api/client";

type Props = {
  currentProfile: string;
  onSaved: () => Promise<void>;
};

export default function SettingsPage({ currentProfile, onSaved }: Props) {
  const [provider, setProvider] = useState<ProviderConfig>({
    provider: "openrouter",
    model: "",
    base_url: "",
    api_key_env: "",
  });
  const [profileMeta, setProfileMeta] = useState({
    display_name: currentProfile,
    description: "",
    avatar_color: "",
  });
  const [toolsets, setToolsets] = useState("core,file,terminal,web,todo,kanban,cron");
  const [uiLanguage, setUiLanguage] = useState("zh");
  const [laneByProfile, setLaneByProfile] = useState(true);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [presets, setPresets] = useState<
    Array<{ id: string; label: string; provider: string; model: string; base_url?: string }>
  >([]);

  useEffect(() => {
    apiGet<ProviderState>("/api/config/provider").then((d) => {
      setProvider(d.provider);
      setProfileMeta({
        display_name: d.profile.display_name,
        description: d.profile.description,
        avatar_color: d.profile.avatar_color || "",
      });
      setToolsets(d.dashboard.toolsets.join(","));
      setUiLanguage(d.dashboard.ui_language);
      setLaneByProfile(d.dashboard.lane_by_profile);
    });
    apiGet<{ presets: typeof presets }>("/api/config/models/presets").then((d) =>
      setPresets(d.presets)
    );
  }, [currentProfile]);

  const save = async () => {
    await apiPut("/api/config/provider", {
      provider,
      fallback_providers: [],
      profile_meta: profileMeta,
      dashboard: {
        toolsets: toolsets
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean),
        ui_language: uiLanguage,
        lane_by_profile: laneByProfile,
      },
    });
    setTestResult("设置已保存。");
    await onSaved();
  };

  const test = async () => {
    const res = await apiPost<{ ok: boolean; response?: string; error?: string }>(
      "/api/config/provider/test",
      { message: "Reply OK only." }
    );
    setTestResult(res.ok ? `连接成功: ${res.response}` : `连接失败: ${res.error}`);
  };

  const applyPreset = (id: string) => {
    const preset = presets.find((item) => item.id === id);
    if (!preset) return;
    setProvider({
      ...provider,
      provider: preset.provider,
      model: preset.model,
      base_url: preset.base_url,
    });
  };

  return (
    <div className="settings-grid">
      <section className="panel">
        <div className="panel-header">
          <div>
            <h3>Provider / Model</h3>
            <p>当前 Profile: {currentProfile}</p>
          </div>
        </div>
        <label>预设</label>
        <select onChange={(e) => applyPreset(e.target.value)} defaultValue="">
          <option value="">选择预设</option>
          {presets.map((preset) => (
            <option key={preset.id} value={preset.id}>
              {preset.label}
            </option>
          ))}
        </select>
        <label>Provider</label>
        <input
          value={provider.provider}
          onChange={(e) => setProvider({ ...provider, provider: e.target.value })}
        />
        <label>Model</label>
        <input
          value={provider.model}
          onChange={(e) => setProvider({ ...provider, model: e.target.value })}
        />
        <label>Base URL</label>
        <input
          value={provider.base_url || ""}
          onChange={(e) => setProvider({ ...provider, base_url: e.target.value })}
        />
        <label>API Key Env</label>
        <input
          value={provider.api_key_env || ""}
          onChange={(e) => setProvider({ ...provider, api_key_env: e.target.value })}
        />
        <label>API Key</label>
        <input
          type="password"
          value={provider.api_key === "***" ? "" : provider.api_key || ""}
          onChange={(e) => setProvider({ ...provider, api_key: e.target.value })}
        />
      </section>
      <section className="panel">
        <div className="panel-header">
          <div>
            <h3>Dashboard 偏好</h3>
            <p>仅保存到当前 Profile 作用域</p>
          </div>
        </div>
        <label>默认工具集（逗号分隔）</label>
        <input value={toolsets} onChange={(e) => setToolsets(e.target.value)} />
        <label>界面语言</label>
        <select value={uiLanguage} onChange={(e) => setUiLanguage(e.target.value)}>
          <option value="zh">中文</option>
          <option value="en">English</option>
        </select>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={laneByProfile}
            onChange={(e) => setLaneByProfile(e.target.checked)}
          />
          看板按执行者分泳道
        </label>
        <label>Profile 显示名</label>
        <input
          value={profileMeta.display_name}
          onChange={(e) => setProfileMeta({ ...profileMeta, display_name: e.target.value })}
        />
        <label>Profile 描述</label>
        <textarea
          rows={4}
          value={profileMeta.description}
          onChange={(e) => setProfileMeta({ ...profileMeta, description: e.target.value })}
        />
        <div className="settings-actions">
          <button className="primary-btn" onClick={save}>
            保存设置
          </button>
          <button onClick={test}>测试连接</button>
        </div>
        {testResult && <div className="inline-success">{testResult}</div>}
      </section>
    </div>
  );
}
