"""Tests for dashboard bootstrap/auth/profile/file/monitor APIs."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config.models import EmperorConfig
from dashboard.server import create_dashboard_app
from helpers import bootstrap_dashboard


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPEROR_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    app = create_dashboard_app(EmperorConfig(), start_dispatcher_loop=False)
    with TestClient(app) as client:
        yield client


def test_bootstrap_status_before_init(app_client: TestClient):
    data = app_client.get("/api/dashboard/bootstrap/status").json()
    assert data["initialized"] is False
    assert data["last_profile"] == "default"


def test_login_requires_valid_token(app_client: TestClient):
    headers = bootstrap_dashboard(app_client, token="secret-token")
    ok = app_client.post("/api/dashboard/auth/login", json={"token": "secret-token"}).json()
    assert ok["ok"] is True

    bad = app_client.get("/api/dashboard/app-state")
    assert bad.status_code == 401

    good = app_client.get("/api/dashboard/app-state", headers=headers)
    assert good.status_code == 200


def test_profile_scoping_and_file_api(app_client: TestClient, tmp_path: Path):
    headers = bootstrap_dashboard(app_client)
    app_client.post(
        "/api/dashboard/profiles",
        json={"name": "reviewer", "display_name": "Reviewer"},
        headers=headers,
    )
    reviewer_headers = {
        **headers,
        "X-Emperor-Profile": "reviewer",
    }

    default_task = app_client.post("/api/kanban/tasks", json={"title": "default task"}, headers=headers)
    reviewer_task = app_client.post(
        "/api/kanban/tasks",
        json={"title": "review task"},
        headers=reviewer_headers,
    )
    assert default_task.status_code == 200
    assert reviewer_task.status_code == 200

    default_board = app_client.get("/api/kanban/board", headers=headers).json()
    reviewer_board = app_client.get("/api/kanban/board", headers=reviewer_headers).json()
    default_ids = {card["id"] for cards in default_board["columns"].values() for card in cards}
    reviewer_ids = {card["id"] for cards in reviewer_board["columns"].values() for card in cards}
    assert default_task.json()["id"] in default_ids
    assert reviewer_task.json()["id"] not in default_ids
    assert reviewer_task.json()["id"] in reviewer_ids

    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    tree = app_client.get("/api/dashboard/files/tree?path=.", headers=headers)
    assert tree.status_code == 200
    content = app_client.get("/api/dashboard/files/content?path=notes.txt", headers=headers).json()
    assert content["content"] == "hello"

    save = app_client.put(
        "/api/dashboard/files/content",
        json={"path": "notes.txt", "content": "updated"},
        headers=headers,
    )
    assert save.status_code == 200
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "updated"

    escaped = app_client.get("/api/dashboard/files/content?path=../oops.txt", headers=headers)
    assert escaped.status_code == 400


def test_monitor_endpoint(app_client: TestClient):
    headers = bootstrap_dashboard(app_client)
    data = app_client.get("/api/dashboard/monitor", headers=headers).json()
    assert data["health"]["status"] == "ok"
    assert "kanban_stats" in data
    assert data["profile"] == "default"
    assert "automation" in data
