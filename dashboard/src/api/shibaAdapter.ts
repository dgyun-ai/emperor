import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  apiPut,
  publicGet,
  SessionInfo,
} from "./client";

export type ShibaSession = SessionInfo & {
  nickname?: string;
  model?: string;
  profile_id?: string;
  agent_id?: string;
};

export type ShibaAgent = {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  model: string;
  toolsets: string[];
};

export type ShibaSkill = {
  name: string;
  description: string;
  source: string;
  pinned: boolean;
  path?: string;
  preview?: string;
  body?: string;
};

export type McpServer = {
  name: string;
  command: string;
  args: string[];
  env: Record<string, string>;
};

export type ShibaSettings = {
  provider?: string;
  model?: string;
  base_url?: string;
  api_key?: string;
  api_key_env?: string;
  toolsets?: string[];
  ui_language?: string;
  lane_by_profile?: boolean;
  ask_user_questions?: boolean;
  a2ui_enabled?: boolean;
  profile?: Record<string, string>;
  workspace?: string;
  mcp?: { enabled: boolean; servers: McpServer[] };
  gateway?: {
    channels: string[];
    wecom_enabled?: boolean;
    wecom_corp_id?: string;
    wecom_agent_id?: string;
    wecom_secret?: string;
    wecom_token?: string;
    wecom_encoding_aes_key?: string;
  };
  voice?: { tts_enabled: boolean };
};

export type AutomationJob = {
  id: string;
  name: string;
  schedule:
    | { kind: "at"; at: string }
    | { kind: "every"; everyMs: number; anchorMs?: number | null }
    | { kind: "cron"; expr: string; tz?: string | null };
  payload:
    | { kind: "systemEvent"; text: string }
    | { kind: "agentTurn"; message: string; model?: string | null; thinking?: string | null; timeoutSeconds?: number | null };
  target_session_id: string;
  enabled: boolean;
  created_at: number;
  updated_at: number;
  last_run_at?: number | null;
  last_status?: string | null;
  last_error?: string | null;
  last_run_id?: string | null;
  next_run_at?: number | null;
};

export type AutomationRun = {
  run_id: string;
  job_id: string;
  status: string;
  trigger: string;
  session_id: string;
  message: string;
  started_at?: number | null;
  finished_at?: number | null;
  result_summary?: string | null;
  error?: string | null;
};

export type GatewayBinding = {
  binding_id: string;
  platform: string;
  external_key: string;
  session_id: string;
  enabled: boolean;
  created_at: number;
  updated_at: number;
};

export type StatusPayload = {
  version: string;
  agent_configured: boolean;
  profile: string;
  provider: string;
  model: string;
  initialized: boolean;
};

export type GatewayHealthPayload = {
  ok: boolean;
  gateway_up: boolean;
  profile: string;
  channels: string[];
  telegram_configured?: boolean;
  wecom_configured?: boolean;
  wecom_enabled?: boolean;
};

export type StatusStreamData = {
  status?: StatusPayload;
  gateway_health?: GatewayHealthPayload;
};

export type StatusStreamMessage =
  | { type: "snapshot"; seq: number; data: StatusStreamData }
  | { type: "update"; seq: number; data: StatusStreamData }
  | { type: "heartbeat"; seq: number };

export const AGENT_STORAGE_KEY = "emperor.dashboard.agent";

export const shiba = {
  authStatus: () => publicGet<{ auth_required: boolean; initialized: boolean }>("/api/auth/status"),
  authVerify: (token: string) => apiPost<{ ok: boolean; last_profile: string }>("/api/auth/verify", { token }, true),
  status: () => apiGet<StatusPayload>("/api/status"),
  settingsGet: () => apiGet<ShibaSettings>("/api/settings"),
  settingsPost: (body: Partial<ShibaSettings> & { profile_meta?: Record<string, string> }) =>
    apiPost("/api/settings", body),
  models: () => apiGet<{ models: Array<{ id: string; label: string; provider: string }>; presets: unknown[] }>("/api/models"),
  sessions: () => apiGet<{ sessions: ShibaSession[] }>("/api/sessions"),
  sessionGet: (id: string) =>
    apiGet<{
      id: string;
      events: Array<{
        type: string;
        id?: string;
        parentId?: string | null;
        timestamp?: string;
        message?: {
          role?: string;
          content?: Array<{
            type?: string;
            text?: string;
            thinking?: string;
            id?: string;
            name?: string;
            surfaceId?: string;
            messages?: Array<Record<string, unknown>>;
          }>;
          timestamp?: number;
        };
      }>;
      messages: Array<{
        role: string;
        content?: string;
        tool_calls?: Array<{ id?: string; function?: { name?: string } }>;
        tool_call_id?: string;
        created_at?: number;
      }>;
      usage?: Record<string, unknown>;
      follow_up_questions?: string[];
      agent_id?: string;
    }>(`/api/sessions/${id}`),
  sessionPatch: (id: string, body: { nickname?: string; model?: string; agent_id?: string }) =>
    apiPatch(`/api/sessions/${id}`, body),
  sessionDelete: (id: string) => apiDelete(`/api/sessions/${id}`),
  sessionArchive: (id: string) => apiPost(`/api/sessions/${id}/archive`),
  createSession: (body?: { agent_id?: string; title?: string }) =>
    apiPost<{ session_id: string }>("/api/chat/sessions", body || {}),
  context: () => apiGet<{ system_prompt: string; token_estimate: number; sections: Array<{ name: string; chars: number }> }>("/api/context"),
  fsExplore: (path = ".") => apiGet<{ path: string; entries: Array<{ name: string; path: string; type: string; size?: number }> }>(`/api/fs/explore?path=${encodeURIComponent(path)}`),
  fileGet: (path: string) => apiGet<{ path: string; content: string }>(`/api/file-get?path=${encodeURIComponent(path)}`),
  fileSave: (path: string, content: string) => apiPost("/api/file-save", { path, content }),
  gatewayHealth: () => apiGet<GatewayHealthPayload>("/api/gateway-health"),
  gatewayRestart: () => apiPost("/api/gateway-restart"),
  gatewayChannels: () =>
    apiGet<{ channels: Array<{ id: string; name: string; enabled: boolean; configured: boolean; callback_url: string }> }>(
      "/api/gateway/channels"
    ),
  wecomBindings: () => apiGet<{ bindings: GatewayBinding[] }>("/api/gateway/wecom/bindings"),
  wecomBindingCreate: (body: { external_key: string; session_id: string; enabled: boolean }) =>
    apiPost<{ binding: GatewayBinding }>("/api/gateway/wecom/bindings", body),
  wecomBindingUpdate: (bindingId: string, body: { external_key?: string; session_id?: string; enabled?: boolean }) =>
    apiPatch<{ binding: GatewayBinding }>(`/api/gateway/wecom/bindings/${bindingId}`, body),
  wecomBindingDelete: (bindingId: string) => apiDelete(`/api/gateway/wecom/bindings/${bindingId}`),
  skills: () => apiGet<{ skills: ShibaSkill[] }>("/api/skills"),
  skillGet: (name: string) => apiGet<ShibaSkill & { body: string }>(`/api/skills/${encodeURIComponent(name)}`),
  skillCreate: (body: { name: string; description?: string; body?: string }) => apiPost("/api/skills", body),
  skillUpdate: (name: string, body: { body: string }) => apiPut(`/api/skills/${encodeURIComponent(name)}`, body),
  skillDelete: (name: string) => apiDelete(`/api/skills/${encodeURIComponent(name)}`),
  skillsPin: (names: string[]) => apiPost("/api/skills/pin", { names }),
  agentsList: () => apiGet<{ agents: ShibaAgent[] }>("/api/agents"),
  agentsCreate: (body: Omit<ShibaAgent, "id"> & { id: string }) => apiPost("/api/agents", body),
  agentsUpdate: (id: string, body: Omit<ShibaAgent, "id">) => apiPut(`/api/agents/${encodeURIComponent(id)}`, body),
  agentsDelete: (id: string) => apiDelete(`/api/agents/${encodeURIComponent(id)}`),
  mcpGet: () => apiGet<{ enabled: boolean; servers: McpServer[] }>("/api/mcp"),
  mcpSave: (servers: McpServer[]) => apiPut("/api/mcp", { servers }),
  plugins: () => apiGet<{ plugins: Array<{ name: string; version: string }> }>("/api/plugins"),
  oauthProviders: () => apiGet<{ providers: Array<{ id: string; name: string; configured: boolean }> }>("/api/oauth/providers"),
  automationStatus: () =>
    apiGet<{ job_count: number; running_count: number; failed_count: number }>("/api/automation/status"),
  automationJobs: () => apiGet<{ jobs: AutomationJob[] }>("/api/automation/jobs"),
  automationJob: (id: string) => apiGet<{ job: AutomationJob; runs: AutomationRun[] }>(`/api/automation/jobs/${id}`),
  automationCreate: (body: {
    name: string;
    schedule: AutomationJob["schedule"];
    payload: AutomationJob["payload"];
    target_session_id: string;
    enabled: boolean;
  }) =>
    apiPost<{ job: AutomationJob }>("/api/automation/jobs", body),
  automationUpdate: (
    id: string,
    body: {
      name?: string;
      schedule?: AutomationJob["schedule"];
      payload?: AutomationJob["payload"];
      target_session_id?: string;
      enabled?: boolean;
    }
  ) => apiPatch<{ job: AutomationJob }>(`/api/automation/jobs/${id}`, body),
  automationDelete: (id: string) => apiDelete(`/api/automation/jobs/${id}`),
  automationTrigger: (id: string) => apiPost<{ ok: boolean; run: AutomationRun }>(`/api/automation/jobs/${id}/trigger`),
  automationRuns: (params?: { status?: string; job_id?: string }) => {
    const search = new URLSearchParams();
    if (params?.status) search.set("status", params.status);
    if (params?.job_id) search.set("job_id", params.job_id);
    const query = search.toString();
    return apiGet<{ runs: AutomationRun[] }>(`/api/automation/runs${query ? `?${query}` : ""}`);
  },
  automationCancelRun: (runId: string) => apiPost<{ ok: boolean; run?: AutomationRun }>(`/api/automation/runs/${runId}/cancel`),
  notifications: () => apiGet<{ notifications: Array<{ id: string; content: string; source: string }> }>("/api/v1/notifications"),
  providerTest: (message: string) => apiPost<{ ok: boolean; response?: string; error?: string }>("/api/config/provider/test", { message }),
  profiles: () => apiGet<{ profiles: Array<{ id: string; name: string; display_name: string }> }>("/api/profiles"),
};
