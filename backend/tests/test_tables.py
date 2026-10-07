"""Unit tests for Stage 4: Table Extraction & Spatial X-Gap Projection (Addendum A2.5, DECISIONS D-010).

Verifies:
1. Dynamic table zone derivation from word box X-distribution gaps (no hardcoded coordinates).
2. Title proximity linking directly above each detected column zone.
3. Page 11 digital sample extracts 3 separate tables: Micro-HD, Mini-HD, Mag-HD.
4. Page 11 scanned sample extracts 3 separate tables: Micro-HD, Mini-HD, Mag-HD.
5. Perturbation invariance: scaling and shifting all bounding boxes produces identical results.
6. Structured record extraction preserves sections, attributes, and values.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.ingestion.reading_order import WordBox
from app.ingestion.tables import (
    TableZone,
    detect_table_zones_from_x_gaps,
    find_x_distribution_gaps,
    format_table_as_markdown,
    perturb_wordboxes,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def digital_p11_data() -> dict[str, Any]:
    with open(FIXTURES_DIR / "wordboxes_sample_1_p11.json", encoding="utf-8") as f:
        res: dict[str, Any] = json.load(f)
        return res


@pytest.fixture
def scanned_p11_data() -> dict[str, Any]:
    with open(FIXTURES_DIR / "wordboxes_sample_1_scanned_p11.json", encoding="utf-8") as f:
        res: dict[str, Any] = json.load(f)
        return res


@pytest.mark.unit
def test_find_x_distribution_gaps() -> None:
    """Verify that gaps between horizontal word boxes are detected accurately."""
    words = [
        # Column 1: x in [10, 50]
        WordBox(text="A", l=10.0, t=10.0, r=30.0, b=20.0),
        WordBox(text="B", l=35.0, t=10.0, r=50.0, b=20.0),
        # Gap: [50, 70] (width 20)
        # Column 2: x in [70, 110]
        WordBox(text="C", l=70.0, t=10.0, r=90.0, b=20.0),
        WordBox(text="D", l=95.0, t=10.0, r=110.0, b=20.0),
    ]
    gaps = find_x_distribution_gaps(words, page_width=200.0, min_gutter_pt=10.0)
    assert len(gaps) == 1
    assert gaps[0][0] == 50.0
    assert gaps[0][1] == 70.0


@pytest.mark.unit
def test_digital_page_11_three_tables_extracted(digital_p11_data: dict[str, Any]) -> None:
    """Verify that Digital Page 11 segments into 3 distinct tables with titles linked."""
    words = [WordBox(**w) for w in digital_p11_data["words"]]
    tables: list[TableZone] = detect_table_zones_from_x_gaps(
        words,
        page_width=digital_p11_data["page_width"],
        page_height=digital_p11_data["page_height"],
    )

    assert len(tables) == 3, f"Expected 3 tables, found {len(tables)}"

    titles = [t.title for t in tables]
    assert titles[0] == "Micro-HD v2 Series"
    assert titles[1] == "Mini-HD v2 Series"
    assert titles[2] == "Mag-HD v2 Series"

    # Positively assert section headers exist in each table
    for t in tables:
        assert any("BODY CONSTRUCTION" in sec for sec in t.sections), (
            f"Table '{t.title}' missing BODY CONSTRUCTION section. Found: {t.sections}"
        )
        assert any("BRUSH" in sec for sec in t.sections), (
            f"Table '{t.title}' missing BRUSH section. Found: {t.sections}"
        )

    # Positively assert attributes in Table 0 (Micro-HD)
    t0_attrs = {r.attribute: r.value for r in tables[0].records}
    assert any("Chassis Construction" in attr for attr in t0_attrs)
    assert any("Weight" in attr for attr in t0_attrs)


@pytest.mark.unit
def test_scanned_page_11_three_tables_extracted(scanned_p11_data: dict[str, Any]) -> None:
    """Verify that Scanned Page 11 also segments into 3 distinct tables with correct titles."""
    words = [WordBox(**w) for w in scanned_p11_data["words"]]
    tables: list[TableZone] = detect_table_zones_from_x_gaps(
        words,
        page_width=scanned_p11_data["page_width"],
        page_height=scanned_p11_data["page_height"],
    )

    assert len(tables) == 3, f"Expected 3 tables on scanned page 11, found {len(tables)}"

    titles = [t.title for t in tables]
    assert titles[0] == "Micro-HD v2 Series"
    assert titles[1] == "Mini-HD v2 Series"
    assert titles[2] == "Mag-HD v2 Series"

    for t in tables:
        assert len(t.records) > 0, f"Table '{t.title}' should have extracted records"


@pytest.mark.unit
def test_perturbation_invariance_on_page_11(digital_p11_data: dict[str, Any]) -> None:
    """Verify that scaling and shifting all bounding boxes produces identical table segmentation."""
    orig_words = [WordBox(**w) for w in digital_p11_data["words"]]
    orig_tables = detect_table_zones_from_x_gaps(
        orig_words,
        page_width=digital_p11_data["page_width"],
        page_height=digital_p11_data["page_height"],
    )

    # 1. Proportional 2D coordinate scaling perturbation
    scale_x = 1.35
    scale_y = 0.85

    scaled_words = perturb_wordboxes(
        orig_words,
        scale_x=scale_x,
        scale_y=scale_y,
    )
    scaled_page_w = digital_p11_data["page_width"] * scale_x
    scaled_page_h = digital_p11_data["page_height"] * scale_y

    scaled_tables = detect_table_zones_from_x_gaps(
        scaled_words,
        page_width=scaled_page_w,
        page_height=scaled_page_h,
    )

    assert len(scaled_tables) == len(orig_tables) == 3
    for orig_t, scaled_t in zip(orig_tables, scaled_tables, strict=True):
        assert orig_t.title == scaled_t.title
        assert len(orig_t.words) == len(scaled_t.words)

    # 2. Coordinate translation / shift perturbation
    shift_x = 50.0
    shifted_words = perturb_wordboxes(
        orig_words,
        shift_x=shift_x,
    )
    shifted_page_w = digital_p11_data["page_width"] + shift_x * 2

    shifted_tables = detect_table_zones_from_x_gaps(
        shifted_words,
        page_width=shifted_page_w,
        page_height=digital_p11_data["page_height"],
    )

    assert len(shifted_tables) == len(orig_tables) == 3
    for orig_t, shifted_t in zip(orig_tables, shifted_tables, strict=True):
        assert orig_t.title == shifted_t.title
        assert len(orig_t.words) == len(shifted_t.words)


@pytest.mark.unit
def test_synthetic_table_perturbation() -> None:
    """Verify perturbation invariance on a synthetic two-table comparison layout."""
    base_words = [
        # Table A (left)
        WordBox(text="Option Alpha", l=30.0, t=100.0, r=120.0, b=115.0),
        WordBox(text="SPECS", l=30.0, t=130.0, r=80.0, b=140.0),
        WordBox(text="Speed: 50 mph", l=30.0, t=150.0, r=130.0, b=162.0),
        WordBox(text="Range: 300 mi", l=30.0, t=170.0, r=130.0, b=182.0),
        # Table B (right) - gap [130, 200]
        WordBox(text="Option Beta", l=200.0, t=100.0, r=280.0, b=115.0),
        WordBox(text="SPECS", l=200.0, t=130.0, r=250.0, b=140.0),
        WordBox(text="Speed: 70 mph", l=200.0, t=150.0, r=300.0, b=162.0),
        WordBox(text="Range: 450 mi", l=200.0, t=170.0, r=300.0, b=182.0),
    ]

    page_w = 400.0
    page_h = 600.0

    tables = detect_table_zones_from_x_gaps(base_words, page_width=page_w, page_height=page_h)
    assert len(tables) == 2
    assert tables[0].title == "Option Alpha"
    assert tables[1].title == "Option Beta"

    # Perturb
    pert_words = perturb_wordboxes(base_words, scale_x=1.5, scale_y=1.2, shift_x=30.0, shift_y=20.0)
    pert_tables = detect_table_zones_from_x_gaps(
        pert_words,
        page_width=page_w * 1.5 + 60.0,
        page_height=page_h * 1.2 + 40.0,
    )

    assert len(pert_tables) == 2
    assert pert_tables[0].title == "Option Alpha"
    assert pert_tables[1].title == "Option Beta"
    assert len(tables[0].words) == len(pert_tables[0].words)
    assert len(tables[1].words) == len(pert_tables[1].words)


@pytest.mark.unit
def test_format_table_as_markdown(digital_p11_data: dict[str, Any]) -> None:
    """Verify markdown table formatting contains expected markdown structure."""
    words = [WordBox(**w) for w in digital_p11_data["words"]]
    tables = detect_table_zones_from_x_gaps(
        words,
        page_width=digital_p11_data["page_width"],
        page_height=digital_p11_data["page_height"],
    )

    md = format_table_as_markdown(tables[0])
    assert "### Micro-HD v2 Series" in md
    assert "| Section | Attribute | Value |" in md
    assert "| --- | --- | --- |" in md
    assert "BODY CONSTRUCTION" in md
