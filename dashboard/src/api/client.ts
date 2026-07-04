const BASE = "";

export const AUTH_TOKEN_KEY = "emperor.dashboard.token";
export const PROFILE_KEY = "emperor.dashboard.profile";

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  const profile = localStorage.getItem(PROFILE_KEY) || "default";
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    "X-Emperor-Profile": profile,
    ...extra,
  };
}

const FETCH_CACHE: RequestCache = "no-store";

async function parseJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  if (!res.ok) {
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  const contentType = res.headers.get("content-type") || "";
  if (text.trimStart().startsWith("<") && !contentType.includes("application/json")) {
    throw new Error(
      `Expected JSON from ${res.url}, but received HTML. Clear browser cache for this site and confirm you are opening http://127.0.0.1:9119/ (not port 9118 or the Vite dev server).`
    );
  }
  try {
    return JSON.parse(text) as T;
  } catch (err) {
    throw new Error(`Invalid JSON from ${res.url}: ${String(err)}`);
  }
}

function fetchInit(init: RequestInit = {}): RequestInit {
  return { cache: FETCH_CACHE, ...init };
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(
    `${BASE}${path}`,
    fetchInit({
      headers: authHeaders(),
    })
  );
  return parseJson<T>(res);
}

export async function publicGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, fetchInit());
  return parseJson<T>(res);
}

export async function apiPost<T>(path: string, body?: unknown, publicRequest = false): Promise<T> {
  const res = await fetch(
    `${BASE}${path}`,
    fetchInit({
      method: "POST",
      headers: publicRequest
        ? { "Content-Type": "application/json" }
        : authHeaders({ "Content-Type": "application/json" }),
      body: body ? JSON.stringify(body) : undefined,
    })
  );
  return parseJson<T>(res);
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(
    `${BASE}${path}`,
    fetchInit({
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    })
  );
  return parseJson<T>(res);
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(
    `${BASE}${path}`,
    fetchInit({
      method: "PUT",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    })
  );
  return parseJson<T>(res);
}

export async function apiDelete<T>(path: string): Promise<T> {
  const res = await fetch(
    `${BASE}${path}`,
    fetchInit({
      method: "DELETE",
      headers: authHeaders(),
    })
  );
  return parseJson<T>(res);
}

export type SseHandler = (event: string, data: Record<string, unknown>) => void;

export async function apiStream(
  path: string,
  body: unknown,
  onEvent: SseHandler,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(
    `${BASE}${path}`,
    fetchInit({
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
      signal,
    })
  );
  if (!res.ok || !res.body) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const lines = part.split("\n");
      let data = "";
      for (const line of lines) {
        if (line.startsWith("data: ")) data = line.slice(6);
      }
      if (!data) continue;
      if (data === "[DONE]") {
        onEvent("done", {});
        continue;
      }
      try {
        const parsed = JSON.parse(data) as Record<string, unknown>;
        const objectType = String(parsed.object || "chat.completion.chunk");
        onEvent(objectType, parsed);
      } catch {
        /* ignore */
      }
    }
  }
}

export function saveToken(token: string) {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

export function saveProfile(profile: string) {
  localStorage.setItem(PROFILE_KEY, profile);
}

export function getProfile() {
  return localStorage.getItem(PROFILE_KEY) || "default";
}

export type DashboardBootstrapStatus = {
  initialized: boolean;
  requires_login: boolean;
  last_profile: string;
  profiles: ProfileRecord[];
};

export type ProfileRecord = {
  name: string;
  display_name: string;
  description: string;
  avatar_color?: string;
  soul?: string;
  initial?: string;
};

export type DashboardAppState = {
  initialized: boolean;
  current_profile: string;
  last_profile: string;
  provider: {
    provider: string;
    model: string;
    base_url?: string;
    api_key_env?: string;
  };
  workspace_root: string;
  nav: string[];
};

export type TaskCard = {
  id: string;
  title: string;
  status: string;
  assignee?: string;
  tenant?: string;
  priority: number;
  parent_ids: string[];
  child_ids: string[];
};

export type BoardData = {
  columns: Record<string, TaskCard[]>;
  tenants: string[];
  assignees: string[];
};

export type TaskDetail = TaskCard & {
  body?: string;
  runs: Array<{
    id: string;
    outcome: string;
    summary?: string;
    metadata?: Record<string, unknown>;
    error?: string;
    profile?: string;
  }>;
  comments: Array<{ id: string; author?: string; body: string }>;
  model_override?: Record<string, string>;
};

export type SessionInfo = {
  id: string;
  title?: string;
  message_count: number;
  updated_local?: string;
};

export type ProviderConfig = {
  provider: string;
  model: string;
  base_url?: string;
  api_key?: string;
  api_key_env?: string;
};

export type ProviderState = {
  provider: ProviderConfig;
  fallback_providers: Array<ProviderConfig>;
  profile: ProfileRecord;
  dashboard: {
    toolsets: string[];
    ui_language: string;
    lane_by_profile: boolean;
  };
};

export type FileTreeEntry = {
  name: string;
  path: string;
  type: "dir" | "file";
  size?: number | null;
};

export type FileTreeResponse = {
  root: string;
  path: string;
  entries: FileTreeEntry[];
};

export type FileContentResponse = {
  root: string;
  path: string;
  content: string;
  updated_at: number;
};

export type MonitorResponse = {
  health: { status: string; service: string };
  profile: string;
  provider: { provider: string; model: string; base_url?: string };
  kanban_stats: {
    by_status: Record<string, number>;
    by_assignee: Record<string, number>;
  };
  dispatcher_enabled: boolean;
  session_count: number;
  automation: {
    job_count: number;
    running_count: number;
    failed_count: number;
  };
  workspace_root: string;
  timestamp: number;
};
