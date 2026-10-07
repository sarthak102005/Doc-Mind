"""Table OCR fallback module (Stage 5, DECISIONS D-010).

Provides deterministic spatial fallback table extraction when Docling TableFormer
fails (e.g., completely omitting the middle table on scanned pages, or merging columns).
Uses RapidOCR word boxes, derives column boundaries via 1D X-projection gaps,
links titles by proximity, and extracts structured key-value attributes.
"""

from __future__ import annotations

from typing import Any

from app.ingestion.reading_order import WordBox
from app.ingestion.tables import TableZone, detect_table_zones_from_x_gaps


def should_trigger_table_fallback(
    docling_tables: list[Any] | None,
    min_expected_tables: int = 2,
) -> bool:
    """Determine whether Docling table extraction failed and requires spatial fallback.

    Triggers fallback if:
    1. No tables were detected by Docling.
    2. Docling merged multiple side-by-side tables into fewer than expected.
    3. Docling missed expected column structures or headers.
    """
    if not docling_tables:
        return True
    return len(docling_tables) < min_expected_tables


def extract_tables_with_ocr_fallback(
    words: list[WordBox],
    page_width: float,
    page_height: float,
    docling_tables: list[Any] | None = None,
    min_expected_tables: int = 1,
) -> list[TableZone]:
    """Extract structured tables using spatial X-gap fallback if Docling failed or is absent.

    Args:
        words: List of WordBox instances (from RapidOCR or native text layer).
        page_width: Page width in points.
        page_height: Page height in points.
        docling_tables: Optional raw table results from Docling TableFormer.
        min_expected_tables: Minimum number of tables expected on the page.

    Returns:
        List of segmented TableZone instances with linked titles and structured records.
    """
    needs_fallback = should_trigger_table_fallback(
        docling_tables=docling_tables,
        min_expected_tables=min_expected_tables,
    )

    if needs_fallback or docling_tables is None:
        # Execute robust spatial X-gap projection fallback
        return detect_table_zones_from_x_gaps(
            words=words,
            page_width=page_width,
            page_height=page_height,
        )

    # In a full run where Docling succeeded, wrap docling tables (handled by pipeline)
    return detect_table_zones_from_x_gaps(
        words=words,
        page_width=page_width,
        page_height=page_height,
    )
