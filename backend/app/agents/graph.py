"""LangGraph agentic orchestration workflow for DocMind."""

from __future__ import annotations

import logging
from typing import Any
from sqlalchemy.orm import Session

from langgraph.graph import END, START, StateGraph

from app.agents.generator import finalize_answer
from app.agents.planner import plan_query
from app.agents.reasoner import synthesize_reasoning
from app.agents.retriever import retrieve_evidence
from app.agents.state import AgentState
from app.agents.verifier import verify_answer
from app.db.models.user import User
from app.retrieval.filters import resolve_authorized_document_ids

logger = logging.getLogger(__name__)


def route_after_verification(state: AgentState) -> str:
    """Determine whether to retry retrieval or proceed to finalize answer."""
    verif = state.get("verification", {})
    retry_count = state.get("retry_count", 0)

    if verif.get("recommend_retry", False) and retry_count <= 1:
        logger.info("Routing back to retriever for targeted retry (attempt %d)", retry_count)
        return "retriever"
    return "generator"


def build_agent_graph() -> StateGraph:
    """Build and compile the multi-node DocMind agent graph."""
    graph = StateGraph(AgentState)

    # Add agent nodes
    graph.add_node("planner", plan_query)
    graph.add_node("retriever", retrieve_evidence)
    graph.add_node("reasoner", synthesize_reasoning)
    graph.add_node("verifier", verify_answer)
    graph.add_node("generator", finalize_answer)

    # Define edges
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "retriever")
    graph.add_edge("retriever", "reasoner")
    graph.add_edge("reasoner", "verifier")
    graph.add_conditional_edges(
        "verifier",
        route_after_verification,
        {
            "retriever": "retriever",
            "generator": "generator",
        },
    )
    graph.add_edge("generator", END)

    return graph.compile()


_compiled_graph = None


def get_agent_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_agent_graph()
    return _compiled_graph


def run_agent_workflow(
    query: str,
    user: User,
    db: Session,
    document_ids: list[str] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Execute the multi-agent reasoning graph for a user query."""
    authorized_ids = resolve_authorized_document_ids(
        user=user,
        db=db,
        requested_ids=document_ids,
    )

    initial_state: AgentState = {
        "query": query,
        "user_id": user.id,
        "authorized_doc_ids": authorized_ids,
        "history": conversation_history or [],
        "plan": [],
        "sub_queries": [],
        "retrieved_evidence": [],
        "draft_answer": "",
        "citations": [],
        "retrieved_chunks": [],
        "verification": {},
        "retry_count": 0,
        "final_answer": "",
        "model_used": "",
        "fallback_occurred": False,
        "has_sufficient_evidence": True,
    }

    workflow = get_agent_graph()
    final_state = workflow.invoke(initial_state)

    return {
        "answer": final_state.get("final_answer", final_state.get("draft_answer", "")),
        "citations": final_state.get("citations", []),
        "retrieved_chunks": final_state.get("retrieved_chunks", []),
        "model_used": final_state.get("model_used", "langgraph-agent"),
        "fallback_occurred": final_state.get("fallback_occurred", False),
        "has_sufficient_evidence": final_state.get("has_sufficient_evidence", True),
        "verification": final_state.get("verification", {}),
    }
