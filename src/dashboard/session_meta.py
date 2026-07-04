"""Per-session metadata (nickname, model override, archived flag)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from constants import get_emperor_home, normalize_profile

_META_FILE = "session_meta.json"


def _path(profile: str) -> Path:
    home = get_emperor_home(normalize_profile(profile))
    home.mkdir(parents=True, exist_ok=True)
    return home / _META_FILE


def _load(profile: str) -> dict[str, dict[str, Any]]:
    path = _path(profile)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(profile: str, data: dict[str, dict[str, Any]]) -> None:
    _path(profile).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_meta(profile: str, session_id: str) -> dict[str, Any]:
    return dict(_load(profile).get(session_id, {}))


def set_meta(profile: str, session_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    data = _load(profile)
    current = data.get(session_id, {})
    for key, value in patch.items():
        if value is None:
            current.pop(key, None)
        else:
            current[key] = value
    data[session_id] = current
    _save(profile, data)
    return current


def mark_archived(profile: str, session_id: str) -> dict[str, Any]:
    return set_meta(profile, session_id, {"archived": True, "archived_at": time.time()})
