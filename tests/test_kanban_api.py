"""Tests for kanban REST API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from config.models import EmperorConfig
from dashboard.server import create_dashboard_app
from helpers import bootstrap_dashboard


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPEROR_HOME", str(tmp_path))
    config = EmperorConfig()
    app = create_dashboard_app(config, start_dispatcher_loop=False)
    with TestClient(app) as c:
        headers = bootstrap_dashboard(c)
        yield c, headers


def test_health(client: tuple[TestClient, dict[str, str]]):
    http, _headers = client
    assert http.get("/health").json()["status"] == "ok"


def test_create_and_board(client: tuple[TestClient, dict[str, str]]):
    http, headers = client
    r = http.post(
        "/api/kanban/tasks",
        json={"title": "Test task", "assignee": "dev", "tenant": "ops"},
        headers=headers,
    )
    assert r.status_code == 200
    task_id = r.json()["id"]

    board = http.get("/api/kanban/board", headers=headers).json()
    ready = [c["id"] for c in board["columns"]["ready"]]
    assert task_id in ready
    assert "ops" in board["tenants"]


def test_task_detail_and_patch(client: tuple[TestClient, dict[str, str]]):
    http, headers = client
    tid = http.post("/api/kanban/tasks", json={"title": "Patch me"}, headers=headers).json()["id"]
    detail = http.get(f"/api/kanban/tasks/{tid}", headers=headers).json()
    assert detail["title"] == "Patch me"

    http.patch(f"/api/kanban/tasks/{tid}", json={"title": "Updated"}, headers=headers)
    assert http.get(f"/api/kanban/tasks/{tid}", headers=headers).json()["title"] == "Updated"


def test_dependency_chain(client: tuple[TestClient, dict[str, str]]):
    http, headers = client
    p = http.post("/api/kanban/tasks", json={"title": "Parent", "assignee": "a"}, headers=headers).json()["id"]
    c = http.post(
        "/api/kanban/tasks",
        json={"title": "Child", "assignee": "a", "parents": [p]},
        headers=headers,
    ).json()["id"]
    board = http.get("/api/kanban/board", headers=headers).json()
    todo_ids = [x["id"] for x in board["columns"]["todo"]]
    assert c in todo_ids

    http.patch(f"/api/kanban/tasks/{p}", json={"status": "done", "summary": "done"}, headers=headers)
    board = http.get("/api/kanban/board", headers=headers).json()
    ready_ids = [x["id"] for x in board["columns"]["ready"]]
    assert c in ready_ids
