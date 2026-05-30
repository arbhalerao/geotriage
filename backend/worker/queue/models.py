"""
ORM models for the job queue
self-contained: no foreign keys into domain tables
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Enum as SAEnum,
    ForeignKey,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base


class JobStatus(str, enum.Enum):
    blocked = "blocked"  # has unsatisfied dependencies
    ready = "ready"  # eligible to be claimed
    running = "running"  # leased by a worker
    succeeded = "succeeded"  # terminal
    failed = "failed"  # transient: will retry, or transition to dead
    dead = "dead"  # terminal: retries exhausted
    skipped = "skipped"  # terminal: a dependency failed


# terminal states that count toward a group's fan-in barrier
TERMINAL = (JobStatus.succeeded, JobStatus.dead, JobStatus.skipped)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_name: Mapped[str] = mapped_column(String, nullable=False)
    args: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, native_enum=False, length=12),
        nullable=False,
        default=JobStatus.ready,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # chain edges: ids of jobs that must finish before this one becomes ready
    depends_on: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}")
    # fan-in membership: the group whose barrier this job counts toward
    group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("job_groups.id", ondelete="CASCADE"), nullable=True)

    locked_by: Mapped[str | None] = mapped_column(String, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # hot path: the claim query scans ready jobs whose run_after has passed
        Index(
            "ix_jobs_claim",
            "priority",
            "run_after",
            postgresql_where=text("status = 'ready'"),
        ),
        # reaper: find running jobs whose lease expired
        Index(
            "ix_jobs_lease",
            "locked_until",
            postgresql_where=text("status = 'running'"),
        ),
        Index("ix_jobs_group_id", "group_id"),
        # dependents lookup: "which jobs depend on me?" → :id = ANY(depends_on)
        Index("ix_jobs_depends_on", "depends_on", postgresql_using="gin"),
    )


class JobGroup(Base):
    """a fan-in barrier: when pending_count hits zero, on_complete is enqueued once"""

    __tablename__ = "job_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pending_count: Mapped[int] = mapped_column(Integer, nullable=False)
    on_complete_task: Mapped[str | None] = mapped_column(String, nullable=True)
    on_complete_args: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    on_complete_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    on_complete_enqueued: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecurringJob(Base):
    """the scheduler enqueues task_name every interval_seconds"""

    __tablename__ = "recurring_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    args: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
