"""Unit tests for Stage 7: Figure Triage & MinIO Crop Storage (Addendum A3.2, DECISIONS D-006, D-012).

Verifies:
1. Figure triage logic: rejects full-page backgrounds and tiny icons; retains informative diagrams.
2. High-resolution crop rendering to valid PNG bytes.
3. Real MinIO upload: verifies objects are stored in the bucket and accessible via presigned URLs.
4. Per-document budget enforcement.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from app.ingestion.figures import (
    FigureCrop,
    classify_and_triage_figure,
    extract_and_store_figure_crops,
    render_figure_crop_png,
    triage_figure_candidate,
)
from app.services.storage import get_storage_service

BENCHMARK_PDF = Path(__file__).parents[2] / "benchmark" / "sample_1.pdf"


@pytest.mark.unit
def test_triage_figure_candidate() -> None:
    """Verify triage filters out background rectangles and tiny icons while accepting diagrams."""
    # 1. Tiny icon (15x15 pt) -> False
    assert (
        triage_figure_candidate(bbox=(10.0, 10.0, 25.0, 25.0), page_width=792.0, page_height=633.6)
        is False
    )

    # 2. Full-page background (780x620 pt on 792x633 page without text) -> False
    assert triage_figure_candidate(
        bbox=(5.0, 5.0, 788.0, 630.0),
        page_width=792.0,
        page_height=633.6,
        has_text_nearby=False,
    ) is False

    # 3. Informative diagram / cutaway (300x200 pt) -> True
    assert triage_figure_candidate(
        bbox=(100.0, 150.0, 450.0, 400.0),
        page_width=792.0,
        page_height=633.6,
    ) is True


@pytest.mark.unit
def test_synthetic_page_with_corporate_keywords_keeps_labelled_diagram() -> None:
    """Verify that a page containing corporate keywords ('family owned', 'distributor')

    does NOT suppress an informative technical diagram on the same page.
    """
    page_text = (
        "We are a proud family owned business and international distributor of high quality "
        "industrial machinery with a strong heritage of manufacturing excellence."
    )
    # Diagram region: 320x220 pt with 8 vector drawings and 12 callout words
    diagram_bbox = (150.0, 100.0, 470.0, 320.0)

    is_informative, flag, score, reason = classify_and_triage_figure(
        bbox=diagram_bbox,
        page_width=792.0,
        page_height=633.6,
        drawings_count=8,
        words_count=12,
        page_text=page_text,
    )

    assert is_informative is True, f"Labelled diagram must be kept informative despite corporate text, reason: {reason}"
    assert flag == "informative"
    assert score >= 85.0


@pytest.mark.unit
def test_containment_duplicates_deduplication() -> None:
    """Verify that smaller inner figure candidate is retained when an outer container duplicates it."""
    from app.ingestion.figures import remove_containment_duplicates

    # Cand A: Outer container (0, 0, 400, 300)
    # Cand B: Inner figure (10, 10, 390, 290) - >90% contained in A
    # Cand C: Separate figure (500, 50, 700, 250) - no overlap
    cands = [
        ((0.0, 0.0, 400.0, 300.0), (800, 600)),
        ((10.0, 10.0, 390.0, 290.0), (800, 600)),
        ((500.0, 50.0, 700.0, 250.0), (400, 400)),
    ]
    deduped = remove_containment_duplicates(cands, containment_threshold=0.85)

    # Should retain 2 candidates (the tighter inner box and the separate candidate)
    assert len(deduped) == 2
    bboxes = [c[0] for c in deduped]
    assert (10.0, 10.0, 390.0, 290.0) in bboxes
    assert (500.0, 50.0, 700.0, 250.0) in bboxes


@pytest.mark.unit
def test_trim_crop_avoiding_half_words() -> None:
    """Verify that bounding box edges are trimmed inward to avoid half-words from neighbouring text."""
    from app.ingestion.figures import trim_crop_avoiding_half_words

    # Initial candidate box: (100, 100, 400, 300)
    # Word 1: partially straddles the right border (starts at 395, ends at 420)
    # Word 2: fully inside (150, 150, 200, 165)
    # Word 3: completely outside (500, 500, 550, 520)
    page_words = [
        (395.0, 120.0, 420.0, 135.0, "neighbouring"),
        (150.0, 150.0, 200.0, 165.0, "callout"),
        (500.0, 500.0, 550.0, 520.0, "outside"),
    ]

    trimmed = trim_crop_avoiding_half_words((100.0, 100.0, 400.0, 300.0), page_words)

    # Right edge should be pulled inward before x=395.0 so no half-word appears
    assert trimmed[2] <= 395.0
    assert trimmed[0] == 100.0
    assert trimmed[1] == 100.0
    assert trimmed[3] == 300.0


@pytest.mark.unit
def test_render_figure_crop_png() -> None:
    """Verify figure crop rendering produces valid PNG image bytes."""
    assert BENCHMARK_PDF.exists(), "Benchmark sample_1.pdf required"
    doc = pymupdf.open(BENCHMARK_PDF)  # type: ignore[no-untyped-call]
    try:
        # Page 4 (cutaway diagram)
        page = doc[3]
        bbox = (50.0, 100.0, 400.0, 400.0)
        png_bytes, w_px, h_px = render_figure_crop_png(page, bbox, dpi=150)

        assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n"), "Must produce valid PNG magic bytes"
        assert w_px > 0
        assert h_px > 0
        assert len(png_bytes) > 1000, "Rendered crop should contain substantial image data"
    finally:
        doc.close()  # type: ignore[no-untyped-call]


@pytest.mark.integration
def test_extract_and_store_figure_crops_minio() -> None:
    """Verify figure extraction, budget capping, and storage in real MinIO container."""
    assert BENCHMARK_PDF.exists(), "Benchmark sample_1.pdf required"
    storage = get_storage_service()
    storage.ensure_bucket()

    doc_id = "test_fig_doc_123"
    max_budget = 3

    crops: list[FigureCrop] = extract_and_store_figure_crops(
        pdf_path=BENCHMARK_PDF,
        document_id=doc_id,
        storage_service=storage,
        max_crops_per_doc=max_budget,
    )

    try:
        assert len(crops) <= max_budget, f"Should respect budget {max_budget}, got {len(crops)}"
        assert len(crops) > 0, "Should extract at least one figure crop"

        for crop in crops:
            assert crop.document_id == doc_id
            assert crop.minio_key.startswith(f"figures/{doc_id}/")
            assert crop.size_bytes > 0

            # Positively assert object exists in MinIO
            assert storage.object_exists(crop.minio_key), f"MinIO object {crop.minio_key} must exist"

            # Verify presigned URL can be generated
            url = storage.get_presigned_download_url(crop.minio_key)
            assert f"figures/{doc_id}" in url or "http" in url

    finally:
        # Cleanup uploaded test crops from MinIO
        for crop in crops:
            storage.delete_file(crop.minio_key)
