import logging
import uuid
from datetime import datetime, timezone

from geoalchemy2.shape import to_shape
from geotriage import Bands, build_normalized_assets
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db.models.aoi import Aoi
from core.db.models.enums import ModelRunStatus, WorkflowItemStatus
from core.db.models.results import ModelRun, WorkflowItem
from core.db.models.stac import StacItem
from core.db.models.workflow import Workflow
from core.db.sync import get_session
from domain.catalogue import get_collection, get_model
from pipeline.stage import load_band

log = logging.getLogger(__name__)


def models_for_item(db: Session, item: WorkflowItem) -> list[tuple[uuid.UUID, object]]:
    """(model_run id, model) for every run queued against this scene"""
    runs = (
        db.execute(
            select(ModelRun).where(
                ModelRun.workflow_item_id == item.id,
                ModelRun.status == ModelRunStatus.queued,
            )
        )
        .scalars()
        .all()
    )
    return [(r.id, get_model(db, r.model_slug)) for r in runs]


def screen_item(workflow_item_id: uuid.UUID, session_factory=get_session) -> bool:
    """
    on False the item is marked `screened_out` and its model runs `skipped`,
    so staging and scoring both no-op
    """
    with session_factory() as db:
        item = db.get(WorkflowItem, workflow_item_id)
        if item is None:
            return False

        candidates = models_for_item(db, item)
        gated = [(run_id, m) for run_id, m in candidates if m.prefilter is not None]

        # nothing to screen, or at least one model wants every scene regardless
        if not gated or len(gated) < len(candidates):
            return True

        stac = db.get(StacItem, item.stac_item_id)
        workflow = db.get(Workflow, item.workflow_id)
        aoi = to_shape(db.get(Aoi, workflow.aoi_id).geometry)
        provider, collection = get_collection(db, stac.collection_slug)

        item.status = WorkflowItemStatus.screening
        db.commit()

        try:
            kept = _any_model_wants_it(gated, stac, collection, provider, aoi)
        except Exception as exc:
            # a failed gate must not silently drop a scene —
            # fall through to the expensive path and let scoring report any real problem
            log.warning("screening failed for item %s, letting it through: %s", item.id, exc)
            item.status = WorkflowItemStatus.queued
            db.commit()
            return True

        if kept:
            item.status = WorkflowItemStatus.queued
            db.commit()
            return True

        now = datetime.now(timezone.utc)
        item.status = WorkflowItemStatus.screened_out
        item.processed_at = now
        for run_id, _ in gated:
            run = db.get(ModelRun, run_id)
            run.status = ModelRunStatus.skipped
            run.completed_at = now
        db.commit()
        return False


def _any_model_wants_it(gated, stac, collection, provider, aoi) -> bool:
    """one coarse read per distinct prefilter, shared across models that agree"""
    cache: dict[tuple[str, float], Bands] = {}

    for _run_id, model in gated:
        prefilter = model.prefilter
        key = (",".join(sorted(prefilter.bands)), prefilter.gsd_m)
        if key not in cache:
            cache[key] = _coarse_bands(prefilter, stac, collection, provider, aoi)
        if model.screen(cache[key]):
            return True
    return False


def _coarse_bands(prefilter, stac, collection, provider, aoi) -> Bands:
    assets = build_normalized_assets(stac.assets, collection, prefilter.bands)
    arrays = {}
    transform = crs = None
    names = list(assets)
    signed = dict(zip(names, provider.sign([assets[n]["href"] for n in names])))
    for name, asset in assets.items():
        array, t, c = load_band(
            asset["href"],
            aoi,
            signed.get(name),
            native_gsd_m=collection.resolution_m,
            target_gsd_m=prefilter.gsd_m,
        )
        arrays[name] = collection.band(name).calibrate(array)
        if transform is None:
            transform, crs = t, c
    return Bands(arrays, collection_slug=collection.slug, transform=transform, crs=crs)
