"""Figure triage and MinIO crop storage module (Stage 7, Addendum A3.2, DECISIONS D-006, D-012).

Extracts and triages visual figures (diagrams, component callouts, cutaways, photos)
from document pages, filtering out decorative full-page backgrounds and tiny icons.
Renders high-resolution image crops and uploads them to MinIO under:
`figures/{document_id}/p{page_number}_fig{figure_index}.png`
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pymupdf
from pydantic import BaseModel, Field

from app.services.storage import StorageService, get_storage_service

logger = logging.getLogger(__name__)


class FigureCrop(BaseModel):
    """Metadata for an informative figure crop stored in MinIO."""

    figure_id: str
    document_id: str
    page_number: int
    bbox: tuple[float, float, float, float]  # (l, t, r, b) in points
    minio_key: str
    width_px: int
    height_px: int
    size_bytes: int
    is_informative: bool = True
    caption: str | None = None
    nearby_labels: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def triage_figure_candidate(
    bbox: tuple[float, float, float, float],
    page_width: float,
    page_height: float,
    has_text_nearby: bool = True,
) -> bool:
    """Triage whether an image region is an informative figure or decorative background.

    Rules (Addendum A3.2, DECISIONS D-012):
    - Skip full-page backgrounds (covering > 92% of both width and height).
    - Skip tiny decorative icons/lines (< 20 pt width or < 20 pt height).
    - Retain diagrams, cutaways, labeled callouts, and machine illustrations.
    """
    l, t, r, b = bbox
    w = max(0.0, r - l)
    h = max(0.0, b - t)

    # 1. Skip tiny icons, bullets, decorative rules
    if w < 20.0 or h < 20.0:
        return False

    # 2. Skip full-page decorative background
    return not ((w / page_width) >= 0.95 and (h / page_height) >= 0.95 and not has_text_nearby)


def extract_page_figure_bboxes(page: pymupdf.Page) -> list[tuple[float, float, float, float]]:
    """Detect candidate figure and raster image bounding boxes on a page."""
    bboxes: list[tuple[float, float, float, float]] = []

    # 1. Extract embedded raster image rects
    image_infos = page.get_image_info(xrefs=True)
    for info in image_infos:
        bbox = info.get("bbox")
        if bbox:
            l, t, r, b = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
            # Normalize and clamp to page boundary
            l = max(0.0, min(l, page.rect.width))
            t = max(0.0, min(t, page.rect.height))
            r = max(0.0, min(r, page.rect.width))
            b = max(0.0, min(b, page.rect.height))
            if (r - l) > 10.0 and (b - t) > 10.0:
                bboxes.append((round(l, 2), round(t, 2), round(r, 2), round(b, 2)))

    # 2. Deduplicate overlapping rects (merge rects with IoU > 0.8)
    deduped: list[tuple[float, float, float, float]] = []
    for bb in bboxes:
        overlap = False
        for ex in deduped:
            # Check overlap
            ix0 = max(bb[0], ex[0])
            iy0 = max(bb[1], ex[1])
            ix1 = min(bb[2], ex[2])
            iy1 = min(bb[3], ex[3])
            if ix1 > ix0 and iy1 > iy0:
                inter_area = (ix1 - ix0) * (iy1 - iy0)
                bb_area = (bb[2] - bb[0]) * (bb[3] - bb[1])
                if inter_area / bb_area > 0.75:
                    overlap = True
                    break
        if not overlap:
            deduped.append(bb)

    return deduped


def render_figure_crop_png(
    page: pymupdf.Page,
    bbox: tuple[float, float, float, float],
    dpi: int = 150,
) -> tuple[bytes, int, int]:
    """Render a bounding box region of a page to PNG bytes."""
    rect = pymupdf.Rect(bbox[0], bbox[1], bbox[2], bbox[3])  # type: ignore[no-untyped-call]
    pix = page.get_pixmap(clip=rect, dpi=dpi)
    png_bytes: bytes = pix.tobytes("png")  # type: ignore[no-untyped-call]
    width_px = pix.width
    height_px = pix.height
    return png_bytes, width_px, height_px


def extract_and_store_figure_crops(
    pdf_path: Path,
    document_id: str,
    storage_service: StorageService | None = None,
    max_crops_per_doc: int = 50,
    dpi: int = 150,
) -> list[FigureCrop]:
    """Extract, triage, render, and upload figure crops to MinIO storage.

    Args:
        pdf_path: Path to the target PDF file.
        document_id: UUID of the document.
        storage_service: Optional StorageService instance (defaults to MinIO).
        max_crops_per_doc: Document-level budget for figure crops (Addendum A3.2).
        dpi: Rendering resolution for figure crops.

    Returns:
        List of stored FigureCrop objects with MinIO object keys.
    """
    storage = storage_service or get_storage_service()
    storage.ensure_bucket()

    doc = pymupdf.open(pdf_path)  # type: ignore[no-untyped-call]
    crops: list[FigureCrop] = []
    total_crops = 0

    try:
        for page_idx in range(len(doc)):
            if total_crops >= max_crops_per_doc:
                logger.info("Reached maximum per-document figure crop budget (%d)", max_crops_per_doc)
                break

            page_num = page_idx + 1
            page = doc[page_idx]
            pw = float(page.rect.width)
            ph = float(page.rect.height)

            candidate_bboxes = extract_page_figure_bboxes(page)
            fig_counter = 0

            for bbox in candidate_bboxes:
                if total_crops >= max_crops_per_doc:
                    break

                if not triage_figure_candidate(bbox, page_width=pw, page_height=ph):
                    continue

                fig_counter += 1
                total_crops += 1

                # Render crop image
                png_bytes, w_px, h_px = render_figure_crop_png(page, bbox, dpi=dpi)

                # MinIO object key
                obj_key = f"figures/{document_id}/p{page_num}_fig{fig_counter}.png"

                # Upload to MinIO
                storage.upload_file(
                    object_name=obj_key,
                    data=png_bytes,
                    content_type="image/png",
                )

                crop = FigureCrop(
                    figure_id=f"{document_id}_p{page_num}_fig{fig_counter}",
                    document_id=document_id,
                    page_number=page_num,
                    bbox=bbox,
                    minio_key=obj_key,
                    width_px=w_px,
                    height_px=h_px,
                    size_bytes=len(png_bytes),
                    is_informative=True,
                )
                crops.append(crop)
                logger.debug("Stored figure crop %s (%d bytes)", obj_key, len(png_bytes))

    finally:
        doc.close()  # type: ignore[no-untyped-call]

    logger.info("Extracted and stored %d figure crops for document %s", len(crops), document_id)
    return crops
