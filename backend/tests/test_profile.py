"""Unit tests for Stage 1: Page Profiler and Ingestion Router."""

from pathlib import Path

import pymupdf
import pytest

from app.ingestion.profile import (
    calculate_text_quality,
    estimate_column_count,
    profile_document,
    profile_page,
)

BENCHMARK_DIR = Path(__file__).resolve().parents[2] / "benchmark"
SAMPLE_DIGITAL = BENCHMARK_DIR / "sample_1.pdf"
SAMPLE_SCANNED = BENCHMARK_DIR / "sample_1_scanned.pdf"


@pytest.mark.unit
def test_calculate_text_quality_metric() -> None:
    """Verify text quality calculation distinguishes valid natural language from corrupted text."""
    # 1. High quality English text
    good_text = "The Micro-HD walk-behind scrubber features up to 2.5 hours of runtime and a 13-gallon tank."
    assert calculate_text_quality(good_text) > 0.90

    # 2. Corrupted text with font unmapping / invalid symbols
    corrupted_symbols = "\ufffd\ufffd\x00\x01\x02\x03\x04\x05\ufffd\ufffd\x1b\x1c\x1d\x1e\x1f" * 10
    assert calculate_text_quality(corrupted_symbols) <= 0.35

    # 3. Text with missing spaces (huge words from font decoding failure)
    huge_word_text = "abcdefghijklmnopqrstuvwxyz" * 10
    assert calculate_text_quality(huge_word_text) < 0.75

    # 4. Empty text
    assert calculate_text_quality("") == 0.0


@pytest.mark.unit
def test_synthetic_low_quality_text_layer_routing() -> None:
    """Verify that pages with low-quality or corrupted text layers are routed away from text_native."""
    # Create an in-memory single-page PDF with corrupted font encoding
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    page = doc.new_page(width=600, height=800)

    # Insert text with low printable quality (e.g. non-ascii symbols / unmapped glyphs)
    corrupted_text = "~ § ¶ ¤ ¥ ¦ © ¬ ® ¯ ° ± ² ³ µ ¶ · ¸ ¹ º » ¼ ½ ¾ ¿ " * 10
    page.insert_text((50, 50), corrupted_text)

    # Profile the synthetic corrupted page
    res = profile_page(page, page_number=1)
    doc.close()  # type: ignore[no-untyped-call]

    assert res.char_count >= 50
    assert res.text_quality < 0.65
    assert res.has_text_layer is False
    # Since text is garbage, it must not be routed to text_native
    assert res.route in ("scanned", "hybrid")


@pytest.mark.unit
def test_column_estimation_synthetic() -> None:
    """Verify column clustering estimates columns correctly from synthetic bounding blocks."""
    page_width = 800.0

    # 1. Single column text
    single_col_blocks = [
        (100.0, 100.0 + i * 30, 400.0, 120.0 + i * 30, f"Line {i}", i, 0)
        for i in range(5)
    ]
    assert estimate_column_count(single_col_blocks, page_width) == 1

    # 2. Three distinct columns (e.g. left ~100, center ~380, right ~650)
    three_col_blocks = [
        (50.0, 100.0, 220.0, 150.0, "Col 1 item 1", 0, 0),
        (50.0, 160.0, 220.0, 210.0, "Col 1 item 2", 1, 0),
        (300.0, 100.0, 480.0, 150.0, "Col 2 item 1", 2, 0),
        (300.0, 160.0, 480.0, 210.0, "Col 2 item 2", 3, 0),
        (560.0, 100.0, 740.0, 150.0, "Col 3 item 1", 4, 0),
        (560.0, 160.0, 740.0, 210.0, "Col 3 item 2", 5, 0),
    ]
    assert estimate_column_count(three_col_blocks, page_width) == 3


@pytest.mark.unit
def test_profile_digital_sample() -> None:
    """Verify that sample_1.pdf is profiled with active text layers and never routed to scanned."""
    assert SAMPLE_DIGITAL.exists(), f"Benchmark PDF missing: {SAMPLE_DIGITAL}"

    profiles = profile_document(SAMPLE_DIGITAL)
    assert len(profiles) == 12

    for p in profiles:
        assert p.char_count > 50, f"Page {p.page_number} has insufficient characters: {p.char_count}"
        assert p.has_text_layer is True
        assert p.text_quality > 0.85
        assert p.duration_ms >= 0.0
        assert p.route in ("text_native", "hybrid")
        assert p.route != "scanned"

    # Page 11 is the text-dense specification sheet
    p11 = profiles[10]
    assert p11.char_count > 5000
    assert p11.route == "text_native"
    assert p11.column_count_est >= 2


@pytest.mark.unit
def test_profile_scanned_sample() -> None:
    """Verify that raster sample_1_scanned.pdf is identified as scanned with zero native text."""
    assert SAMPLE_SCANNED.exists(), f"Benchmark PDF missing: {SAMPLE_SCANNED}"

    profiles = profile_document(SAMPLE_SCANNED)
    assert len(profiles) == 12

    for p in profiles:
        assert p.char_count < 10, f"Page {p.page_number} unexpectedly had text: {p.char_count}"
        assert p.has_text_layer is False
        assert p.text_quality == 0.0
        assert p.image_count >= 1
        assert p.image_area_ratio > 0.8
        assert p.duration_ms >= 0.0
        assert p.route == "scanned"
