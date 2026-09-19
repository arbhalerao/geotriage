import uuid

import pipeline
from builder.runs import run_build
from core.db.sync import get_session
from worker.queue import enqueue, new_group, task


@task("run_workflow")
def run_workflow(workflow_id: str) -> None:
    """
    discovery and planning share one transaction,
    so a scene that exists in the database always already has its jobs enqueued
    """
    workflow_uuid = uuid.UUID(workflow_id)
    try:
        with get_session() as db:
            plan = pipeline.discover(db, workflow_uuid)

            if plan:
                # one fan-in barrier across every score job,
                # whichever finishes last enqueues finalize_workflow exactly once
                barrier = new_group(
                    db,
                    pending_count=sum(len(runs) for runs in plan.values()),
                    on_complete_task="finalize_workflow",
                    on_complete_args=[workflow_id],
                )
                for item_id, run_ids in plan.items():
                    screen = enqueue(db, "screen_item", [str(item_id)])
                    stage = enqueue(db, "store_item_bands", [str(item_id)], depends_on=[screen.id])
                    for run_id in run_ids:
                        enqueue(
                            db,
                            "score_model_run",
                            [str(run_id)],
                            depends_on=[stage.id],
                            group_id=barrier.id,
                        )
            else:
                enqueue(db, "finalize_workflow", [workflow_id])

            db.commit()
    except Exception as exc:
        with get_session() as db:
            pipeline.mark_workflow_failed(db, workflow_uuid, exc)
            db.commit()
        raise


@task("screen_item")
def screen_item(workflow_item_id: str) -> None:
    pipeline.screen_item(uuid.UUID(workflow_item_id))


@task("store_item_bands")
def store_item_bands(workflow_item_id: str) -> None:
    pipeline.stage_bands(uuid.UUID(workflow_item_id))


@task("score_model_run")
def score_model_run(model_run_id: str) -> None:
    pipeline.score_run(uuid.UUID(model_run_id))


@task("finalize_workflow")
def finalize_workflow(workflow_id: str) -> None:
    with get_session() as db:
        pipeline.finalize_workflow(db, uuid.UUID(workflow_id))


@task("delete_workflow_artifacts")
def delete_workflow_artifacts(workflow_id: str) -> None:
    pipeline.delete_workflow_artifacts(uuid.UUID(workflow_id))


@task("smoke_test_model")
def smoke_test_model(model_id: str) -> None:
    pipeline.smoke_test_model(uuid.UUID(model_id))


@task("build_draft")
def build_draft(builder_run_id: str) -> None:
    run_build(uuid.UUID(builder_run_id))


@task("seed_defaults")
def seed_defaults() -> None:
    pipeline.seed_defaults()


@task("check_due_workflows")
def check_due_workflows() -> None:
    """
    the status flip and the enqueue share a transaction,
    so a workflow can't end up marked running with nothing queued to run it
    """
    with get_session() as db:
        for workflow_id in pipeline.claim_due_workflows(db):
            enqueue(db, "run_workflow", [str(workflow_id)], max_attempts=1)
        db.commit()
