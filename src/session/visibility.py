"""Rules for which sessions appear in the web dashboard."""

from __future__ import annotations

from session.store import SessionInfo
from session.title import is_garbage_title, is_placeholder_title


def should_show_in_dashboard(session: SessionInfo) -> bool:
    """Hide ephemeral CLI/test sessions that leaked into the shared DB."""
    if session.platform == "test":
        return False
    if session.platform not in (None, "cli"):
        return True
    if session.message_count > 2:
        return True
    title = (session.title or "").strip()
    if title and not is_garbage_title(title) and not is_placeholder_title(title):
        return True
    return False
