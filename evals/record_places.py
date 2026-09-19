import argparse
import json
import time

import httpx

from builder.places import NOMINATIM, USER_AGENT, fixture_path, from_nominatim
from evals.runner import DATASETS_DIR, EVALS_DIR

PLACES_DIR = EVALS_DIR / "fixtures" / "places"


def lookup(http: httpx.Client, query: str) -> list[dict]:
    response = http.get(NOMINATIM, params={"q": query, "format": "jsonv2", "limit": 5, "accept-language": "en"})
    response.raise_for_status()
    return response.json()


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
            path = fixture_path(PLACES_DIR, query)
            if args.refresh or not path.exists():
                candidates = lookup(http, query)
                path.write_text(json.dumps({"query": query, "candidates": candidates}, indent=2, ensure_ascii=False) + "\n")
                time.sleep(1.1)
            candidates = json.loads(path.read_text())["candidates"]
            if not candidates:
                print(f"{case['id']}: nothing found for {query!r}")
                continue
            if case["expected"]["kind"] == "draft":
                case["expected"]["bbox"] = [round(v, 4) for v in from_nominatim(candidates[:1])[0].bbox]
            print(f"{case['id']}: {candidates[0]['display_name'][:70]}")

    dataset.write_text("".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
