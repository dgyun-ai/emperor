"""Pytest configuration."""

from __future__ import annotations

import pytest

import tools.builtin  # noqa: F401 — register echo tool


@pytest.fixture(autouse=True)
def isolate_emperor_home(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Never write session data to the developer's real ~/.emperor directory."""
    monkeypatch.setenv("EMPEROR_HOME", str(tmp_path))
