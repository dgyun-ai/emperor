import { useEffect, useMemo, useState } from "react";
import { apiDelete, apiGet, apiPost, SessionInfo } from "../api/client";
import UsageBadge from "../components/chat/UsageBadge";
import { useChatSSE } from "../hooks/useChatSSE";

type Props = {
  taskContext?: string | null;
  onClearTaskContext?: () => void;
  profile: string;
  providerLabel: string;
};

export default function ChatPage({
  taskContext,
  onClearTaskContext,
  profile,
  providerLabel,
}: Props) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [history, setHistory] = useState<Array<{ role: string; content: string }>>([]);
  const { send, abort, streaming, blocks, usage, reset } = useChatSSE(activeId);

  const loadSessions = () =>
    apiGet<{ sessions: SessionInfo[] }>("/api/chat/sessions").then((d) => {
      setSessions(d.sessions);
      if (!activeId && d.sessions.length) {
        setActiveId(d.sessions[0].id);
      }
    });

  useEffect(() => {
    loadSessions();
  }, []);

  useEffect(() => {
    if (!activeId) return;
    reset();
    apiGet<{ events: Array<{ type: string; message?: { role?: string; content?: Array<{ type?: string; text?: string }> } }> }>(
      `/api/chat/sessions/${activeId}/messages`
    ).then((d) => {
      const history = d.events
        .filter((event) => event.type === "message" && event.message?.role === "user")
        .map((event) => ({
          role: "user",
          content:
            event.message?.content
              ?.filter((block) => block.type === "text")
              .map((block) => block.text || "")
              .join("") || "",
        }));
      setHistory(history.filter((m) => m.content));
    });
  }, [activeId, reset]);

  const newSession = async () => {
    const body: Record<string, string> = { profile };
    if (taskContext) body.task_id = taskContext;
    const res = await apiPost<{ session_id: string }>("/api/chat/sessions", body);
    setActiveId(res.session_id);
    await loadSessions();
    if (taskContext) {
      setInput(`请在任务 ${taskContext} 的上下文中继续。`);
      onClearTaskContext?.();
    }
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    await send(text);
    await loadSessions();
  };

  const filteredSessions = useMemo(() => {
    if (!search.trim()) return sessions;
    const query = search.toLowerCase();
    return sessions.filter(
      (session) =>
        session.id.toLowerCase().includes(query) ||
        (session.title || "").toLowerCase().includes(query)
    );
  }, [search, sessions]);

  return (
    <div className="workspace-grid workspace-chat">
      <section className="panel session-panel">
        <div className="panel-header">
          <div>
            <h3>会话</h3>
            <p>{profile} 作用域</p>
          </div>
          <button onClick={newSession}>新建</button>
        </div>
        <input
          className="search-input"
          placeholder="搜索会话或 ID"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="session-list">
          {filteredSessions.map((session) => (
            <div
              key={session.id}
              className={`session-card ${activeId === session.id ? "active" : ""}`}
              onClick={() => setActiveId(session.id)}
            >
              <strong>{session.title || session.id.slice(0, 8)}</strong>
              <span>{session.message_count} 条消息</span>
              <small>{session.updated_local || "刚刚"}</small>
            </div>
          ))}
        </div>
      </section>

      <section className="panel chat-panel-shell">
        <div className="panel-header">
          <div>
            <h3>聊天工作台</h3>
            <p>{providerLabel}</p>
          </div>
          {usage && <UsageBadge usage={usage} />}
        </div>
        <div className="messages-stream">
          {!activeId && (
            <div className="empty-panel">
              <h2>欢迎进入 Emperor 控制台</h2>
              <p>从左侧新建会话，或切到文件/看板页面协同工作。</p>
            </div>
          )}
          {history.map((message, index) => (
            <div key={`h-${index}`} className={`message-row ${message.role}`}>
              <div className="message-meta">{message.role}</div>
              <div className="message-bubble">{message.content}</div>
            </div>
          ))}
          {blocks.map((block, index) =>
            block.type === "text" ? (
              <div key={`b-${index}`} className="message-row assistant">
                <div className="message-meta">assistant</div>
                <div className="message-bubble">{block.content}</div>
              </div>
            ) : (
              <div key={`b-${index}`} className="tool-card">
                <strong>{block.name}</strong>
                {block.result && <pre>{block.result.slice(0, 1000)}</pre>}
              </div>
            )
          )}
        </div>
        <div className="composer">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="输入你的任务、问题或下一步操作…"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
          <div className="composer-actions">
            <button onClick={handleSend} disabled={streaming || !activeId}>
              发送
            </button>
            {streaming && <button onClick={abort}>停止</button>}
          </div>
        </div>
      </section>

      <aside className="panel side-panel">
        <div className="panel-header">
          <div>
            <h3>会话侧栏</h3>
            <p>运行上下文</p>
          </div>
          {activeId && (
            <button
              onClick={async () => {
                await apiDelete(`/api/chat/sessions/${activeId}`);
                setActiveId(null);
                setHistory([]);
                await loadSessions();
              }}
            >
              删除
            </button>
          )}
        </div>
        <div className="meta-list">
          <div>
            <span>当前 Profile</span>
            <strong>{profile}</strong>
          </div>
          <div>
            <span>当前会话</span>
            <strong>{activeId ? activeId.slice(0, 8) : "未选择"}</strong>
          </div>
          <div>
            <span>任务上下文</span>
            <strong>{taskContext || "无"}</strong>
          </div>
          <div>
            <span>工具集</span>
            <strong>core / file / terminal / web / todo / kanban</strong>
          </div>
        </div>
      </aside>
    </div>
  );
}

