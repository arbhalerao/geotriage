"""
python -m evals.record_catalogue [SDK_DIR]

writes the descriptors of the platform's default images to `fixtures/catalogue.json`,
so the builder eval sees the same models and collections a fresh install registers,
without docker or a database

read from the SDK's example sources, which are what those default images are built from
"""

import json
import sys
from pathlib import Path

from geotriage import describe

from evals.runner import EVALS_DIR

CATALOGUE_PATH = EVALS_DIR / "fixtures" / "catalogue.json"


def main() -> int:
    sdk = Path(sys.argv[1] if len(sys.argv) > 1 else EVALS_DIR.parent.parent / "geotriage-sdk")
    sys.path[:0] = [str(sdk / "examples" / "models"), str(sdk / "examples" / "providers")]

    # the images backend/domain/seed.py registers by default, and nothing else
    from earth_search import EarthSearchProvider
    from lst import LSTDetector
    from ndwi_water import NDWIWaterDetector
    from planetary_computer_provider import PlanetaryComputerProvider

    catalogue = {
        "models": [describe(m()) for m in (NDWIWaterDetector, LSTDetector)],
        "providers": [describe(p()) for p in (EarthSearchProvider, PlanetaryComputerProvider)],
    }
    CATALOGUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOGUE_PATH.write_text(json.dumps(catalogue, indent=2) + "\n")
    print(f"saved {CATALOGUE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
