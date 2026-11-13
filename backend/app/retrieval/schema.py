"""Structured data models for retrieval and evidence representation."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class EvidenceChunk(BaseModel):
    """Structured evidence item returned by the retrieval pipeline."""

    chunk_id: str
    document_id: str
    filename: str = ""
    page_number: int = 1
    section: str = ""
    section_path: list[str] = Field(default_factory=list)
    chunk_type: str = "text"  # text, table, figure_caption
    text: str
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_citation_dict(self) -> dict[str, Any]:
        """Convert evidence item to a structured citation dictionary."""
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "filename": self.filename,
            "page_number": self.page_number,
            "section": self.section,
            "snippet": self.text[:200] + ("..." if len(self.text) > 200 else ""),
            "score": round(self.score, 4),
            "chunk_type": self.chunk_type,
        }
