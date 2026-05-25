from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from geotriage import Collection, Prefilter, Requires
from geotriage.descriptor import collection_from_descriptor
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.db.models.registry import ProviderCollection, RegisteredModel, RegisteredProvider
from runners.docker import DockerRunner


@dataclass
class ModelSpec:
    """mirrors the attribute surface of a live `Model`, so planning code reads the same"""

    slug: str
    name: str
    description: str
    requires: Requires
    scores: dict[str, dict]
    rasters: list[str]
    prefilter: Prefilter | None
    runner: DockerRunner

    @property
    def primary_score(self) -> str:
        for name, score in self.scores.items():
            if score.get("primary"):
                return name
        raise ValueError(f"model '{self.slug}' declares no primary score")

    def run(self, bands):
        return self.runner.run(bands)

    def screen(self, bands) -> bool:
        return self.runner.screen(bands)


@dataclass
class ProviderSpec:
    slug: str
    name: str
    stac_api_url: str
    collections: dict[str, Collection]
    runner: DockerRunner

    def search(
        self,
        collection_slug: str,
        intersects: dict | None = None,
        datetime: str | None = None,
        query: dict | None = None,
        max_items: int = 500,
    ) -> list[dict]:
        """plain dicts rather than pystac objects, because an image can only hand back JSON"""
        return self.runner.search(
            {
                "collection_slug": collection_slug,
                "intersects": intersects,
                "datetime": datetime,
                "query": query,
                "max_items": max_items,
            }
        )

    def sign(self, hrefs: list[str]) -> list[str]:
        """batched, because a container round-trip per href would cost more than the download it enables"""
        if not hrefs:
            return []
        return self.runner.sign(hrefs)


def model_from_row(row: RegisteredModel) -> ModelSpec:
    descriptor = row.descriptor
    requires = descriptor["requires"]
    prefilter = descriptor.get("prefilter")
    return ModelSpec(
        slug=descriptor["slug"],
        name=descriptor.get("name", descriptor["slug"]),
        description=descriptor.get("description", ""),
        requires=Requires(
            bands=list(requires["bands"]),
            max_cloud_cover=requires.get("max_cloud_cover"),
            gsd_m=requires.get("gsd_m"),
            cost=requires.get("cost", "medium"),
        ),
        scores=descriptor["scores"],
        rasters=list(descriptor.get("rasters", [])),
        prefilter=(None if not prefilter else Prefilter(bands=list(prefilter["bands"]), gsd_m=float(prefilter["gsd_m"]))),
        runner=DockerRunner(row.image),
    )


def provider_from_row(row: RegisteredProvider) -> ProviderSpec:
    descriptor = row.descriptor
    return ProviderSpec(
        slug=descriptor["slug"],
        name=descriptor.get("name", descriptor["slug"]),
        stac_api_url=descriptor.get("stac_api_url", ""),
        collections={slug: collection_from_descriptor(c) for slug, c in descriptor.get("collections", {}).items()},
        runner=DockerRunner(row.image),
    )


def _enabled(table):
    return select(table).where(table.is_enabled.is_(True)).order_by(table.slug)


def all_models(db: Session) -> list[ModelSpec]:
    return [model_from_row(r) for r in db.execute(_enabled(RegisteredModel)).scalars().all()]


def get_model(db: Session, slug: str) -> ModelSpec:
    row = db.execute(_enabled(RegisteredModel).where(RegisteredModel.slug == slug)).scalar_one_or_none()
    if row is None:
        known = ", ".join(m.slug for m in all_models(db)) or "(none registered)"
        raise KeyError(f"No model available with slug '{slug}'. Available: {known}")
    return model_from_row(row)


def all_providers(db: Session) -> list[ProviderSpec]:
    return [provider_from_row(r) for r in db.execute(_enabled(RegisteredProvider)).scalars().all()]


def _owner_query(collection_slug: str):
    return (
        select(RegisteredProvider)
        .join(ProviderCollection, ProviderCollection.provider_id == RegisteredProvider.id)
        .where(ProviderCollection.collection_slug == collection_slug, RegisteredProvider.is_enabled.is_(True))
    )


def get_collection(db: Session, collection_slug: str) -> tuple[ProviderSpec, Collection]:
    row = db.execute(_owner_query(collection_slug)).scalar_one_or_none()
    if row is None:
        known = ", ".join(sorted(c for p in all_providers(db) for c in p.collections)) or "(no providers registered)"
        raise KeyError(f"No provider has collection '{collection_slug}'. Available collections: {known}")
    spec = provider_from_row(row)
    return spec, spec.collections[collection_slug]


def collection_conflicts(declared: list[str], owned: dict[str, str], provider_slug: str) -> list[str]:
    """
    the declared slugs that another provider already owns

    a provider re-registering keeps its own slugs, which is how an author ships a version
    that adds or drops a collection
    """
    return [f"collection '{slug}' is already provided by '{owner}'" for slug in sorted(declared) if (owner := owned.get(slug)) and owner != provider_slug]


def _owned_by_others(rows) -> dict[str, str]:
    return {collection_slug: provider_slug for collection_slug, provider_slug in rows}


def claim_collections(db: Session, provider_id, provider_slug: str, declared: list[str]) -> list[str]:
    """
    take ownership of the declared slugs, or report who already holds them

    the caller's transaction is left untouched when there is a conflict, so a rejected
    registration changes nothing
    """
    owned = _owned_by_others(db.execute(select(ProviderCollection.collection_slug, RegisteredProvider.slug).join(RegisteredProvider, ProviderCollection.provider_id == RegisteredProvider.id)).all())
    problems = collection_conflicts(declared, owned, provider_slug)
    if problems:
        return problems

    db.execute(delete(ProviderCollection).where(ProviderCollection.provider_id == provider_id))
    for slug in declared:
        db.add(ProviderCollection(collection_slug=slug, provider_id=provider_id))
    return []


# the API talks to Postgres through asyncpg while the pipeline uses psycopg2
# the shape is the same, only the fetch differs


async def _rows_async(db, table) -> list[Any]:
    result = await db.execute(_enabled(table))
    return result.scalars().all()


async def all_models_async(db) -> list[ModelSpec]:
    return [model_from_row(r) for r in await _rows_async(db, RegisteredModel)]


async def get_model_async(db, slug: str) -> ModelSpec:
    for spec in await all_models_async(db):
        if spec.slug == slug:
            return spec
    raise KeyError(f"No model available with slug '{slug}'")


async def all_providers_async(db) -> list[ProviderSpec]:
    return [provider_from_row(r) for r in await _rows_async(db, RegisteredProvider)]


async def get_collection_async(db, collection_slug: str):
    row = (await db.execute(_owner_query(collection_slug))).scalar_one_or_none()
    if row is None:
        raise KeyError(f"No provider has collection '{collection_slug}'")
    spec = provider_from_row(row)
    return spec, spec.collections[collection_slug]


async def claim_collections_async(db, provider_id, provider_slug: str, declared: list[str]) -> list[str]:
    result = await db.execute(select(ProviderCollection.collection_slug, RegisteredProvider.slug).join(RegisteredProvider, ProviderCollection.provider_id == RegisteredProvider.id))
    problems = collection_conflicts(declared, _owned_by_others(result.all()), provider_slug)
    if problems:
        return problems

    await db.execute(delete(ProviderCollection).where(ProviderCollection.provider_id == provider_id))
    for slug in declared:
        db.add(ProviderCollection(collection_slug=slug, provider_id=provider_id))
    return []
