"""Unit tests for Stage 5: Table OCR Fallback (DECISIONS D-010).

Verifies:
1. Trigger conditions for table fallback (Docling failure / omission / merger).
2. RapidOCR word boxes on scanned Page 11 recover all 3 spec tables.
3. Positively recovers Mini-HD v2 Series (the table completely missed by Docling TableFormer).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.ingestion.reading_order import WordBox
from app.ingestion.table_ocr_fallback import (
    extract_tables_with_ocr_fallback,
    should_trigger_table_fallback,
)
from app.ingestion.tables import TableZone

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def scanned_p11_data() -> dict[str, Any]:
    with open(FIXTURES_DIR / "wordboxes_sample_1_scanned_p11.json", encoding="utf-8") as f:
        res: dict[str, Any] = json.load(f)
        return res


@pytest.mark.unit
def test_should_trigger_table_fallback() -> None:
    """Verify fallback trigger conditions."""
    assert should_trigger_table_fallback(None, min_expected_tables=2) is True
    assert should_trigger_table_fallback([], min_expected_tables=2) is True
    # Docling merged 3 tables into 1
    assert should_trigger_table_fallback([{"id": "merged_tbl"}], min_expected_tables=3) is True
    # Docling succeeded with expected count
    assert should_trigger_table_fallback([{"id": "1"}, {"id": "2"}], min_expected_tables=2) is False


@pytest.mark.unit
def test_ocr_fallback_recovers_missed_tables_on_scanned_p11(scanned_p11_data: dict[str, Any]) -> None:
    """Verify fallback on scanned Page 11 recovers Mini-HD and all 3 tables with records."""
    ocr_words = [WordBox(**w) for w in scanned_p11_data["words"]]

    # Simulate Docling failure: TableFormer missed Mini-HD and only returned 1 or 2 partial tables
    failed_docling_tables = [{"table_id": "partial_table_1"}]

    recovered_tables: list[TableZone] = extract_tables_with_ocr_fallback(
        words=ocr_words,
        page_width=scanned_p11_data["page_width"],
        page_height=scanned_p11_data["page_height"],
        docling_tables=failed_docling_tables,
        min_expected_tables=3,
    )

    assert len(recovered_tables) == 3, f"Expected 3 recovered tables, got {len(recovered_tables)}"

    titles = [t.title for t in recovered_tables]
    assert titles[0] == "Micro-HD v2 Series"
    assert titles[1] == "Mini-HD v2 Series"  # Previously missed by Docling
    assert titles[2] == "Mag-HD v2 Series"

    # Positively assert Mini-HD (the missed table) has recovered structured records
    mini_hd_table = recovered_tables[1]
    assert mini_hd_table.title == "Mini-HD v2 Series"
    assert len(mini_hd_table.records) > 0, "Mini-HD table should have extracted attribute records"

    # Positively assert all recovered tables contain structured records
    for t in recovered_tables:
        assert len(t.records) > 0
