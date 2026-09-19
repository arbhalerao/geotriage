import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from api.schemas.builder import BuilderRunCreate, BuilderRunResponse
from core.db.models.builder import BuilderRun
from worker.queue import build_job

router = APIRouter(prefix="/builder", tags=["builder"])

# ahead of scene work, because someone is watching the screen for this one
BUILD_PRIORITY = 10


@router.post("/runs", response_model=BuilderRunResponse, status_code=status.HTTP_201_CREATED)
async def start_run(body: BuilderRunCreate, db: AsyncSession = Depends(get_db)):
    run = BuilderRun(conversation=[m.model_dump() for m in body.conversation], steps=[])
    db.add(run)
    await db.flush()
    # one attempt: a retry would repeat the whole conversation, and the run records why it failed
    db.add(build_job("build_draft", [str(run.id)], priority=BUILD_PRIORITY, max_attempts=1))
    await db.commit()
    await db.refresh(run)
    return run


@router.get("/runs/{run_id}", response_model=BuilderRunResponse)
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    run = await db.get(BuilderRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Builder run not found")
    return run
