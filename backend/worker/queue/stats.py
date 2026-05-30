"""
read-only queue introspection,
exposed so the API can render a status view without selecting queue tables itself
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from worker.queue.models import Job, JobStatus


async def queue_stats(session: AsyncSession) -> dict:
    """counts by status, plus the running and pending jobs themselves"""
    count_rows = (await session.execute(select(Job.status, func.count()).group_by(Job.status))).all()
    counts = {status: count for status, count in count_rows}

    active = (await session.execute(select(Job).where(Job.status == JobStatus.running).order_by(Job.started_at.desc()).limit(50))).scalars().all()

    queued = (await session.execute(select(Job).where(Job.status.in_([JobStatus.ready, JobStatus.blocked])).order_by(Job.priority.desc(), Job.run_after).limit(50))).scalars().all()

    workers = sorted({j.locked_by for j in active if j.locked_by})

    active_tasks = [
        {
            "id": str(j.id),
            "name": j.task_name,
            "args": j.args,
            "worker": j.locked_by,
            "attempts": j.attempts,
            "time_start": j.started_at,
        }
        for j in active
    ]

    queued_tasks = [
        {
            "id": str(j.id),
            "name": j.task_name,
            "args": j.args,
            "status": j.status.value,
            "run_after": j.run_after,
        }
        for j in queued
    ]

    return {
        "workers": workers,
        "active_tasks": active_tasks,
        "queued_tasks": queued_tasks,
        "total_active": counts.get(JobStatus.running, 0),
        "total_queued": counts.get(JobStatus.ready, 0) + counts.get(JobStatus.blocked, 0),
        "counts": {status.value: count for status, count in counts.items()},
    }
