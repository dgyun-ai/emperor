import { useEffect, useMemo, useState } from "react";
import { shiba, ShibaSkill } from "../../api/shibaAdapter";
import { FieldRowStack, SettingsPanel, SettingsToast } from "./SettingsPanel";

const DEFAULT_BODY = (name: string, description: string) =>
  `---\ndescription: ${description || name}\n---\n\n# ${name}\n`;

export default function SkillsPanel() {
  const [skills, setSkills] = useState<ShibaSkill[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<ShibaSkill | null>(null);
  const [editorBody, setEditorBody] = useState("");
  const [createName, setCreateName] = useState("");
  const [createDescription, setCreateDescription] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const reload = async () => {
    const data = await shiba.skills();
    setSkills(data.skills);
  };

  useEffect(() => {
    reload().catch(() => undefined);
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return skills;
    return skills.filter(
      (skill) =>
        skill.name.toLowerCase().includes(q) ||
        skill.description.toLowerCase().includes(q)
    );
  }, [skills, query]);

  const pinned = filtered.filter((skill) => skill.pinned);
  const browse = filtered.filter((skill) => !skill.pinned);

  const openSkill = async (skill: ShibaSkill) => {
    const detail = await shiba.skillGet(skill.name);
    setSelected(detail);
    setEditorBody(detail.body || "");
    setMessage(null);
  };

  const togglePin = async (skill: ShibaSkill) => {
    const pinnedNames = skills.filter((s) => s.pinned).map((s) => s.name);
    const next = skill.pinned
      ? pinnedNames.filter((name) => name !== skill.name)
      : [...pinnedNames, skill.name];
    await shiba.skillsPin(next);
    await reload();
  };

  const createSkill = async () => {
    const name = createName.trim();
    if (!name) {
      setMessage("Skill name is required.");
      return;
    }
    await shiba.skillCreate({
      name,
      description: createDescription.trim(),
      body: DEFAULT_BODY(name, createDescription.trim()),
    });
    setCreateName("");
    setCreateDescription("");
    await reload();
    setMessage("Skill created.");
  };

  const saveSkill = async () => {
    if (!selected) return;
    await shiba.skillUpdate(selected.name, { body: editorBody });
    await reload();
    setMessage("Skill saved.");
  };

  const deleteSkill = async (skill: ShibaSkill) => {
    if (skill.source === "builtin") {
      setMessage("Built-in skills are read-only.");
      return;
    }
    if (!window.confirm(`Delete skill "${skill.name}"?`)) return;
    await shiba.skillDelete(skill.name);
    if (selected?.name === skill.name) {
      setSelected(null);
      setEditorBody("");
    }
    await reload();
    setMessage("Skill deleted.");
  };

  const renderCard = (skill: ShibaSkill) => (
    <div key={skill.name} className="skill-card">
      <div className="skill-card-body">
        <div className="skill-card-name">{skill.name}</div>
        <div className="skill-card-desc">{skill.description}</div>
        <div className="skill-card-meta">
          <span className={`skill-badge ${skill.source}`}>{skill.source}</span>
        </div>
      </div>
      <div className="skill-card-actions">
        <button type="button" className="btn-icon" onClick={() => void openSkill(skill)} aria-label="Edit skill">
          <span className="material-icons-round">edit</span>
        </button>
        <button type="button" className="btn-icon" onClick={() => void togglePin(skill)} aria-label="Pin skill">
          <span className="material-icons-round">{skill.pinned ? "push_pin" : "keep"}</span>
        </button>
        {skill.source !== "builtin" && (
          <button type="button" className="btn-icon danger" onClick={() => void deleteSkill(skill)} aria-label="Delete skill">
            <span className="material-icons-round">delete</span>
          </button>
        )}
      </div>
    </div>
  );

  return (
    <SettingsPanel title="Skills" divider="Manage agent skills">
      <SettingsToast message={message} />

      <div className="skills-toolbar">
        <input
          className="form-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search skills"
        />
        <div className="skills-toolbar-actions">
          <input
            className="form-input"
            value={createName}
            onChange={(e) => setCreateName(e.target.value)}
            placeholder="New skill name"
          />
          <input
            className="form-input"
            value={createDescription}
            onChange={(e) => setCreateDescription(e.target.value)}
            placeholder="Description"
          />
          <button type="button" className="btn-action" onClick={() => void createSkill()}>
            Create
          </button>
        </div>
      </div>

      <div className="skills-pinned-section">
        <div className="skills-section-header">
          <span className="material-icons-round">push_pin</span>
          Pinned
          <span className="skills-pin-counter">{pinned.length}</span>
        </div>
        <div className="skills-pinned-list">
          {pinned.length === 0 ? (
            <span className="skills-pinned-empty">No pinned skills</span>
          ) : (
            pinned.map((skill) => (
              <span key={skill.name} className="skills-pinned-chip">
                {skill.name}
                <button type="button" className="btn-chip-remove" onClick={() => void togglePin(skill)}>
                  ×
                </button>
              </span>
            ))
          )}
        </div>
      </div>

      <div className="skills-browse-section">
        <div className="skills-section-header">
          <span className="material-icons-round">school</span>
          All skills
        </div>
        <div className="skills-list">{browse.map(renderCard)}</div>
      </div>

      {selected && (
        <div className="skills-editor">
          <div className="settings-panel-header">
            <h4>Edit {selected.name}</h4>
            <button type="button" className="btn-primary btn-sm" onClick={() => void saveSkill()}>
              Save
            </button>
          </div>
          <FieldRowStack label="SKILL.md">
            <textarea
              className="form-input"
              rows={12}
              value={editorBody}
              onChange={(e) => setEditorBody(e.target.value)}
              disabled={selected.source === "builtin"}
            />
          </FieldRowStack>
        </div>
      )}
    </SettingsPanel>
  );
}
