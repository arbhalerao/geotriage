import logging
import os
import shutil
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db.models.results import WorkflowItem
from runners.docker import SCRATCH

log = logging.getLogger(__name__)

SCENES = os.path.join(SCRATCH, "scenes")

STALE_JOB_FOLDER_S = 2 * 60 * 60


def scene_dir(item_id: uuid.UUID) -> str:
    return os.path.join(SCENES, str(item_id))


def band_path(item_id: uuid.UUID, name: str) -> str:
    return os.path.join(scene_dir(item_id), "bands", f"{name}.tif")


def map_path(item_id: uuid.UUID, name: str) -> str:
    return os.path.join(scene_dir(item_id), "maps", f"{name}.tif")


def ensure_dirs(item_id: uuid.UUID) -> None:
    for sub in ("bands", "maps"):
        os.makedirs(os.path.join(scene_dir(item_id), sub), exist_ok=True)


def remove_scene(item_id: uuid.UUID) -> None:
    shutil.rmtree(scene_dir(item_id), ignore_errors=True)


def sweep(db: Session, now: float | None = None) -> int:
    now = time.time() if now is None else now
    removed = 0
    if os.path.isdir(SCENES):
        names = os.listdir(SCENES)
        ids = {}
        for name in names:
            try:
                ids[uuid.UUID(name)] = name
            except ValueError:
                continue
        live = set(db.execute(select(WorkflowItem.id).where(WorkflowItem.id.in_(ids), WorkflowItem.imagery_kept.is_(None))).scalars()) if ids else set()
        for item_id, name in ids.items():
            if item_id not in live:
                shutil.rmtree(os.path.join(SCENES, name), ignore_errors=True)
                removed += 1
    if os.path.isdir(SCRATCH):
        for name in os.listdir(SCRATCH):
            path = os.path.join(SCRATCH, name)
            if name.startswith(("run-job-", "run-out-")) and now - os.path.getmtime(path) > STALE_JOB_FOLDER_S:
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
    return removed
