import json
from pathlib import Path

import pytest

from evals.runner import Suite, compare, load_cases, run_suite, save_run, saved_runs
from llm import FakeClient, LLMError, Prompt, Reply


def echo_suite() -> Suite:
    def run(case, client):
        return {"answer": client.chat([{"role": "user", "content": case["input"]}]).content}

    def score(case, output):
        return {"right": float(output["answer"] == case["expected"])}

    return Suite(name="echo", description="", metrics=["right"], prompts=[Prompt("echo", "text")], run=run, score=score)


CASES = [
    {"id": "a", "input": "one", "expected": "yes", "tags": ["quick"]},
    {"id": "b", "input": "two", "expected": "yes"},
    {"id": "c", "input": "three", "expected": "yes"},
]


def quiet(_line):
    pass


def test_scores_are_averaged_over_every_case():
    run = run_suite(echo_suite(), CASES, FakeClient(["yes", "no", "yes"]), progress=quiet)
    assert run["summary"]["right"] == pytest.approx(0.667, abs=0.001)
    assert run["summary"]["cases"] == 3


def test_a_case_that_fails_scores_zero_and_the_run_carries_on():
    run = run_suite(echo_suite(), CASES, FakeClient(["yes", LLMError("model server returned 503"), "yes"]), progress=quiet)
    assert [c["scores"]["right"] for c in run["cases"]] == [1.0, 0.0, 1.0]
    assert run["summary"]["errors"] == 1
    assert "503" in run["cases"][1]["error"]


def test_an_unusable_reply_is_kept_on_the_failed_case():
    def run(case, client):
        raise LLMError("the reply did not match Answer", reply=Reply("not json"))

    suite = Suite(name="echo", description="", metrics=["right"], prompts=[], run=run, score=lambda c, o: {})
    result = run_suite(suite, CASES[:1], FakeClient([]), progress=quiet)
    assert result["cases"][0]["output"] == {"unusable_reply": "not json"}


def test_what_each_case_cost_is_added_up_across_its_calls():
    def run(case, client):
        client.chat([])
        client.chat([])
        return {"answer": "yes"}

    suite = Suite(name="echo", description="", metrics=["right"], prompts=[], run=run, score=lambda c, o: {"right": 1.0})
    replies = [Reply("", output_tokens=5, duration_ms=1000, cached=True), Reply("", output_tokens=7, duration_ms=2000)]
    [case] = run_suite(suite, CASES[:1], FakeClient(replies), progress=quiet)["cases"]
    assert (case["calls"], case["cached"], case["output_tokens"], case["duration_ms"]) == (2, 1, 12, 3000)


def test_a_run_records_which_prompt_version_produced_it():
    run = run_suite(echo_suite(), CASES[:1], FakeClient(["yes"]), progress=quiet)
    assert run["prompts"] == {"echo": Prompt("echo", "text").version}


def test_cases_can_be_narrowed_to_a_tag(tmp_path: Path):
    (tmp_path / "echo.jsonl").write_text("\n".join(json.dumps(c) for c in CASES) + "\n")
    assert [c["id"] for c in load_cases("echo", tag="quick", directory=tmp_path)] == ["a"]
    assert len(load_cases("echo", directory=tmp_path)) == 3


def test_a_case_id_used_twice_is_refused(tmp_path: Path):
    (tmp_path / "echo.jsonl").write_text(json.dumps(CASES[0]) + "\n" + json.dumps(CASES[0]) + "\n")
    with pytest.raises(ValueError, match="used twice"):
        load_cases("echo", directory=tmp_path)


def test_saved_runs_list_oldest_first(tmp_path: Path):
    suite = echo_suite()
    first = run_suite(suite, CASES[:1], FakeClient(["yes"]), progress=quiet)
    second = {**first, "started_at": "2099-01-01T00:00:00+00:00"}
    save_run(second, tmp_path)
    save_run(first, tmp_path)
    assert [p.name[:4] for p in saved_runs("echo", tmp_path)][-1] == "2099"


def test_a_comparison_shows_the_score_change_and_which_cases_flipped():
    suite = echo_suite()
    before = run_suite(suite, CASES, FakeClient(["yes", "no", "yes"]), progress=quiet)
    after = run_suite(suite, CASES, FakeClient(["yes", "yes", "no"]), progress=quiet)

    report = compare(before, after, suite.metrics)
    assert "b  right 0.00 -> 1.00" in report
    assert "c  right 1.00 -> 0.00" in report
    assert "  a  " not in report, "a case that scored the same both times is not news"


def test_a_comparison_calls_out_runs_over_different_cases():
    suite = echo_suite()
    before = run_suite(suite, CASES, FakeClient(["yes", "yes", "yes"]), progress=quiet)
    after = {**run_suite(suite, CASES[:1], FakeClient(["yes"]), progress=quiet), "tag": "quick"}
    assert "different cases: every case -> tagged 'quick'" in compare(before, after, suite.metrics)


def test_a_comparison_calls_out_a_changed_prompt():
    suite = echo_suite()
    before = run_suite(suite, CASES[:1], FakeClient(["yes"]), progress=quiet)
    after = {**before, "prompts": {"echo": "echo@new"}}
    assert "prompt changed" in compare(before, after, suite.metrics)
