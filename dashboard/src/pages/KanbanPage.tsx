import { useEffect, useState } from "react";
import {
  apiGet,
  apiPatch,
  apiPost,
  TaskCard,
  TaskDetail,
} from "../api/client";
import { useBoard } from "../hooks/useBoard";

const COLUMNS = [
  { key: "triage", label: "待分诊" },
  { key: "todo", label: "待处理" },
  { key: "ready", label: "就绪" },
  { key: "running", label: "执行中" },
  { key: "blocked", label: "阻塞" },
  { key: "done", label: "完成" },
];

type Props = {
  onOpenChat?: (taskId: string) => void;
};

export default function KanbanPage({ onOpenChat }: Props) {
  const [tenant, setTenant] = useState("");
  const [assignee, setAssignee] = useState("");
  const [search, setSearch] = useState("");
  const [lanes, setLanes] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<TaskDetail | null>(null);

  const { board, refresh } = useBoard({ tenant, assignee, search });

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    apiGet<TaskDetail>(`/api/kanban/tasks/${selected}`).then(setDetail);
  }, [selected]);

  const patchTask = async (patch: Record<string, unknown>) => {
    if (!selected) return;
    const updated = await apiPatch<TaskDetail>(`/api/kanban/tasks/${selected}`, patch);
    setDetail(updated);
    refresh();
  };

  const createTask = async () => {
    const title = prompt("任务标题");
    if (!title) return;
    await apiPost("/api/kanban/tasks", {
      title,
      assignee: assignee || undefined,
      tenant: tenant || undefined,
    });
    refresh();
  };

  const renderCards = (cards: TaskCard[]) =>
    cards.map((card) => (
      <div key={card.id} className="kanban-card" onClick={() => setSelected(card.id)}>
        <div className="kanban-card-title">{card.title}</div>
        <div className="kanban-tags">
          {card.assignee && <span>@{card.assignee}</span>}
          {card.tenant && <span>{card.tenant}</span>}
          <span>P{card.priority}</span>
        </div>
      </div>
    ));

  return (
    <>
      <section className="panel panel-toolbar">
        <div className="toolbar-grid">
          <input
            placeholder="搜索任务"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select value={tenant} onChange={(e) => setTenant(e.target.value)}>
            <option value="">全部租户</option>
            {board?.tenants.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
            <option value="">全部负责人</option>
            {board?.assignees.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={lanes}
              onChange={(e) => setLanes(e.target.checked)}
            />
            按执行者分泳道
          </label>
          <button onClick={() => apiPost("/api/kanban/dispatch", {})}>触发调度</button>
          <button onClick={createTask}>新建任务</button>
        </div>
      </section>

      <div className="kanban-board">
        {COLUMNS.map((col) => {
          const cards = board?.columns[col.key] || [];
          if (col.key === "running" && lanes) {
            const grouped: Record<string, TaskCard[]> = {};
            for (const card of cards) {
              const key = card.assignee || "unassigned";
              grouped[key] = grouped[key] || [];
              grouped[key].push(card);
            }
            return (
              <section key={col.key} className="kanban-column">
                <div className="kanban-column-header">
                  <strong>{col.label}</strong>
                  <span>{cards.length}</span>
                </div>
                <div className="kanban-column-body">
                  {Object.entries(grouped).map(([key, laneCards]) => (
                    <div key={key}>
                      <div className="lane-title">{key}</div>
                      {renderCards(laneCards)}
                    </div>
                  ))}
                </div>
              </section>
            );
          }
          return (
            <section key={col.key} className="kanban-column">
              <div className="kanban-column-header">
                <strong>{col.label}</strong>
                <span>{cards.length}</span>
              </div>
              <div className="kanban-column-body">{renderCards(cards)}</div>
            </section>
          );
        })}
      </div>

      {selected && detail && (
        <>
          <div className="drawer-overlay" onClick={() => setSelected(null)} />
          <aside className="drawer">
            <div className="drawer-top">
              <h2>{detail.title}</h2>
              <button onClick={() => setSelected(null)}>关闭</button>
            </div>
            <label>标题</label>
            <input
              value={detail.title}
              onChange={(e) => setDetail({ ...detail, title: e.target.value })}
              onBlur={() => patchTask({ title: detail.title })}
            />
            <label>负责人</label>
            <input
              value={detail.assignee || ""}
              onChange={(e) => setDetail({ ...detail, assignee: e.target.value })}
              onBlur={() => patchTask({ assignee: detail.assignee || null })}
            />
            <label>正文</label>
            <textarea
              rows={8}
              value={detail.body || ""}
              onChange={(e) => setDetail({ ...detail, body: e.target.value })}
              onBlur={() => patchTask({ body: detail.body })}
            />
            <div className="drawer-actions">
              <button onClick={() => patchTask({ status: "ready" })}>标记就绪</button>
              <button onClick={() => patchTask({ status: "done" })}>完成</button>
              <button
                onClick={() => {
                  const reason = prompt("阻塞原因");
                  if (reason) patchTask({ status: "blocked", reason });
                }}
              >
                设为阻塞
              </button>
              {onOpenChat && (
                <button onClick={() => onOpenChat(selected)}>在聊天中处理</button>
              )}
            </div>
            <h3>运行历史</h3>
            {detail.runs?.map((run) => (
              <div key={run.id} className={`run-row ${run.outcome}`}>
                <strong>{run.outcome}</strong> @{run.profile}
                {run.summary && <div>{run.summary}</div>}
                {run.error && <div className="danger-text">{run.error}</div>}
              </div>
            ))}
          </aside>
        </>
      )}
    </>
  );
}

