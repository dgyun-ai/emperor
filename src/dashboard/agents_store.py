"""Profile-scoped agent definitions stored in agents.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from config.models import EmperorConfig
from constants import get_emperor_home, normalize_profile


class AgentDefinition(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    model: str = ""
    toolsets: list[str] = Field(default_factory=list)


def agents_file(profile: str) -> Path:
    home = get_emperor_home(normalize_profile(profile))
    home.mkdir(parents=True, exist_ok=True)
    return home / "agents.yaml"


def _default_agents(config: EmperorConfig | None = None) -> dict[str, AgentDefinition]:
    config = config or EmperorConfig()
    toolsets = list(config.dashboard.chat.default_toolsets)
    return {
        "default": AgentDefinition(
            name="Default",
            description="Emperor dashboard agent with A2UI support",
            toolsets=toolsets,
        )
    }


def _read_raw(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def load_agents(
    profile: str,
    *,
    config: EmperorConfig | None = None,
    seed_if_missing: bool = True,
) -> dict[str, AgentDefinition]:
    path = agents_file(profile)
    raw = _read_raw(path)
    agents_raw = raw.get("agents") or {}

    if not agents_raw:
        defaults = _default_agents(config)
        if seed_if_missing:
            save_agents(profile, defaults)
        return defaults

    agents: dict[str, AgentDefinition] = {}
    for agent_id, data in agents_raw.items():
        if not isinstance(data, dict):
            continue
        agents[str(agent_id)] = AgentDefinition.model_validate(data)
    if config is not None and "default" in agents:
        default_toolsets = list(config.dashboard.chat.default_toolsets)
        current = list(agents["default"].toolsets)
        merged = current + [toolset for toolset in default_toolsets if toolset not in current]
        if merged != current:
            agents["default"] = agents["default"].model_copy(update={"toolsets": merged})
    return agents or _default_agents(config)


def save_agents(profile: str, agents: dict[str, AgentDefinition]) -> None:
    path = agents_file(profile)
    payload = {
        "agents": {
            agent_id: agent.model_dump()
            for agent_id, agent in agents.items()
        }
    }
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def get_agent(
    profile: str,
    agent_id: str,
    *,
    config: EmperorConfig | None = None,
) -> tuple[str, AgentDefinition]:
    agents = load_agents(profile, config=config)
    if agent_id in agents:
        return agent_id, agents[agent_id]
    if "default" in agents:
        return "default", agents["default"]
    fallback = _default_agents(config)
    return "default", fallback["default"]


def agents_for_runtime(
    profile: str,
    *,
    config: EmperorConfig | None = None,
) -> dict[str, dict[str, str]]:
    agents = load_agents(profile, config=config)
    return {
        agent_id: {
            "name": agent_id,
            "className": "EmperorAgent",
            "description": agent.description or agent.name,
        }
        for agent_id, agent in agents.items()
    }
