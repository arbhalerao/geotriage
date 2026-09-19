import json

import pytest

from builder import agent
from builder.agent import MAX_REPAIRS, MAX_ROUNDS, build
from builder.catalogue import Catalogue
from builder.places import RecordedPlaces
from evals.runner import EVALS_DIR
from evals.suites.builder import pinned_today
from llm import FakeClient, Reply, ToolCall

CATALOGUE = Catalogue.from_file(EVALS_DIR / "fixtures" / "catalogue.json")
PLACES = RecordedPlaces(EVALS_DIR / "fixtures" / "places")
ASK = [{"role": "user", "content": "Monitor water in Dhaka for 2024"}]


@pytest.fixture(autouse=True)
def today():
    with pinned_today():
        yield


def calls(*pairs) -> Reply:
    return Reply("", tool_calls=[ToolCall(name, args) for name, args in pairs])


def answer(**fields) -> Reply:
    base = {
        "kind": "draft",
        "place_id": "place_1",
        "time_mode": "historical",
        "time_start": "2024-01-01",
        "time_end": "2024-12-31",
        "poll_interval_minutes": None,
        "model_slug": "ndwi-water-detector",
        "collection_slugs": [],
        "message": "Water over Dhaka for 2024.",
    }
    return calls(("answer", {**base, **fields}))


def look_up(place="Dhaka, Bangladesh") -> Reply:
    return calls(("list_models", {}), ("find_place", {"query": place}))


def feedback(fake: FakeClient, request: int) -> str:
    return fake.requests[request]["messages"][-1]["content"]


def test_a_clear_request_becomes_a_workflow_the_api_accepts():
    outcome = build(ASK, FakeClient([look_up(), answer()]), CATALOGUE, PLACES)

    assert (outcome.kind, outcome.tool_calls, outcome.repairs) == ("draft", 3, 0)
    draft = outcome.draft
    assert draft["geometry"]["type"] == "Polygon"
    assert draft["time_start"] == "2024-01-01T00:00:00+00:00"
    assert draft["time_end"] == "2024-12-31T23:59:59+00:00"
    assert draft["models"] == [{"model_slug": "ndwi-water-detector"}]
    assert "poll_interval_minutes" not in draft


def test_every_request_offers_the_same_tools_so_the_prompt_can_be_reused():
    fake = FakeClient([look_up(), answer()])
    build(ASK, fake, CATALOGUE, PLACES)
    assert fake.requests[0]["tools"] == fake.requests[1]["tools"]
    assert "answer" in [t.name for t in fake.requests[0]["tools"]]


def test_the_model_sees_today_and_the_tool_results():
    fake = FakeClient([look_up(), answer()])
    build(ASK, fake, CATALOGUE, PLACES)
    final = fake.requests[-1]["messages"]
    assert "2026-09-14" in final[0]["content"]
    assert any(m["role"] == "tool" and "place_1" in m["content"] for m in final)


def test_collections_are_every_one_that_works_unless_the_user_named_some():
    assert build(ASK, FakeClient([look_up(), answer()]), CATALOGUE, PLACES).draft["collection_slugs"] == ["sentinel-2-l2a", "landsat-c2-l2", "landsat-c2-l1"]
    named = build(ASK, FakeClient([look_up(), answer(collection_slugs=["sentinel-2-l2a"])]), CATALOGUE, PLACES)
    assert named.draft["collection_slugs"] == ["sentinel-2-l2a"]


def test_blank_fields_count_as_missing_and_the_problem_says_what_to_give():
    fake = FakeClient([look_up(), answer(time_start=""), answer()])
    outcome = build(ASK, fake, CATALOGUE, PLACES)
    assert (outcome.kind, outcome.repairs) == ("draft", 1)
    assert "first day of the period" in feedback(fake, 2)


def test_a_draft_with_a_problem_is_sent_back_as_the_tool_result_and_the_fix_is_kept():
    fake = FakeClient([look_up(), answer(collection_slugs=["banana"]), answer()])
    outcome = build(ASK, fake, CATALOGUE, PLACES)
    assert (outcome.kind, outcome.repairs) == ("draft", 1)
    returned = fake.requests[2]["messages"][-1]
    assert returned["role"] == "tool" and "'banana' doesn't exist" in returned["content"]


def test_a_draft_that_is_never_fixed_becomes_an_honest_refusal():
    broken = answer(model_slug="vegetation")
    outcome = build(ASK, FakeClient([look_up(), *[broken] * (MAX_REPAIRS + 1)]), CATALOGUE, PLACES)
    assert (outcome.kind, outcome.draft, outcome.repairs) == ("cannot", None, MAX_REPAIRS)
    assert "vegetation" in outcome.message


def test_a_place_over_the_limit_is_refused_whatever_the_model_drafts():
    outcome = build([{"role": "user", "content": "Watch Africa"}], FakeClient([look_up("Africa"), answer()]), CATALOGUE, PLACES)
    assert (outcome.kind, outcome.draft) == ("cannot", None)
    assert "largest area" in outcome.message


def test_a_question_passes_through_with_its_message():
    fake = FakeClient([calls(("find_place", {"query": "Springfield"})), calls(("answer", {"kind": "question", "message": "Which Springfield?"}))])
    outcome = build([{"role": "user", "content": "Water in Springfield"}], fake, CATALOGUE, PLACES)
    assert (outcome.kind, outcome.message) == ("question", "Which Springfield?")


def test_a_question_with_nothing_to_ask_is_sent_back():
    fake = FakeClient([calls(("answer", {"kind": "question", "message": " "})), calls(("answer", {"kind": "question", "message": "Which place?"}))])
    assert build(ASK, fake, CATALOGUE, PLACES).repairs == 1


def test_an_answer_written_out_as_json_is_taken_as_the_answer():
    written = json.dumps(answer().tool_calls[0].arguments)
    outcome = build(ASK, FakeClient([look_up(), Reply(f"```json\n{written}\n```")]), CATALOGUE, PLACES)
    assert (outcome.kind, outcome.gave_up) == ("draft", False)


def test_problems_with_a_written_answer_come_back_as_a_message():
    written = json.dumps(answer(time_start="").tool_calls[0].arguments)
    fake = FakeClient([look_up(), Reply(written), answer()])
    assert build(ASK, fake, CATALOGUE, PLACES).repairs == 1
    returned = fake.requests[2]["messages"][-1]
    assert returned["role"] == "user" and "first day of the period" in returned["content"]


def test_a_short_written_question_or_refusal_is_taken_as_the_answer():
    assert agent.answer_in_text('cannot: The place "Africa" is too large.') == {"kind": "cannot", "message": 'The place "Africa" is too large.'}
    assert agent.answer_in_text("Question: which Portland?") == {"kind": "question", "message": "which Portland?"}
    assert agent.answer_in_text("draft: Dhaka for 2024") is None, "a draft needs its fields"


def test_the_nudge_shows_the_answer_shape():
    fake = FakeClient([look_up(), Reply("draft: Dhaka for 2024"), answer()])
    build(ASK, fake, CATALOGUE, PLACES)
    assert '"time_end": "YYYY-MM-DD"' in feedback(fake, 2)


def test_text_that_merely_contains_braces_is_not_an_answer():
    assert agent.answer_in_text("use {place} here") is None
    assert agent.answer_in_text('{"place": "Dhaka"}') is None


def test_arguments_that_are_not_an_answer_are_sent_back():
    fake = FakeClient([calls(("answer", {"kind": "maybe"})), calls(("answer", {"kind": "cannot", "message": "No detector for that."}))])
    outcome = build(ASK, fake, CATALOGUE, PLACES)
    assert (outcome.kind, outcome.repairs) == ("cannot", 1)
    assert "kind" in feedback(fake, 1)


def test_a_historical_run_ending_today_ends_now():
    outcome = build(ASK, FakeClient([look_up(), answer(time_start="2026-08-01", time_end="2026-09-14")]), CATALOGUE, PLACES)
    assert outcome.draft["time_end"] == "2026-09-14T12:00:00+00:00"


def test_a_historical_run_ending_later_is_a_problem_not_quietly_shortened():
    fake = FakeClient([look_up(), answer(time_start="2027-12-01", time_end="2027-12-31"), calls(("answer", {"kind": "cannot", "message": "That's in the future."}))])
    outcome = build(ASK, fake, CATALOGUE, PLACES)
    assert (outcome.kind, outcome.repairs) == ("cannot", 1)
    assert "can't end in the future" in feedback(fake, 2)


def test_a_recurring_draft_needs_an_interval_and_ignores_a_start():
    missing = answer(time_mode="recurring", time_start="2026-09-14", time_end="2026-10-31", poll_interval_minutes=0)
    fixed = answer(time_mode="recurring", time_start="2026-09-14", time_end="2026-10-31", poll_interval_minutes=1440)
    outcome = build(ASK, FakeClient([look_up(), missing, fixed]), CATALOGUE, PLACES)
    assert outcome.repairs == 1
    assert "time_start" not in outcome.draft
    assert outcome.draft["poll_interval_minutes"] == 1440


def test_a_large_area_or_long_history_is_drafted_with_a_warning():
    outcome = build(ASK, FakeClient([look_up("Rann of Kutch"), answer(time_start="2020-01-01", time_end="2024-12-31")]), CATALOGUE, PLACES)
    assert outcome.kind == "draft"
    assert len(outcome.warnings) == 1, "Kutch is under the warning line, five years of history is not"


def test_a_model_that_never_answers_runs_out_of_rounds_and_says_so():
    outcome = build(ASK, FakeClient([calls(("list_models", {}))] * MAX_ROUNDS), CATALOGUE, PLACES)
    assert (outcome.kind, outcome.gave_up) == ("cannot", True)
    assert "ran out of turns" in outcome.message


def test_progress_is_reported_step_by_step():
    steps = []
    build(ASK, FakeClient([look_up(), answer(time_start=""), answer()]), CATALOGUE, PLACES, on_step=steps.append)
    assert steps == ["Checking the detectors", "Looking up Dhaka, Bangladesh", "Writing the draft", "Fixing the draft"]


def test_the_prompt_is_versioned():
    assert agent.PROMPT.version.startswith("builder@")


def test_a_draft_for_one_of_several_same_named_places_is_sent_back_to_ask():
    ask = [{"role": "user", "content": "Monitor water in Springfield for 2025"}]
    fake = FakeClient([look_up("Springfield"), answer(time_start="2025-01-01", time_end="2025-12-31"), calls(("answer", {"kind": "question", "message": "Which Springfield?"}))])
    outcome = build(ask, fake, CATALOGUE, PLACES)
    assert (outcome.kind, outcome.repairs) == ("question", 1)
    assert "Missouri" in feedback(fake, 2)


def test_naming_the_region_settles_which_place():
    ask = [{"role": "user", "content": "Monitor water in Springfield, Illinois for 2025"}]
    outcome = build(ask, FakeClient([look_up("Springfield"), answer(time_start="2025-01-01", time_end="2025-12-31")]), CATALOGUE, PLACES)
    assert outcome.kind == "draft"


def test_once_the_builder_has_asked_the_reply_is_trusted():
    ask = [
        {"role": "user", "content": "Monitor water in Springfield for 2025"},
        {"role": "assistant", "content": "Which Springfield?"},
        {"role": "user", "content": "the one in the Land of Lincoln"},
    ]
    outcome = build(ask, FakeClient([look_up("Springfield"), answer(time_start="2025-01-01", time_end="2025-12-31")]), CATALOGUE, PLACES)
    assert outcome.kind == "draft"


def test_a_draft_with_dates_the_user_never_gave_is_sent_back_to_ask():
    ask = [{"role": "user", "content": "Check the water around Mumbai"}]
    fake = FakeClient([look_up("Mumbai"), answer(), calls(("answer", {"kind": "question", "message": "For which dates?"}))])
    outcome = build(ask, fake, CATALOGUE, PLACES)
    assert (outcome.kind, outcome.repairs) == ("question", 1)
    assert "didn't say when" in feedback(fake, 2)


def test_a_name_repeated_in_its_own_address_does_not_count_as_naming_the_region():
    ask = [{"role": "user", "content": "Surface temperature in Hyderabad during May 2025"}]
    fake = FakeClient(
        [look_up("Hyderabad"), answer(model_slug="lst-detector", time_start="2025-05-01", time_end="2025-05-31"), calls(("answer", {"kind": "question", "message": "India or Pakistan?"}))]
    )
    assert build(ask, fake, CATALOGUE, PLACES).kind == "question"


def test_the_prompt_carries_the_worked_out_dates():
    fake = FakeClient([look_up(), answer()])
    build(ASK, fake, CATALOGUE, PLACES)
    assert "next summer: 2027-06-01 to 2027-08-31" in fake.requests[0]["messages"][0]["content"]
