"""Skills usage tracking and curation."""

from __future__ import annotations

import json
import time
from pathlib import Path

from constants import get_emperor_home


class SkillsCurator:
    """Track skill usage counts and staleness."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = home or get_emperor_home()
        self.home.mkdir(parents=True, exist_ok=True)
        self.stats_path = self.home / "skills_stats.json"

    def _load(self) -> dict:
        if self.stats_path.exists():
            return json.loads(self.stats_path.read_text(encoding="utf-8"))
        return {}

    def _save(self, data: dict) -> None:
        self.stats_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def record_use(self, skill_name: str) -> None:
        data = self._load()
        entry = data.get(skill_name, {"count": 0, "last_used": 0})
        entry["count"] = entry.get("count", 0) + 1
        entry["last_used"] = time.time()
        data[skill_name] = entry
        self._save(data)

    def get_stats(self) -> dict:
        return self._load()

    def stale_skills(self, *, days: float = 30) -> list[str]:
        data = self._load()
        cutoff = time.time() - days * 86400
        return [name for name, entry in data.items() if entry.get("last_used", 0) < cutoff]
