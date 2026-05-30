"""
periodic work: dispatch recurring jobs and run the reaper

runs on every worker process but only one is ever active at a time,
workers contending for a Postgres advisory lock
if the leader dies its connection drops, the lock releases, and another worker takes over
"""

import logging
import os
import threading
from datetime import timedelta

from sqlalchemy import select, text

from core.db.sync import engine, get_session
from worker.queue.enqueue import build_job
from worker.queue.models import Job, JobStatus, RecurringJob
from worker.queue.worker import _now, reap_expired

log = logging.getLogger(__name__)

# arbitrary but fixed key so all workers contend for the same lock
LEADER_LOCK_KEY = int(os.getenv("SCHEDULER_LOCK_KEY", "918273645"))
TICK_SECONDS = float(os.getenv("SCHEDULER_TICK_SECONDS", "5.0"))
LEADER_RETRY_SECONDS = float(os.getenv("SCHEDULER_LEADER_RETRY_SECONDS", "10.0"))

# a recurring task isn't re-enqueued while a copy is still outstanding
_PENDING = (JobStatus.blocked, JobStatus.ready, JobStatus.running)


def dispatch_due_recurring(session) -> int:
    due = session.execute(select(RecurringJob).where(RecurringJob.enabled.is_(True), RecurringJob.next_run_at <= _now()).with_for_update(skip_locked=True)).scalars().all()
    dispatched = 0
    for r in due:
        already = session.execute(select(Job.id).where(Job.task_name == r.task_name, Job.status.in_(_PENDING)).limit(1)).first()
        if already is None:
            session.add(build_job(r.task_name, r.args, priority=r.priority))
            dispatched += 1
        r.next_run_at = _now() + timedelta(seconds=r.interval_seconds)
    session.commit()
    return dispatched


def _tick() -> None:
    with get_session() as s:
        dispatch_due_recurring(s)
    with get_session() as s:
        reap_expired(s)


def scheduler_loop(stop_event: threading.Event) -> None:
    """while leader, tick until asked to stop or the lock is lost"""
    while not stop_event.is_set():
        conn = engine.connect()
        try:
            got = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LEADER_LOCK_KEY}).scalar()
            if not got:
                conn.close()
                stop_event.wait(LEADER_RETRY_SECONDS)
                continue

            log.info("scheduler: acquired leadership")
            try:
                while not stop_event.is_set():
                    try:
                        _tick()
                    except Exception:  # noqa: BLE001 — never let the leader thread die silently
                        log.exception("scheduler tick failed")
                    stop_event.wait(TICK_SECONDS)
            finally:
                try:
                    conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LEADER_LOCK_KEY})
                except Exception:  # noqa: BLE001
                    pass
        finally:
            conn.close()
