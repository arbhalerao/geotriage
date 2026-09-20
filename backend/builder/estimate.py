import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from shapely.geometry import shape

from builder.guardrails import MAX_SHARE_OF_FREE_DISK
from builder.places import bbox_area_km2

# staging writes each band as float32
BYTES_PER_PIXEL = 4


@dataclass(frozen=True)
class Estimate:
    scenes: int
    staged_bytes: int
    free_bytes: int
    capped: bool
    from_past_window: bool


class Estimator(Protocol):
    def estimate(self, draft: dict, now: datetime) -> Estimate: ...


def staged_bytes(scenes: int, area_km2: float, resolution_m: float, rasters: int) -> int:

    pixels = area_km2 * 1_000_000 / (resolution_m**2)
    return int(scenes * rasters * pixels * BYTES_PER_PIXEL)


def search_window(draft: dict, now: datetime) -> tuple[datetime, datetime, bool]:
    end = datetime.fromisoformat(draft["time_end"])
    if draft["time_mode"] == "historical":
        return datetime.fromisoformat(draft["time_start"]), end, False
    return now - (end - now), now, True


def format_bytes(count: int) -> str:
    for unit, size in (("TB", 1024**4), ("GB", 1024**3), ("MB", 1024**2)):
        if count >= size:
            return f"{count / size:.1f} {unit}"
    return "under 1 MB"


class ArchiveEstimator:


    def __init__(self, session_factory=None, scratch: str | None = None):
        self._session_factory = session_factory
        self._scratch = scratch or os.getenv("RUN_SCRATCH") or tempfile.gettempdir()

    def estimate(self, draft: dict, now: datetime) -> Estimate:
        from domain.catalogue import get_collection, get_model
        from pipeline.discover import MAX_SCENES, search_stac

        if self._session_factory is None:
            from core.db.sync import get_session

            self._session_factory = get_session

        area = shape(draft["geometry"])
        area_km2 = bbox_area_km2(area.bounds)
        start, end, from_past = search_window(draft, now)

        free = shutil.disk_usage(self._scratch).free
        limit_bytes = MAX_SHARE_OF_FREE_DISK * free
        scenes = total_bytes = 0
        capped = False
        with self._session_factory() as db:
            model = get_model(db, draft["models"][0]["model_slug"])
            rasters = len(model.requires.bands) + len(model.rasters)
            for slug in draft["collection_slugs"]:
                if total_bytes > limit_bytes:
                    # already over, so the remaining collections can only make it more so
                    capped = True
                    break
                provider, collection = get_collection(db, slug)
                resolution = max(collection.resolution_m, model.requires.gsd_m or 0) or collection.resolution_m
                per_scene = staged_bytes(1, area_km2, resolution, rasters)
                # just enough scenes to cross the limit, and never more than discovery itself would take
                enough = int((limit_bytes - total_bytes) // per_scene) + 1 if per_scene else MAX_SCENES
                max_items = min(MAX_SCENES, max(enough, 1))
                found = len(search_stac(provider, collection, area, start, end, model.requires.max_cloud_cover, max_items=max_items))
                scenes += found
                total_bytes += found * per_scene
                capped = capped or found >= max_items

        return Estimate(scenes=scenes, staged_bytes=total_bytes, free_bytes=free, capped=capped, from_past_window=from_past)
