"""Evidence verification layer for citation validation and hallucination checking."""

from __future__ import annotations

import logging
import re
from typing import Any
from pydantic import BaseModel, Field

from app.retrieval.schema import EvidenceChunk

logger = logging.getLogger(__name__)


class VerificationResult(BaseModel):
    """Result of groundedness and citation verification."""

    is_verified: bool = True
    citation_coverage: float = 1.0  # Fraction of citations matching actual evidence
    valid_citations: list[dict[str, Any]] = Field(default_factory=list)
    invalid_citations: list[str] = Field(default_factory=list)
    unsupported_sentences: list[str] = Field(default_factory=list)
    recommend_retry: bool = False
    details: str = ""


def verify_answer_citations(
    answer: str,
    evidence_chunks: list[EvidenceChunk],
) -> VerificationResult:
    """Verify that every citation in the answer references actual retrieved documents and pages."""
    if not answer or not evidence_chunks:
        return VerificationResult(
            is_verified=True,
            citation_coverage=1.0,
            details="No citations or empty answer to verify",
        )

    # Build lookup of valid (filename/doc_id, page_number) pairs from evidence
    valid_targets: set[tuple[str, int]] = set()
    for chunk in evidence_chunks:
        doc_key = (chunk.filename.lower() if chunk.filename else chunk.document_id.lower())
        valid_targets.add((doc_key, chunk.page_number))
        if chunk.document_id:
            valid_targets.add((chunk.document_id.lower(), chunk.page_number))

    # Pattern: [Doc: <name>, Page: <num>] or 【Doc: <name>, Page: <num>】
    citation_pattern = re.compile(
        r"[\[\u3010]Doc:\s*([^,]+?),\s*Page:?\s*(\d+)[\]\u3011]",
        re.IGNORECASE,
    )
    matches = citation_pattern.findall(answer)

    if not matches:
        # Check if the answer claims insufficient evidence
        if "insufficient evidence" in answer.lower():
            return VerificationResult(is_verified=True, details="Answer acknowledges insufficient evidence")

        # Answer provided without citations
        return VerificationResult(
            is_verified=True,
            citation_coverage=1.0,
            details="Answer contains no explicit citation tags",
        )

    valid_citations: list[dict[str, Any]] = []
    invalid_citations: list[str] = []

    for doc_name, page_str in matches:
        clean_doc = doc_name.strip().lower()
        try:
            page_num = int(page_str.strip())
        except ValueError:
            page_num = -1

        matched = False
        for (v_doc, v_page) in valid_targets:
            if page_num == v_page and (clean_doc in v_doc or v_doc in clean_doc):
                matched = True
                break

        if matched:
            valid_citations.append({"document": doc_name.strip(), "page": page_num})
        else:
            invalid_citations.append(f"[Doc: {doc_name.strip()}, Page: {page_str.strip()}]")

    total_citations = len(matches)
    coverage = len(valid_citations) / max(1, total_citations)
    is_verified = len(invalid_citations) == 0

    recommend_retry = len(invalid_citations) > 0 and len(valid_citations) == 0

    return VerificationResult(
        is_verified=is_verified,
        citation_coverage=round(coverage, 2),
        valid_citations=valid_citations,
        invalid_citations=invalid_citations,
        recommend_retry=recommend_retry,
        details=(
            f"Verified {len(valid_citations)}/{total_citations} citations."
            + (f" Invalid: {invalid_citations}" if invalid_citations else "")
        ),
    )
