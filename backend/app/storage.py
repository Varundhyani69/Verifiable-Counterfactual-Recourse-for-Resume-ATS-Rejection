"""
Storage backend abstraction.

Implements the StorageBackend Protocol with two concrete backends:
  - LocalFileStorage  — default for local development, writes to UPLOAD_DIR
  - S3CompatibleStorage — activates when S3_ENDPOINT_URL env var is set

Services depend on StorageBackend (the Protocol), not on a concrete class,
so the storage layer can be swapped without changing any business logic.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol defining the minimal interface every storage backend must satisfy."""

    def save(self, file_id: str, data: bytes) -> str:
        """Persist ``data`` under ``file_id`` and return the storage path/URL."""
        ...

    def load(self, path: str) -> bytes:
        """Load and return the raw bytes stored at ``path``."""
        ...

    def delete(self, path: str) -> None:
        """Remove the object at ``path``. Silently succeeds if not found."""
        ...


class LocalFileStorage:
    """
    Writes files to the local filesystem under UPLOAD_DIR.

    Safe for development and single-process deployments. Not suitable for
    multi-replica production environments — use S3CompatibleStorage there.
    """

    def __init__(self, upload_dir: str | None = None) -> None:
        self._root = Path(upload_dir or os.environ.get("UPLOAD_DIR", "/tmp/uploads"))
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, file_id: str, data: bytes) -> str:
        path = self._root / file_id
        path.write_bytes(data)
        return str(path)

    def load(self, path: str) -> bytes:
        return Path(path).read_bytes()

    def delete(self, path: str) -> None:
        target = Path(path)
        if target.exists():
            target.unlink()


class S3CompatibleStorage:
    """
    Writes files to any S3-compatible object storage endpoint.

    Activated automatically when S3_ENDPOINT_URL is set. Requires
    S3_BUCKET_NAME, S3_ACCESS_KEY, and S3_SECRET_KEY env vars.
    """

    def __init__(self) -> None:
        try:
            import boto3  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for S3CompatibleStorage. "
                "Install it with: pip install boto3"
            ) from exc

        self._client = boto3.client(
            "s3",
            endpoint_url=os.environ["S3_ENDPOINT_URL"],
            aws_access_key_id=os.environ["S3_ACCESS_KEY"],
            aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        )
        self._bucket = os.environ["S3_BUCKET_NAME"]

    def save(self, file_id: str, data: bytes) -> str:
        self._client.put_object(Bucket=self._bucket, Key=file_id, Body=data)
        return f"s3://{self._bucket}/{file_id}"

    def load(self, path: str) -> bytes:
        # path format: s3://<bucket>/<key>
        key = path.split("/", 3)[-1]
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def delete(self, path: str) -> None:
        key = path.split("/", 3)[-1]
        self._client.delete_object(Bucket=self._bucket, Key=key)


def get_storage_backend() -> StorageBackend:
    """
    FastAPI dependency / factory that returns the appropriate StorageBackend.

    Returns S3CompatibleStorage if S3_ENDPOINT_URL is set; otherwise falls
    back to LocalFileStorage.
    """
    if os.environ.get("S3_ENDPOINT_URL"):
        return S3CompatibleStorage()
    return LocalFileStorage()
