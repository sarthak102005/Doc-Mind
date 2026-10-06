"""Unit tests for Stage 2: Reading order, horizontal banding, and WordBox abstraction.

Verifies:
1. Page 2: Horizontal bands and intra-band column clustering (Orbital never under models).
2. Page 3: Brush legend extraction, numbers 1-9 association, and asterisk detection.
3. Page 4: Docling AST ingestion for all 21 cutaway labels.
4. Synthetic layout: 2-column article with full-width title and footnote.
5. Scanned WordBox fixtures from RapidOCR can be normalized and processed.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.ingestion.reading_order import (
    WordBox,
    detect_horizontal_bands,
    extract_brush_legend_items,
    group_words_into_lines,
    ingest_ast_text_nodes,
    reconstruct_reading_order,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_page_2_reading_order_bands_and_hierarchy() -> None:
    """Verify Page 2 horizontal bands and intra-band column clustering."""
    fixture_path = FIXTURES_DIR / "wordboxes_sample_1_p2.json"
    assert fixture_path.exists(), f"Missing fixture {fixture_path}"

    with open(fixture_path, encoding="utf-8") as f:
        raw_boxes = json.load(f)

    words = [WordBox(**b) for b in raw_boxes]
    assert len(words) > 100

    blocks = reconstruct_reading_order(words, page_width=792.0, page_height=612.0)
    assert len(blocks) > 0

    # 1. Band headings must be propagated into section paths
    chassis_blocks = [b for b in blocks if "Choose Your Chassis" in b.section_path]
    deck_blocks = [b for b in blocks if "Choose Your Scrub Deck" in b.section_path]
    controller_blocks = [b for b in blocks if "Choose Your Controller" in b.section_path]

    assert len(chassis_blocks) > 0, "Expected chassis band blocks"
    assert len(deck_blocks) > 0, "Expected scrub deck band blocks"
    assert len(controller_blocks) > 0, "Expected controller band blocks"

    # 2. Orbital bullets must NEVER land under a model heading (Micro-HD, Mini-HD, Mag-HD)
    orbital_blocks = [
        b for b in blocks
        if "Orbital" in b.text or any("Orbital" in p for p in b.section_path)
    ]
    assert len(orbital_blocks) > 0, "Expected orbital blocks"
    for ob in orbital_blocks:
        for model in ["Micro-HD", "Mini-HD", "Mag-HD"]:
            assert model not in ob.section_path, (
                f"Orbital block '{ob.text}' must not be under model heading {model}"
            )

    # 3. Cylindrical/Disk/Orbital benefits must NEVER appear under Micro/Mini/Mag
    benefit_blocks = [
        b for b in blocks
        if "Benefits" in b.text or any("Benefits" in p for p in b.section_path)
    ]
    assert len(benefit_blocks) > 0, "Expected benefit blocks"
    for bb in benefit_blocks:
        for model in ["Micro-HD", "Mini-HD", "Mag-HD"]:
            assert model not in bb.section_path, (
                f"Benefit block '{bb.text}' must not appear under model {model}"
            )

    # 4. Verify Chassis models are in Band 0
    micro_blocks = [b for b in blocks if "Micro-HD" in b.section_path]
    mini_blocks = [b for b in blocks if "Mini-HD" in b.section_path]
    mag_blocks = [b for b in blocks if "Mag-HD" in b.section_path]
    assert len(micro_blocks) > 0
    assert len(mini_blocks) > 0
    assert len(mag_blocks) > 0


def test_page_3_brush_legend_association_and_asterisks() -> None:
    """Verify Page 3 legend matches circle numbers 1-9 and asterisks for 4 specific items."""
    fixture_path = FIXTURES_DIR / "wordboxes_sample_1_p3.json"
    assert fixture_path.exists(), f"Missing fixture {fixture_path}"

    with open(fixture_path, encoding="utf-8") as f:
        raw_boxes = json.load(f)

    words = [WordBox(**b) for b in raw_boxes]
    items = extract_brush_legend_items(words)

    # Must find all 9 brush items
    assert len(items) == 9, f"Expected 9 legend items, found {len(items)}"

    # Check numbering from 1 to 9
    numbers = [it["number"] for it in items]
    assert numbers == list(range(1, 10))

    # Check asterisks / not_offered_on_cylindrical
    # Exactly four items: Polypropylene, Tufted Pad Driver, Neoprene Pad Driver, Super Grit
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

    # Check non-asterisk items
    regular_items = [it["name"] for it in items if not it["not_offered_on_cylindrical"]]
    expected_regular = ["Nylon", "Tampico", "Tough Grit", "Midi Grit", "Light Grit"]
    assert sorted(regular_items) == sorted(expected_regular)


def test_page_4_cutaway_labels_ast_ingestion() -> None:
    """Verify that Docling AST tree ingestion captures all 21 cutaway labels."""
    fixture_path = FIXTURES_DIR / "tree_sample_1_p4_texts.json"
    assert fixture_path.exists(), f"Missing fixture {fixture_path}"

    with open(fixture_path, encoding="utf-8") as f:
        tree_dict = json.load(f)

    word_boxes = ingest_ast_text_nodes(tree_dict, page_height=650.0)
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
    # Column 1 (x: 50 to 260)
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
    """Verify that RapidOCR word boxes from scanned fixtures load and process cleanly."""
    for p_num in [2, 3, 4, 11]:
        fixture_path = FIXTURES_DIR / f"wordboxes_sample_1_scanned_p{p_num}.json"
        assert fixture_path.exists(), f"Missing fixture {fixture_path}"

        with open(fixture_path, encoding="utf-8") as f:
            raw_boxes = json.load(f)

        words = [WordBox(**b) for b in raw_boxes]
        assert len(words) > 0, f"Expected word boxes for scanned page {p_num}"

        # Group into lines
        lines = group_words_into_lines(words)
        assert len(lines) > 0

        # Detect bands
        bands = detect_horizontal_bands(lines, page_width=792.0, page_height=612.0)
        assert len(bands) > 0
