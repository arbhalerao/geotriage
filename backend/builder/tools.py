from builder.catalogue import Catalogue
from builder.guardrails import MAX_AREA_KM2
from builder.places import Place, Places, distinct_places
from llm import Tool

LIST_MODELS = Tool(
    name="list_models",
    description="List the detectors that can run on satellite scenes, with what each one measures.",
    parameters={"type": "object", "properties": {}},
)

LIST_COLLECTIONS = Tool(
    name="list_collections",
    description="List the satellite image collections, and whether each one works with the given detector.",
    parameters={
        "type": "object",
        "properties": {"model_slug": {"type": "string", "description": "a slug from list_models"}},
        "required": ["model_slug"],
    },
)

FIND_PLACE = Tool(
    name="find_place",
    description="Look up a place name. Returns up to 5 matches, each with a place_id to use in the draft.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "the place as the user named it, e.g. 'Dhaka, Bangladesh'"}},
        "required": ["query"],
    },
)


class Toolbox:
    definitions = (LIST_MODELS, LIST_COLLECTIONS, FIND_PLACE)

    def __init__(self, catalogue: Catalogue, places: Places):
        self.catalogue = catalogue
        self.places = places
        self.found: dict[str, Place] = {}
        # place_id -> every distinct place its lookup matched, for the ids whose name is ambiguous
        self.ambiguous: dict[str, list[Place]] = {}

    def call(self, name: str, arguments: dict) -> dict:
        handlers = {"list_models": self.list_models, "list_collections": self.list_collections, "find_place": self.find_place}
        if name not in handlers:
            return {"error": f"there is no tool called {name!r}, the tools are {', '.join(handlers)}"}
        try:
            return handlers[name](**arguments)
        except TypeError as exc:
            return {"error": f"wrong arguments for {name}: {exc}"}

    def list_models(self) -> dict:
        return {"models": [{"slug": m.slug, "name": m.name, "description": m.description} for m in self.catalogue.models.values()]}

    def list_collections(self, model_slug: str) -> dict:
        if model_slug not in self.catalogue.models:
            return {"error": f"no model {model_slug!r}, call list_models for the slugs"}
        collections = []
        for slug, collection in self.catalogue.collections.items():
            result = self.catalogue.compatibility(model_slug, slug)
            entry = {"slug": slug, "name": collection.display_name, "description": collection.description, "works_with_model": result.compatible}
            if not result.compatible:
                entry["why_not"] = "; ".join(r.message for r in result.reasons)
            collections.append(entry)
        return {"collections": collections}

    def find_place(self, query: str) -> dict:
        try:
            places = self.places.search(query)
        except Exception as exc:  # noqa: BLE001 — a failed lookup is something the model can say, not a crash
            return {"error": f"the place lookup failed: {exc}"}
        if not places:
            # a geocoder wants a name, not a description, and a small model otherwise gives up here
            return {"places": [], "note": f"nothing found for {query!r}. Try again with only the place's name and region, like 'Lake Titicaca, Peru', leaving out words like near or around."}

        distinct = distinct_places(places)
        matches = []
        for place in places:
            place_id = f"place_{len(self.found) + 1}"
            self.found[place_id] = place
            if len(distinct) > 1:
                self.ambiguous[place_id] = distinct
            matches.append({"place_id": place_id, "name": place.name, "type": place.kind, "area_km2": round(place.area_km2), "too_large": place.area_km2 > MAX_AREA_KM2})
        result = {"places": matches}
        if len(distinct) > 1:
            result["different_places_with_this_name"] = [p.name for p in distinct]
        elif len(matches) > 1:
            # said outright, because a small model otherwise asks "the city or the district?" about one place
            result["note"] = f"these matches are all the same place at different sizes, so use {matches[0]['place_id']} and don't ask which"
        return result
