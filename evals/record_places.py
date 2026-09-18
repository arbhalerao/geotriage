import argparse
import json
import re
import time
from pathlib import Path

import httpx

from evals.runner import DATASETS_DIR, EVALS_DIR

PLACES_DIR = EVALS_DIR / "fixtures" / "places"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy asks every client to identify itself
USER_AGENT = "geotriage-evals/0.1 (local development)"


def fixture_path(query: str) -> Path:
    return PLACES_DIR / f"{re.sub(r'[^a-z0-9]+', '-', query.lower()).strip('-')}.json"


def lookup(http: httpx.Client, query: str) -> list[dict]:
    response = http.get(NOMINATIM, params={"q": query, "format": "jsonv2", "limit": 5, "accept-language": "en"})
    response.raise_for_status()
    return response.json()


def bbox_of(candidate: dict) -> list[float]:
    # Nominatim orders it south, north, west, east; the cases use west, south, east, north like GeoJSON
    south, north, west, east = (float(v) for v in candidate["boundingbox"])
    return [round(west, 4), round(south, 4), round(east, 4), round(north, 4)]


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.record_places")
    parser.add_argument("--refresh", action="store_true", help="look places up again even when already recorded")
    args = parser.parse_args()

    dataset = DATASETS_DIR / "builder.jsonl"
    cases = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    PLACES_DIR.mkdir(parents=True, exist_ok=True)

    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30) as http:
        for case in cases:
            query = case["expected"].get("place")
            if not query:
                continue
            path = fixture_path(query)
            if args.refresh or not path.exists():
                candidates = lookup(http, query)
                path.write_text(json.dumps({"query": query, "candidates": candidates}, indent=2, ensure_ascii=False) + "\n")
                time.sleep(1.1)
            candidates = json.loads(path.read_text())["candidates"]
            if not candidates:
                print(f"{case['id']}: nothing found for {query!r}")
                continue
            if case["expected"]["kind"] == "draft":
                case["expected"]["bbox"] = bbox_of(candidates[0])
            print(f"{case['id']}: {candidates[0]['display_name'][:70]}")

    dataset.write_text("".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
