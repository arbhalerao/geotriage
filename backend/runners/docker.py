from __future__ import annotations

import json
import logging
import os
import shutil
import stat
import subprocess
import tempfile
from typing import Any

import numpy as np
from geotriage import Bands

log = logging.getLogger(__name__)


class ImageError(RuntimeError):
    """
    distinct from a platform error,
    because the fix belongs to whoever built the image and the message is shown to them
    """


DEFAULT_TIMEOUT_S = int(os.getenv("RUN_TIMEOUT_SECONDS", "900"))
DEFAULT_MEMORY = os.getenv("RUN_MEMORY", "2g")
DEFAULT_CPUS = os.getenv("RUN_CPUS", "2")
DEFAULT_PIDS = os.getenv("RUN_PIDS_LIMIT", "256")

# where job directories are created, as this process sees it, and as the docker daemon sees it
# they differ whenever the platform itself runs in a container: `docker run -v` paths are resolved by the daemon on the host,
# not inside the caller
# leaving these unset (running the platform directly on the host) makes them the same path
SCRATCH = os.getenv("RUN_SCRATCH") or tempfile.gettempdir()
SCRATCH_HOST = os.getenv("RUN_SCRATCH_HOST") or SCRATCH


def to_host_path(path: str) -> str:
    if SCRATCH_HOST == SCRATCH:
        return path
    return os.path.join(SCRATCH_HOST, os.path.relpath(path, SCRATCH))


def _limits(network: bool) -> list[str]:
    """an image that runs away takes its own container down, not the worker"""
    flags = [
        "--rm",
        f"--memory={DEFAULT_MEMORY}",
        f"--cpus={DEFAULT_CPUS}",
        f"--pids-limit={DEFAULT_PIDS}",
        "--read-only",
        "--tmpfs=/tmp:rw,size=512m",
        "--security-opt=no-new-privileges",
        "--cap-drop=ALL",
    ]
    if not network:
        flags.append("--network=none")
    return flags


def docker_run(
    image: str,
    command: list[str],
    *,
    mounts: list[tuple[str, str, str]] | None = None,
    network: bool = False,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """
    raises ImageError carrying the container's stderr,
    because that message is for whoever built the image, not for us
    """
    argv = ["docker", "run", *_limits(network)]
    for source, target, mode in mounts or []:
        argv += ["-v", f"{to_host_path(source)}:{target}:{mode}"]
    argv += [image, *command]

    log.debug("image exec: %s", " ".join(argv))
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        raise ImageError(f"image '{image}' did not finish {command[0]} within {timeout_s}s and was killed") from None
    except FileNotFoundError:
        raise ImageError("docker is not available to the worker. Running images needs the docker " "CLI installed and /var/run/docker.sock mounted.") from None

    if result.returncode != 0:
        raise ImageError(_explain(image, command[0], result))
    return result.stdout


def _explain(image: str, command: str, result: subprocess.CompletedProcess) -> str:
    """
    the raw output is usually docker's rather than the image's,
    and says nothing about the actual problem, which is nearly always that the image doesn't speak our protocol
    """
    stderr = _strip_warnings(result.stderr or "").strip()
    stdout = (result.stdout or "").strip()

    if "pull access denied" in stderr or "not found" in stderr and "manifest" in stderr:
        return f"image '{image}' could not be pulled. Is the name right, and is it built or pushed?"

    if result.returncode == 127 or "executable file not found" in stderr:
        return f"image '{image}' has no geotriage entrypoint: running '{command}' found no such " "command. An image must be built FROM a geotriage-sdk base image, which provides it."

    if result.returncode == 137:
        return f"image '{image}' was killed running '{command}', most likely by the memory cap " f"({DEFAULT_MEMORY}). Reduce what it holds in memory or raise RUN_MEMORY."

    detail = (stderr or stdout)[-1500:]
    return f"image '{image}' exited {result.returncode} on '{command}': {detail}"


def _shared_dir(prefix: str, writable: bool) -> str:
    """
    mkdtemp gives 0700 owned by the worker's uid,
    but the container may run as a different uid under rootless Docker or userns remapping,
    so the mount has to be opened up explicitly rather than assumed readable
    """
    os.makedirs(SCRATCH, exist_ok=True)
    path = tempfile.mkdtemp(prefix=prefix, dir=SCRATCH)
    os.chmod(path, 0o777 if writable else 0o755)
    return path


def _publish(path: str) -> None:
    os.chmod(path, os.stat(path).st_mode | stat.S_IRGRP | stat.S_IROTH)


def _strip_warnings(stderr: str) -> str:
    """GDAL in particular is chatty about synthetic inputs, and buries the real error"""
    keep, skip_next = [], False
    for line in stderr.splitlines():
        if skip_next:
            skip_next = False
            continue
        if "Warning:" in line and line.lstrip().startswith(("/", "<")):
            skip_next = True  # warnings.warn prints the offending source line after
            continue
        keep.append(line)
    return "\n".join(keep)


def _json_out(stdout: str, image: str, command: str) -> Any:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        raise ImageError(f"image '{image}' did not print valid JSON on {command}. " f"Got: {stdout.strip()[:400]!r}") from None


class DockerRunner:
    def __init__(self, image: str, timeout_s: int = DEFAULT_TIMEOUT_S):
        self.image = image
        self.timeout_s = timeout_s

    def describe(self) -> dict[str, Any]:
        out = docker_run(self.image, ["describe"], timeout_s=min(self.timeout_s, 120))
        return _json_out(out, self.image, "describe")

    def run(self, bands: Bands) -> dict[str, Any]:
        with _staged(bands) as (in_dir, job_path):
            out_dir = _shared_dir("run-out-", writable=True)
            try:
                mounts = [(in_dir, "/job", "ro"), (out_dir, "/out", "rw")]
                docker_run(
                    self.image,
                    ["run", "--job", "/job/job.json", "--out", "/out/result.json"],
                    mounts=mounts,
                    timeout_s=self.timeout_s,
                )
                result = _read_result(out_dir, self.image)
                result["rasters"] = _load_rasters(result.get("rasters", {}), out_dir)
                return result
            finally:
                shutil.rmtree(out_dir, ignore_errors=True)

    def screen(self, bands: Bands) -> bool:
        with _staged(bands) as (in_dir, _job_path):
            out_dir = _shared_dir("run-out-", writable=True)
            try:
                docker_run(
                    self.image,
                    ["screen", "--job", "/job/job.json", "--out", "/out/result.json"],
                    mounts=[(in_dir, "/job", "ro"), (out_dir, "/out", "rw")],
                    timeout_s=min(self.timeout_s, 300),
                )
                return bool(_read_result(out_dir, self.image).get("keep", True))
            finally:
                shutil.rmtree(out_dir, ignore_errors=True)

    def search(self, job: dict[str, Any]) -> list[dict]:
        """needs the network, which is the whole point of a provider"""
        with _job_dir(job) as in_dir:
            out = docker_run(
                self.image,
                ["search", "--job", "/job/job.json"],
                mounts=[(in_dir, "/job", "ro")],
                network=True,
                timeout_s=min(self.timeout_s, 300),
            )
        return _json_out(out, self.image, "search").get("items", [])

    def sign(self, hrefs: list[str]) -> list[str]:
        """sign a batch in one invocation; per-href would cost more than the download"""
        if not hrefs:
            return []
        with _job_dir({"hrefs": hrefs}) as in_dir:
            out = docker_run(
                self.image,
                ["sign", "--job", "/job/job.json"],
                mounts=[(in_dir, "/job", "ro")],
                network=True,
                timeout_s=min(self.timeout_s, 120),
            )
        signed = _json_out(out, self.image, "sign").get("hrefs", [])
        if len(signed) != len(hrefs):
            raise ImageError(f"image '{self.image}' returned {len(signed)} signed hrefs for {len(hrefs)} inputs")
        return signed


class _staged:
    """write bands to a temp dir as GeoTIFFs and describe them in a job file"""

    def __init__(self, bands: Bands):
        self.bands = bands
        self.path: str | None = None

    def __enter__(self):
        self.path = _shared_dir("run-job-", writable=False)
        job = {
            "collection_slug": self.bands.collection,
            "bands": {},
            "raster_dir": "/out",
            "parameters": {},
        }
        for name in self.bands.names:
            tif = os.path.join(self.path, f"{name}.tif")
            _write_band(tif, self.bands[name], self.bands.transform, self.bands.crs)
            _publish(tif)
            job["bands"][name] = f"/job/{name}.tif"

        job_path = os.path.join(self.path, "job.json")
        with open(job_path, "w") as handle:
            json.dump(job, handle)
        _publish(job_path)
        return self.path, job_path

    def __exit__(self, *_exc):
        shutil.rmtree(self.path, ignore_errors=True)
        return False


class _job_dir:
    """a temp dir holding just a job.json, for commands that need no rasters"""

    def __init__(self, job: dict[str, Any]):
        self.job = job
        self.path: str | None = None

    def __enter__(self) -> str:
        self.path = _shared_dir("run-job-", writable=False)
        job_path = os.path.join(self.path, "job.json")
        with open(job_path, "w") as handle:
            json.dump(self.job, handle)
        _publish(job_path)
        return self.path

    def __exit__(self, *_exc):
        shutil.rmtree(self.path, ignore_errors=True)
        return False


def _write_band(path, array, transform, crs) -> None:
    import rasterio

    data = np.asarray(array, dtype=np.float32)
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "height": int(data.shape[0]),
        "width": int(data.shape[1]),
        "transform": transform,
        "crs": crs,
        "nodata": float(np.nan),
        "compress": "DEFLATE",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)


def _read_result(out_dir: str, image: str) -> dict[str, Any]:
    path = os.path.join(out_dir, "result.json")
    if not os.path.exists(path):
        raise ImageError(f"image '{image}' exited cleanly but wrote no result.json")
    with open(path) as handle:
        return _json_out(handle.read(), image, "result.json")


def _load_rasters(declared: dict[str, str], out_dir: str) -> dict[str, np.ndarray]:
    import rasterio

    loaded = {}
    for name, container_path in declared.items():
        host_path = os.path.join(out_dir, os.path.basename(container_path))
        if not os.path.exists(host_path):
            log.warning("image declared raster '%s' but wrote no file", name)
            continue
        with rasterio.open(host_path) as src:
            loaded[name] = src.read(1).astype(np.float32)
    return loaded
