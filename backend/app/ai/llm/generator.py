"""Grounded question answering and evidence synthesis with citation tracking."""

from __future__ import annotations

import logging
from typing import Any
from pydantic import BaseModel, Field

from app.ai.llm.client import LLMResponse, get_llm_client
from app.retrieval.schema import EvidenceChunk

logger = logging.getLogger(__name__)


class GroundedAnswer(BaseModel):
    """Grounded answer generated from retrieved document evidence."""

    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    model_used: str = ""
    fallback_occurred: bool = False
    has_sufficient_evidence: bool = True
    retrieved_chunks: list[dict[str, Any]] = Field(default_factory=list)


SYSTEM_PROMPT = """You are DocMind, an enterprise document intelligence assistant.
Your answers MUST be strictly grounded in the provided document excerpts.

Strict Rules:
1. Answer using ONLY the retrieved evidence provided below. Do NOT invent facts or extrapolate beyond what is stated.
2. If the provided evidence does not contain sufficient information to answer the question, clearly state: "The provided documents do not contain sufficient evidence to answer this question."
3. Every factual claim should cite its source using the exact format: [Doc: <filename>, Page: <page_number>].
4. If there is conflicting information between documents or versions, explicitly highlight the discrepancy.
5. Never fabricate citations or reference documents/pages that are not in the provided evidence.
"""


def format_evidence_context(evidence_chunks: list[EvidenceChunk]) -> str:
    """Format evidence items into structured numbered source blocks."""
    if not evidence_chunks:
        return "No relevant document excerpts were retrieved."

    formatted_blocks: list[str] = []
    for i, chunk in enumerate(evidence_chunks, 1):
        header = f"[Source {i} | Doc: {chunk.filename or chunk.document_id} | Page: {chunk.page_number} | Section: {chunk.section or 'General'}]"
        block = f"{header}\n{chunk.text.strip()}"
        formatted_blocks.append(block)

    return "\n\n---\n\n".join(formatted_blocks)


def generate_grounded_answer(
    query: str,
    evidence_chunks: list[EvidenceChunk],
    conversation_history: list[dict[str, str]] | None = None,
) -> GroundedAnswer:
    """Generate a grounded response to the user query using retrieved document chunks."""
    # 1. Handle empty evidence case
    if not evidence_chunks:
        return GroundedAnswer(
            answer="The provided documents do not contain sufficient evidence to answer this question.",
            citations=[],
            model_used="none",
            fallback_occurred=False,
            has_sufficient_evidence=False,
            retrieved_chunks=[],
        )

    # 2. Build context and messages
    evidence_context = format_evidence_context(evidence_chunks)
    user_prompt = f"""Retrieved Document Evidence:
----------------------------------------
{evidence_context}
----------------------------------------

User Question: {query}

Provide a direct, accurate answer cited with [Doc: <filename>, Page: <page_number>]."""

    messages: list[dict[str, str]] = []
    if conversation_history:
        # Keep recent turns (up to 4) for context
        for turn in conversation_history[-4:]:
            messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": user_prompt})

    # 3. Call LLM with fallback
    client = get_llm_client()
    llm_resp: LLMResponse = client.generate(messages, system_prompt=SYSTEM_PROMPT)

    # 4. Extract citations from evidence chunks
    citations: list[dict[str, Any]] = []
    seen_citations = set()
    for chunk in evidence_chunks:
        cit_key = (chunk.document_id, chunk.page_number)
        if cit_key not in seen_citations:
            seen_citations.add(cit_key)
            citations.append(chunk.to_citation_dict())

    retrieved_chunk_dicts = [chunk.to_citation_dict() for chunk in evidence_chunks]

    # Check if answer indicates insufficient evidence
    insufficient = "do not contain sufficient evidence" in llm_resp.content.lower()

    return GroundedAnswer(
        answer=llm_resp.content,
        citations=citations if not insufficient else [],
        model_used=llm_resp.model_used,
        fallback_occurred=llm_resp.fallback_occurred,
        has_sufficient_evidence=not insufficient,
        retrieved_chunks=retrieved_chunk_dicts,
    )
