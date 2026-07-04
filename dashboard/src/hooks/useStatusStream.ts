import { useEffect, useState } from "react";
import { AUTH_TOKEN_KEY, getProfile } from "../api/client";
import type { StatusStreamData, StatusStreamMessage } from "../api/shibaAdapter";

const MAX_RECONNECT_DELAY_MS = 30000;

type UseStatusStreamOptions = {
  onData: (data: StatusStreamData) => void;
};

function socketUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/api/status/stream`;
}

export function useStatusStream({ onData }: UseStatusStreamOptions) {
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let closed = false;
    let ws: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let reconnectDelay = 1000;

    const clearReconnectTimer = () => {
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    const scheduleReconnect = () => {
      if (closed || reconnectTimer !== null) return;
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY_MS);
    };

    const connect = () => {
      const token = window.localStorage.getItem(AUTH_TOKEN_KEY);
      if (!token) {
        setConnected(false);
        scheduleReconnect();
        return;
      }

      const profile = encodeURIComponent(getProfile());
      ws = new WebSocket(`${socketUrl()}?token=${encodeURIComponent(token)}&profile=${profile}`);

      ws.onopen = () => {
        if (closed) return;
        reconnectDelay = 1000;
        setConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as StatusStreamMessage;
          if ((message.type === "snapshot" || message.type === "update") && message.data) {
            onData(message.data);
          }
        } catch {
          // Ignore invalid payloads so a single malformed message does not break reconnection.
        }
      };

      ws.onerror = () => {
        ws?.close();
      };

      ws.onclose = () => {
        if (closed) return;
        setConnected(false);
        scheduleReconnect();
      };
    };

    connect();

    return () => {
      closed = true;
      setConnected(false);
      clearReconnectTimer();
      ws?.close();
    };
  }, [onData]);

  return { connected };
}
