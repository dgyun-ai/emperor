import { useEffect, useState } from "react";
import { apiGet, apiPost, apiPut, ProfileRecord } from "../api/client";

type Props = {
  profiles: ProfileRecord[];
  currentProfile: string;
  onProfileChanged: (profile: string) => Promise<void>;
  onProfilesReload: () => Promise<void>;
};

export default function ProfilesPage({
  profiles,
  currentProfile,
  onProfileChanged,
  onProfilesReload,
}: Props) {
  const [selected, setSelected] = useState<string>(currentProfile);
  const [draft, setDraft] = useState<ProfileRecord | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [newName, setNewName] = useState("");

  useEffect(() => {
    setSelected(currentProfile);
  }, [currentProfile]);

  useEffect(() => {
    apiGet<{ profile: ProfileRecord }>(`/api/dashboard/profiles/${selected}`).then((d) =>
      setDraft(d.profile)
    );
  }, [selected]);

  return (
    <div className="workspace-grid workspace-profiles">
      <section className="panel profile-list-panel">
        <div className="panel-header">
          <div>
            <h3>Profiles</h3>
            <p>作用域即人格</p>
          </div>
        </div>
        <div className="create-inline">
          <input
            placeholder="新 profile 名称"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <button
            onClick={async () => {
              if (!newName.trim()) return;
              await apiPost("/api/dashboard/profiles", { name: newName });
              setNewName("");
              await onProfilesReload();
              setSelected(newName);
            }}
          >
            新建
          </button>
        </div>
        <div className="profile-list">
          {profiles.map((profile) => (
            <div
              key={profile.name}
              className={`profile-card ${selected === profile.name ? "active" : ""}`}
              onClick={() => setSelected(profile.name)}
            >
              <strong>{profile.display_name}</strong>
              <span>{profile.name}</span>
            </div>
          ))}
        </div>
      </section>
      <section className="panel profile-editor-panel">
        <div className="panel-header">
          <div>
            <h3>Profile 编辑器</h3>
            <p>{selected}</p>
          </div>
          <button onClick={() => onProfileChanged(selected)}>切换到此 Profile</button>
        </div>
        {draft && (
          <>
            <label>显示名</label>
            <input
              value={draft.display_name}
              onChange={(e) => setDraft({ ...draft, display_name: e.target.value })}
            />
            <label>描述</label>
            <textarea
              rows={3}
              value={draft.description}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            />
            <label>SOUL.md</label>
            <textarea
              rows={14}
              value={draft.soul || ""}
              onChange={(e) => setDraft({ ...draft, soul: e.target.value })}
            />
            {status && <div className="inline-success">{status}</div>}
            <button
              className="primary-btn"
              onClick={async () => {
                await apiPut(`/api/dashboard/profiles/${selected}`, {
                  display_name: draft.display_name,
                  description: draft.description,
                  soul: draft.soul,
                  avatar_color: draft.avatar_color,
                });
                setStatus("已保存 Profile");
                await onProfilesReload();
              }}
            >
              保存 Profile
            </button>
          </>
        )}
      </section>
    </div>
  );
}

