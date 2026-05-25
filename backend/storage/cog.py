from __future__ import annotations

from typing import Any

import numpy as np
import rasterio
from rasterio.io import MemoryFile

from storage import client


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
        "compress": "DEFLATE",
        "predictor": 2,
        "blocksize": 512,
    }


def write_to_disk(path: str, array, transform, crs) -> None:
    with rasterio.open(path, "w", **_profile(array, transform, crs)) as dst:
        dst.write(np.asarray(array, dtype=np.float32), 1)


def put(key: str, array, transform, crs) -> None:
    """encoded in memory, since derived rasters never need disk staging"""
    with MemoryFile() as memfile:
        with memfile.open(**_profile(array, transform, crs)) as dst:
            dst.write(np.asarray(array, dtype=np.float32), 1)
        client.put_bytes(key, memfile.read())


def get_array(key: str) -> tuple[np.ndarray, Any, Any]:
    body = client.get_bytes(key)
    if body is None:
        raise KeyError(f"no object stored at '{key}'")
    with MemoryFile(body) as memfile:
        with memfile.open() as src:
            return src.read(1).astype(np.float32), src.transform, src.crs
