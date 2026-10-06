"""Document management API endpoints (upload, list, detail, status, delete)."""

from __future__ import annotations

import hashlib
import io
import uuid
from typing import Any

import pypdf
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.config import RedisBackend, get_settings
from app.db.models.document import (
    Document,
    DocumentVersion,
    Permission,
    ProcessingStatus,
)
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.document import (
    DocumentDetailResponse,
    DocumentResponse,
    DocumentStatusResponse,
    ProcessingStatusResponse,
)
from app.services.redis_client import enqueue_ingestion_job
from app.services.storage import get_storage_service
from app.services.vector_store import delete_document_vectors
from app.worker.tasks import STAGES, process_document_stub

router = APIRouter(prefix="/documents", tags=["documents"])


def _check_document_access(doc: Document, user: User, db: Session, require_write: bool = False) -> bool:
    """Check if the user has access to the document."""
    if user.role == "admin" or doc.owner_id == user.id:
        return True

    perm = (
        db.query(Permission).filter(Permission.document_id == doc.id, Permission.user_id == user.id).first()
    )
    if not perm:
        return False
    return not (require_write and perm.permission_level not in ("write", "admin"))


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    """Upload a new document (PDF only). Validates size, type, and encryption."""
    settings = get_settings()

    filename = file.filename or "document.pdf"
    content_type = file.content_type or ""

    # 1. Basic format and extension check
    if not filename.lower().endswith(".pdf") and content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF documents are supported (.pdf)",
        )

    # 2. Read bytes and check size
    file_bytes = await file.read()
    size_bytes = len(file_bytes)
    if size_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes)",
        )

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum upload size of {settings.max_upload_mb} MB",
        )

    # 3. Magic bytes validation (%PDF)
    if not file_bytes.startswith(b"%PDF"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid PDF file format (missing %PDF signature)",
        )

    # 4. Encryption and structure check via pypdf
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        if reader.is_encrypted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password-protected PDFs are not supported. Please remove the password and try again.",
            )
        if len(reader.pages) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PDF contains no readable pages",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Corrupt or unreadable PDF file: {exc}",
        ) from exc

    # 5. Compute hash and upload to MinIO
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    doc_id = str(uuid.uuid4())
    minio_key = f"documents/{doc_id}/v1.pdf"

    storage = get_storage_service()
    storage.upload_file(minio_key, file_bytes, content_type="application/pdf")

    # 6. Create Database Records
    doc = Document(
        id=doc_id,
        owner_id=current_user.id,
        filename=filename,
        original_name=filename,
        content_type="application/pdf",
        size_bytes=size_bytes,
        file_hash=file_hash,
        current_version=1,
        status="queued",
        meta_info={"page_count": len(reader.pages)},
    )
    db.add(doc)

    doc_version = DocumentVersion(
        document_id=doc_id,
        version_num=1,
        minio_key=minio_key,
        file_hash=file_hash,
        size_bytes=size_bytes,
    )
    db.add(doc_version)

    # Register admin permission for the owner
    owner_perm = Permission(
        document_id=doc_id,
        user_id=current_user.id,
        permission_level="admin",
    )
    db.add(owner_perm)

    # Initialize processing stages
    for stage in STAGES:
        ps = ProcessingStatus(
            document_id=doc_id,
            stage=stage,
            status="pending",
            progress_percent=0,
        )
        db.add(ps)

    db.commit()
    db.refresh(doc)

    # 7. Queue ingestion task (worker process picks up if Redis; background task if in-memory)
    await enqueue_ingestion_job(doc_id, doc_version.id)
    if settings.redis_backend == RedisBackend.MEMORY:
        background_tasks.add_task(process_document_stub, doc_id)

    return DocumentResponse.model_validate(doc)


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[DocumentResponse]:
    """List documents accessible to the current user."""
    if current_user.role == "admin":
        docs = db.query(Document).order_by(Document.created_at.desc()).all()
    else:
        # User owns the document or has permission
        permitted_query = (
            db.query(Permission.document_id).filter(Permission.user_id == current_user.id).scalar_subquery()
        )
        docs = (
            db.query(Document)
            .filter(
                or_(
                    Document.owner_id == current_user.id,
                    Document.id.in_(permitted_query),
                )
            )
            .order_by(Document.created_at.desc())
            .all()
        )
    return [DocumentResponse.model_validate(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> DocumentDetailResponse:
    """Retrieve document details and presigned download URL."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if not _check_document_access(doc, current_user, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    storage = get_storage_service()
    download_url: str | None = None
    if doc.versions:
        latest_key = doc.versions[-1].minio_key
        download_url = storage.get_presigned_download_url(latest_key)

    detail = DocumentDetailResponse.model_validate(doc)
    detail.download_url = download_url
    return detail


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
def get_document_status(
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> DocumentStatusResponse:
    """Retrieve document ingestion progress status across stages."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc or not _check_document_access(doc, current_user, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    stages = [ProcessingStatusResponse.model_validate(s) for s in doc.processing_statuses]
    return DocumentStatusResponse(
        id=doc.id,
        status=doc.status,
        error_message=doc.error_message,
        stages=stages,
    )


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Delete document, cascading to MinIO objects, Qdrant vectors, and DB rows."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Only owner or admin can delete
    if current_user.role != "admin" and doc.owner_id != current_user.id:
        perm = (
            db.query(Permission)
            .filter(Permission.document_id == doc.id, Permission.user_id == current_user.id)
            .first()
        )
        if not perm or perm.permission_level != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this document",
            )

    # 1. Delete objects from MinIO storage
    storage = get_storage_service()
    for v in doc.versions:
        storage.delete_file(v.minio_key)

    # 2. Delete embeddings from Qdrant
    await delete_document_vectors(document_id)

    # 3. Delete database records (cascading deletes versions, statuses, profiles, tables, permissions)
    db.delete(doc)
    db.commit()

    return {"status": "deleted", "id": document_id}
