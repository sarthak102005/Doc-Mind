"""Agent generator node: finalizes and formats verified response."""

from __future__ import annotations

import logging
from app.agents.state import AgentState

logger = logging.getLogger(__name__)


def finalize_answer(state: AgentState) -> dict[str, Any]:
    """Format final output with verified citations."""
    draft = state.get("draft_answer", "")
    citations = state.get("citations", [])
    has_sufficient = state.get("has_sufficient_evidence", True)

    logger.info("Generator finalized answer (citations=%d)", len(citations))
    return {
        "final_answer": draft,
        "citations": citations if has_sufficient else [],
    }
