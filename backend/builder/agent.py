import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timezone
from typing import Callable, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from api.schemas import workflow as workflow_schema
from builder import calendar
from builder.catalogue import Catalogue
from builder.guardrails import MAX_AREA_KM2, WARN_AREA_KM2, WARN_HISTORY_DAYS
from builder.places import Places
from builder.tools import Toolbox
from llm import Client, Tool, ToolCall, load_prompt
from llm.structured import every_field_required

log = logging.getLogger(__name__)

PROMPT = load_prompt("builder")

# every call to the model, looking things up and answering alike
MAX_ROUNDS = 10
# answers sent back with their problems before the builder gives up and says so
MAX_REPAIRS = 2


class Answer(BaseModel):
    kind: Literal["draft", "question", "cannot"]
    place_id: str | None = Field(None, description="from find_place")
    time_mode: Literal["historical", "recurring"] | None = None
    time_start: str | None = Field(None, description="YYYY-MM-DD, historical only")
    time_end: str | None = Field(None, description="YYYY-MM-DD")
    poll_interval_minutes: int | None = Field(None, description="recurring only")
    model_slug: str | None = None
    collection_slugs: list[str] = Field(default_factory=list, description="only collections the user named, otherwise empty")
    message: str = Field("", description="one or two sentences")

    @field_validator("place_id", "time_mode", "time_start", "time_end", "model_slug", mode="before")
    @classmethod
    def blank_is_missing(cls, value):
        # a small model writes "" for a field it has nothing for, which means the same as leaving it out
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("poll_interval_minutes", mode="before")
    @classmethod
    def zero_is_missing(cls, value):
        return None if value in (0, "", "0") else value


ANSWER = Tool(
    name="answer",
    description="Give your final answer. Call it once, after looking things up.",
    parameters=every_field_required(Answer.model_json_schema()),
)


ANSWER_SHAPE = (
    "Reply with only your answer as JSON, every field present: "
    '{"kind": "draft", "place_id": "place_1", "time_mode": "historical", "time_start": "YYYY-MM-DD", "time_end": "YYYY-MM-DD", '
    '"poll_interval_minutes": null, "model_slug": "...", "collection_slugs": [], "message": "..."}'
)


@dataclass
class Outcome:
    kind: str
    message: str
    draft: dict | None = None
    warnings: list[str] = field(default_factory=list)
    tool_calls: int = 0
    repairs: int = 0
    # the builder stopped trying rather than decided, so a refusal like this is never a correct answer
    gave_up: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def build(conversation: list[dict], client: Client, catalogue: Catalogue, places: Places, on_step: Callable[[str], None] = lambda _step: None) -> Outcome:
    now = workflow_schema.utc_now()
    toolbox = Toolbox(catalogue, places)
    tools = (*toolbox.definitions, ANSWER)
    messages = [{"role": "system", "content": PROMPT.render(today=now.date().isoformat(), next_year=now.year + 1, calendar=calendar.notes(now.date()))}, *conversation]
    tool_calls = repairs = 0
    problems: list[str] = []

    for _ in range(MAX_ROUNDS):
        reply = client.chat(messages, tools=tools)
        calls, in_text = reply.tool_calls, False
        if calls:
            messages.append({"role": "assistant", "content": reply.content, "tool_calls": [{"function": {"name": c.name, "arguments": c.arguments}} for c in calls]})
        else:
            messages.append({"role": "assistant", "content": reply.content})
            written = answer_in_text(reply.content)
            if written is None:
                messages.append({"role": "user", "content": ANSWER_SHAPE})
                continue
            calls, in_text = [ToolCall(ANSWER.name, written)], True

        for call in calls:
            tool_calls += 1
            if call.name != ANSWER.name:
                on_step(_describe(call.name, call.arguments))
                result = toolbox.call(call.name, call.arguments)
            else:
                on_step("Writing the draft" if repairs == 0 else "Fixing the draft")
                outcome, problems = _check(call.arguments, toolbox, catalogue, now, conversation)
                if not problems:
                    outcome.tool_calls, outcome.repairs = tool_calls, repairs
                    return outcome
                if repairs == MAX_REPAIRS:
                    return _give_up(problems, tool_calls, repairs)
                repairs += 1
                log.info("builder answer sent back (repair %d): %s", repairs, problems)
                result = {"accepted": False, "problems": problems, "next": "fix these and call answer again, or answer with a question or cannot"}
            if in_text:
                messages.append({"role": "user", "content": f"Your answer wasn't accepted: {json.dumps(result)}"})
            else:
                messages.append({"role": "tool", "tool_name": call.name, "content": json.dumps(result)})

    return _give_up(problems or ["it ran out of turns without answering"], tool_calls, repairs)


def _give_up(problems: list[str], tool_calls: int, repairs: int) -> Outcome:
    return Outcome(kind="cannot", message="I couldn't put together a workflow that the platform accepts: " + "; ".join(problems), tool_calls=tool_calls, repairs=repairs, gave_up=True)


def answer_in_text(content: str) -> dict | None:
    # "cannot: the place is too large" needs no fields beyond the reason
    short = re.match(r"\s*(question|cannot)\s*:\s*(.+)", content, re.DOTALL | re.IGNORECASE)
    if short and "{" not in content:
        return {"kind": short.group(1).lower(), "message": short.group(2).strip()}

    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end < start:
        return None
    try:
        written = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return None
    return written if isinstance(written, dict) and "kind" in written else None


def _describe(tool: str, arguments: dict) -> str:
    if tool == "find_place":
        return f"Looking up {arguments.get('query', 'the place')}"
    if tool == "list_collections":
        return "Checking which collections work"
    return "Checking the detectors"


def _check(arguments: dict, toolbox: Toolbox, catalogue: Catalogue, now: datetime, conversation: list[dict]) -> tuple[Outcome | None, list[str]]:
    try:
        answer = Answer.model_validate(arguments)
    except ValidationError as exc:
        return None, [f"{'.'.join(map(str, e['loc'])) or 'answer'}: {e['msg']}" for e in exc.errors()[:4]]
    place = toolbox.found.get(answer.place_id or "")
    # a place over the limit is refused outright, there's no point asking which one or when
    too_large = place is not None and place.area_km2 > MAX_AREA_KM2
    if answer.kind == "draft" and not too_large and (guess := unasked_place_guess(answer.place_id, toolbox, conversation) or unasked_time_guess(conversation)):
        return None, [guess]
    return settle(answer, toolbox, catalogue, now)


def unasked_place_guess(place_id: str | None, toolbox: Toolbox, conversation: list[dict]) -> str | None:
    distinct = toolbox.ambiguous.get(place_id or "")
    if not distinct or any(m["role"] == "assistant" for m in conversation):
        return None
    said = " ".join(m["content"] for m in conversation if m["role"] == "user").lower()
    chosen = toolbox.found[place_id]
    parts = [p.strip().lower() for p in chosen.name.split(",")]
    if any(len(part) > 3 and part != parts[0] and part in said for part in parts[1:]):
        return None
    options = "; ".join(p.name for p in distinct[:4])
    return f"several different places have this name ({options}) and the user didn't say which, so answer with a question asking which one"


def unasked_time_guess(conversation: list[dict]) -> str | None:
    if any(m["role"] == "assistant" for m in conversation):
        return None
    if calendar.mentions_time(" ".join(m["content"] for m in conversation if m["role"] == "user")):
        return None
    return "the user didn't say when or for how long, so answer with a question asking for the dates or how long to keep watching"


def settle(answer: Answer, toolbox: Toolbox, catalogue: Catalogue, now: datetime) -> tuple[Outcome, list[str]]:
    message = answer.message.strip()
    if answer.kind != "draft":
        return Outcome(kind=answer.kind, message=message), ([] if message else [f"a {answer.kind} needs a message, the question to ask or the reason"])

    problems = []
    place = toolbox.found.get(answer.place_id or "")
    if place is None:
        problems.append(f"place_id {answer.place_id!r} isn't one that find_place returned")
    elif place.area_km2 > MAX_AREA_KM2:
        # a guardrail, not a mistake to fix: no draft, whatever the model makes of it
        return (
            Outcome(
                kind="cannot", message=f"{place.name} covers about {place.area_km2:,.0f} km², above the largest area a workflow can cover ({MAX_AREA_KM2:,} km²). Try a city, district or lake instead."
            ),
            [],
        )

    model = catalogue.models.get(answer.model_slug or "")
    if model is None:
        problems.append(f"model_slug {answer.model_slug!r} isn't a detector from list_models")
    for slug in answer.collection_slugs:
        if slug not in catalogue.collections:
            problems.append(f"collection {slug!r} doesn't exist")
        elif model is not None and not catalogue.compatibility(model.slug, slug).compatible:
            problems.append(f"collection {slug!r} doesn't work with {model.slug}; if the user asked for it, answer cannot and say why")

    start, end = _day(answer.time_start), _day(answer.time_end)
    if answer.time_mode is None:
        problems.append("time_mode is missing: historical for dates already over, recurring to keep watching")
    if end is None:
        problems.append(f"time_end {answer.time_end!r} isn't a YYYY-MM-DD date: give the last day of the period")
    if answer.time_mode == "historical" and start is None:
        problems.append(f"time_start {answer.time_start!r} isn't a YYYY-MM-DD date: give the first day of the period the user asked about")
    if answer.time_mode == "recurring" and not answer.poll_interval_minutes:
        problems.append("poll_interval_minutes is missing: how often to check, 1440 for daily")
    if problems:
        return Outcome(kind="draft", message=message), problems

    # every collection that works, unless the user named some: the platform can judge compatibility, so the model needn't
    collections = list(dict.fromkeys(answer.collection_slugs)) or [slug for slug in catalogue.collections if catalogue.compatibility(model.slug, slug).compatible]
    payload = {
        "name": f"{model.name}, {place.name.split(',')[0]}",
        "geometry": place.polygon(),
        "time_mode": answer.time_mode,
        "time_end": _end_of(end, now, answer.time_mode).isoformat(),
        "collection_slugs": collections,
        "models": [{"model_slug": model.slug}],
    }
    if answer.time_mode == "historical":
        payload["time_start"] = datetime.combine(start, time.min, tzinfo=timezone.utc).isoformat()
    else:
        payload["poll_interval_minutes"] = answer.poll_interval_minutes

    try:
        workflow_schema.WorkflowCreate(**payload)
    except ValidationError as exc:
        return Outcome(kind="draft", message=message), [e["msg"].removeprefix("Value error, ") for e in exc.errors()]
    if answer.time_mode == "historical" and start > end:
        return Outcome(kind="draft", message=message), ["time_start is after time_end"]

    warnings = []
    if place.area_km2 > WARN_AREA_KM2:
        warnings.append(f"{place.name.split(',')[0]} covers about {place.area_km2:,.0f} km², a large area that will take a long time to scan")
    if answer.time_mode == "historical" and (end - start).days > WARN_HISTORY_DAYS:
        warnings.append(f"{(end - start).days} days of history is a lot of scenes to scan")
    return Outcome(kind="draft", message=message, draft=payload, warnings=warnings), []


def _day(value: str | None) -> date | None:
    try:
        return date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


def _end_of(day: date, now: datetime, mode: str) -> datetime:

    end = datetime.combine(day, time(23, 59, 59), tzinfo=timezone.utc)
    return now if mode == "historical" and day == now.date() else end
