"""Pytest fixtures for DocMind backend tests."""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.db.session as app_session
from app.core.config import REPO_ROOT
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app

# Create temporary SQLite database file for thread-safe test execution
_tmp_dir = tempfile.gettempdir()
TEST_DB_PATH = Path(_tmp_dir) / f"docmind_test_{os.getpid()}.db"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"

os.environ["APP_ENV"] = "test"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Patch global SessionLocal in app.db.session so worker background tasks use the test database
app_session.SessionLocal = TestingSessionLocal
app_session.engine = test_engine


@pytest.fixture(scope="session", autouse=True)
def setup_test_db() -> Generator[None, None, None]:
    """Create all tables in the test database for the session."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    with contextlib.suppress(OSError):
        TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide a database session for a test."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Provide a TestClient with overridden get_db dependency."""
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_pdf_path() -> Path:
    """Return path to sample_1.pdf."""
    path = REPO_ROOT / "benchmark" / "sample_1.pdf"
    assert path.is_file(), f"sample_1.pdf not found at {path}"
    return path
