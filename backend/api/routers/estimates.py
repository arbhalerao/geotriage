import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from api.routers.builder import BUILD_PRIORITY
from api.schemas.estimate import EstimateCreate, EstimateResponse
from core.db.models.builder import StorageEstimate
from worker.queue import build_job

router = APIRouter(prefix="/estimates", tags=["estimates"])


@router.post("", response_model=EstimateResponse, status_code=status.HTTP_201_CREATED)
async def start_estimate(body: EstimateCreate, db: AsyncSession = Depends(get_db)):
    row = StorageEstimate(draft=body.as_draft())
    db.add(row)
    await db.flush()
    db.add(build_job("estimate_storage", [str(row.id)], priority=BUILD_PRIORITY, max_attempts=1))
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/{estimate_id}", response_model=EstimateResponse)
async def get_estimate(estimate_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(StorageEstimate, estimate_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimate not found")
    return row
