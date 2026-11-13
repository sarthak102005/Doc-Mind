"""State definition for LangGraph document intelligence workflow."""

from __future__ import annotations

from typing import Any, TypedDict
from app.retrieval.schema import EvidenceChunk


class AgentState(TypedDict, total=False):
    """Shared state across the DocMind agentic reasoning graph."""

    # Input parameters
    query: str
    user_id: str
    authorized_doc_ids: list[str]
    history: list[dict[str, str]]

    # Planning & Retrieval
    plan: list[str]
    sub_queries: list[str]
    retrieved_evidence: list[EvidenceChunk]

    # Synthesis & Verification
    reasoning: str
    draft_answer: str
    citations: list[dict[str, Any]]
    retrieved_chunks: list[dict[str, Any]]
    verification: dict[str, Any]
    retry_count: int

    # Final outputs
    final_answer: str
    model_used: str
    fallback_occurred: bool
    has_sufficient_evidence: bool
