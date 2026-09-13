from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from api.schemas.workflow import WorkflowCreate

NOW = datetime.now(timezone.utc)
DAY = timedelta(days=1)


def workflow(**fields) -> WorkflowCreate:
    base = dict(name="w", geometry={"type": "Polygon", "coordinates": []}, collection_slugs=["c"], models=[{"model_slug": "m"}])
    return WorkflowCreate(**{**base, **fields})


def test_a_historical_workflow_over_past_dates_is_accepted():
    workflow(time_mode="historical", time_start=NOW - 10 * DAY, time_end=NOW - DAY)


def test_a_historical_workflow_cannot_end_in_the_future():
    """it runs once, over scenes that already exist"""
    with pytest.raises(ValidationError, match="can't end in the future"):
        workflow(time_mode="historical", time_start=NOW - 10 * DAY, time_end=NOW + DAY)


def test_a_historical_workflow_takes_no_interval():
    with pytest.raises(ValidationError, match="only valid for recurring"):
        workflow(time_mode="historical", time_start=NOW - 10 * DAY, time_end=NOW - DAY, poll_interval_minutes=60)


def test_a_recurring_workflow_starts_when_it_is_created():
    before = datetime.now(timezone.utc)
    w = workflow(time_mode="recurring", time_end=NOW + 30 * DAY, poll_interval_minutes=1440)
    assert before <= w.time_start <= datetime.now(timezone.utc)


def test_a_recurring_workflow_does_not_take_a_start():
    """the start is always the moment of creation, so a caller-supplied one would be silently wrong"""
    with pytest.raises(ValidationError, match="send only time_end"):
        workflow(time_mode="recurring", time_start=NOW - DAY, time_end=NOW + 30 * DAY, poll_interval_minutes=60)


def test_a_recurring_workflow_has_to_end_in_the_future():
    with pytest.raises(ValidationError, match="end in the future"):
        workflow(time_mode="recurring", time_end=NOW - DAY, poll_interval_minutes=60)


def test_a_recurring_workflow_needs_an_interval():
    """it keeps fetching on that interval, so without one it would never run again"""
    with pytest.raises(ValidationError, match="need a poll_interval_minutes"):
        workflow(time_mode="recurring", time_end=NOW + 30 * DAY)


def test_a_historical_workflow_needs_a_start():
    with pytest.raises(ValidationError, match="need a time_start"):
        workflow(time_mode="historical", time_end=NOW - DAY)


def test_the_old_fixed_future_name_is_refused():
    with pytest.raises(ValidationError):
        workflow(time_mode="fixed_future", time_end=NOW + 30 * DAY, poll_interval_minutes=60)


def test_a_time_without_a_timezone_is_refused():
    """the platform runs on UTC, and a bare time could mean any zone"""
    with pytest.raises(ValidationError, match="must include a timezone"):
        workflow(time_mode="historical", time_start=datetime(2026, 9, 1), time_end=datetime(2026, 9, 5))


def test_times_in_another_zone_are_stored_as_utc():
    ist = timezone(timedelta(hours=5, minutes=30))
    w = workflow(time_mode="historical", time_start=datetime(2026, 9, 1, 5, 30, tzinfo=ist), time_end=datetime(2026, 9, 5, tzinfo=ist))
    assert w.time_start == datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    assert w.time_start.tzinfo == timezone.utc
