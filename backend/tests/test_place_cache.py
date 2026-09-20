from datetime import datetime, timedelta, timezone

import httpx
import pytest

from builder.places import NominatimPlaces, lookup_key

DHAKA = [{"display_name": "Dhaka, Bangladesh", "addresstype": "city", "boundingbox": ["23.6", "23.9", "90.2", "90.5"], "importance": 0.65}]


class DictCache:
    def __init__(self, fail_get=False, fail_put=False):
        self.rows: dict[str, tuple[str, list[dict], datetime]] = {}
        self.fail_get, self.fail_put = fail_get, fail_put

    def get(self, key):
        if self.fail_get:
            raise RuntimeError("database went away")
        row = self.rows.get(key)
        return (row[1], row[2]) if row else None

    def put(self, key, query, candidates):
        if self.fail_put:
            raise RuntimeError("database went away")
        self.rows[key] = (query, candidates, datetime.now(timezone.utc))


def geocoder(answer=DHAKA):
    """a Nominatim that answers, and counts how often it was asked"""
    asked = []

    def server(request):
        asked.append(request.url.params["q"])
        return httpx.Response(200, json=answer)

    return httpx.MockTransport(server), asked


def unreachable():
    def server(request):
        raise AssertionError(f"OpenStreetMap was asked for {request.url.params['q']!r}, the cache should have answered")

    return httpx.MockTransport(server)


def test_a_place_looked_up_once_is_answered_from_the_cache_after_a_restart():
    cache = DictCache()
    transport, asked = geocoder()
    NominatimPlaces(cache=cache, transport=transport).search("Dhaka")

    # a new client stands in for a restarted worker: its memory is empty, the cache is not
    [dhaka] = NominatimPlaces(cache=cache, transport=unreachable()).search("Dhaka")
    assert dhaka.name == "Dhaka, Bangladesh"
    assert asked == ["Dhaka"]


def test_the_same_place_typed_differently_is_one_lookup():
    assert lookup_key("  Dhaka   Division ") == lookup_key("dhaka division") == "dhaka division"
    cache = DictCache()
    transport, asked = geocoder()
    NominatimPlaces(cache=cache, transport=transport).search("Dhaka ")
    NominatimPlaces(cache=cache, transport=unreachable()).search("DHAKA")
    assert asked == ["Dhaka "]


def test_what_was_asked_is_kept_with_the_answer():
    cache = DictCache()
    transport, _ = geocoder()
    NominatimPlaces(cache=cache, transport=transport).search("Dhaka, Bangladesh")
    query, candidates, _ = cache.rows["dhaka, bangladesh"]
    assert (query, candidates) == ("Dhaka, Bangladesh", DHAKA)


def test_an_answer_older_than_the_limit_is_looked_up_again_and_replaced():
    cache = DictCache()
    cache.rows["dhaka"] = ("Dhaka", [], datetime.now(timezone.utc) - timedelta(days=31))
    transport, asked = geocoder()
    [dhaka] = NominatimPlaces(cache=cache, max_age=timedelta(days=30), transport=transport).search("Dhaka")
    assert asked == ["Dhaka"]
    assert dhaka.name == "Dhaka, Bangladesh"
    assert cache.rows["dhaka"][1] == DHAKA


def test_an_unreadable_cache_falls_back_to_openstreetmap():
    transport, asked = geocoder()
    [dhaka] = NominatimPlaces(cache=DictCache(fail_get=True), transport=transport).search("Dhaka")
    assert dhaka.name == "Dhaka, Bangladesh" and asked == ["Dhaka"]


def test_an_unwritable_cache_still_returns_the_answer():
    transport, _ = geocoder()
    assert NominatimPlaces(cache=DictCache(fail_put=True), transport=transport).search("Dhaka")


def test_a_failed_lookup_is_not_cached():
    cache = DictCache()

    def down(request):
        return httpx.Response(503)

    with pytest.raises(httpx.HTTPStatusError):
        NominatimPlaces(cache=cache, transport=httpx.MockTransport(down)).search("Dhaka")
    assert cache.rows == {}


def test_nothing_found_is_remembered_too():
    """asking again for a place OpenStreetMap doesn't know would only spend the request budget"""
    cache = DictCache()
    transport, asked = geocoder(answer=[])
    assert NominatimPlaces(cache=cache, transport=transport).search("Atlantis") == []
    assert NominatimPlaces(cache=cache, transport=unreachable()).search("Atlantis") == []
    assert asked == ["Atlantis"]
