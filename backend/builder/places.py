import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

import httpx

log = logging.getLogger(__name__)

NOMINATIM = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy asks every client to identify itself
USER_AGENT = "geotriage/0.1 (workflow builder)"


def bbox_area_km2(bbox: tuple[float, float, float, float]) -> float:
    """west, south, east, north in degrees; close enough at the scale of a workflow's area"""
    west, south, east, north = bbox
    width = (east - west) * 111.32 * math.cos(math.radians((south + north) / 2))
    return abs(width * (north - south) * 110.57)


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
        return bbox_area_km2(self.bbox)

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


def lookup_key(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip().lower())


class PlaceCache(Protocol):
    def get(self, key: str) -> tuple[list[dict], datetime] | None: ...

    def put(self, key: str, query: str, candidates: list[dict]) -> None: ...


class PostgresPlaceCache:

    def __init__(self, session_factory=None):
        self._session_factory = session_factory

    def _session(self):
        # imported late, so a places client can be built without a database
        if self._session_factory is None:
            from core.db.sync import get_session

            self._session_factory = get_session
        return self._session_factory()

    def get(self, key: str) -> tuple[list[dict], datetime] | None:
        from core.db.models.builder import PlaceLookup

        with self._session() as db:
            row = db.get(PlaceLookup, key)
            return (row.candidates, row.looked_up_at) if row else None

    def put(self, key: str, query: str, candidates: list[dict]) -> None:
        from sqlalchemy.dialects.postgresql import insert

        from core.db.models.builder import PlaceLookup

        values = {"query_key": key, "query": query, "candidates": candidates, "looked_up_at": datetime.now(timezone.utc)}
        with self._session() as db:
            # two workers looking up the same new place both write it; the later answer is as good as the earlier
            db.execute(insert(PlaceLookup).values(**values).on_conflict_do_update(index_elements=["query_key"], set_=values))
            db.commit()


class NominatimPlaces:
    def __init__(self, cache: PlaceCache | None = None, max_age: timedelta = timedelta(days=30), transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20, transport=transport)
        self._cache = cache
        self._max_age = max_age
        self._seen: dict[str, list[Place]] = {}

    def search(self, query: str) -> list[Place]:
        key = lookup_key(query)
        if key in self._seen:
            return self._seen[key]

        candidates = self._cached(key)
        if candidates is None:
            response = self._http.get(NOMINATIM, params={"q": query, "format": "jsonv2", "limit": 5, "accept-language": "en"})
            response.raise_for_status()
            candidates = response.json()
            self._store(key, query, candidates)

        self._seen[key] = from_nominatim(candidates)
        return self._seen[key]

    def _cached(self, key: str) -> list[dict] | None:
        if self._cache is None:
            return None
        try:
            hit = self._cache.get(key)
        except Exception:  # noqa: BLE001 — the cache is an optimisation, the geocoder is still there
            log.warning("place cache unreadable, asking OpenStreetMap", exc_info=True)
            return None
        if hit is None or datetime.now(timezone.utc) - hit[1] > self._max_age:
            return None
        return hit[0]

    def _store(self, key: str, query: str, candidates: list[dict]) -> None:
        if self._cache is None:
            return
        try:
            self._cache.put(key, query, candidates)
        except Exception:  # noqa: BLE001 — failing to remember an answer doesn't make the answer wrong
            log.warning("place cache unwritable, the answer is used but not kept", exc_info=True)


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
