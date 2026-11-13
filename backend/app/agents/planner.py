"""Agent planner node: analyzes user query and generates sub-queries or search plan."""

from __future__ import annotations

import logging
from app.agents.state import AgentState

logger = logging.getLogger(__name__)


def plan_query(state: AgentState) -> dict[str, Any]:
    """Analyze query complexity and decompose into targeted sub-queries."""
    query = state.get("query", "").strip()
    sub_queries: list[str] = [query]
    plan: list[str] = []

    # Heuristic decomposition for comparison and multi-part queries
    lower_q = query.lower()
    if any(kw in lower_q for kw in ["compare", "difference between", "versus", " vs "]):
        plan.append("Decompose comparative query into separate concept searches")
        if " vs " in lower_q:
            parts = query.split(" vs ")
            if len(parts) == 2:
                sub_queries = [f"{parts[0].strip()}", f"{parts[1].strip()}", query]
        elif " and " in lower_q and ("difference" in lower_q or "compare" in lower_q):
            sub_queries = [query]
    elif " and " in lower_q and len(query.split()) > 10:
        plan.append("Multi-clause query: targeted search for unified concepts")
    else:
        plan.append("Direct targeted retrieval")

    logger.info("Planner formulated plan: %s with sub_queries: %s", plan, sub_queries)
    return {
        "plan": plan,
        "sub_queries": sub_queries,
        "retry_count": state.get("retry_count", 0),
    }
