"""Gateway session routing."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionRouter:
    """Map platform keys to session IDs."""

    _routes: dict[str, str] = field(default_factory=dict)
    _paired: set[str] = field(default_factory=set)

    def get_session(self, platform_key: str) -> str | None:
        return self._routes.get(platform_key)

    def set_session(self, platform_key: str, session_id: str) -> None:
        self._routes[platform_key] = session_id

    def is_paired(self, platform_key: str) -> bool:
        return platform_key in self._paired

    def pair(self, platform_key: str) -> None:
        self._paired.add(platform_key)

    def unpair(self, platform_key: str) -> None:
        self._paired.discard(platform_key)
