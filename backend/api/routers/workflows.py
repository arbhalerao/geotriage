import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import mapping, shape
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from worker.queue import build_job
from geotriage import check_compatibility
from core.db.models.aoi import Aoi
from core.db.models.enums import TimeMode, WorkflowItemStatus, WorkflowStatus
from core.db.models.results import WorkflowItem
from core.db.models.thresholds import ThresholdConfig
from core.db.models.workflow import (
    Workflow,
    WorkflowCollection,
    WorkflowModelCollectionConfig,
    WorkflowModelConfig,
)
from api.schemas.workflow import (
    CollectionConfigResponse,
    ModelConfigResponse,
    ThresholdConfigResponse,
    WorkflowCreate,
    WorkflowResponse,
    WorkflowSummary,
    WorkflowUpdate,
)
from domain.catalogue import get_collection_async, get_model_async

router = APIRouter(prefix="/workflows", tags=["workflows"])
log = logging.getLogger(__name__)


class _Bands:
    """
    the two threshold bands a descriptor declares,
    positionally addressable so the seeding code below reads the same for every model
    """

    def __init__(self, green, yellow):
        self.green = tuple(green)
        self.yellow = tuple(yellow)


def _parse_geometry(geojson: dict[str, Any]):
    geom_type = geojson.get("type", "")
    if geom_type not in ("Polygon", "MultiPolygon"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="geometry must be a GeoJSON Polygon or MultiPolygon",
        )
    try:
        shapely_geom = shape(geojson)
        if not shapely_geom.is_valid:
            raise ValueError("invalid geometry")
        return from_shape(shapely_geom, srid=4326)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid geometry: {exc}",
        )


async def _load_response(workflow: Workflow, db: AsyncSession) -> WorkflowResponse:
    aoi = (await db.execute(select(Aoi).where(Aoi.id == workflow.aoi_id))).scalar_one()
    aoi_geometry = mapping(to_shape(aoi.geometry))

    wc_rows = (await db.execute(select(WorkflowCollection).where(WorkflowCollection.workflow_id == workflow.id))).scalars().all()

    wmc_rows = (await db.execute(select(WorkflowModelConfig).where(WorkflowModelConfig.workflow_id == workflow.id))).scalars().all()

    model_configs = []
    for wmc in wmc_rows:
        cc_rows = (await db.execute(select(WorkflowModelCollectionConfig).where(WorkflowModelCollectionConfig.workflow_model_config_id == wmc.id))).scalars().all()

        tc_rows = (await db.execute(select(ThresholdConfig).where(ThresholdConfig.workflow_model_config_id == wmc.id))).scalars().all()

        model_configs.append(
            ModelConfigResponse(
                id=wmc.id,
                model_slug=wmc.model_slug,
                user_label=wmc.user_label,
                parameters=wmc.parameters,
                collection_configs=[
                    CollectionConfigResponse(
                        collection_slug=cc.collection_slug,
                        compatibility_level=cc.compatibility_level,
                        is_enabled=cc.is_enabled,
                    )
                    for cc in cc_rows
                ],
                threshold_configs=[
                    ThresholdConfigResponse(
                        score_name=tc.score_name,
                        green_min=tc.green_min,
                        green_max=tc.green_max,
                        yellow_min=tc.yellow_min,
                        yellow_max=tc.yellow_max,
                    )
                    for tc in tc_rows
                ],
            )
        )

    # one grouped scan instead of six separate COUNTs, because this endpoint is polled
    status_counts = dict((await db.execute(select(WorkflowItem.status, func.count()).where(WorkflowItem.workflow_id == workflow.id).group_by(WorkflowItem.status))).all())
    total_items = sum(status_counts.values())
    processed_items = status_counts.get(WorkflowItemStatus.processed, 0)
    screened_out_items = status_counts.get(WorkflowItemStatus.screened_out, 0)
    failed_fetch_items = status_counts.get(WorkflowItemStatus.fetch_failed, 0)
    failed_upload_items = status_counts.get(WorkflowItemStatus.upload_failed, 0)
    failed_score_items = status_counts.get(WorkflowItemStatus.score_failed, 0)

    identified_items = (
        await db.execute(
            select(func.count()).where(
                WorkflowItem.workflow_id == workflow.id,
                WorkflowItem.overall_severity.in_(["yellow", "red"]),
            )
        )
    ).scalar_one()

    next_run_at = None
    if workflow.poll_interval_minutes and workflow.last_checked_at:
        next_run_at = workflow.last_checked_at + timedelta(minutes=workflow.poll_interval_minutes)

    return WorkflowResponse(
        id=workflow.id,
        aoi_id=workflow.aoi_id,
        aoi_geometry=aoi_geometry,
        name=workflow.name,
        description=workflow.description,
        time_mode=workflow.time_mode,
        time_start=workflow.time_start,
        time_end=workflow.time_end,
        aoi_filter_mode=workflow.aoi_filter_mode,
        poll_interval_minutes=workflow.poll_interval_minutes,
        last_checked_at=workflow.last_checked_at,
        next_run_at=next_run_at,
        status=workflow.status,
        started_at=workflow.started_at,
        completed_at=workflow.completed_at,
        error_message=workflow.error_message,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
        collection_slugs=[wc.collection_slug for wc in wc_rows],
        model_configs=model_configs,
        total_items=total_items,
        processed_items=processed_items,
        identified_items=identified_items,
        failed_fetch_items=failed_fetch_items,
        failed_upload_items=failed_upload_items,
        failed_score_items=failed_score_items,
        screened_out_items=screened_out_items,
    )


async def _get_workflow(workflow_id: uuid.UUID, db: AsyncSession) -> Workflow:
    workflow = (await db.execute(select(Workflow).where(Workflow.id == workflow_id))).scalar_one_or_none()
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return workflow


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    body: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
):
    if body.time_end <= body.time_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="time_end must be after time_start",
        )

    aoi = Aoi(
        name=body.name,
        geometry=_parse_geometry(body.geometry),
    )
    db.add(aoi)
    await db.flush()

    mc_input = body.models[0]
    try:
        model = await get_model_async(db, mc_input.model_slug)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown model '{mc_input.model_slug}'",
        )

    collection_infos = {}
    for slug in body.collection_slugs:
        try:
            _, info = await get_collection_async(db, slug)
            collection_infos[slug] = info
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown collection '{slug}'",
            )
        level = check_compatibility(model, info).level
        if level == "incompatible":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Collection '{slug}' is not compatible with model '{mc_input.model_slug}'",
            )

    workflow = Workflow(
        aoi_id=aoi.id,
        aoi_filter_mode=body.aoi_filter_mode,
        poll_interval_minutes=body.poll_interval_minutes,
        name=body.name,
        description=body.description,
        time_mode=body.time_mode,
        time_start=body.time_start,
        time_end=body.time_end,
        status=WorkflowStatus.draft,
    )
    db.add(workflow)
    await db.flush()

    for slug in body.collection_slugs:
        db.add(WorkflowCollection(workflow_id=workflow.id, collection_slug=slug))

    wmc = WorkflowModelConfig(
        workflow_id=workflow.id,
        model_slug=mc_input.model_slug,
        user_label=mc_input.user_label,
        parameters=mc_input.parameters,
    )
    db.add(wmc)
    await db.flush()

    for col_slug in body.collection_slugs:
        col_info = collection_infos[col_slug]
        level = check_compatibility(model, col_info).level
        db.add(
            WorkflowModelCollectionConfig(
                workflow_id=workflow.id,
                workflow_model_config_id=wmc.id,
                collection_slug=col_slug,
                compatibility_level=level,
                is_enabled=True,
            )
        )

    user_thresholds = mc_input.thresholds or {}
    for score_name, score in model.scores.items():
        thresholds = score.get("thresholds")
        if not thresholds:
            continue
        defaults = _Bands(green=thresholds["green"], yellow=thresholds["yellow"])
        ov = user_thresholds.get(score_name)
        db.add(
            ThresholdConfig(
                workflow_model_config_id=wmc.id,
                score_name=score_name,
                green_min=ov.green_min if ov else defaults.green[0],
                green_max=ov.green_max if ov else defaults.green[1],
                yellow_min=ov.yellow_min if ov else defaults.yellow[0],
                yellow_max=ov.yellow_max if ov else defaults.yellow[1],
            )
        )

    await db.commit()
    await db.refresh(workflow)
    return await _load_response(workflow, db)


# the pipeline has the canonical set, but importing it would pull the raster stack into the API image
_FAILED_ITEM_STATUSES = [
    WorkflowItemStatus.failed,
    WorkflowItemStatus.fetch_failed,
    WorkflowItemStatus.upload_failed,
    WorkflowItemStatus.score_failed,
]


@router.get("", response_model=list[WorkflowSummary])
async def list_workflows(db: AsyncSession = Depends(get_db)):
    """
    each extra detail is one grouped query across every workflow, so the list costs the same three queries
    however many workflows there are
    """
    rows = (await db.execute(select(Workflow).order_by(Workflow.created_at.desc()))).scalars().all()

    counts: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: {"total": 0, "processed": 0, "failed": 0})
    for workflow_id, item_status, n in (await db.execute(select(WorkflowItem.workflow_id, WorkflowItem.status, func.count()).group_by(WorkflowItem.workflow_id, WorkflowItem.status))).all():
        counts[workflow_id]["total"] += n
        if item_status == WorkflowItemStatus.processed:
            counts[workflow_id]["processed"] += n
        elif item_status in _FAILED_ITEM_STATUSES:
            counts[workflow_id]["failed"] += n

    identified = dict((await db.execute(select(WorkflowItem.workflow_id, func.count()).where(WorkflowItem.overall_severity.in_(["yellow", "red"])).group_by(WorkflowItem.workflow_id))).all())

    return [
        WorkflowSummary(
            id=w.id,
            name=w.name,
            description=w.description,
            time_mode=w.time_mode,
            time_start=w.time_start,
            time_end=w.time_end,
            status=w.status,
            created_at=w.created_at,
            updated_at=w.updated_at,
            total_items=counts[w.id]["total"],
            processed_items=counts[w.id]["processed"],
            identified_items=identified.get(w.id, 0),
            failed_items=counts[w.id]["failed"],
        )
        for w in rows
    ]


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    workflow = await _get_workflow(workflow_id, db)
    return await _load_response(workflow, db)


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: uuid.UUID,
    body: WorkflowUpdate,
    db: AsyncSession = Depends(get_db),
):
    workflow = await _get_workflow(workflow_id, db)
    if workflow.status != WorkflowStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft workflows can be updated",
        )
    if body.name is not None:
        workflow.name = body.name
    if body.description is not None:
        workflow.description = body.description
    workflow.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(workflow)
    return await _load_response(workflow, db)


@router.post("/{workflow_id}/run", response_model=WorkflowResponse)
async def run_workflow(workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    workflow = await _get_workflow(workflow_id, db)
    if workflow.status not in (WorkflowStatus.draft, WorkflowStatus.failed):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot run a workflow with status '{workflow.status.value}'",
        )

    workflow.status = WorkflowStatus.running
    workflow.started_at = datetime.now(timezone.utc)
    workflow.updated_at = datetime.now(timezone.utc)
    # enqueue in the same transaction as the status flip, otherwise a failed dispatch
    # strands the workflow in 'running' with nothing queued and no way to retry it
    # build_job rather than importing the task, because worker.tasks pulls in pipeline -> storage.cog -> rasterio
    # and the API image deliberately has no GDAL
    db.add(build_job("run_workflow", [str(workflow_id)], max_attempts=1))
    await db.commit()
    await db.refresh(workflow)

    return await _load_response(workflow, db)


@router.post("/{workflow_id}/fetch-now", response_model=WorkflowResponse)
async def fetch_now(workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    workflow = await _get_workflow(workflow_id, db)
    if workflow.time_mode != TimeMode.recurring or not workflow.poll_interval_minutes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="fetch-now is only available for recurring workflows",
        )
    if workflow.status == WorkflowStatus.running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow is already running",
        )
    workflow.status = WorkflowStatus.running
    workflow.started_at = datetime.now(timezone.utc)
    workflow.updated_at = datetime.now(timezone.utc)
    # enqueue in the same transaction as the status flip, otherwise a failed dispatch
    # strands the workflow in 'running' with nothing queued and no way to retry it
    # build_job rather than importing the task, because worker.tasks pulls in pipeline -> storage.cog -> rasterio
    # and the API image deliberately has no GDAL
    db.add(build_job("run_workflow", [str(workflow_id)], max_attempts=1))
    await db.commit()
    await db.refresh(workflow)

    return await _load_response(workflow, db)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    workflow = await _get_workflow(workflow_id, db)
    if workflow.status == WorkflowStatus.running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a running workflow",
        )

    aoi_id = workflow.aoi_id
    await db.delete(workflow)

    # an AOI belongs to the workflow that created it and nothing else references one,
    # so flush first to clear the child's foreign key before its parent goes
    await db.flush()
    aoi = (await db.execute(select(Aoi).where(Aoi.id == aoi_id))).scalar_one_or_none()
    if aoi is not None:
        await db.delete(aoi)

    # queue the object-storage cleanup in the same transaction as the delete,
    # so it can't be lost and retries if MinIO is briefly unreachable
    db.add(build_job("delete_workflow_artifacts", [str(workflow_id)]))
    await db.commit()
