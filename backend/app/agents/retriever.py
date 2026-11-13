"""Agent retriever node: executes multi-query retrieval across authorized documents."""

from __future__ import annotations

import logging
from app.agents.state import AgentState
from app.retrieval.dense import retrieve_dense_candidates
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.keyword import rank_keyword_candidates
from app.retrieval.rerank import rerank_evidence
from app.retrieval.schema import EvidenceChunk

logger = logging.getLogger(__name__)


def retrieve_evidence(state: AgentState) -> dict[str, Any]:
    """Execute retrieval across all sub-queries and consolidate evidence."""
    sub_queries = state.get("sub_queries", [state.get("query", "")])
    authorized_ids = state.get("authorized_doc_ids", [])
    collected_chunks: dict[str, EvidenceChunk] = {}

    for sq in sub_queries:
        if not sq:
            continue
        # 1. Dense retrieval
        dense = retrieve_dense_candidates(
            query=sq,
            authorized_document_ids=authorized_ids,
            limit=10,
        )
        if not dense:
            continue

        # 2. Keyword rank
        keyword = rank_keyword_candidates(sq, dense)

        # 3. RRF fusion
        fused = reciprocal_rank_fusion([dense, keyword], k=60, top_n=6)

        for chunk in fused:
            if chunk.chunk_id not in collected_chunks:
                collected_chunks[chunk.chunk_id] = chunk

    evidence_list = list(collected_chunks.values())
    logger.info("Retriever aggregated %d distinct evidence chunks", len(evidence_list))

    # Re-rank across the original query
    final_evidence = rerank_evidence(
        query=state.get("query", ""),
        candidates=evidence_list,
        top_n=8,
    )

    return {
        "retrieved_evidence": final_evidence,
        "retrieved_chunks": [c.to_citation_dict() for c in final_evidence],
    }
