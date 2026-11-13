"""Embedding service client for hosted and local embeddings (BGE-M3).

Integrates with OpenAI-compatible embedding endpoints (e.g. OpenRouter / SiliconFlow).
Features:
- Bounded batching (settings.embed_batch_size)
- Exponential backoff retry handling for 429 / 5xx / timeouts
- Dimensionality validation against settings.embed_dim (1024 for BGE-M3)
- Sanitized logging without exposing API credentials
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Raised when an embedding request fails after retries."""


class EmbeddingDimensionMismatchError(EmbeddingError):
    """Raised when the returned embedding vector dimension does not match configured embed_dim."""


class EmbeddingClient:
    """Client for generating dense vector embeddings via hosted API or local fallback."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.embed_base_url.rstrip("/")
        self.model = self.settings.embed_model
        self.dim = self.settings.embed_dim
        self.batch_size = self.settings.embed_batch_size
        self._api_key = self.settings.embed_api_key.get_secret_value()

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def embed_batch(
        self,
        texts: list[str],
        max_retries: int = 3,
        timeout: float = 30.0,
    ) -> list[list[float]]:
        """Embed a single batch of texts via the OpenAI-compatible /embeddings API."""
        if not texts:
            return []

        # Sanitize texts (replace empty strings with single whitespace)
        clean_texts = [t if t.strip() else " " for t in texts]
        url = f"{self.base_url}/embeddings"
        payload = {
            "model": self.model,
            "input": clean_texts,
            "encoding_format": "float",
        }

        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(url, headers=self._get_headers(), json=payload)

                if resp.status_code == 200:
                    data = resp.json()
                    raw_items = data.get("data", [])
                    # Sort items by index if provided
                    sorted_items = sorted(raw_items, key=lambda x: x.get("index", 0))
                    embeddings = [item["embedding"] for item in sorted_items]

                    if len(embeddings) != len(clean_texts):
                        raise EmbeddingError(
                            f"Mismatch in returned embeddings count: expected {len(clean_texts)}, got {len(embeddings)}"
                        )

                    # Validate vector dimensions
                    for i, vec in enumerate(embeddings):
                        if len(vec) != self.dim:
                            raise EmbeddingDimensionMismatchError(
                                f"Embedding dimension mismatch at index {i}: expected {self.dim}, got {len(vec)}"
                            )

                    return embeddings

                elif resp.status_code in (429, 500, 502, 503, 504):
                    wait_time = (2 ** attempt) * 1.5
                    logger.warning(
                        "Embedding API returned status %s on attempt %d/%d. Retrying in %.1fs...",
                        resp.status_code,
                        attempt + 1,
                        max_retries,
                        wait_time,
                    )
                    time.sleep(wait_time)
                    last_error = EmbeddingError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                else:
                    logger.error(
                        "Non-retryable error from embedding API: status %s, body: %s",
                        resp.status_code,
                        resp.text[:300],
                    )
                    raise EmbeddingError(f"Embedding API error {resp.status_code}: {resp.text[:200]}")

            except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                wait_time = (2 ** attempt) * 1.5
                logger.warning(
                    "Network error (%s) contacting embedding API on attempt %d/%d. Retrying in %.1fs...",
                    type(net_err).__name__,
                    attempt + 1,
                    max_retries,
                    wait_time,
                )
                time.sleep(wait_time)
                last_error = net_err

        raise EmbeddingError(f"Failed to generate embeddings after {max_retries} attempts: {last_error}")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate dense embeddings for a list of texts with automatic batching."""
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch_embeddings = self.embed_batch(batch)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    def embed_query(self, query: str) -> list[float]:
        """Generate a dense embedding vector for a single search query."""
        results = self.embed_batch([query])
        if not results:
            raise EmbeddingError("No embedding returned for query")
        return results[0]


_client_instance: EmbeddingClient | None = None


def get_embedding_client(settings: Settings | None = None) -> EmbeddingClient:
    """Return a singleton EmbeddingClient configured from settings."""
    global _client_instance
    current = settings or get_settings()
    if _client_instance is None or _client_instance.settings != current:
        _client_instance = EmbeddingClient(current)
    return _client_instance
