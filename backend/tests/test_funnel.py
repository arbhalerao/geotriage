import pytest
from geotriage import Model, Prefilter, Requires, Score, Thresholds, check_model

from pipeline.stage import pick_overview


#
# a COG carries pre-decimated copies of itself
# picking the coarsest one that still satisfies the caller is where the bandwidth saving comes from

SENTINEL2_OVERVIEWS = [2, 4, 8, 16, 32]


def test_native_resolution_when_nothing_is_asked_for():
    assert pick_overview(10.0, SENTINEL2_OVERVIEWS, None) is None


def test_picks_the_coarsest_overview_that_still_satisfies_the_target():
    # 10 m native; level index 3 is decimation 16 -> 160 m, index 4 is 320 m
    assert pick_overview(10.0, SENTINEL2_OVERVIEWS, 160.0) == 3
    assert pick_overview(10.0, SENTINEL2_OVERVIEWS, 320.0) == 4


def test_a_target_finer_than_every_overview_reads_full_resolution():
    assert pick_overview(10.0, SENTINEL2_OVERVIEWS, 15.0) is None


def test_a_target_coarser_than_every_overview_takes_the_coarsest():
    assert pick_overview(10.0, SENTINEL2_OVERVIEWS, 10_000.0) == 4


def test_a_file_with_no_overviews_reads_full_resolution():
    assert pick_overview(10.0, [], 160.0) is None


def test_unknown_native_resolution_reads_full_resolution():
    """better to move too many bytes than to silently score the wrong pixels"""
    assert pick_overview(0.0, SENTINEL2_OVERVIEWS, 160.0) is None


def test_the_saving_is_the_square_of_the_decimation():
    """160 m from 10 m is decimation 16, so ~1/256th of the pixels"""
    level = pick_overview(10.0, SENTINEL2_OVERVIEWS, 160.0)
    assert SENTINEL2_OVERVIEWS[level] ** 2 == 256


def a_gated_model(implement_screen: bool) -> Model:
    class Gated(Model):
        slug = "gated"
        name = "Gated"
        requires = Requires(bands=["green", "nir"], gsd_m=None)
        prefilter = Prefilter(bands=["green"], gsd_m=160.0)
        scores = {"s": Score(primary=True, thresholds=Thresholds((0, 1), (1, 2)))}

        def run(self, bands):
            return {"s": 1.0}

    if implement_screen:
        Gated.screen = lambda self, bands: True
    return Gated()


def test_a_declared_prefilter_without_screen_is_refused():
    """otherwise the gate silently passes every scene, which is worse than no gate"""
    problems = check_model(a_gated_model(implement_screen=False))
    assert any("screen()" in p for p in problems)


def test_a_declared_prefilter_with_screen_is_conformant():
    assert check_model(a_gated_model(implement_screen=True)) == []


def test_a_prefilter_needs_a_positive_resolution():
    model = a_gated_model(implement_screen=True)
    model.prefilter = Prefilter(bands=["green"], gsd_m=0.0)
    assert any("gsd_m" in p for p in check_model(model))


def test_a_prefilter_needs_bands():
    model = a_gated_model(implement_screen=True)
    model.prefilter = Prefilter(bands=[], gsd_m=160.0)
    assert any("bands" in p for p in check_model(model))


def test_requires_defaults_to_native_resolution():
    assert Requires(bands=["green"]).gsd_m is None


def test_a_model_can_declare_it_does_not_need_full_resolution():
    assert Requires(bands=["green"], gsd_m=60.0).gsd_m == pytest.approx(60.0)


def test_cost_defaults_to_medium():
    assert Requires(bands=["green"]).cost == "medium"
