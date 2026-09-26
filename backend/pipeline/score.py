import logging
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db.models.enums import ModelRunStatus, Severity, WorkflowItemStatus
from core.db.models.results import ModelRun, ModelScore, WorkflowItem
from core.db.models.stac import StacItem
from core.db.models.thresholds import ThresholdConfig
from core.db.models.workflow import WorkflowModelConfig
from core.db.sync import get_session
from storage import cog
from domain.catalogue import get_model
from pipeline import scratch
from pipeline.cleanup import apply_storage_policy_quietly
from pipeline.stage import stage_bands

log = logging.getLogger(__name__)

_SEVERITY_ORDER = {"green": 0, "yellow": 1, "red": 2}

_ITEM_FAILED = (
    WorkflowItemStatus.fetch_failed,
    WorkflowItemStatus.upload_failed,
    WorkflowItemStatus.failed,
)

# not a failure — the cheap gate decided this scene wasn't worth the work
_ITEM_SKIPPED = (WorkflowItemStatus.screened_out,)


def apply_threshold(value: float, config: ThresholdConfig) -> str:
    if config.green_min <= value <= config.green_max:
        return Severity.green
    if config.yellow_min <= value <= config.yellow_max:
        return Severity.yellow
    return Severity.red


def severity_rank(severity: str | None) -> int:
    return _SEVERITY_ORDER.get(severity or "", -1)


def worst_severity(severities) -> str | None:
    worst = None
    for severity in severities:
        if severity_rank(severity) > severity_rank(worst):
            worst = severity
    return worst


def staged_grid(item: WorkflowItem, model, session_factory) -> tuple[object, object]:
    if any(not os.path.exists(scratch.band_path(item.id, name)) for name in model.requires.bands):
        stage_bands(item.id, session_factory=session_factory)
    return cog.read_grid(scratch.band_path(item.id, model.requires.bands[0]))


def score_run(model_run_id: uuid.UUID, session_factory=get_session) -> uuid.UUID:
    with session_factory() as db:
        run = db.get(ModelRun, model_run_id)
        if run is None:
            return model_run_id

        item = db.get(WorkflowItem, run.workflow_item_id)

        # staging gave up, or the gate rejected it, either way nothing to score
        if item.status in _ITEM_FAILED + _ITEM_SKIPPED:
            run.status = ModelRunStatus.skipped
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
            return model_run_id

        run.status = ModelRunStatus.running
        run.started_at = datetime.now(timezone.utc)
        # idempotent across the parallel runs scoring this same item
        if item.status != WorkflowItemStatus.scoring:
            item.status = WorkflowItemStatus.scoring
        db.commit()

        try:
            wmc = db.get(WorkflowModelConfig, run.workflow_model_config_id)
            thresholds = {tc.score_name: tc for tc in db.execute(select(ThresholdConfig).where(ThresholdConfig.workflow_model_config_id == wmc.id)).scalars().all()}

            model = get_model(db, wmc.model_slug)
            transform, crs = staged_grid(item, model, session_factory)
            stac = db.get(StacItem, item.stac_item_id)

            output = model.run_scene(scratch.scene_dir(item.id), list(model.requires.bands), stac.collection_slug, str(run.id))
            scores = output["scores"]
            metadata = output.get("metadata", {})

            for name, value in scores.items():
                if value is None:
                    continue
                config = thresholds.get(name)
                severity = apply_threshold(float(value), config) if config else Severity.green
                db.add(
                    ModelScore(
                        model_run_id=run.id,
                        score_name=name,
                        score_value=float(value),
                        is_primary=(name == model.primary_score),
                        severity=severity,
                    )
                )

            run.status = ModelRunStatus.success
            run.raw_output = {**scores, **metadata}
            run.completed_at = datetime.now(timezone.utc)
            db.commit()

            try:
                scratch.ensure_dirs(item.id)
                for name, array in output.get("rasters", {}).items():
                    path = scratch.map_path(item.id, name)
                    cog.write_to_disk(f"{path}.part", array, transform, crs)
                    os.replace(f"{path}.part", path)
            except Exception as exc:
                log.warning("derived raster write failed for model_run %s: %s", run.id, exc)

        except Exception as exc:
            item = db.get(WorkflowItem, run.workflow_item_id)
            if item.status not in (
                WorkflowItemStatus.fetch_failed,
                WorkflowItemStatus.upload_failed,
            ):
                item.status = WorkflowItemStatus.score_failed
            run.status = ModelRunStatus.failed
            run.error_message = str(exc)[:500]
            run.completed_at = datetime.now(timezone.utc)
            db.commit()

        finalize_item(db, run.workflow_item_id)

    return model_run_id


def finalize_item(db: Session, item_id: uuid.UUID) -> None:
    """no-op until every model run against the scene has finished"""
    runs = db.execute(select(ModelRun).where(ModelRun.workflow_item_id == item_id)).scalars().all()

    if any(r.status in (ModelRunStatus.queued, ModelRunStatus.running) for r in runs):
        return

    item = db.get(WorkflowItem, item_id)
    now = datetime.now(timezone.utc)
    already_failed = item.status in (*_ITEM_FAILED, WorkflowItemStatus.score_failed)

    succeeded = [r for r in runs if r.status == ModelRunStatus.success]
    if not succeeded:
        if not already_failed:
            item.status = WorkflowItemStatus.failed
        item.processed_at = now
        db.commit()
        apply_storage_policy_quietly(db, item)
        return

    primaries = (
        db.execute(
            select(ModelScore.severity).where(
                ModelScore.model_run_id.in_([r.id for r in succeeded]),
                ModelScore.is_primary.is_(True),
            )
        )
        .scalars()
        .all()
    )

    item.overall_severity = worst_severity(primaries)
    item.status = WorkflowItemStatus.processed
    item.processed_at = now
    db.commit()
    apply_storage_policy_quietly(db, item)
