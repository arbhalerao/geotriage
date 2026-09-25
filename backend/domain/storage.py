import math
import os
import shutil
import tempfile
from typing import Literal

BYTES_PER_PIXEL = 4
MAX_SHARE_OF_FREE_DISK = 0.5
WARN_SHARE_OF_FREE_DISK = 0.1

Verdict = Literal["fits", "large", "too_large"]


_INPUTS_KEPT_FOR = {
    "everything": {"red", "yellow", "green"},
    "alert_and_caution_in_full": {"red", "yellow"},
    "alert_in_full": {"red"},
    "results_only": set(),
    "scores_only": set(),
}


def imagery_to_keep(policy: str, severity: str | None, scored: bool) -> Literal["inputs_and_results", "results", "none"]:
    if policy == "everything":
        return "inputs_and_results"
    if not scored or policy == "scores_only":
        return "none"
    return "inputs_and_results" if severity in _INPUTS_KEPT_FOR[policy] else "results"


def bbox_area_km2(bbox: tuple[float, float, float, float]) -> float:
    west, south, east, north = bbox
    width = (east - west) * 111.32 * math.cos(math.radians((south + north) / 2))
    return abs(width * (north - south) * 110.57)


def clipped_area_km2(scene_footprint: dict | None, area) -> float:
    from shapely.geometry import shape

    if not scene_footprint:
        return bbox_area_km2(area.bounds)
    try:
        overlap = shape(scene_footprint).intersection(area)
    except Exception:  # noqa: BLE001 — an unreadable footprint is sized as the whole area, never as nothing
        return bbox_area_km2(area.bounds)
    return 0.0 if overlap.is_empty else bbox_area_km2(overlap.bounds)


def staged_bytes(scenes: int, area_km2: float, resolution_m: float, rasters: int) -> int:
    pixels = area_km2 * 1_000_000 / (resolution_m**2)
    return int(scenes * rasters * pixels * BYTES_PER_PIXEL)


def staging_resolution(collection_resolution_m: float, model_gsd_m: list[float | None]) -> float:

    if not model_gsd_m or any(gsd is None for gsd in model_gsd_m):
        return collection_resolution_m
    return max(collection_resolution_m, min(model_gsd_m))


def free_bytes(path: str | None = None) -> int:
    return shutil.disk_usage(path or os.getenv("RUN_SCRATCH") or tempfile.gettempdir()).free


def verdict(staged: int, free: int) -> Verdict:
    if staged > MAX_SHARE_OF_FREE_DISK * free:
        return "too_large"
    if staged > WARN_SHARE_OF_FREE_DISK * free:
        return "large"
    return "fits"


def format_bytes(count: int) -> str:
    for unit, size in (("TB", 1024**4), ("GB", 1024**3), ("MB", 1024**2)):
        if count >= size:
            return f"{count / size:.1f} {unit}"
    return "under 1 MB"
