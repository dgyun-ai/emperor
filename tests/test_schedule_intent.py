from __future__ import annotations

from datetime import datetime

from dashboard.schedule_intent import detect_schedule_intent


def test_detect_relative_schedule_intent():
    now = datetime.fromisoformat("2026-07-02T10:00:00+08:00")
    parsed = detect_schedule_intent("5分钟后，给我一个动量报告", now=now)

    assert parsed is not None
    assert parsed.schedule == {"kind": "at", "at": "2026-07-02T02:05:00Z"}
    assert parsed.payload is not None
    assert "动量报告" in str(parsed.payload.get("message") or "")


def test_detect_absolute_schedule_intent():
    now = datetime.fromisoformat("2026-07-02T10:00:00+08:00")
    parsed = detect_schedule_intent("明天上午9点提醒我看盘", now=now)

    assert parsed is not None
    assert parsed.schedule == {"kind": "at", "at": "2026-07-03T01:00:00Z"}
    assert parsed.payload is not None
    assert "提醒我看盘" in str(parsed.payload.get("message") or "")


def test_detect_every_schedule_intent():
    parsed = detect_schedule_intent("每5分钟给我一次报告")

    assert parsed is not None
    assert parsed.schedule == {"kind": "every", "everyMs": 300000}
    assert parsed.payload is not None


def test_detect_daily_cron_schedule_intent():
    now = datetime.fromisoformat("2026-07-02T10:00:00+08:00")
    parsed = detect_schedule_intent("每天上午9点提醒我看盘", now=now)

    assert parsed is not None
    assert parsed.schedule == {"kind": "cron", "expr": "0 9 * * *", "tz": "UTC"}


def test_detect_weekly_cron_schedule_intent():
    now = datetime.fromisoformat("2026-07-02T10:00:00+08:00")
    parsed = detect_schedule_intent("每周一 9 点提醒我复盘", now=now)

    assert parsed is not None
    assert parsed.schedule == {"kind": "cron", "expr": "0 9 * * 1", "tz": "UTC"}
