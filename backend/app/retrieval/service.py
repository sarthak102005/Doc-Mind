"""High-level retrieval service unifying dense search, keyword matching, fusion, and reranking."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.retrieval.dense import retrieve_dense_candidates
from app.retrieval.filters import resolve_authorized_document_ids
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.keyword import rank_keyword_candidates
from app.retrieval.rerank import rerank_evidence
from app.retrieval.schema import EvidenceChunk

if TYPE_CHECKING:
    from app.db.models.user import User

logger = logging.getLogger(__name__)


class RetrievalService:
    """Service coordinates evidence retrieval across documents with permission enforcement."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def retrieve(
        self,
        query: str,
        user: User,
        db: Session,
        document_ids: list[str] | None = None,
        top_k: int = 6,
        score_threshold: float = 0.0,
    ) -> list[EvidenceChunk]:
        """Execute end-to-end retrieval:

        1. Filter document_ids by user permissions.
        2. Perform dense vector search in Qdrant.
        3. Score candidates with keyword matching (hybrid).
        4. Fuse ranks via RRF.
        5. Apply reranking (or pass-through) to select top_k evidence chunks.
        """
        # 1. Resolve authorized documents
        authorized_ids = resolve_authorized_document_ids(
            user=user,
            db=db,
            requested_ids=document_ids,
        )

        if not authorized_ids:
            logger.info("No authorized documents found for user %s (requested=%s)", user.id, document_ids)
            return []

        # 2. Dense candidate retrieval
        dense_candidates = retrieve_dense_candidates(
            query=query,
            authorized_document_ids=authorized_ids,
            limit=self.settings.rerank_candidates,
            score_threshold=score_threshold,
        )

        if not dense_candidates:
            return []

        # 3. Keyword re-ranking of candidates for lexical signals
        keyword_candidates = rank_keyword_candidates(query, dense_candidates)

        # 4. RRF fusion between dense and lexical rankings
        fused = reciprocal_rank_fusion(
            ranked_lists=[dense_candidates, keyword_candidates],
            k=60,
            top_n=max(top_k, 10),
        )

        # 5. Rerank to top_k
        final_evidence = rerank_evidence(
            query=query,
            candidates=fused,
            top_n=top_k,
            settings=self.settings,
        )

        return final_evidence


_retrieval_service: RetrievalService | None = None


def get_retrieval_service(settings: Settings | None = None) -> RetrievalService:
    global _retrieval_service
    current = settings or get_settings()
    if _retrieval_service is None or _retrieval_service.settings != current:
        _retrieval_service = RetrievalService(current)
    return _retrieval_service
