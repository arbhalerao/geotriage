from __future__ import annotations

import sys
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from core.config import settings

_client = None

_MISSING_CODES = ("404", "NoSuchKey", "NotFound")


def s3() -> Any:
    global _client
    if _client is None:
        endpoint = settings.MINIO_ENDPOINT
        if not endpoint.startswith("http"):
            endpoint = f"http://{endpoint}"
        _client = boto3.client(
            "s3",
            endpoint_url=endpoint,
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


def put_bytes(key: str, body: bytes, content_type: str = "image/tiff") -> None:
    s3().put_object(Bucket=settings.MINIO_BUCKET, Key=key, Body=body, ContentType=content_type)


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


def delete_keys(keys: list[str]) -> None:
    if not keys:
        return
    s3().delete_objects(
        Bucket=settings.MINIO_BUCKET,
        Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
    )


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
