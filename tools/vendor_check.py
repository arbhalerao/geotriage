"""
Fail if the vendored contract wheel no longer matches the contract source.

Only the Python inside the wheel is compared. Packaging metadata carries the SDK's
README and so changes for reasons that cannot affect the platform; code drift is the
thing that silently makes the admission gate validate against different rules than the
base image authors build on.

Skips when there is no contract checkout to compare against, so a clone of this repo
alone still passes `make check`.
"""

import filecmp
import pathlib
import sys
import tempfile
import zipfile


def wheel_sources(wheel: pathlib.Path, into: pathlib.Path) -> pathlib.Path:
    with zipfile.ZipFile(wheel) as z:
        z.extractall(into)
    return into / "geotriage"


def differences(a: pathlib.Path, b: pathlib.Path) -> list[str]:
    cmp = filecmp.dircmp(a, b, ignore=["__pycache__"])
    out = [f"only in the wheel: {n}" for n in cmp.left_only]
    out += [f"only in the source: {n}" for n in cmp.right_only]
    out += [f"differs: {n}" for n in cmp.diff_files]
    for name in cmp.subdirs:
        out += [f"{name}/{d}" for d in differences(a / name, b / name)]
    return out


def main(argv: list[str]) -> int:
    vendor, sdk_dir = pathlib.Path(argv[1]), pathlib.Path(argv[2])
    source = sdk_dir / "geotriage"
    if not source.is_dir():
        print(f"vendor-check: no contract checkout at {sdk_dir}, skipping")
        return 0

    wheels = sorted(vendor.glob("*.whl"))
    if len(wheels) != 1:
        print(f"vendor-check: expected exactly one wheel in {vendor}, found {len(wheels)}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        problems = differences(wheel_sources(wheels[0], pathlib.Path(tmp)), source)

    if problems:
        print(f"vendor-check: {wheels[0].name} is behind {source}:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        print("\n  run `make vendor-sdk` and commit the result", file=sys.stderr)
        return 1

    print("vendor-check: the vendored contract matches the source")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
