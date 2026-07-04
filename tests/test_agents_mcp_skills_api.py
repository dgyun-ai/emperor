"""Tests for agents, skills CRUD, and MCP dashboard APIs."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from config.models import EmperorConfig
from dashboard.agents_store import load_agents, save_agents, AgentDefinition
from dashboard.server import create_dashboard_app
from helpers import bootstrap_dashboard


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPEROR_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    app = create_dashboard_app(EmperorConfig(), start_dispatcher_loop=False)
    with TestClient(app) as client:
        yield client


def test_agents_crud(app_client: TestClient):
    headers = bootstrap_dashboard(app_client)

    listed = app_client.get("/api/agents", headers=headers)
    assert listed.status_code == 200
    assert any(agent["id"] == "default" for agent in listed.json()["agents"])

    created = app_client.post(
        "/api/agents",
        headers=headers,
        json={
            "id": "coder",
            "name": "Coder",
            "description": "Code-focused agent",
            "system_prompt": "You write code.",
            "model": "",
            "toolsets": ["core", "file"],
        },
    )
    assert created.status_code == 200
    assert created.json()["id"] == "coder"

    updated = app_client.put(
        "/api/agents/coder",
        headers=headers,
        json={
            "name": "Coder Pro",
            "description": "Updated",
            "system_prompt": "",
            "model": "gpt-4o",
            "toolsets": ["core"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Coder Pro"

    session = app_client.post(
        "/api/chat/sessions",
        headers=headers,
        json={"agent_id": "coder"},
    )
    sid = session.json()["session_id"]
    detail = app_client.get(f"/api/sessions/{sid}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["agent_id"] == "coder"

    deleted = app_client.delete("/api/agents/coder", headers=headers)
    assert deleted.status_code == 200


def test_default_agent_backfills_new_default_toolsets(app_client: TestClient):
    headers = bootstrap_dashboard(app_client)
    profile = headers["X-Emperor-Profile"]
    save_agents(
        profile,
        {
            "default": AgentDefinition(
                name="Default",
                description="legacy",
                toolsets=["core", "file"],
            )
        },
    )

    agents = load_agents(profile, config=EmperorConfig())
    assert "cron" in agents["default"].toolsets


def test_skills_crud(app_client: TestClient, tmp_path):
    headers = bootstrap_dashboard(app_client)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "skills").mkdir()

    created = app_client.post(
        "/api/skills",
        headers=headers,
        json={
            "name": "demo-skill",
            "description": "Demo",
            "body": "---\ndescription: Demo\n---\n\n# Demo\n",
        },
    )
    assert created.status_code == 200

    fetched = app_client.get("/api/skills/demo-skill", headers=headers)
    assert fetched.status_code == 200
    assert "Demo" in fetched.json()["body"]

    updated = app_client.put(
        "/api/skills/demo-skill",
        headers=headers,
        json={"body": "---\ndescription: Demo updated\n---\n\n# Demo updated\n"},
    )
    assert updated.status_code == 200

    deleted = app_client.delete("/api/skills/demo-skill", headers=headers)
    assert deleted.status_code == 200


def test_mcp_config_roundtrip(app_client: TestClient, tmp_path):
    headers = bootstrap_dashboard(app_client)

    saved = app_client.put(
        "/api/mcp",
        headers=headers,
        json={
            "servers": [
                {
                    "name": "fs",
                    "command": "npx",
                    "args": ["-y", "demo"],
                    "env": {"FOO": "bar"},
                }
            ]
        },
    )
    assert saved.status_code == 200
    assert saved.json()["enabled"] is True

    loaded = app_client.get("/api/mcp", headers=headers)
    assert loaded.status_code == 200
    servers = loaded.json()["servers"]
    assert len(servers) == 1
    assert servers[0]["name"] == "fs"

    settings = app_client.get("/api/settings", headers=headers)
    assert settings.status_code == 200
    assert settings.json()["mcp"]["enabled"] is True
