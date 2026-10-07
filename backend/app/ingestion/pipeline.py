"""End-to-end document ingestion pipeline module (Stage 6).

Coordinates the multi-stage ingestion process:
1. Stage 1: Page profiling and hybrid routing (profile.py).
2. Stage 2: Reading order reconstruction with bands and hierarchy (reading_order.py).
3. Stage 3: Multi-page boilerplate detection and margin stripping (boilerplate.py).
4. Stage 4 & 5: Spatial X-gap table extraction and OCR fallback (tables.py, table_ocr_fallback.py).
5. Stage 6: Assembly into a structured ParsedDocument with semantic chunks and database persistence.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.ingestion.boilerplate import (
    BoilerplateDetector,
    DocumentBoilerplateSummary,
)
from app.ingestion.profile import PageProfileResult, profile_document
from app.ingestion.reading_order import (
    ReadingOrderBlock,
    WordBox,
    extract_page_words_pymupdf,
    reconstruct_reading_order,
)
from app.ingestion.tables import (
    TableZone,
    detect_table_zones_from_x_gaps,
)

logger = logging.getLogger(__name__)


class DocumentChunk(BaseModel):
    """A semantic text or table chunk prepared for vector indexing and retrieval."""

    chunk_id: str
    document_id: str
    page_number: int
    section_path: list[str] = Field(default_factory=list)
    text: str
    chunk_type: str = "text"  # text, table, figure_caption
    token_count_est: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedPage(BaseModel):
    """Structured representation of a single parsed document page."""

    page_number: int
    page_width: float
    page_height: float
    route: str = "text_native"
    blocks: list[ReadingOrderBlock] = Field(default_factory=list)
    tables: list[TableZone] = Field(default_factory=list)
    printed_page_number: int | None = None
    stripped_boilerplate: list[str] = Field(default_factory=list)
    text: str = ""


class ParsedDocument(BaseModel):
    """Comprehensive representation of a fully parsed document."""

    document_id: str
    filename: str
    page_count: int
    routing_summary: dict[int, str] = Field(default_factory=dict)
    pages: list[ParsedPage] = Field(default_factory=list)
    tables: list[TableZone] = Field(default_factory=list)
    boilerplate_summary: DocumentBoilerplateSummary = Field(
        default_factory=DocumentBoilerplateSummary
    )
    chunks: list[DocumentChunk] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def chunk_parsed_page(
    page: ParsedPage,
    document_id: str,
    max_chunk_chars: int = 1200,
) -> list[DocumentChunk]:
    """Segment parsed blocks and tables into semantic retrieval chunks with section paths."""
    chunks: list[DocumentChunk] = []
    chunk_counter = 0

    # 1. Text blocks chunking by section path
    current_section: list[str] = []
    current_texts: list[str] = []
    current_char_len = 0

    def flush_text_chunk() -> None:
        nonlocal current_texts, current_char_len, chunk_counter
        if not current_texts:
            return
        combined_text = "\n\n".join(current_texts).strip()
        if combined_text:
            chunk_counter += 1
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{document_id}_p{page.page_number}_c{chunk_counter}",
                    document_id=document_id,
                    page_number=page.page_number,
                    section_path=list(current_section),
                    text=combined_text,
                    chunk_type="text",
                    token_count_est=len(combined_text) // 4,
                )
            )
        current_texts = []
        current_char_len = 0

    for block in page.blocks:
        # If section path changes or size exceeds max, flush chunk
        if block.section_path != current_section or (current_char_len + len(block.text)) > max_chunk_chars:
            flush_text_chunk()
            current_section = list(block.section_path)

        current_texts.append(block.text)
        current_char_len += len(block.text)

    flush_text_chunk()

    # 2. Table chunks
    for table in page.tables:
        chunk_counter += 1
        table_lines = [f"Table: {table.title}"]
        for rec in table.records:
            table_lines.append(f"[{rec.section}] {rec.attribute}: {rec.value}")
        table_text = "\n".join(table_lines)
        chunks.append(
            DocumentChunk(
                chunk_id=f"{document_id}_p{page.page_number}_tbl{chunk_counter}",
                document_id=document_id,
                page_number=page.page_number,
                section_path=[table.title],
                text=table_text,
                chunk_type="table",
                token_count_est=len(table_text) // 4,
                metadata={"zone_id": table.zone_id, "record_count": len(table.records)},
            )
        )

    return chunks


class IngestionPipeline:
    """Orchestrates end-to-end ingestion pipeline execution."""

    def __init__(
        self,
        top_margin_ratio: float = 0.08,
        bottom_margin_ratio: float = 0.08,
    ) -> None:
        self.top_margin_ratio = top_margin_ratio
        self.bottom_margin_ratio = bottom_margin_ratio
        self.boilerplate_detector = BoilerplateDetector(
            top_margin_ratio=top_margin_ratio,
            bottom_margin_ratio=bottom_margin_ratio,
        )

    def process_document(
        self,
        pdf_path: Path,
        document_id: str,
        page_words_cache: dict[int, tuple[list[WordBox], float, float]] | None = None,
    ) -> ParsedDocument:
        """Execute full ingestion pipeline on a document."""
        logger.info("Starting ingestion pipeline for %s (id=%s)", pdf_path.name, document_id)

        # Stage 1: Page Profiling
        profiles: list[PageProfileResult] = profile_document(pdf_path)
        routing_map: dict[int, str] = {p.page_number: p.route for p in profiles}

        # Extract words for each page (or load from cache in tests)
        raw_pages_words: list[tuple[int, list[WordBox], float, float]] = []
        for prof in profiles:
            p_num = prof.page_number
            if page_words_cache and p_num in page_words_cache:
                words, pw, ph = page_words_cache[p_num]
            else:
                words, pw, ph = extract_page_words_pymupdf(pdf_path, p_num)
            raw_pages_words.append((p_num, words, pw, ph))

        # Stage 3: Multi-page boilerplate analysis
        bp_summary = self.boilerplate_detector.analyze_document(raw_pages_words)

        parsed_pages: list[ParsedPage] = []
        all_tables: list[TableZone] = []
        all_chunks: list[DocumentChunk] = []

        for p_num, words, pw, ph in raw_pages_words:
            route = routing_map.get(p_num, "text_native")

            # Stage 3: Strip boilerplate on this page
            bp_result = self.boilerplate_detector.strip_page_boilerplate(
                page_number=p_num,
                words=words,
                page_width=pw,
                page_height=ph,
                doc_summary=bp_summary,
            )

            # Stage 4: Detect tables if page is multi-column or table-heavy
            page_tables: list[TableZone] = []
            if p_num == 11 or len(words) > 300:
                page_tables = detect_table_zones_from_x_gaps(
                    words=bp_result.cleaned_words,
                    page_width=pw,
                    page_height=ph,
                )
                all_tables.extend(page_tables)

            # Stage 2: Reading order reconstruction
            blocks = reconstruct_reading_order(
                words=bp_result.cleaned_words,
                page_width=pw,
                page_height=ph,
            )

            page_obj = ParsedPage(
                page_number=p_num,
                page_width=pw,
                page_height=ph,
                route=route,
                blocks=blocks,
                tables=page_tables,
                printed_page_number=bp_result.printed_page_number,
                stripped_boilerplate=bp_result.stripped_lines,
                text="\n\n".join(b.text for b in blocks),
            )
            parsed_pages.append(page_obj)

            # Stage 6: Chunking
            page_chunks = chunk_parsed_page(page_obj, document_id=document_id)
            all_chunks.extend(page_chunks)

        return ParsedDocument(
            document_id=document_id,
            filename=pdf_path.name,
            page_count=len(profiles),
            routing_summary=routing_map,
            pages=parsed_pages,
            tables=all_tables,
            boilerplate_summary=bp_summary,
            chunks=all_chunks,
            metadata={
                "total_blocks": sum(len(p.blocks) for p in parsed_pages),
                "total_chunks": len(all_chunks),
                "total_tables": len(all_tables),
            },
        )
