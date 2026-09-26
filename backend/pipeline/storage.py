import uuid

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db.models.aoi import Aoi
from core.db.models.results import WorkflowItem
from core.db.models.stac import StacItem
from core.db.models.workflow import Workflow, WorkflowModelCollectionConfig, WorkflowModelConfig
from domain.catalogue import get_collection, get_model
from domain.storage import clipped_area_km2, format_bytes, free_bytes, staged_bytes, staging_resolution, verdict


class StorageLimitExceeded(Exception):
    pass


def bytes_for_scenes(
    overlaps_by_collection: dict[str, list[float]], resolution_by_collection: dict[str, float], models_by_collection: dict[str, list]
) -> tuple[int, int]:
    bands_total = maps_total = 0
    for slug, overlaps in overlaps_by_collection.items():
        models = models_by_collection.get(slug, [])
        if not models:
            continue
        bands = {band for model in models for band in model.requires.bands}
        maps = sum(len(model.rasters) for model in models)
        resolution = staging_resolution(resolution_by_collection[slug], [model.requires.gsd_m for model in models])
        bands_total += sum(staged_bytes(1, km2, resolution, len(bands)) for km2 in overlaps)
        maps_total += sum(staged_bytes(1, km2, resolution, maps) for km2 in overlaps)
    return bands_total, maps_total


def kept_at_most(policy: str, bands: int, maps: int) -> int:
    if policy == "scores_only":
        return 0
    if policy == "results_only":
        return maps
    return bands + maps


def planned_bytes(db: Session, workflow_id: uuid.UUID, item_ids: list[uuid.UUID]) -> tuple[int, int, int]:
    workflow = db.get(Workflow, workflow_id)
    area = to_shape(db.get(Aoi, workflow.aoi_id).geometry)
    rows = db.execute(select(StacItem.collection_slug, StacItem.geometry).join(WorkflowItem, WorkflowItem.stac_item_id == StacItem.id).where(WorkflowItem.id.in_(item_ids))).all()
    overlaps_by_collection: dict[str, list[float]] = {}
    for slug, footprint in rows:
        overlaps_by_collection.setdefault(slug, []).append(clipped_area_km2(mapping(to_shape(footprint)), area))

    enabled = db.execute(
        select(WorkflowModelCollectionConfig.collection_slug, WorkflowModelConfig.model_slug)
        .join(WorkflowModelConfig, WorkflowModelConfig.id == WorkflowModelCollectionConfig.workflow_model_config_id)
        .where(WorkflowModelCollectionConfig.workflow_id == workflow_id, WorkflowModelCollectionConfig.is_enabled.is_(True))
    ).all()
    models: dict[str, object] = {}
    models_by_collection: dict[str, list] = {}
    for collection_slug, model_slug in enabled:
        if model_slug not in models:
            models[model_slug] = get_model(db, model_slug)
        models_by_collection.setdefault(collection_slug, []).append(models[model_slug])

    resolution_by_collection = {slug: get_collection(db, slug)[1].resolution_m for slug in overlaps_by_collection}
    return len(rows), *bytes_for_scenes(overlaps_by_collection, resolution_by_collection, models_by_collection)


def check_storage(
    db: Session, workflow_id: uuid.UUID, item_ids: list[uuid.UUID], free: int | None = None, stored_free: int | None = None, policy: str | None = None
) -> None:
    if not item_ids:
        return
    scenes, bands, maps = planned_bytes(db, workflow_id, item_ids)
    working = bands + maps
    free = free_bytes() if free is None else free
    if verdict(working, free) == "too_large":
        raise StorageLimitExceeded(
            f"This run needs about {format_bytes(working)} of working space for {scenes} scenes, more than half of the {format_bytes(free)} free. "
            "Nothing was downloaded. Narrow the area or the dates, or free up space, then run it again."
        )

    if policy is None:
        policy = db.get(Workflow, workflow_id).storage_policy.value
    kept = kept_at_most(policy, bands, maps)
    if stored_free is None:
        from storage import client as store

        stored_free = store.free_bytes()
    if kept and stored_free is not None and verdict(kept, stored_free) == "too_large":
        raise StorageLimitExceeded(
            f"This run could keep up to {format_bytes(kept)} from {scenes} scenes, more than half of the {format_bytes(stored_free)} free in storage. "
            "Nothing was downloaded. Narrow the area or the dates, or free up space, then run it again."
        )
