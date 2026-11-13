"""Qdrant vector store management, collection setup, indexing, search, and cleanup."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _get_qdrant_headers(settings: Settings) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.qdrant_api_key is not None and settings.qdrant_api_key.get_secret_value():
        headers["api-key"] = settings.qdrant_api_key.get_secret_value()
    return headers


def ensure_collection(
    collection_name: str | None = None,
    dim: int | None = None,
    settings: Settings | None = None,
) -> None:
    """Ensure that the specified Qdrant vector collection exists with the required dimension."""
    cfg = settings or get_settings()
    coll = collection_name or cfg.qdrant_text_collection
    dimension = dim or cfg.embed_dim
    base_url = cfg.qdrant_url.rstrip("/")
    headers = _get_qdrant_headers(cfg)

    check_url = f"{base_url}/collections/{coll}"
    try:
        with httpx.Client(timeout=cfg.health_timeout_seconds) as client:
            resp = client.get(check_url, headers=headers)
            if resp.status_code == 200:
                logger.debug("Qdrant collection '%s' already exists", coll)
                return

            if resp.status_code == 404:
                # Create collection with Cosine distance
                create_url = f"{base_url}/collections/{coll}"
                payload = {
                    "vectors": {
                        "size": dimension,
                        "distance": "Cosine",
                    }
                }
                c_resp = client.put(create_url, headers=headers, json=payload)
                if c_resp.status_code in (200, 201):
                    logger.info("Successfully created Qdrant collection '%s' (dim=%d)", coll, dimension)
                else:
                    logger.warning(
                        "Failed to create Qdrant collection '%s': HTTP %d %s",
                        coll,
                        c_resp.status_code,
                        c_resp.text[:200],
                    )
    except Exception as exc:  # noqa: BLE001
        logger.error("Error ensuring Qdrant collection '%s': %s", coll, exc)


def upsert_document_chunks(
    document_id: str,
    chunks: list[Any],
    embeddings: list[list[float]],
    owner_id: str = "",
    filename: str = "",
    collection_name: str | None = None,
    settings: Settings | None = None,
) -> int:
    """Index semantic document chunks and their dense embeddings into Qdrant.

    Uses deterministic UUIDs based on (document_id, chunk_id) to ensure idempotency.
    """
    if not chunks:
        return 0

    if len(chunks) != len(embeddings):
        raise ValueError(
            f"Chunks count ({len(chunks)}) does not match embeddings count ({len(embeddings)})"
        )

    cfg = settings or get_settings()
    coll = collection_name or cfg.qdrant_text_collection
    ensure_collection(coll, dim=cfg.embed_dim, settings=cfg)

    base_url = cfg.qdrant_url.rstrip("/")
    headers = _get_qdrant_headers(cfg)
    upsert_url = f"{base_url}/collections/{coll}/points"

    points: list[dict[str, Any]] = []
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        # Generate deterministic point UUID to prevent duplicates on ingestion retries
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"docmind:{document_id}:{chunk.chunk_id}"))

        payload = {
            "document_id": document_id,
            "chunk_id": chunk.chunk_id,
            "owner_id": owner_id,
            "filename": filename,
            "page_number": getattr(chunk, "page_number", 1),
            "section_path": getattr(chunk, "section_path", []),
            "chunk_type": getattr(chunk, "chunk_type", "text"),
            "text": chunk.text,
            "token_count": getattr(chunk, "token_count_est", len(chunk.text) // 4),
            "metadata": getattr(chunk, "metadata", {}),
        }

        points.append({
            "id": point_id,
            "vector": embedding,
            "payload": payload,
        })

    # Upsert in batches of 64
    batch_size = 64
    upserted_count = 0
    with httpx.Client(timeout=30.0) as client:
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            resp = client.put(upsert_url, headers=headers, json={"points": batch})
            if resp.status_code in (200, 201):
                upserted_count += len(batch)
            else:
                logger.error(
                    "Qdrant points upsert failed: HTTP %d %s",
                    resp.status_code,
                    resp.text[:300],
                )
                raise RuntimeError(f"Failed to upsert points into Qdrant: {resp.text[:200]}")

    logger.info(
        "Successfully indexed %d chunks for document %s into Qdrant '%s'",
        upserted_count,
        document_id,
        coll,
    )
    return upserted_count


def search_vectors(
    query_vector: list[float],
    limit: int = 10,
    document_ids: list[str] | None = None,
    owner_id: str | None = None,
    score_threshold: float = 0.0,
    collection_name: str | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve nearest neighbor chunks from Qdrant with metadata filtering."""
    cfg = settings or get_settings()
    coll = collection_name or cfg.qdrant_text_collection
    base_url = cfg.qdrant_url.rstrip("/")
    headers = _get_qdrant_headers(cfg)
    search_url = f"{base_url}/collections/{coll}/points/search"

    filter_conditions: list[dict[str, Any]] = []

    if document_ids:
        if len(document_ids) == 1:
            filter_conditions.append({
                "key": "document_id",
                "match": {"value": document_ids[0]},
            })
        else:
            filter_conditions.append({
                "key": "document_id",
                "match": {"any": document_ids},
            })

    if owner_id:
        filter_conditions.append({
            "key": "owner_id",
            "match": {"value": owner_id},
        })

    search_payload: dict[str, Any] = {
        "vector": query_vector,
        "limit": limit,
        "with_payload": True,
        "with_vector": False,
    }

    if score_threshold > 0.0:
        search_payload["score_threshold"] = score_threshold

    if filter_conditions:
        search_payload["filter"] = {"must": filter_conditions}

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(search_url, headers=headers, json=search_payload)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("result", [])
                hits = []
                for item in results:
                    payload = item.get("payload", {})
                    hits.append({
                        "id": item.get("id"),
                        "score": item.get("score", 0.0),
                        "payload": payload,
                        "text": payload.get("text", ""),
                        "document_id": payload.get("document_id", ""),
                        "chunk_id": payload.get("chunk_id", ""),
                        "page_number": payload.get("page_number", 1),
                        "section_path": payload.get("section_path", []),
                        "chunk_type": payload.get("chunk_type", "text"),
                        "filename": payload.get("filename", ""),
                    })
                return hits
            elif resp.status_code == 404:
                logger.warning("Qdrant collection '%s' not found during search", coll)
                return []
            else:
                logger.error("Qdrant search error: HTTP %d %s", resp.status_code, resp.text[:200])
                return []
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to execute search against Qdrant '%s': %s", coll, exc)
        return []


def delete_document_vectors_sync(document_id: str, settings: Settings | None = None) -> None:
    """Synchronously delete all vector embeddings belonging to a document from Qdrant collections."""
    cfg = settings or get_settings()
    headers = _get_qdrant_headers(cfg)

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

    collections = [cfg.qdrant_text_collection, cfg.qdrant_image_collection]
    with httpx.Client(timeout=cfg.health_timeout_seconds) as client:
        for coll in collections:
            url = f"{cfg.qdrant_url.rstrip('/')}/collections/{coll}/points/delete"
            try:
                resp = client.post(url, headers=headers, json=filter_payload)
                if resp.status_code in (200, 404):
                    logger.debug("Cleaned vectors for doc %s from %s", document_id, coll)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Qdrant delete points unreachable for %s: %s", coll, exc)


async def delete_document_vectors(document_id: str) -> None:
    """Delete all vector embeddings belonging to a document from Qdrant collections (async)."""
    settings = get_settings()
    headers = _get_qdrant_headers(settings)

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
