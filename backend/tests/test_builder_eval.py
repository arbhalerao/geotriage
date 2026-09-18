from evals.runner import Suite, run_suite
from evals.suites.builder import metrics_for, score
from llm import FakeClient

DHAKA = [90.33, 23.66, 90.51, 23.90]

RECURRING = {
    "id": "dhaka-floods-daily",
    "input": "Watch for flooding around Dhaka every day until the end of October",
    "expected": {
        "kind": "draft",
        "time_mode": "recurring",
        "time_end": "2026-10-31",
        "poll_interval_minutes": 1440,
        "bbox": DHAKA,
        "model": "ndwi-water-detector",
        "collections_allowed": ["sentinel-2-l2a", "landsat-c2-l2"],
    },
}

QUESTION = {"id": "springfield-which", "input": "Monitor water in Springfield", "expected": {"kind": "question"}}


def polygon(minx, miny, maxx, maxy) -> dict:
    return {"type": "Polygon", "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]]}


def draft(**changes) -> dict:
    payload = {
        "name": "Dhaka floods",
        "geometry": polygon(*DHAKA),
        "time_mode": "recurring",
        "time_end": "2026-10-31T23:59:59Z",
        "poll_interval_minutes": 1440,
        "collection_slugs": ["sentinel-2-l2a"],
        "models": [{"model_slug": "ndwi-water-detector"}],
    }
    return {"kind": "draft", "draft": {**payload, **changes}, "message": ""}


def test_a_right_draft_scores_full_marks_on_everything_that_applies():
    scores = score(RECURRING, draft())
    assert scores == {m: (0.0 if m == "asks_needlessly" else 1.0) for m in metrics_for(RECURRING)}


def test_validity_is_judged_against_the_pinned_day_not_the_real_one():
    """an end of 2026-09-01 is past on the eval's day, so a recurring draft ending then is invalid, whatever today really is"""
    assert score(RECURRING, draft(time_end="2026-09-01T00:00:00Z"))["valid"] == 0.0


def test_a_recurring_draft_that_sends_its_own_start_gets_the_dates_wrong():
    assert score(RECURRING, draft(time_start="2026-09-14T00:00:00Z"))["dates"] == 0.0


def test_an_area_somewhere_else_misses():
    assert score(RECURRING, draft(geometry=polygon(72.77, 18.89, 72.98, 19.27)))["area"] == 0.0


def test_a_collection_outside_the_allowed_ones_misses():
    assert score(RECURRING, draft(collection_slugs=["sentinel-2-l2a", "landsat-c2-l1"]))["collections"] == 0.0


def test_hourly_is_not_a_fair_reading_of_daily():
    assert score(RECURRING, draft(poll_interval_minutes=60))["interval"] == 0.0
    assert score(RECURRING, draft(poll_interval_minutes=720))["interval"] == 1.0


def test_asking_on_a_clear_prompt_misses_every_draft_metric():
    scores = score(RECURRING, {"kind": "question", "message": "where?"})
    assert scores["asks_needlessly"] == 1.0
    assert scores["kind"] == scores["valid"] == scores["area"] == 0.0


def test_a_question_case_is_scored_only_on_asking():
    assert score(QUESTION, {"kind": "question"}) == {"kind": 1.0, "asks_when_needed": 1.0}


def test_either_accepted_kind_counts():
    case = {"id": "past-end", "expected": {"kind": ["cannot", "question"]}}
    assert score(case, {"kind": "question"})["kind"] == score(case, {"kind": "cannot"})["kind"] == 1.0


def test_metrics_are_averaged_only_over_the_cases_they_apply_to():
    suite = Suite(
        name="builder",
        description="",
        metrics=["kind", "area", "asks_when_needed"],
        prompts=[],
        run=lambda c, _: draft() if c is RECURRING else {"kind": "draft"},
        score=score,
        metrics_for=metrics_for,
    )
    summary = run_suite(suite, [RECURRING, QUESTION], FakeClient([]), progress=lambda _l: None)["summary"]
    assert summary["area"] == 1.0, "the question case has no area, and must not count as a miss"
    assert summary["asks_when_needed"] == 0.0
    assert summary["kind"] == 0.5
