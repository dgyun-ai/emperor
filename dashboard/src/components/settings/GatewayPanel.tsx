import { useEffect, useState } from "react";
import { GatewayBinding, shiba, ShibaSettings } from "../../api/shibaAdapter";
import { FieldRow, SettingsPanel } from "./SettingsPanel";

type Props = {
  settings: ShibaSettings;
  onSettingsChange: (patch: Partial<ShibaSettings>) => void;
  onMessage?: (msg: string) => void;
};

type SessionOption = {
  id: string;
  title?: string;
  nickname?: string;
};

function sessionLabel(session: SessionOption): string {
  return session.nickname || session.title || session.id.slice(0, 8);
}

export default function GatewayPanel({ settings, onSettingsChange, onMessage }: Props) {
  const [channels, setChannels] = useState<Array<{ id: string; name: string; enabled: boolean; configured: boolean; callback_url: string }>>([]);
  const [bindings, setBindings] = useState<GatewayBinding[]>([]);
  const [sessions, setSessions] = useState<SessionOption[]>([]);
  const [externalKey, setExternalKey] = useState("");
  const [sessionId, setSessionId] = useState("");

  const gateway: NonNullable<ShibaSettings["gateway"]> = settings.gateway || { channels: [] };
  const channelNames = (gateway.channels || []).join(", ") || "dashboard";

  const reload = async () => {
    const [channelData, bindingData, sessionData] = await Promise.all([
      shiba.gatewayChannels(),
      shiba.wecomBindings(),
      shiba.sessions(),
    ]);
    setChannels(channelData.channels);
    setBindings(bindingData.bindings);
    setSessions(sessionData.sessions);
    if (!sessionId && sessionData.sessions[0]?.id) {
      setSessionId(sessionData.sessions[0].id);
    }
  };

  useEffect(() => {
    void reload().catch(() => undefined);
  }, []);

  const saveBinding = async () => {
    if (!externalKey.trim() || !sessionId) return;
    await shiba.wecomBindingCreate({ external_key: externalKey.trim(), session_id: sessionId, enabled: true });
    setExternalKey("");
    await reload();
  };

  return (
    <SettingsPanel title="Gateway" divider="Channels">
      <div className="channel-top-bar">
        <div className="channel-top-chip">
          <span className="material-icons-round">router</span>
          Channels
        </div>
        <div className="channel-top-stats">
          <span className="stat-active">{channelNames}</span>
        </div>
      </div>

      <FieldRow label="Active channels">
        <input className="form-input" readOnly value={channelNames} />
      </FieldRow>
      <button
        type="button"
        className="btn-action"
        onClick={() => {
          void shiba.gatewayRestart().then(() => onMessage?.("Gateway restart requested."));
        }}
      >
        Request gateway restart
      </button>

      <div className="channel-detail-pane" style={{ marginTop: 16 }}>
        <div className="channel-detail-header">
          <div>
            <strong>企业微信</strong>
            <div className="session-subline">
              {(channels.find((item) => item.id === "wecom")?.configured ?? false) ? "Configured" : "Not configured"}
            </div>
          </div>
        </div>
        <FieldRow label="Enabled">
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={Boolean(gateway.wecom_enabled)}
              onChange={(e) =>
                onSettingsChange({
                  gateway: { ...gateway, wecom_enabled: e.target.checked },
                })
              }
            />
            Enable WeCom channel
          </label>
        </FieldRow>
        <FieldRow label="Corp ID">
          <input
            className="form-input"
            value={gateway.wecom_corp_id || ""}
            onChange={(e) => onSettingsChange({ gateway: { ...gateway, wecom_corp_id: e.target.value } })}
          />
        </FieldRow>
        <FieldRow label="Agent ID">
          <input
            className="form-input"
            value={gateway.wecom_agent_id || ""}
            onChange={(e) => onSettingsChange({ gateway: { ...gateway, wecom_agent_id: e.target.value } })}
          />
        </FieldRow>
        <FieldRow label="Secret">
          <input
            className="form-input"
            value={gateway.wecom_secret || ""}
            onChange={(e) => onSettingsChange({ gateway: { ...gateway, wecom_secret: e.target.value } })}
          />
        </FieldRow>
        <FieldRow label="Token">
          <input
            className="form-input"
            value={gateway.wecom_token || ""}
            onChange={(e) => onSettingsChange({ gateway: { ...gateway, wecom_token: e.target.value } })}
          />
        </FieldRow>
        <FieldRow label="Encoding AES Key">
          <input
            className="form-input"
            value={gateway.wecom_encoding_aes_key || ""}
            onChange={(e) => onSettingsChange({ gateway: { ...gateway, wecom_encoding_aes_key: e.target.value } })}
          />
        </FieldRow>
        <FieldRow label="Callback URL">
          <input
            className="form-input"
            readOnly
            value={channels.find((item) => item.id === "wecom")?.callback_url || ""}
          />
        </FieldRow>

        <div className="panel-header" style={{ marginTop: 16 }}>
          <div>
            <h3>Bindings</h3>
            <p>Bind a WeCom source to an existing session.</p>
          </div>
        </div>
        <FieldRow label="External key">
          <input className="form-input" value={externalKey} onChange={(e) => setExternalKey(e.target.value)} />
        </FieldRow>
        <FieldRow label="Session">
          <select className="form-input" value={sessionId} onChange={(e) => setSessionId(e.target.value)}>
            <option value="">Select session</option>
            {sessions.map((session) => (
              <option key={session.id} value={session.id}>
                {sessionLabel(session)}
              </option>
            ))}
          </select>
        </FieldRow>
        <button type="button" className="btn-action" onClick={() => void saveBinding()}>
          Add binding
        </button>
        <div className="history-list" style={{ marginTop: 12 }}>
          {bindings.map((binding) => (
            <div key={binding.binding_id} className="history-item">
              <div className="session-info">
                <span className="session-name">{binding.external_key}</span>
                <span className="session-subline">
                  <span className="ob-badge badge-agent">{binding.session_id.slice(0, 8)}</span>
                  <span className="ob-badge badge-channel-webui">{binding.enabled ? "enabled" : "disabled"}</span>
                </span>
              </div>
              <div className="session-actions">
                <button
                  type="button"
                  className="btn-session-menu"
                  onClick={() =>
                    void shiba
                      .wecomBindingUpdate(binding.binding_id, { enabled: !binding.enabled })
                      .then(reload)
                  }
                >
                  <span className="material-icons-round">{binding.enabled ? "toggle_on" : "toggle_off"}</span>
                </button>
                <button
                  type="button"
                  className="btn-session-menu"
                  onClick={() => void shiba.wecomBindingDelete(binding.binding_id).then(reload)}
                >
                  <span className="material-icons-round">delete</span>
                </button>
              </div>
            </div>
          ))}
          {bindings.length === 0 && <div className="history-item loading">No bindings</div>}
        </div>
      </div>
    </SettingsPanel>
  );
}
