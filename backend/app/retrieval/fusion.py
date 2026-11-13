"""Reciprocal Rank Fusion (RRF) for hybrid dense and lexical result fusion."""

from __future__ import annotations

from typing import Sequence

from app.retrieval.schema import EvidenceChunk


def reciprocal_rank_fusion(
    ranked_lists: list[Sequence[EvidenceChunk]],
    k: int = 60,
    top_n: int = 10,
) -> list[EvidenceChunk]:
    """Fuse multiple ranked candidate lists using standard RRF: score = sum(1 / (k + rank))."""
    scores: dict[str, float] = {}
    chunk_lookup: dict[str, EvidenceChunk] = {}

    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked):
            cid = chunk.chunk_id
            chunk_lookup[cid] = chunk
            # 0-indexed rank, so position is rank + 1
            scores[cid] = scores.get(cid, 0.0) + (1.0 / (k + (rank + 1)))

    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    results: list[EvidenceChunk] = []
    for cid in sorted_ids[:top_n]:
        base_chunk = chunk_lookup[cid]
        fused_chunk = base_chunk.model_copy(update={"score": scores[cid]})
        results.append(fused_chunk)

    return results
