"""Unit tests for OCR accuracy and evaluation metrics (Item 1: Metric Sanity).

Tests:
1. Born-digital text vs itself gives F1 = 100% and CER = 0.0%.
2. Shuffled text gives F1 = 100% and high CER.
3. '441-481lbs' vs '441 - 481 lbs' matches identically after token normalization.
4. Strict duplicate handling via multiset (Counter) matching.
5. End-to-end verification on sample_1.pdf Page 11 born-digital text.
"""

from __future__ import annotations

import random
from pathlib import Path

import pymupdf
import pytest

from eval.metrics.ocr import (
    compute_cer,
    compute_numeric_token_recall,
    compute_token_f1,
    extract_numeric_tokens,
    normalize_tokens,
)


def test_born_digital_vs_itself_perfect_match() -> None:
    """Born-digital text compared to itself must give 100% F1 and 0.0% CER."""
    sample_text = (
        "Micro-HD Technical Specifications: 24 VDC System, 130 ah Battery, "
        "Weight 441 - 481 lbs (200 - 218 kg), Scrub Deck: Disk 20 inch, 0.75 hp Motor."
    )
    tokens = normalize_tokens(sample_text)
    p, r, f1 = compute_token_f1(tokens, tokens)
    cer = compute_cer(sample_text, sample_text)

    assert p == pytest.approx(1.0)
    assert r == pytest.approx(1.0)
    assert f1 == pytest.approx(1.0)
    assert cer == pytest.approx(0.0)


def test_shuffled_text_high_f1_high_cer() -> None:
    """Shuffled words must preserve ~100% token F1 (order-invariant) but yield a high CER."""
    words = [
        "chassis", "construction", "3/16", "steel", "disk", "cylindrical",
        "orbital", "actuator", "downpressure", "scrub", "deck", "441", "481", "lbs"
    ]
    gt_text = " ".join(words)

    # Deterministically shuffle tokens
    rng = random.Random(42)
    shuffled_words = list(words)
    rng.shuffle(shuffled_words)
    shuffled_text = " ".join(shuffled_words)

    gt_tokens = normalize_tokens(gt_text)
    shuffled_tokens = normalize_tokens(shuffled_text)

    p, r, f1 = compute_token_f1(gt_tokens, shuffled_tokens)
    cer = compute_cer(gt_text, shuffled_text)

    assert f1 == pytest.approx(1.0), "Order-invariant token F1 should be 100% for shuffled tokens"
    assert cer > 0.40, f"Expected high CER for shuffled text, got {cer:.2%}"


def test_range_and_unit_normalization() -> None:
    """'441-481lbs' vs '441 - 481 lbs' must match identically after normalization."""
    t1 = "Weight: 441-481lbs (200-218kg)"
    t2 = "Weight: 441 - 481 lbs (200 - 218 kg)"

    toks1 = normalize_tokens(t1)
    toks2 = normalize_tokens(t2)

    assert toks1 == toks2, f"Tokens differ: {toks1} vs {toks2}"
    p, r, f1 = compute_token_f1(toks1, toks2)
    assert f1 == pytest.approx(1.0)

    # Also test numeric token extraction specifically
    nums1 = extract_numeric_tokens(t1)
    nums2 = extract_numeric_tokens(t2)
    assert nums1 == ["441", "481", "200", "218"]
    assert nums2 == ["441", "481", "200", "218"]
    assert nums1 == nums2


def test_duplicate_handling_multiset_matching() -> None:
    """Multiset matching must enforce 1-to-1 correspondence for repeated tokens."""
    # GT has two '24's and one '36'; OCR only extracted one '24' and one '36'
    gt_toks = ["24", "24", "36"]
    ocr_toks = ["24", "36"]

    p, r, f1 = compute_token_f1(gt_toks, ocr_toks)
    # Matched = 2 ("24" and "36"). GT count = 3 -> Recall = 2/3 = 66.67%
    assert p == pytest.approx(1.0)
    assert r == pytest.approx(2 / 3)
    assert f1 == pytest.approx(2 * 1.0 * (2 / 3) / (1.0 + 2 / 3))

    # Over-generation in OCR
    ocr_extra = ["24", "24", "24", "36"]
    p_ex, r_ex, f1_ex = compute_token_f1(gt_toks, ocr_extra)
    # Matched = 3 (two "24"s and one "36"). OCR count = 4 -> Precision = 3/4 = 75%
    assert p_ex == pytest.approx(0.75)
    assert r_ex == pytest.approx(1.0)

    # compute_numeric_token_recall check
    rec, matched, missed = compute_numeric_token_recall("24 VDC 24V 36 in", "24 VDC 36 in")
    assert rec == pytest.approx(2 / 3)
    assert matched == ["24", "36"]
    assert missed == ["24"]


def test_page11_ground_truth_self_evaluation() -> None:
    """Evaluate Page 11 of sample_1.pdf against itself."""
    pdf_path = Path(__file__).resolve().parents[2] / "benchmark" / "sample_1.pdf"
    if not pdf_path.exists():
        pytest.skip("sample_1.pdf not found")

    doc = pymupdf.open(pdf_path)
    p11_text = doc[10].get_text()
    doc.close()

    gt_tokens = normalize_tokens(p11_text)
    gt_nums = extract_numeric_tokens(p11_text)

    # Self-match checks
    _, _, f1_full = compute_token_f1(gt_tokens, gt_tokens)
    rec_num, matched, missed = compute_numeric_token_recall(p11_text, p11_text)
    cer = compute_cer(p11_text, p11_text)

    assert f1_full == pytest.approx(1.0)
    assert rec_num == pytest.approx(1.0)
    assert len(missed) == 0
    assert cer == pytest.approx(0.0)
