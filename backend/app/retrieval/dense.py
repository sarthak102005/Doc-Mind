"""Dense vector retrieval using hosted BGE-M3 embeddings and Qdrant."""

from __future__ import annotations

import logging
from typing import Any

from app.ai.embeddings.client import get_embedding_client
from app.retrieval.schema import EvidenceChunk
from app.services.vector_store import search_vectors

logger = logging.getLogger(__name__)


def retrieve_dense_candidates(
    query: str,
    authorized_document_ids: list[str] | None = None,
    limit: int = 15,
    score_threshold: float = 0.0,
) -> list[EvidenceChunk]:
    """Embed the search query and perform approximate nearest neighbor search in Qdrant."""
    if authorized_document_ids is not None and len(authorized_document_ids) == 0:
        return []

    try:
        client = get_embedding_client()
        query_vector = client.embed_query(query)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to generate query embedding: %s", exc)
        return []

    hits = search_vectors(
        query_vector=query_vector,
        limit=limit,
        document_ids=authorized_document_ids,
        score_threshold=score_threshold,
    )

    evidence_items: list[EvidenceChunk] = []
    for hit in hits:
        payload = hit.get("payload", {})
        section_path = payload.get("section_path", [])
        section_str = " > ".join(section_path) if isinstance(section_path, list) else str(section_path)

        evidence_items.append(
            EvidenceChunk(
                chunk_id=payload.get("chunk_id", str(hit.get("id"))),
                document_id=payload.get("document_id", ""),
                filename=payload.get("filename", ""),
                page_number=payload.get("page_number", 1),
                section=section_str,
                section_path=section_path if isinstance(section_path, list) else [section_str],
                chunk_type=payload.get("chunk_type", "text"),
                text=payload.get("text", ""),
                score=float(hit.get("score", 0.0)),
                metadata=payload.get("metadata", {}),
            )
        )

    return evidence_items
