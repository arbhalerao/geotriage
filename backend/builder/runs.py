import logging
import uuid

from builder import agent
from builder.catalogue import Catalogue
from builder.places import NominatimPlaces
from core.db.models.builder import BuilderRun
from core.db.models.enums import BuilderRunStatus
from core.db.sync import get_session
from llm import TracedClient, default_client

log = logging.getLogger(__name__)

# one per worker process, so a place looked up once isn't asked of OpenStreetMap again
_places = None


def _shared_places() -> NominatimPlaces:
    global _places
    if _places is None:
        _places = NominatimPlaces()
    return _places


def run_build(run_id: uuid.UUID, session_factory=get_session, client=None, catalogue=None, places=None) -> None:
    with session_factory() as db:
        run = db.get(BuilderRun, run_id)
        if run is None:
            return
        conversation = list(run.conversation)
        catalogue = catalogue or Catalogue.from_session(db)
        run.status = BuilderRunStatus.running
        db.commit()

    def record(**changes) -> None:
        with session_factory() as db:
            run = db.get(BuilderRun, run_id)
            for name, value in changes.items():
                setattr(run, name, value)
            db.commit()

    steps: list[str] = []

    def on_step(step: str) -> None:
        steps.append(step)
        record(steps=list(steps))

    client = client or TracedClient(default_client(), purpose="builder", prompt_version=agent.PROMPT.version)
    try:
        outcome = agent.build(conversation, client, catalogue, places or _shared_places(), on_step=on_step)
    except Exception as exc:
        record(status=BuilderRunStatus.failed, error=str(exc)[:1000])
        raise
    record(status=BuilderRunStatus.done, outcome=outcome.as_dict())
