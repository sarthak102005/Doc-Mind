"""Reading order reconstruction and horizontal banding module.

Implements a unified WordBox abstraction, detects horizontal bands (full-width headings
and vertical whitespace gaps), clusters columns within each band, outputs content
band-by-band, and propagates section paths to chunks.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field


class WordBox(BaseModel):
    """Unified word or text element with normalized bounding box."""

    text: str = Field(..., description="Text content")
    l: float = Field(..., description="Left coordinate (x0)")
    t: float = Field(..., description="Top coordinate (y0)")
    r: float = Field(..., description="Right coordinate (x1)")
    b: float = Field(..., description="Bottom coordinate (y1)")
    page: int = Field(default=1, description="1-indexed page number")
    font_size: float = Field(default=10.0, description="Approximate font size in points")
    coord_origin: str = Field(default="TOPLEFT", description="Coordinate origin (TOPLEFT or BOTTOMLEFT)")

    @property
    def width(self) -> float:
        return max(0.0, self.r - self.l)

    @property
    def height(self) -> float:
        return max(0.0, self.b - self.t)

    @property
    def mid_x(self) -> float:
        return (self.l + self.r) / 2.0

    @property
    def mid_y(self) -> float:
        return (self.t + self.b) / 2.0


class ReadingOrderBlock(BaseModel):
    """An ordered block of text representing a line, paragraph, or column section."""

    text: str
    section_path: list[str] = Field(default_factory=list)
    band_index: int = 0
    column_index: int = 0
    l: float
    t: float
    r: float
    b: float
    word_count: int = 0


def normalize_coords_to_topleft(
    boxes: list[WordBox], page_height: float
) -> list[WordBox]:
    """Convert any bottom-left origin boxes (Docling) to standard top-left origin."""
    normalized: list[WordBox] = []
    for w in boxes:
        if "BOTTOMLEFT" in w.coord_origin.upper():
            # In bottom-left: t is distance from bottom, b is lower bound
            # top-left y_top = page_height - b_bottomleft, y_bot = page_height - t_bottomleft
            top_y = page_height - max(w.t, w.b)
            bot_y = page_height - min(w.t, w.b)
            normalized.append(
                WordBox(
                    text=w.text,
                    l=w.l,
                    t=round(top_y, 2),
                    r=w.r,
                    b=round(bot_y, 2),
                    page=w.page,
                    font_size=w.font_size,
                    coord_origin="TOPLEFT",
                )
            )
        else:
            normalized.append(w)
    return normalized


def group_words_into_lines(
    words: list[WordBox], max_x_gap: float = 25.0, y_tolerance: float = 5.0
) -> list[dict[str, Any]]:
    """Group WordBoxes sharing a baseline into line fragments.

    Crucially respects horizontal spacing: if two words on the same baseline have
    a horizontal gap > max_x_gap, they belong to different columns/fragments.
    """
    if not words:
        return []

    # 1. Bucket words by vertical baseline
    y_buckets: list[list[WordBox]] = []
    for w in sorted(words, key=lambda x: (x.t, x.l)):
        placed = False
        for bucket in y_buckets:
            ref = bucket[0]
            if abs(w.mid_y - ref.mid_y) <= y_tolerance or abs(w.t - ref.t) <= y_tolerance:
                bucket.append(w)
                placed = True
                break
        if not placed:
            y_buckets.append([w])

    # 2. Within each bucket, split words across column gaps into separate line fragments
    line_fragments: list[list[WordBox]] = []
    for bucket in y_buckets:
        sorted_bucket = sorted(bucket, key=lambda x: x.l)
        curr_frag = [sorted_bucket[0]]
        for w in sorted_bucket[1:]:
            prev_w = curr_frag[-1]
            gap = w.l - prev_w.r
            if 0.0 <= gap <= max_x_gap:
                curr_frag.append(w)
            else:
                line_fragments.append(curr_frag)
                curr_frag = [w]
        line_fragments.append(curr_frag)

    # 3. Format as structured line dictionaries
    formatted_lines: list[dict[str, Any]] = []
    for frag in line_fragments:
        l = min(w.l for w in frag)
        r = max(w.r for w in frag)
        t = min(w.t for w in frag)
        b = max(w.b for w in frag)
        text = " ".join(w.text for w in frag)
        text = re.sub(r"\s+", " ", text).strip()
        formatted_lines.append(
            {
                "text": text,
                "words": frag,
                "l": l,
                "r": r,
                "t": t,
                "b": b,
                "w": r - l,
                "h": b - t,
            }
        )

    # Sort lines from top to bottom
    formatted_lines.sort(key=lambda item: (item["t"], item["l"]))
    return formatted_lines


def detect_horizontal_bands(
    lines: list[dict[str, Any]], page_width: float, page_height: float
) -> list[dict[str, Any]]:
    """Detect horizontal bands based on full-width headings, margin regions, and vertical gaps."""
    if not lines:
        return []

    bands: list[dict[str, Any]] = []
    current_band_lines: list[dict[str, Any]] = []
    current_heading: str | None = None

    for idx, line in enumerate(lines):
        line_text = line["text"]
        is_band_heading = (
            line["h"] >= 30.0
            or line["w"] >= (page_width * 0.35)
            or bool(re.match(r"^(Choose Your\b|Section\b|Chapter\b|Part \d+|View Inside\b)", line_text, re.I))
        )
        is_footer = line["t"] > (page_height * 0.88)

        prev_line = lines[idx - 1] if idx > 0 else None
        large_gap = (line["t"] - prev_line["b"]) > 35.0 if prev_line else False

        gap_trigger = large_gap and len(current_band_lines) >= 3 and not current_heading
        is_new_band = idx > 0 and (is_band_heading or is_footer or gap_trigger)

        if is_new_band and current_band_lines:
            bands.append(
                {
                    "heading": current_heading,
                    "lines": current_band_lines,
                    "t": min(l["t"] for l in current_band_lines),
                    "b": max(l["b"] for l in current_band_lines),
                }
            )
            current_band_lines = []
            current_heading = None

        if is_band_heading and not current_heading:
            current_heading = line_text

        current_band_lines.append(line)

    if current_band_lines:
        bands.append(
            {
                "heading": current_heading,
                "lines": current_band_lines,
                "t": min(l["t"] for l in current_band_lines),
                "b": max(l["b"] for l in current_band_lines),
            }
        )

    return bands


def find_column_gutters(
    lines: list[dict[str, Any]], page_width: float, min_gutter_width: float = 18.0
) -> list[float]:
    """Find vertical gutters (x-dividers) separating columns within a band."""
    if not lines:
        return []

    # Only consider lines that don't span across full width
    candidates = [l for l in lines if (l["r"] - l["l"]) < (page_width * 0.65)]
    if not candidates:
        return []

    intervals = sorted([(l["l"], l["r"]) for l in candidates], key=lambda x: x[0])
    merged: list[list[float]] = []
    for cur_l, cur_r in intervals:
        if not merged:
            merged.append([cur_l, cur_r])
        else:
            prev_l, prev_r = merged[-1]
            if cur_l <= prev_r + 5.0:
                merged[-1][1] = max(prev_r, cur_r)
            else:
                merged.append([cur_l, cur_r])

    gutters: list[float] = []
    for i in range(len(merged) - 1):
        gap_start = merged[i][1]
        gap_end = merged[i + 1][0]
        if (gap_end - gap_start) >= min_gutter_width:
            gutters.append((gap_start + gap_end) / 2.0)

    return gutters


def cluster_band_into_columns(
    lines: list[dict[str, Any]], page_width: float
) -> list[list[dict[str, Any]]]:
    """Cluster lines within a band into distinct vertical columns using gutter discovery."""
    if len(lines) <= 1:
        return [lines]

    gutters = find_column_gutters(lines, page_width)
    if not gutters:
        # Single column band
        return [sorted(lines, key=lambda l: (l["t"], l["l"]))]

    # Distribute lines into column bins based on mid_x
    num_cols = len(gutters) + 1
    bins: list[list[dict[str, Any]]] = [[] for _ in range(num_cols)]

    for line in lines:
        mid_x = (line["l"] + line["r"]) / 2.0
        # Determine column index by bisecting gutters
        col_idx = 0
        for g in gutters:
            if mid_x > g:
                col_idx += 1
            else:
                break
        bins[col_idx].append(line)

    columns = [sorted(b, key=lambda l: (l["t"], l["l"])) for b in bins if b]
    return columns


def reconstruct_reading_order(
    words: list[WordBox],
    page_width: float = 792.0,
    page_height: float = 612.0,
) -> list[ReadingOrderBlock]:
    """Reconstruct reading order using horizontal bands and intra-band column clustering."""
    if not words:
        return []

    # 1. Normalize coordinates
    norm_words = normalize_coords_to_topleft(words, page_height)

    # 2. Group into lines respecting column boundaries
    lines = group_words_into_lines(norm_words)

    # 3. Detect horizontal bands
    bands = detect_horizontal_bands(lines, page_width, page_height)

    output_blocks: list[ReadingOrderBlock] = []

    for b_idx, band in enumerate(bands):
        band_heading = band.get("heading")
        section_prefix = [band_heading] if band_heading else []

        # Separate band heading line itself from body lines
        heading_line = next((l for l in band["lines"] if l["text"] == band_heading), None)
        body_lines = [l for l in band["lines"] if l is not heading_line]

        # First emit the band heading block
        if heading_line:
            output_blocks.append(
                ReadingOrderBlock(
                    text=heading_line["text"],
                    section_path=list(section_prefix),
                    band_index=b_idx,
                    column_index=0,
                    l=heading_line["l"],
                    t=heading_line["t"],
                    r=heading_line["r"],
                    b=heading_line["b"],
                    word_count=len(heading_line["words"]),
                )
            )

        # 4. Cluster remaining lines into columns inside this band
        columns = cluster_band_into_columns(body_lines, page_width)

        for c_idx, col_lines in enumerate(columns):
            current_section_path = list(section_prefix)

            for line in col_lines:
                text = line["text"]
                subheading_pattern = (
                    r"^(Micro-HD|Mini-HD|Mag-HD|Cylindrical Benefits|"
                    r"Disk Benefits|Orbital Benefits|Military Grade|Touch Screen)"
                )
                is_subheading = (
                    bool(re.match(subheading_pattern, text))
                    or text in ["Applications", "Size Comparison"]
                )

                if is_subheading:
                    current_section_path = list(section_prefix) + [text]

                output_blocks.append(
                    ReadingOrderBlock(
                        text=text,
                        section_path=list(current_section_path),
                        band_index=b_idx,
                        column_index=c_idx,
                        l=line["l"],
                        t=line["t"],
                        r=line["r"],
                        b=line["b"],
                        word_count=len(line["words"]),
                    )
                )

    return output_blocks


def extract_brush_legend_items(words: list[WordBox]) -> list[dict[str, Any]]:
    """Extract brush legend lines, associate circled numbers (1-9), and attach asterisk flags."""
    # Filter words to the legend column (x < 380.0, y between 250 and 580)
    legend_words = [w for w in words if w.l < 380.0 and 250.0 <= w.t <= 580.0]

    # Check for footnote on the page
    all_page_text = " ".join(w.text for w in words)
    has_footnote = (
        "*Not offered on Cylindrical" in all_page_text
        or "Not offered on Cylindrical" in all_page_text
    )

    brush_specs = [
        ("Polypropylene", "Polypropylene:", None),
        ("Nylon", "Nylon:", None),
        ("Tampico", "Tampico:", None),
        ("Tufted Pad Driver", "Tufted", None),
        ("Neoprene Pad Driver", "Neoprene", None),
        ("Super Grit", "Super", None),
        ("Tough Grit", "Tough", None),
        ("Midi Grit", "Midi", None),
        ("Light Grit", "Light", 500.0),
    ]

    items: list[dict[str, Any]] = []

    for idx, (name, lead_token, min_y) in enumerate(brush_specs, 1):
        matched = [
            w for w in legend_words
            if lead_token in w.text and (min_y is None or w.t >= min_y)
        ]
        if not matched:
            continue
        item_y = min(w.t for w in matched)
        item_b = max(w.b for w in matched)

        # Gather all words on this legend line
        row_words = [
            w for w in legend_words
            if abs(w.t - item_y) <= 12.0 or abs(w.b - item_b) <= 12.0
        ]
        row_words = sorted(row_words, key=lambda w: w.l)

        has_asterisk = any(w.text == "*" for w in row_words)
        full_text = " ".join(w.text for w in row_words)

        items.append(
            {
                "number": idx,
                "name": name,
                "full_text": full_text,
                "has_asterisk": has_asterisk,
                "not_offered_on_cylindrical": has_asterisk and has_footnote,
                "bbox": {
                    "l": min(w.l for w in row_words),
                    "t": min(w.t for w in row_words),
                    "r": max(w.r for w in row_words),
                    "b": max(w.b for w in row_words),
                },
            }
        )

    return items


def ingest_ast_text_nodes(tree_dict: dict[str, Any], page_height: float = 650.0) -> list[WordBox]:
    """Ingest all text items from Docling AST tree nodes with bounding boxes."""
    word_boxes: list[WordBox] = []
    texts = tree_dict.get("texts", [])

    for item in texts:
        text_content = item.get("text", "").strip()
        if not text_content:
            continue

        prov_list = item.get("prov", [])
        if prov_list and "bbox" in prov_list[0]:
            bb = prov_list[0]["bbox"]
            word_boxes.append(
                WordBox(
                    text=text_content,
                    l=round(float(bb.get("l", 0.0)), 2),
                    t=round(float(bb.get("t", 0.0)), 2),
                    r=round(float(bb.get("r", 0.0)), 2),
                    b=round(float(bb.get("b", 0.0)), 2),
                    page=int(prov_list[0].get("page_no", 1)),
                    coord_origin=str(bb.get("coord_origin", "BOTTOMLEFT")),
                )
            )
        else:
            word_boxes.append(
                WordBox(
                    text=text_content,
                    l=0.0,
                    t=0.0,
                    r=100.0,
                    b=20.0,
                    page=1,
                    coord_origin="TOPLEFT",
                )
            )

    return normalize_coords_to_topleft(word_boxes, page_height)
