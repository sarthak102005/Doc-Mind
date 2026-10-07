"""Unit tests for Stage 6: ParsedDocument Model & Ingestion Pipeline.

Verifies:
1. ParsedDocument, ParsedPage, and DocumentChunk models.
2. Semantic chunking with hierarchical section paths.
3. Multi-page pipeline execution using saved wordbox fixtures.
4. Table chunk generation with structured attribute records.
5. Boilerplate integration and document metadata tracking.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.ingestion.pipeline import (
    DocumentChunk,
    IngestionPipeline,
    ParsedDocument,
    ParsedPage,
    chunk_parsed_page,
)
from app.ingestion.reading_order import ReadingOrderBlock, WordBox
from app.ingestion.tables import TableRecord, TableZone

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def digital_fixtures() -> dict[int, tuple[list[WordBox], float, float]]:
    """Load cached wordboxes for pages 2, 3, 4, 11."""
    cache: dict[int, tuple[list[WordBox], float, float]] = {}
    for p_num in [2, 3, 4, 11]:
        p_path = FIXTURES_DIR / f"wordboxes_sample_1_p{p_num}.json"
        if p_path.exists():
            with open(p_path, encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
                words = [WordBox(**w) for w in data["words"]]
                cache[p_num] = (words, data["page_width"], data["page_height"])
    return cache


@pytest.mark.unit
def test_document_chunk_model_validation() -> None:
    """Verify DocumentChunk serialization and defaults."""
    chunk = DocumentChunk(
        chunk_id="doc1_p2_c1",
        document_id="doc1",
        page_number=2,
        section_path=["Choose Your Chassis", "Micro-HD"],
        text="Sample bullet text for Micro-HD chassis.",
        chunk_type="text",
        token_count_est=10,
    )
    assert chunk.chunk_id == "doc1_p2_c1"
    assert chunk.section_path == ["Choose Your Chassis", "Micro-HD"]
    assert chunk.token_count_est == 10
    assert chunk.chunk_type == "text"


@pytest.mark.unit
def test_chunk_parsed_page_text_and_tables() -> None:
    """Verify chunk_parsed_page generates distinct text and table chunks with paths."""
    page = ParsedPage(
        page_number=2,
        page_width=792.0,
        page_height=633.6,
        route="text_native",
        blocks=[
            ReadingOrderBlock(
                text="Automotive Plants",
                section_path=["Choose Your Chassis", "Micro-HD", "Applications"],
                l=50.0,
                t=200.0,
                r=150.0,
                b=215.0,
            ),
            ReadingOrderBlock(
                text="Heavy Manufacturing",
                section_path=["Choose Your Chassis", "Micro-HD", "Applications"],
                l=50.0,
                t=220.0,
                r=160.0,
                b=235.0,
            ),
            ReadingOrderBlock(
                text="Distribution Centers",
                section_path=["Choose Your Chassis", "Mini-HD", "Applications"],
                l=300.0,
                t=200.0,
                r=420.0,
                b=215.0,
            ),
        ],
        tables=[
            TableZone(
                zone_id=0,
                title="Micro-HD v2 Series",
                bbox=(18.0, 100.0, 250.0, 500.0),
                records=[
                    TableRecord(
                        entity="Micro-HD v2 Series",
                        section="BODY CONSTRUCTION",
                        attribute="Chassis",
                        value="Steel",
                    )
                ],
            )
        ],
    )

    chunks = chunk_parsed_page(page, document_id="doc_test")
    assert len(chunks) == 3  # 2 text chunks (by section path) + 1 table chunk

    # Text chunk 1
    assert chunks[0].section_path == ["Choose Your Chassis", "Micro-HD", "Applications"]
    assert "Automotive Plants" in chunks[0].text
    assert "Heavy Manufacturing" in chunks[0].text

    # Text chunk 2
    assert chunks[1].section_path == ["Choose Your Chassis", "Mini-HD", "Applications"]
    assert "Distribution Centers" in chunks[1].text

    # Table chunk
    assert chunks[2].chunk_type == "table"
    assert chunks[2].section_path == ["Micro-HD v2 Series"]
    assert "Table: Micro-HD v2 Series" in chunks[2].text
    assert "[BODY CONSTRUCTION] Chassis: Steel" in chunks[2].text


@pytest.mark.unit
def test_pipeline_on_multi_page_fixtures(
    digital_fixtures: dict[int, tuple[list[WordBox], float, float]],
) -> None:
    """Verify IngestionPipeline processes fixture pages into a complete ParsedDocument."""
    # Use sample_1.pdf as metadata source
    benchmark_pdf = Path(__file__).parents[2] / "benchmark" / "sample_1.pdf"
    assert benchmark_pdf.exists(), "Benchmark sample_1.pdf must exist for metadata"

    pipeline = IngestionPipeline()
    parsed_doc: ParsedDocument = pipeline.process_document(
        pdf_path=benchmark_pdf,
        document_id="doc_unit_test",
        page_words_cache=digital_fixtures,
    )

    assert parsed_doc.document_id == "doc_unit_test"
    assert parsed_doc.page_count == 12
    assert len(parsed_doc.pages) == 12

    # Check Page 2 has chunks with hierarchical paths
    p2 = next(p for p in parsed_doc.pages if p.page_number == 2)
    assert len(p2.blocks) > 0

    p2_chunks = [c for c in parsed_doc.chunks if c.page_number == 2]
    assert len(p2_chunks) > 0
    assert any("Applications" in c.section_path for c in p2_chunks)

    # Check Page 11 has extracted tables
    p11 = next(p for p in parsed_doc.pages if p.page_number == 11)
    assert len(p11.tables) == 3
    assert p11.tables[0].title == "Micro-HD v2 Series"
    assert p11.tables[1].title == "Mini-HD v2 Series"
    assert p11.tables[2].title == "Mag-HD v2 Series"

    # Check total chunks exist and contain tables
    table_chunks = [c for c in parsed_doc.chunks if c.chunk_type == "table"]
    assert len(table_chunks) >= 3
    assert any("Micro-HD v2 Series" in c.text for c in table_chunks)
