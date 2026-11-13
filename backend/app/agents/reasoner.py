"""Agent reasoner node: synthesizes evidence and drafts grounded response."""

from __future__ import annotations

import logging
from app.agents.state import AgentState
from app.ai.llm.generator import generate_grounded_answer

logger = logging.getLogger(__name__)


def synthesize_reasoning(state: AgentState) -> dict[str, Any]:
    """Synthesize evidence into a drafted grounded response."""
    evidence = state.get("retrieved_evidence", [])
    query = state.get("query", "")
    history = state.get("history", [])

    grounded = generate_grounded_answer(
        query=query,
        evidence_chunks=evidence,
        conversation_history=history,
    )

    logger.info("Reasoner drafted answer with model %s (sufficient=%s)", grounded.model_used, grounded.has_sufficient_evidence)

    return {
        "draft_answer": grounded.answer,
        "citations": grounded.citations,
        "model_used": grounded.model_used,
        "fallback_occurred": grounded.fallback_occurred,
        "has_sufficient_evidence": grounded.has_sufficient_evidence,
    }
