import uuid
from types import SimpleNamespace

import pytest

import pipeline.cleanup as cleanup
from core.db.models.enums import ImageryKept, Severity, StoragePolicy, WorkflowItemStatus
from domain.storage import imagery_to_keep

EVERY = "inputs_and_results"


@pytest.mark.parametrize(
    "policy, alert, caution, normal",
    [
        ("everything", EVERY, EVERY, EVERY),
        ("alert_and_caution_in_full", EVERY, EVERY, "results"),
        ("alert_in_full", EVERY, "results", "results"),
        ("results_only", "results", "results", "results"),
        ("scores_only", "none", "none", "none"),
    ],
)
def test_each_policy_keeps_what_its_row_says(policy, alert, caution, normal):
    assert [imagery_to_keep(policy, severity, scored=True) for severity in ("red", "yellow", "green")] == [alert, caution, normal]


def test_a_scene_that_wasn_t_scored_keeps_nothing_except_under_everything():
    assert imagery_to_keep("alert_and_caution_in_full", None, scored=False) == "none"
    assert imagery_to_keep("results_only", None, scored=False) == "none"
    assert imagery_to_keep("everything", None, scored=False) == EVERY


def test_every_policy_is_covered():
    for policy in StoragePolicy:
        imagery_to_keep(policy.value, "red", scored=True)


class Db:
    def __init__(self, policy):
        self.workflow = SimpleNamespace(storage_policy=StoragePolicy(policy))

    def get(self, _model, _id):
        return self.workflow


def a_scene(severity, status=WorkflowItemStatus.processed):
    return SimpleNamespace(id=uuid.uuid4(), workflow_id=uuid.uuid4(), overall_severity=Severity(severity) if severity else None, status=status, imagery_kept=None)


@pytest.fixture
def deleted(monkeypatch):
    removed = []
    monkeypatch.setattr(cleanup, "layer_names", lambda db, item: ({"green", "nir"}, {"ndwi"}))
    monkeypatch.setattr(cleanup.store, "delete_keys", lambda keys: removed.extend(keys))
    return removed


def names(keys):
    return sorted(key.rsplit("/", 1)[1].removesuffix(".tif") for key in keys)


def test_a_normal_scene_under_the_default_policy_loses_its_inputs_and_keeps_its_results(deleted):
    scene = a_scene("green")
    cleanup.apply_storage_policy(Db("alert_and_caution_in_full"), scene)
    assert names(deleted) == ["green", "nir"]
    assert scene.imagery_kept == ImageryKept.results


def test_an_alert_scene_under_the_default_policy_keeps_everything(deleted):
    scene = a_scene("red")
    cleanup.apply_storage_policy(Db("alert_and_caution_in_full"), scene)
    assert deleted == []
    assert scene.imagery_kept == ImageryKept.inputs_and_results


def test_scores_only_deletes_inputs_and_results_alike(deleted):
    scene = a_scene("red")
    cleanup.apply_storage_policy(Db("scores_only"), scene)
    assert names(deleted) == ["green", "ndwi", "nir"]
    assert scene.imagery_kept == ImageryKept.none


def test_a_failed_scene_s_partial_files_go(deleted):
    scene = a_scene(None, status=WorkflowItemStatus.fetch_failed)
    cleanup.apply_storage_policy(Db("results_only"), scene)
    assert names(deleted) == ["green", "ndwi", "nir"]


def test_a_scene_already_applied_is_left_alone(deleted):
    scene = a_scene("green")
    scene.imagery_kept = ImageryKept.results
    cleanup.apply_storage_policy(Db("scores_only"), scene)
    assert deleted == []


def test_a_cleanup_that_fails_mid_scoring_is_rolled_back_and_left_for_finalize(monkeypatch):
    calls = []

    class Session:
        def commit(self):
            calls.append("commit")

        def rollback(self):
            calls.append("rollback")

    def boom(db, item):
        raise ConnectionError("storage unreachable")

    monkeypatch.setattr(cleanup, "apply_storage_policy", boom)
    cleanup.apply_storage_policy_quietly(Session(), a_scene("green"))
    assert calls == ["rollback"]
