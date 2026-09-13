from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import live
from api.routers import live as live_router
from api.routers import models, providers, results, workflows
from api.routers import worker as worker_router
from core.db.session import AsyncSessionLocal
from worker.queue import build_job


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # queue the default models and providers rather than registering them here:
    # admission runs containers, which needs the raster stack and docker access the worker has
    # the task is idempotent, so booting again is a no-op
    async with AsyncSessionLocal() as db:
        db.add(build_job("seed_defaults", [], max_attempts=1))
        await db.commit()
    async with live.running(live.hub):
        yield


app = FastAPI(title="Geotriage", lifespan=lifespan)

app.include_router(models.router)
app.include_router(providers.router)
app.include_router(workflows.router)
app.include_router(results.router)
app.include_router(worker_router.router)
app.include_router(live_router.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
