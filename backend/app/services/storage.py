"""Storage service interfacing with MinIO (S3 compatible) for PDF and object storage."""

from __future__ import annotations

import io
import logging
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.bucket = self.settings.minio_bucket
        self._client: Minio | None = None
        self._mock_mode = False

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
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                logger.info("Created MinIO bucket '%s'", self.bucket)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not connect to MinIO (%s); falling back to local filesystem storage",
                exc,
            )
            self._mock_mode = True
            local_dir = self.settings.cache_path / "mock_storage" / self.bucket
            local_dir.mkdir(parents=True, exist_ok=True)

    def upload_file(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/pdf",
    ) -> str:
        """Upload binary data to MinIO. Returns the object key."""
        if not self._mock_mode:
            try:
                self.ensure_bucket()
                if not self._mock_mode:
                    stream = io.BytesIO(data)
                    self.client.put_object(
                        bucket_name=self.bucket,
                        object_name=object_name,
                        data=stream,
                        length=len(data),
                        content_type=content_type,
                    )
                    return object_name
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "MinIO upload failed (%s); persisting to mock storage fallback",
                    exc,
                )
                self._mock_mode = True

        # Fallback local filesystem storage
        target = self.settings.cache_path / "mock_storage" / self.bucket / object_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return object_name

    def get_presigned_download_url(
        self,
        object_name: str,
        expires_seconds: int = 3600,
    ) -> str:
        """Generate a presigned GET URL for downloading an object."""
        if not self._mock_mode:
            try:
                return self.client.presigned_get_object(
                    bucket_name=self.bucket,
                    object_name=object_name,
                    expires=timedelta(seconds=expires_seconds),
                )
            except Exception:  # noqa: BLE001
                pass

        # In fallback mode, return a synthetic local reference URL
        return f"/api/v1/documents/raw/{object_name}"

    def delete_file(self, object_name: str) -> None:
        """Remove an object from storage."""
        if not self._mock_mode:
            try:
                self.client.remove_object(self.bucket, object_name)
                return
            except (S3Error, Exception) as exc:  # noqa: BLE001
                logger.warning("MinIO remove_object failed: %s", exc)

        # Remove from fallback local storage if present
        target = self.settings.cache_path / "mock_storage" / self.bucket / object_name
        if target.exists():
            import contextlib

            with contextlib.suppress(OSError):
                target.unlink()


_storage_service: StorageService | None = None


def get_storage_service() -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
