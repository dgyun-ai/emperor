import { useEffect, useMemo, useState } from "react";
import { apiGet, MonitorResponse } from "../api/client";
import { AutomationJob, AutomationRun, shiba, ShibaSession } from "../api/shibaAdapter";

type MonitorPageProps = {
  onOpenSession?: (sessionId: string) => void;
};

type JobFormState = {
  name: string;
  scheduleKind: "at" | "every" | "cron";
  at: string;
  everyMs: string;
  anchorMs: string;
  cronExpr: string;
  cronTz: string;
  payloadKind: "systemEvent" | "agentTurn";
  systemText: string;
  agentMessage: string;
  agentModel: string;
  agentThinking: string;
  timeoutSeconds: string;
  target_session_id: string;
  enabled: boolean;
};

type EditorMode = "idle" | "create" | "edit";
type JobFilter = "all" | "enabled" | "running" | "failed" | "disabled";
type JobSort = "recent" | "failed" | "name";
type RunScope = "job" | "all";

const EMPTY_FORM: JobFormState = {
  name: "",
  scheduleKind: "every",
  at: "",
  everyMs: "300000",
  anchorMs: "",
  cronExpr: "0 9 * * 1",
  cronTz: "Asia/Shanghai",
  payloadKind: "agentTurn",
  systemText: "",
  agentMessage: "",
  agentModel: "",
  agentThinking: "",
  timeoutSeconds: "",
  target_session_id: "",
  enabled: true,
};

function toDatetimeLocalValueFromIso(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function toIsoFromDatetimeLocal(value: string): string | null {
  if (!value.trim()) return null;
  return new Date(value).toISOString();
}

function payloadSummary(job: AutomationJob): string {
  return job.payload.kind === "systemEvent" ? job.payload.text : job.payload.message;
}

function jobScheduleLabel(job: AutomationJob): string {
  if (job.schedule.kind === "at") return `at ${job.schedule.at}`;
  if (job.schedule.kind === "every") return `every ${job.schedule.everyMs}ms`;
  return `cron ${job.schedule.expr} (${job.schedule.tz || "UTC"})`;
}

function formatTime(value?: number | null): string {
  if (!value) return "Never";
  return new Date(value * 1000).toLocaleString();
}

function formatRelative(value?: number | null): string {
  if (!value) return "Never";
  const diff = Date.now() - value * 1000;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function trimText(value?: string | null, length = 96): string {
  if (!value) return "No summary";
  return value.length > length ? `${value.slice(0, length)}...` : value;
}

function jobDisplayStatus(job: AutomationJob, jobRuns: AutomationRun[]): string {
  if (jobRuns.some((run) => run.status === "running")) return "running";
  if (!job.enabled) return "disabled";
  return job.last_status || "idle";
}

function statusClass(status: string): string {
  switch (status) {
    case "running":
      return "status-running";
    case "succeeded":
      return "status-succeeded";
    case "failed":
      return "status-failed";
    case "cancelled":
      return "status-cancelled";
    case "disabled":
      return "status-disabled";
    default:
      return "status-idle";
  }
}

function formFromJob(job: AutomationJob): JobFormState {
  const base: JobFormState = {
    ...EMPTY_FORM,
    name: job.name,
    target_session_id: job.target_session_id,
    enabled: job.enabled,
  };
  if (job.schedule.kind === "at") {
    base.scheduleKind = "at";
    base.at = toDatetimeLocalValueFromIso(job.schedule.at);
  } else if (job.schedule.kind === "every") {
    base.scheduleKind = "every";
    base.everyMs = String(job.schedule.everyMs);
    base.anchorMs = job.schedule.anchorMs ? String(job.schedule.anchorMs) : "";
  } else {
    base.scheduleKind = "cron";
    base.cronExpr = job.schedule.expr;
    base.cronTz = job.schedule.tz || "UTC";
  }
  if (job.payload.kind === "systemEvent") {
    base.payloadKind = "systemEvent";
    base.systemText = job.payload.text;
  } else {
    base.payloadKind = "agentTurn";
    base.agentMessage = job.payload.message;
    base.agentModel = job.payload.model || "";
    base.agentThinking = job.payload.thinking || "";
    base.timeoutSeconds = job.payload.timeoutSeconds != null ? String(job.payload.timeoutSeconds) : "";
  }
  return base;
}

function buildRequestFromForm(form: JobFormState): {
  name: string;
  schedule: AutomationJob["schedule"];
  payload: AutomationJob["payload"];
  target_session_id: string;
  enabled: boolean;
} | null {
  if (!form.name.trim() || !form.target_session_id) return null;
  let schedule: AutomationJob["schedule"];
  if (form.scheduleKind === "at") {
    const at = toIsoFromDatetimeLocal(form.at);
    if (!at) return null;
    schedule = { kind: "at", at };
  } else if (form.scheduleKind === "every") {
    if (!form.everyMs.trim()) return null;
    schedule = {
      kind: "every",
      everyMs: Number(form.everyMs),
      ...(form.anchorMs.trim() ? { anchorMs: Number(form.anchorMs) } : {}),
    };
  } else {
    if (!form.cronExpr.trim()) return null;
    schedule = { kind: "cron", expr: form.cronExpr.trim(), ...(form.cronTz.trim() ? { tz: form.cronTz.trim() } : {}) };
  }

  const payload: AutomationJob["payload"] =
    form.payloadKind === "systemEvent"
      ? { kind: "systemEvent", text: form.systemText }
      : {
          kind: "agentTurn",
          message: form.agentMessage,
          ...(form.agentModel.trim() ? { model: form.agentModel.trim() } : {}),
          ...(form.agentThinking.trim() ? { thinking: form.agentThinking.trim() } : {}),
          ...(form.timeoutSeconds.trim() ? { timeoutSeconds: Number(form.timeoutSeconds) } : {}),
        };

  if (payload.kind === "systemEvent" && !payload.text.trim()) return null;
  if (payload.kind === "agentTurn" && !payload.message.trim()) return null;

  return {
    name: form.name.trim(),
    schedule,
    payload,
    target_session_id: form.target_session_id,
    enabled: form.enabled,
  };
}

function validateForm(form: JobFormState, sessions: ShibaSession[]): string | null {
  if (!form.name.trim()) return "请填写任务名称。";
  if (!form.target_session_id && sessions.length === 0) return "当前没有可绑定的 Session，请先创建一个会话。";
  if (!form.target_session_id) return "请选择要绑定的 Session。";

  if (form.scheduleKind === "at" && !form.at.trim()) return "请选择执行时间。";
  if (form.scheduleKind === "every" && !form.everyMs.trim()) return "请填写 everyMs。";
  if (form.scheduleKind === "cron" && !form.cronExpr.trim()) return "请填写 cron 表达式。";

  if (form.payloadKind === "systemEvent" && !form.systemText.trim()) return "请填写 systemEvent 的 text。";
  if (form.payloadKind === "agentTurn" && !form.agentMessage.trim()) return "请填写 agentTurn 的 message。";

  return null;
}

export default function MonitorPage({ onOpenSession }: MonitorPageProps) {
  const [data, setData] = useState<MonitorResponse | null>(null);
  const [jobs, setJobs] = useState<AutomationJob[]>([]);
  const [runs, setRuns] = useState<AutomationRun[]>([]);
  const [sessions, setSessions] = useState<ShibaSession[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<AutomationJob | null>(null);
  const [selectedRuns, setSelectedRuns] = useState<AutomationRun[]>([]);
  const [editorMode, setEditorMode] = useState<EditorMode>("idle");
  const [runScope, setRunScope] = useState<RunScope>("job");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<JobFilter>("all");
  const [sortBy, setSortBy] = useState<JobSort>("recent");
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<JobFormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);

  const reload = async (jobId?: string | null) => {
    const [monitor, jobData, runData, sessionData] = await Promise.all([
      apiGet<MonitorResponse>("/api/dashboard/monitor"),
      shiba.automationJobs(),
      shiba.automationRuns(),
      shiba.sessions(),
    ]);

    setData(monitor);
    setJobs(jobData.jobs);
    setRuns(runData.runs);
    setSessions(sessionData.sessions);

    const preferredSessionId = form.target_session_id || sessionData.sessions[0]?.id || "";
    setForm((current) => ({
      ...current,
      target_session_id: current.target_session_id || preferredSessionId,
    }));

    const nextSelectedId = jobId ?? selectedJobId;
    const targetJob = nextSelectedId ? jobData.jobs.find((job) => job.id === nextSelectedId) || null : null;
    setSelectedJobId(targetJob?.id || null);

    if (!targetJob) {
      setSelectedJob(null);
      setSelectedRuns([]);
      if (editorMode === "edit") setEditorMode("idle");
      return;
    }

    const detail = await shiba.automationJob(targetJob.id);
    setSelectedJob(detail.job);
    setSelectedRuns(detail.runs);

    if (editorMode === "edit") {
      setForm(formFromJob(detail.job));
    }
  };

  useEffect(() => {
    void reload().catch(() => undefined);
  }, []);

  const sessionLabelMap = useMemo(() => {
    const entries = sessions.map((session) => [session.id, session.nickname || session.title || session.id] as const);
    return new Map(entries);
  }, [sessions]);

  const jobRunsMap = useMemo(() => {
    const map = new Map<string, AutomationRun[]>();
    for (const run of runs) {
      const existing = map.get(run.job_id) || [];
      existing.push(run);
      map.set(run.job_id, existing);
    }
    return map;
  }, [runs]);

  const normalizedJobs = useMemo(() => {
    return jobs.map((job) => {
      const sessionLabel = sessionLabelMap.get(job.target_session_id) || job.target_session_id;
      const jobRuns = jobRunsMap.get(job.id) || [];
      const derivedStatus = jobDisplayStatus(job, jobRuns);
      return {
        ...job,
        session_label: sessionLabel,
        derived_status: derivedStatus,
        last_run_display: formatRelative(job.last_run_at),
      };
    });
  }, [jobRunsMap, jobs, sessionLabelMap]);

  const filteredJobs = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    const nextJobs = normalizedJobs.filter((job) => {
      if (filter === "enabled" && !job.enabled) return false;
      if (filter === "disabled" && job.enabled) return false;
      if (filter === "running" && job.derived_status !== "running") return false;
      if (filter === "failed" && job.derived_status !== "failed") return false;
      if (!keyword) return true;
      const haystack = `${job.name} ${payloadSummary(job)} ${job.session_label}`.toLowerCase();
      return haystack.includes(keyword);
    });

    nextJobs.sort((a, b) => {
      if (sortBy === "name") return a.name.localeCompare(b.name);
      if (sortBy === "failed") {
        const aScore = a.derived_status === "failed" ? 1 : 0;
        const bScore = b.derived_status === "failed" ? 1 : 0;
        if (aScore !== bScore) return bScore - aScore;
      }
      return (b.last_run_at || 0) - (a.last_run_at || 0);
    });

    return nextJobs;
  }, [filter, normalizedJobs, search, sortBy]);

  const visibleRuns = useMemo(() => {
    if (runScope === "all" || !selectedJobId) return runs;
    return selectedRuns;
  }, [runScope, runs, selectedJobId, selectedRuns]);

  const latestRunAt = useMemo(() => {
    const timestamps = jobs.map((job) => job.last_run_at || 0).filter(Boolean);
    return timestamps.length ? Math.max(...timestamps) : null;
  }, [jobs]);

  const failedJobs = useMemo(
    () => normalizedJobs.filter((job) => job.derived_status === "failed").length,
    [normalizedJobs]
  );

  const runningJobs = useMemo(
    () => normalizedJobs.filter((job) => job.derived_status === "running").length,
    [normalizedJobs]
  );

  const startCreate = () => {
    setEditorMode("create");
    setSelectedJobId(null);
    setSelectedJob(null);
    setSelectedRuns([]);
    setRunScope("all");
    setFormError(null);
    setForm({
      ...EMPTY_FORM,
      target_session_id: sessions[0]?.id || "",
    });
  };

  const startEdit = async (jobId: string) => {
    setSelectedJobId(jobId);
    setEditorMode("edit");
    setRunScope("job");
    const detail = await shiba.automationJob(jobId);
    setSelectedJob(detail.job);
    setSelectedRuns(detail.runs);
    setForm(formFromJob(detail.job));
  };

  const selectJob = async (jobId: string) => {
    setSelectedJobId(jobId);
    setEditorMode("idle");
    setRunScope("job");
    const detail = await shiba.automationJob(jobId);
    setSelectedJob(detail.job);
    setSelectedRuns(detail.runs);
  };

  const resetEditor = () => {
    setEditorMode("idle");
    setFormError(null);
    setForm({
      ...EMPTY_FORM,
      target_session_id: sessions[0]?.id || "",
    });
  };

  const submitJob = async () => {
    const normalizedForm = {
      ...form,
      target_session_id: form.target_session_id || sessions[0]?.id || "",
    };
    const validationError = validateForm(normalizedForm, sessions);
    if (validationError) {
      setFormError(validationError);
      return;
    }

    const payload = buildRequestFromForm(normalizedForm);
    if (!payload) {
      setFormError("任务配置不完整，请检查表单填写。");
      return;
    }

    setFormError(null);
    setSaving(true);
    try {
      if (editorMode === "edit" && selectedJobId) {
        await shiba.automationUpdate(selectedJobId, payload);
        await reload(selectedJobId);
      } else {
        const created = await shiba.automationCreate(payload);
        await reload(created.job.id);
        setSelectedJobId(created.job.id);
      }
      setEditorMode("idle");
    } finally {
      setSaving(false);
    }
  };

  const toggleJob = async (job: AutomationJob) => {
    await shiba.automationUpdate(job.id, { enabled: !job.enabled });
    await reload(job.id);
  };

  const triggerJob = async (jobId: string) => {
    await shiba.automationTrigger(jobId);
    await reload(jobId);
  };

  const deleteJob = async (jobId: string) => {
    await shiba.automationDelete(jobId);
    const nextId = selectedJobId === jobId ? null : selectedJobId;
    setSelectedJobId(nextId);
    setSelectedJob(null);
    setSelectedRuns([]);
    setEditorMode("idle");
    await reload(nextId);
  };

  const cancelRun = async (runId: string) => {
    await shiba.automationCancelRun(runId);
    await reload(selectedJobId);
  };

  const detailJob = selectedJobId ? normalizedJobs.find((job) => job.id === selectedJobId) || null : null;

  return (
    <div className="monitor-shell">
      <section className="monitor-hero">
        <div className="monitor-title-row">
          <div>
            <span className="monitor-eyebrow">Automation Console</span>
            <h1>任务管理台</h1>
            <p>支持 `at` / `every` / `cron` 三类调度，以及 `systemEvent` / `agentTurn` 两类执行载荷。</p>
          </div>
          <div className="monitor-inline-actions">
            <button className="btn-secondary" type="button" onClick={() => void reload(selectedJobId)}>
              刷新
            </button>
            <button className="primary-btn" type="button" onClick={startCreate}>
              新建任务
            </button>
          </div>
        </div>

        <div className="monitor-summary-grid">
          <article className="monitor-summary-card">
            <span>服务状态</span>
            <strong>{data?.health.status || "unknown"}</strong>
            <small>{data?.provider.provider || "provider"} / {data?.provider.model || "model"}</small>
          </article>
          <article className="monitor-summary-card">
            <span>任务总数</span>
            <strong>{jobs.length}</strong>
            <small>当前 Profile：{data?.profile || "default"}</small>
          </article>
          <article className="monitor-summary-card">
            <span>运行中</span>
            <strong>{runningJobs}</strong>
            <small>最近失败 {failedJobs}</small>
          </article>
          <article className="monitor-summary-card">
            <span>最近运行</span>
            <strong>{formatRelative(latestRunAt)}</strong>
            <small>{formatTime(latestRunAt)}</small>
          </article>
        </div>
      </section>

      <section className="monitor-main">
        <div className="monitor-primary-column">
          <div className="monitor-task-panel">
            <div className="monitor-panel-header">
              <div>
                <h2>全部任务</h2>
                <p>直接管理当前 profile 下全部 automation jobs。</p>
              </div>
              <div className="monitor-toolbar">
                <input
                  className="form-input"
                  type="search"
                  placeholder="搜索名称、载荷、会话"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
                <select className="form-input" value={filter} onChange={(event) => setFilter(event.target.value as JobFilter)}>
                  <option value="all">全部状态</option>
                  <option value="enabled">启用中</option>
                  <option value="running">运行中</option>
                  <option value="failed">失败</option>
                  <option value="disabled">已禁用</option>
                </select>
                <select className="form-input" value={sortBy} onChange={(event) => setSortBy(event.target.value as JobSort)}>
                  <option value="recent">最近运行优先</option>
                  <option value="failed">失败优先</option>
                  <option value="name">名称排序</option>
                </select>
              </div>
            </div>

            <div className="monitor-task-table-wrap">
              <table className="monitor-task-table">
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>状态</th>
                    <th>调度</th>
                    <th>载荷</th>
                    <th>目标 Session</th>
                    <th>下次执行</th>
                    <th>启用</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredJobs.map((job) => (
                    <tr key={job.id} className={job.id === selectedJobId ? "monitor-row-active" : ""} onClick={() => void selectJob(job.id)}>
                      <td>
                        <div className="monitor-cell-title">{job.name}</div>
                        <div className="monitor-muted">{trimText(payloadSummary(job), 72)}</div>
                      </td>
                      <td>
                        <span className={`monitor-status-badge ${statusClass(job.derived_status)}`}>{job.derived_status}</span>
                      </td>
                      <td>{jobScheduleLabel(job)}</td>
                      <td>{job.payload.kind}</td>
                      <td>
                        <div className="monitor-cell-title">{job.session_label}</div>
                        <div className="monitor-muted">{job.target_session_id.slice(0, 8)}</div>
                      </td>
                      <td>
                        <div>{formatRelative(job.next_run_at)}</div>
                        <div className="monitor-muted">{formatTime(job.next_run_at)}</div>
                      </td>
                      <td>{job.enabled ? "Yes" : "No"}</td>
                    </tr>
                  ))}
                  {filteredJobs.length === 0 && (
                    <tr>
                      <td colSpan={7}>
                        <div className="monitor-empty-inline">当前条件下没有任务。</div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <section className="monitor-runs-panel">
            <div className="monitor-panel-header">
              <div>
                <h2>运行记录</h2>
                <p>{runScope === "job" && detailJob ? `${detailJob.name} 的最近运行` : "当前 profile 的全局运行记录"}</p>
              </div>
              <div className="monitor-inline-actions">
                <button className={runScope === "job" ? "primary-btn" : "btn-secondary"} type="button" disabled={!detailJob} onClick={() => setRunScope("job")}>
                  当前任务
                </button>
                <button className={runScope === "all" ? "primary-btn" : "btn-secondary"} type="button" onClick={() => setRunScope("all")}>
                  全部运行
                </button>
              </div>
            </div>

            <div className="monitor-runs-list">
              {visibleRuns.map((run) => {
                const runSession = sessionLabelMap.get(run.session_id) || run.session_id;
                return (
                  <article key={run.run_id} className="monitor-run-card">
                    <div className="monitor-run-main">
                      <div className="monitor-inline-actions">
                        <span className={`monitor-status-badge ${statusClass(run.status)}`}>{run.status}</span>
                        <span className="monitor-pill">{run.trigger}</span>
                        <span className="monitor-pill">{runSession}</span>
                      </div>
                      <strong>{trimText(run.message, 100)}</strong>
                      <p>{trimText(run.result_summary || run.error || "No summary", 160)}</p>
                    </div>
                    <div className="monitor-run-side">
                      <span>{formatTime(run.started_at)}</span>
                      <span className="monitor-muted">{run.finished_at ? `Finished ${formatTime(run.finished_at)}` : "Still running"}</span>
                      {run.status === "running" && (
                        <button className="btn-secondary" type="button" onClick={() => void cancelRun(run.run_id)}>
                          终止
                        </button>
                      )}
                    </div>
                  </article>
                );
              })}
              {visibleRuns.length === 0 && <div className="monitor-empty-inline">暂无运行记录。</div>}
            </div>
          </section>
        </div>

        <aside className="monitor-detail-panel">
          {(editorMode === "create" || editorMode === "edit") && (
            <>
              <div className="monitor-panel-header">
                <div>
                  <h2>{editorMode === "create" ? "新建任务" : "编辑任务"}</h2>
                  <p>调度与执行载荷均使用结构化配置。</p>
                </div>
              </div>
              <div className="monitor-detail-section">
                <label>
                  <span>名称</span>
                  <input className="form-input" value={form.name} onChange={(event) => {
                    setFormError(null);
                    setForm((current) => ({ ...current, name: event.target.value }));
                  }} />
                </label>
                <label>
                  <span>调度类型</span>
                  <select className="form-input" value={form.scheduleKind} onChange={(event) => {
                    setFormError(null);
                    setForm((current) => ({ ...current, scheduleKind: event.target.value as JobFormState["scheduleKind"] }));
                  }}>
                    <option value="at">at</option>
                    <option value="every">every</option>
                    <option value="cron">cron</option>
                  </select>
                </label>
                {form.scheduleKind === "at" && (
                  <label>
                    <span>执行时间</span>
                    <input className="form-input" type="datetime-local" value={form.at} onChange={(event) => {
                      setFormError(null);
                      setForm((current) => ({ ...current, at: event.target.value }));
                    }} />
                  </label>
                )}
                {form.scheduleKind === "every" && (
                  <>
                    <label>
                      <span>everyMs</span>
                      <input className="form-input" value={form.everyMs} onChange={(event) => {
                        setFormError(null);
                        setForm((current) => ({ ...current, everyMs: event.target.value }));
                      }} />
                    </label>
                    <label>
                      <span>anchorMs（可选）</span>
                      <input className="form-input" value={form.anchorMs} onChange={(event) => {
                        setFormError(null);
                        setForm((current) => ({ ...current, anchorMs: event.target.value }));
                      }} />
                    </label>
                  </>
                )}
                {form.scheduleKind === "cron" && (
                  <>
                    <label>
                      <span>expr</span>
                      <input className="form-input" value={form.cronExpr} onChange={(event) => {
                        setFormError(null);
                        setForm((current) => ({ ...current, cronExpr: event.target.value }));
                      }} />
                    </label>
                    <label>
                      <span>tz</span>
                      <input className="form-input" value={form.cronTz} onChange={(event) => {
                        setFormError(null);
                        setForm((current) => ({ ...current, cronTz: event.target.value }));
                      }} />
                    </label>
                  </>
                )}
                <label>
                  <span>载荷类型</span>
                  <select className="form-input" value={form.payloadKind} onChange={(event) => {
                    setFormError(null);
                    setForm((current) => ({ ...current, payloadKind: event.target.value as JobFormState["payloadKind"] }));
                  }}>
                    <option value="agentTurn">agentTurn</option>
                    <option value="systemEvent">systemEvent</option>
                  </select>
                </label>
                {form.payloadKind === "systemEvent" ? (
                  <label>
                    <span>text</span>
                    <textarea className="form-input monitor-textarea" value={form.systemText} onChange={(event) => {
                      setFormError(null);
                      setForm((current) => ({ ...current, systemText: event.target.value }));
                    }} />
                  </label>
                ) : (
                  <>
                    <label>
                      <span>message</span>
                      <textarea className="form-input monitor-textarea" value={form.agentMessage} onChange={(event) => {
                        setFormError(null);
                        setForm((current) => ({ ...current, agentMessage: event.target.value }));
                      }} />
                    </label>
                    <label>
                      <span>model（可选）</span>
                      <input className="form-input" value={form.agentModel} onChange={(event) => {
                        setFormError(null);
                        setForm((current) => ({ ...current, agentModel: event.target.value }));
                      }} />
                    </label>
                    <label>
                      <span>thinking（可选）</span>
                      <input className="form-input" value={form.agentThinking} onChange={(event) => {
                        setFormError(null);
                        setForm((current) => ({ ...current, agentThinking: event.target.value }));
                      }} />
                    </label>
                    <label>
                      <span>timeoutSeconds（可选）</span>
                      <input className="form-input" value={form.timeoutSeconds} onChange={(event) => {
                        setFormError(null);
                        setForm((current) => ({ ...current, timeoutSeconds: event.target.value }));
                      }} />
                    </label>
                  </>
                )}
                <label>
                  <span>绑定 Session</span>
                  <select className="form-input" value={form.target_session_id} onChange={(event) => {
                    setFormError(null);
                    setForm((current) => ({ ...current, target_session_id: event.target.value }));
                  }}>
                    <option value="">选择会话</option>
                    {sessions.map((session) => (
                      <option key={session.id} value={session.id}>
                        {(session.nickname || session.title || session.id).slice(0, 80)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="monitor-check">
                  <input type="checkbox" checked={form.enabled} onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))} />
                  <span>启用任务</span>
                </label>
                {formError && <div className="inline-error">{formError}</div>}
              </div>
              <div className="monitor-inline-actions">
                <button className="btn-secondary" type="button" onClick={resetEditor}>
                  取消
                </button>
                <button className="primary-btn" type="button" disabled={saving} onClick={() => void submitJob()}>
                  {saving ? "保存中..." : editorMode === "create" ? "创建任务" : "保存变更"}
                </button>
              </div>
            </>
          )}

          {editorMode === "idle" && !detailJob && (
            <div className="monitor-empty-state">
              <span className="monitor-eyebrow">No selection</span>
              <h2>选择一个任务查看详情</h2>
              <p>右侧会显示任务配置、最近运行记录和操作入口。也可以直接新建一个任务。</p>
              <button className="primary-btn" type="button" onClick={startCreate}>
                新建任务
              </button>
            </div>
          )}

          {detailJob && editorMode === "idle" && (
            <>
              <div className="monitor-panel-header">
                <div>
                  <h2>{detailJob.name}</h2>
                  <p>{trimText(payloadSummary(detailJob), 140)}</p>
                </div>
                <span className={`monitor-status-badge ${statusClass(detailJob.derived_status)}`}>{detailJob.derived_status}</span>
              </div>
              <div className="monitor-detail-section">
                <div className="monitor-detail-grid">
                  <div>
                    <span className="monitor-detail-label">调度</span>
                    <strong>{jobScheduleLabel(detailJob)}</strong>
                  </div>
                  <div>
                    <span className="monitor-detail-label">载荷类型</span>
                    <strong>{detailJob.payload.kind}</strong>
                  </div>
                  <div>
                    <span className="monitor-detail-label">启用状态</span>
                    <strong>{detailJob.enabled ? "Enabled" : "Disabled"}</strong>
                  </div>
                  <div>
                    <span className="monitor-detail-label">目标 Session</span>
                    <strong>{detailJob.session_label}</strong>
                  </div>
                  <div>
                    <span className="monitor-detail-label">最近运行</span>
                    <strong>{formatTime(detailJob.last_run_at)}</strong>
                  </div>
                  <div>
                    <span className="monitor-detail-label">下次执行</span>
                    <strong>{formatTime(detailJob.next_run_at)}</strong>
                  </div>
                </div>
              </div>
              <div className="monitor-detail-section">
                <div className="monitor-section-head">
                  <h3>操作</h3>
                </div>
                <div className="monitor-inline-actions">
                  <button className="btn-secondary" type="button" onClick={() => void startEdit(detailJob.id)}>
                    编辑
                  </button>
                  <button className="btn-secondary" type="button" onClick={() => void triggerJob(detailJob.id)}>
                    手动触发
                  </button>
                  <button className="btn-secondary" type="button" onClick={() => void toggleJob(detailJob)}>
                    {detailJob.enabled ? "禁用" : "启用"}
                  </button>
                  {onOpenSession && (
                    <button className="btn-secondary" type="button" onClick={() => onOpenSession(detailJob.target_session_id)}>
                      打开会话
                    </button>
                  )}
                </div>
              </div>
              <div className="monitor-detail-section monitor-danger-zone">
                <div className="monitor-section-head">
                  <h3>危险操作</h3>
                  <p>删除后不会保留任务配置。</p>
                </div>
                <button className="btn-secondary monitor-danger-btn" type="button" onClick={() => void deleteJob(detailJob.id)}>
                  删除任务
                </button>
              </div>
            </>
          )}
        </aside>
      </section>
    </div>
  );
}
