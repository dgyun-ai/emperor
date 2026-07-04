export type UsageBlock = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
};

export type ContextBlock = {
  used_tokens: number;
  max_tokens: number;
  percent: number;
  compressed?: boolean;
};

export type UsageSnapshot = {
  turn: UsageBlock;
  session: UsageBlock;
  context: ContextBlock;
};

function readBlock(raw: Record<string, unknown> | undefined, keys: string[]): UsageBlock {
  const src = raw || {};
  const prompt = Number(src[keys[0]] ?? 0);
  const completion = Number(src[keys[1]] ?? 0);
  const total = Number(src[keys[2]] ?? prompt + completion);
  return {
    prompt_tokens: Number.isFinite(prompt) ? prompt : 0,
    completion_tokens: Number.isFinite(completion) ? completion : 0,
    total_tokens: Number.isFinite(total) ? total : 0,
  };
}

/** Normalize backend usage_update / session usage payloads (nested or legacy flat). */
export function normalizeUsage(raw: Record<string, unknown> | null | undefined): UsageSnapshot | null {
  if (!raw) return null;

  const turnRaw = (raw.turn as Record<string, unknown> | undefined) || undefined;
  const sessionRaw = (raw.session as Record<string, unknown> | undefined) || undefined;
  const contextRaw = (raw.context as Record<string, unknown> | undefined) || undefined;

  const used =
    Number(contextRaw?.used_tokens ?? raw.context_tokens ?? raw.used_tokens ?? 0) || 0;
  const max =
    Number(contextRaw?.max_tokens ?? raw.max_context_tokens ?? raw.max_tokens ?? 0) || 0;
  const percent =
    Number(contextRaw?.percent ?? (max ? (used / max) * 100 : 0)) || 0;

  return {
    turn: turnRaw
      ? readBlock(turnRaw, ["prompt_tokens", "completion_tokens", "total_tokens"])
      : readBlock(raw, ["turn_prompt_tokens", "turn_completion_tokens", "turn_total_tokens"]),
    session: sessionRaw
      ? readBlock(sessionRaw, ["prompt_tokens", "completion_tokens", "total_tokens"])
      : readBlock(raw, ["session_prompt_tokens", "session_completion_tokens", "session_total_tokens"]),
    context: {
      used_tokens: used,
      max_tokens: max,
      percent: Math.round(percent * 10) / 10,
      compressed: Boolean(contextRaw?.compressed ?? raw.compressed),
    },
  };
}

export function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${Math.round(n / 1000)}k`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export function usageTierClass(percent: number): string {
  if (percent >= 90) return "usage-crit";
  if (percent >= 75) return "usage-high";
  if (percent >= 50) return "usage-mid";
  return "usage-low";
}

export function formatUsageTitle(snap: UsageSnapshot): string {
  const { context, turn, session } = snap;
  const compressed = context.compressed ? " · 已压缩" : "";
  return (
    `上下文 ${context.used_tokens.toLocaleString()}/${context.max_tokens.toLocaleString()} ` +
    `(${context.percent}%)${compressed}\n` +
    `本轮 输入/输出 ${turn.prompt_tokens.toLocaleString()}/${turn.completion_tokens.toLocaleString()}\n` +
    `会话累计 ${session.total_tokens.toLocaleString()} tokens`
  );
}

export function formatUsageCompact(snap: UsageSnapshot): string {
  const { context, turn, session } = snap;
  const compressed = context.compressed ? " · 已压缩" : "";
  return (
    `ctx ${formatTokenCount(context.used_tokens)}/${formatTokenCount(context.max_tokens)} ` +
    `(${context.percent}%)${compressed} · ` +
    `turn ${formatTokenCount(turn.total_tokens)} · ` +
    `session ${formatTokenCount(session.total_tokens)}`
  );
}

/** Apply usage from an OpenAI SSE chunk, preserving context/session when only turn tokens arrive. */
export function applyUsageChunk(
  prev: UsageSnapshot | null,
  data: Record<string, unknown>
): UsageSnapshot | null {
  const emperor = data.emperor;
  if (emperor && typeof emperor === "object") {
    const snapshot = (emperor as Record<string, unknown>).usage_snapshot;
    if (snapshot && typeof snapshot === "object") {
      return normalizeUsage(snapshot as Record<string, unknown>);
    }
  }

  const usage = data.usage;
  if (!usage || typeof usage !== "object") return prev;

  const u = usage as Record<string, unknown>;
  if (u.turn && u.context) {
    return normalizeUsage(u);
  }

  const merged = normalizeUsage({
    turn: {
      prompt_tokens: u.prompt_tokens,
      completion_tokens: u.completion_tokens,
      total_tokens: u.total_tokens,
    },
    ...(prev
      ? {
          session: prev.session,
          context: prev.context,
        }
      : {}),
  });
  if (merged?.context.max_tokens) return merged;
  return prev;
}
