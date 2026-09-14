import asyncio
import math
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from storage import client as store
from core.db.models.results import ModelRun, ModelScore, WorkflowItem
from core.db.models.stac import StacItem
from core.db.models.workflow import Workflow
from api.schemas.results import (
    ModelRunResponse,
    ModelScoreResponse,
    StacItemResponse,
    TimeseriesPoint,
    TimeseriesResponse,
    WorkflowItemDetail,
    WorkflowItemPage,
    WorkflowItemSummary,
)

router = APIRouter(tags=["results"])


async def _get_workflow(workflow_id: uuid.UUID, db: AsyncSession) -> Workflow:
    wf = (await db.execute(select(Workflow).where(Workflow.id == workflow_id))).scalar_one_or_none()
    if wf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return wf


async def _load_model_runs(wi_id: uuid.UUID, db: AsyncSession) -> list[ModelRunResponse]:
    runs = (await db.execute(select(ModelRun).where(ModelRun.workflow_item_id == wi_id))).scalars().all()

    result = []
    for mr in runs:
        scores = (await db.execute(select(ModelScore).where(ModelScore.model_run_id == mr.id))).scalars().all()
        result.append(
            ModelRunResponse(
                id=mr.id,
                model_slug=mr.model_slug,
                status=mr.status,
                started_at=mr.started_at,
                completed_at=mr.completed_at,
                error_message=mr.error_message,
                scores=[
                    ModelScoreResponse(
                        score_name=s.score_name,
                        score_value=s.score_value,
                        is_primary=s.is_primary,
                        severity=s.severity,
                    )
                    for s in scores
                ],
            )
        )
    return result


@router.get("/workflows/{workflow_id}/items", response_model=WorkflowItemPage)
async def list_items(
    workflow_id: uuid.UUID,
    severity: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    await _get_workflow(workflow_id, db)

    base = select(WorkflowItem, StacItem).join(StacItem, StacItem.id == WorkflowItem.stac_item_id).where(WorkflowItem.workflow_id == workflow_id)
    if severity:
        base = base.where(WorkflowItem.overall_severity == severity)

    total: int = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    rows = (await db.execute(base.order_by(WorkflowItem.discovered_at.desc()).offset((page - 1) * page_size).limit(page_size))).all()

    return WorkflowItemPage(
        items=[
            WorkflowItemSummary(
                id=wi.id,
                collection_slug=si.collection_slug,
                stac_item_id=si.stac_item_id,
                scene_datetime=si.datetime,
                status=wi.status,
                overall_severity=wi.overall_severity,
                discovered_at=wi.discovered_at,
                processed_at=wi.processed_at,
                bbox=si.bbox,
            )
            for wi, si in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, math.ceil(total / page_size)),
    )


@router.get("/workflows/{workflow_id}/timeseries", response_model=TimeseriesResponse)
async def get_timeseries(workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_workflow(workflow_id, db)

    rows = (
        await db.execute(
            select(
                WorkflowItem.id,
                StacItem.stac_item_id,
                StacItem.datetime,
                ModelScore.score_name,
                ModelScore.score_value,
                ModelScore.severity,
            )
            .join(StacItem, StacItem.id == WorkflowItem.stac_item_id)
            .join(ModelRun, ModelRun.workflow_item_id == WorkflowItem.id)
            .join(ModelScore, ModelScore.model_run_id == ModelRun.id)
            .where(
                WorkflowItem.workflow_id == workflow_id,
                WorkflowItem.status == "processed",
            )
            .order_by(StacItem.datetime)
        )
    ).all()

    score_names: set[str] = set()
    points: list[TimeseriesPoint] = []
    for item_id, stac_item_id, dt, score_name, score_value, severity in rows:
        score_names.add(score_name)
        points.append(
            TimeseriesPoint(
                item_id=item_id,
                stac_item_id=stac_item_id,
                scene_datetime=dt,
                score_name=score_name,
                score_value=score_value,
                severity=severity,
            )
        )

    return TimeseriesResponse(available_scores=sorted(score_names), points=points)


@router.get("/workflows/{workflow_id}/items/{item_id}", response_model=WorkflowItemDetail)
async def get_item(
    workflow_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await _get_workflow(workflow_id, db)

    row = (
        await db.execute(select(WorkflowItem, StacItem).join(StacItem, StacItem.id == WorkflowItem.stac_item_id).where(WorkflowItem.id == item_id, WorkflowItem.workflow_id == workflow_id))
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    wi, si = row
    return WorkflowItemDetail(
        id=wi.id,
        collection_slug=si.collection_slug,
        stac_item_id=si.stac_item_id,
        scene_datetime=si.datetime,
        status=wi.status,
        overall_severity=wi.overall_severity,
        discovered_at=wi.discovered_at,
        processed_at=wi.processed_at,
        stac_item=StacItemResponse(
            id=si.stac_item_id,
            collection=si.collection_slug,
            datetime=si.datetime,
            bbox=si.bbox,
            properties=si.properties,
            assets={k: {kk: vv for kk, vv in v.items() if kk != "href"} for k, v in si.assets.items()},
        ),
        model_runs=await _load_model_runs(wi.id, db),
    )


_ASSET_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@router.get("/workflows/{workflow_id}/items/{item_id}/assets/{name}")
async def download_asset(
    workflow_id: uuid.UUID,
    item_id: uuid.UUID,
    name: str,
    db: AsyncSession = Depends(get_db),
):
    """stream a stored COG (raw band or derived raster) out of MinIO"""
    if not _ASSET_NAME_RE.match(name):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invalid asset name",
        )

    wi = (
        await db.execute(
            select(WorkflowItem).where(
                WorkflowItem.id == item_id,
                WorkflowItem.workflow_id == workflow_id,
            )
        )
    ).scalar_one_or_none()
    if wi is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    key = store.band_key(workflow_id, item_id, name)
    data = await asyncio.to_thread(store.get_bytes, key)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    return Response(
        content=data,
        media_type="image/tiff",
        headers={"Content-Disposition": f'attachment; filename="{name}.tif"'},
    )
