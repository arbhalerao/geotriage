from domain.catalogue import collection_conflicts


def test_an_unclaimed_slug_is_free():
    assert collection_conflicts(["sentinel-2-l2a"], {}, "earth-search") == []


def test_a_slug_another_provider_owns_is_refused():
    owned = {"sentinel-2-l2a": "earth-search"}
    problems = collection_conflicts(["sentinel-2-l2a"], owned, "acme")

    assert len(problems) == 1
    assert "sentinel-2-l2a" in problems[0]
    assert "earth-search" in problems[0], "the error has to name who holds it"


def test_a_provider_keeps_its_own_slugs_when_it_re_registers():
    """re-registering under the same slug is how an author ships a new version"""
    owned = {"sentinel-2-l2a": "earth-search"}
    assert collection_conflicts(["sentinel-2-l2a"], owned, "earth-search") == []


def test_a_version_can_add_a_collection():
    owned = {"sentinel-2-l2a": "earth-search"}
    assert collection_conflicts(["sentinel-2-l2a", "sentinel-1-grd"], owned, "earth-search") == []


def test_a_version_can_drop_a_collection():
    owned = {"sentinel-2-l2a": "earth-search", "sentinel-1-grd": "earth-search"}
    assert collection_conflicts(["sentinel-2-l2a"], owned, "earth-search") == []


def test_every_conflicting_slug_is_reported_not_just_the_first():
    owned = {"landsat-c2-l1": "planetary-computer", "landsat-c2-l2": "planetary-computer"}
    problems = collection_conflicts(["landsat-c2-l1", "landsat-c2-l2", "acme-wv3"], owned, "acme")

    assert len(problems) == 2, "an author fixing one at a time is a bad loop"


def test_a_partial_overlap_still_refuses_the_whole_registration():
    owned = {"sentinel-2-l2a": "earth-search"}
    assert collection_conflicts(["acme-wv3", "sentinel-2-l2a"], owned, "acme")
