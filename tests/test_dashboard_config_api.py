"""Tests for dashboard config API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from config.models import EmperorConfig
from dashboard.server import create_dashboard_app
from helpers import bootstrap_dashboard


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPEROR_HOME", str(tmp_path))
    app = create_dashboard_app(EmperorConfig(), start_dispatcher_loop=False)
    with TestClient(app) as c:
        headers = bootstrap_dashboard(c)
        yield c, headers


def test_get_provider_masks_key(client: tuple[TestClient, dict[str, str]], tmp_path):
    http, headers = client
    cfg_dir = tmp_path / "profiles" / "default"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "config.yaml"
    cfg_path.write_text(
        "provider:\n  provider: openrouter\n  model: test-model\n  api_key: secret-key\n",
        encoding="utf-8",
    )
    data = http.get("/api/config/provider", headers=headers).json()
    assert data["provider"]["model"] == "test-model"
    assert data["provider"].get("api_key") == "***"


def test_put_provider(client: tuple[TestClient, dict[str, str]]):
    http, headers = client
    http.put(
        "/api/config/provider",
        json={
            "provider": {"provider": "openai", "model": "gpt-4o", "base_url": "https://api.openai.com/v1"},
            "fallback_providers": [],
        },
        headers=headers,
    )
    data = http.get("/api/config/provider", headers=headers).json()
    assert data["provider"]["model"] == "gpt-4o"


def test_model_presets(client: tuple[TestClient, dict[str, str]]):
    http, headers = client
    data = http.get("/api/config/models/presets", headers=headers).json()
    assert len(data["presets"]) >= 1
