"""Storage service interfacing with MinIO (S3 compatible) for PDF and object storage."""

from __future__ import annotations

import io
import logging
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from app.core.config import Settings, StorageBackend, get_settings

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.bucket = self.settings.minio_bucket
        self._client: Minio | None = None

    @property
    def is_minio(self) -> bool:
        return self.settings.storage_backend == StorageBackend.MINIO

    @property
    def client(self) -> Minio:
        if self._client is None:
            sec_key = self.settings.minio_secret_key.get_secret_value()
            self._client = Minio(
                endpoint=self.settings.minio_endpoint,
                access_key=self.settings.minio_access_key,
                secret_key=sec_key,
                secure=self.settings.minio_secure,
            )
        return self._client

    def ensure_bucket(self) -> None:
        """Create bucket if it does not already exist."""
        if self.is_minio:
            try:
                if not self.client.bucket_exists(self.bucket):
                    self.client.make_bucket(self.bucket)
                    logger.info("Created MinIO bucket '%s'", self.bucket)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "MinIO configured (STORAGE_BACKEND=minio) but unreachable at %s: %s",
                    self.settings.minio_endpoint,
                    exc,
                )
                msg = (
                    f"MinIO storage is configured (STORAGE_BACKEND=minio) but unreachable "
                    f"at {self.settings.minio_endpoint}: {exc}"
                )
                raise RuntimeError(msg) from exc
        else:
            local_dir = self.settings.cache_path / "storage" / self.bucket
            local_dir.mkdir(parents=True, exist_ok=True)

    def upload_file(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/pdf",
    ) -> str:
        """Upload binary data to storage backend. Returns the object key."""
        if self.is_minio:
            self.ensure_bucket()
            try:
                stream = io.BytesIO(data)
                self.client.put_object(
                    bucket_name=self.bucket,
                    object_name=object_name,
                    data=stream,
                    length=len(data),
                    content_type=content_type,
                )
                logger.info("Uploaded %d bytes to MinIO object %s", len(data), object_name)
                return object_name
            except Exception as exc:  # noqa: BLE001
                logger.error("MinIO upload failed for %s: %s", object_name, exc)
                raise RuntimeError(f"MinIO upload failed for {object_name}: {exc}") from exc
        else:
            target = self.settings.cache_path / "storage" / self.bucket / object_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            logger.info("Saved %d bytes to filesystem object %s", len(data), object_name)
            return object_name

    def get_presigned_download_url(
        self,
        object_name: str,
        expires_seconds: int = 3600,
    ) -> str:
        """Generate a presigned GET URL for downloading an object."""
        if self.is_minio:
            try:
                return self.client.presigned_get_object(
                    bucket_name=self.bucket,
                    object_name=object_name,
                    expires=timedelta(seconds=expires_seconds),
                )
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"MinIO presigned download URL failed for {object_name}: {exc}") from exc
        return f"/api/v1/documents/raw/{object_name}"

    def object_exists(self, object_name: str) -> bool:
        """Check whether object exists in storage."""
        if self.is_minio:
            try:
                self.client.stat_object(self.bucket, object_name)
                return True
            except S3Error as err:
                if err.code in ("NoSuchKey", "404"):
                    return False
                raise RuntimeError(f"MinIO stat_object failed for {object_name}: {err}") from err
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"MinIO stat_object connection failed for {object_name}: {exc}") from exc
        else:
            target = self.settings.cache_path / "storage" / self.bucket / object_name
            return target.is_file()

    def delete_file(self, object_name: str) -> None:
        """Remove an object from storage."""
        if self.is_minio:
            try:
                self.client.remove_object(self.bucket, object_name)
                logger.info("Deleted MinIO object %s", object_name)
                return
            except S3Error as err:
                if err.code in ("NoSuchKey", "404"):
                    return
                raise RuntimeError(f"MinIO remove_object failed for {object_name}: {err}") from err
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"MinIO delete failed for {object_name}: {exc}") from exc
        else:
            target = self.settings.cache_path / "storage" / self.bucket / object_name
            if target.exists():
                import contextlib

                with contextlib.suppress(OSError):
                    target.unlink()


_storage_service: StorageService | None = None


def get_storage_service(settings: Settings | None = None) -> StorageService:
    global _storage_service
    current = settings or get_settings()
    if _storage_service is None or _storage_service.settings.storage_backend != current.storage_backend:
        _storage_service = StorageService(current)
    return _storage_service
