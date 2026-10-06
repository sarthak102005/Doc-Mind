"""Ingestion worker tasks and lifecycle stubs (Phase 1)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models.document import Document, ProcessingStatus

logger = logging.getLogger(__name__)

STAGES = ["profile", "parse", "tables", "chunk", "index"]


def _run_stub(db: Session, document_id: str) -> None:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        logger.warning("Document %s not found for ingestion", document_id)
        return

    # 1. Transition to processing
    doc.status = "processing"
    doc.updated_at = datetime.now(UTC)
    db.commit()

    # 2. Simulate stage progression
    now = datetime.now(UTC)
    for stage in STAGES:
        stage_rec = (
            db.query(ProcessingStatus)
            .filter(ProcessingStatus.document_id == document_id, ProcessingStatus.stage == stage)
            .first()
        )
        if not stage_rec:
            stage_rec = ProcessingStatus(
                document_id=document_id,
                stage=stage,
                status="running",
                progress_percent=50,
                started_at=now,
            )
            db.add(stage_rec)
        else:
            stage_rec.status = "running"
            stage_rec.started_at = now

        db.commit()

        # Mark completed
        stage_rec.status = "completed"
        stage_rec.progress_percent = 100
        stage_rec.completed_at = datetime.now(UTC)
        stage_rec.duration_ms = 50
        db.commit()

    # 3. Transition to ready
    doc.status = "ready"
    doc.updated_at = datetime.now(UTC)
    db.commit()
    logger.info("Ingestion stub complete for document %s -> ready", document_id)


def process_document_stub(document_id: str, db: Session | None = None) -> None:
    """Simulate ingestion pipeline progression for Phase 1.

    Transitions: queued -> processing -> ready, updating ProcessingStatus stages.
    """
    logger.info("Starting ingestion stub for document %s", document_id)
    if db is not None:
        _run_stub(db, document_id)
    else:
        from app.db import session as db_session_module

        with db_session_module.SessionLocal() as session:
            _run_stub(session, document_id)
