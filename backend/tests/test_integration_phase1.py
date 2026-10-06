"""Phase 1 integration tests: verify real PostgreSQL, Redis, and MinIO."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import REPO_ROOT, RedisBackend, Settings, StorageBackend, get_settings
from app.db.models.document import Document, DocumentVersion, Permission, ProcessingStatus
from app.db.models.user import User
from app.services.redis_client import enqueue_ingestion_job, pop_ingestion_job
from app.services.storage import StorageService

pytestmark = pytest.mark.integration


@pytest.fixture
def real_settings() -> Settings:
    return Settings(
        storage_backend=StorageBackend.MINIO,
        redis_backend=RedisBackend.REDIS,
        app_env="dev",
    )


@pytest.fixture
def real_engine(real_settings: Settings):
    return create_engine(real_settings.sqlalchemy_database_url)


@pytest.fixture
def real_session(real_engine):
    factory = sessionmaker(bind=real_engine)
    with factory() as session:
        yield session


@pytest.fixture
def sample_pdf_path() -> Path:
    path = REPO_ROOT / "benchmark" / "sample_1.pdf"
    assert path.is_file(), f"sample_1.pdf missing at {path}"
    return path


def test_integration_postgres_connection(real_engine) -> None:
    """Verify live PostgreSQL container connection and Alembic migration tables."""
    with real_engine.connect() as conn:
        res = conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
        )
        tables = {row[0] for row in res}
        expected = {
            "users",
            "documents",
            "document_versions",
            "processing_statuses",
            "page_profiles",
            "table_records",
            "permissions",
            "conversations",
            "messages",
            "alembic_version",
        }
        assert expected.issubset(tables), f"Missing tables in PostgreSQL: {expected - tables}"


def test_integration_minio_operations(real_settings: Settings) -> None:
    """Verify real MinIO bucket creation, upload, stat, presigned URL, and delete."""
    storage = StorageService(real_settings)
    assert storage.is_minio is True
    storage.ensure_bucket()
    assert storage.client.bucket_exists(storage.bucket) is True

    test_key = f"test_objects/{uuid.uuid4()}.pdf"
    data = b"%PDF-1.4 test payload for live minio storage"

    # Upload
    storage.upload_file(test_key, data, content_type="application/pdf")
    assert storage.object_exists(test_key) is True

    # Presigned URL
    url = storage.get_presigned_download_url(test_key, expires_seconds=600)
    assert "http" in url
    assert storage.bucket in url
    assert test_key in url

    # Delete
    storage.delete_file(test_key)
    assert storage.object_exists(test_key) is False


@pytest.mark.asyncio
async def test_integration_redis_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify live Redis queue push, pop, and payload fidelity."""
    monkeypatch.setenv("REDIS_BACKEND", "redis")
    get_settings.cache_clear()

    # Drain leftover jobs from previous test runs
    while True:
        old = await pop_ingestion_job(timeout=1)
        if not old:
            break

    doc_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())

    enqueued = await enqueue_ingestion_job(doc_id, version_id, {"source": "integration_test"})
    assert enqueued is True

    job = await pop_ingestion_job(timeout=3)
    assert job is not None
    assert job["document_id"] == doc_id
    assert job["version_id"] == version_id
    assert job["metadata"].get("source") == "integration_test"


def test_integration_postgres_cascading(sample_pdf_path: Path, real_session) -> None:
    """Verify SQLAlchemy models and foreign key cascading deletion in PostgreSQL."""
    db = real_session
    user = User(
        email=f"integ_{uuid.uuid4().hex[:8]}@docmind.internal",
        hashed_password="fakehashedpassword",
        full_name="Integration Tester",
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    doc_id = str(uuid.uuid4())
    doc = Document(
        id=doc_id,
        owner_id=user.id,
        filename="sample_1.pdf",
        original_name="sample_1.pdf",
        content_type="application/pdf",
        size_bytes=sample_pdf_path.stat().st_size,
        file_hash="fakehash123",
        current_version=1,
        status="queued",
    )
    db.add(doc)

    v = DocumentVersion(
        document_id=doc_id,
        version_num=1,
        minio_key=f"documents/{doc_id}/v1.pdf",
        file_hash="fakehash123",
        size_bytes=100,
    )
    db.add(v)

    ps = ProcessingStatus(
        document_id=doc_id,
        stage="profile",
        status="pending",
        progress_percent=0,
    )
    db.add(ps)

    perm = Permission(
        document_id=doc_id,
        user_id=user.id,
        permission_level="admin",
    )
    db.add(perm)

    db.commit()

    # Verify records exist
    assert db.query(Document).filter(Document.id == doc_id).first() is not None
    assert db.query(DocumentVersion).filter(DocumentVersion.document_id == doc_id).count() == 1
    assert db.query(ProcessingStatus).filter(ProcessingStatus.document_id == doc_id).count() == 1
    assert db.query(Permission).filter(Permission.document_id == doc_id).count() == 1

    # Delete document - cascading delete should clear versions, statuses, permissions
    db.delete(doc)
    db.commit()

    assert db.query(Document).filter(Document.id == doc_id).first() is None
    assert db.query(DocumentVersion).filter(DocumentVersion.document_id == doc_id).count() == 0
    assert db.query(ProcessingStatus).filter(ProcessingStatus.document_id == doc_id).count() == 0
    assert db.query(Permission).filter(Permission.document_id == doc_id).count() == 0

    # Clean up test user
    db.delete(user)
    db.commit()
