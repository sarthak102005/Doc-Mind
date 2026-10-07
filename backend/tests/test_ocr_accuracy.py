"""Unit tests for Stage 8: OCR Accuracy & Evaluation Metrics (Addendum A2.2, Done Criteria).

Verifies:
1. Levenshtein edit distance and CER calculation logic.
2. Numeric token extraction and recall calculation.
3. Body text CER on benchmark sample pages meets the < 5% target (Page 2, 3, 4).
4. Numeric token recall on Page 11 technical specifications is calculated and verified.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingestion.reading_order import WordBox, reconstruct_reading_order
from eval.metrics.ocr import (
    clean_line_text,
    compute_aligned_cer,
    compute_numeric_token_recall,
    extract_numeric_tokens,
    levenshtein_distance,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.unit
def test_levenshtein_distance() -> None:
    """Verify Levenshtein distance calculations on simple strings."""
    assert levenshtein_distance("", "") == 0
    assert levenshtein_distance("kitten", "sitting") == 3
    assert levenshtein_distance("Micro-HD", "Micro-HD") == 0
    assert levenshtein_distance("Micro-HD", "Micro HD") == 1


@pytest.mark.unit
def test_numeric_token_extraction_and_recall() -> None:
    """Verify numeric token extraction and recall calculation."""
    gt_text = "Run time: 2.5 h for Micro-HD, 3.5 h for Mini-HD, 5.0 h for Mag-HD. 130 Ah or 210 Ah."
    ocr_text = "Run time: 2.5 h for Micro-HD, 3.5 h for Mini-HD, 5.0 h for Mag-HD. 130 Ah."

    tokens = extract_numeric_tokens(gt_text)
    assert tokens == ["2.5", "3.5", "5.0", "130", "210"]

    recall, matched, missed = compute_numeric_token_recall(gt_text, ocr_text)
    assert recall == 4 / 5  # 80%
    assert matched == ["2.5", "3.5", "5.0", "130"]
    assert missed == ["210"]


@pytest.mark.unit
def test_page_2_body_text_cer_under_five_percent() -> None:
    """Verify Page 2 body text CER on scanned OCR against digital ground truth is under 5%."""
    p2_dig_path = FIXTURES_DIR / "wordboxes_sample_1_p2.json"
    p2_scan_path = FIXTURES_DIR / "wordboxes_sample_1_scanned_p2.json"

    assert p2_dig_path.exists() and p2_scan_path.exists()

    dig_data = json.loads(p2_dig_path.read_text("utf-8"))
    scan_data = json.loads(p2_scan_path.read_text("utf-8"))

    dig_boxes = [WordBox(**w) for w in dig_data["words"]]
    scan_boxes = [WordBox(**w) for w in scan_data["words"]]

    dig_blocks = reconstruct_reading_order(dig_boxes, 792.0, 633.6)
    scan_blocks = reconstruct_reading_order(scan_boxes, 792.0, 633.6)

    # Clean lines and filter out boilerplate / footer text
    dig_lines = [
        clean_line_text(b.text)
        for b in dig_blocks
        if len(clean_line_text(b.text)) > 3
        and not any(
            k in b.text.lower() for k in ["factorycat.com", "rps corporation", "fc-walk-behind"]
        )
    ]
    scan_lines = [
        clean_line_text(b.text) for b in scan_blocks if len(clean_line_text(b.text)) > 3
    ]

    cer, edits, gt_chars = compute_aligned_cer(dig_lines, scan_lines)

    # Done criterion: CER under 5% on body text (actual ~1.75%)
    assert cer < 0.05, f"Expected CER < 0.05, got {cer:.4f} ({edits}/{gt_chars} edits)"


@pytest.mark.unit
def test_page_3_and_4_body_text_cer() -> None:
    """Verify Page 3 and Page 4 body text lines achieve low CER against digital ground truth."""
    for page_num in (3, 4):
        dig_path = FIXTURES_DIR / f"wordboxes_sample_1_p{page_num}.json"
        scan_path = FIXTURES_DIR / f"wordboxes_sample_1_scanned_p{page_num}.json"
        if not dig_path.exists() or not scan_path.exists():
            continue

        dig_data = json.loads(dig_path.read_text("utf-8"))
        scan_data = json.loads(scan_path.read_text("utf-8"))

        dig_boxes = [WordBox(**w) for w in dig_data["words"]]
        scan_boxes = [WordBox(**w) for w in scan_data["words"]]

        dig_blocks = reconstruct_reading_order(dig_boxes, 792.0, 633.6)
        scan_blocks = reconstruct_reading_order(scan_boxes, 792.0, 633.6)

        dig_lines = [
            clean_line_text(b.text)
            for b in dig_blocks
            if len(clean_line_text(b.text)) > 3
            and not any(
                k in b.text.lower()
                for k in ["factorycat.com", "rps corporation", "fc-walk-behind"]
            )
        ]
        scan_lines = [
            clean_line_text(b.text) for b in scan_blocks if len(clean_line_text(b.text)) > 3
        ]

        cer, edits, gt_chars = compute_aligned_cer(dig_lines, scan_lines)
        assert cer < 0.05, f"Expected Page {page_num} CER < 0.05, got {cer:.4f} ({edits}/{gt_chars})"


@pytest.mark.unit
def test_page_11_spec_numeric_recall() -> None:
    """Verify numeric recall on Page 11 and ensure key runtime specs are captured."""
    p11_dig_path = FIXTURES_DIR / "wordboxes_sample_1_p11.json"
    p11_scan_path = FIXTURES_DIR / "wordboxes_sample_1_scanned_p11.json"

    assert p11_dig_path.exists() and p11_scan_path.exists()

    p11_dig_words = json.loads(p11_dig_path.read_text("utf-8"))["words"]
    p11_scan_words = json.loads(p11_scan_path.read_text("utf-8"))["words"]

    dig_text = " ".join(w["text"] for w in p11_dig_words)
    scan_text = " ".join(w["text"] for w in p11_scan_words)

    recall, matched, _ = compute_numeric_token_recall(dig_text, scan_text)

    # Must recall substantial proportion (> 70%) on dense scanned raster
    assert recall > 0.70, f"Expected numeric recall > 0.70, got {recall:.4f}"

    # Critical spec numbers must be recalled in the scanned OCR tokens
    for spec_val in ["2.5", "3.5", "5.0", "130", "210"]:
        assert spec_val in matched, f"Critical spec value {spec_val} should be recalled"
