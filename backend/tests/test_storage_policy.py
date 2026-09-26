import os
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
def uploaded(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(cleanup.scratch, "SCENES", str(tmp_path))
    monkeypatch.setattr(cleanup, "layer_names", lambda db, item: ({"green", "nir"}, {"ndwi"}))
    monkeypatch.setattr(cleanup.store, "upload_file", lambda key, path: sent.append(key))
    return sent


def staged(scene, bands=("green", "nir"), maps=("ndwi",)):
    cleanup.scratch.ensure_dirs(scene.id)
    for name in bands:
        open(cleanup.scratch.band_path(scene.id, name), "wb").close()
    for name in maps:
        open(cleanup.scratch.map_path(scene.id, name), "wb").close()
    return scene


def names(keys):
    return sorted(key.rsplit("/", 1)[1].removesuffix(".tif") for key in keys)


def test_a_normal_scene_under_the_default_policy_uploads_only_its_maps(uploaded):
    scene = staged(a_scene("green"))
    cleanup.apply_storage_policy(Db("alert_and_caution_in_full"), scene)
    assert names(uploaded) == ["ndwi"], "its bands never travel to MinIO"
    assert scene.imagery_kept == ImageryKept.results


def test_an_alert_scene_under_the_default_policy_uploads_everything(uploaded):
    scene = staged(a_scene("red"))
    cleanup.apply_storage_policy(Db("alert_and_caution_in_full"), scene)
    assert names(uploaded) == ["green", "ndwi", "nir"]
    assert scene.imagery_kept == ImageryKept.inputs_and_results


def test_scores_only_uploads_nothing(uploaded):
    scene = staged(a_scene("red"))
    cleanup.apply_storage_policy(Db("scores_only"), scene)
    assert uploaded == []
    assert scene.imagery_kept == ImageryKept.none


def test_a_scene_that_failed_part_way_keeps_only_what_it_got_to(uploaded):
    scene = staged(a_scene(None, status=WorkflowItemStatus.fetch_failed), bands=("green",), maps=())
    cleanup.apply_storage_policy(Db("everything"), scene)
    assert names(uploaded) == ["green"]


def test_a_scene_already_applied_is_left_alone(uploaded):
    scene = staged(a_scene("red"))
    scene.imagery_kept = ImageryKept.results
    cleanup.apply_storage_policy(Db("everything"), scene)
    assert uploaded == []


def test_the_work_folder_goes_only_after_the_commit(uploaded):
    order = []
    scene = staged(a_scene("green"))

    class Session(Db):
        def commit(self):
            order.append(("commit", os.path.isdir(cleanup.scratch.scene_dir(scene.id))))

    cleanup.finish_scene(Session("alert_and_caution_in_full"), scene)
    assert order == [("commit", True)], "the files are still there when the commit happens"
    assert not os.path.exists(cleanup.scratch.scene_dir(scene.id))


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
    monkeypatch.setattr(cleanup.scratch, "remove_scene", lambda item_id: calls.append("removed"))
    cleanup.apply_storage_policy_quietly(Session(), a_scene("green"))
    assert calls == ["rollback"], "a scene whose upload failed keeps its work folder for finalize to try again"


def test_the_sweep_clears_settled_and_vanished_scenes_and_stale_job_folders_only(monkeypatch, tmp_path):
    import time

    import pipeline.scratch as scratch

    monkeypatch.setattr(scratch, "SCRATCH", str(tmp_path))
    monkeypatch.setattr(scratch, "SCENES", str(tmp_path / "scenes"))
    working, settled, vanished = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for item_id in (working, settled, vanished):
        scratch.ensure_dirs(item_id)
    (tmp_path / "run-job-old").mkdir()
    (tmp_path / "run-job-new").mkdir()
    old = time.time() - scratch.STALE_JOB_FOLDER_S - 60
    os.utime(tmp_path / "run-job-old", (old, old))

    class Result:
        def scalars(self):
            return [working]

    class Session:
        def execute(self, _query):
            return Result()

    assert scratch.sweep(Session()) == 3
    assert sorted(os.listdir(tmp_path / "scenes")) == [str(working)], "a scene still being worked on stays"
    assert sorted(p for p in os.listdir(tmp_path) if p.startswith("run-")) == ["run-job-new"]


def test_scratch_folders_reach_images_through_the_volume_by_name(monkeypatch):
    import runners.docker as docker

    monkeypatch.setattr(docker, "SCRATCH", "/run-scratch")
    monkeypatch.setattr(docker, "SCRATCH_VOLUME", "geotriage-run-scratch")
    assert docker.mount_args("/run-scratch/scenes/abc", "/job", "ro") == ["--mount", "type=volume,src=geotriage-run-scratch,dst=/job,volume-subpath=scenes/abc,readonly"]
    assert docker.mount_args("/run-scratch/scenes/abc/out-1", "/out", "rw") == ["--mount", "type=volume,src=geotriage-run-scratch,dst=/out,volume-subpath=scenes/abc/out-1"]


def test_without_a_volume_folders_are_mounted_by_their_own_path(monkeypatch):
    import runners.docker as docker

    monkeypatch.setattr(docker, "SCRATCH", "/tmp")
    monkeypatch.setattr(docker, "SCRATCH_VOLUME", None)
    assert docker.mount_args("/tmp/run-job-x", "/job", "ro") == ["-v", "/tmp/run-job-x:/job:ro"]
