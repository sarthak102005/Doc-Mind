"""Security and permission filtering for document retrieval."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.db.models.document import Document, Permission

if TYPE_CHECKING:
    from app.db.models.user import User

logger = logging.getLogger(__name__)


def resolve_authorized_document_ids(
    user: User,
    db: Session,
    requested_ids: list[str] | None = None,
) -> list[str]:
    """Resolve the list of document IDs the user is authorized to query.

    If requested_ids is provided, returns the intersection of requested IDs
    and user-accessible documents.
    If requested_ids is None or empty, returns all document IDs accessible by the user.
    """
    if user.role == "admin":
        query = db.query(Document.id).filter(Document.status == "ready")
        if requested_ids:
            query = query.filter(Document.id.in_(requested_ids))
        accessible_ids = [row[0] for row in query.all()]
        return accessible_ids

    # Regular user: owner or has Permission row
    owner_query = db.query(Document.id).filter(
        Document.owner_id == user.id,
        Document.status == "ready",
    )
    perm_query = (
        db.query(Permission.document_id)
        .join(Document, Document.id == Permission.document_id)
        .filter(
            Permission.user_id == user.id,
            Document.status == "ready",
        )
    )

    if requested_ids:
        owner_query = owner_query.filter(Document.id.in_(requested_ids))
        perm_query = perm_query.filter(Permission.document_id.in_(requested_ids))

    accessible_set = {row[0] for row in owner_query.all()}.union({row[0] for row in perm_query.all()})
    return list(accessible_set)
