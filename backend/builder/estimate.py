import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Protocol

from shapely.geometry import shape

from domain.storage import MAX_SHARE_OF_FREE_DISK, bbox_area_km2, clipped_area_km2, free_bytes, staged_bytes, staging_resolution, verdict

log = logging.getLogger(__name__)

GROWTH = 8


@dataclass(frozen=True)
class Estimate:
    scenes: int
    staged_bytes: int
    free_bytes: int
    capped: bool
    input_bytes: int = 0
    result_bytes: int = 0

    @property
    def verdict(self) -> str:
        return verdict(self.staged_bytes, self.free_bytes)

    def as_result(self) -> dict:
        return {**asdict(self), "verdict": self.verdict}


class Estimator(Protocol):
    def estimate(self, draft: dict, now: datetime) -> Estimate: ...


def can_estimate(draft: dict) -> bool:
    return draft.get("time_mode") == "historical"


class ArchiveEstimator:


    def __init__(self, session_factory=None, scratch: str | None = None):
        self._session_factory = session_factory
        self._scratch = scratch

    def estimate(self, draft: dict, now: datetime) -> Estimate:
        from domain.catalogue import get_collection, get_model
        from pipeline.discover import MAX_SCENES, search_stac

        if self._session_factory is None:
            from core.db.sync import get_session

            self._session_factory = get_session

        if not can_estimate(draft):
            raise ValueError("only a historical workflow's storage can be estimated")
        area = shape(draft["geometry"])
        area_km2 = bbox_area_km2(area.bounds)
        start, end = datetime.fromisoformat(draft["time_start"]), datetime.fromisoformat(draft["time_end"])

        free = free_bytes(self._scratch)
        limit_bytes = MAX_SHARE_OF_FREE_DISK * free
        scenes = total_bytes = 0
        capped = False
        with self._session_factory() as db:
            model = get_model(db, draft["models"][0]["model_slug"])
            bands, derived = len(model.requires.bands), len(model.rasters)
            rasters = bands + derived
            input_total = result_total = 0
            for slug in draft["collection_slugs"]:
                if total_bytes > limit_bytes:
                    # already over, so the remaining collections can only make it more so
                    capped = True
                    break
                provider, collection = get_collection(db, slug)
                resolution = staging_resolution(collection.resolution_m, [model.requires.gsd_m])

                def search(max_items: int) -> tuple[list[dict], int, int]:
                    items = search_stac(provider, collection, area, start, end, model.requires.max_cloud_cover, max_items=max_items)
                    overlaps = [clipped_area_km2(item.get("geometry"), area) for item in items]
                    return items, sum(staged_bytes(1, km2, resolution, bands) for km2 in overlaps), sum(staged_bytes(1, km2, resolution, derived) for km2 in overlaps)

                whole = staged_bytes(1, area_km2, resolution, rasters)
                max_items = min(MAX_SCENES, max(int((limit_bytes - total_bytes) // whole) + 1, 1)) if whole else MAX_SCENES
                while True:
                    items, found_inputs, found_results = search(max_items)
                    found_bytes = found_inputs + found_results
                    settled = len(items) < max_items or max_items >= MAX_SCENES or total_bytes + found_bytes > limit_bytes
                    if settled:
                        break
                    max_items = min(MAX_SCENES, max_items * GROWTH)
                scenes += len(items)
                total_bytes += found_bytes
                input_total += found_inputs
                result_total += found_results
                capped = capped or len(items) >= max_items

        return Estimate(
            scenes=scenes,
            staged_bytes=total_bytes,
            free_bytes=free,
            capped=capped,
            input_bytes=input_total,
            result_bytes=result_total,
        )


def run_estimate(estimate_id: uuid.UUID, session_factory=None, estimator: Estimator | None = None, now: datetime | None = None) -> None:
    from api.schemas.workflow import utc_now
    from core.db.models.builder import StorageEstimate
    from core.db.models.enums import BuilderRunStatus

    if session_factory is None:
        from core.db.sync import get_session

        session_factory = get_session

    with session_factory() as db:
        row = db.get(StorageEstimate, estimate_id)
        if row is None:
            return
        draft = dict(row.draft)
        row.status = BuilderRunStatus.running
        db.commit()

    def record(**changes) -> None:
        with session_factory() as db:
            row = db.get(StorageEstimate, estimate_id)
            for name, value in changes.items():
                setattr(row, name, value)
            db.commit()

    try:
        result = (estimator or ArchiveEstimator()).estimate(draft, now or utc_now())
    except Exception as exc:
        record(status=BuilderRunStatus.failed, error=str(exc)[:1000])
        raise
    record(status=BuilderRunStatus.done, result=result.as_result())
