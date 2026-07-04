import {
  formatUsageCompact,
  formatUsageTitle,
  normalizeUsage,
  usageTierClass,
  type UsageSnapshot,
} from "../../utils/usageSnapshot";

type Props = {
  usage: Record<string, unknown> | UsageSnapshot | null;
  className?: string;
};

export default function UsageBadge({ usage, className = "" }: Props) {
  const snap = usage && "context" in usage && "turn" in usage
    ? (usage as UsageSnapshot)
    : normalizeUsage(usage as Record<string, unknown> | null);
  if (!snap || !snap.context.max_tokens) return null;

  return (
    <div
      className={`token-badge ${usageTierClass(snap.context.percent)} ${className}`.trim()}
      title={formatUsageTitle(snap)}
    >
      <span className="material-icons-round">data_usage</span>
      {formatUsageCompact(snap)}
    </div>
  );
}
