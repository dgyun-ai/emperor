import { useEffect, useState } from "react";
import { McpServer, shiba } from "../../api/shibaAdapter";
import { FieldRow, FieldRowStack, SettingsPanel, SettingsToast } from "./SettingsPanel";

const EMPTY_SERVER: McpServer = {
  name: "",
  command: "",
  args: [],
  env: {},
};

export default function McpPanel() {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  const reload = async () => {
    const data = await shiba.mcpGet();
    setServers(data.servers.length ? data.servers : [{ ...EMPTY_SERVER }]);
  };

  useEffect(() => {
    reload().catch(() => undefined);
  }, []);

  const updateServer = (index: number, patch: Partial<McpServer>) => {
    setServers((current) =>
      current.map((server, i) => (i === index ? { ...server, ...patch } : server))
    );
  };

  const addServer = () => {
    setServers((current) => [...current, { ...EMPTY_SERVER }]);
  };

  const removeServer = (index: number) => {
    setServers((current) => current.filter((_, i) => i !== index));
  };

  const save = async () => {
    const payload = servers
      .map((server) => ({
        ...server,
        name: server.name.trim(),
        command: server.command.trim(),
        args: server.args,
        env: server.env,
      }))
      .filter((server) => server.name || server.command);
    await shiba.mcpSave(payload);
    await reload();
    setMessage("MCP configuration saved.");
  };

  return (
    <SettingsPanel
      title="MCP"
      divider="Model Context Protocol servers"
      actions={
        <div className="settings-panel-actions">
          <button type="button" className="btn-secondary btn-sm" onClick={addServer}>
            Add server
          </button>
          <button type="button" className="btn-primary btn-sm" onClick={() => void save()}>
            Save MCP
          </button>
        </div>
      }
    >
      <SettingsToast message={message} />

      <div className="mcp-server-list">
        {servers.map((server, index) => (
          <div key={`${server.name}-${index}`} className="mcp-server-card">
            <FieldRow label="Name">
              <input
                className="form-input"
                value={server.name}
                onChange={(e) => updateServer(index, { name: e.target.value })}
                placeholder="filesystem"
              />
            </FieldRow>
            <FieldRow label="Command">
              <input
                className="form-input"
                value={server.command}
                onChange={(e) => updateServer(index, { command: e.target.value })}
                placeholder="npx"
              />
            </FieldRow>
            <FieldRow label="Args">
              <input
                className="form-input"
                value={server.args.join(", ")}
                onChange={(e) =>
                  updateServer(index, {
                    args: e.target.value
                      .split(",")
                      .map((part) => part.trim())
                      .filter(Boolean),
                  })
                }
                placeholder="-y,@modelcontextprotocol/server-filesystem,/tmp"
              />
            </FieldRow>
            <FieldRowStack label="Env">
              <input
                className="form-input"
                value={Object.entries(server.env)
                  .map(([key, value]) => `${key}=${value}`)
                  .join(", ")}
                onChange={(e) => {
                  const env: Record<string, string> = {};
                  for (const part of e.target.value.split(",")) {
                    const trimmed = part.trim();
                    if (!trimmed) continue;
                    const [key, ...rest] = trimmed.split("=");
                    if (key) env[key.trim()] = rest.join("=").trim();
                  }
                  updateServer(index, { env });
                }}
                placeholder="API_KEY=secret"
              />
            </FieldRowStack>
            <button type="button" className="btn-danger btn-sm" onClick={() => removeServer(index)}>
              Remove server
            </button>
          </div>
        ))}
      </div>
    </SettingsPanel>
  );
}
