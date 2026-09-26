import os
import uuid
from datetime import datetime, timezone

import numpy as np
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db.models.aoi import Aoi
from core.db.models.enums import ModelRunStatus, WorkflowItemStatus
from core.db.models.results import ModelRun, WorkflowItem
from core.db.models.stac import StacItem
from core.db.models.workflow import Workflow, WorkflowModelCollectionConfig, WorkflowModelConfig
from core.db.sync import get_session
from pipeline import scratch
from storage import cog
from geotriage import build_normalized_assets
from domain.catalogue import get_collection, get_model


def target_gsd(db: Session, item: WorkflowItem, stac: StacItem) -> float | None:
    """
    the finest resolution any enabled model asks for, or None for native

    when every model on a scene declares one, the platform can read an overview instead
    """
    models = _enabled_models(db, item, stac)
    if not models or any(m.requires.gsd_m is None for m in models):
        return None
    return min(m.requires.gsd_m for m in models)


def _enabled_models(db: Session, item: WorkflowItem, stac: StacItem) -> list:
    links = (
        db.execute(
            select(WorkflowModelCollectionConfig).where(
                WorkflowModelCollectionConfig.workflow_id == item.workflow_id,
                WorkflowModelCollectionConfig.collection_slug == stac.collection_slug,
                WorkflowModelCollectionConfig.is_enabled.is_(True),
            )
        )
        .scalars()
        .all()
    )
    models = []
    for link in links:
        wmc = db.get(WorkflowModelConfig, link.workflow_model_config_id)
        if wmc is not None:
            models.append(get_model(db, wmc.model_slug))
    return models


def required_bands(db: Session, item: WorkflowItem, stac: StacItem) -> list[str]:
    """union of band names across every model enabled for this scene's collection"""
    enabled = (
        db.execute(
            select(WorkflowModelCollectionConfig).where(
                WorkflowModelCollectionConfig.workflow_id == item.workflow_id,
                WorkflowModelCollectionConfig.collection_slug == stac.collection_slug,
                WorkflowModelCollectionConfig.is_enabled.is_(True),
            )
        )
        .scalars()
        .all()
    )
    names: set[str] = set()
    for link in enabled:
        wmc = db.get(WorkflowModelConfig, link.workflow_model_config_id)
        if wmc is None:
            continue
        names.update(get_model(db, wmc.model_slug).requires.bands)
    return sorted(names)


def pick_overview(native_gsd_m: float, decimations: list[int], target_gsd_m: float | None):
    """
    index of the coarsest overview still at least as fine as `target_gsd_m`, None for full resolution

    COGs ship pre-decimated copies of themselves,
    so reading level 4 of a 10 m scene pulls roughly 1/256th of the bytes
    """
    if not target_gsd_m or not decimations or native_gsd_m <= 0:
        return None
    usable = [i for i, factor in enumerate(decimations) if native_gsd_m * factor <= target_gsd_m]
    return max(usable) if usable else None


def load_band(href: str, aoi_geom_wgs84, signed_href=None, native_gsd_m=0.0, target_gsd_m=None):
    """
    returns (array, transform, crs) with values as stored,
    the caller calibrating since it knows which band it is

    `signed_href` is batched by the caller, because a container provider charges a round-trip per call
    with `target_gsd_m` set, GDAL serves the decimated grid as if it were the dataset,
    so the AOI clip below is unchanged and only far fewer bytes cross the network
    """
    import rasterio
    from rasterio.mask import mask as rio_mask
    from rasterio.warp import transform_geom

    url = f"/vsicurl/{signed_href or href}"

    level = None
    if target_gsd_m:
        with rasterio.open(url) as probe:
            level = pick_overview(native_gsd_m, probe.overviews(1), target_gsd_m)

    with rasterio.open(url, overview_level=level) if level is not None else rasterio.open(url) as src:
        aoi_proj = transform_geom("EPSG:4326", src.crs.to_string(), mapping(aoi_geom_wgs84))
        out, out_transform = rio_mask(src, [aoi_proj], crop=True, nodata=0)
        data = out[0].astype(np.float32)
        nodata = src.nodata if src.nodata is not None else 0
        data[data == nodata] = np.nan
        return data, out_transform, src.crs


def fail_runs_for_item(db: Session, item_id: uuid.UUID, message: str) -> None:
    runs = db.execute(select(ModelRun).where(ModelRun.workflow_item_id == item_id)).scalars().all()
    now = datetime.now(timezone.utc)
    for run in runs:
        if run.status in (ModelRunStatus.queued, ModelRunStatus.running):
            run.status = ModelRunStatus.failed
            run.error_message = message[:500]
            run.completed_at = now


def _mark_item_failed(session_factory, item_id: uuid.UUID, status: WorkflowItemStatus, error: Exception) -> None:
    """its own connection, because the session that hit the error may be unusable"""
    with session_factory() as db:
        item = db.get(WorkflowItem, item_id)
        if item is not None:
            item.status = status
            item.error_message = str(error)[:500]
            fail_runs_for_item(db, item.id, str(error))
            db.commit()


def stage_bands(workflow_item_id: uuid.UUID, session_factory=get_session) -> uuid.UUID:
    with session_factory() as db:
        item = db.get(WorkflowItem, workflow_item_id)
        if item is None:
            return workflow_item_id
        if item.status == WorkflowItemStatus.screened_out:
            return workflow_item_id  # the cheap gate already rejected this scene

        stac = db.get(StacItem, item.stac_item_id)
        workflow = db.get(Workflow, item.workflow_id)
        aoi = db.get(Aoi, workflow.aoi_id)
        provider, col_info = get_collection(db, stac.collection_slug)

        wanted = [name for name in required_bands(db, item, stac) if not os.path.exists(scratch.band_path(item.id, name))]
        if not wanted:
            return workflow_item_id
        gsd = target_gsd(db, item, stac)

        try:
            assets = build_normalized_assets(stac.assets, col_info, wanted)
        except ValueError as exc:
            item.status = WorkflowItemStatus.fetch_failed
            item.error_message = str(exc)[:500]
            fail_runs_for_item(db, item.id, str(exc))
            db.commit()
            raise

        aoi_geom = to_shape(aoi.geometry)

        item.status = WorkflowItemStatus.fetching
        db.commit()

        try:
            # inside the try, because the item is already `fetching`:
            # a signer that raises outside it strands the scene there with its runs still queued
            # one signing round-trip for the whole scene, not one per band
            names = list(assets)
            signed = dict(zip(names, provider.sign([assets[n]["href"] for n in names])))
            scratch.ensure_dirs(item.id)

            for name, asset in assets.items():
                array, transform, crs = load_band(
                    asset["href"],
                    aoi_geom,
                    signed.get(name),
                    native_gsd_m=col_info.resolution_m,
                    target_gsd_m=gsd,
                )
                if array is None or array.size == 0:
                    raise ValueError(f"empty array for band '{name}'")
                # store physical units, not digital numbers: the collection owns the conversion,
                # so a model never learns which archive it came from
                array = col_info.band(name).calibrate(array)
                path = scratch.band_path(item.id, name)
                cog.write_to_disk(f"{path}.part", array, transform, crs)
                os.replace(f"{path}.part", path)
                del array
        except Exception as exc:
            _mark_item_failed(session_factory, workflow_item_id, WorkflowItemStatus.fetch_failed, exc)
            raise

    return workflow_item_id
