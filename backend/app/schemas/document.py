"""Document schemas for API responses and requests."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ProcessingStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: str
    status: str
    progress_percent: int
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None


class DocumentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version_num: int
    file_hash: str
    size_bytes: int
    created_at: datetime


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    filename: str
    original_name: str
    content_type: str
    size_bytes: int
    file_hash: str
    current_version: int
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentDetailResponse(DocumentResponse):
    meta_info: dict[str, Any]
    versions: list[DocumentVersionResponse] = []
    processing_statuses: list[ProcessingStatusResponse] = []
    download_url: str | None = None


class DocumentStatusResponse(BaseModel):
    id: str
    status: str
    error_message: str | None = None
    stages: list[ProcessingStatusResponse] = []
