"""CLI skin/theme engine (Hermes hermes_cli/skin_engine.py pattern)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from constants import get_emperor_home

logger = logging.getLogger(__name__)

_active_skin: SkinConfig | None = None
_active_skin_name: str = "default"


@dataclass
class SkinConfig:
    name: str
    description: str = ""
    colors: dict[str, str] = field(default_factory=dict)
    branding: dict[str, str] = field(default_factory=dict)
    tool_prefix: str = "⎿"

    def get_color(self, key: str, fallback: str = "") -> str:
        return self.colors.get(key, fallback)

    def get_branding(self, key: str, fallback: str = "") -> str:
        return self.branding.get(key, fallback)


_BUILTIN_SKINS: dict[str, dict[str, Any]] = {
    "default": {
        "name": "default",
        "description": "Classic emperor gold",
        "colors": {
            "banner_border": "#CD7F32",
            "banner_title": "#FFD700",
            "banner_accent": "#FFBF00",
            "banner_dim": "#B8860B",
            "banner_text": "#FFF8DC",
            "ui_accent": "#FFBF00",
            "ui_label": "#DAA520",
            "ui_ok": "#4caf50",
            "ui_error": "#ef5350",
            "ui_warn": "#ffa726",
            "prompt": "#FFD700",
            "input_rule": "#CD7F32",
            "status_bar_bg": "#1a1a2e",
            "status_bar_text": "#C0C0C0",
            "status_bar_strong": "#FFD700",
            "status_bar_dim": "#8B8682",
            "tool_bullet": "cyan",
        },
        "branding": {
            "agent_name": "emperor",
            "welcome": "欢迎！输入消息或 /help 查看命令。",
            "prompt_symbol": "❯",
            "goodbye": "再见！⚜",
        },
    },
    "slate": {
        "name": "slate",
        "description": "Cool blue developer theme",
        "colors": {
            "banner_border": "#4a6fa5",
            "banner_title": "#7eb8ff",
            "banner_accent": "#5b9bd5",
            "banner_dim": "#6b8cae",
            "banner_text": "#d0e4ff",
            "ui_accent": "#5b9bd5",
            "ui_label": "#8cb4d9",
            "ui_ok": "#66bb6a",
            "ui_error": "#ef5350",
            "ui_warn": "#ffb74d",
            "prompt": "#7eb8ff",
            "input_rule": "#4a6fa5",
            "status_bar_bg": "#0f1419",
            "status_bar_text": "#a8b8c8",
            "status_bar_strong": "#7eb8ff",
            "status_bar_dim": "#5a6a7a",
            "tool_bullet": "bright_blue",
        },
        "branding": {
            "agent_name": "emperor",
            "welcome": "Welcome — type a message or /help.",
            "prompt_symbol": "❯",
            "goodbye": "Goodbye.",
        },
    },
    "mono": {
        "name": "mono",
        "description": "Grayscale monochrome",
        "colors": {
            "banner_border": "#888888",
            "banner_title": "#eeeeee",
            "banner_accent": "#cccccc",
            "banner_dim": "#777777",
            "banner_text": "#dddddd",
            "ui_accent": "#cccccc",
            "ui_label": "#aaaaaa",
            "ui_ok": "#bbbbbb",
            "ui_error": "#ff6666",
            "ui_warn": "#cccc66",
            "prompt": "#eeeeee",
            "input_rule": "#666666",
            "status_bar_bg": "#1a1a1a",
            "status_bar_text": "#cccccc",
            "status_bar_strong": "#ffffff",
            "status_bar_dim": "#888888",
            "tool_bullet": "white",
        },
        "branding": {
            "agent_name": "emperor",
            "welcome": "Type a message or /help.",
            "prompt_symbol": ">",
            "goodbye": "Bye.",
        },
    },
    "crimson": {
        "name": "crimson",
        "description": "Warm crimson accent theme",
        "colors": {
            "banner_border": "#8b2942",
            "banner_title": "#ff6b6b",
            "banner_accent": "#e94560",
            "banner_dim": "#a05252",
            "banner_text": "#ffe4e4",
            "ui_accent": "#e94560",
            "ui_label": "#d4a0a0",
            "ui_ok": "#81c784",
            "ui_error": "#ff5252",
            "ui_warn": "#ffb74d",
            "prompt": "#ff8a8a",
            "input_rule": "#8b2942",
            "status_bar_bg": "#1a0f12",
            "status_bar_text": "#c8a8a8",
            "status_bar_strong": "#ff6b6b",
            "status_bar_dim": "#8b6868",
            "tool_bullet": "bright_red",
        },
        "branding": {
            "agent_name": "emperor",
            "welcome": "欢迎 — 输入 /help 查看命令。",
            "prompt_symbol": "❯",
            "goodbye": "再见！",
        },
    },
}


def _skins_dir(profile: str | None = None) -> Path:
    return get_emperor_home(profile) / "skins"


def _ui_state_path(profile: str | None = None) -> Path:
    return get_emperor_home(profile) / "ui_state.yaml"


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.debug("Failed to load %s: %s", path, exc)
        return {}


def _section(data: dict[str, Any], key: str, skin_name: str) -> dict[str, Any]:
    value = data.get(key)
    if isinstance(value, dict):
        return value
    if value is not None:
        logger.warning("Skin %s: invalid %s section", skin_name, key)
    return {}


def _build_skin_config(data: dict[str, Any]) -> SkinConfig:
    default = _BUILTIN_SKINS["default"]
    skin_name = str(data.get("name", "unknown"))
    colors = dict(default.get("colors", {}))
    colors.update(_section(data, "colors", skin_name))
    branding = dict(default.get("branding", {}))
    branding.update(_section(data, "branding", skin_name))
    return SkinConfig(
        name=skin_name,
        description=str(data.get("description", "")),
        colors=colors,
        branding=branding,
        tool_prefix=str(data.get("tool_prefix", default.get("tool_prefix", "⎿"))),
    )


def _load_skin_from_yaml(path: Path) -> dict[str, Any] | None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "name" in data:
            return data
    except Exception as exc:
        logger.debug("Failed to load skin %s: %s", path, exc)
    return None


def list_skins(*, profile: str | None = None) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for name, data in _BUILTIN_SKINS.items():
        result.append(
            {
                "name": name,
                "description": str(data.get("description", "")),
                "source": "builtin",
            }
        )
    skins_path = _skins_dir(profile)
    if skins_path.is_dir():
        for path in sorted(skins_path.glob("*.yaml")):
            data = _load_skin_from_yaml(path)
            if not data:
                continue
            skin_name = str(data.get("name", path.stem))
            if any(s["name"] == skin_name for s in result):
                continue
            result.append(
                {
                    "name": skin_name,
                    "description": str(data.get("description", "")),
                    "source": "user",
                }
            )
    return result


def load_skin(name: str, *, profile: str | None = None) -> SkinConfig:
    user_file = _skins_dir(profile) / f"{name}.yaml"
    if user_file.is_file():
        data = _load_skin_from_yaml(user_file)
        if data:
            return _build_skin_config(data)
    if name in _BUILTIN_SKINS:
        return _build_skin_config(_BUILTIN_SKINS[name])
    logger.warning("Skin %r not found, using default", name)
    return _build_skin_config(_BUILTIN_SKINS["default"])


def get_active_skin() -> SkinConfig:
    global _active_skin
    if _active_skin is None:
        _active_skin = load_skin(_active_skin_name)
    return _active_skin


def get_active_skin_name() -> str:
    return _active_skin_name


def set_active_skin(name: str, *, profile: str | None = None, persist: bool = True) -> SkinConfig:
    global _active_skin, _active_skin_name
    _active_skin_name = name
    _active_skin = load_skin(name, profile=profile)
    if persist:
        path = _ui_state_path(profile)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump({"skin": name}, allow_unicode=True), encoding="utf-8")
    return _active_skin


def init_skin_from_config(config: Any, *, profile: str | None = None) -> SkinConfig:
    """Initialize active skin from config + persisted ui_state."""
    skin_name = "default"
    if hasattr(config, "ui") and getattr(config.ui, "skin", None):
        skin_name = str(config.ui.skin).strip() or "default"
    state = _load_yaml_mapping(_ui_state_path(profile))
    if isinstance(state.get("skin"), str) and state["skin"].strip():
        skin_name = state["skin"].strip()
    return set_active_skin(skin_name, profile=profile, persist=False)


def get_prompt_symbol(fallback: str = "❯") -> str:
    symbol = get_active_skin().get_branding("prompt_symbol", fallback).strip() or fallback
    return f"{symbol} "


def build_prompt_toolkit_style() -> dict[str, str]:
    """Build prompt_toolkit Style dict from active skin."""
    skin = get_active_skin()
    prompt = skin.get_color("prompt", "")
    dim = skin.get_color("banner_dim", "#888888")
    input_rule = skin.get_color("input_rule", dim)
    status_bg = skin.get_color("status_bar_bg", "#1a1a2e")
    status_text = skin.get_color("status_bar_text", "#C0C0C0")
    status_strong = skin.get_color("status_bar_strong", skin.get_color("banner_title", "#FFD700"))
    status_dim = skin.get_color("status_bar_dim", "#8B8682")
    menu_bg = skin.get_color("completion_menu_bg", status_bg)
    menu_current = skin.get_color("completion_menu_current_bg", "#333355")
    return {
        "input-area": "",
        "placeholder": f"{dim} italic",
        "prompt": prompt,
        "prompt-working": f"{dim} italic",
        "hint": f"{dim} italic",
        "status-bar": f"bg:{status_bg} {status_text}",
        "status-bar-strong": f"bg:{status_bg} {status_strong} bold",
        "status-bar-dim": f"bg:{status_bg} {status_dim}",
        "input-rule": input_rule,
        "completion-menu": f"bg:{menu_bg} {skin.get_color('banner_text', '#FFF8DC')}",
        "completion-menu.completion.current": f"bg:{menu_current} {status_strong}",
        "spinner": f"{dim} italic",
    }


def format_skin_list(*, active: str | None = None, locale: str | None = None) -> str:
    from i18n.locale import normalize_locale

    zh = normalize_locale(locale) == "zh"
    lines = ["可用皮肤：" if zh else "Available skins:"]
    for item in list_skins():
        marker = "●" if item["name"] == (active or get_active_skin_name()) else " "
        src = "内置" if item["source"] == "builtin" and zh else item["source"]
        if not zh and item["source"] == "builtin":
            src = "builtin"
        desc = item["description"]
        lines.append(f"  {marker} {item['name']:<12} [{src}] {desc}")
    lines.append("")
    lines.append("/skin <name> 切换" if zh else "/skin <name> to switch")
    return "\n".join(lines)
