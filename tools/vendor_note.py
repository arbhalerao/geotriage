"""
Regenerate backend/vendor/README.md so it describes the wheel sitting beside it.

Run from `make vendor-sdk`, never by hand: the point is that the provenance and the
binary are written in the same breath and cannot drift.
"""

import hashlib
import pathlib
import subprocess
import sys

TEMPLATE = """# Vendored contract

`geotriage-sdk` is a separate repo, but the platform imports it — the admission gate
runs its `check_descriptor`, staging runs its `calibrate`, and the runners build its
`Bands`. Rather than make a build here depend on a registry or a sibling checkout, the
built wheel is committed.

A fresh clone of this repo builds with no network and nothing else present.

This is the *contract*, not the catalogue. Adding a model or a provider is a container
image registered through the API and never touches this directory. Refresh it only when
the contract itself changes.

| | |
|---|---|
| wheel | `{wheel}` |
| sha256 | `{sha}` |
| built from | `{commit}`{dirty} |

## Refreshing it

From the platform repo, with a checkout of the contract next to it:

```bash
make vendor-sdk    # rebuilds the wheel and this file
make build         # rebuild the images against it
```

Commit both files together.
"""


def main(argv: list[str]) -> int:
    vendor, sdk_dir = pathlib.Path(argv[1]), pathlib.Path(argv[2])
    wheels = sorted(vendor.glob("*.whl"))
    if len(wheels) != 1:
        print(f"expected exactly one wheel in {vendor}, found {len(wheels)}", file=sys.stderr)
        return 1

    wheel = wheels[0]
    commit = subprocess.run(["git", "-C", str(sdk_dir), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or "(not a git checkout)"
    changed = subprocess.run(["git", "-C", str(sdk_dir), "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    dirty = f" plus {len(changed.splitlines())} uncommitted file(s)" if changed else ""

    (vendor / "README.md").write_text(
        TEMPLATE.format(
            wheel=wheel.name,
            sha=hashlib.sha256(wheel.read_bytes()).hexdigest(),
            commit=commit,
            dirty=dirty,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
