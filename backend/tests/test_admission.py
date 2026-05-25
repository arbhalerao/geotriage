import numpy as np
import pytest

from domain import images
from runners.docker import ImageError

MODEL_DESCRIPTOR = {
    "descriptor_version": 1,
    "kind": "model",
    "slug": "ndwi-water",
    "name": "NDWI Water",
    "description": "",
    "requires": {"bands": ["green", "nir"], "max_cloud_cover": 30.0, "gsd_m": None, "cost": "medium"},
    "prefilter": None,
    "scores": {
        "ndwi_mean": {
            "description": "",
            "unit": "index",
            "range": [-1.0, 1.0],
            "primary": True,
            "thresholds": {"green": [0.3, 1.0], "yellow": [0.0, 0.3]},
        }
    },
    "rasters": [],
}

PROVIDER_DESCRIPTOR = {
    "descriptor_version": 1,
    "kind": "provider",
    "slug": "acme",
    "name": "ACME",
    "stac_api_url": "https://stac.acme.test/v1",
    "auth": "NoAuth",
    "collections": {
        "acme-l2": {
            "slug": "acme-l2",
            "display_name": "ACME L2",
            "description": "",
            "processing_level": "SR",
            "sensor_type": "multispectral",
            "resolution_m": 10.0,
            "cloud_cover_property": "eo:cloud_cover",
            "bands": [{"normalized_name": "green", "asset_key": "B03", "description": "", "scale": 0.0001, "offset": 0.0}],
        }
    },
}


class FakeRunner:
    """
    stands in for a container

    `describe` and `run` either return a canned answer or raise ImageError,
    which is exactly the surface DockerRunner presents to the gate
    """

    def __init__(self, descriptor=None, scores=None, describe_error=None, run_error=None, screen_error=None):
        self._descriptor = descriptor
        self._scores = scores
        self._describe_error = describe_error
        self._run_error = run_error
        self._screen_error = screen_error
        self.calls: list[str] = []

    def describe(self):
        self.calls.append("describe")
        if self._describe_error:
            raise ImageError(self._describe_error)
        return self._descriptor

    def run(self, bands, raster_dir=None):
        self.calls.append("run")
        if self._run_error:
            raise ImageError(self._run_error)
        assert isinstance(bands.green, np.ndarray), "the gate must hand the image real arrays"
        return {"scores": self._scores, "metadata": {}, "rasters": {}}

    def screen(self, bands):
        self.calls.append("screen")
        if self._screen_error:
            raise ImageError(self._screen_error)
        return True


@pytest.fixture
def runner(monkeypatch):
    holder = {}

    def install(fake):
        holder["fake"] = fake
        monkeypatch.setattr(images, "DockerRunner", lambda image: fake)
        return fake

    return install


def test_a_conformant_model_passes_every_stage(runner):
    fake = runner(FakeRunner(MODEL_DESCRIPTOR, scores={"ndwi_mean": 0.4}))
    verdict = images.admit("acme/ndwi:1.0", "model")

    assert verdict.ok
    assert verdict.descriptor["slug"] == "ndwi-water"
    assert [name for name, _, _ in verdict.checks] == ["describe", "declarations", "smoke run"]
    assert all(passed for _, passed, _ in verdict.checks)
    assert fake.calls == ["describe", "run"]


def test_an_image_that_cannot_describe_itself_stops_at_the_first_stage(runner):
    fake = runner(FakeRunner(describe_error="no geotriage entrypoint"))
    verdict = images.admit("alpine:latest", "model")

    assert not verdict.ok
    assert [name for name, _, _ in verdict.checks] == ["describe"]
    assert "no geotriage entrypoint" in verdict.problems[0]
    assert fake.calls == ["describe"], "nothing is run after describe fails"


def test_incoherent_declarations_stop_before_the_smoke_run(runner):
    broken = {**MODEL_DESCRIPTOR, "requires": {**MODEL_DESCRIPTOR["requires"], "bands": ["green", "green"]}}
    fake = runner(FakeRunner(broken))
    verdict = images.admit("acme/broken:1.0", "model")

    assert not verdict.ok
    assert [name for name, _, _ in verdict.checks] == ["describe", "declarations"]
    assert any("duplicate" in p for p in verdict.problems)
    assert "run" not in fake.calls, "a malformed image is never executed"


def test_registering_a_provider_image_as_a_model_is_refused(runner):
    runner(FakeRunner(PROVIDER_DESCRIPTOR))
    verdict = images.admit("acme/archive:1.0", "model")

    assert not verdict.ok
    assert any("'provider'" in p and "'model'" in p for p in verdict.problems), verdict.problems


def test_a_provider_is_admitted_without_a_smoke_run(runner):
    """a provider's equivalent is `geotriage verify`, which needs its live archive"""
    fake = runner(FakeRunner(PROVIDER_DESCRIPTOR))
    verdict = images.admit("acme/archive:1.0", "provider")

    assert verdict.ok
    assert [name for name, _, _ in verdict.checks] == ["describe", "declarations"]
    assert fake.calls == ["describe"]


def test_smoke_false_answers_without_touching_the_raster_stack(runner):
    """the API uses this so a registration form gets an immediate verdict"""
    fake = runner(FakeRunner(MODEL_DESCRIPTOR, scores={"ndwi_mean": 0.4}))
    verdict = images.admit("acme/ndwi:1.0", "model", smoke=False)

    assert verdict.ok
    assert [name for name, _, _ in verdict.checks] == ["describe", "declarations"]
    assert fake.calls == ["describe"]


def test_an_image_that_cannot_score_is_refused(runner):
    runner(FakeRunner(MODEL_DESCRIPTOR, run_error="ValueError: no"))
    verdict = images.admit("acme/ndwi:1.0", "model")

    assert not verdict.ok
    assert ("smoke run", False) in [(n, p) for n, p, _ in verdict.checks]
    assert any("synthetic scene" in p for p in verdict.problems)


def test_an_image_that_withholds_a_declared_score_is_refused(runner):
    """declaring a score and not returning it is the failure the contract exists to catch"""
    runner(FakeRunner(MODEL_DESCRIPTOR, scores={"ndwi_men": 0.4}))
    verdict = images.admit("acme/typo:1.0", "model")

    assert not verdict.ok
    assert any("ndwi_mean" in p for p in verdict.problems), verdict.problems


def test_a_declared_prefilter_is_smoke_screened_too(runner):
    gated = {**MODEL_DESCRIPTOR, "prefilter": {"bands": ["green"], "gsd_m": 300.0}}
    fake = runner(FakeRunner(gated, scores={"ndwi_mean": 0.4}))
    verdict = images.admit("acme/gated:1.0", "model")

    assert verdict.ok
    assert fake.calls == ["describe", "run", "screen"]
    assert "smoke screen" in [n for n, _, _ in verdict.checks]


def test_a_prefilter_that_raises_is_refused(runner):
    gated = {**MODEL_DESCRIPTOR, "prefilter": {"bands": ["green"], "gsd_m": 300.0}}
    runner(FakeRunner(gated, scores={"ndwi_mean": 0.4}, screen_error="boom"))
    verdict = images.admit("acme/gated:1.0", "model")

    assert not verdict.ok
    assert any("prefilter" in p for p in verdict.problems), verdict.problems


def test_the_synthetic_scene_carries_every_declared_band():
    bands = images._synthetic_bands(MODEL_DESCRIPTOR)
    assert bands.names == ["green", "nir"]
    assert bands.shape == images.SMOKE_SHAPE
    assert bands.green.valid_count == images.SMOKE_SHAPE[0] * images.SMOKE_SHAPE[1]
