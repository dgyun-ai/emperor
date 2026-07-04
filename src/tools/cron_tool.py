"""Automation scheduling tool."""

from __future__ import annotations

import json

from constants import get_emperor_home, normalize_profile
from context.tool_context import ToolContext
from cron.scheduler import CronScheduler
from tools.base import ToolResult
from tools.registry import register_tool

_schedulers: dict[str, CronScheduler] = {}


def get_scheduler(profile: str | None = None) -> CronScheduler:
    profile_name = normalize_profile(profile)
    home = get_emperor_home(profile_name)
    key = str(home)
    scheduler = _schedulers.get(key)
    if scheduler is None:
        scheduler = CronScheduler(home=home)
        _schedulers[key] = scheduler
    return scheduler


@register_tool(
    name="cron",
    description="Manage structured automation jobs with schedule and payload objects.",
    toolset="cron",
    input_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "add", "remove"]},
            "name": {"type": "string"},
            "schedule": {"type": "object"},
            "payload": {"type": "object"},
            "target_session_id": {"type": "string"},
            "job_id": {"type": "string"},
            "enabled": {"type": "boolean"},
        },
        "required": ["action"],
    },
)
async def cron_tool(input: dict, ctx: ToolContext) -> ToolResult:
    scheduler = get_scheduler(str(ctx.extra.get("profile") or "default"))
    action = input["action"]
    if action == "list":
        jobs = []
        for job in scheduler.list_jobs():
            payload = job.to_dict()
            payload["next_run_at"] = scheduler.next_run_at(job)
            jobs.append(payload)
        return ToolResult(content=json.dumps(jobs, ensure_ascii=False))
    if action == "add":
        schedule = input.get("schedule")
        payload = input.get("payload")
        name = input.get("name", "job")
        target_session_id = input.get("target_session_id", "")
        enabled = bool(input.get("enabled", True))
        try:
            job = scheduler.add_job(
                name=name,
                schedule=schedule,
                payload=payload,
                target_session_id=target_session_id,
                enabled=enabled,
            )
        except ValueError as exc:
            return ToolResult(content=str(exc), is_error=True)
        job_payload = job.to_dict()
        job_payload["next_run_at"] = scheduler.next_run_at(job)
        return ToolResult(content=json.dumps(job_payload, ensure_ascii=False))
    if action == "remove":
        job_id = input.get("job_id", "")
        ok = scheduler.remove_job(job_id)
        return ToolResult(content=json.dumps({"removed": ok}))
    return ToolResult(content="Unknown action", is_error=True)
