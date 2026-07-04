import { AUTH_TOKEN_KEY, PROFILE_KEY } from "../api/client";

/** Auth headers for CopilotKit / AG-UI requests. */
export function copilotKitHeaders(): Record<string, string> {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  const profile = localStorage.getItem(PROFILE_KEY) || "default";
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    "X-Emperor-Profile": profile,
  };
}
