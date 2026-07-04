"""Local timezone formatting for session timestamps."""

from __future__ import annotations

from datetime import datetime


def format_local_timestamp(ts: float, *, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format UTC epoch seconds as local wall-clock time."""
    return datetime.fromtimestamp(ts).strftime(fmt)


def session_to_dict(info: object) -> dict[str, object]:
    """Serialize SessionInfo with a local-time field for CLI/JSON export."""
    from session.store import SessionInfo

    if not isinstance(info, SessionInfo):
        raise TypeError("expected SessionInfo")
    data: dict[str, object] = dict(info.__dict__)
    data["updated_at_local"] = format_local_timestamp(info.updated_at)
    return data


def format_session_age(ts: float, *, now: float | None = None) -> str:
    """Short relative age label (e.g. 5m, 2h, 3d)."""
    import time

    reference = now if now is not None else time.time()
    age_min = max(0, int((reference - ts) / 60))
    if age_min < 60:
        return f"{age_min}m"
    age_hours = age_min // 60
    if age_hours < 48:
        return f"{age_hours}h"
    return f"{age_hours // 24}d"
