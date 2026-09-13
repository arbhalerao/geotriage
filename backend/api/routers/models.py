import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from geotriage import check_compatibility
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from api.schemas.catalogue import (
    CompatibilityResponse,
    ModelResponse,
    ScoreOutputResponse,
    ThresholdBandResponse,
)
from api.schemas.registry import AdmissionCheck, AdmissionResponse, ImageRegister, RegisteredResponse
from core.db.models.registry import RegisteredModel
from domain.catalogue import ModelSpec, ProviderSpec, all_models_async, all_providers_async
from worker.queue import build_job

router = APIRouter(prefix="/models", tags=["models"])


def _model_response(model: ModelSpec, providers: list[ProviderSpec]) -> ModelResponse:
    compatible_collections: dict[str, CompatibilityResponse] = {}
    for provider in providers:
        for info in provider.collections.values():
            result = check_compatibility(model, info)
            compatible_collections[info.slug] = CompatibilityResponse(
                level=result.level,
                reasons=[r.message for r in result.reasons],
            )

    return ModelResponse(
        slug=model.slug,
        name=model.name,
        description=model.description,
        primary_score=model.primary_score,
        required_bands=list(model.requires.bands),
        derived_rasters=list(model.rasters),
        max_cloud_cover=model.requires.max_cloud_cover,
        score_outputs={
            name: ScoreOutputResponse(
                description=score.get("description", ""),
                unit=score.get("unit", ""),
                value_range=tuple(score.get("range", (-1.0, 1.0))),
            )
            for name, score in model.scores.items()
        },
        compatible_collections=compatible_collections,
        default_thresholds={
            name: ThresholdBandResponse(
                green=tuple(score["thresholds"]["green"]),
                yellow=tuple(score["thresholds"]["yellow"]),
            )
            for name, score in model.scores.items()
            if score.get("thresholds")
        },
    )


def _registered_response(row: RegisteredModel) -> RegisteredResponse:
    return RegisteredResponse(
        id=str(row.id),
        slug=row.slug,
        name=row.descriptor.get("name", row.slug),
        image=row.image,
        is_enabled=row.is_enabled,
        descriptor=row.descriptor,
        registered_at=row.registered_at,
        admission=row.admission,
    )


@router.get("", response_model=list[ModelResponse])
async def list_models(db: AsyncSession = Depends(get_db)):
    providers = await all_providers_async(db)
    return [_model_response(m, providers) for m in await all_models_async(db)]


@router.get("/registered", response_model=list[RegisteredResponse])
async def list_registered(db: AsyncSession = Depends(get_db)):
    """
    every registered image, including ones still being smoke-tested or that failed

    `GET /models` answers what a workflow can select, which is a different question:
    a model that failed its smoke test belongs on this list and not on that one
    """
    rows = (await db.execute(select(RegisteredModel).order_by(RegisteredModel.registered_at.desc()))).scalars().all()
    return [_registered_response(r) for r in rows]


@router.get("/{slug}", response_model=ModelResponse)
async def get_model_by_slug(slug: str, db: AsyncSession = Depends(get_db)):
    model = next((m for m in await all_models_async(db) if m.slug == slug), None)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Model '{slug}' not found")
    return _model_response(model, await all_providers_async(db))


@router.post("", response_model=AdmissionResponse, status_code=status.HTTP_201_CREATED)
async def register_model(body: ImageRegister, db: AsyncSession = Depends(get_db)):
    """
    runs in a thread, because admission shells out to docker and takes seconds,
    and blocking the event loop on it would stall every other request

    a model is registered disabled with a smoke test queued,
    so it becomes usable only once it has proved it can score a scene rather than merely describe itself
    """
    import asyncio

    from domain.images import admit

    # structural checks only: they need no GDAL, and the API image has none
    verdict = await asyncio.to_thread(admit, body.image, "model", False)
    checks = [AdmissionCheck(name=n, passed=p, detail=d) for n, p, d in verdict.checks]

    if not verdict.ok:
        return AdmissionResponse(admitted=False, checks=checks, problems=verdict.problems)

    descriptor = verdict.descriptor
    slug = descriptor["slug"]

    existing = (await db.execute(select(RegisteredModel).where(RegisteredModel.slug == slug))).scalar_one_or_none()
    if existing:
        # re-registering the same slug is how an author ships a new version,
        # and it replaces the image only after the new one has passed the same gate
        existing.image = body.image
        existing.descriptor = descriptor
        row = existing
    else:
        row = RegisteredModel(slug=slug, image=body.image, descriptor=descriptor)
        db.add(row)

    row.admission = {"checks": [c.model_dump() for c in checks], "smoke_pending": True}
    row.is_enabled = False

    # the primary key is a python-side default, so it only exists after a flush,
    # and the queued job needs to name it
    await db.flush()
    db.add(build_job("smoke_test_model", [str(row.id)], max_attempts=1))
    checks.append(AdmissionCheck(name="smoke run", passed=False, detail="queued, runs in the worker"))

    await db.commit()
    await db.refresh(row)
    return AdmissionResponse(admitted=True, checks=checks, registered=_registered_response(row))


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_model(model_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(RegisteredModel).where(RegisteredModel.id == model_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    await db.delete(row)
    await db.commit()
