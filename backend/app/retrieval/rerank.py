"""Reranking layer for candidate refinement (API, local cross-encoder, or pass-through)."""

from __future__ import annotations

import logging
from typing import Sequence

import httpx

from app.core.config import RerankBackend, Settings, get_settings
from app.retrieval.schema import EvidenceChunk

logger = logging.getLogger(__name__)


def rerank_evidence(
    query: str,
    candidates: Sequence[EvidenceChunk],
    top_n: int = 6,
    settings: Settings | None = None,
) -> list[EvidenceChunk]:
    """Rerank candidate evidence chunks. Falls back cleanly to dense/fused order on failure."""
    if not candidates:
        return []

    cfg = settings or get_settings()

    if cfg.rerank_backend == RerankBackend.OFF or not cfg.rerank_base_url or not cfg.rerank_model:
        return list(candidates[:top_n])

    url = f"{cfg.rerank_base_url.rstrip('/')}/rerank"
    headers = {"Content-Type": "application/json"}
    api_key = cfg.rerank_api_key.get_secret_value()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    docs = [c.text for c in candidates]
    payload = {
        "model": cfg.rerank_model,
        "query": query,
        "documents": docs,
        "top_n": top_n,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                reranked: list[EvidenceChunk] = []
                for item in results:
                    idx = item.get("index")
                    rel_score = item.get("relevance_score", 0.0)
                    if idx is not None and 0 <= idx < len(candidates):
                        orig = candidates[idx]
                        reranked.append(orig.model_copy(update={"score": float(rel_score)}))
                if reranked:
                    return reranked
            else:
                logger.warning("Rerank API returned status %d. Falling back to base order.", resp.status_code)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Reranking failed or unreachable (%s). Using candidate order.", exc)

    return list(candidates[:top_n])
