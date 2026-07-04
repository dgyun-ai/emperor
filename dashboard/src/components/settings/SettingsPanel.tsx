import { ReactNode } from "react";

type PanelProps = {
  children: ReactNode;
  title?: string;
  divider?: string;
  actions?: ReactNode;
};

export function SettingsPanel({ children, title, divider, actions }: PanelProps) {
  return (
    <div className="settings-panel">
      {(title || actions) && (
        <div className="settings-panel-header">
          {title ? <h3>{title}</h3> : <span />}
          {actions}
        </div>
      )}
      {divider && (
        <div className="settings-section-divider">
          <span className="material-icons-round">tune</span>
          {divider}
        </div>
      )}
      {children}
    </div>
  );
}

type FieldRowProps = {
  label: string;
  children: ReactNode;
};

export function FieldRow({ label, children }: FieldRowProps) {
  return (
    <div className="field-row">
      <label>{label}</label>
      {children}
    </div>
  );
}

type FieldRowStackProps = {
  label: string;
  children: ReactNode;
};

export function FieldRowStack({ label, children }: FieldRowStackProps) {
  return (
    <div className="field-row field-row-stack">
      <label>{label}</label>
      {children}
    </div>
  );
}

type SettingsCheckboxProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  hint?: string;
};

export function SettingsCheckbox({ checked, onChange, label, hint }: SettingsCheckboxProps) {
  return (
    <>
      <label className="settings-checkbox">
        <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        {label}
      </label>
      {hint && <p className="settings-hint">{hint}</p>}
    </>
  );
}

export function SettingsToast({ message }: { message: string | null }) {
  if (!message) return null;
  return <p className="settings-note settings-toast">{message}</p>;
}
