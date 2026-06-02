from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from worker.queue.stats import queue_stats

router = APIRouter(prefix="/worker", tags=["worker"])


@router.get("/status")
async def worker_status(db: AsyncSession = Depends(get_db)):
    """
    the queue is a table,
    so this is a query rather than an RPC broadcast that times out when no worker answers
    """
    return await queue_stats(db)
