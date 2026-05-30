import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db.models.enums import TimeMode, WorkflowItemStatus, WorkflowStatus
from core.db.models.results import WorkflowItem
from core.db.models.workflow import Workflow

FAILED_ITEM_STATUSES = {
    WorkflowItemStatus.failed,
    WorkflowItemStatus.fetch_failed,
    WorkflowItemStatus.upload_failed,
    WorkflowItemStatus.score_failed,
}

# a monitoring workflow is only re-dispatched once its previous run has settled
_RESTARTABLE = [
    WorkflowStatus.completed,
    WorkflowStatus.completed_with_errors,
    WorkflowStatus.failed,
]


def workflow_status(total: int, failed: int) -> WorkflowStatus:
    if total == 0 or failed == total:
        return WorkflowStatus.failed
    if failed > 0:
        return WorkflowStatus.completed_with_errors
    return WorkflowStatus.completed


def finalize_workflow(db: Session, workflow_id: uuid.UUID) -> None:
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        return

    statuses = db.execute(select(WorkflowItem.status).where(WorkflowItem.workflow_id == workflow_id)).scalars().all()
    total = len(statuses)
    failed = sum(1 for s in statuses if s in FAILED_ITEM_STATUSES)

    now = datetime.now(timezone.utc)
    workflow.status = workflow_status(total, failed)
    workflow.error_message = f"{failed}/{total} items failed" if failed else None
    workflow.completed_at = now
    workflow.updated_at = now
    workflow.last_checked_at = now
    db.commit()


def is_due(workflow: Workflow, now: datetime) -> bool:
    if workflow.last_checked_at is None:
        return True
    return (workflow.last_checked_at + timedelta(minutes=workflow.poll_interval_minutes)) <= now


def claim_due_workflows(db: Session, now: datetime | None = None) -> list[uuid.UUID]:
    """
    flips every due monitoring workflow to running,
    claiming and dispatching staying separate so the caller can enqueue however it likes
    """
    now = now or datetime.now(timezone.utc)

    candidates = (
        db.execute(
            select(Workflow).where(
                Workflow.time_mode == TimeMode.fixed_future,
                Workflow.poll_interval_minutes.isnot(None),
                Workflow.status.in_(_RESTARTABLE),
            )
        )
        .scalars()
        .all()
    )

    claimed = []
    for workflow in candidates:
        if not is_due(workflow, now):
            continue
        workflow.status = WorkflowStatus.running
        workflow.started_at = now
        workflow.updated_at = now
        claimed.append(workflow.id)

    if claimed:
        db.commit()
    return claimed
