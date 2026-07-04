"""Agents management API."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from dashboard.agents_store import AgentDefinition, load_agents, save_agents
from dashboard.context import get_request_config, get_request_profile

router = APIRouter(prefix="/api/agents", tags=["agents"])

_AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class AgentPayload(BaseModel):
    id: str
    name: str
    description: str = ""
    system_prompt: str = ""
    model: str = ""
    toolsets: list[str] = Field(default_factory=list)


def _validate_agent_id(agent_id: str) -> None:
    if not _AGENT_ID_RE.match(agent_id):
        raise HTTPException(400, "Agent id must match ^[a-z][a-z0-9_-]{0,63}$")


@router.get("")
async def list_agents(request: Request):
    profile = get_request_profile(request)
    config = get_request_config(request)
    agents = load_agents(profile, config=config)
    return {
        "agents": [
            {"id": agent_id, **agent.model_dump()}
            for agent_id, agent in agents.items()
        ]
    }


@router.post("")
async def create_agent(request: Request, body: AgentPayload):
    _validate_agent_id(body.id)
    profile = get_request_profile(request)
    config = get_request_config(request)
    agents = load_agents(profile, config=config)
    if body.id in agents:
        raise HTTPException(409, "Agent already exists")
    agent = AgentDefinition(
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        model=body.model,
        toolsets=body.toolsets,
    )
    agents[body.id] = agent
    save_agents(profile, agents)
    return {"ok": True, "id": body.id, **agent.model_dump()}


class AgentUpdatePayload(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    model: str = ""
    toolsets: list[str] = Field(default_factory=list)


@router.put("/{agent_id}")
async def update_agent(request: Request, agent_id: str, body: AgentUpdatePayload):
    _validate_agent_id(agent_id)
    profile = get_request_profile(request)
    config = get_request_config(request)
    agents = load_agents(profile, config=config)
    if agent_id not in agents:
        raise HTTPException(404, "Agent not found")
    agents[agent_id] = AgentDefinition.model_validate(body.model_dump())
    save_agents(profile, agents)
    return {"ok": True, "id": agent_id, **agents[agent_id].model_dump()}


@router.delete("/{agent_id}")
async def delete_agent(request: Request, agent_id: str):
    profile = get_request_profile(request)
    config = get_request_config(request)
    agents = load_agents(profile, config=config)
    if agent_id not in agents:
        raise HTTPException(404, "Agent not found")
    if len(agents) <= 1:
        raise HTTPException(400, "Cannot delete the last agent")
    del agents[agent_id]
    save_agents(profile, agents)
    return {"ok": True, "id": agent_id}
