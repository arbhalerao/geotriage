from __future__ import annotations

from typing import Any

import numpy as np
import rasterio


def _profile(array, transform, crs) -> dict:
    return {
        "driver": "COG",
        "dtype": "float32",
        "count": 1,
        "height": int(array.shape[0]),
        "width": int(array.shape[1]),
        "transform": transform,
        "crs": crs,
        "nodata": float(np.nan),
        "compress": "ZSTD",
        "predictor": 3,
        "blocksize": 512,
    }


def write_to_disk(path: str, array, transform, crs) -> None:
    with rasterio.open(path, "w", **_profile(array, transform, crs)) as dst:
        dst.write(np.asarray(array, dtype=np.float32), 1)


def read_grid(path: str) -> tuple[Any, Any]:
    with rasterio.open(path) as src:
        return src.transform, src.crs
