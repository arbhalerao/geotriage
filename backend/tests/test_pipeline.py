from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core.db.models.enums import Severity, WorkflowStatus
from core.db.models.thresholds import ThresholdConfig
from core.db.models.workflow import Workflow
from pipeline.discover import cloud_ceiling
from pipeline.finalize import is_due, workflow_status
from pipeline.score import apply_threshold, severity_rank, worst_severity


def thresholds(**kwargs) -> ThresholdConfig:
    base = dict(green_min=0.3, green_max=1.0, yellow_min=0.0, yellow_max=0.3)
    return ThresholdConfig(**{**base, **kwargs})


def test_value_inside_the_green_band_is_green():
    assert apply_threshold(0.5, thresholds()) == Severity.green


def test_value_inside_the_yellow_band_is_yellow():
    assert apply_threshold(0.1, thresholds()) == Severity.yellow


def test_value_in_neither_band_falls_through_to_red():
    assert apply_threshold(-0.5, thresholds()) == Severity.red


def test_overlapping_band_edges_resolve_to_green():
    """green and yellow both contain 0.3; green is tested first and wins"""
    assert apply_threshold(0.3, thresholds()) == Severity.green


def test_value_beyond_every_declared_band_is_red():
    """nothing declares 99.0, and red is the fall-through, so it lands there"""
    assert apply_threshold(99.0, thresholds()) == Severity.red


def test_severity_ranks_ascend_from_green_to_red():
    assert severity_rank("green") < severity_rank("yellow") < severity_rank("red")


def test_unknown_severity_ranks_below_everything():
    assert severity_rank(None) < severity_rank("green")
    assert severity_rank("") < severity_rank("green")


def test_worst_severity_wins():
    assert worst_severity(["green", "red", "yellow"]) == "red"
    assert worst_severity(["green", "yellow"]) == "yellow"
    assert worst_severity(["green"]) == "green"


def test_worst_severity_of_nothing_is_none():
    assert worst_severity([]) is None


def test_a_workflow_with_no_scenes_failed():
    assert workflow_status(total=0, failed=0) == WorkflowStatus.failed


def test_every_scene_failing_fails_the_workflow():
    assert workflow_status(total=5, failed=5) == WorkflowStatus.failed


def test_some_scenes_failing_completes_with_errors():
    assert workflow_status(total=5, failed=2) == WorkflowStatus.completed_with_errors


def test_no_failures_completes_cleanly():
    assert workflow_status(total=5, failed=0) == WorkflowStatus.completed


def test_a_workflow_never_checked_is_due():
    assert is_due(Workflow(poll_interval_minutes=60, last_checked_at=None), datetime.now(timezone.utc))


def test_a_workflow_checked_recently_is_not_due():
    now = datetime.now(timezone.utc)
    workflow = Workflow(poll_interval_minutes=60, last_checked_at=now - timedelta(minutes=10))
    assert not is_due(workflow, now)


def test_a_workflow_past_its_interval_is_due():
    now = datetime.now(timezone.utc)
    workflow = Workflow(poll_interval_minutes=60, last_checked_at=now - timedelta(minutes=61))
    assert is_due(workflow, now)


def test_the_interval_boundary_counts_as_due():
    now = datetime.now(timezone.utc)
    workflow = Workflow(poll_interval_minutes=60, last_checked_at=now - timedelta(minutes=60))
    assert is_due(workflow, now)


class _FakeModel:
    """just the one declaration cloud_ceiling reads"""

    def __init__(self, max_cloud_cover):
        self.requires = SimpleNamespace(max_cloud_cover=max_cloud_cover)


def test_cloud_ceiling_takes_the_strictest_model():
    # one model allows 30%, another 20% — the scene has to satisfy both
    assert cloud_ceiling([_FakeModel(30.0), _FakeModel(20.0)]) == pytest.approx(20.0)


def test_cloud_ceiling_of_one_model_is_its_own_limit():
    assert cloud_ceiling([_FakeModel(30.0)]) == pytest.approx(30.0)


def test_cloud_ceiling_with_no_models_is_unset():
    assert cloud_ceiling([]) is None


def test_a_model_that_does_not_care_about_cloud_does_not_set_a_ceiling():
    assert cloud_ceiling([_FakeModel(None), _FakeModel(None)]) is None


def test_a_model_without_a_limit_does_not_relax_another_model_s():
    assert cloud_ceiling([_FakeModel(20.0), _FakeModel(None)]) == pytest.approx(20.0)
