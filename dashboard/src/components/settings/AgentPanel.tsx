import { ShibaSettings } from "../../api/shibaAdapter";
import {
  FieldRow,
  FieldRowStack,
  SettingsCheckbox,
  SettingsPanel,
} from "./SettingsPanel";

type Props = {
  settings: ShibaSettings;
  toolsets: string;
  onSettingsChange: (patch: Partial<ShibaSettings>) => void;
  onToolsetsChange: (value: string) => void;
};

export default function AgentPanel({ settings, toolsets, onSettingsChange, onToolsetsChange }: Props) {
  return (
    <SettingsPanel title="Agent" divider="Profile & behavior">
      <FieldRow label="Profile">
        <input
          className="form-input"
          readOnly
          value={settings.profile?.display_name || "default"}
        />
      </FieldRow>
      <FieldRow label="Workspace">
        <input className="form-input" readOnly value={settings.workspace || ""} />
      </FieldRow>
      <FieldRow label="UI language">
        <input
          className="form-input"
          value={settings.ui_language || "zh"}
          onChange={(e) => onSettingsChange({ ui_language: e.target.value })}
        />
      </FieldRow>
      <FieldRowStack label="Default toolsets">
        <textarea
          className="form-input"
          rows={3}
          value={toolsets}
          onChange={(e) => onToolsetsChange(e.target.value)}
        />
      </FieldRowStack>
      <SettingsCheckbox
        checked={settings.ask_user_questions ?? true}
        onChange={(checked) => onSettingsChange({ ask_user_questions: checked })}
        label="回答后推荐追问（最多 3 条）"
      />
      <SettingsCheckbox
        checked={settings.a2ui_enabled ?? false}
        onChange={(checked) => onSettingsChange({ a2ui_enabled: checked })}
        label="启用 A2UI 富交互界面"
        hint="开启后 Agent 可使用 render_a2ui 工具生成交互式 UI。"
      />
      <SettingsCheckbox
        checked={settings.lane_by_profile ?? true}
        onChange={(checked) => onSettingsChange({ lane_by_profile: checked })}
        label="Kanban lane by profile"
      />
    </SettingsPanel>
  );
}
