"""Page profiling and ingestion routing module.

Inspects document pages to determine text character density, image area ratio,
text layer quality, and column layout, routing pages to text_native, hybrid,
or scanned_raster pipelines.
"""

from __future__ import annotations

import string
import time
from pathlib import Path
from typing import Any

import pymupdf
from pydantic import BaseModel, Field

from app.core.config import get_settings


class PageProfileResult(BaseModel):
    """Profile metrics and routing decision for a single document page."""

    page_number: int = Field(..., description="1-indexed page number")
    char_count: int = Field(..., description="Total characters extracted natively")
    char_density: float = Field(..., description="Characters per square point of page area")
    text_quality: float = Field(..., description="Score 0.0-1.0 measuring printable text layer quality")
    image_area_ratio: float = Field(
        ..., description="Ratio of page area covered by raster images (0.0 to 1.0)"
    )
    image_count: int = Field(..., description="Number of embedded raster images on page")
    column_count_est: int = Field(default=1, description="Estimated number of text columns (1, 2, 3+)")
    has_text_layer: bool = Field(..., description="Whether a native searchable text layer exists")
    route: str = Field(..., description="Ingestion route: 'text_native', 'hybrid', or 'scanned'")
    page_width: float = Field(..., description="Width of page in points")
    page_height: float = Field(..., description="Height of page in points")
    duration_ms: float = Field(default=0.0, description="Profiling latency in milliseconds")
    profile_metadata: dict[str, Any] = Field(default_factory=dict, description="Detailed profile metadata")


def calculate_text_quality(text: str) -> float:
    """Measure the quality of extracted text based on printable characters and word sanity."""
    clean = text.strip()
    if not clean:
        return 0.0

    valid_chars = set(
        string.ascii_letters + string.digits + string.whitespace + string.punctuation + "–—’“”°·±µ²/³\\"
    )
    total_len = len(clean)
    valid_count = sum(1 for c in clean if c in valid_chars)
    char_ratio = valid_count / total_len

    words = clean.split()
    if not words:
        return 0.0

    avg_len = sum(len(w) for w in words) / len(words)
    # Natural language words typically average between 2.0 and 15.0 characters
    if 2.0 <= avg_len <= 15.0:
        word_sanity = 1.0
    elif avg_len < 2.0:
        word_sanity = max(0.0, avg_len / 2.0)
    else:
        word_sanity = max(0.0, 1.0 - (avg_len - 15.0) / 15.0)

    return round((char_ratio * 0.7) + (word_sanity * 0.3), 4)


def estimate_column_count(text_blocks: list[tuple[Any, ...]], page_width: float) -> int:
    """Estimate the number of text columns based on block horizontal bounding box clusters."""
    if len(text_blocks) < 3:
        return 1

    # Filter out full-width headers or footers spanning > 75% page width
    body_blocks = []
    for b in text_blocks:
        x0, _, x1, _ = b[:4]
        width = x1 - x0
        if width < (page_width * 0.75):
            body_blocks.append((x0, x1))

    if len(body_blocks) < 3:
        return 1

    midpoints = [(x0 + x1) / 2.0 for x0, x1 in body_blocks]
    col_width = page_width / 3.0
    bins = [0, 0, 0]
    for mid in midpoints:
        idx = min(2, int(mid // col_width))
        bins[idx] += 1

    active_columns = sum(1 for count in bins if count >= max(2, len(body_blocks) * 0.15))
    return max(1, active_columns)


def compute_rectangles_union_area(
    rects: list[pymupdf.Rect], page_rect: pymupdf.Rect
) -> float:
    """Compute the exact geometric union area of rectangles clipped to page boundary.

    Uses a 1D sweep-line algorithm (Klee's measure in 2D) to avoid inflating
    coverage when images overlap.
    """
    clipped: list[tuple[float, float, float, float]] = []
    for r in rects:
        c = pymupdf.Rect(r).intersect(page_rect)  # type: ignore[no-untyped-call]
        if not c.is_empty and c.width > 0 and c.height > 0:
            clipped.append((float(c.x0), float(c.y0), float(c.x1), float(c.y1)))

    if not clipped:
        return 0.0

    xs = sorted(set([c[0] for c in clipped] + [c[2] for c in clipped]))
    total_area = 0.0

    for i in range(len(xs) - 1):
        x_left, x_right = xs[i], xs[i + 1]
        dx = x_right - x_left
        if dx <= 0.0:
            continue

        y_intervals: list[tuple[float, float]] = [
            (c[1], c[3]) for c in clipped if c[0] <= x_left and c[2] >= x_right
        ]
        if not y_intervals:
            continue

        y_intervals.sort()
        merged_h = 0.0
        cur_y0, cur_y1 = y_intervals[0]
        for y0, y1 in y_intervals[1:]:
            if y0 <= cur_y1:
                cur_y1 = max(cur_y1, y1)
            else:
                merged_h += cur_y1 - cur_y0
                cur_y0, cur_y1 = y0, y1
        merged_h += cur_y1 - cur_y0
        total_area += dx * merged_h

    return float(total_area)


def profile_page(page: pymupdf.Page, page_number: int) -> PageProfileResult:
    """Profile a single PyMuPDF Page and decide the ingestion route.

    Route semantics:
    - 'text_native': Clean, sufficient native text layer with minimal image content.
      No OCR required.
    - 'scanned': Missing or corrupted text layer (e.g. unmapped font glyphs).
      Requires full-page OCR via RapidOCR.
    - 'hybrid': High-quality native text layer exists and is used as primary text stream,
      AND significant raster image regions exist.
      NOTE: Hybrid does NOT mean "OCR every image region". Native text is preserved directly.
      Region OCR runs ONLY for figures that pass informative triage (e.g. diagram callouts,
      spec badges), decorative full-page backgrounds are skipped, and invocations are
      capped by settings.max_region_ocr_per_doc.
    """
    t0 = time.perf_counter()
    settings = get_settings()

    rect = page.rect
    width = float(rect.width)
    height = float(rect.height)
    page_area = max(1.0, width * height)

    # 1. Native text layer inspection & quality check
    raw_text: str = page.get_text()  # type: ignore[no-untyped-call]
    clean_text = raw_text.strip()
    char_count = len(clean_text)
    char_density = round(char_count / page_area, 6)
    text_quality = calculate_text_quality(raw_text)

    # 2. Text blocks inspection for column estimation
    raw_blocks = page.get_text("blocks")  # type: ignore[no-untyped-call]
    text_blocks = [b for b in raw_blocks if b[4].strip() and b[6] == 0]
    column_est = estimate_column_count(text_blocks, width)

    # 3. Image inspection with union coverage (avoiding overlapping sum inflation)
    img_info_list = page.get_image_info(xrefs=True)
    image_count = len(img_info_list)
    image_rects = [pymupdf.Rect(info["bbox"]) for info in img_info_list]  # type: ignore[no-untyped-call]
    union_img_area = compute_rectangles_union_area(image_rects, rect)
    image_area_ratio = round(min(1.0, union_img_area / page_area), 4)

    # 4. Routing decision per settings thresholds (A2.1 / D-003)
    has_text_layer = (
        char_count >= settings.profile_min_text_chars
        and text_quality >= settings.profile_text_quality_threshold
    )

    if not has_text_layer:
        # Insufficient or corrupted text layer -> always requires OCR (scanned or hybrid)
        is_hybrid_fallback = char_count >= settings.profile_min_text_chars and image_area_ratio > 0.1
        route = "hybrid" if is_hybrid_fallback else "scanned"
    elif image_area_ratio > settings.profile_image_area_hybrid_threshold:
        route = "hybrid"
    else:
        route = "text_native"

    duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    return PageProfileResult(
        page_number=page_number,
        char_count=char_count,
        char_density=char_density,
        text_quality=text_quality,
        image_area_ratio=image_area_ratio,
        image_count=image_count,
        column_count_est=column_est,
        has_text_layer=has_text_layer,
        route=route,
        page_width=width,
        page_height=height,
        duration_ms=duration_ms,
        profile_metadata={
            "text_block_count": len(text_blocks),
            "line_count": len(clean_text.splitlines()),
        },
    )


def profile_document(pdf_path: str | Path) -> list[PageProfileResult]:
    """Profile all pages in a PDF document and return per-page profile results."""
    doc = pymupdf.open(str(pdf_path))  # type: ignore[no-untyped-call]
    profiles: list[PageProfileResult] = []
    try:
        for idx in range(len(doc)):
            page_profile = profile_page(doc[idx], page_number=idx + 1)
            profiles.append(page_profile)
    finally:
        doc.close()  # type: ignore[no-untyped-call]
    return profiles
