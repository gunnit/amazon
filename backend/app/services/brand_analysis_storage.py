"""Storage abstraction for Brand Analysis source files and PPTX artifacts.

Two backends are supported:

* ``db`` (default) — bytes live in the existing ``LargeBinary`` columns on
  :class:`BrandAnalysisJob.artifact_data` and
  :class:`BrandAnalysisSourceFile.file_data`. Save is a no-op (the model
  carries the bytes); load reads from the model. ``storage_ref`` is set to
  ``{"backend": "db"}`` so the API knows where bytes came from.
* ``s3`` — bytes are uploaded to S3 under
  ``brand-analysis/{organization_id}/{job_id}/...`` using the same boto3
  configuration as :mod:`app.services.image_service`. The existing
  ``LargeBinary`` columns are still written when bytes are small enough to
  keep the on-disk artifact accessible from the DB; ``storage_ref`` records
  the S3 key for the canonical copy.

Selecting the backend is controlled by
``settings.BRAND_ANALYSIS_STORAGE_BACKEND``. Callers do not need to know
which backend is active — they receive a :class:`StorageRef` they can pass
back to :meth:`BrandAnalysisStorage.load`.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class StorageRef:
    """Where the bytes for a given object live."""

    backend: str  # "db" | "s3"
    key: Optional[str] = None  # S3 key when backend == "s3"

    def to_dict(self) -> dict:
        out: dict = {"backend": self.backend}
        if self.key:
            out["key"] = self.key
        return out

    @classmethod
    def from_dict(cls, value: Optional[dict]) -> Optional["StorageRef"]:
        if not value:
            return None
        return cls(backend=str(value.get("backend") or "db"), key=value.get("key"))


class BrandAnalysisStorage:
    """Persistence helper for Brand Analysis sources and artifacts."""

    def __init__(self) -> None:
        self.backend = (settings.BRAND_ANALYSIS_STORAGE_BACKEND or "db").lower()
        self._s3 = None
        if self.backend == "s3":
            try:
                import boto3  # noqa: WPS433

                self._s3 = boto3.client(
                    "s3",
                    region_name=settings.AWS_S3_REGION,
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                )
            except Exception:  # pragma: no cover - missing creds in CI
                logger.exception("Falling back to DB storage; boto3 unavailable")
                self.backend = "db"

    # ------------------------------------------------------------------
    # save
    # ------------------------------------------------------------------

    def save_source(
        self,
        *,
        organization_id: UUID,
        job_id: UUID,
        year: int,
        filename: str,
        content_type: Optional[str],
        data: bytes,
    ) -> StorageRef:
        if self.backend != "s3" or self._s3 is None:
            return StorageRef(backend="db")
        key = f"brand-analysis/{organization_id}/{job_id}/sources/{year}-{uuid.uuid4().hex}-{_safe(filename)}"
        self._put(key, data, content_type)
        return StorageRef(backend="s3", key=key)

    def save_artifact(
        self,
        *,
        organization_id: UUID,
        job_id: UUID,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> StorageRef:
        if self.backend != "s3" or self._s3 is None:
            return StorageRef(backend="db")
        key = f"brand-analysis/{organization_id}/{job_id}/artifacts/{_safe(filename)}"
        self._put(key, data, content_type)
        return StorageRef(backend="s3", key=key)

    # ------------------------------------------------------------------
    # load
    # ------------------------------------------------------------------

    def load(self, ref: Optional[StorageRef], *, fallback: Optional[bytes] = None) -> Optional[bytes]:
        """Return bytes for the given ref. Falls back to ``fallback`` for DB-backed records."""
        if ref is None or ref.backend != "s3" or self._s3 is None or not ref.key:
            return fallback
        try:
            response = self._s3.get_object(Bucket=settings.AWS_S3_BUCKET, Key=ref.key)
            return response["Body"].read()
        except Exception:  # pragma: no cover - missing creds in CI
            logger.exception("S3 fetch failed for %s; using DB fallback", ref.key)
            return fallback

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _put(self, key: str, data: bytes, content_type: Optional[str]) -> None:
        assert self._s3 is not None
        self._s3.put_object(
            Bucket=settings.AWS_S3_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )


def _safe(value: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "file"
