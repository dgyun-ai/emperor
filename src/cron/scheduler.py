"""Profile-scoped automation scheduler with structured schedules and payloads."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from constants import get_emperor_home
from cron.jobs import (
    RUN_STATUS_CANCELLED,
    RUN_STATUS_FAILED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_SUCCEEDED,
    CronJob,
    CronRun,
    PayloadSpec,
    ScheduleSpec,
    new_job,
    new_run,
)

JobExecutor = Callable[[CronJob, str], Awaitable[str]]


def _parse_iso_timestamp(value: str) -> datetime:
    source = value.strip()
    if not source:
        raise ValueError("Schedule at.at must not be empty")
    if source.endswith("Z"):
        source = source[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(source)
    except ValueError as exc:
        raise ValueError("Schedule at.at must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if coerced <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return coerced


def _coerce_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _parse_cron_token(token: str, minimum: int, maximum: int) -> set[int]:
    values: set[int] = set()
    for part in token.split(","):
        item = part.strip()
        if not item:
            raise ValueError("Cron tokens must not be empty")
        if item == "*":
            values.update(range(minimum, maximum + 1))
            continue
        if item.startswith("*/"):
            step = _coerce_positive_int(item[2:], "Cron step")
            values.update(range(minimum, maximum + 1, step))
            continue
        if "-" in item:
            left, right = item.split("-", 1)
            start = _coerce_int(left, "Cron range start")
            end = _coerce_int(right, "Cron range end")
            if start > end:
                raise ValueError("Cron range start must be <= end")
            if start < minimum or end > maximum:
                raise ValueError("Cron range is out of bounds")
            values.update(range(start, end + 1))
            continue
        try:
            current = _coerce_int(item, "Cron token")
        except ValueError as exc:
            raise ValueError("Cron token must be numeric, *, */n, n-m, or comma-separated") from exc
        if current < minimum or current > maximum:
            raise ValueError("Cron token is out of bounds")
        values.add(current)
    return values


def _weekday_value(dt: datetime) -> int:
    return (dt.weekday() + 1) % 7


class CronScheduler:
    """Scheduler for at/every/cron jobs with old-format migration."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = home or get_emperor_home()
        self.home.mkdir(parents=True, exist_ok=True)
        self.jobs_path = self.home / "cron_jobs.json"
        self.runs_path = self.home / "cron_runs.json"
        self._jobs: list[CronJob] = []
        self._runs: list[CronRun] = []
        self._task: asyncio.Task[None] | None = None
        self._executor: JobExecutor | None = None
        self._run_tasks: dict[str, asyncio.Task[None]] = {}
        self._job_running: dict[str, str] = {}
        self._loop_handle: asyncio.AbstractEventLoop | None = None
        self._load()

    def _normalize_legacy_job(self, raw: dict[str, Any]) -> tuple[CronJob, bool]:
        mutated = False
        if "target_session_id" in raw and "payload" in raw and "schedule" in raw and isinstance(raw["schedule"], dict):
            return CronJob(**raw), mutated

        kind = str(raw.get("kind") or "recurring").strip().lower()
        schedule: ScheduleSpec
        if kind == "once":
            run_at = raw.get("run_at")
            if run_at is None:
                raise ValueError("Legacy one-shot jobs require run_at")
            schedule = {"kind": "at", "at": _format_iso_utc(datetime.fromtimestamp(float(run_at), tz=timezone.utc))}
        else:
            schedule_str = str(raw.get("schedule") or "")
            if not schedule_str.startswith("every:"):
                raise ValueError("Legacy recurring jobs must use every:N format")
            seconds = float(schedule_str.split(":", 1)[1])
            schedule = {"kind": "every", "everyMs": int(seconds * 1000)}
        payload: PayloadSpec = {"kind": "agentTurn", "message": str(raw.get("message") or "")}
        job = CronJob(
            id=str(raw["id"]),
            name=str(raw.get("name") or "job"),
            schedule=schedule,
            payload=payload,
            target_session_id=str(raw.get("session_id") or ""),
            enabled=bool(raw.get("enabled", True)),
            created_at=float(raw.get("created_at") or time.time()),
            updated_at=float(raw.get("updated_at") or time.time()),
            last_run_at=float(raw["last_run_at"]) if raw.get("last_run_at") is not None else None,
            last_status=str(raw["last_status"]) if raw.get("last_status") is not None else None,
            last_error=str(raw["last_error"]) if raw.get("last_error") is not None else None,
            last_run_id=str(raw["last_run_id"]) if raw.get("last_run_id") is not None else None,
        )
        mutated = True
        return job, mutated

    def _load(self) -> None:
        write_back_jobs = False
        if self.jobs_path.exists():
            raw_jobs = json.loads(self.jobs_path.read_text(encoding="utf-8"))
            normalized_jobs: list[CronJob] = []
            for item in raw_jobs:
                job, mutated = self._normalize_legacy_job(item)
                job.schedule = self._validate_schedule(
                    job.schedule,
                    created_at=job.created_at,
                    allow_past=True,
                )
                job.payload = self._validate_payload(job.payload)
                if not job.target_session_id.strip():
                    raise ValueError("Job target_session_id must not be empty")
                normalized_jobs.append(job)
                write_back_jobs = write_back_jobs or mutated
            self._jobs = normalized_jobs
        if self.runs_path.exists():
            raw_runs = json.loads(self.runs_path.read_text(encoding="utf-8"))
            self._runs = [CronRun(**item) for item in raw_runs]
        if write_back_jobs:
            self._save_jobs()

    def _save_jobs(self) -> None:
        data = [job.to_dict() for job in self._jobs]
        self.jobs_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _save_runs(self) -> None:
        data = [run.to_dict() for run in self._runs]
        self.runs_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _validate_schedule(
        self,
        schedule: ScheduleSpec,
        *,
        created_at: float | None = None,
        allow_past: bool = False,
    ) -> ScheduleSpec:
        if not isinstance(schedule, dict):
            raise ValueError("Schedule must be an object")
        kind = str(schedule.get("kind") or "").strip()
        if kind not in {"at", "every", "cron"}:
            raise ValueError("Schedule kind must be at, every, or cron")
        normalized: ScheduleSpec = {"kind": kind}
        now = datetime.now(tz=timezone.utc)
        if kind == "at":
            raw_at = schedule.get("at")
            if not isinstance(raw_at, str):
                raise ValueError("Schedule at.at must be a string")
            parsed = _parse_iso_timestamp(raw_at)
            if not allow_past and parsed <= now:
                raise ValueError("Schedule at.at must be in the future")
            normalized["at"] = _format_iso_utc(parsed)
            return normalized
        if kind == "every":
            every_ms = _coerce_positive_int(schedule.get("everyMs"), "Schedule every.everyMs")
            normalized["everyMs"] = every_ms
            anchor = schedule.get("anchorMs")
            if anchor is not None:
                normalized["anchorMs"] = int(anchor)
            elif created_at is not None:
                normalized["anchorMs"] = int(created_at * 1000)
            return normalized
        expr = schedule.get("expr")
        if not isinstance(expr, str) or not expr.strip():
            raise ValueError("Schedule cron.expr must be a non-empty string")
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError("Schedule cron.expr must have 5 fields")
        _parse_cron_token(parts[0], 0, 59)
        _parse_cron_token(parts[1], 0, 23)
        _parse_cron_token(parts[2], 1, 31)
        _parse_cron_token(parts[3], 1, 12)
        _parse_cron_token(parts[4], 0, 7)
        tz_name = str(schedule.get("tz") or "UTC")
        try:
            ZoneInfo(tz_name)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Schedule cron.tz must be a valid IANA timezone") from exc
        normalized["expr"] = " ".join(parts)
        normalized["tz"] = tz_name
        return normalized

    def _validate_payload(self, payload: PayloadSpec) -> PayloadSpec:
        if not isinstance(payload, dict):
            raise ValueError("Payload must be an object")
        kind = str(payload.get("kind") or "").strip()
        if kind == "systemEvent":
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Payload systemEvent.text must be a non-empty string")
            return {"kind": "systemEvent", "text": text}
        if kind == "agentTurn":
            message = payload.get("message")
            if not isinstance(message, str) or not message.strip():
                raise ValueError("Payload agentTurn.message must be a non-empty string")
            normalized: PayloadSpec = {"kind": "agentTurn", "message": message}
            model = payload.get("model")
            if model is not None:
                normalized["model"] = str(model)
            thinking = payload.get("thinking")
            if thinking is not None:
                normalized["thinking"] = str(thinking)
            timeout = payload.get("timeoutSeconds")
            if timeout is not None:
                if isinstance(timeout, bool):
                    raise ValueError("Payload agentTurn.timeoutSeconds must be an integer")
                normalized["timeoutSeconds"] = int(timeout)
            return normalized
        raise ValueError("Payload kind must be systemEvent or agentTurn")

    def _validate_job_fields(
        self,
        *,
        schedule: ScheduleSpec,
        payload: PayloadSpec,
        target_session_id: str,
        created_at: float | None = None,
        allow_past: bool = False,
    ) -> tuple[ScheduleSpec, PayloadSpec, str]:
        normalized_schedule = self._validate_schedule(schedule, created_at=created_at, allow_past=allow_past)
        normalized_payload = self._validate_payload(payload)
        target = target_session_id.strip()
        if not target:
            raise ValueError("Job target_session_id must not be empty")
        return normalized_schedule, normalized_payload, target

    def _cron_next_after(self, schedule: ScheduleSpec, after_ms: int) -> int:
        expr = str(schedule["expr"])
        minute_values = _parse_cron_token(expr.split()[0], 0, 59)
        hour_values = _parse_cron_token(expr.split()[1], 0, 23)
        dom_values = _parse_cron_token(expr.split()[2], 1, 31)
        month_values = _parse_cron_token(expr.split()[3], 1, 12)
        raw_dow_values = _parse_cron_token(expr.split()[4], 0, 7)
        dow_values = {0 if value == 7 else value for value in raw_dow_values}
        zone = ZoneInfo(str(schedule.get("tz") or "UTC"))
        current = datetime.fromtimestamp(after_ms / 1000, tz=zone).replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = current + timedelta(days=366)
        while current <= limit:
            if (
                current.minute in minute_values
                and current.hour in hour_values
                and current.day in dom_values
                and current.month in month_values
                and _weekday_value(current) in dow_values
            ):
                return int(current.astimezone(timezone.utc).timestamp() * 1000)
            current += timedelta(minutes=1)
        raise ValueError("Unable to compute next cron occurrence within 1 year")

    def next_run_at(self, job: CronJob, *, now: float | None = None) -> float | None:
        current_ts = now if now is not None else time.time()
        schedule = job.schedule
        kind = str(schedule["kind"])
        if not job.enabled:
            return None
        if kind == "at":
            if job.last_run_at is not None:
                return None
            return _parse_iso_timestamp(str(schedule["at"])).timestamp()
        if kind == "every":
            every_ms = int(schedule["everyMs"])
            anchor_ms = int(schedule.get("anchorMs") or int(job.created_at * 1000))
            if job.last_run_at is None:
                return anchor_ms / 1000
            return job.last_run_at + every_ms / 1000
        reference_ms = int((job.last_run_at if job.last_run_at is not None else (job.created_at - 1)) * 1000)
        next_ms = self._cron_next_after(schedule, reference_ms)
        return next_ms / 1000 if next_ms / 1000 >= current_ts - 366 * 24 * 3600 else None

    def set_executor(self, executor: JobExecutor) -> None:
        self._executor = executor

    def add_job(
        self,
        *,
        name: str,
        schedule: ScheduleSpec,
        payload: PayloadSpec,
        target_session_id: str,
        enabled: bool = True,
    ) -> CronJob:
        created_at = time.time()
        normalized_schedule, normalized_payload, normalized_target = self._validate_job_fields(
            schedule=schedule,
            payload=payload,
            target_session_id=target_session_id,
            created_at=created_at,
        )
        job = new_job(
            name=name,
            schedule=normalized_schedule,
            payload=normalized_payload,
            target_session_id=normalized_target,
        )
        job.enabled = enabled
        self._jobs.append(job)
        self._save_jobs()
        return job

    def list_jobs(self) -> list[CronJob]:
        return list(self._jobs)

    def get_job(self, job_id: str) -> CronJob | None:
        return next((job for job in self._jobs if job.id == job_id), None)

    def update_job(
        self,
        job_id: str,
        *,
        name: str | None = None,
        schedule: ScheduleSpec | None = None,
        payload: PayloadSpec | None = None,
        target_session_id: str | None = None,
        enabled: bool | None = None,
    ) -> CronJob | None:
        job = self.get_job(job_id)
        if job is None:
            return None
        next_schedule = schedule if schedule is not None else job.schedule
        next_payload = payload if payload is not None else job.payload
        next_target = target_session_id if target_session_id is not None else job.target_session_id
        normalized_schedule, normalized_payload, normalized_target = self._validate_job_fields(
            schedule=next_schedule,
            payload=next_payload,
            target_session_id=next_target,
            created_at=job.created_at,
            allow_past=job.last_run_at is not None or not job.enabled,
        )
        job.schedule = normalized_schedule
        job.payload = normalized_payload
        job.target_session_id = normalized_target
        if name is not None:
            job.name = name
        if enabled is not None:
            job.enabled = enabled
        job.updated_at = time.time()
        self._save_jobs()
        return job

    def remove_job(self, job_id: str) -> bool:
        before = len(self._jobs)
        self._jobs = [job for job in self._jobs if job.id != job_id]
        if len(self._jobs) == before:
            return False
        self._save_jobs()
        return True

    def list_runs(self, *, job_id: str | None = None, status: str | None = None, limit: int = 100) -> list[CronRun]:
        runs = self._runs
        if job_id:
            runs = [run for run in runs if run.job_id == job_id]
        if status:
            runs = [run for run in runs if run.status == status]
        runs = sorted(runs, key=lambda run: run.started_at or 0, reverse=True)
        return runs[:limit]

    def get_run(self, run_id: str) -> CronRun | None:
        return next((run for run in self._runs if run.run_id == run_id), None)

    def running_count(self) -> int:
        return sum(1 for run in self._runs if run.status == RUN_STATUS_RUNNING)

    def failed_count(self) -> int:
        return sum(1 for run in self._runs if run.status == RUN_STATUS_FAILED)

    def bind_running_task(self, run_id: str, task: asyncio.Task[None], job_id: str) -> None:
        self._run_tasks[run_id] = task
        self._job_running[job_id] = run_id

    async def cancel_run(self, run_id: str) -> bool:
        run = self.get_run(run_id)
        if run is None or run.status != RUN_STATUS_RUNNING:
            return False
        task = self._run_tasks.get(run_id)
        if task is None:
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True

    async def start(self) -> None:
        if self._task is not None:
            return
        self._loop_handle = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        for run_id in list(self._run_tasks):
            await self.cancel_run(run_id)
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._loop_handle = None

    def _create_run(self, job: CronJob, trigger: str) -> CronRun:
        run = new_run(job, trigger=trigger)
        self._runs.append(run)
        self._save_runs()
        return run

    def _set_run_status(
        self,
        run: CronRun,
        *,
        status: str,
        result_summary: str | None = None,
        error: str | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> None:
        now = time.time()
        run.status = status
        if started and run.started_at is None:
            run.started_at = now
        if finished:
            run.finished_at = now
        if result_summary is not None:
            run.result_summary = result_summary
        if error is not None:
            run.error = error
        self._save_runs()

        job = self.get_job(run.job_id)
        if job is not None:
            job.last_run_id = run.run_id
            if started:
                job.last_run_at = run.started_at
            job.last_status = status
            job.last_error = error
            job.updated_at = now
            if job.schedule.get("kind") == "at" and status in {RUN_STATUS_SUCCEEDED, RUN_STATUS_FAILED, RUN_STATUS_CANCELLED}:
                job.enabled = False
            self._save_jobs()

    async def trigger_job(self, job_id: str, *, trigger: str = "manual") -> CronRun:
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if self._job_running.get(job.id):
            raise RuntimeError("Job is already running")
        if self._executor is None:
            raise RuntimeError("Scheduler executor not configured")
        if self._loop_handle is None:
            self._loop_handle = asyncio.get_running_loop()
        run = self._create_run(job, trigger)
        task = self._loop_handle.create_task(self._execute_run(job, run))
        self.bind_running_task(run.run_id, task, job.id)
        return run

    async def _execute_run(self, job: CronJob, run: CronRun) -> None:
        self._set_run_status(run, status=RUN_STATUS_RUNNING, started=True)
        try:
            assert self._executor is not None
            result = await self._executor(job, run.trigger)
        except asyncio.CancelledError:
            self._set_run_status(run, status=RUN_STATUS_CANCELLED, finished=True, error="Cancelled")
            raise
        except Exception as exc:  # noqa: BLE001
            self._set_run_status(run, status=RUN_STATUS_FAILED, finished=True, error=str(exc))
        else:
            self._set_run_status(
                run,
                status=RUN_STATUS_SUCCEEDED,
                finished=True,
                result_summary=result[:500],
                error=None,
            )
        finally:
            self._run_tasks.pop(run.run_id, None)
            self._job_running.pop(job.id, None)

    async def _loop(self) -> None:
        while True:
            now = time.time()
            for job in self._jobs:
                if not job.enabled or self._executor is None:
                    continue
                if self._job_running.get(job.id):
                    continue
                next_run = self.next_run_at(job, now=now)
                if next_run is None or next_run > now:
                    continue
                run = self._create_run(job, "schedule")
                task = (self._loop_handle or asyncio.get_running_loop()).create_task(self._execute_run(job, run))
                self.bind_running_task(run.run_id, task, job.id)
            await asyncio.sleep(1)
