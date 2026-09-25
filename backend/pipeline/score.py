import logging
import uuid
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db.models.enums import ModelRunStatus, Severity, WorkflowItemStatus
from core.db.models.results import ModelRun, ModelScore, WorkflowItem
from core.db.models.stac import StacItem
from core.db.models.thresholds import ThresholdConfig
from core.db.models.workflow import WorkflowModelConfig
from core.db.sync import get_session
from storage import client as store
from storage import cog
from geotriage.bands import Bands
from domain.catalogue import get_model
from pipeline.cleanup import apply_storage_policy_quietly

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


def load_bands(db: Session, item: WorkflowItem, model) -> tuple[Bands, object, object]:
    """bands were calibrated at staging time, so what comes back is already in physical units"""
    arrays: dict[str, np.ndarray] = {}
    transform = crs = None
    for name in model.requires.bands:
        array, t, c = cog.get_array(store.band_key(item.workflow_id, item.id, name))
        arrays[name] = array
        if transform is None:
            transform, crs = t, c

    stac = db.get(StacItem, item.stac_item_id)
    bands = Bands(arrays, collection_slug=stac.collection_slug, transform=transform, crs=crs)
    return bands, transform, crs


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
            bands, transform, crs = load_bands(db, item, model)

            # the runner validates the output against the model's declarations,
            # so a score the model promised and didn't return raises rather than vanishing
            output = model.run(bands)
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

            # the scores are already persisted, so failing to write a derived raster must not fail the run
            try:
                for name, array in output.get("rasters", {}).items():
                    key = store.band_key(item.workflow_id, item.id, name)
                    if store.band_exists(key):
                        continue
                    cog.put(key, array, transform, crs)
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
