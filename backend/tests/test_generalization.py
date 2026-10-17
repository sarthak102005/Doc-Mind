"""Generalization unit tests on synthetic PDF documents.

Tests:
1. Two-column article with full-width title, columnar text, and bottom footnote (reading order & boilerplate).
2. Fully ruled specification table: must detect exactly ONE table using PyMuPDF find_tables.
3. Two independent side-by-side tables separated by a horizontal gutter: must detect exactly TWO tables.
4. Single borderless multi-column table: routes to X-gap projection.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from app.ingestion.boilerplate import BoilerplateDetector
from app.ingestion.profile import profile_document
from app.ingestion.reading_order import extract_page_words_pymupdf, reconstruct_reading_order
from app.ingestion.tables import detect_table_zones_from_x_gaps, detect_tables

GENERALIZATION_DIR = Path("D:/DocMind/benchmark/generalization")
ARTICLE_PDF = GENERALIZATION_DIR / "synthetic_article_2col.pdf"
RULED_TABLE_PDF = GENERALIZATION_DIR / "synthetic_ruled_table.pdf"
SIDE_BY_SIDE_PDF = GENERALIZATION_DIR / "synthetic_side_by_side_tables.pdf"
BORDERLESS_PDF = GENERALIZATION_DIR / "synthetic_borderless_table.pdf"


def test_synthetic_article_reading_order_and_routing() -> None:
    """Two-column article must route to text_native and order: Title -> Col 1 -> Col 2 -> Footnote."""
    if not ARTICLE_PDF.exists():
        pytest.skip("synthetic_article_2col.pdf not found")

    profiles = profile_document(ARTICLE_PDF)
    assert len(profiles) == 1
    p = profiles[0]
    assert p.route == "text_native", f"Expected route text_native, got {p.route}"

    words, pw, ph = extract_page_words_pymupdf(ARTICLE_PDF, page_number=1)
    blocks = reconstruct_reading_order(words, pw, ph)

    texts = [b.text for b in blocks]
    intro_idx = next(i for i, t in enumerate(texts) if "1. INTRODUCTION" in t)
    exp_idx = next(i for i, t in enumerate(texts) if "3. EXPERIMENTAL VALIDATION" in t)
    fn_idx = next(i for i, t in enumerate(texts) if "[1] Document processing" in t)

    assert intro_idx < exp_idx, "Column 1 text must appear before Column 2 text!"
    assert exp_idx < fn_idx, "Column 2 text must appear before Footnote!"

    # Boilerplate check
    detector = BoilerplateDetector(min_page_repetitions=1)
    summary = detector.analyze_document([(1, words, pw, ph)])
    page_res = detector.strip_page_boilerplate(
        page_number=1, words=words, page_width=pw, page_height=ph, doc_summary=summary
    )
    assert len(page_res.stripped_lines) >= 2, "Expected header and footer boilerplate lines stripped"


def test_synthetic_ruled_table_exact_one_detection() -> None:
    """synthetic_ruled_table.pdf must detect exactly ONE table using PyMuPDF find_tables."""
    if not RULED_TABLE_PDF.exists():
        pytest.skip("synthetic_ruled_table.pdf not found")

    words, pw, ph = extract_page_words_pymupdf(RULED_TABLE_PDF, page_number=1)
    zones, method_used = detect_tables(
        pdf_path=RULED_TABLE_PDF,
        page_number=1,
        words=words,
        page_width=pw,
        page_height=ph,
    )

    # User requirement: exactly ONE table detected on synthetic_ruled_table.pdf
    assert len(zones) == 1, f"Expected exactly 1 table, got {len(zones)}"
    assert method_used == "pymupdf_find_tables", f"Expected pymupdf_find_tables, got {method_used}"

    table = zones[0]
    assert "Table 1" in table.title or "Operational Specifications" in table.title
    assert len(table.records) >= 3, f"Expected at least 3 records, got {len(table.records)}"


def test_synthetic_side_by_side_tables_detection() -> None:
    """synthetic_side_by_side_tables.pdf must detect exactly TWO independent tables."""
    if not SIDE_BY_SIDE_PDF.exists():
        pytest.skip("synthetic_side_by_side_tables.pdf not found")

    words, pw, ph = extract_page_words_pymupdf(SIDE_BY_SIDE_PDF, page_number=1)
    zones, method_used = detect_tables(
        pdf_path=SIDE_BY_SIDE_PDF,
        page_number=1,
        words=words,
        page_width=pw,
        page_height=ph,
    )

    assert len(zones) == 2, f"Expected exactly 2 side-by-side tables, got {len(zones)}"
    assert method_used == "pymupdf_find_tables"

    titles = [z.title for z in zones]
    assert any("Table 1" in t or "Motor" in t for t in titles)
    assert any("Table 2" in t or "Tank" in t for t in titles)


def test_synthetic_borderless_table_routing() -> None:
    """synthetic_borderless_table.pdf has no vector ruling lines and routes to X-gap projection."""
    if not BORDERLESS_PDF.exists():
        pytest.skip("synthetic_borderless_table.pdf not found")

    words, pw, ph = extract_page_words_pymupdf(BORDERLESS_PDF, page_number=1)
    zones, method_used = detect_tables(
        pdf_path=BORDERLESS_PDF,
        page_number=1,
        words=words,
        page_width=pw,
        page_height=ph,
    )

    assert method_used == "xgap_projection", f"Expected xgap_projection for borderless table, got {method_used}"
    assert len(zones) >= 1
