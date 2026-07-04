"""Tests for ShibaClaw-compatible dashboard API."""

from __future__ import annotations

import hashlib
import time

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from agent.deps import AgentDeps
from config.models import EmperorConfig
import dashboard.shiba_compat_api as shiba_compat_api
from dashboard.server import create_dashboard_app
from engine.query_engine import QueryEngine
from helpers import TEST_CONFIG, bootstrap_dashboard, make_sequential_mock, mock_text_response


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPEROR_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    app = create_dashboard_app(EmperorConfig(), start_dispatcher_loop=False)
    with TestClient(app) as client:
        yield client


def test_auth_status_public(app_client: TestClient):
    data = app_client.get("/api/auth/status").json()
    assert "initialized" in data


def test_shiba_settings_roundtrip(app_client: TestClient):
    headers = bootstrap_dashboard(app_client)
    get_res = app_client.get("/api/settings", headers=headers)
    assert get_res.status_code == 200
    body = get_res.json()
    assert "provider" in body
    assert "toolsets" in body

    post_res = app_client.post(
        "/api/settings",
        headers=headers,
        json={"ui_language": "en", "toolsets": ["core", "file"]},
    )
    assert post_res.status_code == 200
    assert post_res.json()["ok"] is True


def test_shiba_sessions_and_context(app_client: TestClient):
    headers = bootstrap_dashboard(app_client)
    create = app_client.post("/api/chat/sessions", headers=headers, json={})
    assert create.status_code == 200
    sid = create.json()["session_id"]

    list_res = app_client.get("/api/sessions", headers=headers)
    assert list_res.status_code == 200
    ids = [s["id"] for s in list_res.json()["sessions"]]
    assert sid in ids

    patch = app_client.patch(
        f"/api/sessions/{sid}",
        headers=headers,
        json={"nickname": "Test chat", "model": "gpt-4o"},
    )
    assert patch.status_code == 200
    assert patch.json()["nickname"] == "Test chat"

    ctx = app_client.get("/api/context", headers=headers)
    assert ctx.status_code == 200
    assert "system_prompt" in ctx.json()

    detail = app_client.get(f"/api/sessions/{sid}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert "usage" in body
    assert body["usage"]["context"]["max_tokens"] > 0


def test_shiba_fs_and_gateway(app_client: TestClient, tmp_path):
    headers = bootstrap_dashboard(app_client)
    (tmp_path / "demo.txt").write_text("hi", encoding="utf-8")

    tree = app_client.get("/api/fs/explore?path=.", headers=headers)
    assert tree.status_code == 200

    health = app_client.get("/api/gateway-health", headers=headers)
    assert health.status_code == 200
    assert health.json()["gateway_up"] is True

    skills = app_client.get("/api/skills", headers=headers)
    assert skills.status_code == 200

    plugins = app_client.get("/api/plugins", headers=headers)
    assert plugins.status_code == 200

    jobs = app_client.get("/api/automation/jobs", headers=headers)
    assert jobs.status_code == 200

    notes = app_client.get("/api/v1/notifications", headers=headers)
    assert notes.status_code == 200


def test_status_stream_requires_valid_token(app_client: TestClient):
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with app_client.websocket_connect("/api/status/stream?token=bad-token&profile=default"):
            pass
    assert excinfo.value.code == 4401


def test_status_stream_sends_snapshot_and_heartbeat(app_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    headers = bootstrap_dashboard(app_client)
    monkeypatch.setattr(shiba_compat_api, "STATUS_STREAM_POLL_SECONDS", 0.01)
    monkeypatch.setattr(shiba_compat_api, "STATUS_STREAM_HEARTBEAT_SECONDS", 0.03)

    token = headers["Authorization"].removeprefix("Bearer ")
    with app_client.websocket_connect(f"/api/status/stream?token={token}&profile=default") as websocket:
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "snapshot"
        assert snapshot["seq"] == 1
        assert snapshot["data"]["status"]["agent_configured"] is True
        assert snapshot["data"]["gateway_health"]["channels"] == ["dashboard"]

        heartbeat = websocket.receive_json()
        assert heartbeat["type"] == "heartbeat"
        assert heartbeat["seq"] == 2


def test_status_stream_pushes_gateway_updates(app_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    headers = bootstrap_dashboard(app_client)
    monkeypatch.setattr(shiba_compat_api, "STATUS_STREAM_POLL_SECONDS", 0.01)
    monkeypatch.setattr(shiba_compat_api, "STATUS_STREAM_HEARTBEAT_SECONDS", 1.0)

    token = headers["Authorization"].removeprefix("Bearer ")
    with app_client.websocket_connect(f"/api/status/stream?token={token}&profile=default") as websocket:
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "snapshot"
        assert snapshot["data"]["gateway_health"]["wecom_enabled"] is False

        updated = app_client.put(
            "/api/gateway/wecom/settings",
            headers=headers,
            json={
                "enabled": True,
                "corp_id": "corp-1",
                "agent_id": "1000002",
                "secret": "sec",
                "token": "tok",
                "encoding_aes_key": "aes-key",
            },
        )
        assert updated.status_code == 200

        message = websocket.receive_json()
        assert message["type"] == "update"
        assert message["data"]["gateway_health"]["wecom_enabled"] is True
        assert "wecom" in message["data"]["gateway_health"]["channels"]


def test_automation_and_wecom_endpoints(app_client: TestClient):
    headers = bootstrap_dashboard(app_client)

    import dashboard.chat_api as chat_api

    original_build = chat_api._build_engine
    call_model = make_sequential_mock([lambda: mock_text_response("job reply"), lambda: mock_text_response("wecom reply")])

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

    try:
        session_id = app_client.post("/api/chat/sessions", headers=headers, json={}).json()["session_id"]

        created = app_client.post(
            "/api/automation/jobs",
            headers=headers,
            json={
                "name": "Heartbeat",
                "schedule": {"kind": "every", "everyMs": 60000},
                "payload": {"kind": "agentTurn", "message": "ping"},
                "target_session_id": session_id,
                "enabled": True,
            },
        )
        assert created.status_code == 200
        job_id = created.json()["job"]["id"]
        assert created.json()["job"]["schedule"]["kind"] == "every"

        updated = app_client.patch(
            f"/api/automation/jobs/{job_id}",
            headers=headers,
            json={"payload": {"kind": "agentTurn", "message": "ping again"}, "enabled": False},
        )
        assert updated.status_code == 200
        assert updated.json()["job"]["payload"]["message"] == "ping again"
        assert updated.json()["job"]["enabled"] is False

        one_shot = app_client.post(
            "/api/automation/jobs",
            headers=headers,
            json={
                "name": "One Shot",
                "schedule": {"kind": "at", "at": "2099-01-01T00:00:00Z"},
                "payload": {"kind": "systemEvent", "text": "remind me"},
                "target_session_id": session_id,
                "enabled": True,
            },
        )
        assert one_shot.status_code == 200
        assert one_shot.json()["job"]["payload"]["kind"] == "systemEvent"

        app_client.patch(f"/api/automation/jobs/{job_id}", headers=headers, json={"enabled": True})
        trigger = app_client.post(f"/api/automation/jobs/{job_id}/trigger", headers=headers)
        assert trigger.status_code == 200
        run_id = trigger.json()["run"]["run_id"]

        for _ in range(20):
            run_list = app_client.get("/api/automation/runs", headers=headers).json()["runs"]
            target = next((run for run in run_list if run["run_id"] == run_id), None)
            if target and target["status"] == "succeeded":
                break
            time.sleep(0.05)
        else:
            raise AssertionError("automation run did not succeed")

        app_client.put(
            "/api/gateway/wecom/settings",
            headers=headers,
            json={
                "enabled": True,
                "corp_id": "corp-1",
                "agent_id": "1000002",
                "secret": "sec",
                "token": "tok",
                "encoding_aes_key": "aes-key",
            },
        )

        health = app_client.get("/api/gateway-health", headers=headers)
        assert health.status_code == 200
        assert health.json()["wecom_configured"] is True

        binding = app_client.post(
            "/api/gateway/wecom/bindings",
            headers=headers,
            json={"external_key": "wecom-user-1", "session_id": session_id, "enabled": True},
        )
        assert binding.status_code == 200

        echostr = "hello"
        timestamp = "1"
        nonce = "2"
        sig = hashlib.sha1("".join(sorted(["tok", timestamp, nonce, echostr])).encode("utf-8")).hexdigest()
        verify = app_client.get(
            f"/api/gateway/wecom/callback?msg_signature={sig}&timestamp={timestamp}&nonce={nonce}&echostr={echostr}",
            headers=headers,
        )
        assert verify.status_code == 200
        assert verify.text == echostr

        xml = """
        <xml>
          <ToUserName><![CDATA[toUser]]></ToUserName>
          <FromUserName><![CDATA[wecom-user-1]]></FromUserName>
          <CreateTime>1348831860</CreateTime>
          <MsgType><![CDATA[text]]></MsgType>
          <Content><![CDATA[hello from wecom]]></Content>
          <MsgId>1234567890123456</MsgId>
          <AgentID>1000002</AgentID>
        </xml>
        """.strip()
        body_sig = hashlib.sha1("".join(sorted(["tok", timestamp, nonce, xml])).encode("utf-8")).hexdigest()
        post = app_client.post(
            f"/api/gateway/wecom/callback?msg_signature={body_sig}&timestamp={timestamp}&nonce={nonce}",
            headers={**headers, "content-type": "application/xml"},
            content=xml,
        )
        assert post.status_code == 200
        assert post.json()["ok"] == "success"
    finally:
        chat_api._build_engine = original_build  # type: ignore[assignment]
