from types import SimpleNamespace

import pytest

import pipeline.storage as storage
from domain.storage import bbox_area_km2, staged_bytes, verdict

GB = 1024**3


def model(bands, rasters=(), gsd=None):
    return SimpleNamespace(requires=SimpleNamespace(bands=list(bands), gsd_m=gsd), rasters=list(rasters))


def test_a_scene_stages_its_collection_s_bands_once_plus_every_model_s_rasters():
    water, extra = model(["green", "nir"], ["ndwi"]), model(["nir", "red"], ["ndvi"])
    bands, maps = storage.bytes_for_scenes({"s2": [100.0] * 10}, {"s2": 10.0}, {"s2": [water, extra]})
    assert (bands, maps) == (10 * staged_bytes(1, 100, 10.0, 3), 10 * staged_bytes(1, 100, 10.0, 2))


def test_scenes_in_a_collection_no_model_uses_stage_nothing():
    assert storage.bytes_for_scenes({"s2": [100.0] * 10}, {"s2": 10.0}, {}) == (0, 0)


def test_models_that_all_ask_for_a_coarser_grid_are_staged_from_an_overview():
    coarse = model(["thermal1"], gsd=100.0)
    assert storage.bytes_for_scenes({"l2": [100.0]}, {"l2": 30.0}, {"l2": [coarse]}) == (staged_bytes(1, 100, 100.0, 1), 0)


def test_each_scene_is_sized_by_where_it_overlaps_the_area():
    from shapely.geometry import box, mapping

    from domain.storage import clipped_area_km2

    area = box(0, 0, 4, 4)
    corner = mapping(box(3, 3, 5, 5))
    assert clipped_area_km2(corner, area) == pytest.approx(bbox_area_km2((3, 3, 4, 4)))
    assert clipped_area_km2(mapping(box(10, 10, 11, 11)), area) == 0.0
    assert clipped_area_km2(None, area) == pytest.approx(bbox_area_km2((0, 0, 4, 4))), "no footprint counts as all of it"


def planned(monkeypatch, bands_gb, maps_gb, scenes=900):
    monkeypatch.setattr(storage, "planned_bytes", lambda db, workflow_id, item_ids: (scenes, int(bands_gb * GB), int(maps_gb * GB)))


def test_a_run_needing_over_half_the_free_working_space_stops_with_the_numbers(monkeypatch):
    planned(monkeypatch, bands_gb=50, maps_gb=10)
    with pytest.raises(storage.StorageLimitExceeded, match="about 60.0 GB of working space for 900 scenes, more than half of the 100.0 GB free"):
        storage.check_storage(None, "wf", ["item"], free=100 * GB, stored_free=1000 * GB, policy="everything")


def test_a_run_that_could_keep_over_half_of_storage_stops_even_with_room_to_work(monkeypatch):
    planned(monkeypatch, bands_gb=50, maps_gb=10)
    with pytest.raises(storage.StorageLimitExceeded, match="keep up to 60.0 GB from 900 scenes, more than half of the 100.0 GB free in storage"):
        storage.check_storage(None, "wf", ["item"], free=1000 * GB, stored_free=100 * GB, policy="alert_in_full")


def test_a_lighter_policy_is_checked_against_what_it_keeps(monkeypatch):
    planned(monkeypatch, bands_gb=50, maps_gb=10)
    storage.check_storage(None, "wf", ["item"], free=1000 * GB, stored_free=100 * GB, policy="results_only")
    storage.check_storage(None, "wf", ["item"], free=1000 * GB, stored_free=1 * GB, policy="scores_only")


def test_storage_that_can_t_say_its_free_space_skips_that_check(monkeypatch):
    planned(monkeypatch, bands_gb=50, maps_gb=10)
    monkeypatch.setattr("storage.client.free_bytes", lambda: None)
    storage.check_storage(None, "wf", ["item"], free=1000 * GB, policy="everything")


def test_a_run_that_fits_goes_ahead(monkeypatch):
    planned(monkeypatch, bands_gb=15, maps_gb=5, scenes=40)
    storage.check_storage(None, "wf", ["item"], free=100 * GB, stored_free=100 * GB, policy="everything")


def test_a_run_that_found_nothing_isn_t_checked(monkeypatch):
    def fail(*_args):
        raise AssertionError("nothing to size")

    monkeypatch.setattr(storage, "planned_bytes", fail)
    storage.check_storage(None, "wf", [], free=1)


def test_the_run_check_and_the_estimates_share_one_limit():
    assert verdict(51, 100) == "too_large" and verdict(11, 100) == "large" and verdict(10, 100) == "fits"
    assert bbox_area_km2((0, 0, 1, 1)) == pytest.approx(12_309, rel=0.01)
