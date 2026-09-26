from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from builder.agent import build
from builder.catalogue import Catalogue
from builder.estimate import ArchiveEstimator, Estimate, can_estimate
from builder.places import RecordedPlaces
from domain.storage import bbox_area_km2, format_bytes, staged_bytes
from evals.runner import EVALS_DIR
from evals.suites.builder import pinned_today
from llm import FakeClient, Reply, ToolCall

CATALOGUE = Catalogue.from_file(EVALS_DIR / "fixtures" / "catalogue.json")
PLACES = RecordedPlaces(EVALS_DIR / "fixtures" / "places")
ASK = [{"role": "user", "content": "Monitor water in Dhaka for 2024"}]
GB = 1024**3


@pytest.fixture(autouse=True)
def today():
    with pinned_today():
        yield


class Fixed:
    """an estimator that answers with what it's given, and remembers the draft it was asked about"""

    def __init__(self, estimate: Estimate | None = None, fails: bool = False):
        self.result, self.fails, self.asked = estimate, fails, []

    def estimate(self, draft, now):
        self.asked.append(draft)
        if self.fails:
            raise ConnectionError("archive unreachable")
        return self.result


def estimate(staged_gb: float, free_gb: float = 100, scenes: int = 40, capped: bool = False) -> Estimate:
    return Estimate(scenes=scenes, staged_bytes=int(staged_gb * GB), free_bytes=int(free_gb * GB), capped=capped)


def draft_for(estimator, **answer) -> "Outcome":
    replies = [
        Reply("", tool_calls=[ToolCall("find_place", {"query": "Dhaka, Bangladesh"})]),
        Reply(
            "",
            tool_calls=[
                ToolCall(
                    "answer",
                    {
                        "kind": "draft",
                        "place_id": "place_1",
                        "time_mode": "historical",
                        "time_start": "2024-01-01",
                        "time_end": "2024-12-31",
                        "model_slug": "ndwi-water-detector",
                        "collection_slugs": [],
                        "message": "Water over Dhaka for 2024.",
                        **answer,
                    },
                )
            ],
        ),
    ]
    return build(ASK, FakeClient(replies), CATALOGUE, PLACES, estimator=estimator)


def test_a_draft_that_fits_carries_its_estimate_and_no_warning():
    outcome = draft_for(Fixed(estimate(staged_gb=2)))
    assert outcome.kind == "draft"
    assert (outcome.estimate["scenes"], outcome.estimate["verdict"]) == (40, "fits")
    assert outcome.warnings == []


def test_a_draft_taking_a_large_share_of_the_disk_is_drafted_with_that_verdict():
    """the form shows the verdict next to Create, so it isn't repeated as a warning"""
    outcome = draft_for(Fixed(estimate(staged_gb=20, free_gb=100)))
    assert outcome.kind == "draft"
    assert outcome.estimate["verdict"] == "large"
    assert outcome.warnings == []


def test_a_draft_that_would_fill_the_disk_is_refused_with_the_numbers():
    outcome = draft_for(Fixed(estimate(staged_gb=60, free_gb=100, scenes=900, capped=True)))
    assert (outcome.kind, outcome.draft, outcome.repairs) == ("cannot", None, 0)
    assert "at least 60.0 GB of storage, more than half of the 100.0 GB free" in outcome.message
    assert outcome.stopped_at == "storage"


def test_a_refusal_counted_in_full_gives_the_exact_figures():
    outcome = draft_for(Fixed(estimate(staged_gb=60, free_gb=100, scenes=900)))
    assert "about 60.0 GB of storage, more than half of the 100.0 GB free" in outcome.message


def test_an_archive_that_is_down_costs_the_estimate_not_the_draft():
    outcome = draft_for(Fixed(fails=True))
    assert outcome.kind == "draft"
    assert outcome.estimate is None
    assert "Couldn't estimate" in outcome.warnings[0]


def test_the_estimate_is_asked_about_the_payload_that_would_be_created():
    fixed = Fixed(estimate(staged_gb=1))
    draft_for(fixed)
    [asked] = fixed.asked
    assert asked["collection_slugs"] == ["sentinel-2-l2a", "landsat-c2-l2", "landsat-c2-l1"]
    assert asked["time_start"].startswith("2024-01-01")


def test_without_an_estimator_nothing_is_estimated():
    """the eval runs this way: it has no archive to search"""
    assert draft_for(None).estimate is None


def test_staged_size_is_scenes_times_rasters_times_pixels():
    # 100 km² at 10 m is a million pixels a raster; three float32 rasters for ten scenes
    assert staged_bytes(scenes=10, area_km2=100, resolution_m=10, rasters=3) == 10 * 3 * 1_000_000 * 4


def test_a_recurring_draft_is_never_estimated():
    fixed = Fixed(estimate(staged_gb=1))
    outcome = draft_for(fixed, time_mode="recurring", time_start=None, time_end="2026-12-31", poll_interval_minutes=1440)
    assert (outcome.kind, outcome.estimate, fixed.asked) == ("draft", None, [])


def test_only_a_historical_workflow_can_be_estimated():
    assert can_estimate({"time_mode": "historical"}) and not can_estimate({"time_mode": "recurring"})
    with pytest.raises(ValueError, match="only a historical"):
        ArchiveEstimator(session_factory=lambda: None).estimate({"time_mode": "recurring", "geometry": {}, "time_end": "2026-12-31"}, datetime(2026, 9, 14, tzinfo=timezone.utc))


def test_sizes_read_naturally():
    assert format_bytes(3 * GB + GB // 2) == "3.5 GB"
    assert format_bytes(512 * 1024**2) == "512.0 MB"
    assert format_bytes(10) == "under 1 MB"


def archive(monkeypatch, found_per_collection: dict[str, int], resolutions: dict[str, float], free_bytes: int):
    """an ArchiveEstimator over fake collections, recording the limit each search was given"""
    import importlib
    import shutil

    import domain.catalogue

    # by module path: the pipeline package re-exports a function named discover, which hides the module as an attribute
    discover = importlib.import_module("pipeline.discover")
    model = SimpleNamespace(requires=SimpleNamespace(bands=["green", "nir"], max_cloud_cover=30.0, gsd_m=None), rasters=["ndwi"])
    collections = {slug: SimpleNamespace(slug=slug, resolution_m=r) for slug, r in resolutions.items()}
    searches = []

    def search(provider, collection, area, start, end, max_cloud, max_items=discover.MAX_SCENES):
        searches.append((collection.slug, max_cloud, max_items))
        return [{}] * min(found_per_collection[collection.slug], max_items)

    monkeypatch.setattr(domain.catalogue, "get_model", lambda db, slug: model)
    monkeypatch.setattr(domain.catalogue, "get_collection", lambda db, slug: (None, collections[slug]))
    monkeypatch.setattr(discover, "search_stac", search)
    monkeypatch.setattr(shutil, "disk_usage", lambda path: SimpleNamespace(free=free_bytes))
    import domain.storage

    monkeypatch.setattr(domain.storage.shutil, "disk_usage", lambda path: SimpleNamespace(free=free_bytes))

    @contextmanager
    def no_database():
        yield None

    return ArchiveEstimator(session_factory=no_database, scratch="/scratch"), searches, discover


SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [0.1, 0], [0.1, 0.1], [0, 0.1], [0, 0]]]}


def a_draft(collections: list[str]) -> dict:
    return {
        "geometry": SQUARE,
        "time_mode": "historical",
        "time_start": "2024-01-01T00:00:00+00:00",
        "time_end": "2024-12-31T00:00:00+00:00",
        "collection_slugs": collections,
        "models": [{"model_slug": "ndwi"}],
    }


def test_a_draft_under_the_limit_is_counted_exactly_with_discovery_s_search(monkeypatch):
    estimator, searches, _ = archive(monkeypatch, {"fine": 5, "coarse": 7}, {"fine": 10.0, "coarse": 30.0}, free_bytes=1000 * GB)
    result = estimator.estimate(a_draft(["fine", "coarse"]), datetime.now(timezone.utc))

    area = bbox_area_km2((0, 0, 0.1, 0.1))
    assert result.scenes == 12
    assert result.staged_bytes == 5 * staged_bytes(1, area, 10.0, 3) + 7 * staged_bytes(1, area, 30.0, 3)
    assert result.capped is False
    assert result.input_bytes + result.result_bytes == result.staged_bytes
    assert result.input_bytes == 2 * result.result_bytes, "two bands for every derived raster, on the same grid"
    assert [cloud for _, cloud, _ in searches] == [30.0, 30.0], "searched with the model's cloud limit, as discovery would"


def test_a_huge_draft_stops_counting_once_it_is_over_the_limit(monkeypatch):
    """with 10 GB free the limit is 5 GB, so counting stops at the first scene past it instead of paging on"""
    estimator, searches, discover = archive(monkeypatch, {"fine": 5000, "coarse": 5000}, {"fine": 10.0, "coarse": 30.0}, free_bytes=10 * GB)
    result = estimator.estimate(a_draft(["fine", "coarse"]), datetime.now(timezone.utc))

    per_scene = staged_bytes(1, bbox_area_km2((0, 0, 0.1, 0.1)), 10.0, 3)
    [(slug, _, max_items)] = searches
    assert slug == "fine", "the second collection can't change the verdict, so it isn't searched"
    assert max_items == int(5 * GB // per_scene) + 1 < discover.MAX_SCENES, "just enough scenes to cross the limit"
    assert result.staged_bytes > 5 * GB
    assert result.capped is True


def test_the_count_never_asks_for_more_than_discovery_would_take(monkeypatch):
    estimator, searches, discover = archive(monkeypatch, {"fine": 3}, {"fine": 10.0}, free_bytes=10**15)
    estimator.estimate(a_draft(["fine"]), datetime.now(timezone.utc))
    assert searches[0][2] == discover.MAX_SCENES


def test_scenes_that_only_overlap_part_of_the_area_are_counted_on_in_growing_batches(monkeypatch):
    """small overlaps don't cross the limit in the first few scenes, so it counts further, a batch at a time"""
    from shapely.geometry import box, mapping

    estimator, searches, discover = archive(monkeypatch, {"fine": 5000}, {"fine": 10.0}, free_bytes=10 * GB)
    sliver = mapping(box(0, 0, 0.01, 0.01))  # a hundredth of the square on each side

    import importlib

    module = importlib.import_module("pipeline.discover")
    original = module.search_stac

    def search(provider, collection, area, start, end, max_cloud, max_items=module.MAX_SCENES):
        return [{"geometry": sliver} for _ in original(provider, collection, area, start, end, max_cloud, max_items=max_items)]

    monkeypatch.setattr(module, "search_stac", search)
    result = estimator.estimate(a_draft(["fine"]), datetime.now(timezone.utc))

    limits = [limit for _, _, limit in searches]
    assert limits[1:] == [min(discover.MAX_SCENES, limit * 8) for limit in limits[:-1]], "each recount is eight times larger"
    assert limits[-1] == discover.MAX_SCENES and result.capped, "slivers never cross the limit, so it counts as far as discovery would"
    assert result.verdict == "fits"
