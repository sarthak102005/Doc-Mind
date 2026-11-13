"""Text (BGE-M3) and image (SigLIP2) embedding interfaces (Phase 3)."""

from app.ai.embeddings.client import (
    EmbeddingClient,
    EmbeddingDimensionMismatchError,
    EmbeddingError,
    get_embedding_client,
)

__all__ = [
    "EmbeddingClient",
    "EmbeddingDimensionMismatchError",
    "EmbeddingError",
    "get_embedding_client",
]
