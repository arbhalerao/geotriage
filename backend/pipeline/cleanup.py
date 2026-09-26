import logging
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db.models.enums import ImageryKept, WorkflowItemStatus
from core.db.models.results import WorkflowItem
from core.db.models.stac import StacItem
from core.db.models.workflow import Workflow, WorkflowModelCollectionConfig, WorkflowModelConfig
from domain.catalogue import get_model
from domain.storage import imagery_to_keep
from pipeline import scratch
from storage import client as store

log = logging.getLogger(__name__)


def layer_names(db: Session, item: WorkflowItem) -> tuple[set[str], set[str]]:
    stac = db.get(StacItem, item.stac_item_id)
    slugs = db.execute(
        select(WorkflowModelConfig.model_slug)
        .join(WorkflowModelCollectionConfig, WorkflowModelCollectionConfig.workflow_model_config_id == WorkflowModelConfig.id)
        .where(
            WorkflowModelCollectionConfig.workflow_id == item.workflow_id,
            WorkflowModelCollectionConfig.collection_slug == stac.collection_slug,
            WorkflowModelCollectionConfig.is_enabled.is_(True),
        )
    ).scalars()
    inputs, results = set(), set()
    for slug in set(slugs):
        model = get_model(db, slug)
        inputs.update(model.requires.bands)
        results.update(model.rasters)
    return inputs - results, results


def apply_storage_policy(db: Session, item: WorkflowItem) -> None:
    if item.imagery_kept is not None:
        return
    workflow = db.get(Workflow, item.workflow_id)
    keep = imagery_to_keep(workflow.storage_policy.value, item.overall_severity.value if item.overall_severity else None, scored=item.status == WorkflowItemStatus.processed)
    if keep != "none":
        inputs, results = layer_names(db, item)
        files = {name: scratch.map_path(item.id, name) for name in results}
        if keep == "inputs_and_results":
            files.update({name: scratch.band_path(item.id, name) for name in inputs})
        for name, path in sorted(files.items()):
            if os.path.exists(path):
                store.upload_file(store.band_key(item.workflow_id, item.id, name), path)
    item.imagery_kept = ImageryKept(keep)


def finish_scene(db: Session, item: WorkflowItem) -> None:
    apply_storage_policy(db, item)
    db.commit()
    scratch.remove_scene(item.id)


def apply_storage_policy_quietly(db: Session, item: WorkflowItem) -> None:
    try:
        finish_scene(db, item)
    except Exception:  # noqa: BLE001 — an upload that failed is retried at finalize, never a reason to fail a scene's scoring
        db.rollback()
        log.warning("couldn't apply the storage policy to scene %s, finalize will try again", item.id, exc_info=True)
