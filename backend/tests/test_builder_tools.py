import httpx
import pytest

from builder.catalogue import Catalogue
from builder.places import NominatimPlaces, Place, RecordedPlaces
from builder.tools import Toolbox
from evals.runner import EVALS_DIR

CATALOGUE = Catalogue.from_file(EVALS_DIR / "fixtures" / "catalogue.json")
PLACES = RecordedPlaces(EVALS_DIR / "fixtures" / "places")


def toolbox() -> Toolbox:
    return Toolbox(CATALOGUE, PLACES)


def test_temperature_needs_a_thermal_band_only_landsat_level_2_has():
    works = {c["slug"]: c["works_with_model"] for c in toolbox().list_collections("lst-detector")["collections"]}
    assert works == {"sentinel-2-l2a": False, "landsat-c2-l2": True, "landsat-c2-l1": False}


def test_a_collection_that_does_not_work_says_why():
    [sentinel] = [c for c in toolbox().list_collections("lst-detector")["collections"] if c["slug"] == "sentinel-2-l2a"]
    assert "thermal1" in sentinel["why_not"]


def test_an_unknown_model_points_back_at_list_models():
    assert "list_models" in toolbox().list_collections("vegetation")["error"]


def test_every_registered_model_is_listed():
    assert {m["slug"] for m in toolbox().list_models()["models"]} == {"ndwi-water-detector", "lst-detector", "ship-counter"}


def test_found_places_get_short_ids_that_stay_unique_across_lookups():
    tools = toolbox()
    first = tools.find_place("Dhaka")["places"]
    second = tools.find_place("Springfield")["places"]
    ids = [p["place_id"] for p in first + second]
    assert len(ids) == len(set(ids)) == len(tools.found)
    assert tools.found[ids[0]].name.startswith("Dhaka")


def test_a_continent_is_flagged_as_too_large():
    [africa] = toolbox().find_place("Africa")["places"]
    assert africa["too_large"] is True


def test_a_city_is_not():
    assert toolbox().find_place("Dhaka, Bangladesh")["places"][0]["too_large"] is False


def test_a_failed_lookup_is_reported_to_the_model_not_raised():
    class Down:
        def search(self, query):
            raise httpx.ConnectError("offline")

    assert "lookup failed" in Toolbox(CATALOGUE, Down()).find_place("Dhaka")["error"]


def test_a_made_up_tool_or_bad_arguments_come_back_as_errors():
    tools = toolbox()
    assert "no tool" in tools.call("delete_everything", {})["error"]
    assert "wrong arguments" in tools.call("find_place", {"place": "Dhaka"})["error"]


def test_a_recording_matches_the_same_place_typed_differently():
    assert PLACES.search("Dhaka")[0].name == PLACES.search("Dhaka, Bangladesh")[0].name
    assert PLACES.search("CHILIKA LAKE")
    assert PLACES.search("Upper Lake Bhopal")[0].name.startswith("Upper Lake")
    assert PLACES.search("the Rann of Kutch")
    assert PLACES.search("Atlantis") == []


def test_a_description_rather_than_a_name_finds_nothing_as_a_geocoder_would():
    assert PLACES.search("lakes near Pune") == []


def test_the_closest_recording_wins():
    assert PLACES.search("India")[0].kind == "country"


def test_a_bounding_box_area_is_roughly_right():
    """one degree square on the equator is about 111 km a side"""
    assert Place("equator", "test", (0.0, 0.0, 1.0, 1.0)).area_km2 == pytest.approx(12_309, rel=0.01)


def test_nominatim_answers_are_parsed_and_asked_for_only_once():
    asked = []

    def server(request):
        asked.append(request.url.params["q"])
        return httpx.Response(200, json=[{"display_name": "Dhaka, Bangladesh", "addresstype": "city", "boundingbox": ["23.6", "23.9", "90.2", "90.5"]}])

    places = NominatimPlaces(transport=httpx.MockTransport(server))
    [dhaka] = places.search("Dhaka")
    places.search("dhaka ")
    assert dhaka.bbox == (90.2, 23.6, 90.5, 23.9), "reordered from south, north, west, east"
    assert asked == ["Dhaka"]


def test_same_named_places_far_apart_are_told_apart_from_one_place_at_several_sizes():
    assert "different_places_with_this_name" in toolbox().find_place("Portland")
    assert "different_places_with_this_name" not in toolbox().find_place("Dhaka, Bangladesh"), "Dhaka's city, district and division overlap"


def test_an_obscure_namesake_does_not_make_a_name_ambiguous():
    first = Place("Cairo, Egypt", "city", (31.0, 29.9, 31.5, 30.2), importance=0.75)
    namesake = Place("Cairo, Illinois", "city", (-89.2, 36.9, -89.1, 37.1), importance=0.3)
    rival = Place("Cairo, Georgia", "city", (-84.3, 30.8, -84.1, 30.9), importance=0.7)
    from builder.places import distinct_places

    assert distinct_places([first, namesake]) == [first]
    assert distinct_places([first, namesake, rival]) == [first, rival]


def test_a_place_that_is_not_found_suggests_a_shorter_query():
    assert "only the place's name" in toolbox().find_place("the lakes near Atlantis")["note"]


def test_a_name_wrapped_in_other_words_is_found_by_its_capitalised_part():
    result = toolbox().find_place("port of Rotterdam")
    assert result["places"][0]["name"].startswith("Rotterdam")
    assert "'Rotterdam'" in result["matched"], "the model is told which name the matches are for"
    assert toolbox().find_place("lakes near Pune")["places"], "a description ending in a name finds the name"


def test_lowercase_words_never_start_a_retry():
    tools = toolbox()
    assert tools.find_place("my farm near the river")["places"] == []
    assert tools.last_found == []


def test_a_place_found_as_typed_says_nothing_about_matching():
    assert "matched" not in toolbox().find_place("Rotterdam, Netherlands")


def test_one_place_at_several_sizes_is_said_to_be_one_place():
    assert "same place at different sizes" in toolbox().find_place("Delhi, India")["note"]
