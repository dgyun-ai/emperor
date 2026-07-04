"""Tests for chat SSE API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent.deps import AgentDeps
from config.models import AgentConfig, EmperorConfig
from dashboard.server import create_dashboard_app
from engine.query_engine import QueryEngine
from helpers import TEST_CONFIG, bootstrap_dashboard, make_sequential_mock, mock_text_response


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPEROR_HOME", str(tmp_path))
    app = create_dashboard_app(TEST_CONFIG, start_dispatcher_loop=False)

    call_model = make_sequential_mock([lambda: mock_text_response("Hello from SSE")])

    import dashboard.chat_api as chat_api

    original_build = chat_api._build_engine

    def mock_build(**kwargs):
        return QueryEngine(
            deps=AgentDeps.with_call_model(call_model),
            config=TEST_CONFIG,
            tools=[],
            max_turns=3,
            profile=kwargs.get("profile", "default"),
            session_id=kwargs.get("session_id"),
        )

    chat_api._build_engine = mock_build  # type: ignore[assignment]

    with TestClient(app) as c:
        headers = bootstrap_dashboard(c)
        yield c, headers

    chat_api._build_engine = original_build  # type: ignore[assignment]


def test_session_crud(client: tuple[TestClient, dict[str, str]]):
    http, headers = client
    sid = http.post("/api/chat/sessions", json={}, headers=headers).json()["session_id"]
    sessions = http.get("/api/chat/sessions", headers=headers).json()["sessions"]
    created = next(s for s in sessions if s["id"] == sid)
    assert created["title"] == "新会话"
    assert any(s["id"] == sid for s in sessions)
    http.delete(f"/api/chat/sessions/{sid}", headers=headers)


def test_sse_stream(client: tuple[TestClient, dict[str, str]]):
    http, headers = client
    sid = http.post("/api/chat/sessions", json={}, headers=headers).json()["session_id"]
    with http.stream(
        "POST",
        f"/api/chat/sessions/{sid}/messages",
        json={"content": "hi"},
        headers=headers,
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
        assert "chat.completion.chunk" in body
        assert "[DONE]" in body


def test_schedule_intent_creates_once_job(client: tuple[TestClient, dict[str, str]]):
    http, headers = client
    sid = http.post("/api/chat/sessions", json={}, headers=headers).json()["session_id"]

    with http.stream(
        "POST",
        f"/api/chat/sessions/{sid}/messages",
        json={"content": "5分钟后，给我一个动量报告"},
        headers=headers,
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())

    assert "已创建定时任务" in body
    jobs = http.get("/api/automation/jobs", headers=headers).json()["jobs"]
    target = next(job for job in jobs if job["target_session_id"] == sid)
    assert target["schedule"]["kind"] == "at"
    assert "这是之前安排的定时任务" in target["payload"]["message"]


def test_schedule_intent_creates_recurring_job(client: tuple[TestClient, dict[str, str]]):
    http, headers = client
    sid = http.post("/api/chat/sessions", json={}, headers=headers).json()["session_id"]

    with http.stream(
        "POST",
        f"/api/chat/sessions/{sid}/messages",
        json={"content": "每5分钟给我一次报告"},
        headers=headers,
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())

    assert "已创建定时任务" in body
    jobs = http.get("/api/automation/jobs", headers=headers).json()["jobs"]
    target = next(job for job in jobs if job["target_session_id"] == sid)
    assert target["schedule"]["kind"] == "every"
    assert target["schedule"]["everyMs"] == 300000
