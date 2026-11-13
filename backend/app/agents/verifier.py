"""Agent verifier node: validates citations and groundedness of the draft answer."""

from __future__ import annotations

import logging
from app.agents.state import AgentState
from app.retrieval.verifier import verify_answer_citations

logger = logging.getLogger(__name__)


def verify_answer(state: AgentState) -> dict[str, Any]:
    """Verify citations and factual grounding against retrieved evidence."""
    draft = state.get("draft_answer", "")
    evidence = state.get("retrieved_evidence", [])
    retry_count = state.get("retry_count", 0)

    verif = verify_answer_citations(answer=draft, evidence_chunks=evidence)

    # Allow bounded single retry if verifier detects severe citation hallucination and retry_count == 0
    should_retry = verif.recommend_retry and (retry_count < 1)

    logger.info(
        "Verifier result: is_verified=%s, coverage=%.2f, retry=%s",
        verif.is_verified,
        verif.citation_coverage,
        should_retry,
    )

    return {
        "verification": verif.model_dump(),
        "retry_count": retry_count + 1 if should_retry else retry_count,
    }
