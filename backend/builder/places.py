import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

NOMINATIM = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy asks every client to identify itself
USER_AGENT = "geotriage/0.1 (workflow builder)"


@dataclass(frozen=True)
class Place:
    name: str
    kind: str
    # west, south, east, north, like GeoJSON
    bbox: tuple[float, float, float, float]
    # OpenStreetMap's own sense of how prominent the place is, 0 to 1
    importance: float = 0.0

    @property
    def area_km2(self) -> float:
        """of the bounding box, which is what a drafted workflow covers"""
        west, south, east, north = self.bbox
        width = (east - west) * 111.32 * math.cos(math.radians((south + north) / 2))
        return abs(width * (north - south) * 110.57)

    def overlaps(self, other: "Place") -> bool:
        west, south, east, north = self.bbox
        o_west, o_south, o_east, o_north = other.bbox
        return not (east < o_west or o_east < west or north < o_south or o_north < south)

    def polygon(self) -> dict:
        west, south, east, north = self.bbox
        return {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}


# a second match at least this prominent, relative to the first, is a real alternative rather than an obscure namesake
RIVAL_IMPORTANCE = 0.7


def distinct_places(places: list[Place]) -> list[Place]:

    if not places:
        return []
    first = places[0]
    return [first, *(p for p in places[1:] if not p.overlaps(first) and p.importance >= RIVAL_IMPORTANCE * first.importance)]


class Places(Protocol):
    def search(self, query: str) -> list[Place]: ...


def from_nominatim(results: list[dict]) -> list[Place]:
    places = []
    for result in results:
        # Nominatim orders its box south, north, west, east
        south, north, west, east = (float(v) for v in result["boundingbox"])
        places.append(Place(name=result["display_name"], kind=result.get("addresstype") or result.get("type", ""), bbox=(west, south, east, north), importance=float(result.get("importance") or 0.0)))
    return places


def fixture_path(directory: Path, query: str) -> Path:
    return directory / f"{re.sub(r'[^a-z0-9]+', '-', query.lower()).strip('-')}.json"


class NominatimPlaces:

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20, transport=transport)
        self._seen: dict[str, list[Place]] = {}

    def search(self, query: str) -> list[Place]:
        key = query.strip().lower()
        if key not in self._seen:
            response = self._http.get(NOMINATIM, params={"q": query, "format": "jsonv2", "limit": 5, "accept-language": "en"})
            response.raise_for_status()
            self._seen[key] = from_nominatim(response.json())
        return self._seen[key]


class RecordedPlaces:
    def __init__(self, directory: Path):
        self._recordings = {}
        for path in sorted(directory.glob("*.json")):
            data = json.loads(path.read_text())
            self._recordings[data["query"].lower()] = from_nominatim(data["candidates"])

    def search(self, query: str) -> list[Place]:
        wanted = _words(query)
        if not wanted:
            return []
        matches = [(len(_words(recorded) - wanted), recorded) for recorded in self._recordings if wanted <= _words(recorded)]
        # the closest recording wins: "India" is the country, not "Delhi, India"
        return self._recordings[min(matches)[1]] if matches else []


# articles a geocoder shrugs off
_IGNORED = {"the", "a", "an"}


def _words(query: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", query.lower())) - _IGNORED
