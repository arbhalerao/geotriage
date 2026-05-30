"""
the execution engine: claim jobs, run them, resolve dependencies and fan-in

pure queue mechanism — it knows nothing about what the tasks actually do
tasks are looked up by name in the registry and called with their stored args;
they open their own DB sessions
the session used here is only for queue bookkeeping
"""

import logging
import os
import random
import socket
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text, update

from core.db.sync import get_session
from worker.queue.enqueue import build_job
from worker.queue.models import Job, JobGroup, JobStatus, TERMINAL
from worker.queue.registry import get_task, is_registered

log = logging.getLogger(__name__)

LEASE_SECONDS = int(os.getenv("WORKER_LEASE_SECONDS", "1800"))
# renew the lease well within its window so the reaper never steals a job that's still being worked on (e.g. a slow multi-band download)
HEARTBEAT_INTERVAL = max(LEASE_SECONDS / 3.0, 10.0)
POLL_INTERVAL = float(os.getenv("WORKER_POLL_SECONDS", "1.0"))
POLL_JITTER = float(os.getenv("WORKER_POLL_JITTER", "0.5"))
BASE_BACKOFF = float(os.getenv("WORKER_BACKOFF_BASE", "2.0"))
MAX_BACKOFF = float(os.getenv("WORKER_BACKOFF_MAX", "300"))
BACKOFF_JITTER = 0.25


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _backoff_seconds(attempts: int) -> float:
    base = min(BASE_BACKOFF * (2 ** max(attempts - 1, 0)), MAX_BACKOFF)
    return base + random.uniform(0, base * BACKOFF_JITTER)


_CLAIM_SQL = text(
    """
    WITH c AS (
        SELECT id FROM jobs
        WHERE status = 'ready' AND run_after <= now()
        ORDER BY priority DESC, run_after
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    UPDATE jobs
       SET status = 'running',
           locked_by = :wid,
           locked_at = now(),
           locked_until = now() + make_interval(secs => :lease),
           attempts = attempts + 1,
           started_at = COALESCE(started_at, now())
      FROM c
     WHERE jobs.id = c.id
    RETURNING jobs.id
    """
)


def claim_one(session, worker_id: str):
    """SKIP LOCKED lets n workers run this concurrently and each get a distinct row"""
    row = session.execute(_CLAIM_SQL, {"wid": worker_id, "lease": LEASE_SECONDS}).first()
    session.commit()
    return row[0] if row else None


def _resolve_dependents(session, finished_job_id) -> None:
    dependents = session.execute(select(Job).where(Job.depends_on.any(finished_job_id), Job.status == JobStatus.blocked).with_for_update(skip_locked=True)).scalars().all()
    for dep in dependents:
        dep_statuses = session.execute(select(Job.status).where(Job.id.in_(dep.depends_on))).scalars().all()
        # if any dependency failed terminally,
        # this job can never run → skip it (which itself cascades to *its* dependents and decrements its group)
        if any(s in (JobStatus.dead, JobStatus.skipped) for s in dep_statuses):
            _finish_terminal(session, dep, JobStatus.skipped)
        elif all(s == JobStatus.succeeded for s in dep_statuses):
            dep.status = JobStatus.ready
            dep.run_after = _now()
        # else: some dependency still pending → leave blocked


def _decrement_group(session, group_id) -> None:
    """
    the worker that brings a group's barrier to zero enqueues the continuation,
    exactly once, guarded by on_complete_enqueued
    """
    remaining = (session.execute(update(JobGroup).where(JobGroup.id == group_id).values(pending_count=JobGroup.pending_count - 1).returning(JobGroup.pending_count))).scalar_one()
    if remaining > 0:
        return
    won = session.execute(update(JobGroup).where(JobGroup.id == group_id, JobGroup.on_complete_enqueued.is_(False)).values(on_complete_enqueued=True).returning(JobGroup.id)).first()
    if won is None:
        return  # another worker already enqueued the continuation
    group = session.get(JobGroup, group_id)
    if group.on_complete_task:
        session.add(
            build_job(
                group.on_complete_task,
                group.on_complete_args,
                priority=group.on_complete_priority,
            )
        )


def _finish_terminal(session, job: Job, status: JobStatus) -> None:
    """everything happens in the caller's transaction, so it is atomic and idempotent"""
    assert status in TERMINAL
    job.status = status
    job.finished_at = _now()
    job.locked_by = None
    job.locked_until = None
    group_id = job.group_id
    _resolve_dependents(session, job.id)
    if group_id is not None:
        _decrement_group(session, group_id)


def _reschedule(session, job: Job, error: Exception) -> None:
    job.status = JobStatus.ready
    job.run_after = _now() + timedelta(seconds=_backoff_seconds(job.attempts))
    job.last_error = str(error)[:1000]
    job.locked_by = None
    job.locked_until = None


def _heartbeat(job_id, stop_event: threading.Event) -> None:
    """push the lease forward so the reaper doesn't treat a slow-but-alive worker as dead"""
    while not stop_event.wait(HEARTBEAT_INTERVAL):
        try:
            with get_session() as s:
                s.execute(update(Job).where(Job.id == job_id, Job.status == JobStatus.running).values(locked_until=_now() + timedelta(seconds=LEASE_SECONDS)))
                s.commit()
        except Exception:  # noqa: BLE001 — a failed heartbeat must not kill the worker
            log.warning("heartbeat failed for job %s", job_id, exc_info=True)


def execute_job(job_id, worker_id: str) -> None:
    with get_session() as s:
        job = s.get(Job, job_id)
        if job is None:
            return
        task_name = job.task_name
        args = list(job.args or [])

    if not is_registered(task_name):
        # unknown task — permanent failure, don't burn retries on it
        with get_session() as s:
            job = s.get(Job, job_id)
            if job and job.status == JobStatus.running:
                job.last_error = f"no task registered under '{task_name}'"
                _finish_terminal(s, job, JobStatus.dead)
                s.commit()
        return

    stop_heartbeat = threading.Event()
    heartbeat = threading.Thread(target=_heartbeat, args=(job_id, stop_heartbeat), name=f"hb-{job_id}", daemon=True)
    heartbeat.start()

    error: Exception | None = None
    try:
        get_task(task_name)(*args)
    except Exception as exc:  # noqa: BLE001 — any task failure feeds retry/dead-letter
        error = exc
        log.exception("job %s (%s) raised", job_id, task_name)
    finally:
        stop_heartbeat.set()
        heartbeat.join(timeout=5)

    with get_session() as s:
        job = s.get(Job, job_id)
        # if the lease expired and the reaper already requeued this job,
        # its status is no longer 'running' — don't double-handle the outcome
        if job is None or job.status != JobStatus.running:
            return
        if error is None:
            _finish_terminal(s, job, JobStatus.succeeded)
        elif job.attempts >= job.max_attempts:
            job.last_error = str(error)[:1000]
            _finish_terminal(s, job, JobStatus.dead)
        else:
            _reschedule(s, job, error)
        s.commit()


def reap_expired(session) -> int:
    """a lease that expired means the worker holding it died"""
    expired = session.execute(select(Job).where(Job.status == JobStatus.running, Job.locked_until < _now()).with_for_update(skip_locked=True)).scalars().all()
    for job in expired:
        if job.attempts >= job.max_attempts:
            job.last_error = "lease expired (worker presumed dead)"
            _finish_terminal(session, job, JobStatus.dead)
        else:
            job.status = JobStatus.ready
            job.run_after = _now()
            job.locked_by = None
            job.locked_until = None
    session.commit()
    return len(expired)


def worker_loop(stop_event: threading.Event, idx: int = 0) -> None:
    worker_id = f"{socket.gethostname()}-{os.getpid()}-{idx}"
    log.info("worker %s started", worker_id)
    while not stop_event.is_set():
        try:
            with get_session() as s:
                job_id = claim_one(s, worker_id)
            if job_id is None:
                stop_event.wait(POLL_INTERVAL + random.uniform(0, POLL_JITTER))
                continue
            execute_job(job_id, worker_id)
        except Exception:  # noqa: BLE001 — keep the loop alive through transient DB errors
            log.exception("worker %s loop error", worker_id)
            stop_event.wait(POLL_INTERVAL)
    log.info("worker %s stopped", worker_id)
