from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import sys
import time
import urllib.request
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from core.config import settings

log = logging.getLogger(__name__)

_client = None

_MISSING_CODES = ("404", "NoSuchKey", "NotFound")


def s3() -> Any:
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=_endpoint(),
            aws_access_key_id=settings.MINIO_ROOT_USER,
            aws_secret_access_key=settings.MINIO_ROOT_PASSWORD,
            region_name="us-east-1",
            config=Config(signature_version="s3v4"),
        )
    return _client


def band_key(workflow_id, workflow_item_id, name: str) -> str:
    return f"{workflow_id}/{workflow_item_id}/{name}.tif"


def band_exists(key: str) -> bool:
    try:
        s3().head_object(Bucket=settings.MINIO_BUCKET, Key=key)
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code", "") in _MISSING_CODES:
            return False
        raise


def upload_file(key: str, path: str) -> None:
    s3().upload_file(path, settings.MINIO_BUCKET, key)


def get_bytes(key: str) -> bytes | None:
    try:
        obj = s3().get_object(Bucket=settings.MINIO_BUCKET, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code", "") in _MISSING_CODES:
            return None
        raise
    return obj["Body"].read()


def delete_workflow_prefix(workflow_id) -> None:
    """deletes every object under {workflow_id}/, a no-op if the prefix is empty"""
    client = s3()
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.MINIO_BUCKET, Prefix=f"{workflow_id}/"):
        contents = page.get("Contents") or []
        if not contents:
            continue
        client.delete_objects(
            Bucket=settings.MINIO_BUCKET,
            Delete={"Objects": [{"Key": o["Key"]} for o in contents]},
        )


def _endpoint() -> str:
    endpoint = settings.MINIO_ENDPOINT
    return endpoint if endpoint.startswith("http") else f"http://{endpoint}"


def _metrics_token() -> str:
    def encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = encode(json.dumps({"alg": "HS512", "typ": "JWT"}).encode())
    claims = encode(json.dumps({"exp": int(time.time()) + 60, "sub": settings.MINIO_ROOT_USER, "iss": "prometheus"}).encode())
    signature = encode(hmac.new(settings.MINIO_ROOT_PASSWORD.encode(), f"{header}.{claims}".encode(), hashlib.sha512).digest())
    return f"{header}.{claims}.{signature}"


def free_bytes() -> int | None:
    request = urllib.request.Request(f"{_endpoint()}/minio/v2/metrics/cluster", headers={"Authorization": f"Bearer {_metrics_token()}"})
    try:
        body = urllib.request.urlopen(request, timeout=5).read().decode()
    except Exception:  # noqa: BLE001 — not knowing the free space skips that check, it never stops a run
        log.warning("couldn't read MinIO's free space", exc_info=True)
        return None
    found = re.search(r"^minio_cluster_capacity_usable_free_bytes(?:\{[^}]*\})? ([0-9.e+]+)$", body, re.MULTILINE)
    return int(float(found.group(1))) if found else None


def init_bucket() -> None:
    """idempotent"""
    try:
        s3().create_bucket(Bucket=settings.MINIO_BUCKET)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise


def _main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] != "init":
        print("usage: python -m storage init", file=sys.stderr)
        return 2
    init_bucket()
    print(f"bucket '{settings.MINIO_BUCKET}' ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
