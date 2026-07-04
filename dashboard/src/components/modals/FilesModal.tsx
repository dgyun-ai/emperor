import { useEffect, useState } from "react";
import { shiba } from "../../api/shibaAdapter";

type Props = {
  open: boolean;
  onClose: () => void;
};

export default function FilesModal({ open, onClose }: Props) {
  const [path, setPath] = useState(".");
  const [entries, setEntries] = useState<Array<{ name: string; path: string; type: string }>>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState("");

  const load = async (p: string) => {
    const data = await shiba.fsExplore(p);
    setPath(data.path);
    setEntries(data.entries);
  };

  useEffect(() => {
    if (open) load(".").catch(() => undefined);
  }, [open]);

  const openFile = async (filePath: string) => {
    const data = await shiba.fileGet(filePath);
    setSelected(filePath);
    setContent(data.content);
  };

  const save = async () => {
    if (!selected) return;
    await shiba.fileSave(selected, content);
  };

  if (!open) return null;

  return (
    <div className="modal-overlay active" id="files-modal" onClick={onClose}>
      <div className="modal-content files-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Files</h2>
          <button type="button" className="btn-close" onClick={onClose}>
            <span className="material-icons-round">close</span>
          </button>
        </div>
        <div className="modal-body files-layout">
          <div className="files-tree">
            <button type="button" className="btn-command" onClick={() => load(path === "." ? "." : ".")}>
              Root
            </button>
            {entries.map((e) => (
              <button
                key={e.path}
                type="button"
                className="files-entry"
                onClick={() => (e.type === "dir" ? load(e.path) : openFile(e.path))}
              >
                <span className="material-icons-round">{e.type === "dir" ? "folder" : "description"}</span>
                {e.name}
              </button>
            ))}
          </div>
          <div className="files-editor">
            <div className="files-path">{selected || path}</div>
            <textarea value={content} onChange={(ev) => setContent(ev.target.value)} rows={16} />
            <button type="button" className="btn-action" disabled={!selected} onClick={save}>
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
