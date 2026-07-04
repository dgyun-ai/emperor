"""Automation / cron jobs API."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from dashboard.context import get_request_config, get_request_profile, get_request_store
from tools.cron_tool import get_scheduler

router = APIRouter(prefix="/api/automation", tags=["automation"])


def configure_automation_api(profile: str | None = None) -> None:
    scheduler = get_scheduler(profile)

    async def execute_job(job, trigger: str) -> str:
        import dashboard.chat_api as chat_api

        store = get_request_store_from_profile(profile or "default")
        await store.initialize()
        if await store.get_session(job.target_session_id) is None:
            raise RuntimeError(f"Session not found: {job.target_session_id}")

        payload_kind = str(job.payload.get("kind") or "")
        if payload_kind == "systemEvent":
            text = str(job.payload.get("text") or "")
            await store.append_message(job.target_session_id, {"role": "system", "content": text})
            return f"{trigger}: system event injected"

        if payload_kind != "agentTurn":
            raise RuntimeError(f"Unsupported payload kind: {payload_kind}")

        config = get_request_config_from_profile(profile or "default").model_copy(deep=True)
        model_override: dict[str, Any] = {}
        if job.payload.get("model"):
            model_override["model"] = str(job.payload["model"])
        engine = chat_api._build_engine(
            profile=profile or "default",
            config=config,
            session_id=job.target_session_id,
            model_override=model_override or None,
        )
        await engine.initialize()
        await engine.resume_session(job.target_session_id)

        timeout_seconds = int(job.payload.get("timeoutSeconds") or 0)
        message = str(job.payload.get("message") or "")
        coro = engine.chat(message)
        if timeout_seconds > 0:
            reply = await asyncio.wait_for(coro, timeout=timeout_seconds)
        else:
            reply = await coro
        return f"{trigger}: {reply[:200]}"

    scheduler.set_executor(execute_job)


def get_request_config_from_profile(profile: str):
    from config.loader import load_config
    from constants import get_emperor_home

    return load_config(home=get_emperor_home(profile), profile=profile)


def get_request_store_from_profile(profile: str):
    from session.store import SessionStore

    return SessionStore.for_profile(profile)


def _scheduler_for_request(request: Request):
    return get_scheduler(get_request_profile(request))


async def _require_session(request: Request, session_id: str) -> None:
    store = get_request_store(request)
    await store.initialize()
    if await store.get_session(session_id) is None:
        raise HTTPException(400, f"Session not found: {session_id}")


def _job_payload(job, scheduler) -> dict[str, Any]:
    payload = job.to_dict()
    payload["next_run_at"] = scheduler.next_run_at(job)
    return payload


def _run_payload(run) -> dict[str, Any]:
    return run.to_dict()


class ScheduleAt(BaseModel):
    kind: Literal["at"]
    at: str


class ScheduleEvery(BaseModel):
    kind: Literal["every"]
    everyMs: int = Field(gt=0)
    anchorMs: int | None = None


class ScheduleCron(BaseModel):
    kind: Literal["cron"]
    expr: str = Field(min_length=1)
    tz: str | None = None


class PayloadSystemEvent(BaseModel):
    kind: Literal["systemEvent"]
    text: str = Field(min_length=1)


class PayloadAgentTurn(BaseModel):
    kind: Literal["agentTurn"]
    message: str = Field(min_length=1)
    model: str | None = None
    thinking: str | None = None
    timeoutSeconds: int | None = None


ScheduleModel = ScheduleAt | ScheduleEvery | ScheduleCron
PayloadModel = PayloadSystemEvent | PayloadAgentTurn


class JobCreate(BaseModel):
    name: str = Field(min_length=1)
    schedule: ScheduleModel
    payload: PayloadModel
    target_session_id: str = Field(min_length=1)
    enabled: bool = True


class JobUpdate(BaseModel):
    name: str | None = None
    schedule: ScheduleModel | None = None
    payload: PayloadModel | None = None
    target_session_id: str | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def ensure_non_empty_update(self):
        if (
            self.name is None
            and self.schedule is None
            and self.payload is None
            and self.target_session_id is None
            and self.enabled is None
        ):
            raise ValueError("Empty update payload")
        return self


@router.get("/status")
async def automation_status(request: Request):
    scheduler = _scheduler_for_request(request)
    return {
        "ok": True,
        "running": True,
        "job_count": len(scheduler.list_jobs()),
        "running_count": scheduler.running_count(),
        "failed_count": scheduler.failed_count(),
    }


@router.get("/jobs")
async def list_jobs(request: Request):
    scheduler = _scheduler_for_request(request)
    return {"jobs": [_job_payload(job, scheduler) for job in scheduler.list_jobs()]}


@router.post("/jobs")
async def create_job(request: Request, req: JobCreate):
    await _require_session(request, req.target_session_id)
    scheduler = _scheduler_for_request(request)
    try:
        job = scheduler.add_job(
            name=req.name,
            schedule=req.schedule.model_dump(exclude_none=True),
            payload=req.payload.model_dump(exclude_none=True),
            target_session_id=req.target_session_id,
            enabled=req.enabled,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"job": _job_payload(job, scheduler)}


@router.get("/jobs/{job_id}")
async def get_job(request: Request, job_id: str):
    scheduler = _scheduler_for_request(request)
    job = scheduler.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return {"job": _job_payload(job, scheduler), "runs": [_run_payload(run) for run in scheduler.list_runs(job_id=job_id)]}


@router.patch("/jobs/{job_id}")
async def update_job(request: Request, job_id: str, req: JobUpdate):
    if req.target_session_id is not None:
        await _require_session(request, req.target_session_id)
    scheduler = _scheduler_for_request(request)
    try:
        job = scheduler.update_job(
            job_id,
            name=req.name,
            schedule=req.schedule.model_dump(exclude_none=True) if req.schedule is not None else None,
            payload=req.payload.model_dump(exclude_none=True) if req.payload is not None else None,
            target_session_id=req.target_session_id,
            enabled=req.enabled,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if job is None:
        raise HTTPException(404, "Job not found")
    return {"job": _job_payload(job, scheduler)}


@router.delete("/jobs/{job_id}")
async def delete_job(request: Request, job_id: str):
    scheduler = _scheduler_for_request(request)
    if scheduler.remove_job(job_id):
        return {"ok": True}
    raise HTTPException(404, "Job not found")


@router.post("/jobs/{job_id}/trigger")
async def trigger_job(request: Request, job_id: str):
    scheduler = _scheduler_for_request(request)
    try:
        run = await scheduler.trigger_job(job_id, trigger="manual")
    except KeyError as exc:
        raise HTTPException(404, "Job not found") from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True, "run": _run_payload(run)}


@router.get("/runs")
async def list_runs(request: Request, status: str | None = None, job_id: str | None = None):
    scheduler = _scheduler_for_request(request)
    return {"runs": [_run_payload(run) for run in scheduler.list_runs(status=status, job_id=job_id)]}


@router.post("/runs/{run_id}/cancel")
async def cancel_run(request: Request, run_id: str):
    scheduler = _scheduler_for_request(request)
    if await scheduler.cancel_run(run_id):
        run = scheduler.get_run(run_id)
        return {"ok": True, "run": _run_payload(run) if run is not None else None}
    raise HTTPException(404, "Run not found or not running")
