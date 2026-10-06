"""Database engine and session management."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base

settings = get_settings()

connect_args: dict[str, Any] = {}
if settings.sqlalchemy_database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
elif "postgresql" in settings.sqlalchemy_database_url:
    connect_args["connect_timeout"] = max(1, int(settings.health_timeout_seconds))

engine = create_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables registered with Base."""
    Base.metadata.create_all(bind=engine)
