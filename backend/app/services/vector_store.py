"""Qdrant vector store management and cleanup helpers."""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def delete_document_vectors(document_id: str) -> None:
    """Delete all vector embeddings belonging to a document from Qdrant collections."""
    settings = get_settings()
    headers = {}
    if settings.qdrant_api_key is not None and settings.qdrant_api_key.get_secret_value():
        headers["api-key"] = settings.qdrant_api_key.get_secret_value()

    filter_payload = {
        "filter": {
            "must": [
                {
                    "key": "document_id",
                    "match": {"value": document_id},
                }
            ]
        }
    }

    collections = [settings.qdrant_text_collection, settings.qdrant_image_collection]
    async with httpx.AsyncClient(timeout=3.0) as client:
        for coll in collections:
            url = f"{settings.qdrant_url.rstrip('/')}/collections/{coll}/points/delete"
            try:
                resp = await client.post(url, headers=headers, json=filter_payload)
                if resp.status_code in (200, 404):
                    logger.debug("Cleaned vectors for doc %s from %s", document_id, coll)
                else:
                    logger.warning(
                        "Qdrant returned %s when deleting points from %s",
                        resp.status_code,
                        coll,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Qdrant delete points unreachable for %s: %s", coll, exc)
