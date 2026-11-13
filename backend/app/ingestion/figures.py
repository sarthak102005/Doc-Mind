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


def classify_and_triage_figure(
    bbox: tuple[float, float, float, float],
    page_width: float,
    page_height: float,
    img_dim: tuple[int, int] | None = None,
    drawings_count: int = 0,
    words_count: int = 0,
    page_text: str = "",
) -> tuple[bool, str, float, str]:
    """Triage and classify an image region using general geometrical and content features.

    Rules:
    - Uses coarse flags: 'informative' vs 'uninformative'.
    - No hardcoded page numbers, no page-specific coordinate windows, no corporate keywords.
    - Filters out decorative backgrounds, full-width banners, corner badges, and tiny icons.

    Returns:
        (is_informative, flag, score, reason)
    """
    l, t, r, b = bbox
    w = max(0.0, r - l)
    h = max(0.0, b - t)
    area_rat = (w * h) / max(1.0, page_width * page_height)
    aspect = w / max(1.0, h)
    w_rat = w / page_width

    # 1. Low-resolution card containers or tiny icons/badges
    if img_dim and img_dim[0] < 250 and img_dim[1] < 250:
        return False, "uninformative", 0.0, "Pixel dimension too small for technical figure"
    if area_rat < 0.025 or w < 35.0 or h < 35.0:
        return False, "uninformative", 0.0, "Area ratio < 2.5% or dimension < 35 pt"
    if aspect > 4.0 or aspect < 0.25:
        return False, "uninformative", 0.0, f"Aspect ratio {aspect:.2f} outside valid range"

    # 2. Decorative background washes / full-page containers
    if area_rat > 0.65:
        # Full-page technical schematic (e.g. cutaway diagram) has vector leader lines and words
        if drawings_count >= 10 and words_count >= 20:
            return True, "informative", 100.0, "Full-page technical cutaway schematic"
        return False, "uninformative", 0.0, "Full-page background without technical callouts"

    if w_rat >= 0.88 and area_rat > 0.15 and words_count < 20:
        return False, "uninformative", 0.0, "Full-width decorative background banner"

    # 3. Informative technical figures
    # A. Labelled diagram or annotated schematic (drawings overlay or callout text)
    if drawings_count >= 3 or (words_count >= 3 and area_rat >= 0.04):
        score = 85.0 + min(15.0, drawings_count * 0.5 + words_count * 0.2)
        return True, "informative", score, f"Technical schematic ({drawings_count} drawings, {words_count} words)"

    # B. Component render / instrument display / technical photograph
    if 0.03 <= area_rat <= 0.65 and 0.35 <= aspect <= 3.5:
        score = 70.0 + (area_rat * 25.0)
        return True, "informative", score, "Technical illustration or component render"

    return False, "uninformative", 0.0, "Does not meet technical criteria"


def triage_figure_candidate(
    bbox: tuple[float, float, float, float],
    page_width: float,
    page_height: float,
    has_text_nearby: bool = True,
    page_number: int | None = None,
    img_dim: tuple[int, int] | None = None,
    drawings_count: int = 0,
    words_count: int = 0,
    page_text: str = "",
) -> bool:
    """Triage whether an image region is an informative figure using general features only."""
    is_k, _, _, _ = classify_and_triage_figure(
        bbox=bbox,
        page_width=page_width,
        page_height=page_height,
        img_dim=img_dim,
        drawings_count=drawings_count,
        words_count=words_count,
        page_text=page_text,
    )
    return is_k


def remove_containment_duplicates(
    candidates: list[tuple[tuple[float, float, float, float], tuple[int, int]]],
    containment_threshold: float = 0.85,
) -> list[tuple[tuple[float, float, float, float], tuple[int, int]]]:
    """Remove candidate boxes that are largely contained within another candidate box.

    If box A is >= containment_threshold contained in box B, keep the tighter/smaller
    box to avoid outer decorative container margins.
    """
    if not candidates:
        return []

    # Sort by area ascending so smaller boxes are evaluated first
    sorted_cands = sorted(
        candidates,
        key=lambda c: (c[0][2] - c[0][0]) * (c[0][3] - c[0][1]),
    )
    kept: list[tuple[tuple[float, float, float, float], tuple[int, int]]] = []

    for cand in sorted_cands:
        bb, dim = cand
        cand_area = max(1.0, (bb[2] - bb[0]) * (bb[3] - bb[1]))
        is_duplicate = False

        for existing in kept:
            ex_bb, _ = existing
            ex_area = max(1.0, (ex_bb[2] - ex_bb[0]) * (ex_bb[3] - ex_bb[1]))

            ix0 = max(bb[0], ex_bb[0])
            iy0 = max(bb[1], ex_bb[1])
            ix1 = min(bb[2], ex_bb[2])
            iy1 = min(bb[3], ex_bb[3])

            if ix1 > ix0 and iy1 > iy0:
                inter_area = (ix1 - ix0) * (iy1 - iy0)
                # If either box is >= threshold contained in the other
                if (inter_area / cand_area >= containment_threshold) or (inter_area / ex_area >= containment_threshold):
                    is_duplicate = True
                    break

        if not is_duplicate:
            kept.append(cand)

    return kept


def trim_crop_avoiding_half_words(
    bbox: tuple[float, float, float, float],
    page_words: list[Any],
) -> tuple[float, float, float, float]:
    """Trim bbox boundaries so no half-words from neighbouring text appear in the crop.

    If a word partially intersects an edge (not fully contained inside the bbox),
    the boundary is trimmed inward past the word to prevent half-words.
    """
    l, t, r, b = bbox

    for w in page_words:
        wl, wt, wr, wb = float(w[0]), float(w[1]), float(w[2]), float(w[3])
        # Check if word intersects the bounding box
        if wl < r and wr > l and wt < b and wb > t:
            # If word is fully contained within the box, keep it intact
            if wl >= l and wr <= r and wt >= t and wb <= b:
                continue

            # Word straddles left edge
            if wl < l < wr:
                if wr + 1.0 < r - 25.0:
                    l = wr + 1.0
            # Word straddles right edge
            if wl < r < wr:
                if wl - 1.0 > l + 25.0:
                    r = wl - 1.0
            # Word straddles top edge
            if wt < t < wb:
                if wb + 1.0 < b - 25.0:
                    t = wb + 1.0
            # Word straddles bottom edge
            if wt < b < wb:
                if wt - 1.0 > t + 25.0:
                    b = wt - 1.0

    return (round(l, 2), round(t, 2), round(r, 2), round(b, 2))


def extract_page_figure_bboxes(page: pymupdf.Page) -> list[tuple[tuple[float, float, float, float], tuple[int, int]]]:
    """Detect candidate figure bounding boxes and deduplicate overlapping/contained rects."""
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

    # 2. Deduplicate containment duplicates (>= 85% overlap)
    deduped = remove_containment_duplicates(candidates, containment_threshold=0.85)

    # 3. Deduplicate overlapping rects using true Intersection-over-Union (IoU > 0.75)
    final_candidates: list[tuple[tuple[float, float, float, float], tuple[int, int]]] = []
    for cand in deduped:
        bb, dim = cand
        overlap = False
        bb_area = (bb[2] - bb[0]) * (bb[3] - bb[1])
        for ex_bb, _ in final_candidates:
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
            final_candidates.append(cand)

    return final_candidates


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
    max_crops_per_doc: int = 30,
    dpi: int = 150,
) -> list[FigureCrop]:
    """Extract, triage, render, and upload figure crops to MinIO storage.

    Budget allocation rules:
    - Document-level budget of ~30 candidates (max_crops_per_doc).
    - Guarantees at least 1 top-ranked candidate per page that has informative figures.
    - Remaining budget filled by global ranking across all pages.
    - Crops are trimmed so no half-words from neighbouring text appear.
    """
    storage = storage_service or get_storage_service()
    storage.ensure_bucket()

    doc = pymupdf.open(pdf_path)  # type: ignore[no-untyped-call]
    crops: list[FigureCrop] = []

    try:
        # Collect candidates across all pages
        per_page_candidates: dict[int, list[dict[str, Any]]] = {}

        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            page = doc[page_idx]
            pw = float(page.rect.width)
            ph = float(page.rect.height)

            candidate_items = extract_page_figure_bboxes(page)
            page_drawings = page.get_drawings()
            page_words = page.get_text("words")
            page_text = page.get_text("text")

            page_cands: list[dict[str, Any]] = []

            for bbox, img_dim in candidate_items:
                rect = pymupdf.Rect(max(0.0, bbox[0] - 5), max(0.0, bbox[1] - 5), min(pw, bbox[2] + 5), min(ph, bbox[3] + 5))
                dw_cnt = len([d for d in page_drawings if rect.intersects(d["rect"])])
                w_cnt = len([w for w in page_words if rect.contains(pymupdf.Point(w[0], w[1]))])

                is_k, flag, score, reason = classify_and_triage_figure(
                    bbox,
                    page_width=pw,
                    page_height=ph,
                    img_dim=img_dim,
                    drawings_count=dw_cnt,
                    words_count=w_cnt,
                    page_text=page_text,
                )
                if not is_k:
                    continue

                # Trim crop to avoid partial neighbouring words
                trimmed_bbox = trim_crop_avoiding_half_words(bbox, page_words)

                area = (trimmed_bbox[2] - trimmed_bbox[0]) * (trimmed_bbox[3] - trimmed_bbox[1])
                page_cands.append({
                    "page_num": page_num,
                    "page_idx": page_idx,
                    "bbox": trimmed_bbox,
                    "img_dim": img_dim,
                    "score": score,
                    "area": area,
                    "reason": reason,
                    "flag": flag,
                })

            if page_cands:
                # Sort page candidates by score descending, area descending
                page_cands.sort(key=lambda x: (x["score"], x["area"]), reverse=True)
                per_page_candidates[page_num] = page_cands

        # 1. Guarantee: Pick top-1 candidate for each page that has figures (up to max_crops_per_doc)
        selected_candidates: list[dict[str, Any]] = []
        selected_keys: set[tuple[int, tuple[float, float, float, float]]] = set()

        # Collect top candidate per page
        top_per_page = [cands[0] for _, cands in sorted(per_page_candidates.items())]
        if len(top_per_page) > max_crops_per_doc:
            # If budget is smaller than number of pages, take highest scoring ones
            top_per_page.sort(key=lambda x: (x["score"], x["area"]), reverse=True)
            top_per_page = top_per_page[:max_crops_per_doc]

        for top_cand in top_per_page:
            selected_candidates.append(top_cand)
            selected_keys.add((top_cand["page_num"], top_cand["bbox"]))

        # 2. Fill remaining budget up to max_crops_per_doc globally
        remaining_pool: list[dict[str, Any]] = []
        for page_num, cands in per_page_candidates.items():
            for c in cands:
                key = (page_num, c["bbox"])
                if key not in selected_keys:
                    remaining_pool.append(c)

        # Sort remaining candidates by score descending, then area descending
        remaining_pool.sort(key=lambda x: (x["score"], x["area"]), reverse=True)

        for c in remaining_pool:
            if len(selected_candidates) >= max_crops_per_doc:
                break
            selected_candidates.append(c)
            selected_keys.add((c["page_num"], c["bbox"]))

        # Sort selected candidates by page_num, then top coordinate
        selected_candidates.sort(key=lambda x: (x["page_num"], x["bbox"][1]))

        # Render and store selected figure crops
        page_fig_counter: dict[int, int] = {}

        for item in selected_candidates:
            page_num = item["page_num"]
            page_idx = item["page_idx"]
            page = doc[page_idx]
            bbox = item["bbox"]

            fig_idx = page_fig_counter.get(page_num, 0) + 1
            page_fig_counter[page_num] = fig_idx

            png_bytes, w_px, h_px = render_figure_crop_png(page, bbox, dpi=dpi)
            obj_key = f"figures/{document_id}/p{page_num}_fig{fig_idx}.png"

            storage.upload_file(
                object_name=obj_key,
                data=png_bytes,
                content_type="image/png",
            )

            crop = FigureCrop(
                figure_id=f"{document_id}_p{page_num}_fig{fig_idx}",
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
