"""Plugin discovery from user and project directories."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path

from constants import get_emperor_home


@dataclass
class PluginInfo:
    name: str
    path: Path
    version: str = "0.0.0"


class PluginManager:
    """Discover plugins from ~/.emperor/plugins and project .emperor/plugins."""

    def __init__(self, project_dir: Path | None = None) -> None:
        self.project_dir = project_dir or Path.cwd()
        self.user_plugins = get_emperor_home() / "plugins"
        self.project_plugins = self.project_dir / ".emperor" / "plugins"

    def discover(self) -> list[PluginInfo]:
        plugins: dict[str, PluginInfo] = {}
        for base in [self.user_plugins, self.project_plugins]:
            if not base.is_dir():
                continue
            for child in base.iterdir():
                if not child.is_dir():
                    continue
                manifest = child / "plugin.json"
                name = child.name
                version = "0.0.0"
                if manifest.exists():
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                    name = data.get("name", name)
                    version = data.get("version", version)
                plugins[name] = PluginInfo(name=name, path=child, version=version)
        return list(plugins.values())

    def load_plugin_module(self, plugin: PluginInfo) -> object | None:
        entry = plugin.path / "main.py"
        if not entry.exists():
            return None
        spec = importlib.util.spec_from_file_location(f"emperor_plugin_{plugin.name}", entry)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
