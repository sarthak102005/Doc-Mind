"""Unit tests for Stage 2: Reading order, horizontal banding, and WordBox abstraction.

Verifies:
1. Page 2 (Digital & Scanned): Horizontal bands, intra-band column clustering, and positive
   assertions that Applications bullets sit under their own model headings, benefit bullets
   sit under their own deck headings, and controller bullets sit under their own headings.
2. Generic numbered legend detection: FactoryCat Page 3 legend and synthetic fruit legend.
3. Page 4: Docling AST ingestion for all 21 cutaway labels.
4. Synthetic layout: 2-column article with full-width title and footnote.
5. Scanned WordBox fixtures from RapidOCR: unit consistency with digital PDF.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.ingestion.reading_order import (
    WordBox,
    detect_horizontal_bands,
    extract_numbered_legend_items,
    group_words_into_lines,
    ingest_ast_text_nodes,
    reconstruct_reading_order,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_page_2_reading_order_bands_and_hierarchy() -> None:
    """Verify Digital Page 2 horizontal bands and intra-band column clustering."""
    fixture_path = FIXTURES_DIR / "wordboxes_sample_1_p2.json"
    assert fixture_path.exists(), f"Missing fixture {fixture_path}"

    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    page_width = float(data["page_width"])
    page_height = float(data["page_height"])
    assert data["unit"] == "pt"
    assert data["coord_origin"] == "TOPLEFT"

    words = [WordBox(**b) for b in data["words"]]
    assert len(words) > 100

    blocks = reconstruct_reading_order(words, page_width=page_width, page_height=page_height)
    assert len(blocks) > 0

    print("\n--- DIGITAL PAGE 2 BLOCKS ---")
    for i, b in enumerate(blocks):
        clean_text = b.text.encode("ascii", "replace").decode("ascii")
        print(f"[{i:2d}] Band {b.band_index} Col {b.column_index} | {b.section_path} | {clean_text}")

    # 1. Band headings must be propagated into section paths
    chassis_blocks = [b for b in blocks if "Choose Your Chassis" in b.section_path]
    deck_blocks = [b for b in blocks if "Choose Your Scrub Deck" in b.section_path]
    controller_blocks = [b for b in blocks if "Choose Your Controller" in b.section_path]

    assert len(chassis_blocks) > 0, "Expected chassis band blocks"
    assert len(deck_blocks) > 0, "Expected scrub deck band blocks"
    assert len(controller_blocks) > 0, "Expected controller band blocks"

    # 2. Positive assertions: Each Applications bullet sits under its own model heading
    micro_app_bullets = [
        b for b in blocks
        if b.section_path == ["Choose Your Chassis", "Micro-HD", "Applications"]
        and any(k in b.text for k in ["Automotive Shops", "Machine Shops", "Warehouses"])
    ]
    mini_app_bullets = [
        b for b in blocks
        if b.section_path == ["Choose Your Chassis", "Mini-HD", "Applications"]
        and any(k in b.text for k in ["Fabrication Shops", "Beverage Distribution", "Food Packaging"])
    ]
    mag_app_bullets = [
        b for b in blocks
        if b.section_path == ["Choose Your Chassis", "Mag-HD", "Applications"]
        and any(k in b.text for k in ["Distribution", "Sports Arenas", "Aviation"])
    ]

    assert len(micro_app_bullets) >= 3, f"Expected 3 Micro-HD app bullets, got {len(micro_app_bullets)}"
    assert len(mini_app_bullets) >= 3, f"Expected 3 Mini-HD app bullets, got {len(mini_app_bullets)}"
    assert len(mag_app_bullets) >= 3, f"Expected 3 Mag-HD app bullets, got {len(mag_app_bullets)}"

    # 3. Positive assertions: Deck benefits sit under their own benefit headings within scrub deck band
    cyl_bullets = [
        b for b in blocks
        if b.section_path == ["Choose Your Scrub Deck", "Cylindrical Benefits"]
        and any(k in b.text for k in ["Pre-Sweeping", "Simultaneously", "Tile & Grout", "Track Fields"])
    ]
    disk_bullets = [
        b for b in blocks
        if b.section_path == ["Choose Your Scrub Deck", "Disk Benefits"]
        and any(k in b.text for k in ["Brush/ Pad Selection", "Maintenance Cost", "Irregular Floors"])
    ]
    orbital_bullets = [
        b for b in blocks
        if b.section_path == ["Choose Your Scrub Deck", "Orbital Benefits"]
        and any(k in b.text for k in ["Chemical Free", "Water Usage", "VCT Prep", "Slip & Fall"])
    ]

    assert len(cyl_bullets) >= 4, f"Expected Cylindrical bullets, got {len(cyl_bullets)}"
    assert len(disk_bullets) >= 3, f"Expected Disk bullets, got {len(disk_bullets)}"
    assert len(orbital_bullets) >= 3, f"Expected Orbital bullets, got {len(orbital_bullets)}"

    # 4. Positive assertions: Controller bullets sit under their own headings
    mil_bullets = [
        b for b in blocks
        if b.section_path == ["Choose Your Controller", "Military Grade"]
        and "Year 1970 Technology" in b.text
    ]
    touch_bullets = [
        b for b in blocks
        if b.section_path == ["Choose Your Controller", "Touch Screen"]
        and "Year 2010 Technology" in b.text
    ]
    assert len(mil_bullets) >= 1, "Expected Year 1970 bullet under Military Grade"
    assert len(touch_bullets) >= 1, "Expected Year 2010 bullet under Touch Screen"


def test_scanned_page_2_reading_order_bands_and_hierarchy() -> None:
    """Verify Scanned Page 2 horizontal bands, intra-band column clustering, and positive hierarchy."""
    fixture_path = FIXTURES_DIR / "wordboxes_sample_1_scanned_p2.json"
    assert fixture_path.exists(), f"Missing fixture {fixture_path}"

    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    page_width = float(data["page_width"])
    page_height = float(data["page_height"])
    assert data["unit"] == "pt"
    assert data["coord_origin"] == "TOPLEFT"

    words = [WordBox(**b) for b in data["words"]]
    assert len(words) > 30

    blocks = reconstruct_reading_order(words, page_width=page_width, page_height=page_height)
    assert len(blocks) > 0

    print("\n--- SCANNED PAGE 2 BLOCKS ---")
    for i, b in enumerate(blocks):
        clean_text = b.text.encode("ascii", "replace").decode("ascii")
        print(f"[{i:2d}] Band {b.band_index} Col {b.column_index} | {b.section_path} | {clean_text}")

    # 1. Positive assertions: Each Applications bullet sits under its own model heading
    micro_app = [
        b for b in blocks
        if b.section_path == ["Choose Your Chassis", "Micro-HD", "Applications"]
        and any(k in b.text for k in ["Automotive Shops", "Machine Shops", "Warehouses"])
    ]
    mini_app = [
        b for b in blocks
        if b.section_path == ["Choose Your Chassis", "Mini-HD", "Applications"]
        and any(k in b.text for k in ["Fabrication Shops", "Beverage Distribution", "Food Packaging"])
    ]
    mag_app = [
        b for b in blocks
        if b.section_path == ["Choose Your Chassis", "Mag-HD", "Applications"]
        and any(k in b.text for k in ["Distribution", "Sports Arenas", "Aviation"])
    ]

    assert len(micro_app) >= 3, f"Scanned: Expected 3 Micro-HD app bullets, got {len(micro_app)}"
    assert len(mini_app) >= 3, f"Scanned: Expected 3 Mini-HD app bullets, got {len(mini_app)}"
    assert len(mag_app) >= 3, f"Scanned: Expected 3 Mag-HD app bullets, got {len(mag_app)}"

    # 2. Positive assertions: Scrub deck benefits sit under their own headings
    cyl_bullets = [
        b for b in blocks
        if b.section_path == ["Choose Your Scrub Deck", "Cylindrical Benefits"]
        and any(k in b.text for k in ["Pre-Sweeping", "Simultaneously", "Tile & Grout", "Track Fields"])
    ]
    disk_bullets = [
        b for b in blocks
        if b.section_path == ["Choose Your Scrub Deck", "Disk Benefits"]
        and any(k in b.text for k in ["Brush/ Pad Selection", "Maintenance Cost", "Irregular Floors"])
    ]
    orbital_bullets = [
        b for b in blocks
        if b.section_path == ["Choose Your Scrub Deck", "Orbital Benefits"]
        and any(k in b.text for k in ["Chemical Free", "Water Usage", "VCT Prep", "Slip & Fall"])
    ]

    assert len(cyl_bullets) >= 3, f"Scanned: Expected Cylindrical bullets, got {len(cyl_bullets)}"
    assert len(disk_bullets) >= 3, f"Scanned: Expected Disk bullets, got {len(disk_bullets)}"
    assert len(orbital_bullets) >= 3, f"Scanned: Expected Orbital bullets, got {len(orbital_bullets)}"

    # 3. Positive assertions: Controller bullets sit under their own headings
    mil_bullets = [
        b for b in blocks
        if b.section_path == ["Choose Your Controller", "Military Grade"]
        and "Year 1970 Technology" in b.text
    ]
    assert len(mil_bullets) >= 1, "Scanned: Expected Year 1970 bullet under Military Grade"

    touch_blocks = [
        b for b in blocks
        if any("Touch Screen" in p for p in b.section_path)
    ]
    assert len(touch_blocks) >= 1, "Scanned: Expected Touch Screen heading block"


def test_page_3_brush_legend_association_and_asterisks() -> None:
    """Verify Page 3 legend matches circle numbers 1-9 and asterisks for 4 specific items."""
    fixture_path = FIXTURES_DIR / "wordboxes_sample_1_p3.json"
    assert fixture_path.exists(), f"Missing fixture {fixture_path}"

    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    words = [WordBox(**b) for b in data["words"]]
    items = extract_numbered_legend_items(
        words, page_width=float(data["page_width"]), page_height=float(data["page_height"])
    )

    # Must find all 9 brush items
    assert len(items) == 9, f"Expected 9 legend items, found {len(items)}"

    # Check numbering from 1 to 9
    numbers = [it["number"] for it in items]
    assert numbers == list(range(1, 10))

    # Check asterisks / not_offered_on_cylindrical linked to footnote
    nocyl_items = [it["name"] for it in items if it["not_offered_on_cylindrical"]]
    expected_nocyl = [
        "Polypropylene",
        "Tufted Pad Driver",
        "Neoprene Pad Driver",
        "Super Grit",
    ]
    assert sorted(nocyl_items) == sorted(expected_nocyl), (
        f"Expected {expected_nocyl}, got {nocyl_items}"
    )

    # Check footnote attached
    for it in items:
        if it["not_offered_on_cylindrical"]:
            assert "Not offered on Cylindrical Brushes" in it["footnote"]

    # Check non-asterisk items
    regular_items = [it["name"] for it in items if not it["not_offered_on_cylindrical"]]
    expected_regular = ["Nylon", "Tampico", "Tough Grit", "Midi Grit", "Light Grit"]
    assert sorted(regular_items) == sorted(expected_regular)


def test_synthetic_numbered_fruit_legend_with_asterisks() -> None:
    """Verify generic numbered legend detector on completely different domain (fruit legend).

    Proves that legend detection does not depend on hard-coded brush names or coordinates.
    """
    fruit_lines = [
        "1 Apple: Crisp Gala apples from Washington orchards",
        "2 * Banana: Cavendish variety with yellow peel",
        "3 Orange: Florida Valencia sweet citrus",
        "4 * Mango: Organic Alphonso and Honey varieties",
        "5 Grape: Seedless red table grapes",
    ]

    boxes: list[WordBox] = []
    cur_y = 100.0
    for line_text in fruit_lines:
        cur_x = 50.0
        for token in line_text.split():
            tok_w = len(token) * 5.0
            boxes.append(
                WordBox(
                    text=token,
                    l=cur_x,
                    t=cur_y,
                    r=cur_x + tok_w,
                    b=cur_y + 12.0,
                    font_size=10.0,
                    page=1,
                )
            )
            cur_x += tok_w + 4.0
        cur_y += 30.0

    # Footnote at y=600
    fn_text = "* Seasonal availability only"
    cur_x = 50.0
    for token in fn_text.split():
        tok_w = len(token) * 5.0
        boxes.append(
            WordBox(
                text=token,
                l=cur_x,
                t=600.0,
                r=cur_x + tok_w,
                b=612.0,
                font_size=9.0,
                page=1,
            )
        )
        cur_x += tok_w + 4.0

    items = extract_numbered_legend_items(boxes, page_width=500.0, page_height=700.0)

    assert len(items) == 5, f"Expected 5 fruit items, got {len(items)}"
    assert [it["number"] for it in items] == [1, 2, 3, 4, 5]

    item_names = [it["name"] for it in items]
    assert item_names == ["Apple", "Banana", "Orange", "Mango", "Grape"]

    asterisk_items = [it["name"] for it in items if it["has_asterisk"]]
    assert asterisk_items == ["Banana", "Mango"]

    for it in items:
        if it["has_asterisk"]:
            assert it["footnote"] == "Seasonal availability only"
        else:
            assert it["footnote"] == ""


def test_page_4_cutaway_labels_ast_ingestion() -> None:
    """Verify that Docling AST tree ingestion captures all 21 cutaway labels."""
    fixture_path = FIXTURES_DIR / "tree_sample_1_p4_texts.json"
    assert fixture_path.exists(), f"Missing fixture {fixture_path}"

    with open(fixture_path, encoding="utf-8") as f:
        tree_dict = json.load(f)

    page_height = float(tree_dict.get("page_height", 633.6))
    word_boxes = ingest_ast_text_nodes(tree_dict, page_height=page_height)
    assert len(word_boxes) == 21, f"Expected 21 cutaway labels, got {len(word_boxes)}"

    # Verify key labels are present
    all_texts = [w.text for w in word_boxes]
    assert "Drain Saver Basket" in all_texts
    assert "Stainless Vac Screen" in all_texts
    assert "Recovery Lid" in all_texts
    assert "Patented Vac Bandeau" in all_texts
    assert "Tall Rollers" in all_texts


def test_synthetic_two_column_article_with_title_and_footnote() -> None:
    """Verify reading order on a generic 2-column layout with a full-width title and footnote.

    Proves that the horizontal banding and column clustering algorithms are general
    and not hard-coded or tuned specifically to FactoryCat catalog pages.
    """
    page_w = 600.0
    page_h = 800.0

    boxes: list[WordBox] = []

    # 1. Full-width Title at the top (x: 50 to 550, y: 30 to 65, height: 35)
    title_words = ["Comprehensive", "Study", "on", "Automated", "Document", "Layout", "Analysis"]
    cur_x = 50.0
    for w in title_words:
        w_width = len(w) * 12.0
        boxes.append(
            WordBox(
                text=w,
                l=cur_x,
                t=30.0,
                r=cur_x + w_width,
                b=65.0,
                font_size=20.0,
                page=1,
            )
        )
        cur_x += w_width + 8.0

    # 2. Two columns of body text (y: 100 to 180)
    col1_lines = [
        "In this section we present the background.",
        "Early approaches relied heavily on rigid rules.",
        "Recent advances leverage deep learning models.",
    ]
    cur_y = 100.0
    for line in col1_lines:
        line_x = 50.0
        for token in line.split():
            tok_w = len(token) * 4.0
            boxes.append(
                WordBox(
                    text=token,
                    l=line_x,
                    t=cur_y,
                    r=line_x + tok_w,
                    b=cur_y + 12.0,
                    font_size=10.0,
                    page=1,
                )
            )
            line_x += tok_w + 4.0
        cur_y += 20.0

    # Column 2 (x: 320 to 530, separated by 60pt gutter)
    col2_lines = [
        "Our experiments benchmark precision across datasets.",
        "Results demonstrate horizontal banding utility.",
        "Ablation studies validate dynamic gutter detection.",
    ]
    cur_y = 100.0  # SAME vertical baseline as Column 1!
    for line in col2_lines:
        line_x = 320.0
        for token in line.split():
            tok_w = len(token) * 4.0
            boxes.append(
                WordBox(
                    text=token,
                    l=line_x,
                    t=cur_y,
                    r=line_x + tok_w,
                    b=cur_y + 12.0,
                    font_size=10.0,
                    page=1,
                )
            )
            line_x += tok_w + 4.0
        cur_y += 20.0

    # 3. Footnote in footer margin (y: 740 to 755, x: 50 to 500)
    footnote_text = "*This work was supported by the AI Research Foundation."
    fn_x = 50.0
    for token in footnote_text.split():
        tok_w = len(token) * 4.0
        boxes.append(
            WordBox(
                text=token,
                l=fn_x,
                t=740.0,
                r=fn_x + tok_w,
                b=755.0,
                font_size=8.0,
                page=1,
            )
        )
        fn_x += tok_w + 3.0

    # Execute reading order reconstruction
    blocks = reconstruct_reading_order(boxes, page_width=page_w, page_height=page_h)
    assert len(blocks) > 0

    block_texts = [b.text for b in blocks]

    # Verification:
    # 1. Full-width title MUST be the very first block
    assert "Comprehensive Study" in block_texts[0]

    # 2. All Column 1 lines MUST appear BEFORE any Column 2 lines (no interleaving!)
    col1_indices = [
        i for i, text in enumerate(block_texts)
        if any(keyword in text for keyword in ["background", "rigid rules", "Recent advances"])
    ]
    col2_keywords = [
        "benchmark precision",
        "horizontal banding",
        "Ablation studies",
    ]
    col2_indices = [
        i for i, text in enumerate(block_texts)
        if any(keyword in text for keyword in col2_keywords)
    ]

    assert len(col1_indices) == 3, f"Expected 3 Col 1 lines, got {len(col1_indices)}"
    assert len(col2_indices) == 3, f"Expected 3 Col 2 lines, got {len(col2_indices)}"

    # Max index of Col 1 must be strictly less than min index of Col 2
    assert max(col1_indices) < min(col2_indices), (
        f"Col 1 lines ({col1_indices}) must precede Col 2 lines ({col2_indices}) without interleaving!"
    )

    # 3. Footnote MUST be the last block
    assert "AI Research Foundation" in block_texts[-1]


def test_scanned_wordbox_fixtures_rapidocr() -> None:
    """Verify that RapidOCR word boxes from scanned fixtures load and have matching units."""
    for p_num in [2, 3, 4, 11]:
        fixture_path = FIXTURES_DIR / f"wordboxes_sample_1_scanned_p{p_num}.json"
        assert fixture_path.exists(), f"Missing fixture {fixture_path}"

        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)

        assert data["unit"] == "pt", f"Page {p_num} unit should be pt"
        assert data["coord_origin"] == "TOPLEFT"
        assert data["page_width"] == 792.0
        assert data["page_height"] == 633.6

        words = [WordBox(**b) for b in data["words"]]
        assert len(words) > 0, f"Expected word boxes for scanned page {p_num}"

        # Group into lines
        lines = group_words_into_lines(words)
        assert len(lines) > 0

        # Detect bands using fixture dimensions
        bands = detect_horizontal_bands(
            lines, page_width=float(data["page_width"]), page_height=float(data["page_height"])
        )
        assert len(bands) > 0
