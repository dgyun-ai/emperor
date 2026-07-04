import { useMemo, useState } from "react";
import { apiPost, ProfileRecord } from "../api/client";

type Props = {
  initialized: boolean;
  profiles: ProfileRecord[];
  onBootstrapped: (token: string, profile: string) => Promise<void>;
  onLoggedIn: (token: string, profile: string) => Promise<void>;
};

export default function WelcomePage({
  initialized,
  profiles,
  onBootstrapped,
  onLoggedIn,
}: Props) {
  const [token, setToken] = useState("");
  const [profileName, setProfileName] = useState("default");
  const [displayName, setDisplayName] = useState("默认执行体");
  const [description, setDescription] = useState("面向中文研发工作流的默认 Emperor profile。");
  const [provider, setProvider] = useState("openrouter");
  const [model, setModel] = useState("anthropic/claude-sonnet-4");
  const [baseUrl, setBaseUrl] = useState("https://openrouter.ai/api/v1");
  const [apiKeyEnv, setApiKeyEnv] = useState("OPENROUTER_API_KEY");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const defaultProfile = useMemo(() => profiles[0]?.name || "default", [profiles]);

  const handleBootstrap = async () => {
    setBusy(true);
    setError(null);
    try {
      await apiPost(
        "/api/dashboard/bootstrap",
        {
          token,
          profile_name: profileName,
          profile_display_name: displayName,
          profile_description: description,
          provider: {
            provider,
            model,
            base_url: baseUrl,
            api_key_env: apiKeyEnv,
            api_key: apiKey || undefined,
          },
        },
        true
      );
      await onBootstrapped(token, profileName);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleLogin = async () => {
    setBusy(true);
    setError(null);
    try {
      await apiPost("/api/dashboard/auth/login", { token }, true);
      await onLoggedIn(token, defaultProfile);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="welcome-shell">
      <div className="welcome-hero">
        <div className="hero-badge">WebUI / Phase 1</div>
        <h1>Emperor 中文控制台</h1>
        <p>
          提供聊天工作台、文件浏览、任务看板、Profiles、
          设置中心与运行监控。
        </p>
      </div>

      {!initialized ? (
        <div className="welcome-panel">
          <h2>首次引导</h2>
          <p>完成共享 Token、默认 Profile 与模型配置后进入控制台。</p>
          <div className="form-grid">
            <label>
              访问 Token
              <input value={token} onChange={(e) => setToken(e.target.value)} type="password" />
            </label>
            <label>
              Profile 名称
              <input value={profileName} onChange={(e) => setProfileName(e.target.value)} />
            </label>
            <label>
              Profile 显示名
              <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </label>
            <label className="full">
              Profile 描述
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
            </label>
            <label>
              Provider
              <input value={provider} onChange={(e) => setProvider(e.target.value)} />
            </label>
            <label>
              Model
              <input value={model} onChange={(e) => setModel(e.target.value)} />
            </label>
            <label>
              Base URL
              <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
            </label>
            <label>
              API Key Env
              <input value={apiKeyEnv} onChange={(e) => setApiKeyEnv(e.target.value)} />
            </label>
            <label className="full">
              API Key（可选）
              <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} type="password" />
            </label>
          </div>
          {error && <div className="inline-error">{error}</div>}
          <button className="primary-btn" disabled={busy || !token.trim()} onClick={handleBootstrap}>
            {busy ? "正在初始化…" : "完成初始化"}
          </button>
        </div>
      ) : (
        <div className="welcome-panel">
          <h2>控制台登录</h2>
          <p>Dashboard 已初始化，请输入共享 Token 进入控制台。</p>
          <label>
            访问 Token
            <input value={token} onChange={(e) => setToken(e.target.value)} type="password" />
          </label>
          <div className="profile-preview-row">
            {profiles.map((profile) => (
              <div key={profile.name} className="profile-preview">
                <strong>{profile.display_name}</strong>
                <span>{profile.name}</span>
              </div>
            ))}
          </div>
          {error && <div className="inline-error">{error}</div>}
          <button className="primary-btn" disabled={busy || !token.trim()} onClick={handleLogin}>
            {busy ? "正在验证…" : "登录控制台"}
          </button>
        </div>
      )}
    </div>
  );
}

