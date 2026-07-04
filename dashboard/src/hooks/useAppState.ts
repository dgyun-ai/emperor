import { useCallback, useEffect, useState } from "react";
import { shiba, StatusStreamData } from "../api/shibaAdapter";
import { useStatusStream } from "./useStatusStream";

export type AppStatus = "connecting" | "ready" | "working" | "gateway-down" | "not-configured";

export function useAppState() {
  const [baseStatus, setBaseStatus] = useState<Exclude<AppStatus, "working">>("connecting");
  const [providerLabel, setProviderLabel] = useState("--");
  const [channels, setChannels] = useState<string[]>([]);
  const [agentConfigured, setAgentConfigured] = useState(false);
  const [working, setWorkingState] = useState(false);

  const applyStatusData = useCallback((data: StatusStreamData) => {
    const nextStatus = data.status;
    const nextHealth = data.gateway_health;

    if (nextStatus) {
      setAgentConfigured(nextStatus.agent_configured);
      setProviderLabel(`${nextStatus.provider} / ${nextStatus.model || "?"}`);
    }
    if (nextHealth) {
      setChannels(nextHealth.channels || []);
    }

    if (nextStatus?.agent_configured === false) {
      setBaseStatus("not-configured");
      return;
    }
    if (nextHealth?.gateway_up === false) {
      setBaseStatus("gateway-down");
      return;
    }
    if (nextStatus || nextHealth) {
      setBaseStatus("ready");
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [st, health] = await Promise.all([shiba.status(), shiba.gatewayHealth()]);
      applyStatusData({ status: st, gateway_health: health });
    } catch {
      setBaseStatus("gateway-down");
    }
  }, [applyStatusData]);

  const { connected } = useStatusStream({ onData: applyStatusData });

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (connected) {
      return;
    }
    const timer = window.setInterval(() => {
      void refresh();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [connected, refresh]);

  const setWorking = (working: boolean) => {
    setWorkingState(working);
  };

  const status: AppStatus = working ? "working" : baseStatus;

  return { status, providerLabel, channels, agentConfigured, refresh, setWorking };
}
