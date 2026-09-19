import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from geotriage import Collection, Requires, check_compatibility
from geotriage.compat import CompatibilityResult
from geotriage.descriptor import collection_from_descriptor
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db.models.registry import RegisteredModel, RegisteredProvider


@dataclass(frozen=True)
class CatalogueModel:
    slug: str
    name: str
    description: str
    requires: Requires


class Catalogue:
    def __init__(self, models: list[dict], providers: list[dict]):
        self.models = {
            m["slug"]: CatalogueModel(
                slug=m["slug"],
                name=m.get("name", m["slug"]),
                description=m.get("description", ""),
                requires=Requires(bands=list(m["requires"]["bands"]), max_cloud_cover=m["requires"].get("max_cloud_cover")),
            )
            for m in models
        }
        self.collections: dict[str, Collection] = {slug: collection_from_descriptor(c) for p in providers for slug, c in p.get("collections", {}).items()}

    @classmethod
    def from_session(cls, db: Session) -> "Catalogue":
        def enabled(table):
            return [row.descriptor for row in db.execute(select(table).where(table.is_enabled.is_(True)).order_by(table.slug)).scalars()]

        return cls(enabled(RegisteredModel), enabled(RegisteredProvider))

    @classmethod
    def from_file(cls, path: Path) -> "Catalogue":
        data = json.loads(path.read_text())
        return cls(data["models"], data["providers"])

    def compatibility(self, model_slug: str, collection_slug: str) -> CompatibilityResult:
        # check_compatibility reads only `requires` off a model
        return check_compatibility(SimpleNamespace(requires=self.models[model_slug].requires), self.collections[collection_slug])
