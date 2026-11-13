"""Render contact sheet montage and figure manifest for benchmark/debug/.

Uses the production pipeline's committed figure triage logic in backend/app/ingestion/figures.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pymupdf
from PIL import Image, ImageDraw

from app.ingestion.figures import (
    classify_and_triage_figure,
    extract_page_figure_bboxes,
    render_figure_crop_png,
)

DEBUG_DIR = REPO_ROOT / "benchmark" / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)
PDF_PATH = REPO_ROOT / "benchmark" / "sample_1.pdf"


def generate_contact_sheet_and_manifest(max_budget: int = 30) -> tuple[Path, Path, dict[int, int]]:
    """Generate figure manifest and contact sheet using production figure triage logic."""
    doc = pymupdf.open(PDF_PATH)
    all_candidates = []
    per_page_informative: dict[int, list[dict[str, Any]]] = {}

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        pw = float(page.rect.width)
        ph = float(page.rect.height)
        page_num = page_idx + 1

        candidate_items = extract_page_figure_bboxes(page)
        page_drawings = page.get_drawings()
        page_words = page.get_text("words")
        page_text = page.get_text("text")

        for bbox, img_dim in candidate_items:
            rect = pymupdf.Rect(
                max(0.0, bbox[0] - 5),
                max(0.0, bbox[1] - 5),
                min(pw, bbox[2] + 5),
                min(ph, bbox[3] + 5),
            )
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

            cand_dict = {
                "page": page_num,
                "page_idx": page_idx,
                "bbox": [round(x, 1) for x in bbox],
                "flag": flag,
                "score": score,
                "reason": reason,
                "kept": is_k,
                "dim": img_dim,
                "area_ratio": round(
                    (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) / (pw * ph), 3
                ),
            }
            all_candidates.append(cand_dict)

            if is_k:
                if page_num not in per_page_informative:
                    per_page_informative[page_num] = []
                per_page_informative[page_num].append(cand_dict)

    # 1. Enforce document-level budget ~30:
    # Guarantee at least 1 top-ranked candidate per page that has figures
    final_kept: list[dict[str, Any]] = []
    selected_keys: set[tuple[int, tuple[float, ...]]] = set()

    for p in sorted(per_page_informative.keys()):
        cands = per_page_informative[p]
        cands.sort(
            key=lambda c: (
                c["score"],
                (c["bbox"][2] - c["bbox"][0]) * (c["bbox"][3] - c["bbox"][1]),
            ),
            reverse=True,
        )
        top = cands[0]
        final_kept.append(top)
        selected_keys.add((p, tuple(top["bbox"])))

    # 2. Fill remaining budget globally
    remaining = []
    for p, cands in per_page_informative.items():
        for c in cands:
            key = (p, tuple(c["bbox"]))
            if key not in selected_keys:
                remaining.append(c)

    remaining.sort(
        key=lambda c: (
            c["score"],
            (c["bbox"][2] - c["bbox"][0]) * (c["bbox"][3] - c["bbox"][1]),
        ),
        reverse=True,
    )

    for c in remaining:
        if len(final_kept) >= max_budget:
            break
        final_kept.append(c)
        selected_keys.add((c["page"], tuple(c["bbox"])))

    final_kept.sort(key=lambda c: (c["page"], c["bbox"][1]))
    page_counts: dict[int, int] = {}
    for c in final_kept:
        p = c["page"]
        page_counts[p] = page_counts.get(p, 0) + 1

    # Update manifest records status
    manifest_records = []
    for c in all_candidates:
        key = (c["page"], tuple(c["bbox"]))
        status = "kept" if key in selected_keys else "skipped"
        manifest_records.append(
            {
                "page": c["page"],
                "bbox": c["bbox"],
                "flag": c["flag"],
                "score": c["score"],
                "area_ratio": c["area_ratio"],
                "status": status,
                "reason": c["reason"],
            }
        )

    # Write manifest
    manifest_path = DEBUG_DIR / "figure_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_records, f, indent=2)

    # 2. Render contact sheet montage PNG (4 columns)
    cols = 4
    rows = (len(final_kept) + cols - 1) // cols
    cell_w = 320
    cell_h = 240
    montage = Image.new("RGB", (cols * cell_w, max(cell_h, rows * cell_h)), color=(240, 242, 245))
    draw = ImageDraw.Draw(montage)

    for idx, k in enumerate(final_kept):
        c = idx % cols
        r = idx // cols
        x0 = c * cell_w
        y0 = r * cell_h

        p_idx = k["page_idx"]
        page = doc[p_idx]
        b = k["bbox"]
        png_bytes, _, _ = render_figure_crop_png(page, tuple(b), dpi=150)

        import io
        img = Image.open(io.BytesIO(png_bytes))
        img.thumbnail((cell_w - 20, cell_h - 45))

        paste_x = x0 + (cell_w - img.width) // 2
        paste_y = y0 + 10 + ((cell_h - 45) - img.height) // 2
        montage.paste(img, (paste_x, paste_y))

        draw.rectangle(
            [x0 + 5, y0 + 5, x0 + cell_w - 5, y0 + cell_h - 5],
            outline=(200, 205, 215),
            width=1,
        )
        label = f"P{k['page']}: {k['flag']} ({k['score']:.0f})"
        draw.rectangle(
            [x0 + 8, y0 + cell_h - 32, x0 + cell_w - 8, y0 + cell_h - 8],
            fill=(30, 41, 59),
        )
        draw.text((x0 + 14, y0 + cell_h - 26), label, fill=(255, 255, 255))

    doc.close()

    contact_path = DEBUG_DIR / "contact_sheet.png"
    montage.save(str(contact_path))

    return contact_path, manifest_path, page_counts


if __name__ == "__main__":
    cp, mp, counts = generate_contact_sheet_and_manifest()
    print("Kept counts per page:", counts)
    print("Total kept:", sum(counts.values()))
    print("Contact sheet path:", cp)
    print("Manifest path:", mp)
