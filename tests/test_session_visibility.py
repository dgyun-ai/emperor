"""Tests for dashboard session visibility rules."""

from __future__ import annotations

from session.store import SessionInfo
from session.visibility import should_show_in_dashboard


def _session(**kwargs) -> SessionInfo:
    defaults = {
        "id": "sess-1",
        "profile": "default",
        "title": None,
        "platform": "cli",
        "created_at": 0.0,
        "updated_at": 0.0,
    }
    defaults.update(kwargs)
    return SessionInfo(**defaults)


def test_hides_cli_test_pollution():
    assert not should_show_in_dashboard(_session(title=None, message_count=2))
    assert not should_show_in_dashboard(_session(title="p1", message_count=2))
    assert not should_show_in_dashboard(_session(platform="test", message_count=2, title="hello"))


def test_shows_meaningful_sessions():
    assert should_show_in_dashboard(_session(platform="web", title="新会话", message_count=2))
    assert should_show_in_dashboard(_session(platform="cli", title="你是谁", message_count=2))
    assert should_show_in_dashboard(_session(platform="cli", title=None, message_count=8))
    assert should_show_in_dashboard(_session(platform="telegram", title=None, message_count=2))
