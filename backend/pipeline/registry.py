import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from core.db.models.registry import RegisteredModel, RegisteredProvider
from core.db.sync import get_session
from domain.catalogue import claim_collections
from domain.images import admit
from domain.seed import BUILTIN_MODELS, BUILTIN_PROVIDERS

log = logging.getLogger(__name__)


def smoke_test_model(model_id: uuid.UUID, session_factory=get_session) -> bool:
    """runs the registered image against synthetic bands and enables it if it holds up"""
    with session_factory() as db:
        row = db.get(RegisteredModel, model_id)
        if row is None:
            return False

        verdict = admit(row.image, "model", smoke=True)
        checks = [{"name": n, "passed": p, "detail": d} for n, p, d in verdict.checks]

        row.admission = {"checks": checks, "smoke_pending": False}
        row.is_enabled = verdict.ok
        row.updated_at = datetime.now(timezone.utc)
        if not verdict.ok:
            row.admission["problems"] = verdict.problems
            log.warning("model %s (%s) failed its smoke test: %s", row.slug, row.image, verdict.problems)
        db.commit()
        return verdict.ok


def seed_defaults(session_factory=get_session) -> dict[str, list[str]]:
    """
    register the default images, if they are present and not already registered

    runs on boot, and an image that isn't built yet is reported rather than raised:
    a fresh checkout that hasn't run `make builtins` should come up empty, not dead
    """
    registered, skipped = [], []
    for image, table, kind in [
        *((i, RegisteredModel, "model") for i in BUILTIN_MODELS),
        *((i, RegisteredProvider, "provider") for i in BUILTIN_PROVIDERS),
    ]:
        with session_factory() as db:
            if db.execute(select(table.id).where(table.image == image)).scalar_one_or_none():
                continue

            verdict = admit(image, kind, smoke=(kind == "model"))
            if not verdict.ok:
                skipped.append(f"{image}: {'; '.join(verdict.problems)}")
                continue

            descriptor = verdict.descriptor
            slug = descriptor["slug"]
            existing = db.execute(select(table).where(table.slug == slug)).scalar_one_or_none()
            if existing is not None:
                # someone registered their own image under this slug; theirs wins
                continue

            row = table(
                slug=slug,
                image=image,
                descriptor=descriptor,
                is_enabled=True,
                admission={"checks": [{"name": n, "passed": p, "detail": d} for n, p, d in verdict.checks]},
            )
            db.add(row)
            db.flush()

            if kind == "provider":
                conflicts = claim_collections(db, row.id, slug, list(descriptor.get("collections", {})))
                if conflicts:
                    db.rollback()
                    skipped.append(f"{image}: {'; '.join(conflicts)}")
                    continue

            db.commit()
            registered.append(slug)

    if registered:
        log.info("seeded %d default(s): %s", len(registered), ", ".join(registered))
    for problem in skipped:
        log.warning("default image unavailable, skipping — %s", problem)
    return {"registered": registered, "skipped": skipped}


def delete_workflow_artifacts(workflow_id: uuid.UUID) -> None:
    """
    a queued job rather than a best-effort call after the commit,
    so a failed cleanup retries and a permanent failure is visible as a dead job rather than a log line
    """
    from storage import client as store

    store.delete_workflow_prefix(workflow_id)
