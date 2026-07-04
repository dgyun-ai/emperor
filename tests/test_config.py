"""Config loading tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from config.loader import load_config, save_config
from config.models import EmperorConfig
from constants import DEFAULT_EMPEROR_HOME_NAME, get_config_path, get_emperor_home


def test_default_emperor_home_is_user_data_root(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("EMPEROR_HOME", raising=False)
    home = Path.home() / DEFAULT_EMPEROR_HOME_NAME
    if not os.access(home.parent, os.W_OK):
        home = Path.cwd() / DEFAULT_EMPEROR_HOME_NAME
    assert get_emperor_home() == home
    assert get_emperor_home("default") == home / "profiles" / "default"


def test_load_default_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EMPEROR_HOME", str(tmp_path))
    config = load_config()
    assert config.provider.provider == "openrouter"
    assert get_config_path(tmp_path).exists()


def test_save_and_reload_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EMPEROR_HOME", str(tmp_path))
    config = EmperorConfig()
    config.provider.model = "test/model"
    save_config(config, tmp_path)
    reloaded = load_config(home=tmp_path)
    assert reloaded.provider.model == "test/model"
