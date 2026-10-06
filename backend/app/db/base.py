"""Declarative base for all SQLAlchemy models in DocMind."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all DocMind database models."""

    pass
