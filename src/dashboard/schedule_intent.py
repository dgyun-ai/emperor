"""Parse schedule intent from chat text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


_ACTION_HINTS = (
    "提醒",
    "给我",
    "发我",
    "发给我",
    "通知我",
    "告诉我",
    "生成",
    "提供",
    "发送",
    "汇报",
    "报告",
)


@dataclass
class ScheduleIntentResult:
    schedule: dict[str, object] | None = None
    payload: dict[str, object] | None = None
    error: str | None = None
    schedule_phrase: str | None = None


def _cleanup_action_text(text: str, schedule_phrase: str) -> str:
    cleaned = text.strip()
    if schedule_phrase:
        cleaned = cleaned.replace(schedule_phrase, "", 1).strip()
    cleaned = re.sub(r"^[，,、\s]+", "", cleaned)
    cleaned = re.sub(r"[。．\.]+$", "", cleaned)
    return cleaned.strip()


def _has_action_hint(text: str) -> bool:
    return any(token in text for token in _ACTION_HINTS)


def _to_agent_payload(action_text: str) -> dict[str, object]:
    return {"kind": "agentTurn", "message": f"这是之前安排的定时任务，请现在执行：{action_text}"}


def _period_to_hour(period: str, hour: int) -> int:
    if period in {"下午", "晚上", "今晚"} and hour < 12:
        return hour + 12
    if period == "中午" and hour < 11:
        return hour + 12
    if period == "凌晨" and hour == 12:
        return 0
    return hour


def _parse_relative(text: str, now: datetime) -> ScheduleIntentResult | None:
    match = re.search(r"(?P<value>\d+)\s*(?P<unit>秒钟后|秒后|分钟后|分后|小时后|天后)", text)
    if not match:
        return None
    value = int(match.group("value"))
    unit = match.group("unit")
    if "秒" in unit:
        delta = timedelta(seconds=value)
    elif "分" in unit:
        delta = timedelta(minutes=value)
    elif "小时" in unit:
        delta = timedelta(hours=value)
    else:
        delta = timedelta(days=value)
    action_text = _cleanup_action_text(text, match.group(0))
    if not action_text or not _has_action_hint(action_text):
        return ScheduleIntentResult(error="检测到定时表达，但缺少明确执行内容。", schedule_phrase=match.group(0))
    target = (now + delta).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return ScheduleIntentResult(schedule={"kind": "at", "at": target}, payload=_to_agent_payload(action_text), schedule_phrase=match.group(0))


def _parse_day_time(text: str, now: datetime) -> ScheduleIntentResult | None:
    match = re.search(
        r"(?P<day>今天|明天)\s*(?P<period>凌晨|早上|上午|中午|下午|晚上|今晚)?\s*"
        r"(?P<hour>\d{1,2})\s*(?:(?:[:：点时])\s*(?P<minute>\d{1,2})?\s*(?:分)?)?",
        text,
    )
    if not match:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    if hour > 23 or minute > 59:
        return ScheduleIntentResult(error="无法解析定时时间，请提供有效的小时和分钟。")
    target = now
    if match.group("day") == "明天":
        target = target + timedelta(days=1)
    hour = _period_to_hour(match.group("period") or "", hour)
    if hour > 23:
        return ScheduleIntentResult(error="无法解析定时时间，请检查上午/下午与小时是否冲突。")
    target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if match.group("day") == "今天" and target <= now:
        return ScheduleIntentResult(error="指定时间已过去，请提供未来时间。")
    action_text = _cleanup_action_text(text, match.group(0))
    if not action_text or not _has_action_hint(action_text):
        return ScheduleIntentResult(error="检测到定时表达，但缺少明确执行内容。", schedule_phrase=match.group(0))
    at = target.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return ScheduleIntentResult(schedule={"kind": "at", "at": at}, payload=_to_agent_payload(action_text), schedule_phrase=match.group(0))


def _parse_every(text: str) -> ScheduleIntentResult | None:
    match = re.search(r"每\s*(?P<value>\d+)\s*(?P<unit>秒|分钟|分|小时|天)\s*(?P<action>.*)", text)
    if not match:
        return None
    value = int(match.group("value"))
    unit = match.group("unit")
    factor = 1000 if unit == "秒" else 60 * 1000 if unit in {"分钟", "分"} else 3600 * 1000 if unit == "小时" else 24 * 3600 * 1000
    action_text = match.group("action").strip()
    if not action_text or not _has_action_hint(action_text):
        return ScheduleIntentResult(error="检测到周期任务，但缺少明确执行内容。", schedule_phrase=match.group(0))
    return ScheduleIntentResult(
        schedule={"kind": "every", "everyMs": value * factor},
        payload=_to_agent_payload(action_text),
        schedule_phrase=match.group(0),
    )


def _parse_daily_cron(text: str, now: datetime) -> ScheduleIntentResult | None:
    match = re.search(
        r"每天\s*(?P<period>凌晨|早上|上午|中午|下午|晚上|今晚)?\s*(?P<hour>\d{1,2})\s*(?:(?:[:：点时])\s*(?P<minute>\d{1,2})?\s*(?:分)?)?\s*(?P<action>.*)",
        text,
    )
    if not match:
        return None
    hour = _period_to_hour(match.group("period") or "", int(match.group("hour")))
    minute = int(match.group("minute") or 0)
    if hour > 23 or minute > 59:
        return ScheduleIntentResult(error="无法解析每天执行时间，请检查小时与分钟。")
    action_text = match.group("action").strip()
    if not action_text or not _has_action_hint(action_text):
        return ScheduleIntentResult(error="检测到周期任务，但缺少明确执行内容。", schedule_phrase=match.group(0))
    tz_name = str(now.tzinfo.key) if isinstance(now.tzinfo, ZoneInfo) else "UTC"
    return ScheduleIntentResult(
        schedule={"kind": "cron", "expr": f"{minute} {hour} * * *", "tz": tz_name},
        payload=_to_agent_payload(action_text),
        schedule_phrase=match.group(0),
    )


def _parse_weekly_cron(text: str, now: datetime) -> ScheduleIntentResult | None:
    match = re.search(
        r"每周(?P<dow>[一二三四五六日天])\s*(?P<period>凌晨|早上|上午|中午|下午|晚上|今晚)?\s*"
        r"(?P<hour>\d{1,2})\s*(?:(?:[:：点时])\s*(?P<minute>\d{1,2})?\s*(?:分)?)?\s*(?P<action>.*)",
        text,
    )
    if not match:
        return None
    weekday_map = {"日": 0, "天": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}
    hour = _period_to_hour(match.group("period") or "", int(match.group("hour")))
    minute = int(match.group("minute") or 0)
    if hour > 23 or minute > 59:
        return ScheduleIntentResult(error="无法解析每周执行时间，请检查小时与分钟。")
    action_text = match.group("action").strip()
    if not action_text or not _has_action_hint(action_text):
        return ScheduleIntentResult(error="检测到周期任务，但缺少明确执行内容。", schedule_phrase=match.group(0))
    tz_name = str(now.tzinfo.key) if isinstance(now.tzinfo, ZoneInfo) else "UTC"
    return ScheduleIntentResult(
        schedule={"kind": "cron", "expr": f"{minute} {hour} * * {weekday_map[match.group('dow')]}", "tz": tz_name},
        payload=_to_agent_payload(action_text),
        schedule_phrase=match.group(0),
    )


def detect_schedule_intent(text: str, *, now: datetime | None = None) -> ScheduleIntentResult | None:
    source = text.strip()
    if not source:
        return None
    current = now or datetime.now().astimezone()

    for parser in (_parse_relative, _parse_day_time):
        parsed = parser(source, current)
        if parsed is not None:
            return parsed

    for parser in (_parse_weekly_cron, _parse_daily_cron):
        parsed = parser(source, current)
        if parsed is not None:
            return parsed

    recurring = _parse_every(source)
    if recurring is not None:
        return recurring

    maybe_schedule = any(token in source for token in ("分钟后", "小时后", "天后", "明天", "今天", "每", "提醒"))
    if maybe_schedule and _has_action_hint(source):
        return ScheduleIntentResult(error="检测到定时请求，但暂时无法解析时间，请改成“5分钟后…”、“每天上午9点…”或“每周一9点…”。")
    return None
