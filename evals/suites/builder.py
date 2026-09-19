from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from unittest import mock

from pydantic import ValidationError
from shapely.geometry import box, shape

from api.schemas import workflow as workflow_schema
from builder import agent
from builder.catalogue import Catalogue
from builder.places import RecordedPlaces
from evals.runner import EVALS_DIR, Suite
from llm import Client

# fixed, so "until the end of October" means the same date in every run, whatever the calendar says
TODAY = date(2026, 9, 14)

# the share of the expected area's bounding box a draft's has to overlap, intersection over union
AREA_OVERLAP = 0.5

DRAFT_METRICS = ["mode", "dates", "area", "model", "collections", "asks_needlessly"]
METRICS = ["kind", "valid", *DRAFT_METRICS, "interval", "asks_when_needed"]


# from the plan: a little below what a large hosted model would need, since a small local model clearing them is the point
TARGETS = {
    "kind": (">=", 0.85),
    "valid": (">=", 1.0),
    "mode": (">=", 0.85),
    "dates": (">=", 0.85),
    "interval": (">=", 0.85),
    "area": (">=", 0.85),
    "model": (">=", 0.85),
    "collections": (">=", 0.85),
    "asks_when_needed": (">=", 0.80),
    "asks_needlessly": ("<=", 0.10),
}


def expected_kinds(case: dict) -> list[str]:
    """a case may accept more than one kind, e.g. asking about an impossible date is as good as refusing it"""
    kind = case["expected"]["kind"]
    return kind if isinstance(kind, list) else [kind]


def metrics_for(case: dict) -> list[str]:
    kinds = expected_kinds(case)
    if kinds == ["draft"]:
        interval = ["interval"] if case["expected"]["time_mode"] == "recurring" else []
        return ["kind", *DRAFT_METRICS, *interval]
    return ["kind", "asks_when_needed"] if kinds == ["question"] else ["kind"]


@contextmanager
def pinned_today():
    noon = datetime.combine(TODAY, time(12), tzinfo=timezone.utc)
    with mock.patch.object(workflow_schema, "utc_now", return_value=noon):
        yield


def score(case: dict, output: dict) -> dict[str, float]:
    kinds = expected_kinds(case)
    kind = None if output.get("gave_up") else output.get("kind")
    scores = {"kind": float(kind in kinds)}
    draft = output.get("draft") if kind == "draft" else None
    if draft:
        with pinned_today():
            try:
                workflow_schema.WorkflowCreate(**draft)
                scores["valid"] = 1.0
            except (ValidationError, TypeError):
                scores["valid"] = 0.0

    if kinds == ["question"]:
        scores["asks_when_needed"] = float(kind == "question")
    if kinds != ["draft"]:
        return scores

    expected = case["expected"]
    scores["asks_needlessly"] = float(kind == "question")
    if not draft:
        scores.update({m: 0.0 for m in metrics_for(case) if m not in scores})
        return scores

    scores["mode"] = float(draft.get("time_mode") == expected["time_mode"])
    scores["dates"] = float(_dates_match(draft, expected))
    scores["area"] = float(_overlap(draft.get("geometry"), expected["bbox"]) >= AREA_OVERLAP)
    models = [m.get("model_slug") for m in draft.get("models") or []]
    scores["model"] = float(models == [expected["model"]])
    chosen = set(draft.get("collection_slugs") or [])
    scores["collections"] = float(bool(chosen) and chosen <= set(expected["collections_allowed"]))
    if expected["time_mode"] == "recurring":
        scores["interval"] = float(_interval_close(draft.get("poll_interval_minutes"), expected["poll_interval_minutes"]))
    return scores


def _day(value) -> date | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _dates_match(draft: dict, expected: dict) -> bool:
    tolerance = expected.get("tolerance_days", 1)

    def near(actual, wanted) -> bool:
        day = _day(actual) if actual is not None else None
        return day is not None and abs((day - date.fromisoformat(wanted)).days) <= tolerance

    if not near(draft.get("time_end"), expected["time_end"]):
        return False
    if expected["time_mode"] == "recurring":
        # a recurring workflow starts when it's created, sending a start is itself a mistake
        return draft.get("time_start") is None
    return near(draft.get("time_start"), expected["time_start"])


def _overlap(geometry: dict | None, bbox: list[float]) -> float:
    """bounding boxes rather than exact outlines: the case names roughly where, not a surveyed boundary"""
    try:
        drawn = box(*shape(geometry).bounds)
    except Exception:  # noqa: BLE001 — anything that isn't a usable geometry simply doesn't overlap
        return 0.0
    wanted = box(*bbox)
    union = drawn.union(wanted).area
    return drawn.intersection(wanted).area / union if union else 0.0


def _interval_close(actual, wanted: int) -> bool:
    """within a factor of two: "daily" as 12 or 36 hours is a fair reading, as a week is not"""
    return isinstance(actual, int) and actual > 0 and wanted / 2 <= actual <= wanted * 2


CATALOGUE = Catalogue.from_file(EVALS_DIR / "fixtures" / "catalogue.json")
PLACES = RecordedPlaces(EVALS_DIR / "fixtures" / "places")


def run_agent(case: dict, client: Client) -> dict:
    with pinned_today():
        return agent.build([{"role": "user", "content": case["input"]}], client, CATALOGUE, PLACES).as_dict()


def always_ask(case: dict, client: Client) -> dict:
    return {"kind": "question", "draft": None, "message": "Could you tell me more about what you want to watch?"}


BUILDER = Suite(
    name="builder",
    description="the workflow builder agent, on the local model",
    metrics=METRICS,
    prompts=[agent.PROMPT],
    run=run_agent,
    score=score,
    metrics_for=metrics_for,
    targets=TARGETS,
)

ALWAYS_ASKS = Suite(
    name="builder_always_asks",
    description="baseline for the builder: asks a question whatever it is told",
    metrics=METRICS,
    prompts=[],
    run=always_ask,
    score=score,
    dataset="builder",
    metrics_for=metrics_for,
    uses_model=False,
    targets=TARGETS,
)
