import { useCallback, useEffect, useState } from "react";
import { apiGet, AUTH_TOKEN_KEY, BoardData, getProfile } from "../api/client";

export function useBoard(filters: {
  tenant?: string;
  assignee?: string;
  search?: string;
}) {
  const [board, setBoard] = useState<BoardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (filters.tenant) params.set("tenant", filters.tenant);
      if (filters.assignee) params.set("assignee", filters.assignee);
      if (filters.search) params.set("search", filters.search);
      const q = params.toString();
      const data = await apiGet<BoardData>(`/api/kanban/board${q ? `?${q}` : ""}`);
      setBoard(data);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, [filters.tenant, filters.assignee, filters.search]);

  useEffect(() => {
    refresh();
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const token = localStorage.getItem(AUTH_TOKEN_KEY) || "";
    const profile = encodeURIComponent(getProfile());
    const ws = new WebSocket(
      `${proto}://${location.host}/api/kanban/events?since=0&token=${encodeURIComponent(
        token
      )}&profile=${profile}`
    );
    ws.onmessage = () => refresh();
    const iv = setInterval(refresh, 15000);
    return () => {
      ws.close();
      clearInterval(iv);
    };
  }, [refresh]);

  return { board, error, refresh };
}
