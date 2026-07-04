"""Cron job and run definitions."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any


RUN_STATUS_QUEUED = "queued"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_SUCCEEDED = "succeeded"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_CANCELLED = "cancelled"

RUN_STATUSES = {
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_SUCCEEDED,
    RUN_STATUS_FAILED,
    RUN_STATUS_CANCELLED,
}

ScheduleSpec = dict[str, Any]
PayloadSpec = dict[str, Any]


@dataclass
class CronJob:
    id: str
    name: str
    schedule: ScheduleSpec
    payload: PayloadSpec
    target_session_id: str
    enabled: bool = True
    created_at: float = 0.0
    updated_at: float = 0.0
    last_run_at: float | None = None
    last_status: str | None = None
    last_error: str | None = None
    last_run_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class CronRun:
    run_id: str
    job_id: str
    status: str
    trigger: str
    session_id: str
    message: str
    started_at: float | None = None
    finished_at: float | None = None
    result_summary: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def payload_summary(payload: PayloadSpec) -> str:
    kind = str(payload.get("kind") or "")
    if kind == "systemEvent":
        text = payload.get("text")
        return str(text) if isinstance(text, str) else ""
    if kind == "agentTurn":
        message = payload.get("message")
        return str(message) if isinstance(message, str) else ""
    return ""


def new_job(
    *,
    name: str,
    schedule: ScheduleSpec,
    payload: PayloadSpec,
    target_session_id: str,
) -> CronJob:
    now = time.time()
    return CronJob(
        id=str(uuid.uuid4()),
        name=name,
        schedule=schedule,
        payload=payload,
        target_session_id=target_session_id,
        created_at=now,
        updated_at=now,
    )


def new_run(job: CronJob, trigger: str) -> CronRun:
    return CronRun(
        run_id=str(uuid.uuid4()),
        job_id=job.id,
        status=RUN_STATUS_QUEUED,
        trigger=trigger,
        session_id=job.target_session_id,
        message=payload_summary(job.payload),
    )
