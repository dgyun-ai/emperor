"""In-memory notification store with JSON persistence."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from constants import get_emperor_home

_MAX = 200


def _path() -> Path:
    home = get_emperor_home()
    home.mkdir(parents=True, exist_ok=True)
    return home / "notifications.json"


def _load() -> list[dict[str, Any]]:
    path = _path()
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(items: list[dict[str, Any]]) -> None:
    _path().write_text(json.dumps(items[-_MAX:], indent=2, ensure_ascii=False), encoding="utf-8")


def list_notifications() -> list[dict[str, Any]]:
    return _load()


def add_notification(*, content: str, source: str = "system", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    item = {
        "id": str(uuid.uuid4()),
        "content": content,
        "source": source,
        "metadata": metadata or {},
        "created_at": time.time(),
        "read": False,
    }
    items = _load()
    items.append(item)
    _save(items)
    return item


def clear_notifications() -> None:
    _save([])
