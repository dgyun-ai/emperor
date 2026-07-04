"""Profile-scoped gateway channel bindings."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from constants import get_emperor_home


@dataclass
class GatewayBinding:
    binding_id: str
    platform: str
    external_key: str
    session_id: str
    enabled: bool = True
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class GatewayBindingStore:
    def __init__(self, home: Path | None = None) -> None:
        self.home = home or get_emperor_home()
        self.home.mkdir(parents=True, exist_ok=True)
        self.path = self.home / "gateway_bindings.json"
        self._bindings: list[GatewayBinding] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._bindings = [GatewayBinding(**item) for item in raw]

    def _save(self) -> None:
        self.path.write_text(
            json.dumps([binding.to_dict() for binding in self._bindings], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def list_bindings(self, *, platform: str | None = None) -> list[GatewayBinding]:
        bindings = self._bindings
        if platform:
            bindings = [item for item in bindings if item.platform == platform]
        return list(bindings)

    def get_binding(self, binding_id: str) -> GatewayBinding | None:
        return next((item for item in self._bindings if item.binding_id == binding_id), None)

    def get_by_external_key(self, platform: str, external_key: str) -> GatewayBinding | None:
        return next(
            (
                item
                for item in self._bindings
                if item.platform == platform and item.external_key == external_key and item.enabled
            ),
            None,
        )

    def add_binding(self, *, platform: str, external_key: str, session_id: str, enabled: bool = True) -> GatewayBinding:
        now = time.time()
        binding = GatewayBinding(
            binding_id=str(uuid.uuid4()),
            platform=platform,
            external_key=external_key,
            session_id=session_id,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        self._bindings.append(binding)
        self._save()
        return binding

    def update_binding(
        self,
        binding_id: str,
        *,
        external_key: str | None = None,
        session_id: str | None = None,
        enabled: bool | None = None,
    ) -> GatewayBinding | None:
        binding = self.get_binding(binding_id)
        if binding is None:
            return None
        if external_key is not None:
            binding.external_key = external_key
        if session_id is not None:
            binding.session_id = session_id
        if enabled is not None:
            binding.enabled = enabled
        binding.updated_at = time.time()
        self._save()
        return binding

    def delete_binding(self, binding_id: str) -> bool:
        before = len(self._bindings)
        self._bindings = [item for item in self._bindings if item.binding_id != binding_id]
        if len(self._bindings) == before:
            return False
        self._save()
        return True
