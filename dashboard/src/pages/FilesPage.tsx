import { useEffect, useState } from "react";
import {
  apiGet,
  apiPut,
  FileContentResponse,
  FileTreeResponse,
} from "../api/client";

type Props = {
  workspaceRoot: string;
};

export default function FilesPage({ workspaceRoot }: Props) {
  const [tree, setTree] = useState<FileTreeResponse | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  const loadTree = async (path = ".") => {
    const data = await apiGet<FileTreeResponse>(`/api/dashboard/files/tree?path=${encodeURIComponent(path)}`);
    setTree(data);
  };

  const loadFile = async (path: string) => {
    const data = await apiGet<FileContentResponse>(
      `/api/dashboard/files/content?path=${encodeURIComponent(path)}`
    );
    setSelectedPath(data.path);
    setContent(data.content);
  };

  useEffect(() => {
    loadTree();
  }, []);

  return (
    <div className="workspace-grid workspace-files">
      <section className="panel file-tree-panel">
        <div className="panel-header">
          <div>
            <h3>工作区</h3>
            <p>{workspaceRoot || tree?.root}</p>
          </div>
          <button onClick={() => loadTree(tree?.path || ".")}>刷新</button>
        </div>
        <div className="tree-breadcrumb">
          <button onClick={() => loadTree(".")}>root</button>
          {tree?.path !== "." && (
            <button
              onClick={() => {
                const parent = tree?.path.split("/").slice(0, -1).join("/") || ".";
                loadTree(parent);
              }}
            >
              上一级
            </button>
          )}
        </div>
        <div className="tree-list">
          {tree?.entries.map((entry) => (
            <div
              key={entry.path}
              className={`tree-entry ${selectedPath === entry.path ? "active" : ""}`}
              onClick={() =>
                entry.type === "dir" ? loadTree(entry.path) : loadFile(entry.path)
              }
            >
              <strong>{entry.name}</strong>
              <span>{entry.type === "dir" ? "目录" : `${entry.size || 0} B`}</span>
            </div>
          ))}
        </div>
      </section>
      <section className="panel editor-panel">
        <div className="panel-header">
          <div>
            <h3>文件编辑器</h3>
            <p>{selectedPath || "未选择文件"}</p>
          </div>
          {selectedPath && (
            <button
              onClick={async () => {
                await apiPut("/api/dashboard/files/content", {
                  path: selectedPath,
                  content,
                });
                setStatus("已保存");
              }}
            >
              保存
            </button>
          )}
        </div>
        {status && <div className="inline-success">{status}</div>}
        <textarea
          className="editor-textarea"
          value={content}
          onChange={(e) => {
            setContent(e.target.value);
            setStatus("未保存修改");
          }}
          placeholder="从左侧选择文本文件开始查看或编辑。"
        />
      </section>
    </div>
  );
}

