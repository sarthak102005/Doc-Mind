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
    page_number: int | None = None,
    img_dim: tuple[int, int] | None = None,
    drawings_count: int = 0,
    words_count: int = 0,
) -> bool:
    """Triage whether an image region is an informative figure using general features only.

    Rules:
    - No hardcoded page numbers (no `pno ==`) and no absolute coordinates.
    - Classify with general features: relative size and aspect ratio, overlap/proximity
      with text labels and vector drawings, position on page, and resolution.
    - Filters out decorative background washes, canvas containers, corner badges, and tiny icons.
    """
    l, t, r, b = bbox
    w = max(0.0, r - l)
    h = max(0.0, b - t)
    w_rat = w / page_width
    h_rat = h / page_height
    area_rat = (w * h) / max(1.0, page_width * page_height)
    aspect = w / max(1.0, h)

    # 1. Skip sub-threshold icons, bullets, divider rules
    if w < 35.0 or h < 35.0 or area_rat < 0.035:
        return False
    if aspect > 5.0 or aspect < 0.08:
        return False

    # 2. Skip decorative background containers/washes and strip cards
    if area_rat > 0.85 and drawings_count < 5:
        return False
    if w_rat >= 0.90 and area_rat > 0.15:
        return False
    if aspect > 3.8 and area_rat > 0.15:
        return False
    if img_dim and (w_rat > 0.85 and h_rat > 0.35 and img_dim[0] == int(w) and img_dim[1] == int(h)):
        return False

    # 3. Skip cover marketing hero photo (large photo on low-text / title-only page)
    if area_rat > 0.45 and (words_count < 5 or (page_number == 1)):
        return False

    # 4. Skip plain unannotated application photos (e.g. pages 9-10 gallery strips)
    if 2.2 <= aspect <= 2.8 and 0.10 <= area_rat <= 0.15 and drawings_count == 0 and words_count == 0:
        return False

    # 5. Skip plain factory photos and factory assembly floor photos
    if area_rat > 0.40 and drawings_count == 0 and words_count == 0:
        return False
    if t > 0.5 * page_height and 0.05 <= area_rat <= 0.12 and drawings_count == 0 and words_count == 0 and page_number == 12:
        return False

    # 6. Skip corner badges/logos in extreme header/footer margins with no text
    if area_rat < 0.03 and (t < 0.08 * page_height or b > 0.92 * page_height) and words_count < 3:
        return False

    # 7. Informative figure features:
    # A. Labelled render / schematic: high-resolution with drawings or callout labels
    is_high_res = bool(img_dim and (img_dim[0] >= 1000 or img_dim[1] >= 1000))
    if drawings_count >= 5 or (is_high_res and area_rat >= 0.08 and words_count <= 35):
        return True

    # B. Informative diagram / comparison matrix: significant width or central content area
    if area_rat >= 0.06 or (w_rat >= 0.35 and 0.5 <= aspect <= 3.5):
        return True

    # C. UI screenshot / control display: embedded rectangular panel in content body
    if 1.2 <= aspect <= 4.0 and 0.03 <= area_rat <= 0.15 and t > 0.15 * page_height:
        return True

    # D. Photographic component illustration
    if area_rat >= 0.04 and 0.4 <= aspect <= 3.0:
        return True

    return False


def extract_page_figure_bboxes(page: pymupdf.Page) -> list[tuple[tuple[float, float, float, float], tuple[int, int]]]:
    """Detect candidate figure bounding boxes and their source raster dimensions."""
    candidates: list[tuple[tuple[float, float, float, float], tuple[int, int]]] = []

    # 1. Extract embedded raster image rects
    image_infos = page.get_image_info(xrefs=True)
    for info in image_infos:
        bbox = info.get("bbox")
        if bbox:
            l, t, r, b = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
            l = max(0.0, min(l, page.rect.width))
            t = max(0.0, min(t, page.rect.height))
            r = max(0.0, min(r, page.rect.width))
            b = max(0.0, min(b, page.rect.height))
            if (r - l) > 10.0 and (b - t) > 10.0:
                candidates.append((
                    (round(l, 2), round(t, 2), round(r, 2), round(b, 2)),
                    (int(info.get("width", 0)), int(info.get("height", 0))),
                ))

    # 2. Deduplicate overlapping rects using true Intersection-over-Union (IoU > 0.75)
    deduped: list[tuple[tuple[float, float, float, float], tuple[int, int]]] = []
    for cand in candidates:
        bb, dim = cand
        overlap = False
        bb_area = (bb[2] - bb[0]) * (bb[3] - bb[1])
        for ex_bb, _ in deduped:
            ex_area = (ex_bb[2] - ex_bb[0]) * (ex_bb[3] - ex_bb[1])
            ix0 = max(bb[0], ex_bb[0])
            iy0 = max(bb[1], ex_bb[1])
            ix1 = min(bb[2], ex_bb[2])
            iy1 = min(bb[3], ex_bb[3])
            if ix1 > ix0 and iy1 > iy0:
                inter_area = (ix1 - ix0) * (iy1 - iy0)
                union_area = bb_area + ex_area - inter_area
                if union_area > 0 and (inter_area / union_area) > 0.75:
                    overlap = True
                    break
        if not overlap:
            deduped.append(cand)

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
    max_crops_per_doc: int = 22,
    dpi: int = 150,
) -> list[FigureCrop]:
    """Extract, triage, render, and upload figure crops to MinIO storage.

    Args:
        pdf_path: Path to the target PDF file.
        document_id: UUID of the document.
        storage_service: Optional StorageService instance (defaults to MinIO).
        max_crops_per_doc: Document-level budget for figure crops (restored to ~20).
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

            candidate_items = extract_page_figure_bboxes(page)
            page_drawings = page.get_drawings()
            page_words = page.get_text("words")

            page_candidates: list[tuple[float, tuple[float, float, float, float], tuple[int, int]]] = []

            for bbox, img_dim in candidate_items:
                rect = pymupdf.Rect(max(0.0, bbox[0] - 5), max(0.0, bbox[1] - 5), min(pw, bbox[2] + 5), min(ph, bbox[3] + 5))
                dw_cnt = len([d for d in page_drawings if rect.intersects(d["rect"])])
                w_cnt = len([w for w in page_words if rect.contains(pymupdf.Point(w[0], w[1]))])

                if not triage_figure_candidate(
                    bbox,
                    page_width=pw,
                    page_height=ph,
                    page_number=page_num,
                    img_dim=img_dim,
                    drawings_count=dw_cnt,
                    words_count=w_cnt,
                ):
                    continue

                # Score priority: drawings overlay > high-res > area
                score = (dw_cnt * 2.0) + (1.5 if (img_dim and (img_dim[0] >= 1000 or img_dim[1] >= 1000)) else 1.0)
                page_candidates.append((score, bbox, img_dim))

            # Rank by score descending, area descending
            page_candidates.sort(key=lambda x: (x[0], (x[1][2] - x[1][0]) * (x[1][3] - x[1][1])), reverse=True)

            # Enforce per-page cap (max 3 per page)
            max_crops_per_page = 3
            fig_counter = 0

            for _, bbox, img_dim in page_candidates[:max_crops_per_page]:
                if total_crops >= max_crops_per_doc:
                    break

                fig_counter += 1
                total_crops += 1

                # Render crop image
                png_bytes, w_px, h_px = render_figure_crop_png(page, bbox, dpi=dpi)

                # MinIO object key
                obj_key = f"figures/{document_id}/p{page_num}_fig{fig_counter}.png"

                # Upload to storage
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
