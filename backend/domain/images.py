from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from geotriage import Bands, check_descriptor

from runners.docker import DockerRunner, ImageError

log = logging.getLogger(__name__)

SMOKE_SHAPE = (32, 32)


@dataclass
class Admission:
    ok: bool
    descriptor: dict[str, Any] | None = None
    problems: list[str] = field(default_factory=list)
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    def record(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append((name, passed, detail))


def _synthetic_bands(descriptor: dict, collection_slug: str = "smoke-test") -> Bands:
    """
    deliberately boring reflectance:
    the point is to prove the model runs and returns what it declared, not to check its science
    """
    rng = np.random.default_rng(0)
    arrays = {name: rng.uniform(0.02, 0.6, size=SMOKE_SHAPE).astype(np.float32) for name in descriptor["requires"]["bands"]}
    return Bands(arrays, collection_slug=collection_slug)


def admit(image: str, expected_kind: str | None = None, smoke: bool = True) -> Admission:
    """
    `smoke=False` stops after the structural checks,
    which need no raster libraries and answer in about a second

    the API uses it so a registration form gets an immediate verdict,
    the worker then runs the smoke test, which stages real GeoTIFFs and so belongs where GDAL lives
    """
    verdict = Admission(ok=False)
    runner = DockerRunner(image)

    # 1. does it describe itself?
    try:
        descriptor = runner.describe()
    except ImageError as exc:
        verdict.record("describe", False, str(exc))
        verdict.problems.append(str(exc))
        return verdict
    verdict.record("describe", True, f"kind={descriptor.get('kind')}")
    verdict.descriptor = descriptor

    # 2. do the declarations hold up?
    problems = check_descriptor(descriptor)
    if expected_kind and descriptor.get("kind") != expected_kind:
        problems.append(f"this image describes itself as a {descriptor.get('kind')!r}, " f"but it is being registered as a {expected_kind!r}")
    if problems:
        verdict.record("declarations", False, "; ".join(problems))
        verdict.problems.extend(problems)
        return verdict
    verdict.record("declarations", True, f"slug={descriptor['slug']}")

    # 3. does it actually execute?
    # models only, a provider's equivalent is `verify`, which needs its live archive rather than synthetic input
    if smoke and descriptor["kind"] == "model":
        smoke_result = _smoke_test(runner, descriptor)
        verdict.checks.extend(smoke_result.checks)
        if not smoke_result.ok:
            verdict.problems.extend(smoke_result.problems)
            return verdict

    verdict.ok = True
    return verdict


def _smoke_test(runner: DockerRunner, descriptor: dict) -> Admission:
    result = Admission(ok=False)
    bands = _synthetic_bands(descriptor)

    try:
        output = runner.run(bands)
    except ImageError as exc:
        result.record("smoke run", False, str(exc))
        result.problems.append(f"the image could not score a synthetic scene: {exc}")
        return result

    declared = set(descriptor["scores"])
    returned = set(output.get("scores", {}))
    missing = declared - returned
    if missing:
        detail = f"did not return declared score(s): {sorted(missing)}"
        result.record("smoke run", False, detail)
        result.problems.append(detail)
        return result

    result.record("smoke run", True, f"returned {sorted(returned)}")

    if descriptor.get("prefilter"):
        try:
            kept = runner.screen(_synthetic_bands(descriptor))
        except ImageError as exc:
            result.record("smoke screen", False, str(exc))
            result.problems.append(f"the image declares a prefilter but screen() failed: {exc}")
            return result
        result.record("smoke screen", True, f"returned {kept}")

    result.ok = True
    return result
