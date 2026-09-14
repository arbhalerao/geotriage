import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from geotriage import Collection
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from api.schemas.catalogue import CollectionResponse
from api.schemas.registry import AdmissionCheck, AdmissionResponse, ImageRegister, RegisteredResponse
from core.db.models.registry import RegisteredProvider
from domain.catalogue import all_providers_async, claim_collections_async

router = APIRouter(tags=["providers"])


def _collection_response(info: Collection) -> CollectionResponse:
    return CollectionResponse(
        slug=info.slug,
        display_name=info.display_name,
        processing_level=info.processing_level,
        resolution_m=info.resolution_m,
    )


def _registered_response(row: RegisteredProvider) -> RegisteredResponse:
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


@router.get("/providers/registered", response_model=list[RegisteredResponse])
async def list_registered(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(RegisteredProvider).order_by(RegisteredProvider.registered_at.desc()))).scalars().all()
    return [_registered_response(r) for r in rows]


@router.post("/providers", response_model=AdmissionResponse, status_code=status.HTTP_201_CREATED)
async def register_provider(body: ImageRegister, db: AsyncSession = Depends(get_db)):
    import asyncio

    from domain.images import admit

    verdict = await asyncio.to_thread(admit, body.image, "provider", False)
    checks = [AdmissionCheck(name=n, passed=p, detail=d) for n, p, d in verdict.checks]

    if not verdict.ok:
        return AdmissionResponse(admitted=False, checks=checks, problems=verdict.problems)

    descriptor = verdict.descriptor
    slug = descriptor["slug"]

    existing = (await db.execute(select(RegisteredProvider).where(RegisteredProvider.slug == slug))).scalar_one_or_none()
    if existing:
        existing.image = body.image
        existing.descriptor = descriptor
        row = existing
    else:
        row = RegisteredProvider(slug=slug, image=body.image, descriptor=descriptor)
        db.add(row)

    row.admission = {"checks": [c.model_dump() for c in checks]}
    row.is_enabled = True

    # the id is a python-side default, and claiming collections needs it
    await db.flush()

    declared = list(descriptor.get("collections", {}))
    conflicts = await claim_collections_async(db, row.id, slug, declared)
    if conflicts:
        await db.rollback()
        checks.append(AdmissionCheck(name="collections", passed=False, detail="; ".join(conflicts)))
        return AdmissionResponse(admitted=False, checks=checks, problems=conflicts)
    checks.append(AdmissionCheck(name="collections", passed=True, detail=", ".join(declared)))

    await db.commit()
    await db.refresh(row)
    return AdmissionResponse(admitted=True, checks=checks, registered=_registered_response(row))


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_provider(provider_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(RegisteredProvider).where(RegisteredProvider.id == provider_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    await db.delete(row)
    await db.commit()


@router.get("/collections", response_model=list[CollectionResponse])
async def list_collections(db: AsyncSession = Depends(get_db)):
    return [_collection_response(info) for provider in await all_providers_async(db) for info in provider.collections.values()]
