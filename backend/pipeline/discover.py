import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import mapping, shape
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.db.models.aoi import Aoi
from core.db.models.enums import ModelRunStatus, TimeMode, WorkflowItemStatus, WorkflowStatus
from core.db.models.results import ModelRun, WorkflowItem
from core.db.models.stac import StacItem
from core.db.models.workflow import (
    Workflow,
    WorkflowCollection,
    WorkflowModelCollectionConfig,
    WorkflowModelConfig,
)
from domain.catalogue import get_collection, get_model

log = logging.getLogger(__name__)

# a scene counts as "enclosed" by the AOI when most of it falls inside
_ENCLOSED_OVERLAP = 0.8

# hard cap on one search
# hitting it means the workflow is seeing part of the archive,
# so it is logged rather than silently truncated
MAX_SCENES = 2000

# plan: workflow_item id -> the model_run ids waiting on that item's bands
Plan = dict[uuid.UUID, list[uuid.UUID]]


def search_stac(spec, col_info, aoi_shape, time_start, time_end, max_cloud_cover, max_items=MAX_SCENES):
    """
    the cheapest stage of the funnel: cloud cover and geometry are metadata the archive already indexes,
    so pushing them into the query means those scenes never travel
    the client-side pass below stays as a safety net for archives that ignore `query`
    `max_items` below the cap is for callers that only need to know whether there are at least that many
    """
    dt_str = f"{time_start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{time_end.strftime('%Y-%m-%dT%H:%M:%SZ')}"

    # cloud cover lives under a different properties key per archive,
    # so hardcoding "eo:cloud_cover" silently disables filtering for any provider that names it differently
    cc_key = col_info.cloud_cover_property

    query = {cc_key: {"lte": max_cloud_cover}} if cc_key and max_cloud_cover is not None else None
    common = dict(
        collection_slug=col_info.slug,
        intersects=mapping(aoi_shape),
        datetime=dt_str,
        max_items=max_items,
    )

    try:
        items = spec.search(query=query, **common)
    except Exception:
        # not every archive implements the query extension
        # fall back to plain search and let the client-side filter below do the work
        log.warning("server-side filtering rejected by %s; falling back", spec.stac_api_url)
        items = spec.search(query=None, **common)

    if len(items) >= MAX_SCENES:
        log.warning(
            "search for '%s' hit the %d scene cap — results are truncated",
            col_info.slug,
            MAX_SCENES,
        )

    results = []
    for item in items:
        properties = item.get("properties", {})
        cc = properties.get(cc_key) if cc_key else None
        if max_cloud_cover is None or cc is None or float(cc) <= max_cloud_cover:
            results.append(item)
    return results


def upsert_stac_item(db: Session, collection_slug: str, stac_item: dict) -> StacItem:
    """
    two concurrent workflows covering the same area discover the same scenes,
    and read-then-insert loses that race: one hits uq_stac_items_collection_item and rolls back
    the entire discovery transaction, losing every scene found for that workflow

    ON CONFLICT DO NOTHING makes the insert a no-op for the loser, who then reads the winner's row
    the scene cache is shared by design, so either row is equally correct
    """
    item_id = stac_item["id"]
    properties = stac_item.get("properties", {})
    raw_dt = properties.get("datetime") or ""

    values = {
        "id": uuid.uuid4(),
        "collection_slug": collection_slug,
        "stac_item_id": item_id,
        "geometry": from_shape(shape(stac_item["geometry"]), srid=4326),
        "bbox": list(stac_item["bbox"]) if stac_item.get("bbox") else None,
        "datetime": datetime.fromisoformat(raw_dt.replace("Z", "+00:00")),
        "properties": dict(properties),
        "assets": dict(stac_item.get("assets", {})),
        "cloud_cover": properties.get("eo:cloud_cover"),
    }

    inserted = db.execute(pg_insert(StacItem).values(**values).on_conflict_do_nothing(constraint="uq_stac_items_collection_item").returning(StacItem.id)).scalar_one_or_none()

    if inserted is None:
        # someone else got there first — ours or a concurrent workflow's
        return db.execute(
            select(StacItem).where(
                StacItem.collection_slug == collection_slug,
                StacItem.stac_item_id == item_id,
            )
        ).scalar_one()

    return db.get(StacItem, inserted)


def cloud_ceiling(models) -> float | None:
    """the strictest cloud limit across a workflow's models, or None if none cares"""
    ceiling = None
    for model in models:
        limit = model.requires.max_cloud_cover
        if limit is not None:
            ceiling = limit if ceiling is None else min(ceiling, limit)
    return ceiling


def encloses(aoi_shape, stac_item: dict) -> bool:
    """undecidable geometry counts as a keep"""
    try:
        item_shape = shape(stac_item["geometry"])
        if item_shape.area <= 0:
            return False
        return item_shape.intersection(aoi_shape).area / item_shape.area >= _ENCLOSED_OVERLAP
    except Exception:
        return True


def discover(db: Session, workflow_id: uuid.UUID) -> Plan:
    """
    persist newly matched scenes with their model runs and return what needs processing
    the caller owns the transaction
    """
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        return {}

    aoi = db.get(Aoi, workflow.aoi_id)
    aoi_shape = to_shape(aoi.geometry)
    aoi_filter_mode = workflow.aoi_filter_mode or "intersects"

    # a recurring workflow's later runs search only from last_checked_at forward
    search_time_start = workflow.time_start
    if workflow.time_mode == TimeMode.recurring and workflow.last_checked_at:
        search_time_start = workflow.last_checked_at

    collections = db.execute(select(WorkflowCollection).where(WorkflowCollection.workflow_id == workflow_id)).scalars().all()
    model_configs = db.execute(select(WorkflowModelConfig).where(WorkflowModelConfig.workflow_id == workflow_id)).scalars().all()

    max_cc = cloud_ceiling(get_model(db, wmc.model_slug) for wmc in model_configs)
    plan: Plan = defaultdict(list)

    for wc in collections:
        spec, col_info = get_collection(db, wc.collection_slug)
        stac_items = search_stac(spec, col_info, aoi_shape, search_time_start, workflow.time_end, max_cc)
        if aoi_filter_mode == "enclosed":
            stac_items = [i for i in stac_items if encloses(aoi_shape, i)]

        for stac_item in stac_items:
            db_item = upsert_stac_item(db, wc.collection_slug, stac_item)

            already_seen = db.execute(
                select(WorkflowItem.id).where(
                    WorkflowItem.workflow_id == workflow_id,
                    WorkflowItem.stac_item_id == db_item.id,
                )
            ).scalar_one_or_none()
            if already_seen:
                continue

            item = WorkflowItem(
                workflow_id=workflow_id,
                stac_item_id=db_item.id,
                status=WorkflowItemStatus.queued,
            )
            db.add(item)
            db.flush()

            for wmc in model_configs:
                enabled = db.execute(
                    select(WorkflowModelCollectionConfig.id).where(
                        WorkflowModelCollectionConfig.workflow_model_config_id == wmc.id,
                        WorkflowModelCollectionConfig.collection_slug == wc.collection_slug,
                        WorkflowModelCollectionConfig.is_enabled.is_(True),
                    )
                ).scalar_one_or_none()
                if enabled is None:
                    continue

                run = ModelRun(
                    workflow_item_id=item.id,
                    workflow_model_config_id=wmc.id,
                    model_slug=wmc.model_slug,
                    status=ModelRunStatus.queued,
                )
                db.add(run)
                db.flush()
                plan[item.id].append(run.id)

    return dict(plan)


def mark_workflow_failed(db: Session, workflow_id: uuid.UUID, error: Exception | str) -> None:
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        return
    workflow.status = WorkflowStatus.failed
    workflow.error_message = str(error)
    workflow.completed_at = datetime.now(timezone.utc)
