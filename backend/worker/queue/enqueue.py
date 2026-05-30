"""
the public scheduling API: build jobs, enqueue them, open fan-in groups

`build_job` is session-agnostic, so it works for both the async API and the sync worker
`enqueue` and `new_group` are sync helpers for worker-side planning,
which needs the generated id immediately to wire up dependencies
"""

import uuid
from datetime import datetime
from typing import Sequence

from worker.queue.models import Job, JobGroup, JobStatus


def build_job(
    task_name: str,
    args: list | None = None,
    *,
    depends_on: Sequence[uuid.UUID] | None = None,
    group_id: uuid.UUID | None = None,
    priority: int = 0,
    max_attempts: int = 3,
    run_after: datetime | None = None,
) -> Job:
    """the job is unpersisted, and starts `blocked` if it has dependencies"""
    deps = list(depends_on or [])
    job = Job(
        task_name=task_name,
        args=list(args or []),
        depends_on=deps,
        group_id=group_id,
        priority=priority,
        max_attempts=max_attempts,
        status=JobStatus.blocked if deps else JobStatus.ready,
    )
    if run_after is not None:
        job.run_after = run_after
    return job


def enqueue(session, task_name: str, args: list | None = None, **kwargs) -> Job:
    """flushes so the caller can use the generated id"""
    job = build_job(task_name, args, **kwargs)
    session.add(job)
    session.flush()
    return job


def new_group(
    session,
    *,
    pending_count: int,
    on_complete_task: str | None = None,
    on_complete_args: list | None = None,
    on_complete_priority: int = 0,
) -> JobGroup:
    """when the barrier's last member finishes, on_complete is enqueued"""
    group = JobGroup(
        pending_count=pending_count,
        on_complete_task=on_complete_task,
        on_complete_args=list(on_complete_args or []),
        on_complete_priority=on_complete_priority,
    )
    session.add(group)
    session.flush()
    return group
