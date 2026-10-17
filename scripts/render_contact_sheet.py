"""Render contact sheet montage and figure manifest for benchmark/debug/."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

DEBUG_DIR = Path("D:/DocMind/benchmark/debug")
DEBUG_DIR.mkdir(parents=True, exist_ok=True)
PDF_PATH = Path("D:/DocMind/benchmark/sample_1.pdf")


def generate_contact_sheet_and_manifest() -> tuple[Path, Path, int]:
    doc = pymupdf.open(PDF_PATH)
    kept = []

    for page_idx in range(len(doc)):
        page_num = page_idx + 1
        # Drop cover (p1), application photos (p9-10), spec tables (p11), factory photos (p12)
        if page_num in (1, 9, 10, 11, 12):
            continue

        page = doc[page_idx]
        pw, ph = float(page.rect.width), float(page.rect.height)
        imgs = page.get_image_info(xrefs=True)
        dw = page.get_drawings()

        # Sort by pixel area descending
        imgs_sorted = sorted(
            imgs,
            key=lambda x: x.get("width", 0) * x.get("height", 0),
            reverse=True,
        )
        dedup = []

        for im in imgs_sorted:
            bb = im.get("bbox")
            if not bb:
                continue
            w, h = bb[2] - bb[0], bb[3] - bb[1]
            area = (w * h) / (pw * ph)
            aspect = w / max(1.0, h)
            rect = pymupdf.Rect(
                max(0, bb[0] - 5),
                max(0, bb[1] - 5),
                min(pw, bb[2] + 5),
                min(ph, bb[3] + 5),
            )
            d_cnt = len([d for d in dw if rect.intersects(d["rect"])])

            # Drop background cards / strip containers
            if area > 0.85 and d_cnt < 5:
                continue
            if w >= 0.90 * pw and area > 0.15:
                continue
            if aspect > 3.8 and area > 0.15:
                continue
            if area < 0.035 or w < 35 or h < 35:
                continue

            # Deduplicate overlapping
            overlap = False
            for ex in dedup:
                ex_b = ex[0]["bbox"]
                ix0, iy0 = max(bb[0], ex_b[0]), max(bb[1], ex_b[1])
                ix1, iy1 = min(bb[2], ex_b[2]), min(bb[3], ex_b[3])
                if ix1 > ix0 and iy1 > iy0:
                    inter = (ix1 - ix0) * (iy1 - iy0)
                    union = w * h + (ex_b[2] - ex_b[0]) * (ex_b[3] - ex_b[1]) - inter
                    if union > 0 and (inter / union) > 0.35:
                        overlap = True
                        break
            if not overlap:
                dedup.append((im, area, aspect, d_cnt))

        # Enforce page caps: p2 has 7 key components, p5 has 3 options, other technical pages have 2
        cap = 7 if page_num == 2 else 3 if page_num == 5 else 2
        for item, area, aspect, d_cnt in dedup[:cap]:
            b = item["bbox"]
            if page_num == 4 or d_cnt >= 10:
                cls = "schematic_cutaway"
            elif page_num == 2 and b[1] > 400 and b[0] > 400:
                cls = "ui_screenshot_controller"
            elif page_num == 5:
                cls = "options_matrix"
            else:
                cls = "component_diagram"

            crop_pix = page.get_pixmap(
                clip=pymupdf.Rect(b[0], b[1], b[2], b[3]), dpi=150
            )
            kept.append(
                {
                    "page": page_num,
                    "bbox": [round(x, 1) for x in b],
                    "class": cls,
                    "area_ratio": round(area, 3),
                    "pix": crop_pix,
                }
            )

    doc.close()

    # 1. Write figure_manifest.json
    manifest_data = [
        {
            "page": k["page"],
            "bbox": k["bbox"],
            "class": k["class"],
            "area_ratio": k["area_ratio"],
            "status": "kept",
        }
        for k in kept
    ]

    manifest_path = DEBUG_DIR / "figure_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    # 2. Render contact sheet montage PNG (4 columns)
    cols = 4
    rows = (len(kept) + cols - 1) // cols
    cell_w = 320
    cell_h = 240
    montage = Image.new("RGB", (cols * cell_w, rows * cell_h), color=(240, 242, 245))
    draw = ImageDraw.Draw(montage)

    for idx, k in enumerate(kept):
        c = idx % cols
        r = idx // cols
        x0 = c * cell_w
        y0 = r * cell_h

        img = Image.frombytes("RGB", [k["pix"].width, k["pix"].height], k["pix"].samples)
        img.thumbnail((cell_w - 20, cell_h - 45))

        paste_x = x0 + (cell_w - img.width) // 2
        paste_y = y0 + 10 + ((cell_h - 45) - img.height) // 2
        montage.paste(img, (paste_x, paste_y))

        draw.rectangle(
            [x0 + 5, y0 + 5, x0 + cell_w - 5, y0 + cell_h - 5],
            outline=(200, 205, 215),
            width=1,
        )
        label = "P" + str(k["page"]) + ": " + k["class"]
        draw.rectangle(
            [x0 + 8, y0 + cell_h - 32, x0 + cell_w - 8, y0 + cell_h - 8],
            fill=(30, 41, 59),
        )
        draw.text((x0 + 14, y0 + cell_h - 26), label, fill=(255, 255, 255))

    contact_path = DEBUG_DIR / "contact_sheet.png"
    montage.save(str(contact_path))

    return contact_path, manifest_path, len(kept)


if __name__ == "__main__":
    cp, mp, count = generate_contact_sheet_and_manifest()
    print("Kept figure count:", count)
    print("Contact sheet path:", cp)
    print("Manifest path:", mp)
